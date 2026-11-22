"""Admin console core API for HerScheme (Module 7).

Rule-change proposals are stored here, but nothing touches scheme rules until an
admin approves a proposal. Every approve or dismiss writes an AuditLog row.
"""
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.admin_auth import require_admin
from app.db import SessionLocal
from app.models import AuditLog, RuleProposal, Scheme, SchemeRule

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


def get_db():
    # Local copy of main.get_db so this module does not import main (avoids a cycle).
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ChangeIn(BaseModel):
    rule_key: str
    new_value: Any


class ProposalIn(BaseModel):
    scheme_slug: str
    source_text: str = Field(max_length=20000)
    changes: List[ChangeIn]


def _current_rule(scheme: Scheme, rule_key: str):
    for rule in scheme.rules:
        if rule.rule_key == rule_key:
            return rule
    return None


@router.post("/proposals")
def create_proposal(body: ProposalIn, db: Session = Depends(get_db)):
    scheme = db.query(Scheme).filter(Scheme.slug == body.scheme_slug).first()
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found")

    changes = []
    for change in body.changes:
        rule = _current_rule(scheme, change.rule_key)
        old_value = rule.rule_value if rule is not None else None
        if change.new_value != old_value:
            changes.append(
                {
                    "rule_key": change.rule_key,
                    "old_value": old_value,
                    "new_value": change.new_value,
                }
            )

    if not changes:
        return {"changed": False, "changes": []}

    proposal = RuleProposal(
        scheme_id=scheme.id,
        source_text=body.source_text,
        changes_json=changes,
        status="pending",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return {"changed": True, "proposal_id": proposal.id, "changes": changes}


@router.get("/proposals")
def list_pending_proposals(db: Session = Depends(get_db)):
    rows = (
        db.query(RuleProposal, Scheme.slug)
        .join(Scheme, Scheme.id == RuleProposal.scheme_id)
        .filter(RuleProposal.status == "pending")
        .order_by(RuleProposal.id)
        .all()
    )
    return [
        {
            "id": proposal.id,
            "scheme_slug": slug,
            "created_at": proposal.created_at.isoformat() if proposal.created_at else None,
            "changes": proposal.changes_json,
        }
        for proposal, slug in rows
    ]


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: int, db: Session = Depends(get_db)):
    proposal = db.get(RuleProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="Proposal is not pending")

    scheme = db.get(Scheme, proposal.scheme_id)
    before = {}
    after = {}
    for change in proposal.changes_json:
        rule_key = change["rule_key"]
        new_value = change["new_value"]
        rule = _current_rule(scheme, rule_key)
        before[rule_key] = rule.rule_value if rule is not None else None
        after[rule_key] = new_value
        if rule is None:
            db.add(SchemeRule(scheme_id=scheme.id, rule_key=rule_key, rule_value=new_value))
        else:
            rule.rule_value = new_value

    scheme.last_verified_at = datetime.now(timezone.utc)
    proposal.status = "approved"
    db.add(
        AuditLog(
            actor="admin",
            action="approve_proposal",
            before_json=before,
            after_json=after,
        )
    )
    db.commit()
    return {"id": proposal.id, "status": proposal.status, "scheme_slug": scheme.slug}


@router.post("/proposals/{proposal_id}/dismiss")
def dismiss_proposal(proposal_id: int, db: Session = Depends(get_db)):
    proposal = db.get(RuleProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="Proposal is not pending")

    proposal.status = "dismissed"
    db.add(
        AuditLog(
            actor="admin",
            action="dismiss_proposal",
            before_json={"proposal_id": proposal.id, "status": "pending"},
            after_json={"proposal_id": proposal.id, "status": "dismissed"},
        )
    )
    db.commit()
    return {"id": proposal.id, "status": proposal.status}


class SchemeIn(BaseModel):
    slug: Optional[str] = None
    name_en: str
    name_te: Optional[str] = None
    level: str = "state"
    lane: Optional[str] = None
    description: Optional[str] = None
    official_url: Optional[str] = None
    status: str = "published"
    rules: Optional[List[ChangeIn]] = None


@router.post("/schemes")
def create_scheme(body: SchemeIn, db: Session = Depends(get_db)):
    import re
    slug = body.slug
    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", body.name_en.lower()).strip("-")
    if db.query(Scheme).filter(Scheme.slug == slug).first():
        slug = f"{slug}-{int(datetime.now().timestamp())}"

    scheme = Scheme(
        slug=slug,
        name_en=body.name_en,
        name_te=body.name_te or body.name_en,
        level=body.level,
        lane=body.lane or "general",
        description=body.description or "",
        official_url=body.official_url or "https://telangana.gov.in",
        status=body.status,
        last_verified_at=datetime.now(timezone.utc),
    )
    db.add(scheme)
    db.flush()

    if body.rules:
        for r in body.rules:
            db.add(
                SchemeRule(
                    scheme_id=scheme.id,
                    rule_key=r.rule_key,
                    rule_value=r.new_value,
                    needs_verification=False,
                )
            )

    db.add(
        AuditLog(
            actor="admin",
            action="create_scheme",
            before_json=None,
            after_json={"slug": scheme.slug, "name_en": scheme.name_en},
        )
    )
    db.commit()
    db.refresh(scheme)
    return {
        "id": scheme.id,
        "slug": scheme.slug,
        "name_en": scheme.name_en,
        "name_te": scheme.name_te,
        "status": scheme.status,
    }

