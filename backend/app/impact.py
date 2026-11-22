"""Aggregate-only impact numbers for sponsors (Module 8).

Returns counts and averages only. No names, phone numbers, account IDs or raw
messages are read or returned here. Districts and costs are optional in the data;
the result says which ones were actually recorded.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import ServiceSession

TOP_N = 5


def compute_impact(db: Session) -> dict:
    total_helped = (
        db.query(func.count(func.distinct(ServiceSession.session_key))).scalar() or 0
    )

    district_rows = (
        db.query(ServiceSession.district, func.count(ServiceSession.id))
        .filter(ServiceSession.district.isnot(None))
        .group_by(ServiceSession.district)
        .order_by(func.count(ServiceSession.id).desc(), ServiceSession.district)
        .limit(TOP_N)
        .all()
    )
    scheme_rows = (
        db.query(ServiceSession.scheme_slug, func.count(ServiceSession.id))
        .filter(ServiceSession.scheme_slug.isnot(None))
        .group_by(ServiceSession.scheme_slug)
        .order_by(func.count(ServiceSession.id).desc(), ServiceSession.scheme_slug)
        .limit(TOP_N)
        .all()
    )
    avg_cost = (
        db.query(func.avg(ServiceSession.cost_amount))
        .filter(ServiceSession.cost_amount.isnot(None))
        .scalar()
    )
    districts_recorded = (
        db.query(func.count(ServiceSession.id))
        .filter(ServiceSession.district.isnot(None))
        .scalar()
        or 0
    ) > 0
    costs_recorded = avg_cost is not None

    return {
        "total_women_helped": int(total_helped),
        "top_districts": [{"district": d, "sessions": int(c)} for d, c in district_rows],
        "top_schemes": [{"scheme_slug": s, "sessions": int(c)} for s, c in scheme_rows],
        "average_cost_per_session": round(float(avg_cost), 2) if costs_recorded else None,
        "districts_recorded": districts_recorded,
        "costs_recorded": costs_recorded,
    }
