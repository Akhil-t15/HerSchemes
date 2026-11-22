from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db import Base

FORBIDDEN_WORDS = ("aadhaar", "aadhar", "pan", "voter", "ration", "bank", "account")


def _engine():
    return create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )


def test_schema_creates_expected_tables():
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    tables = set(inspect(engine).get_table_names())
    assert {"schemes", "scheme_rules", "scheme_documents", "audit_log"} <= tables


def test_schema_has_no_sensitive_id_columns():
    engine = _engine()
    Base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    for table in ("schemes", "scheme_rules", "scheme_documents", "audit_log"):
        for col in insp.get_columns(table):
            name = col["name"].lower()
            for word in FORBIDDEN_WORDS:
                assert word not in name, f"{table}.{col['name']} looks like sensitive data"
