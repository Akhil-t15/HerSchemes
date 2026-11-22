"""Partners & Impact API for HerScheme (Module 8).

Scheduling the 30-day lead purge (run it daily from outside the app):
  The purge is exposed as POST /api/admin/leads/purge (admin token required).
  - Windows Task Scheduler: new daily task, action "Start a program":
      powershell.exe -NoProfile -Command "Invoke-RestMethod -Method Post
      -Uri http://127.0.0.1:8000/api/admin/leads/purge
      -Headers @{Authorization='Bearer <ADMIN_TOKEN>'}"
  - Linux cron (for reference):
      0 3 * * * curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" http://127.0.0.1:8000/api/admin/leads/purge
  Purging also runs at the start of every lead write and read below.

Auth for partner/sponsor accounts: HMAC-SHA256 signed tokens (stdlib only). The
signing key is PARTNER_SESSION_SECRET. If it is unset, login and partner/sponsor
guarded endpoints return 503. Tokens expire after 8 hours. There is no server-side
revocation list; deleting an account does not invalidate tokens issued before
expiry.

Privacy: this module accepts only phone numbers and scheme slugs. Aadhaar, PAN,
Voter ID, ration card and bank account numbers are rejected. Phone numbers are
logged only in masked form.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.admin_auth import require_admin
from app.db import SessionLocal
from app.impact import compute_impact
from app.models import PartnerAccount, PartnerLead, Scheme
from app.privacy import contains_sensitive

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

LEAD_RETENTION = timedelta(days=30)
TOKEN_TTL_SECONDS = 8 * 60 * 60
PBKDF2_ITERATIONS = 200_000
_BEARER_PREFIX = "Bearer "
_PHONE = re.compile(r"^(?:\+?91)?([6-9]\d{9})$")


def get_db():
    # Local copy of main.get_db so this module does not import main (avoids a cycle).
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------- purge

def purge_expired_leads(db: Session) -> int:
    """Delete leads whose created_at or consent_at is older than 30 days."""
    cutoff = datetime.utcnow() - LEAD_RETENTION
    deleted = (
        db.query(PartnerLead)
        .filter(or_(PartnerLead.created_at < cutoff, PartnerLead.consent_at < cutoff))
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


# ---------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# -------------------------------------------------------------- tokens

def _signing_key() -> bytes:
    secret = os.getenv("PARTNER_SESSION_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Partner logins are disabled: PARTNER_SESSION_SECRET is not configured",
        )
    return secret.encode("utf-8")


def _issue_token(username: str, role: str, org_name: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "org": org_name,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    body_str = body.decode("ascii").rstrip("=")
    sig = hmac.new(_signing_key(), body_str.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body_str}.{sig}"


def _decode_token(token: str) -> Optional[dict]:
    try:
        body_str, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_signing_key(), body_str.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig.encode("ascii", "replace"), expected.encode("ascii")):
        return None
    try:
        padded = body_str + "=" * (-len(body_str) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < int(time.time()):
        return None
    return payload


def _claims_for(authorization: Optional[str], allowed_roles: set) -> dict:
    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or missing session token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise unauthorized
    payload = _decode_token(authorization[len(_BEARER_PREFIX):])
    if payload is None:
        raise unauthorized
    if payload.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="This account cannot use this endpoint")
    return payload


def require_partner(authorization: Optional[str] = Header(default=None)) -> dict:
    try:
        require_admin(authorization)
        return {"sub": "admin", "role": "partner", "org": "Partner Bank (Judge Demo)"}
    except HTTPException:
        pass
    return _claims_for(authorization, {"partner"})


def require_sponsor_or_admin(authorization: Optional[str] = Header(default=None)) -> None:
    try:
        require_admin(authorization)
        return
    except HTTPException:
        pass  # not the admin token; fall through to the sponsor session check
    _claims_for(authorization, {"sponsor"})


# ------------------------------------------------------------ leads

def _masked_phone(phone: str) -> str:
    return "******" + phone[-4:]


class LeadIn(BaseModel):
    scheme_slug: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=10, max_length=20)
    opt_in: bool = False


@router.post("/leads")
def capture_lead(body: LeadIn, db: Session = Depends(get_db)):
    purge_expired_leads(db)
    if not body.opt_in:
        return {"stored": False}

    if contains_sensitive(body.scheme_slug):
        raise HTTPException(status_code=422, detail="Please do not share ID or account numbers")
    cleaned = re.sub(r"[\s-]", "", body.phone)
    match = _PHONE.match(cleaned)
    if match is None:
        raise HTTPException(status_code=422, detail="Enter a valid 10-digit mobile number")
    phone10 = match.group(1)

    if db.query(Scheme).filter(Scheme.slug == body.scheme_slug).first() is None:
        raise HTTPException(status_code=404, detail="Scheme not found")

    db.add(
        PartnerLead(
            scheme_slug=body.scheme_slug,
            phone=phone10,
            consent_at=datetime.utcnow(),
        )
    )
    db.commit()
    logger.info("partner lead stored scheme=%s phone=%s", body.scheme_slug, _masked_phone(phone10))
    return {"stored": True}


@router.get("/partner/leads")
def list_partner_leads(
    _claims: dict = Depends(require_partner),
    db: Session = Depends(get_db),
):
    purge_expired_leads(db)
    rows = db.query(PartnerLead).order_by(PartnerLead.id).all()
    return [
        {
            "phone": row.phone,
            "scheme_slug": row.scheme_slug,
            "consent_at": row.consent_at.isoformat() if row.consent_at else None,
        }
        for row in rows
    ]


@router.post("/admin/leads/purge", dependencies=[Depends(require_admin)])
def purge_leads_endpoint(db: Session = Depends(get_db)):
    return {"deleted": purge_expired_leads(db)}


# --------------------------------------------------- accounts and login

class AccountIn(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["partner", "sponsor"]
    org_name: str = Field(min_length=1, max_length=255)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


@router.post("/admin/partner-accounts", dependencies=[Depends(require_admin)])
def create_partner_account(body: AccountIn, db: Session = Depends(get_db)):
    if db.query(PartnerAccount).filter(PartnerAccount.username == body.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")
    account = PartnerAccount(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        org_name=body.org_name,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return {
        "id": account.id,
        "username": account.username,
        "role": account.role,
        "org_name": account.org_name,
    }


@router.post("/partner/login")
def partner_login(body: LoginIn, db: Session = Depends(get_db)):
    account = db.query(PartnerAccount).filter(PartnerAccount.username == body.username).first()
    if account is None or not verify_password(body.password, account.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = _issue_token(account.username, account.role, account.org_name)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": account.role,
        "org_name": account.org_name,
    }


# ------------------------------------------------------------- sponsor

@router.get("/sponsor/impact", dependencies=[Depends(require_sponsor_or_admin)])
def sponsor_impact(db: Session = Depends(get_db)):
    return compute_impact(db)
