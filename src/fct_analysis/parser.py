"""Parser utilities for feature 0005.

Exposes `parse_cases(input_path)` which reads either:
    - a single exporter JSON file containing an array of cases, or
    - a directory containing many per-case JSON files.

Returns a pandas.DataFrame with normalized fields used by downstream modules.
"""
from __future__ import annotations

import json
from typing import List
from pathlib import Path

import pandas as pd


def _parse_cases_list(data: List[dict]) -> pd.DataFrame:
    """Parse a list of case dictionaries (for database/directory sources)."""
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


def _normalize_date(d: str) -> str | None:
    if not d:
        return None
    try:
        return pd.to_datetime(d).date().isoformat()
    except Exception:
        return None


def parse_cases(input_path: str) -> pd.DataFrame:
    """Load exporter data from `input_path` and return normalized DataFrame.

    `input_path` may be:
      - path to a JSON file containing an array of case dicts, or
      - path to a directory containing many per-case JSON files (will load all
        files ending with `.json` in alphanumeric order).

    The returned DataFrame contains at minimum these columns:
      - case_number
      - filing_date (ISO YYYY-MM-DD or None)
      - docket_entries (list of dicts)
    """
    p = Path(input_path)

    data: List[dict] = []
    if p.is_dir():
        # load each JSON file
        for child in sorted(p.iterdir()):
            if child.is_file() and child.suffix.lower() == ".json":
                try:
                    with child.open("r", encoding="utf-8") as fh:
                        obj = json.load(fh)
                        # some per-case files may already be a dict
                        if isinstance(obj, list):
                            data.extend(obj)
                        else:
                            data.append(obj)
                except Exception:
                    # ignore malformed files but continue
                    continue
    else:
        # assume a single JSON file containing an array
        with open(input_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

    return _parse_cases_list(data)
