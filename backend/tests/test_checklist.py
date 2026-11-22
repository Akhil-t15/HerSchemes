from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.checklist import build_checklist, get_checklist
from app.db import Base
from app.main import app, get_db
from app.models import Scheme, SchemeDocument, SchemeRule

OFFICIAL_URL = "https://example.gov.in/apply"
TELUGU_UDYAM = "ఉద్యమ్ రిజిస్ట్రేషన్"
TELUGU_MEESEVA = "మీసేవ సర్టిఫికేట్"


def _make_session_factory(scheme_rows=None, documents=None, rules=None):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    session = TestSession()
    session.add_all(scheme_rows or [])
    session.commit()
    session.add_all(documents or [])
    session.add_all(rules or [])
    session.commit()
    session.close()
    return TestSession


def _override(TestSession):
    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _full_setup():
    """Published scheme with a free Udyam paper, a paid MeeSeva certificate,
    apply steps in EN/TE, plus a draft scheme for the 404 check."""
    scheme = Scheme(
        slug="chk-pub",
        name_en="Checklist Scheme",
        name_te="చెక్లిస్ట్ పథకం",
        level="state",
        official_url=OFFICIAL_URL,
        status="published",
    )
    draft = Scheme(
        slug="chk-draft", name_en="Draft Checklist", level="state", status="draft"
    )
    TestSession = _make_session_factory(scheme_rows=[scheme, draft])

    session = TestSession()
    pub = session.query(Scheme).filter(Scheme.slug == "chk-pub").one()
    session.add_all(
        [
            SchemeDocument(
                scheme_id=pub.id,
                title_en="Udyam Registration",
                title_te=TELUGU_UDYAM,
                fee_amount=0,
                currency="INR",
                is_free=True,
                needs_verification=False,
            ),
            SchemeDocument(
                scheme_id=pub.id,
                title_en="MeeSeva Caste Certificate",
                title_te=TELUGU_MEESEVA,
                fee_amount=100,
                currency="INR",
                processing_days=7,
                is_free=False,
                needs_verification=False,
            ),
            SchemeRule(
                scheme_id=pub.id,
                rule_key="apply_steps_en",
                rule_value=["Visit the portal", "Submit the form"],
                needs_verification=False,
            ),
            SchemeRule(
                scheme_id=pub.id,
                rule_key="apply_steps_te",
                rule_value=["పోర్టల్ సందర్శించండి", "ఫారం సమర్పించండి"],
                needs_verification=False,
            ),
        ]
    )
    session.commit()
    session.close()
    return TestSession


def test_free_and_paid_papers_are_grouped():
    TestSession = _full_setup()
    client = _override(TestSession)
    try:
        r = client.get("/api/schemes/chk-pub/checklist")
        assert r.status_code == 200
        body = r.json()

        udyam = [p for p in body["free_papers"] if p["title_en"] == "Udyam Registration"]
        assert len(udyam) == 1
        assert udyam[0]["fee_amount"] == 0

        paid = [
            c
            for c in body["meeseva_certificates"]
            if c["title_en"] == "MeeSeva Caste Certificate"
        ]
        assert len(paid) == 1
        assert paid[0]["processing_days"] == 7
        assert paid[0]["fee_amount"] == 100
    finally:
        app.dependency_overrides.clear()


def test_section_items_carry_bilingual_titles():
    TestSession = _full_setup()
    client = _override(TestSession)
    try:
        body = client.get("/api/schemes/chk-pub/checklist").json()
        items = body["free_papers"] + body["meeseva_certificates"]
        assert items
        for item in items:
            assert "title_en" in item
            assert "title_te" in item
        titles_te = {item["title_te"] for item in items}
        assert TELUGU_UDYAM in titles_te
        assert TELUGU_MEESEVA in titles_te
    finally:
        app.dependency_overrides.clear()


def test_where_to_apply_uses_official_url_and_rule_steps():
    TestSession = _full_setup()
    client = _override(TestSession)
    try:
        body = client.get("/api/schemes/chk-pub/checklist").json()
        apply = body["where_to_apply"]
        assert apply["official_url"] == OFFICIAL_URL
        assert apply["steps_en"] == ["Visit the portal", "Submit the form"]
        assert apply["steps_te"] == ["పోర్టల్ సందర్శించండి", "ఫారం సమర్పించండి"]
        assert apply["needs_verification"] is False
    finally:
        app.dependency_overrides.clear()


def test_draft_scheme_returns_404():
    TestSession = _full_setup()
    client = _override(TestSession)
    try:
        r = client.get("/api/schemes/chk-draft/checklist")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_unknown_slug_returns_404():
    TestSession = _full_setup()
    client = _override(TestSession)
    try:
        r = client.get("/api/schemes/does-not-exist/checklist")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_query_params_are_not_echoed_back():
    TestSession = _full_setup()
    client = _override(TestSession)
    try:
        r = client.get("/api/schemes/chk-pub/checklist?aadhaar=123456789012")
        assert r.status_code == 200
        assert "123456789012" not in r.text
    finally:
        app.dependency_overrides.clear()


def test_scheme_without_documents_returns_empty_lists():
    scheme = Scheme(
        slug="chk-empty",
        name_en="Empty Scheme",
        level="central",
        official_url=OFFICIAL_URL,
        status="published",
    )
    TestSession = _make_session_factory(scheme_rows=[scheme])

    session = TestSession()
    try:
        result = get_checklist(session, "chk-empty")
        assert result is not None
        assert result["free_papers"] == []
        assert result["meeseva_certificates"] == []
    finally:
        session.close()

    # build_checklist directly, with no documents and no rules
    bare = Scheme(slug="bare", name_en="Bare", level="state", status="published")
    built = build_checklist(bare, [], [])
    assert built["free_papers"] == []
    assert built["meeseva_certificates"] == []
    assert built["where_to_apply"]["steps_en"] == []
    assert built["where_to_apply"]["steps_te"] == []
