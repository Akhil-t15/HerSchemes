// Module 9: live voice session (LiveKit room with a voice agent).
// Only the agent's audio and the masked transcript text are used here. Raw transcript text is
// never stored or logged; each segment goes to the server for masking first.
import { Room, RoomEvent } from "livekit-client";

// How long to wait for the voice agent to join before the caller is told to use text mode.
const AGENT_WAIT_MS = 15000;
// Shown in the chat when no voice agent joins (English and Telugu).
const NO_AGENT_MESSAGE =
  "No voice agent joined. Please use text mode. / ఏజెంట్ చేరలేదు. దయచేసి టెక్స్ట్ మోడ్ ఉపయోగించండి.";

// The session currently running, or null. Cleared by stopVoice() and on failure.
let session = null;

// Disconnects the room and removes the audio elements of one session. Safe to call twice.
function teardown(current) {
  current.stopped = true;
  if (current.teardownAudio) {
    try {
      current.teardownAudio();
    } catch {
      // ignore
    }
  }
  current.options?.onAgentSpeaking?.(false);
  for (const { track, el } of current.audioEls) {
    try {
      track.detach();
    } catch {
      // already detached
    }
    el.remove();
  }
  current.audioEls = [];
  if (current.room) {
    try {
      current.room.disconnect();
    } catch {
      // room already closed
    }
  }
}

// Reports a failed start to the caller, unless the user already stopped the session.
function fail(current, options, message) {
  if (current.stopped) return false;
  if (session === current) session = null;
  teardown(current);
  options.onUnavailable?.(typeof message === "string" && message ? message : undefined);
  return false;
}

// Ends one transcript segment in the browser without text (used when the final result is lost
// or empty). The id is marked so a late interim reply cannot reopen it.
function closeSegment(current, options, segId) {
  current.applied.set(segId, Number.MAX_SAFE_INTEGER);
  options.onTranscriptChunk?.("", false, segId, true);
}

