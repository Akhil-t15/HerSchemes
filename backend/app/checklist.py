from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Scheme, SchemeDocument, SchemeRule


def _fee(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _is_free(doc: SchemeDocument) -> bool:
    # A document is a free paper when it is flagged free, or carries no fee.
    return bool(doc.is_free) or not _fee(doc.fee_amount)


def _rule_by_key(rules: list[SchemeRule], key: str) -> Optional[SchemeRule]:
    for rule in rules:
        if rule.rule_key == key:
            return rule
    return None


def _string_list(rule: Optional[SchemeRule]) -> list[str]:
    if rule is None or not isinstance(rule.rule_value, list):
        return []
    return [str(item) for item in rule.rule_value if isinstance(item, str)]


def _string_value(rule: Optional[SchemeRule]) -> Optional[str]:
    if rule is None or not isinstance(rule.rule_value, str):
        return None
    return rule.rule_value


def build_checklist(
    scheme: Scheme,
    documents: list[SchemeDocument],
    rules: list[SchemeRule],
) -> dict:
    free_papers = []
    meeseva_certificates = []
    for doc in documents:
        if _is_free(doc):
            free_papers.append(
                {
                    "title_en": doc.title_en,
                    "title_te": doc.title_te,
                    "fee_amount": _fee(doc.fee_amount),
                    "currency": doc.currency,
                    "source_url": doc.source_url,
                    "needs_verification": bool(doc.needs_verification),
                }
            )
        else:
            meeseva_certificates.append(
                {
                    "title_en": doc.title_en,
                    "title_te": doc.title_te,
                    "fee_amount": _fee(doc.fee_amount),
                    "currency": doc.currency,
                    "processing_days": doc.processing_days,
                    "source_url": doc.source_url,
                    "needs_verification": bool(doc.needs_verification),
                }
            )

    steps_en_rule = _rule_by_key(rules, "apply_steps_en")
    steps_te_rule = _rule_by_key(rules, "apply_steps_te")
    step_rules = [r for r in (steps_en_rule, steps_te_rule) if r is not None]
    # No verified steps data means the apply section must be treated as unverified.
    apply_needs_verification = (
        any(bool(r.needs_verification) for r in step_rules) if step_rules else True
    )

    return {
        "slug": scheme.slug,
        "name_en": scheme.name_en,
        "name_te": scheme.name_te,
        "free_papers": free_papers,
        "meeseva_certificates": meeseva_certificates,
        "where_to_apply": {
            "official_url": scheme.official_url,
            "needs_verification": apply_needs_verification,
            "steps_en": _string_list(steps_en_rule),
            "steps_te": _string_list(steps_te_rule),
        },
        "udyam_warning_en": _string_value(_rule_by_key(rules, "free_warning_en")),
        "udyam_warning_te": _string_value(_rule_by_key(rules, "free_warning_te")),
    }


def get_checklist(db: Session, slug: str) -> Optional[dict]:
    scheme = (
        db.query(Scheme)
        .filter(Scheme.slug == slug, Scheme.status == "published")
        .first()
    )
    if scheme is None:
        return None
    documents = (
        db.query(SchemeDocument).filter(SchemeDocument.scheme_id == scheme.id).all()
    )
    rules = db.query(SchemeRule).filter(SchemeRule.scheme_id == scheme.id).all()
    return build_checklist(scheme, documents, rules)
