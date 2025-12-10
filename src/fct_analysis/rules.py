"""Rule-based classifier for case type and status.

This module contains minimal, deterministic keyword rules used by the MVP.
"""
from __future__ import annotations

from typing import Any


MANDAMUS_KEYWORDS = ("mandamus", "compel", "delay")


def _text_from_row(row: Any) -> str:
    parts = [
        str(row.get("style_of_cause", "") or ""),
    ]
    for de in row.get("docket_entries", []) or []:
        parts.append(str(de.get("summary", "")))
    return " ".join(parts).lower()


def classify_case_rule(row: Any) -> dict[str, str]:
    """Given a row-like mapping, return a minimal classification dict.

    Returns: {"type": "Mandamus"|"Other", "status": "Ongoing"|"Discontinued"|"Granted"|"Dismissed"}
    """
    text = _text_from_row(row)
    ctype = "Mandamus" if any(k in text for k in MANDAMUS_KEYWORDS) else "Other"
    # Simple status priority checks
    if "notice of discontinuance" in text:
        status = "Discontinued"
    elif "granted" in text or "allowed" in text:
        status = "Granted"
    elif "dismissed" in text:
        status = "Dismissed"
    else:
        status = "Ongoing"
    return {"type": ctype, "status": status}
"""Rule-based classifier for feature 0005 (quick mode).

Provides `classify_case_rule(case_obj)` which returns a dict with `type` and
`status` keys. The implementation is intentionally simple and deterministic
so tests can run offline.
"""
from __future__ import annotations

import re
from typing import Any


MANDAMUS_RE = re.compile(r"\b(mandamus|compel|delay)\b", re.I)
DISCONTINUED_RE = re.compile(r"notice of discontinuance", re.I)
GRANTED_RE = re.compile(r"\b(granted|allowed)\b", re.I)
DISMISSED_RE = re.compile(r"\b(dismissed)\b", re.I)


def _text_from_case(case: Any) -> str:
    parts = []
    if isinstance(case, dict):
        parts.append(case.get("style_of_cause") or "")
        parts.append(case.get("title") or "")
        for de in case.get("docket_entries") or []:
            parts.append(de.get("summary") or "")
    else:
        # assume series-like
        parts.append(str(case.get("style_of_cause", "")))
    return "\n".join([p for p in parts if p])


def classify_case_rule(case_obj: Any) -> dict:
    """Classify a single case using keyword rules.

    Returns a dict: {"type": "Mandamus"|"Other", "status": 'Discontinued'|'Granted'|'Dismissed'|'Ongoing'}
    """
    text = _text_from_case(case_obj)

    # Type
    if MANDAMUS_RE.search(text):
        typ = "Mandamus"
    else:
        typ = "Other"

    # Status priority
    if DISCONTINUED_RE.search(text):
        status = "Discontinued"
    elif GRANTED_RE.search(text):
        status = "Granted"
    elif DISMISSED_RE.search(text):
        status = "Dismissed"
    else:
        status = "Ongoing"

    return {"type": typ, "status": status}
