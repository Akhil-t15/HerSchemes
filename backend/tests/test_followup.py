"""Tests for Module 3 LLM-powered follow-up (app.followup and app.followup_api).

No network: the Groq call is always monkeypatched, and every test runs
against an in-memory SQLite database.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import followup, models  # noqa: F401
from app.db import Base
from app.followup import (
    FACT_KEYS,
    MAX_QUESTION_ROUNDS,
    PRIVACY_WARNING_EN,
    LLMProvider,
    detect_missing_facts,
    find_missing,
    run_followup,
)
from app.followup_api import get_db
from app.main import app
from app.models import Scheme

client = TestClient(app)

AADHAAR_SPACED = "2345 6789 0123"
AADHAAR_DIGITS = "234567890123"
FULL_FACTS = {
    "location": "Guntur",
    "shg_member": "yes",
    "business_status": "new",
    "loan_amount": "200000",
    "past_govt_loan": "no",
}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    # No Groq API key (so no network is ever used) and a large budget.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEYS", raising=False)
    monkeypatch.setattr(followup, "_get_groq_api_keys", lambda: [])
    monkeypatch.setenv("CHAT_DAILY_BUDGET", "100000")


@pytest.fixture(autouse=True)
def seeded_db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    session = TestSession()
    session.add_all(
        [
            Scheme(slug="pub-one", name_en="Published One", level="central", status="published"),
            Scheme(slug="draft-one", name_en="Draft One", level="state", status="draft"),
        ]
    )
    session.commit()
    session.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestSession
    app.dependency_overrides.clear()


def _run(TestSession, **kwargs):
    db = TestSession()
    try:
        return run_followup(db, **kwargs)
    finally:
        db.close()


def _post(**body):
    payload = {"message": "hello", "lang": "en"}
    payload.update(body)
    return client.post("/api/chat/follow-up", json=payload)


# ---------- fallback (no LLM) tests ----------

def test_fallback_asks_first_missing_fact():
    """Without a Groq key the deterministic fallback asks the first missing question."""
    body = _post(message="I want to start a shop").json()
    assert body["done"] is False
    # reply should contain the fallback question
    assert body["reply"] is not None or len(body["questions"]) > 0


def test_all_facts_known_is_done(seeded_db):
    result = _run(
        seeded_db, message="hello", lang="en", known_facts=FULL_FACTS,
        rounds_asked=0, skipped=False
    )
    assert result["done"] is True
    assert result["matches"]


def test_skipped_means_done():
    body = _post(skipped=True, rounds_asked=0).json()
    assert body["done"] is True


def test_rounds_at_cap_is_done():
    body = _post(rounds_asked=MAX_QUESTION_ROUNDS).json()
    assert body["done"] is True


def test_negative_rounds_asked_rejected():
    assert _post(rounds_asked=-1).status_code == 422


def test_endpoint_rejects_unknown_language():
    assert _post(lang="fr").status_code == 422


# ---------- response shape ----------

def test_endpoint_response_keys():
    body = _post(message="hello").json()
    expected_keys = {"reply", "questions", "matches", "masked_text", "done", "known_facts", "warning", "question_key"}
    assert expected_keys == set(body.keys())


# ---------- privacy masking ----------

def test_aadhaar_masked_in_endpoint_output():
    message = f"my aadhaar is {AADHAAR_SPACED} and I want a shop"
    body = _post(message=message).json()
    assert body["masked_text"] == "my aadhaar is [AADHAAR HIDDEN] and I want a shop"
    assert body["warning"] == PRIVACY_WARNING_EN
    raw = json.dumps(body)
    assert AADHAAR_SPACED not in raw
    assert AADHAAR_DIGITS not in raw


# ---------- no guaranteed wording ----------

def test_no_guaranteed_substring_in_any_output():
    cases = [
        {"message": "hello", "lang": "en"},
        {"message": "I want a loan", "lang": "en", "rounds_asked": 1},
        {"message": "", "lang": "en", "skipped": True},
        {"message": "x", "lang": "en", "known_facts": FULL_FACTS},
    ]
    for case in cases:
        body = _post(**case).json()
        assert "guaranteed" not in json.dumps(body).lower()


# ---------- matches ----------

def test_matches_published_only(seeded_db):
    result = _run(
        seeded_db, message="hello", lang="en", known_facts=FULL_FACTS,
        rounds_asked=0, skipped=False
    )
    slugs = [m["slug"] for m in result["matches"]]
    assert "pub-one" in slugs
    assert "draft-one" not in slugs


# ---------- known_facts accumulation ----------

def test_known_facts_returned_in_response():
    body = _post(message="hello", known_facts={"location": "Hyderabad"}).json()
    assert "known_facts" in body
    assert body["known_facts"]["location"] == "Hyderabad"


# ---------- history field accepted ----------

def test_history_accepted():
    body = _post(
        message="warangal",
        history=[
            {"role": "user", "content": "I want to start a tailoring shop"},
            {"role": "assistant", "content": "Which town do you live in?"},
        ],
    ).json()
    assert "reply" in body or "questions" in body


# ---------- legacy compatibility ----------

def test_detect_missing_facts_dict():
    assert detect_missing_facts({}) == list(FACT_KEYS)
    assert detect_missing_facts(FULL_FACTS) == []


def test_find_missing_uses_known_facts():
    missing = find_missing("hello", {"location": "Guntur"})
    assert "location" not in missing
    assert "shg_member" in missing


# ---------- LLM fact parsing ----------

def test_parse_facts_from_llm_response():
    from app.followup import _parse_facts
    llm_text = '''That's great! Warangal is a wonderful place.

```facts
{"location": "Warangal", "shg_member": null, "business_status": "starting new", "loan_amount": null, "past_govt_loan": null}
```'''
    facts = _parse_facts(llm_text)
    assert facts["location"] == "Warangal"
    assert facts["business_status"] == "starting new"
    assert "shg_member" not in facts  # null values not included


def test_clean_response_removes_facts_block():
    from app.followup import _clean_response
    llm_text = '''Hello! How can I help?

```facts
{"location": null}
```'''
    cleaned = _clean_response(llm_text)
    assert "facts" not in cleaned
    assert "Hello! How can I help?" in cleaned


# ---------- multi-turn progression test ----------

def test_multiturn_flow_progresses_without_repeating_questions():
    # Turn 1: user says "I want to start a tailoring shop"
    r1 = _post(message="I want to start a tailoring shop", known_facts={}, rounds_asked=0).json()
    assert r1["done"] is False
    assert r1["known_facts"].get("business_status") == "new business"
    # Should ask for location
    reply_lower = r1["reply"].lower()
    assert any(k in reply_lower for k in ("village", "town", "where", "location", "district", "place"))
    assert r1["question_key"] == "location"

    # Turn 2: user replies "warangal"
    r2 = _post(
        message="warangal",
        known_facts=r1["known_facts"],
        rounds_asked=1,
        history=[
            {"role": "user", "content": "I want to start a tailoring shop"},
            {"role": "assistant", "content": r1["reply"]},
        ],
        last_question_key=r1["question_key"],
    ).json()
    assert r2["done"] is False
    assert r2["known_facts"].get("location").lower() == "warangal"
    # It must NOT repeat location question!
    assert "village" not in r2["reply"].lower() and "town" not in r2["reply"].lower()
    # It moves to SHG member question
    assert r2["question_key"] == "shg_member"

    # Turn 3: user replies "no"
    r3 = _post(
        message="no",
        known_facts=r2["known_facts"],
        rounds_asked=2,
        history=[
            {"role": "user", "content": "I want to start a tailoring shop"},
            {"role": "assistant", "content": r1["reply"]},
            {"role": "user", "content": "warangal"},
            {"role": "assistant", "content": r2["reply"]},
        ],
        last_question_key=r2["question_key"],
    ).json()
    assert r3["known_facts"].get("shg_member") is False
    assert r3["question_key"] == "loan_amount"


# ---------- proactive schemes presentation tests ----------

def test_heuristic_extracts_karimanagar_alias():
    from app.followup import _extract_heuristics
    facts = _extract_heuristics("karimanagar", {})
    assert facts.get("location") == "Karimnagar"


def test_heuristic_extracts_agriculture_business():
    from app.followup import _extract_heuristics
    facts = _extract_heuristics("I do agriculture in Telangana", {})
    assert facts.get("business_status") == "new business"


def test_llm_mode_proactively_presents_schemes_when_key_facts_known(seeded_db, monkeypatch):
    """When LLM finishes asking questions and presents schemes, it must be done proactively without typing 'ok'."""
    groq_reply = (
        "Thank you for sharing your location in Karimnagar! As an individual in agriculture, "
        "you are likely eligible for collateral-free loans under the Kisan Credit Card (KCC) scheme. "
        "I will now present the specific government schemes matching your profile.\n"
        "```facts\n"
        '{"location": "Karimnagar", "business_status": "agriculture"}\n'
        "```"
    )
    monkeypatch.setattr(followup, "_call_groq", lambda msgs: groq_reply)

    result = _run(
        seeded_db,
        message="karimanagar",
        lang="en",
        known_facts={"business_status": "agriculture"},
        rounds_asked=1,
        skipped=False,
    )
    assert result["done"] is True
    assert len(result["matches"]) > 0
    assert result["known_facts"]["location"] == "Karimnagar"
    # Should not duplicate closing statement
    assert "Based on your details, here are the government schemes that match your profile:" not in result["reply"]


def test_llm_mode_proactively_presents_schemes_when_no_question_asked(seeded_db, monkeypatch):
    """If LLM response contains no question to the user, done must be True so user isn't stuck."""
    groq_reply = (
        "Here are the government schemes matching your profile.\n"
        "```facts\n"
        '{"location": "Warangal"}\n'
        "```"
    )
    monkeypatch.setattr(followup, "_call_groq", lambda msgs: groq_reply)

    result = _run(
        seeded_db,
        message="warangal",
        lang="en",
        known_facts={"business_status": "tailoring"},
        rounds_asked=1,
        skipped=False,
    )
    assert result["done"] is True
    assert len(result["matches"]) > 0


def test_user_acknowledgment_triggers_done(seeded_db):
    """If user types 'ok' or 'yes' after at least 1 round, it should present schemes."""
    result = _run(
        seeded_db,
        message="ok",
        lang="en",
        known_facts={"location": "Karimnagar", "business_status": "agriculture"},
        rounds_asked=1,
        skipped=False,
    )
    assert result["done"] is True
    assert len(result["matches"]) > 0

