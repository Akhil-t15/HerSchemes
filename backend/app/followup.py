"""LLM-powered follow-up chat logic for HerScheme (Module 3).

Uses Groq Cloud (free tier, OpenAI-compatible) to understand user intent,
extract profile facts from natural conversation, and generate helpful
responses about government schemes for women entrepreneurs.

The LLM receives only masked text (privacy.mask_sensitive runs first).
Eligibility is still decided by the deterministic matching engine; the LLM
handles conversation flow and fact extraction only.

Environment variables (read at call time):
  GROQ_API_KEY          Groq Cloud API key (required for LLM mode)
  CHAT_LLM_MODEL        model name on Groq (default: llama-3.3-70b-versatile)
  CHAT_LLM_TIMEOUT      seconds per LLM call (default 10)
  CHAT_DAILY_BUDGET     max LLM calls per UTC day (default 500)
"""

import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.privacy import mask_sensitive
from app.schemes_repo import list_published_schemes

log = logging.getLogger(__name__)

LABEL_LIKELY = "Likely Eligible"
LABEL_NEEDS_INFO = "Needs More Info"
FACT_KEYS = ("location", "shg_member", "business_status", "loan_amount", "past_govt_loan")

PRIVACY_WARNING_EN = "For your safety, numbers like Aadhaar or bank account were hidden. Please do not share them."
PRIVACY_WARNING_TE = (
    "మీ భద్రత కోసం ఆధార్ లేదా బ్యాంక్ ఖాతా వంటి నంబర్లు దాచబడ్డాయి. దయచేసి వాటిని పంచుకోవద్దు."
)
PRIVACY_WARNING = {"en": PRIVACY_WARNING_EN, "te": PRIVACY_WARNING_TE}

MAX_QUESTION_ROUNDS = 5
MAX_QUESTIONS_PER_ROUND = 2

SYSTEM_PROMPT = """\
You are HerScheme Assistant, an expert, warm, and highly adaptive government schemes advisor for women entrepreneurs in Telangana and India.
Your mission is to understand each woman's specific business and funding needs, connect her situation to real government schemes, and ask only relevant, insightful follow-up questions.

IMPORTANT: ADAPT DYNAMICALLY TO HER BUSINESS (DO NOT ACT LIKE A ROBOTIC SURVEY):
1. Tailor your response directly to her specific business and activity:
   - Tailoring / Boutique / Handicrafts / Artisans: Acknowledge her craft. Mention that PM Vishwakarma offers ₹15,000 free toolkit + 5% interest loans, and Indira Mahila Shakti offers school uniform stitching contracts for SHG women. Ask if she needs equipment/machinery or if she is part of an SHG.
   - Food / Pickles / Snacks / Dairy / Agriculture: Acknowledge her food business. Mention that food processing units qualify for up to 35% government subsidies under PMEGP and fast micro-loans under Stree Nidhi. Ask about her location or scale.
   - Retail / Kirana / General Trade: Mention working capital loans like PM Mudra (up to ₹50,000 Shishu, up to ₹5 Lakh Kishore) without collateral.
   - Women's Self-Help Group (SHG) member: Acknowledge her SHG group advantage. Explain how Stree Nidhi (disbursed in 48 hours) and Indira Mahila Shakti give priority zero/low-interest loans to SHG members.
   - Rural / Village resident: Mention that rural women get enhanced 35% subsidies under central schemes.
2. If she has ALREADY provided facts in her message or conversation history (e.g., location, business type, or loan amount), NEVER re-ask them!
3. Ask at most 1 short, focused question per turn that genuinely matters for her business. Briefly explain WHY it helps find the right scheme for her.
4. Keep replies warm, encouraging, and concise (1-3 sentences).
5. When location and business status are known (or after 2 rounds), do NOT ask further questions — warmly conclude and let her know you are presenting the matching schemes.
6. Never promise or guarantee approval — always say "Likely Eligible" or "Needs More Info".
7. Never ask for Aadhaar, PAN, bank account numbers, or sensitive documents.

After your response, output a JSON block on a NEW LINE in this exact format:
```facts
{"location": null, "shg_member": null, "business_status": null, "loan_amount": null, "past_govt_loan": null}
```

Fill in any facts you've learned from the FULL conversation so far. Use null for facts you haven't learned yet. For shg_member and past_govt_loan, use true/false. For location, business_status, and loan_amount, use strings.
"""


