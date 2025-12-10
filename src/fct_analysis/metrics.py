"""Metrics computations for fct_analysis (clean).

Provides `compute_durations(df)` returning DataFrame with `age_of_case`,
`time_to_close` and `rule9_wait` fields (best-effort placeholders).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


def _to_date(d: Any) -> pd.Timestamp | pd.NaT:
    if d is None:
        return pd.NaT
    try:
        return pd.to_datetime(d)
    except Exception:
        return pd.NaT


def compute_durations(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Use timezone-aware UTC date for 'today' to avoid deprecation warnings
    today_date = datetime.now(timezone.utc).date()

    df["filing_date_parsed"] = df.get("filing_date").apply(_to_date) if "filing_date" in df else pd.NaT

    def _age(row: Any) -> int | None:
        fd = row.get("filing_date_parsed")
        if fd is pd.NaT or fd is None:
            return None
        try:
            # Compute using dates to avoid tz-aware vs naive Timestamp issues
            return int((today_date - fd.date()).days)
        except Exception:
            return None

    df["age_of_case"] = df.apply(_age, axis=1)

    # time_to_close: look for outcome_date or decision_date in raw
    def _time_to_close(row: Any) -> int | None:
        raw = row.get("raw") or {}
        filing = row.get("filing_date_parsed")
        outcome = raw.get("outcome_date") or raw.get("decision_date")
        outd = _to_date(outcome)
        if filing is pd.NaT or outd is pd.NaT:
            return None
        try:
            return int((outd - filing).days)
        except Exception:
            return None

    df["time_to_close"] = df.apply(_time_to_close, axis=1)

    # rule9_wait: find first docket entry with summary mentioning Rule 9
    import re

    RULE9_RE = re.compile(r"rule\s*9", re.I)

    def _rule9_wait(row: Any) -> int | None:
        filing = row.get("filing_date_parsed")
        if filing is pd.NaT:
            return None
        for de in row.get("docket_entries") or []:
            summary = de.get("summary") or ""
            if RULE9_RE.search(summary):
                entry_date = _to_date(de.get("entry_date"))
                if entry_date is pd.NaT:
                    return None
                try:
                    return int((entry_date - filing).days)
                except Exception:
                    return None
        return None

    df["rule9_wait"] = df.apply(_rule9_wait, axis=1)

    return df
