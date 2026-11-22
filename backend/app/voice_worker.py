"""HerScheme live voice agent worker (Module 9).

How to run (from the backend/ folder):
  Terminal 1 - API:     uvicorn app.main:app --reload
  Terminal 2 - Worker:  python -m app.voice_worker start

Required environment variables (read with os.getenv only, never hardcoded):
  LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, SARVAM_API_KEY

If any key is missing, or the LiveKit connection fails, the worker logs a short
non-sensitive message and exits cleanly. Callers are then told to use text mode.

Pipeline (one LiveKit room per call):
  caller audio -> Silero VAD (endpointing + barge-in) -> Sarvam STT (per utterance)
  -> privacy shield (voice.sanitize_transcript_chunk) -> followup / matching / schemes_repo
  -> short reply (voice.truncate_reply, 35 words) -> Sarvam TTS -> caller audio.

Nothing is written to disk. Raw transcripts and audio are never logged or persisted.
Scheme rules come only from the database (SchemeRule rows via app.matching).
No language model writes eligibility text.

This module imports livekit-agents lazily, so pytest can import it without the package.
"""
import asyncio
import io
import logging
import os
import re
import uuid
import wave
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv not installed: fall back to the process environment
    load_dotenv = None

# Load backend/.env before any os.getenv use (same path as app/main.py).
if load_dotenv is not None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from app import voice
from app.followup import FACT_KEYS, detect_missing_facts, run_followup
from app.matching import STATUS_LIKELY, STATUS_NEEDS_INFO, match_schemes

logger = logging.getLogger("herscheme.voice_worker")

REPLY_MAX_WORDS = 35
MAX_SCHEMES_SPOKEN = 2
GREETING_EN = "Namaste. You can speak in Telugu or English. Tell me about your scheme needs."
TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]")
GUARANTEE_RE = re.compile(r"\bguaranteed\b", re.IGNORECASE)

# Turn-taking and latency settings (see the report in the module docstring above).
MIN_ENDPOINTING_DELAY = 0.3      # seconds of silence before the caller's turn ends
MAX_ENDPOINTING_DELAY = 0.8      # upper bound if the caller keeps pausing
MIN_INTERRUPTION_DURATION = 0.3  # seconds of caller speech that stops the agent (barge-in)

# Idle handling: after a reply, a silent caller gets a prompt, then the call ends. Seconds, from env.
VOICE_IDLE_PROMPT_SECONDS = int(os.getenv("VOICE_IDLE_PROMPT_SECONDS", "20"))
VOICE_IDLE_END_SECONDS = int(os.getenv("VOICE_IDLE_END_SECONDS", "40"))
IDLE_PROMPT = {"en": "Are you still there?", "te": "మీరు ఇంకా ఉన్నారా?"}
IDLE_GOODBYE = {
    "en": "Thank you for calling HerScheme. Goodbye.",
    "te": "HerScheme కి కాల్ చేసినందుకు ధన్యవాదాలు. వీడ్కోలు.",
}
# Single-instance guard: a second worker on this machine cannot bind this loopback port.
VOICE_WORKER_LOCK_PORT = int(os.getenv("VOICE_WORKER_LOCK_PORT", "9082"))



@dataclass
class CallState:
    """Per-call, in-memory state only. Discarded when the call ends."""
    lang: str = "en"
    known: Dict[str, Any] = field(default_factory=dict)
    answers: Dict[str, Any] = field(default_factory=dict)
    rounds_asked: int = 0
    stt_failed_notified: bool = False
    segment_id: Optional[str] = None  # transcript segment of the utterance in progress



def _sanitize_reply(text: str) -> str:
    text = GUARANTEE_RE.sub("likely", text)
    return voice.truncate_reply(text, REPLY_MAX_WORDS)


def _short_question(question: str) -> str:
    return question.split(" (Why:")[0].strip()


def _scheme_name(match: Dict[str, Any], lang: str) -> str:
    if lang == "te" and match.get("name_te"):
        return match["name_te"]
    return match.get("name_en") or match.get("slug", "")


