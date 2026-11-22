from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.voice import sanitize_transcript_chunk, truncate_reply

client = TestClient(app)

# Valid Aadhaar format: first digit must be 2-9 (privacy.py rule).
AADHAAR_TEXT = "my aadhaar is 2345 6789 0123"
BACKEND_DIR = Path(__file__).resolve().parents[1]
AUDIO_GLOBS = ("*.wav", "*.mp3", "*.webm")


def _audio_files():
    found = set()
    for pattern in AUDIO_GLOBS:
        found.update(str(p) for p in BACKEND_DIR.rglob(pattern))
    return found


def test_token_unconfigured_returns_200_and_unavailable(monkeypatch):
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    resp = client.get("/api/voice/token", params={"identity": "tester"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["voice_available"] is False
    assert "text mode" in body["message"]


def test_truncate_reply_limits_to_35_words():
    long_text = " ".join(f"word{i}" for i in range(50))
    result = truncate_reply(long_text)
    assert len(result.split()) <= 35


def test_sanitize_hides_aadhaar_digits():
    result = sanitize_transcript_chunk(AADHAAR_TEXT)
    assert not any(ch.isdigit() for ch in result["text"])
    assert result["hidden"] is True


def test_transcript_endpoint_hides_aadhaar_digits():
    resp = client.post("/api/voice/transcript", json={"text": AADHAAR_TEXT})
    assert resp.status_code == 200
    body = resp.json()
    assert body["hidden"] is True
    assert not any(ch.isdigit() for ch in body["text"])
    assert not any(ch.isdigit() for ch in (body["warning"] or ""))
    assert body["warning"] is not None


def test_no_audio_files_written():
    before = _audio_files()
    client.get("/api/voice/status")
    client.get("/api/voice/token", params={"identity": "tester"})
    client.post("/api/voice/transcript", json={"text": AADHAAR_TEXT})
    assert _audio_files() == before
