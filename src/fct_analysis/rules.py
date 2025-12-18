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

# More precise patterns for outcome detection
# These patterns should be more specific to avoid false positives
GRANTED_RE = re.compile(r"\b(granted|allowed)\b.*(application|appeal|petition|leave|judicial review)", re.I)
DISMISSED_RE = re.compile(r"\b(dismissed|dismissing|denied|rejected|refused)\b.*(application|appeal|petition|leave|judicial review)", re.I)

# Entity extraction patterns
VISA_OFFICE_RE = re.compile(r"\b((?:Vancouver|Calgary|Toronto|Montreal|Ottawa|Edmonton|Winnipeg|Halifax|Victoria|Quebec|London|Hamilton|Saskatoon|Regina|St\. John's|Charlottetown|Fredericton|Moncton|Windsor|Kitchener|Burnaby|Richmond|Surrey|Kelowna|Abbotsford|Coquitlam|Saanich|Nanaimo|Prince George|Kamloops|Cranbrook|Penticton|Fort St\. John|Dawson Creek|Terrace|Prince Rupert|Williams Lake|Merritt|Campbell River|Port Alberni|Parksville|Courtenay|Comox|Duncan|Nanaimo|Powell River|Sechelt|Sunshine Coast|Whistler|Squamish|North Vancouver|West Vancouver|New Westminster|Maple Ridge|Coquitlam|Port Coquitlam|Port Moody|Delta|Surrey|Langley|Abbotsford|Chilliwack|Mission|Hope|Princeton|Merritt|Kamloops|Vernon|Kelowna|Penticton|Cranbrook|Nelson|Castlegar|Trail|Grand Forks|Creston|Fernie|Sparwood|Kimberley|Invermere|Golden|Canmore|Banff|Jasper|Hinton|Edson|Whitecourt|Slave Lake|High Level|Fort McMurray|Cold Lake|Lloydminster|North Battleford|Prince Albert|Moose Jaw|Swift Current|Yorkton|Estevan|Weyburn|Melville|Yorkton|Regina|Saskatoon|Prince Albert|Moose Jaw|Swift Current|Brandon|Portage la Prairie|Steinbach|Thompson|Dauphin|Flin Flon|Churchill|Selkirk|Morden|Winkler|Altona|Plum Coulee|Carman|Morris|Gimli|Selkirk|Beausejour|Lac du Bonnet|Steinbach|Niverville|St\. Pierre-Jolys|Emerson|Gretna|Morden|Winkler|Altona|Plum Coulee|Carman|Morris|Gimli|Selkirk|Beausejour|Lac du Bonnet|Steinbach|Niverville|St\. Pierre-Jolys|Emerson|Gretna|Morden|Winkler|Altona|Plum Coulee|Carman|Morris|Gimli|Selkirk|Beausejour|Lac du Bonnet|Steinbach|Niverville|St\. Pierre-Jolys|Emerson|Gretna|Morden|Winkler|Altona|Plum Coulee|Carman|Morris|Gimli|Selkirk|Beausejour|Lac du Bonnet|Steinbach|Niverville|St\. Pierre-Jolys|Emerson|Gretna) (?:Visa|Immigration|Application Centre|Office|Centre))\b", re.I)

JUDGE_PATTERN_RE = re.compile(r"\b(Judge|Justice|The Honourable|Hon\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", re.I)


def _text_from_case(case: Any) -> str:
    parts = []
    if isinstance(case, dict):
        parts.append(case.get("style_of_cause") or "")
        parts.append(case.get("title") or "")
        for de in case.get("docket_entries") or []:
            # Try both possible field names for summary
            summary = de.get("summary") or de.get("recorded_entry_summary") or ""
            parts.append(summary)
    else:
        # assume series-like
        parts.append(str(case.get("style_of_cause", "")))
    return "\n".join([p for p in parts if p])


def classify_case_rule(case_obj: Any) -> dict:
    """Classify a single case using keyword rules.

    Returns the full classification result including entities and metadata.
    """
    from .nlp_engine import get_nlp_engine
    return get_nlp_engine().classify_case(case_obj)