def _has_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


# ---------- per-day request budget (in memory only) ----------

_budget_lock = threading.Lock()
_budget_day = None
_budget_used = 0


def _daily_budget() -> int:
    try:
        return max(0, int(os.environ.get("CHAT_DAILY_BUDGET", "500")))
    except ValueError:
        return 500


def try_spend_budget() -> bool:
    global _budget_day, _budget_used
    today = datetime.now(timezone.utc).date()
    with _budget_lock:
        if today != _budget_day:
            _budget_day = today
            _budget_used = 0
        if _budget_used >= _daily_budget():
            return False
        _budget_used += 1
        return True


# ---------- Groq LLM integration ----------

def _groq_model() -> str:
    return os.environ.get("CHAT_LLM_MODEL", "qwen/qwen3.8-27b")


def _llm_timeout() -> float:
    try:
        return float(os.environ.get("CHAT_LLM_TIMEOUT", "15"))
    except ValueError:
        return 15.0


_key_lock = threading.Lock()
_key_index = 0


def _get_groq_api_keys() -> List[str]:
    """Retrieve all available Groq API keys from environment or .env file."""
    keys: List[str] = []

    # Check GROQ_API_KEYS (comma or whitespace separated)
    raw_keys = os.environ.get("GROQ_API_KEYS", "")
    if raw_keys:
        for k in re.split(r"[\s,]+", raw_keys):
            cleaned = k.strip().rstrip(",").strip()
            if cleaned.startswith("gsk_") and cleaned not in keys:
                keys.append(cleaned)

    # Check GROQ_API_KEY
    single = os.environ.get("GROQ_API_KEY", "")
    if single:
        for k in re.split(r"[\s,]+", single):
            cleaned = k.strip().rstrip(",").strip()
            if cleaned.startswith("gsk_") and cleaned not in keys:
                keys.append(cleaned)

    # Check numbered keys GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3
    for i in range(1, 10):
        k = os.environ.get(f"GROQ_API_KEY_{i}", "").strip().rstrip(",").strip()
        if k.startswith("gsk_") and k not in keys:
            keys.append(k)

    # If still empty or fewer than 3 keys, check backend/.env directly
    if len(keys) < 3:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            try:
                content = env_path.read_text(encoding="utf-8")
                found = re.findall(r"gsk_[A-Za-z0-9]+", content)
                for f in found:
                    if f not in keys:
                        keys.append(f)
            except Exception:
                pass

    return keys


def _call_groq(messages: List[Dict[str, str]]) -> Optional[str]:
    """Call Groq's OpenAI-compatible chat completions endpoint with automatic key rotation."""
    global _key_index
    keys = _get_groq_api_keys()
    if not keys:
        log.warning("No GROQ_API_KEY set, falling back to deterministic mode")
        return None
    if not try_spend_budget():
        log.warning("Daily LLM budget exhausted")
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": _groq_model(),
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 512,
    }

    total_keys = len(keys)
    with _key_lock:
        start_idx = _key_index % total_keys

    for attempt in range(total_keys):
        idx = (start_idx + attempt) % total_keys
        api_key = keys[idx]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        try:
            with httpx.Client(timeout=_llm_timeout()) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            choice = data.get("choices", [{}])[0]
            text = choice.get("message", {}).get("content", "")
            if isinstance(text, str) and text.strip():
                with _key_lock:
                    _key_index = idx
                return text
            log.warning("Groq returned empty content with key %s...", api_key[:10])
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            log.warning("Groq key %s... failed with HTTP %s: %s", api_key[:10], status, e.response.text[:120])
            if status in (400, 401, 403, 429, 500, 502, 503, 504) and attempt + 1 < total_keys:
                log.info("Rotating to next available Groq API key (attempt %s/%s)...", attempt + 2, total_keys)
                continue
            return None
        except (httpx.TimeoutException, httpx.RequestError) as e:
            log.warning("Groq network/timeout with key %s...: %s", api_key[:10], e)
            if attempt + 1 < total_keys:
                log.info("Retrying with next Groq API key...")
                continue
            return None
        except Exception as e:
            log.error("Groq API call unexpected error: %s: %s", type(e).__name__, e)
            return None

    return None


