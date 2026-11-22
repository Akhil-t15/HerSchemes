import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import PartnerAccount, PartnerLead, Scheme, ServiceSession

client = TestClient(app)

ADMIN_TOKEN = "test-admin-token"
ADMIN_AUTH = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("PARTNER_SESSION_SECRET", "test-partner-secret")


@pytest.fixture
def scheme():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    slug = f"test-partner-{uuid.uuid4().hex[:8]}"
    s = Scheme(slug=slug, name_en="Partner Test Scheme", level="state", status="published")
    db.add(s)
    db.commit()
    db.close()
    yield slug

    db = SessionLocal()
    db.query(PartnerLead).filter(PartnerLead.scheme_slug == slug).delete()
    db.query(Scheme).filter(Scheme.slug == slug).delete()
    db.commit()
    db.close()


@pytest.fixture
def accounts():
    created = []
    yield created
    db = SessionLocal()
    for username in created:
        db.query(PartnerAccount).filter(PartnerAccount.username == username).delete()
    db.commit()
    db.close()


def _make_account(role, accounts):
    username = f"test-{role}-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/admin/partner-accounts",
        json={
            "username": username,
            "password": PASSWORD,
            "role": role,
            "org_name": f"Test {role} org",
        },
        headers=ADMIN_AUTH,
    )
    assert r.status_code == 200, r.text
    accounts.append(username)
    return username


def _login(username):
    r = client.post("/api/partner/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _lead_count(slug):
    db = SessionLocal()
    try:
        return db.query(PartnerLead).filter(PartnerLead.scheme_slug == slug).count()
    finally:
        db.close()


# ---- opt-in lead capture ----

def test_opt_out_stores_nothing_and_returns_200(scheme):
    r = client.post(
        "/api/leads",
        json={"scheme_slug": scheme, "phone": "9876543210", "opt_in": False},
    )
    assert r.status_code == 200
    assert r.json() == {"stored": False}
    assert _lead_count(scheme) == 0


def test_opt_in_default_is_off(scheme):
    r = client.post("/api/leads", json={"scheme_slug": scheme, "phone": "9876543210"})
    assert r.status_code == 200
    assert _lead_count(scheme) == 0


def test_opt_in_stores_lead_with_consent_timestamp(scheme):
    r = client.post(
        "/api/leads",
        json={"scheme_slug": scheme, "phone": "+91 98765-43210", "opt_in": True},
    )
    assert r.status_code == 200
    assert r.json() == {"stored": True}
    db = SessionLocal()
    try:
        lead = db.query(PartnerLead).filter(PartnerLead.scheme_slug == scheme).one()
        assert lead.phone == "9876543210"
        assert lead.consent_at is not None
    finally:
        db.close()


@pytest.mark.parametrize(
    "phone",
    [
        "123456789012",  # Aadhaar-shaped (starts 1, not a mobile)
        "ABCDE1234F",  # PAN-shaped
        "12345678901234567",  # bank-account-shaped
        "1234",  # too short
    ],
)
def test_sensitive_or_non_mobile_numbers_rejected(scheme, phone):
    r = client.post("/api/leads", json={"scheme_slug": scheme, "phone": phone, "opt_in": True})
    assert r.status_code == 422
    assert _lead_count(scheme) == 0


def test_unknown_scheme_returns_404(scheme):
    r = client.post(
        "/api/leads",
        json={"scheme_slug": "no-such-scheme-xyz", "phone": "9876543210", "opt_in": True},
    )
    assert r.status_code == 404


# ---- purge ----

def test_purge_removes_leads_older_than_30_days(scheme):
    db = SessionLocal()
    old = datetime.utcnow() - timedelta(days=31)
    db.add(PartnerLead(scheme_slug=scheme, phone="9000000001", consent_at=old, created_at=old))
    db.add(PartnerLead(scheme_slug=scheme, phone="9000000002", consent_at=datetime.utcnow()))
    db.commit()
    db.close()

    r = client.post("/api/admin/leads/purge", headers=ADMIN_AUTH)
    assert r.status_code == 200
    assert r.json()["deleted"] >= 1

    db = SessionLocal()
    try:
        phones = [l.phone for l in db.query(PartnerLead).filter(PartnerLead.scheme_slug == scheme)]
    finally:
        db.close()
    assert phones == ["9000000002"]


def test_purge_endpoint_requires_admin(scheme):
    assert client.post("/api/admin/leads/purge").status_code == 401


# ---- accounts and login ----

def test_admin_creates_account_without_exposing_hash(accounts):
    username = f"test-partner-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/admin/partner-accounts",
        json={"username": username, "password": PASSWORD, "role": "partner", "org_name": "Org"},
        headers=ADMIN_AUTH,
    )
    accounts.append(username)
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "partner"
    assert "password_hash" not in body and "password" not in body


