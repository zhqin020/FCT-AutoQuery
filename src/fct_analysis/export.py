"""Export helpers for CSV/JSON outputs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_case_details(df: pd.DataFrame, out_csv: str | Path) -> None:
    p = Path(out_csv)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)


def write_summary(summary_obj: dict[str, Any], out_json: str | Path) -> None:
    p = Path(out_json)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(summary_obj, fh, indent=2)
"""Export helpers for feature 0005.

Provide CSV and JSON exporters used by CLI and tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_case_details(df: pd.DataFrame, out_csv: str) -> None:
    p = Path(out_csv)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Write a safe CSV with index=False
    df.to_csv(p, index=False)


def write_summary(summary_obj: Any, out_json: str) -> None:
    p = Path(out_json)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(summary_obj, fh, ensure_ascii=False, indent=2)