def answer_utterance(state: CallState, raw_text: str) -> str:
    """Build the spoken reply for one caller utterance. Synchronous (uses the DB).

    The raw text is masked first and only the masked text is used after that.
    """
    # Privacy shield runs before any follow-up, matching or DB work.
    clean = voice.sanitize_transcript_chunk(raw_text)
    masked = clean["text"]
    state.lang = "te" if TELUGU_RE.search(masked) else "en"

    # Facts mentioned in speech count as known for later turns.
    state.known.update({k: True for k in FACT_KEYS if k not in detect_missing_facts(masked)})

    try:
        # Lazy imports keep module import cheap and avoid DB setup at import time.
        from app.db import SessionLocal

        db = SessionLocal()
        try:
            result = run_followup(
                db,
                masked,
                state.lang,
                dict(state.known),
                state.rounds_asked,
                skipped=False,
            )
            if result.get("known_facts"):
                state.known.update(result["known_facts"])
                state.answers.update(result["known_facts"])

            parts = []
            if result.get("warning"):
                parts.append(voice.SENSITIVE_WARNING)

            if not result["done"] and result.get("reply"):
                state.rounds_asked += 1
                parts.append(result["reply"])
            elif not result["done"] and result.get("questions"):
                state.rounds_asked += 1
                parts.append(_short_question(result["questions"][0]))
            else:
                # Rules are evaluated by the matching engine against database rows only.
                lanes = match_schemes(db, state.answers, datetime.now(timezone.utc))["lanes"]
                flat = [m for lane in lanes.values() for m in lane]
                likely = [_scheme_name(m, state.lang) for m in flat
                          if m["status"] == STATUS_LIKELY][:MAX_SCHEMES_SPOKEN]
                needs = [_scheme_name(m, state.lang) for m in flat
                         if m["status"] == STATUS_NEEDS_INFO][:MAX_SCHEMES_SPOKEN]
                if likely:
                    parts.append(f"{STATUS_LIKELY}: {', '.join(likely)}.")
                if needs:
                    parts.append(f"{STATUS_NEEDS_INFO}: {', '.join(needs)}.")
                if not parts:
                    parts.append("No published schemes match yet. Please use text mode for details.")
        finally:
            db.close()
    except Exception as exc:
        # Log the exception type only: messages may echo caller text.
        logger.warning("voice reply failed (%s); caller should use text mode", type(exc).__name__)
        return voice.VOICE_UNAVAILABLE_MESSAGE

    return _sanitize_reply(" ".join(parts))


def _latest_user_text(chat_ctx) -> str:
    for item in reversed(list(getattr(chat_ctx, "items", []) or [])):
        if getattr(item, "role", None) == "user":
            return (getattr(item, "text_content", None) or "").strip()
    return ""


def _caller_identity(room) -> str:
    """Identity of the caller (the remote participant). Empty string if none has joined yet."""
    for identity in room.remote_participants:
        return identity
    return ""


async def _publish_user_transcript(room, raw_text: str, language, segment_id: str, final: bool) -> None:
    """Publish one caller transcript segment (interim or final) to the room, masked first.

    Interim and final results of one utterance share segment_id, so the browser replaces the text
    in place. An empty final segment is still sent so the browser can close the segment.
    Raw text is never logged or stored; only the masked text is published.
    """
    from livekit import rtc

    masked = voice.sanitize_transcript_chunk(raw_text)["text"].strip()
    identity = _caller_identity(room)
    if not identity or (not masked and not final):
        return
    segment = rtc.TranscriptionSegment(
        id=segment_id,
        text=masked,
        start_time=0,
        end_time=0,
        language=language or "",
        final=final,
    )
    try:
        await room.local_participant.publish_transcription(
            rtc.Transcription(participant_identity=identity, track_sid="", segments=[segment])
        )
    except Exception as exc:
        # Log the exception type only: messages may echo caller text.
        logger.warning("transcript publish failed (%s)", type(exc).__name__)


def _pcm_to_wav(frame) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(frame.num_channels)
        w.setsampwidth(2)  # 16-bit PCM from LiveKit
        w.setframerate(frame.sample_rate)
        w.writeframes(bytes(frame.data))
    return buf.getvalue()


def _wav_to_pcm(wav_bytes: bytes):
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels()


