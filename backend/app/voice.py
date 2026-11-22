"""Live voice helpers for HerScheme (Module 9).

Transport: LiveKit (token minting only; media runs in the browser/LiveKit server).
Speech: Sarvam AI REST API for speech-to-text and text-to-speech.

Nothing here writes audio to disk. Transcript text is passed through the privacy
shield in app.privacy and is never logged or stored by this module.
"""
import base64
import os
import uuid

import httpx

from app.privacy import mask_sensitive

SARVAM_BASE_URL = "https://api.sarvam.ai"
SARVAM_TIMEOUT_SECONDS = 30.0

VOICE_UNAVAILABLE_MESSAGE = "Voice is unavailable right now. Please use text mode."
SENSITIVE_WARNING = (
    "A private ID was hidden. Please do not share Aadhaar, PAN, ration card or bank numbers."
)
# Must match AgentServer(agent_name=...) in app/voice_worker.py. Tokens dispatch this agent.
AGENT_NAME = "herscheme-voice"


def livekit_url():
    url = os.getenv("LIVEKIT_URL", "").strip().rstrip(",")
    if "demp-mrw9cu80.livekit.cloud" in url:
        return "wss://demp-mrw9cu80.ohyderabad1a.production.livekit.cloud"
    return url


def livekit_api_key():
    return os.getenv("LIVEKIT_API_KEY", "").strip().rstrip(",")


def livekit_api_secret():
    return os.getenv("LIVEKIT_API_SECRET", "").strip().rstrip(",")


def sarvam_api_key():
    return os.getenv("SARVAM_API_KEY", "").strip().rstrip(",")


def voice_configured():
    """True only when all three LiveKit settings are present."""
    return bool(livekit_url() and livekit_api_key() and livekit_api_secret())


def mint_livekit_token(identity, room):
    """Build a LiveKit join token for the given identity and room."""
    # Lazy import so the app starts even when livekit-api is not installed.
    from livekit import api
    from livekit.protocol.agent_dispatch import RoomAgentDispatch
    from livekit.protocol.room import RoomConfiguration

    # Room config asks LiveKit to dispatch the voice agent worker into this room on join.
    room_config = RoomConfiguration(agents=[RoomAgentDispatch(agent_name=AGENT_NAME)])
    token = (
        api.AccessToken(livekit_api_key(), livekit_api_secret())
        .with_identity(identity)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
            )
        )
        .with_room_config(room_config)
    )
    return token.to_jwt()


def new_room_name():
    return f"herscheme-{uuid.uuid4().hex}"


def truncate_reply(text, max_words=35):
    """Return at most max_words whitespace-separated words."""
    words = (text or "").split()
    return " ".join(words[:max_words])


def sanitize_transcript_chunk(text):
    """Mask private IDs in a transcript chunk.

    Returns {"text": sanitized, "hidden": bool}. The raw text is not logged or stored.
    """
    masked, categories = mask_sensitive(text or "")
    return {"text": masked, "hidden": bool(categories)}


def _require_sarvam_key():
    key = sarvam_api_key()
    if not key:
        raise RuntimeError("SARVAM_API_KEY is not set; Sarvam speech services are unavailable.")
    return key


_SARVAM_CLIENT = None


def _get_sarvam_client():
    global _SARVAM_CLIENT
    if _SARVAM_CLIENT is None or _SARVAM_CLIENT.is_closed:
        _SARVAM_CLIENT = httpx.AsyncClient(timeout=SARVAM_TIMEOUT_SECONDS)
    return _SARVAM_CLIENT


async def sarvam_stt(audio_bytes, language_code="unknown", filename="speech.webm",
                     content_type="audio/webm"):
    """Send audio to Sarvam speech-to-text and return the transcript string.

    Audio is held in memory only and is not written to disk.
    """
    key = _require_sarvam_key()
    files = {"file": (filename, audio_bytes, content_type)}
    data = {"model": "saarika:v2.5", "language_code": language_code}
    client = _get_sarvam_client()
    resp = await client.post(
        f"{SARVAM_BASE_URL}/speech-to-text",
        headers={"api-subscription-key": key},
        files=files,
        data=data,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("transcript", "")


async def sarvam_tts(text, target_language_code="en-IN", speaker="kavitha"):
    """Convert text to speech via Sarvam and return raw WAV bytes (in memory only)."""
    key = _require_sarvam_key()
    body = {
        "inputs": [truncate_reply(text)],
        "target_language_code": target_language_code,
        "speaker": speaker,
        "model": "bulbul:v3",
    }
    client = _get_sarvam_client()
    resp = await client.post(
        f"{SARVAM_BASE_URL}/text-to-speech",
        headers={"api-subscription-key": key, "Content-Type": "application/json"},
        json=body,
    )
    resp.raise_for_status()
    payload = resp.json()
    audios = payload.get("audios") or []
    if not audios:
        return b""
    return base64.b64decode(audios[0])
