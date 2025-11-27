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
