"""Admin token check for the HerScheme admin console (Module 7).

ADMIN_TOKEN is read from the environment on every request. If it is unset or
empty, admin requests are refused with 503. Otherwise the request must send
`Authorization: Bearer <token>` matching ADMIN_TOKEN, or it gets 401.
"""
import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException

_BEARER_PREFIX = "Bearer "


def require_admin(authorization: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin console is disabled: ADMIN_TOKEN is not configured",
        )
    if not authorization or not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    supplied = authorization[len(_BEARER_PREFIX):]
    if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
