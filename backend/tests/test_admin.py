import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import AuditLog, RuleProposal, Scheme, SchemeRule

client = TestClient(app)

TOKEN = "test-admin-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)


@pytest.fixture
def scheme():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    start_audit_id = db.query(func.max(AuditLog.id)).scalar() or 0
    s = Scheme(
        slug=f"test-admin-{uuid.uuid4().hex[:8]}",
        name_en="Admin Test Scheme",
        level="state",
        status="published",
    )
    s.rules.append(SchemeRule(rule_key="max_loan", rule_value=100000, needs_verification=False))
    db.add(s)
    db.commit()
    info = {"id": s.id, "slug": s.slug}
    db.close()

    yield info

    db = SessionLocal()
    db.query(RuleProposal).filter(RuleProposal.scheme_id == info["id"]).delete()
    db.query(SchemeRule).filter(SchemeRule.scheme_id == info["id"]).delete()
    db.query(Scheme).filter(Scheme.id == info["id"]).delete()
    db.query(AuditLog).filter(AuditLog.id > start_audit_id).delete()
    db.commit()
    db.close()


def _propose(slug, new_value):
    return client.post(
        "/api/admin/proposals",
        json={
            "scheme_slug": slug,
            "source_text": "G.O. test notice",
            "changes": [{"rule_key": "max_loan", "new_value": new_value}],
        },
        headers=AUTH,
    )


def _rule_value(scheme_id):
    db = SessionLocal()
    try:
        rule = db.query(SchemeRule).filter_by(scheme_id=scheme_id, rule_key="max_loan").one()
        return rule.rule_value
    finally:
        db.close()


def _last_verified(scheme_id):
    db = SessionLocal()
    try:
        return db.get(Scheme, scheme_id).last_verified_at
    finally:
        db.close()


def _proposal_count(scheme_id):
    db = SessionLocal()
    try:
        return db.query(RuleProposal).filter(RuleProposal.scheme_id == scheme_id).count()
    finally:
        db.close()


def test_no_admin_token_configured_returns_503(monkeypatch, scheme):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    r = client.get("/api/admin/proposals", headers=AUTH)
    assert r.status_code == 503


def test_empty_admin_token_configured_returns_503(monkeypatch, scheme):
    monkeypatch.setenv("ADMIN_TOKEN", "")
    r = client.get("/api/admin/proposals", headers=AUTH)
    assert r.status_code == 503


def test_missing_token_returns_401(scheme):
    r = client.get("/api/admin/proposals")
    assert r.status_code == 401


def test_wrong_token_returns_401(scheme):
    r = client.get("/api/admin/proposals", headers={"Authorization": "Bearer wrong-token"})
    assert r.status_code == 401


def test_unchanged_value_stores_nothing(scheme):
    r = _propose(scheme["slug"], 100000)
    assert r.status_code == 200
    assert r.json() == {"changed": False, "changes": []}
    assert _proposal_count(scheme["id"]) == 0


def test_real_change_creates_proposal(scheme):
    r = _propose(scheme["slug"], 200000)
    assert r.status_code == 200
    body = r.json()
    assert body["changed"] is True
    assert isinstance(body["proposal_id"], int)
    assert body["changes"] == [
        {"rule_key": "max_loan", "old_value": 100000, "new_value": 200000}
    ]
    assert _proposal_count(scheme["id"]) == 1


def test_approve_applies_value_sets_verified_and_writes_audit(scheme):
    proposal_id = _propose(scheme["slug"], 200000).json()["proposal_id"]
    r = client.post(f"/api/admin/proposals/{proposal_id}/approve", headers=AUTH)
    assert r.status_code == 200
    assert _rule_value(scheme["id"]) == 200000
    assert _last_verified(scheme["id"]) is not None

    db = SessionLocal()
    try:
        audit = (
            db.query(AuditLog)
            .filter(AuditLog.action == "approve_proposal")
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert audit is not None
        assert audit.actor == "admin"
        assert audit.before_json == {"max_loan": 100000}
        assert audit.after_json == {"max_loan": 200000}
    finally:
        db.close()


def test_dismiss_does_not_change_rule_values(scheme):
    proposal_id = _propose(scheme["slug"], 200000).json()["proposal_id"]
    r = client.post(f"/api/admin/proposals/{proposal_id}/dismiss", headers=AUTH)
    assert r.status_code == 200
    assert _rule_value(scheme["id"]) == 100000


def test_approving_twice_returns_409(scheme):
    proposal_id = _propose(scheme["slug"], 200000).json()["proposal_id"]
    first = client.post(f"/api/admin/proposals/{proposal_id}/approve", headers=AUTH)
    assert first.status_code == 200
    second = client.post(f"/api/admin/proposals/{proposal_id}/approve", headers=AUTH)
    assert second.status_code == 409
