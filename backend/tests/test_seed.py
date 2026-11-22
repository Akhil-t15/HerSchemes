from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db import Base
from app.models import Scheme
from app.seed import SEED_PATH, seed_schemes


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_seed_file_has_six_draft_schemes():
    import json

    with open(SEED_PATH, encoding="utf-8") as f:
        entries = json.load(f)
    assert len(entries) == 6
    assert all(e["status"] == "draft" for e in entries)


def test_seed_inserts_six_schemes():
    session = _session()
    assert seed_schemes(session) == 6
    assert session.query(Scheme).count() == 6


def test_seed_is_idempotent():
    session = _session()
    seed_schemes(session)
    seed_schemes(session)
    assert session.query(Scheme).count() == 6


def test_reseed_does_not_unpublish_scheme():
    session = _session()
    seed_schemes(session)
    scheme = session.query(Scheme).filter_by(slug="pmegp").one()
    scheme.status = "published"
    session.commit()

    seed_schemes(session)
    assert session.query(Scheme).filter_by(slug="pmegp").one().status == "published"
