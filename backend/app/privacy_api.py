"""Privacy check endpoint for HerScheme.

Masks sensitive ID numbers in a message and reports whether any were found.
Nothing is stored, logged or printed here; only the masked text and a boolean
warning flag leave this module.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.privacy import mask_sensitive

router = APIRouter()


class PrivacyCheckIn(BaseModel):
    text: str = Field(max_length=2000)


def check_message(text: str) -> dict:
    masked, categories = mask_sensitive(text)
    return {"masked_text": masked, "warning": bool(categories)}


@router.post("/api/privacy/check")
def privacy_check(body: PrivacyCheckIn):
    return check_message(body.text)
