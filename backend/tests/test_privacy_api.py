from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_aadhaar_is_masked_and_warned():
    r = client.post("/api/privacy/check", json={"text": "my aadhaar is 2345 6789 0123"})
    assert r.status_code == 200
    body = r.json()
    assert body["warning"] is True
    assert "2345 6789 0123" not in body["masked_text"]


def test_clean_text_passes_through_unchanged():
    text = "I want to start a tailoring shop"
    r = client.post("/api/privacy/check", json={"text": text})
    assert r.status_code == 200
    body = r.json()
    assert body["warning"] is False
    assert body["masked_text"] == text


def test_empty_text_returns_no_warning():
    r = client.post("/api/privacy/check", json={"text": ""})
    assert r.status_code == 200
    assert r.json()["warning"] is False


def test_text_over_2000_chars_is_rejected():
    r = client.post("/api/privacy/check", json={"text": "a" * 2001})
    assert r.status_code == 422


def test_response_keys_are_exact():
    r = client.post("/api/privacy/check", json={"text": "hello"})
    assert set(r.json().keys()) == {"masked_text", "warning"}
