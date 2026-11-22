"""Module 4 - Scheme Matching Engine.

All eligibility logic lives in data (SchemeRule rows). Nothing here names a
scheme or a rule.

Rule format (SchemeRule):
    rule_key   = the profile answer key to test, e.g. "business_type",
                 "loan_amount_band", "shg_member", "stage"
    rule_value = {"op": "equals" | "in" | "lte" | "gte", "value": <expected>}

    equals : answer == value
    in     : answer is one of the values in the list `value`
    lte    : answer <= value   (numeric answers)
    gte    : answer >= value   (numeric answers)

    Examples:
        rule_key "business_type"    {"op": "in", "value": ["manufacturing", "services"]}
        rule_key "loan_amount_band" {"op": "in", "value": ["under_1_lakh"]}
        rule_key "shg_member"       {"op": "equals", "value": true}

Conflict rule (SchemeRule on the scheme that conflicts):
    rule_key   = "conflicts_with"
    rule_value = {"slugs": [...], "explanation_en": "...", "explanation_te": "..."}
    Conflict rules are never evaluated as eligibility conditions.

Evaluation for one scheme:
    - Any evaluable rule fails            -> scheme excluded.
    - No evaluable rules                  -> "Needs More Info" (included).
    - An answer key is missing, or a
      rule is malformed / has unknown op  -> "Needs More Info" (included).
    - At least one rule, all pass         -> "Likely Eligible".
    Only these two status strings are ever produced.

Rules with needs_verification=True are still evaluated; the match carries
`needs_verification: True` so the UI can flag it.

`stale` is is_stale(scheme.last_verified_at, today).
"""

from app.schemes_repo import is_stale, list_published_schemes

LANES = ("state", "central", "addon")
CONFLICT_KEY = "conflicts_with"
STATUS_LIKELY = "Likely Eligible"
STATUS_NEEDS_INFO = "Needs More Info"


def _evaluate(rule_value, actual):
    """Return "pass", "fail", or "unknown" (malformed rule or op)."""
    if not isinstance(rule_value, dict):
        return "unknown"
    op = rule_value.get("op")
    expected = rule_value.get("value")
    try:
        if op == "equals":
            ok = actual == expected
        elif op == "in":
            if not isinstance(expected, list):
                return "unknown"
            ok = actual in expected
        elif op == "lte":
            ok = actual <= expected
        elif op == "gte":
            ok = actual >= expected
        else:
            return "unknown"
    except TypeError:
        return "unknown"
    return "pass" if ok else "fail"


def _evaluate_scheme(rules, answers):
    """Return (status, passed_rules), or (None, []) when the scheme is excluded."""
    conditions = sorted(
        (r for r in rules if r.rule_key != CONFLICT_KEY), key=lambda r: r.id or 0
    )
    if not conditions:
        return STATUS_NEEDS_INFO, []

    passed = []
    needs_info = False
    for rule in conditions:
        actual = answers.get(rule.rule_key)
        if actual is None:
            needs_info = True
            continue
        result = _evaluate(rule.rule_value, actual)
        if result == "fail":
            return None, []
        if result == "unknown":
            needs_info = True
        else:
            passed.append(rule)

    status = STATUS_NEEDS_INFO if needs_info else STATUS_LIKELY
    return status, passed


def match_schemes(session, answers: dict, today):
    """Match published schemes against profile `answers`.

    Returns {"lanes": {"state": [...], "central": [...], "addon": [...]},
             "conflicts": [...]}.
    """
    schemes = list_published_schemes(session)

    matches = {}  # slug -> (scheme, match dict)
    for scheme in schemes:
        status, passed = _evaluate_scheme(scheme.rules, answers)
        if status is None:
            continue
        match = {
            "slug": scheme.slug,
            "name_en": scheme.name_en,
            "name_te": scheme.name_te,
            "official_url": scheme.official_url,
            "level": scheme.level,
            "lane": scheme.level,
            "status": status,
            "reasons": [f"{r.rule_key}: {r.rule_value.get('value')}" for r in passed],
            "stale": is_stale(scheme.last_verified_at, today),
            "needs_verification": any(r.needs_verification for r in scheme.rules),
        }
        matches[scheme.slug] = (scheme, match)

    lanes = {lane: [] for lane in LANES}
    for scheme, match in matches.values():
        if scheme.level in lanes:
            lanes[scheme.level].append(match)

    conflicts = []
    seen_pairs = set()
    for scheme, _ in matches.values():
        for rule in sorted(scheme.rules, key=lambda r: r.id or 0):
            if rule.rule_key != CONFLICT_KEY or not isinstance(rule.rule_value, dict):
                continue
            listed = rule.rule_value.get("slugs")
            if not isinstance(listed, list):
                continue
            for other in listed:
                if other == scheme.slug or other not in matches:
                    continue
                pair = tuple(sorted((scheme.slug, other)))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                conflicts.append(
                    {
                        "slugs": [scheme.slug, other],
                        "pick_one": True,
                        "explanation_en": rule.rule_value.get("explanation_en"),
                        "explanation_te": rule.rule_value.get("explanation_te"),
                    }
                )

    return {"lanes": lanes, "conflicts": conflicts}