def test_account_creation_requires_admin(accounts):
    r = client.post(
        "/api/admin/partner-accounts",
        json={"username": "x-no-admin", "password": PASSWORD, "role": "partner", "org_name": "O"},
    )
    assert r.status_code == 401


def test_account_creation_rejects_unknown_role(accounts):
    r = client.post(
        "/api/admin/partner-accounts",
        json={"username": "x-bad-role", "password": PASSWORD, "role": "admin", "org_name": "O"},
        headers=ADMIN_AUTH,
    )
    assert r.status_code == 422


def test_wrong_password_returns_401(accounts):
    username = _make_account("partner", accounts)
    r = client.post("/api/partner/login", json={"username": username, "password": "nope-nope-nope"})
    assert r.status_code == 401


# ---- partner leads endpoint ----

def test_partner_lists_only_phone_scheme_and_consent(scheme, accounts):
    client.post("/api/leads", json={"scheme_slug": scheme, "phone": "9876543210", "opt_in": True})
    username = _make_account("partner", accounts)
    r = client.get("/api/partner/leads", headers=_login(username))
    assert r.status_code == 200
    mine = [row for row in r.json() if row["scheme_slug"] == scheme]
    assert len(mine) == 1
    assert set(mine[0].keys()) == {"phone", "scheme_slug", "consent_at"}
    assert mine[0]["phone"] == "9876543210"


def test_sponsor_token_cannot_read_partner_leads(accounts):
    username = _make_account("sponsor", accounts)
    r = client.get("/api/partner/leads", headers=_login(username))
    assert r.status_code == 403


def test_partner_leads_without_token_returns_401():
    assert client.get("/api/partner/leads").status_code == 401


def test_tampered_token_returns_401(accounts):
    username = _make_account("partner", accounts)
    token = _login(username)["Authorization"][len("Bearer "):]
    body, sig = token.rsplit(".", 1)
    forged = f"{body}.{'0' * len(sig)}"
    r = client.get("/api/partner/leads", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


# ---- sponsor impact ----

def test_impact_counts_distinct_sessions_and_aggregates_only(accounts):
    key_a = f"test-sess-{uuid.uuid4().hex[:8]}"
    key_b = f"test-sess-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    before = client.get("/api/sponsor/impact", headers=ADMIN_AUTH).json()
    db.add_all(
        [
            ServiceSession(session_key=key_a, scheme_slug="test-impact-x", district="TestDistrictA"),
            ServiceSession(session_key=key_a, scheme_slug="test-impact-x", district="TestDistrictA"),
            ServiceSession(session_key=key_b, scheme_slug="test-impact-x", district="TestDistrictA",
                           cost_amount=100),
        ]
    )
    db.commit()
    db.close()

    username = _make_account("sponsor", accounts)
    r = client.get("/api/sponsor/impact", headers=_login(username))
    assert r.status_code == 200
    body = r.json()
    assert body["total_women_helped"] == before["total_women_helped"] + 2
    assert set(body.keys()) == {
        "total_women_helped",
        "top_districts",
        "top_schemes",
        "average_cost_per_session",
        "districts_recorded",
        "costs_recorded",
    }
    assert body["costs_recorded"] is True

    db = SessionLocal()
    try:
        db.query(ServiceSession).filter(ServiceSession.session_key.in_([key_a, key_b])).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def test_impact_rejects_partner_token(accounts):
    username = _make_account("partner", accounts)
    r = client.get("/api/sponsor/impact", headers=_login(username))
    assert r.status_code == 403


def test_impact_without_token_returns_401():
    assert client.get("/api/sponsor/impact").status_code == 401
