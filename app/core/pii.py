"""PII / secret detection + redaction (R9). Deterministic — safety must not depend on
the LLM. Used by the critic (pii_risk), the handoff bundle, and the Phase 5 redaction
pass over every response, bundle and log line.

Target: zero PII/secret leakage. Redaction replaces with typed placeholders so the
structure is still readable.
"""
from __future__ import annotations

import re
from typing import Any

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# card: 13-19 digits possibly separated by spaces/dashes (card_last4 of 4 digits won't match)
CARD = re.compile(r"\b(?:\d[ \-]?){13,19}\b")
PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[ \-.]?)?(?:\(?\d{3}\)?[ \-.]?)\d{3}[ \-.]?\d{4}(?!\d)")
# secrets: sk-… style keys, bearer tokens, api_key=…, long hex/base64 blobs
SECRET = re.compile(
    r"\b(?:sk-[A-Za-z0-9]{12,}|tok_[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._\-]{12,}"
    r"|(?:api[_\-]?key|token|secret|password)\s*[=:]\s*\S+"
    r"|[A-Fa-f0-9]{32,}|[A-Za-z0-9_\-]{40,})\b",
    re.IGNORECASE,
)

_ORDER = [("[SECRET]", SECRET), ("[EMAIL]", EMAIL), ("[CARD]", CARD), ("[PHONE]", PHONE)]


def detect(text: str) -> list[dict]:
    if not text:
        return []
    found = []
    for label, rx in _ORDER:
        for m in rx.finditer(text):
            found.append({"type": label.strip("[]").lower(), "match": m.group(0)[:4] + "…"})
    return found


def risk(text: str) -> str:
    """Highest risk level present in text: none|low|medium|high."""
    if not text:
        return "none"
    if SECRET.search(text) or CARD.search(text):
        return "high"
    if EMAIL.search(text) or PHONE.search(text):
        return "medium"
    return "none"


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    for label, rx in _ORDER:
        out = rx.sub(label, out)
    return out


def redact_obj(obj: Any) -> Any:
    """Recursively redact every string inside a dict/list structure."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    return obj
