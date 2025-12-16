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

# Entity extraction patterns
VISA_OFFICE_RE = re.compile(r"\b((?:Vancouver|Calgary|Toronto|Montreal|Ottawa|Edmonton|Winnipeg|Halifax|Victoria|Quebec|London|Hamilton|Saskatoon|Regina|St\. John's|Charlottetown|Fredericton|Moncton|Windsor|Kitchener|Burnaby|Richmond|Surrey|Kelowna|Abbotsford|Coquitlam|Saanich|Nanaimo|Prince George|Kamloops|Cranbrook|Penticton|Fort St\. John|Dawson Creek|Terrace|Prince Rupert|Williams Lake|Merritt|Campbell River|Port Alberni|Parksville|Courtenay|Comox|Duncan|Nanaimo|Powell River|Sechelt|Sunshine Coast|Whistler|Squamish|North Vancouver|West Vancouver|New Westminster|Maple Ridge|Coquitlam|Port Coquitlam|Port Moody|Delta|Surrey|Langley|Abbotsford|Chilliwack|Mission|Hope|Princeton|Merritt|Kamloops|Vernon|Kelowna|Penticton|Cranbrook|Nelson|Castlegar|Trail|Grand Forks|Creston|Fernie|Sparwood|Kimberley|Invermere|Golden|Canmore|Banff|Jasper|Hinton|Edson|Whitecourt|Slave Lake|High Level|Fort McMurray|Cold Lake|Lloydminster|North Battleford|Prince Albert|Moose Jaw|Swift Current|Yorkton|Estevan|Weyburn|Melville|Yorkton|Regina|Saskatoon|Prince Albert|Moose Jaw|Swift Current|Brandon|Portage la Prairie|Steinbach|Thompson|Dauphin|Flin Flon|Churchill|Selkirk|Morden|Winkler|Altona|Plum Coulee|Carman|Morris|Gimli|Selkirk|Beausejour|Lac du Bonnet|Steinbach|Niverville|St\. Pierre-Jolys|Emerson|Gretna|Morden|Winkler|Altona|Plum Coulee|Carman|Morris|Gimli|Selkirk|Beausejour|Lac du Bonnet|Steinbach|Niverville|St\. Pierre-Jolys|Emerson|Gretna|Morden|Winkler|Altona|Plum Coulee|Carman|Morris|Gimli|Selkirk|Beausejour|Lac du Bonnet|Steinbach|Niverville|St\. Pierre-Jolys|Emerson|Gretna|Morden|Winkler|Altona|Plum Coulee|Carman|Morris|Gimli|Selkirk|Beausejour|Lac du Bonnet|Steinbach|Niverville|St\. Pierre-Jolys|Emerson|Gretna) (?:Visa|Immigration|Application Centre|Office|Centre))\b", re.I)

JUDGE_PATTERN_RE = re.compile(r"\b(Judge|Justice|The Honourable|Hon\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", re.I)


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


def extract_entities_rule(case_obj: Any) -> dict:
    """Extract basic entities (visa office, judge) using pattern matching.
    
    Returns a dict: {"visa_office": str|None, "judge": str|None}
    """
    text = _text_from_case(case_obj)
    
    visa_office = None
    judge = None
    
    # Extract visa office
    visa_match = VISA_OFFICE_RE.search(text)
    if visa_match:
        visa_office = visa_match.group(1).strip()
    
    # Extract judge name
    judge_match = JUDGE_PATTERN_RE.search(text)
    if judge_match:
        judge = judge_match.group(2).strip()
    
    return {
        "visa_office": visa_office,
        "judge": judge
    }
