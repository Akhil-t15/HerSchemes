from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Scheme

STALE_AFTER = timedelta(days=30)


def list_published_schemes(session: Session):
    return (
        session.query(Scheme)
        .filter(Scheme.status == "published")
        .order_by(Scheme.id)
        .all()
    )


def is_stale(last_verified_at, now: datetime) -> bool:
    """True when last verification is more than 30 days before `now`.

    A missing verification date counts as stale.
    """
    if last_verified_at is None:
        return True
    return (now - last_verified_at) > STALE_AFTER