def _parse_facts(llm_text: str) -> Dict[str, Any]:
    """Extract the JSON facts block from the LLM response."""
    facts: Dict[str, Any] = {}
    match = re.search(r"```facts\s*\n(.*?)\n```", llm_text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict):
                for key in FACT_KEYS:
                    if key in parsed and parsed[key] is not None:
                        facts[key] = parsed[key]
        except (json.JSONDecodeError, ValueError):
            pass
    return facts


def _clean_response(llm_text: str) -> str:
    """Remove the facts JSON block from the response shown to the user."""
    cleaned = re.sub(r"\s*```facts\s*\n.*?\n```\s*", "", llm_text, flags=re.DOTALL)
    return cleaned.strip()


def _build_messages(
    history: List[Dict[str, str]],
    masked_text: str,
    known_facts: Dict[str, Any],
    lang: str,
    schemes_summary: str,
) -> List[Dict[str, str]]:
    """Build the messages list for the Groq API call."""
    if lang == "te":
        lang_instruction = (
            "CRITICAL LANGUAGE INSTRUCTION:\n"
            "The current user interface language is TELUGU (తెలుగు).\n"
            "You MUST write your entire conversational response in natural, fluent TELUGU SCRIPT (తెలుగు లిపి).\n"
            "Do NOT write in English or Latin transliteration. Use pure Telugu letters for all sentences.\n"
            "Even if the user writes in English, Roman letters, or Tenglish (e.g. 'yes 2 L', 'Warangal', 'tailoring'),\n"
            "your reply MUST be completely in Telugu script.\n"
            "(The JSON ```facts block at the end must still keep its standard English keys)."
        )
    else:
        lang_instruction = (
            "LANGUAGE INSTRUCTION:\n"
            "The user interface language is ENGLISH. Respond in simple, warm, supportive English."
        )

    facts_note = json.dumps({k: known_facts.get(k) for k in FACT_KEYS}, ensure_ascii=False)

    system = (
        f"{SYSTEM_PROMPT}\n\n"
        f"{lang_instruction}\n\n"
        f"Facts gathered so far: {facts_note}\n\n"
        f"Available schemes and key benefits in our database:\n{schemes_summary}"
    )

    messages = [{"role": "system", "content": system}]

    for msg in history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content.strip():
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": masked_text})
    return messages


def _get_schemes_summary(session: Session) -> str:
    """Rich summary of available schemes for the LLM context."""
    schemes = list_published_schemes(session)
    if not schemes:
        return "No schemes currently published."
    lines = []
    for s in schemes:
        name = s.name_en or s.slug
        level = s.level or ""
        lane = s.lane or ""
        b_en = getattr(s, "benefit_en", None) or s.description or ""
        lines.append(f"- {name} ({level}, {lane}): {b_en}")
    return "\n".join(lines)


