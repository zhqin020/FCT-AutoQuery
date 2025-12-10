"""Simple heuristic extractors for Visa Office and Judge.

These are lightweight, deterministic functions used before falling back to LLM.
They use regexes and known name lists to pick likely values from free text.
"""
from __future__ import annotations

import re
from typing import Optional


VISABOX_RE = re.compile(r"\b(Beijing|Ankara|New Delhi|Delhi|Toronto|Vancouver|London|Mumbai|Ottawa)\b", re.I)
JUDGE_RE = re.compile(r"\bJustice\s+([A-Z][a-z]+)|\bJudge\s+([A-Z][a-z]+)", re.I)


def extract_visa_office_heuristic(text: str) -> Optional[str]:
    if not text:
        return None
    m = VISABOX_RE.search(text)
    if m:
        return m.group(1)
    return None


def extract_judge_heuristic(text: str) -> Optional[str]:
    if not text:
        return None
    m = JUDGE_RE.search(text)
    if m:
        # group may be in either group 1 or 2
        return (m.group(1) or m.group(2))
    return None