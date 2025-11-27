"""Parser utilities for feature 0005.

Exposes `parse_cases(input_path)` which reads exporter JSON (array of Case.to_dict())
and returns a pandas.DataFrame with normalized fields used by downstream modules.
"""
from __future__ import annotations

import json
from typing import List
from datetime import datetime

import pandas as pd


def _normalize_date(d: str) -> str | None:
    if not d:
        return None
    try:
        return pd.to_datetime(d).date().isoformat()
    except Exception:
        return None


def parse_cases(input_path: str) -> pd.DataFrame:
    """Load exporter JSON file and return normalized DataFrame.

    The returned DataFrame contains at minimum these columns:
      - case_number
      - filing_date (ISO YYYY-MM-DD or None)
      - docket_entries (list of dicts)

    Tests should use `tests/fixtures/0005_cases.json` as input.
    """
    with open(input_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    rows: List[dict] = []
    for case in data:
        case_number = case.get("case_number") or case.get("case_id")
        filing_date = _normalize_date(case.get("filing_date") or case.get("date"))
        docket_entries = case.get("docket_entries") or []
        rows.append({
            "case_number": case_number,
            "filing_date": filing_date,
            "docket_entries": docket_entries,
            "raw": case,
        })

    df = pd.DataFrame(rows)
    return df