def build_livekit_components():
    """Create the livekit-agents classes. Raises ImportError if the SDK is missing."""
    from livekit import rtc
    from livekit.agents import Agent, stt as lk_stt, tts as lk_tts, utils

    class SarvamSTT(lk_stt.STT):
        """Sarvam speech-to-text for one VAD-segmented utterance (via voice.sarvam_stt)."""

        def __init__(self, state: CallState):
            super().__init__(
                capabilities=lk_stt.STTCapabilities(streaming=False, interim_results=False)
            )
            self._state = state

        async def _recognize_impl(self, buffer, *, language=None, conn_options=None):
            frames = buffer if isinstance(buffer, list) else [buffer]
            if not frames:
                return lk_stt.SpeechEvent(
                    type=lk_stt.SpeechEventType.FINAL_TRANSCRIPT,
                    alternatives=[lk_stt.SpeechData(language="unknown", text="")],
                )
            wav = _pcm_to_wav(rtc.combine_audio_frames(frames))
            try:
                raw = await voice.sarvam_stt(
                    wav, language_code="unknown", filename="utterance.wav",
                    content_type="audio/wav",
                )
            except Exception as exc:
                logger.warning("Sarvam STT request failed (%s)", type(exc).__name__)
                raise
            # Mask at the point the transcript is born; raw text is not kept.
            masked = voice.sanitize_transcript_chunk(raw)["text"]
            return lk_stt.SpeechEvent(
                type=lk_stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[lk_stt.SpeechData(language="unknown", text=masked)],
            )

    class SarvamChunkedStream(lk_tts.ChunkedStream):
        def __init__(self, *, tts, input_text, conn_options, state: CallState):
            super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
            self._state = state

        async def _run(self, output_emitter):
            code = "te-IN" if self._state.lang == "te" else "en-IN"
            wav = await voice.sarvam_tts(self._input_text, target_language_code=code)
            if not wav:
                return
            pcm, rate, channels = _wav_to_pcm(wav)
            output_emitter.initialize(
                request_id=utils.shortuuid(),
                sample_rate=rate,
                num_channels=channels,
                mime_type="audio/pcm",
            )
            output_emitter.push(pcm)
            output_emitter.flush()

    class SarvamTTS(lk_tts.TTS):
        """Sarvam text-to-speech (via voice.sarvam_tts)."""

        def __init__(self, state: CallState):
            super().__init__(
                capabilities=lk_tts.TTSCapabilities(streaming=False),
                sample_rate=22050,
                num_channels=1,
            )
            self._state = state

        def _synthesize(self, chunk, *, conn_options):
            # 2.0: the framework calls _synthesize per segment; chunk.said is the plain words.
            return SarvamChunkedStream(
                tts=self, input_text=chunk.said, conn_options=conn_options, state=self._state
            )

    class HerSchemeAgent(Agent):
        """Replies come from answer_utterance(), registered as the session llm_node in entrypoint."""

        def __init__(self, state: CallState):
            super().__init__(instructions="Short phone replies about government scheme eligibility.")
            self._state = state

    return {
        "STT": SarvamSTT,
        "TTS": SarvamTTS,
        "Agent": HerSchemeAgent,
    }


_VAD = None


def _get_vad():
    """Load the Silero VAD model once per worker process.

    livekit-agents 2.0 has no prewarm hook on AgentServer, so the model is cached here instead.
    """
    global _VAD
    if _VAD is None:
        from livekit.plugins import silero

        _VAD = silero.VAD.load()
    return _VAD


async def entrypoint(ctx):
    from livekit.agents import VoiceSession
    from livekit.agents.job import AutoSubscribe  # 2.0: not re-exported from livekit.agents
    from livekit.agents.stt import StreamAdapter

    parts = build_livekit_components()
    state = CallState()
    vad = _get_vad()

    session = VoiceSession(
        vad=vad,
        stt=StreamAdapter(stt=parts["STT"](state), vad=vad),
        tts=parts["TTS"](state),
        llm=None,
        # 2.0 nests turn-taking settings under turn_handling.
        turn_handling={
            "turn_detection": "vad",
            "endpointing": {
                "min_delay": MIN_ENDPOINTING_DELAY,
                "max_delay": MAX_ENDPOINTING_DELAY,
            },
            # caller speech stops the agent immediately (barge-in)
            "interruption": {"enabled": True, "min_duration": MIN_INTERRUPTION_DURATION},
        },
    )

    @session.on("error")
    def _on_error(event):
        # STT/TTS failure: tell the caller to use text mode, at most once per call.
        logger.warning(
            "voice session error (%s): %s",
            getattr(event, "source", "unknown"),
            getattr(event, "error", "unknown"),
        )
        if not state.stt_failed_notified:
            state.stt_failed_notified = True
            session.say(voice.VOICE_UNAVAILABLE_MESSAGE)

    # Reply generation: the session calls this for every caller turn (session-level hook in 2.0;
    # Agent has no llm_node method).
    @session.llm_node
    async def _reply(run_ctx, chat_ctx, tools, model_settings):
        raw = _latest_user_text(chat_ctx)
        if not raw:
            return
        # answer_utterance masks the text and truncates the reply to REPLY_MAX_WORDS.
        yield await asyncio.to_thread(answer_utterance, state, raw)

    # Silence timer for this call: the running idle task, and whether the caller has joined.
    idle: Dict[str, Any] = {"task": None, "ready": False}

    def _cancel_idle() -> None:
        task = idle["task"]
        idle["task"] = None
        if task is not None and not task.done():
            task.cancel()

    async def _idle_flow() -> None:
        # Prompt after VOICE_IDLE_PROMPT_SECONDS of silence, then say goodbye and close the
        # session after VOICE_IDLE_END_SECONDS more. Caller speech cancels this task.
        try:
            await asyncio.sleep(VOICE_IDLE_PROMPT_SECONDS)
            await session.say(IDLE_PROMPT.get(state.lang, IDLE_PROMPT["en"]))
            await asyncio.sleep(VOICE_IDLE_END_SECONDS)
            await session.say(IDLE_GOODBYE.get(state.lang, IDLE_GOODBYE["en"]))
            logger.info("caller silent past the idle limit; ending the call")
            await session.aclose(reason="idle_timeout", drain=True)
            ctx.shutdown(reason="idle timeout")
        except Exception as exc:
            logger.warning("idle handling stopped (%s)", type(exc).__name__)

    # The agent is idle again after each reply: start the silence timer unless one is running.
    @session.on("agent_state_changed")
    def _on_agent_state(event):
        if event.new_state != "idle" or not idle["ready"]:
            return
        if idle["task"] is None or idle["task"].done():
            idle["task"] = asyncio.ensure_future(_idle_flow())

    # Caller speech cancels the silence timer.
    @session.on("user_state_changed")
    def _on_user_state(event):
        if event.new_state == "speaking":
            _cancel_idle()

    # Caller speech -> room transcription track and immediate spoken response.
    # Interim and final results of one utterance share a segment id; the final result triggers
    # answer_utterance and streams the spoken reply back to the caller.
    async def _handle_turn(raw_text: str) -> None:
        if not raw_text or not raw_text.strip():
            return
        _cancel_idle()
        logger.info("Processing caller speech: %s", raw_text)
        try:
            reply = await asyncio.to_thread(answer_utterance, state, raw_text)
            logger.info("Spoken answer: %s", reply)
            if reply and ctx.room.isconnected():
                await session.say(reply)
        except Exception as exc:
            logger.warning("Reply generation failed (%s)", type(exc).__name__)
            if ctx.room.isconnected():
                await session.say(voice.VOICE_UNAVAILABLE_MESSAGE)

    @session.on("user_input_transcribed")
    def _on_user_transcript(event):
        if state.segment_id is None:
            state.segment_id = uuid.uuid4().hex
        segment_id = state.segment_id
        final = bool(getattr(event, "is_final", False))
        if final:
            state.segment_id = None
        asyncio.ensure_future(
            _publish_user_transcript(
                ctx.room, event.transcript, getattr(event, "language", None), segment_id, final
            )
        )
        if final and event.transcript and event.transcript.strip():
            asyncio.ensure_future(_handle_turn(event.transcript.strip()))

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await session.start(agent=parts["Agent"](state), room=ctx.room)
    # Greet only after the caller has joined, so nothing is spoken to an empty room.
    await ctx.wait_for_participant()
    idle["ready"] = True
    await session.say(GREETING_EN)


