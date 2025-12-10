"""Heuristic extractors for Visa Office and Judge from case text.

These are cheap, fast heuristics used before falling back to LLM calls.
"""
from __future__ import annotations

import re
from typing import Optional


COMMON_VISA_OFFICES = [
    "Beijing",
    "Ankara",
    "New Delhi",
    "Delhi",
    "Mumbai",
    "London",
    "Islamabad",
    "Lagos",
    "Accra",
    "Manila",
    "Mexico City",
    "Tehran",
    "Cairo",
    "Nairobi",
]


def extract_visa_office_heuristic(text: str) -> Optional[str]:
    if not text:
        return None
    for office in COMMON_VISA_OFFICES:
        if re.search(r"\b" + re.escape(office) + r"\b", text, re.I):
            return office
    # look for patterns like 'Visa Office: X' or 'Visa Office - X'
    m = re.search(r"Visa Office[:\-]\s*([A-Za-z \.\-]{2,40})", text, re.I)
    if m:
        return m.group(1).strip()
    return None


def extract_judge_heuristic(text: str) -> Optional[str]:
    if not text:
        return None
    # common patterns: 'Judge Smith', 'per Justice Smith', 'Justice Smith'
    m = re.search(r"(?:Judge|Justice|per Justice)\.?:?\s*([A-Z][A-Za-z\-]+(?:\s[A-Z][A-Za-z\-]+)?)", text)
    if m:
        return m.group(1).strip()
    # patterns like 'Reasons of [Name]'
    m2 = re.search(r"Reasons of Judge\s+([A-Z][A-Za-z\-]+)", text)
    if m2:
        return m2.group(1).strip()
    return None
