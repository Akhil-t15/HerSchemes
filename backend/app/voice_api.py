from typing import Optional
import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.voice import (
    SENSITIVE_WARNING,
    VOICE_UNAVAILABLE_MESSAGE,
    livekit_url,
    mint_livekit_token,
    new_room_name,
    sanitize_transcript_chunk,
    voice_configured,
)

router = APIRouter(prefix="/api/voice")


class TranscriptIn(BaseModel):
    text: str


@router.get("/status")
def voice_status():
    available = voice_configured()
    if available:
        return {"voice_available": True, "message": "Voice is available."}
    return {"voice_available": False, "message": VOICE_UNAVAILABLE_MESSAGE}


@router.get("/token")
def voice_token(identity: Optional[str] = Query(None, max_length=64)):
    if not voice_configured():
        return {"voice_available": False, "message": VOICE_UNAVAILABLE_MESSAGE}
    who = identity or f"guest-{uuid.uuid4().hex[:8]}"
    room = new_room_name()
    return {
        "voice_available": True,
        "url": livekit_url(),
        "token": mint_livekit_token(who, room),
        "room": room,
    }


@router.post("/transcript")
def voice_transcript(body: TranscriptIn):
    result = sanitize_transcript_chunk(body.text)
    hidden = result["hidden"]
    return {
        "text": result["text"],
        "hidden": hidden,
        "warning": SENSITIVE_WARNING if hidden else None,
    }
