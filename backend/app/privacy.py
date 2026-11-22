"""Privacy shield for HerScheme.

Hides Aadhaar, PAN, Voter ID, ration card and bank account numbers in user text
before it reaches the AI layer, the database or logs. The original text is never
stored. This is best-effort pattern matching: ration card formats differ by state,
so that check relies on nearby context words. Matched values are never logged.
"""
import re

PRIVACY_NOTICE_EN = (
    "Please do not share Aadhaar, PAN, Voter ID, ration card or bank account numbers. "
    "We hide them automatically."
)
PRIVACY_NOTICE_TE = (
    "దయచేసి ఆధార్, పాన్, ఓటర్ ఐడీ, రేషన్ కార్డు లేదా బ్యాంక్ ఖాతా నంబర్లను పంచుకోవద్దు. "
    "మేము వాటిని స్వయంచాలకంగా దాచిపెడతాము."
)

_AADHAAR = re.compile(r"\b[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}\b")
_PAN = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")
_VOTER_ID = re.compile(r"\b[A-Za-z]{3}\d{7}\b")
_BANK = re.compile(r"\b\d{9,18}\b")
_DIGITS_10_12 = re.compile(r"\b\d{10,12}\b")
_RATION_WORDS = re.compile(r"ration|రేషన్", re.IGNORECASE)

# Order matters: Aadhaar before bank account; ration card before bank account.
_SIMPLE_RULES = [
    ("aadhaar", _AADHAAR, "[AADHAAR HIDDEN]"),
    ("pan", _PAN, "[PAN HIDDEN]"),
    ("voter_id", _VOTER_ID, "[VOTER ID HIDDEN]"),
]


def _mask_ration_card(text):
    """Mask 10-12 digit runs that follow a ration-card word within 20 characters."""
    pieces = []
    last = 0
    found = False
    for m in _DIGITS_10_12.finditer(text):
        window = text[max(0, m.start() - 20):m.start()]
        if _RATION_WORDS.search(window):
            pieces.append(text[last:m.start()])
            pieces.append("[RATION CARD HIDDEN]")
            last = m.end()
            found = True
    pieces.append(text[last:])
    return "".join(pieces), found


def mask_sensitive(text):
    """Return (masked_text, categories_found). Categories are names only, never values."""
    if not text:
        return "", []
    categories = []
    for name, pattern, token in _SIMPLE_RULES:
        text, found = pattern.subn(token, text)
        if found:
            categories.append(name)
    text, found = _mask_ration_card(text)
    if found:
        categories.append("ration_card")
    text, found = _BANK.subn("[ACCOUNT NUMBER HIDDEN]", text)
    if found:
        categories.append("bank_account")
    return text, categories


def contains_sensitive(text):
    _, categories = mask_sensitive(text)
    return bool(categories)
