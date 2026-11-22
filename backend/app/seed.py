"""Idempotent loader for scheme seed data.

Run from backend/ with: python -m app.seed
"""

import json
from pathlib import Path

from app.db import Base, SessionLocal, engine
from app.models import Scheme, SchemeDocument, SchemeRule

SEED_PATH = Path(__file__).resolve().parents[1] / "seed" / "schemes.json"

_SCALAR_FIELDS = ("name_en", "name_te", "level", "lane", "description", "official_url")


def seed_schemes(session, path=SEED_PATH):
    """Upsert schemes by slug. Safe to run repeatedly; never duplicates rows.

    Publication status and last_verified_at are only set on insert, so re-running
    the seed never un-publishes or re-stamps a scheme that was reviewed later.
    """
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)

    for entry in entries:
        scheme = session.query(Scheme).filter_by(slug=entry["slug"]).one_or_none()
        if scheme is None:
            scheme = Scheme(slug=entry["slug"], status=entry.get("status", "draft"))
            session.add(scheme)

        for field in _SCALAR_FIELDS:
            setattr(scheme, field, entry.get(field))

        if "rules" in entry:
            scheme.rules = [
                SchemeRule(
                    rule_key=r["rule_key"],
                    rule_value=r.get("rule_value"),
                    needs_verification=r.get("needs_verification", True),
                )
                for r in entry["rules"]
            ]
        if "documents" in entry:
            scheme.documents = [
                SchemeDocument(
                    title_en=d["title_en"],
                    title_te=d.get("title_te"),
                    fee_amount=d.get("fee_amount"),
                    currency=d.get("currency"),
                    processing_days=d.get("processing_days"),
                    is_free=d.get("is_free", False),
                    source_url=d.get("source_url"),
                    needs_verification=d.get("needs_verification", True),
                )
                for d in entry["documents"]
            ]

    session.commit()
    return len(entries)


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        count = seed_schemes(session)
    print(f"Seeded {count} schemes from {SEED_PATH}")


if __name__ == "__main__":
    main()