// Sends one transcript segment (interim or final) to the server; the server returns masked text.
// Replies are applied in send order per segment, so an older reply cannot overwrite newer text.
async function sendSegment(current, options, segId, text, isFinal) {
  const seq = ++current.seq;
  let result = null;
  try {
    const res = await fetch("/api/voice/transcript", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (res.ok) result = await res.json();
  } catch {
    result = null; // dropped chunk; never fall back to the raw text
  }
  if (current.stopped) return;
  if (!result || typeof result.text !== "string") {
    if (isFinal) closeSegment(current, options, segId);
    return;
  }
  if (seq < (current.applied.get(segId) ?? 0)) return;
  current.applied.set(segId, seq);
  options.onTranscriptChunk?.(result.text, result.warning === true, segId, isFinal);
}

// True when an agent participant is in the room.
function hasAgent(room) {
  for (const participant of room.remoteParticipants.values()) {
    if (participant.isAgent === true) return true;
  }
  return false;
}

// Resolves true once an agent participant is in the room, or false after ms without one.
function waitForAgent(room, ms) {
  if (hasAgent(room)) return Promise.resolve(true);
  return new Promise((resolve) => {
    let timer = null;
    const finish = (joined) => {
      clearTimeout(timer);
      room.off(RoomEvent.ParticipantConnected, onJoin);
      resolve(joined);
    };
    const onJoin = (participant) => {
      if (participant && participant.isAgent === true) finish(true);
    };
    room.on(RoomEvent.ParticipantConnected, onJoin);
    timer = setTimeout(() => finish(false), ms);
  });
}

// Starts a live voice session. Resolves true when the agent has joined and the mic is on,
// false when unavailable or stopped.
// options: onTranscriptChunk(text, warning, segId, isFinal), onUnavailable(message),
//          onEnded(), onAudioBlocked()
export async function startVoice(options = {}) {
  stopVoice();
  const current = { room: null, audioEls: [], stopped: false, seq: 0, applied: new Map(), options };
  session = current;

  try {
    // Room creation and audio unlock run before the first await, inside the click handler,
    // so the browser still treats them as user-initiated.
    const room = new Room();
    current.room = room;
    room.startAudio?.().catch(() => {});

    const identity = `visitor-${Math.random().toString(36).slice(2, 10)}`;
    const res = await fetch(`/api/voice/token?identity=${encodeURIComponent(identity)}`);
    if (!res.ok) return fail(current, options);
    const data = await res.json();
    if (!data || data.voice_available !== true || !data.url || !data.token) {
      return fail(current, options, data && data.message);
    }
    if (current.stopped) return false;

    // Agent audio plays through an <audio> element per subscribed audio track.
    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind !== "audio" || current.stopped) return;
      const el = track.attach();
      el.autoplay = true;
      document.body.append(el);
      current.audioEls.push({ track, el });

      const notifySpeaking = (speaking, freqData) => {
        if (!current.stopped) options.onAgentSpeaking?.(speaking, freqData);
      };

      el.addEventListener("play", () => notifySpeaking(true));
      el.addEventListener("playing", () => notifySpeaking(true));
      el.addEventListener("pause", () => notifySpeaking(false));
      el.addEventListener("ended", () => notifySpeaking(false));

      // Real audio frequency analysis for waveform animation
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx && track.mediaStreamTrack) {
          const actx = new AudioCtx();
          const srcNode = actx.createMediaStreamSource(new MediaStream([track.mediaStreamTrack]));
          const analyser = actx.createAnalyser();
          analyser.fftSize = 64;
          analyser.smoothingTimeConstant = 0.65;
          srcNode.connect(analyser);

          const freqData = new Uint8Array(analyser.frequencyBinCount);
          let animId = null;

          const checkAudio = () => {
            if (current.stopped) {
              actx.close().catch(() => {});
              return;
            }
            analyser.getByteFrequencyData(freqData);
            let sum = 0;
            for (let i = 0; i < freqData.length; i++) sum += freqData[i];
            const avg = sum / freqData.length;
            const isSpeaking = avg > 6 && !el.paused;
            notifySpeaking(isSpeaking, isSpeaking ? freqData : null);
            animId = requestAnimationFrame(checkAudio);
          };
          animId = requestAnimationFrame(checkAudio);
          current.teardownAudio = () => {
            if (animId) cancelAnimationFrame(animId);
            actx.close().catch(() => {});
          };
        }
      } catch {
        // Fallback to media element play/pause events
      }

      // Autoplay can still be blocked; the caller is then asked to tap to hear the agent.
      el.play().catch(() => options.onAudioBlocked?.());
    });

    // Server-side Silero VAD handles barge-in cleanly. Do not pause/play the <audio>
    // element on ActiveSpeakersChanged, as pausing a live WebRTC track causes packet
    // dropouts, stuttering, and cuts words in the middle when acoustic echo triggers localSpeaking.
    room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
      if (current.stopped) return;
      const remoteSpeaking = speakers.some((p) => !p.isLocal && p !== room.localParticipant);
      if (remoteSpeaking) {
        options.onAgentSpeaking?.(true);
      }
    });

    // Only the user's own speech goes to the transcript box; agent speech is skipped.
    // Interim and final segments are both sent; the same segment id means the same utterance.
    room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
      if (current.stopped) return;
      if (participant && !participant.isLocal) return;
      for (const seg of segments || []) {
        const segId = typeof seg.id === "string" ? seg.id : "";
        if (!segId) continue;
        const isFinal = seg.final === true;
        const text = typeof seg.text === "string" ? seg.text.trim() : "";
        if (!text) {
          if (isFinal) closeSegment(current, options, segId);
          continue;
        }
        sendSegment(current, options, segId, text, isFinal);
      }
    });

    // Remote end or network loss: clean up and tell the caller the session has ended.
    room.on(RoomEvent.Disconnected, () => {
      if (current.stopped) return;
      if (session === current) session = null;
      teardown(current);
      options.onEnded?.();
    });

    await room.connect(data.url, data.token);
    if (current.stopped) {
      teardown(current);
      return false;
    }
    await room.localParticipant.setMicrophoneEnabled(true, {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    });
    if (current.stopped) {
      teardown(current);
      return false;
    }
    // Connected is not enough: wait for the voice agent to join, or tell the caller to use text.
    const agentJoined = await waitForAgent(room, AGENT_WAIT_MS);
    if (current.stopped) {
      teardown(current);
      return false;
    }
    if (!agentJoined) return fail(current, options, NO_AGENT_MESSAGE);
    return true;
  } catch {
    return fail(current, options);
  }
}

// Replays agent audio after the browser blocked autoplay. Called from a user gesture.
export function resumeVoiceAudio() {
  const current = session;
  if (!current || current.stopped) return;
  current.room?.startAudio?.().catch(() => {});
  for (const { el } of current.audioEls) {
    el.play().catch(() => {});
  }
}

// Stops the running live voice session, if any, and removes its audio elements.
export function stopVoice() {
  const current = session;
  session = null;
  if (current) teardown(current);
}
