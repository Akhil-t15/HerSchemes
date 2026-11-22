from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db import Base
from app.main import app, get_db
from app.models import Scheme


def _setup():
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
            Scheme(slug="pub-two", name_en="Published Two", level="state", status="published"),
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
    return TestClient(app)


def test_health_endpoint():
    client = _setup()
    try:
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
    finally:
        app.dependency_overrides.clear()


def test_schemes_endpoint_returns_only_published():
    client = _setup()
    try:
        r = client.get("/api/schemes")
        assert r.status_code == 200
        slugs = [s["slug"] for s in r.json()]
        assert slugs == ["pub-one", "pub-two"]
        assert "draft-one" not in slugs
    finally:
        app.dependency_overrides.clear()