def build_matches(session: Session, known_facts: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Candidate published schemes with relevance, official URL, and offering benefits."""
    missing = [k for k in FACT_KEYS if not _has_value(known_facts.get(k))]
    status = LABEL_NEEDS_INFO if missing else LABEL_LIKELY
    schemes = list_published_schemes(session)
    if not schemes:
        from app.models import Scheme
        schemes = session.query(Scheme).order_by(Scheme.id).all()

    matches = []
    for s in schemes:
        lane_str = str(s.lane or "").lower()
        is_bank_loan = any(w in lane_str for w in ("loan", "central loan", "bank")) or s.slug in (
            "pm-mudra", "pmegp", "pm-vishwakarma", "stree-nidhi"
        )
        matches.append({
            "slug": s.slug,
            "name_en": s.name_en,
            "name_te": s.name_te,
            "official_url": s.official_url,
            "level": s.level,
            "lane": s.lane,
            "status": status,
            "is_bank_loan": is_bank_loan,
            "benefit_en": getattr(s, "benefit_en", None) or s.description,
            "benefit_te": getattr(s, "benefit_te", None),
            "description": s.description,
        })
    return matches


# ---------- Deterministic fallback (no LLM available) for DEMO ONLY----------

# The ordered list of questions to ask, one at a time
_FALLBACK_FLOW = [
    {
        "key": "location",
        "en": "Which village or town do you live in?",
        "te": "మీరు ఏ గ్రామం లేదా పట్టణంలో నివసిస్తున్నారు?",
    },
    {
        "key": "business_status",
        "en": "Are you starting a new business or already running one?",
        "te": "మీరు కొత్త వ్యాపారం ప్రారంభిస్తున్నారా లేక ఇప్పటికే నడుపుతున్నారా?",
    },
    {
        "key": "shg_member",
        "en": "Are you a member of a Self Help Group (SHG)?",
        "te": "మీరు స్వయం సహాయక సంఘం (SHG) సభ్యురాలా?",
    },
    {
        "key": "loan_amount",
        "en": "About how much loan do you need?",
        "te": "మీకు ఎంత రుణం అవసరం?",
    },
    {
        "key": "past_govt_loan",
        "en": "Have you taken a government loan before?",
        "te": "మీరు గతంలో ప్రభుత్వ రుణం తీసుకున్నారా?",
    },
]


def _extract_heuristics(text: str, facts: Dict[str, Any]) -> Dict[str, Any]:
    """Extract obvious facts directly from free-form text in any turn."""
    lowered = text.lower()
    updated = dict(facts)

    # Business status & intent
    if not _has_value(updated.get("business_status")):
        if any(w in lowered for w in ("start", "starting", "new", "open", "opening", "కొత్త", "ప్రారంభ")):
            updated["business_status"] = "new business"
        elif any(w in lowered for w in ("running", "already", "existing", "expand", "pickle", "pickles", "papad", "food", "నడుపుతున్న", "ఉన్న")):
            updated["business_status"] = "already running"
        elif any(w in lowered for w in ("tailoring", "shop", "boutique", "dairy", "kirana", "beauty", "కుట్టు", "దుకాణం")):
            updated["business_status"] = "new business"

    # SHG membership
    if not _has_value(updated.get("shg_member")):
        if any(w in lowered for w in ("shg", "dwakra", "self help", "డ్వాక్రా", "స్వయం సహాయక", "సంఘం")):
            updated["shg_member"] = True

    # Location (Telangana / AP districts and major cities)
    if not _has_value(updated.get("location")):
        if any(w in lowered for w in ("village", "rural", "గ్రామం", "పల్లె")):
            updated["location"] = "Rural Village"
        elif any(w in lowered for w in ("town", "city", "urban", "పట్టణం", "నగరం")):
            updated["location"] = "Urban Town"
        else:
            districts = (
                "warangal", "karimnagar", "hyderabad", "khammam", "nizamabad", "nalgonda",
                "mahbubnagar", "adilabad", "medak", "rangareddy", "sangareddy", "siddipet",
                "jagtial", "mancherial", "peddapalli", "suryapet", "yadadri", "bhadradri",
                "kothagudem", "kamareddy", "vikarabad", "wanaparthy", "nagarkurnool",
                "jogulamba", "gadwal", "guntur", "vijayawada", "visakhapatnam", "tirupati",
            )
            for d in districts:
                if re.search(r"\b" + re.escape(d) + r"\b", lowered):
                    updated["location"] = d.capitalize()
                    break

    # Loan amount
    if not _has_value(updated.get("loan_amount")):
        match = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lakhs|k|thousand|లక్ష|రూ|rs|inr)", lowered)
        if match:
            updated["loan_amount"] = match.group(0)

    return updated


def _fallback_extract_fact(
    last_question_key: Optional[str],
    user_text: str,
    known_facts: Dict[str, Any],
) -> Dict[str, Any]:
    """In deterministic mode, map the user's answer to the last question asked.

    The user's reply is the answer to whatever question the assistant last asked.
    We store it as-is for free-text facts, or parse yes/no for boolean ones.
    """
    updated = dict(known_facts)
    text = user_text.strip().lower()

    if not text or not last_question_key:
        return updated

    if last_question_key in ("shg_member", "past_govt_loan"):
        yes_words = {"yes", "haan", "ha", "avunu", "అవును", "ఔను", "true", "y"}
        no_words = {"no", "nahi", "ledu", "లేదు", "false", "n"}
        if any(w in text for w in yes_words):
            updated[last_question_key] = True
        elif any(w in text for w in no_words):
            updated[last_question_key] = False
        else:
            updated[last_question_key] = user_text.strip()
    else:
        # location, business_status, loan_amount: store as given
        updated[last_question_key] = user_text.strip()

    return updated


def _fallback_next_question(
    known_facts: Dict[str, Any], lang: str
) -> Optional[Dict[str, str]]:
    """Return the next question to ask, or None if all facts are gathered."""
    for item in _FALLBACK_FLOW:
        if not _has_value(known_facts.get(item["key"])):
            return {"key": item["key"], "text": item[lang if lang == "te" else "en"]}
    return None


def _infer_last_question(history: Optional[List[Dict[str, str]]]) -> Optional[str]:
    """If client didn't send last_question_key, infer it from the last assistant message."""
    if not history:
        return None
    for prev in reversed(history):
        if prev.get("role") == "assistant":
            content = (prev.get("content") or "").lower()
            if any(w in content for w in ("village", "town", "నివసిస్తున్నారు", "location")):
                return "location"
            if any(w in content for w in ("starting a new business", "కొత్త వ్యాపారం", "running one", "business")):
                return "business_status"
            if any(w in content for w in ("self help", "shg", "స్వయం సహాయక")):
                return "shg_member"
            if any(w in content for w in ("how much loan", "రుణం అవసరం", "amount")):
                return "loan_amount"
            if any(w in content for w in ("taken a government loan", "గతంలో ప్రభుత్వ రుణం")):
                return "past_govt_loan"
            break
    return None


def _clean_trailing_question(text: str, lang: str) -> str:
    """When schemes are shown, remove any trailing question sentence or prompt for more info."""
    closing = (
        "మీ వివరాల ఆధారంగా, మీ కోసం సరిపోలే ప్రభుత్వ పథకాలు ఇక్కడ ఉన్నాయి:"
        if lang == "te"
        else "Based on your details, here are the government schemes that match your profile:"
    )
    if not text:
        return closing

    question_starters = (
        "have you", "are you", "do you", "did you", "can you", "will you",
        "how much", "how many", "what is", "what kind", "which village",
        "which town", "which city", "where do", "where are",
        "మీరు", "మీకు", "ఎంత", "ఏ గ్రామం", "తీసుకున్నారా", "ఉన్నారా", "నడుపుతున్నారా"
    )

    raw_sentences = re.split(r"(?<=[.!?\n])\s+", text.strip())
    kept = []
    for s in raw_sentences:
        st = s.strip()
        if not st:
            continue
        lowered = st.lower()
        is_question = st.endswith("?") or any(lowered.startswith(q) for q in question_starters)
        if not is_question:
            kept.append(st)

    intro = " ".join(kept).strip()
    if intro and not intro.endswith((".", "!", "?")):
        intro += "."

    return f"{intro} {closing}".strip() if intro else closing


# ---------- Main entry point ----------

def run_followup(
    session: Session,
    message: str,
    lang: str,
    known_facts: Optional[Dict[str, Any]],
    rounds_asked: int,
    skipped: bool,
    history: Optional[List[Dict[str, str]]] = None,
    last_question_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Full Module 3 turn. Returns only masked text, never the raw message."""
    masked, categories = mask_sensitive(message or "")
    lang = "te" if lang == "te" else "en"
    known_facts = dict(known_facts or {})

    # If skipped or we've exceeded round cap, we're done.
    if skipped or rounds_asked >= MAX_QUESTION_ROUNDS:
        return {
            "reply": None,
            "questions": [],
            "matches": build_matches(session, known_facts),
            "masked_text": masked,
            "done": True,
            "known_facts": known_facts,
            "warning": PRIVACY_WARNING[lang] if categories else None,
            "question_key": None,
        }

    # First, always extract any obvious facts directly from user's message
    if masked.strip():
        known_facts = _extract_heuristics(masked, known_facts)

    # Try the LLM path
    schemes_summary = _get_schemes_summary(session)
    messages = _build_messages(history or [], masked, known_facts, lang, schemes_summary)
    llm_response = _call_groq(messages)

    if llm_response:
        # Extract facts from the LLM output
        new_facts = _parse_facts(llm_response)
        for k, v in new_facts.items():
            if _has_value(v):
                known_facts[k] = v

        reply_text = _clean_response(llm_response)

        # Check if we have enough facts to be "done"
        missing = [k for k in FACT_KEYS if not _has_value(known_facts.get(k))]
        has_key_facts = _has_value(known_facts.get("location")) and _has_value(
            known_facts.get("business_status")
        )
        done = not missing or (has_key_facts and rounds_asked >= 3)

        if not done and missing:
            question_key = missing[0]
        else:
            question_key = None

        if done:
            reply_text = _clean_trailing_question(reply_text, lang)

        return {
            "reply": reply_text,
            "questions": [],
            "matches": build_matches(session, known_facts) if done else [],
            "masked_text": masked,
            "done": done,
            "known_facts": known_facts,
            "warning": PRIVACY_WARNING[lang] if categories else None,
            "question_key": question_key,
        }

    # Fallback: deterministic path when LLM is unavailable.
    # If client didn't supply last_question_key, infer it from history
    effective_last_key = last_question_key or _infer_last_question(history)
    if effective_last_key and masked.strip():
        known_facts = _fallback_extract_fact(effective_last_key, masked, known_facts)

    # Find the next missing fact to ask about.
    next_q = _fallback_next_question(known_facts, lang)
    # Complete and show schemes if all facts are known, or if key facts (location, business, etc.) are gathered
    has_essential_facts = _has_value(known_facts.get("location")) and (
        _has_value(known_facts.get("business_status")) or _has_value(known_facts.get("loan_amount"))
    )
    done = next_q is None or (has_essential_facts and rounds_asked >= 3)
    if done:
        next_q = None

    return {
        "reply": next_q["text"] if next_q else None,
        "questions": [next_q["text"]] if next_q else [],
        "matches": build_matches(session, known_facts) if done else [],
        "masked_text": masked,
        "done": done,
        "known_facts": known_facts,
        "warning": PRIVACY_WARNING[lang] if categories else None,
        "question_key": next_q["key"] if next_q else None,
    }


# Legacy helpers kept for backward compatibility with tests.

def detect_missing_facts(text_or_known_facts):
    if isinstance(text_or_known_facts, dict):
        return [k for k in FACT_KEYS if not _has_value(text_or_known_facts.get(k))]
    return list(FACT_KEYS)


def find_missing(masked_text, known_facts):
    from_known = set(detect_missing_facts(known_facts or {}))
    return [k for k in FACT_KEYS if k in from_known]


def select_questions(missing, lang):
    bank = {item["key"]: item for item in _FALLBACK_FLOW}
    picked = []
    for key in missing:
        if key in bank:
            picked.append({"key": key, "question": bank[key][lang if lang == "te" else "en"], "why": ""})
        if len(picked) >= MAX_QUESTIONS_PER_ROUND:
            break
    return picked


# Keep the LLMProvider class for test compatibility
class LLMProvider:
    def __init__(self, url="", api_key=""):
        self.url = url
        self.api_key = api_key

    def generate(self, prompt, timeout):
        raise NotImplementedError


def get_providers():
    return []
