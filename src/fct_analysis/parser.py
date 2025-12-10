"""Parser utilities for fct_analysis feature.

Minimal implementations to load exporter JSON and return a pandas.DataFrame.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def parse_cases(input_path: str | Path) -> pd.DataFrame:
    p = Path(input_path)
    with p.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    # Expecting a list of dict-like case objects
    if not isinstance(data, list):
        raise ValueError("Expected exporter JSON array of case objects")
    # Normalize simple fields into DataFrame; keep nested docket_entries as-is
    rows: list[dict[str, Any]] = []
    for case in data:
        rows.append(
            {
                "case_number": case.get("case_number") or case.get("case_id") or case.get("caseId"),
                "filing_date": case.get("filing_date") or case.get("date") or None,
                "style_of_cause": case.get("style_of_cause") or case.get("title") or "",
                "court_office": case.get("office") or case.get("court") or None,
                "docket_entries": case.get("docket_entries") or [],
                **{k: v for k, v in case.items() if k not in ("docket_entries",)},
            }
        )
    df = pd.DataFrame(rows)
    return df
"""Parser utilities for feature 0005.

Exposes `parse_cases(input_path)` which reads either:
    - a single exporter JSON file containing an array of cases, or
    - a directory containing many per-case JSON files.

Returns a pandas.DataFrame with normalized fields used by downstream modules.
"""
from __future__ import annotations

import json
from typing import List
from datetime import datetime
from pathlib import Path

import pandas as pd


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

    This makes the CLI usable directly against `output/json/<year>/` folders.
    """
    p = Path(input_path)

    data: List[dict] = []
    if p.is_dir():
        # load each JSON file
        for child in sorted(p.iterdir()):
            if child.is_file() and child.suffix.lower() == ".json":
                try:
                    with open(child, "r", encoding="utf-8") as fh:
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
