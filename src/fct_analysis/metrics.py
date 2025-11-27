"""Metrics computations for feature 0005.

Provides `compute_durations(df)` which returns a copy of the DataFrame with
`time_to_close`, `age_of_case`, and `rule9_wait` columns where applicable.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


def compute_durations(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    today = date.today()

    def _days_between(a: str | None, b: str | None) -> float | None:
        if not a or not b:
            return None
        try:
            da = datetime.fromisoformat(a).date()
            db = datetime.fromisoformat(b).date()
            return (db - da).days
        except Exception:
            return None

    # time_to_close: outcome_date - filing_date if outcome_date exists in raw
    def _compute_time_to_close(row: Any) -> float | None:
        raw = row.get("raw") or {}
        filing = row.get("filing_date")
        outcome = raw.get("outcome_date") or raw.get("decision_date")
        return _days_between(filing, outcome)

    df["time_to_close"] = df.apply(_compute_time_to_close, axis=1)

    def _compute_age(row: Any) -> float | None:
        filing = row.get("filing_date")
        if not filing:
            return None
        try:
            fd = datetime.fromisoformat(filing).date()
            return (today - fd).days
        except Exception:
            return None

    df["age_of_case"] = df.apply(_compute_age, axis=1)

    # rule9_wait: find first docket entry with summary matching Rule 9 keywords
    import re

    RULE9_RE = re.compile(r"rule\s*9", re.I)

    def _rule9_wait(row: Any) -> float | None:
        filing = row.get("filing_date")
        if not filing:
            return None
        for de in row.get("docket_entries") or []:
            summary = de.get("summary") or ""
            if RULE9_RE.search(summary):
                entry_date = de.get("entry_date")
                return _days_between(filing, entry_date)
        return None

    df["rule9_wait"] = df.apply(_rule9_wait, axis=1)

    return df
