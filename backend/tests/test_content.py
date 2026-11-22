import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FORBIDDEN = ["aadhaar", "pan", "voter", "ration", "bank", "account"]


def _assert_no_forbidden_keys(item):
    for key in item:
        for word in FORBIDDEN:
            assert word not in key.lower(), f"forbidden field name: {key}"


def test_quick_queries_endpoint():
    r = client.get("/api/quick-queries")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 5
    for item in items:
        for key in ["id", "text_en", "text_te", "answers"]:
            assert key in item
        _assert_no_forbidden_keys(item)