_LOCK_SOCKET = None


def _acquire_single_instance_lock() -> bool:
    """Hold a loopback port for this process's lifetime so only one worker on this machine registers.

    Returns False when another worker already holds the port. If the port cannot be used for
    another reason (for example a Windows reserved range), the worker starts without the guard.
    """
    global _LOCK_SOCKET
    import errno
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", VOICE_WORKER_LOCK_PORT))
        sock.listen(1)
    except OSError as exc:
        sock.close()
        if getattr(exc, "winerror", None) == 10048 or exc.errno == errno.EADDRINUSE:
            return False
        logger.warning("single-instance guard unavailable (%s); starting without it",
                       type(exc).__name__)
        return True
    _LOCK_SOCKET = sock
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not voice.voice_configured() or not voice.sarvam_api_key():
        logger.warning(
            "Voice worker not started: set LIVEKIT_URL, LIVEKIT_API_KEY, "
            "LIVEKIT_API_SECRET and SARVAM_API_KEY. Users should use text mode."
        )
        return

    if not _acquire_single_instance_lock():
        logger.warning("Another voice worker is already running on this machine; "
                       "this one will not register. Stop the extra worker process.")
        return


    try:
        from livekit.agents import AgentServer, cli, rtc_session
    except ImportError:
        logger.warning("Voice worker not started: livekit-agents is not installed "
                       "(pip install -r requirements.txt). Users should use text mode.")
        return

    # 2.0: WorkerOptions is replaced by AgentServer; the entrypoint is served as an rtc_session.
    # Windows reserves 8075-8174 (among other ranges), so livekit-agents' defaults 8080/8081
    # fail with WinError 10013. Ports are read from the environment; defaults avoid reserved ranges.
    public_port = int(os.getenv("VOICE_WORKER_PORT", "9080"))
    health_port = int(os.getenv("VOICE_WORKER_HEALTH_PORT", "9081"))
    server = AgentServer(
        agent_name=voice.AGENT_NAME,  # must match the token's RoomAgentDispatch
        listeners={"public": {"port": public_port}, "health": {"port": health_port}},
    )
    server.add(rtc_session()(entrypoint))
    try:
        cli.run_app(server)
    except Exception as exc:
        logger.error("Voice worker stopped (%s). Users should use text mode.", type(exc).__name__)


if __name__ == "__main__":
    main()

