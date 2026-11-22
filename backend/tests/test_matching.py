import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db import Base
from app.main import app, get_db
from app.matching import match_schemes
from app.models import Scheme, SchemeRule

NOW = datetime(2025, 1, 31, 12, 0, 0)
FRESH = NOW - timedelta(days=1)
OLD = NOW - timedelta(days=45)

CONFLICT_EN = "PMEGP and PM Vishwakarma cannot both be availed for the same unit."
CONFLICT_TE = "PMEGP mariu PM Vishwakarma rendu okesari teesukoleru."

ANSWERS = {
    "business_type": "manufacturing",
    "location_type": "rural",
    "shg_member": True,
    "loan_amount_band": "under_1_lakh",
}


def _add(session, slug, level, last_verified_at, rules=()):
    scheme = Scheme(
        slug=slug,
        name_en=slug,
        name_te=None,
        level=level,
        lane=level,
        official_url="https://example.test/" + slug,
        last_verified_at=last_verified_at,
        status="published",
    )
    scheme.rules = [
        SchemeRule(rule_key=key, rule_value=value, needs_verification=True)
        for key, value in rules
    ]
    session.add(scheme)
    session.commit()
    return scheme


def _setup():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    _add(
        session,
        "pmegp",
        "central",
        FRESH,
        [
            ("business_type", {"op": "in", "value": ["manufacturing", "services"]}),
            (
                "conflicts_with",
                {
                    "slugs": ["pm-vishwakarma"],
                    "explanation_en": CONFLICT_EN,
                    "explanation_te": CONFLICT_TE,
                },
            ),
        ],
    )
    _add(
        session,
        "pm-vishwakarma",
        "central",
        FRESH,
        [("business_type", {"op": "in", "value": ["manufacturing", "services"]})],
    )
    _add(
        session,
        "test-state-scheme",
        "state",
        FRESH,
        [("location_type", {"op": "equals", "value": "rural"})],
    )
    _add(
        session,
        "test-addon-old",
        "addon",
        OLD,
        [("shg_member", {"op": "equals", "value": True})],
    )
    _add(
        session,
        "test-mudra-small",
        "central",
        FRESH,
        [("loan_amount_band", {"op": "in", "value": ["under_1_lakh"]})],
    )
    _add(
        session,
        "test-mudra-medium",
        "central",
        FRESH,
        [("loan_amount_band", {"op": "in", "value": ["1_to_10_lakh"]})],
    )
    _add(
        session,
        "test-needs-info",
        "central",
        FRESH,
        [("stage", {"op": "equals", "value": "new"})],
    )
    return session


def _slugs(lanes, lane):
    return [m["slug"] for m in lanes[lane]]


def _find(lanes, slug):
    for lane in lanes.values():
        for m in lane:
            if m["slug"] == slug:
                return m
    return None


def test_lanes_grouped_by_level_in_order():
    session = _setup()
    result = match_schemes(session, ANSWERS, NOW)
    assert list(result["lanes"].keys()) == ["state", "central", "addon"]
    assert _slugs(result["lanes"], "state") == ["test-state-scheme"]
    assert _slugs(result["lanes"], "addon") == ["test-addon-old"]
    assert "pmegp" in _slugs(result["lanes"], "central")
    assert "pm-vishwakarma" in _slugs(result["lanes"], "central")


def test_failed_rule_excludes_scheme():
    session = _setup()
    result = match_schemes(session, ANSWERS, NOW)
    assert _find(result["lanes"], "test-mudra-medium") is None


def test_conflict_alert_from_db_row():
    session = _setup()
    result = match_schemes(session, ANSWERS, NOW)
    pairs = [
        c for c in result["conflicts"] if set(c["slugs"]) == {"pmegp", "pm-vishwakarma"}
    ]
    assert len(pairs) == 1
    assert pairs[0]["pick_one"] is True
    assert pairs[0]["explanation_en"] == CONFLICT_EN
    assert pairs[0]["explanation_te"] == CONFLICT_TE


def test_loan_band_under_1_lakh_selects_small_only():
    session = _setup()
    result = match_schemes(session, ANSWERS, NOW)
    assert _find(result["lanes"], "test-mudra-small") is not None
    assert _find(result["lanes"], "test-mudra-medium") is None


def test_loan_band_1_to_10_lakh_selects_medium_only():
    session = _setup()
    answers = dict(ANSWERS, loan_amount_band="1_to_10_lakh")
    result = match_schemes(session, answers, NOW)
    assert _find(result["lanes"], "test-mudra-medium") is not None
    assert _find(result["lanes"], "test-mudra-small") is None


def test_stale_flag_true_for_old_verification():
    session = _setup()
    result = match_schemes(session, ANSWERS, NOW)
    assert _find(result["lanes"], "test-addon-old")["stale"] is True


def test_stale_flag_false_for_recent_verification():
    session = _setup()
    result = match_schemes(session, ANSWERS, NOW)
    assert _find(result["lanes"], "test-state-scheme")["stale"] is False


def test_likely_eligible_status_when_rules_pass():
    session = _setup()
    result = match_schemes(session, ANSWERS, NOW)
    assert _find(result["lanes"], "pmegp")["status"] == "Likely Eligible"


def test_needs_more_info_when_answer_key_missing():
    session = _setup()
    result = match_schemes(session, ANSWERS, NOW)
    match = _find(result["lanes"], "test-needs-info")
    assert match is not None
    assert match["status"] == "Needs More Info"


def test_guaranteed_never_appears_in_output():
    session = _setup()
    result = match_schemes(session, ANSWERS, NOW)
    assert "Guaranteed" not in json.dumps(result)


def test_match_route_returns_200():
    session = _setup()

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    try:
        client = TestClient(app)
        response = client.get(
            "/api/match",
            params={
                "business_type": "manufacturing",
                "location_type": "rural",
                "district": "Warangal",
                "shg_member": "true",
                "stage": "new",
                "loan_amount_band": "under_1_lakh",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"lanes", "conflicts"}
        assert "Guaranteed" not in response.text
    finally:
        app.dependency_overrides.clear()
