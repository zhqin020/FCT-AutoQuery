"""Export helpers for CSV/JSON outputs (clean).
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd


def _convert_decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: _convert_decimal_to_float(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_convert_decimal_to_float(item) for item in obj]
    return obj


def write_case_details(df: pd.DataFrame, out_csv: str) -> None:
    p = Path(out_csv)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)


def write_summary(summary_obj: Any, out_json: str) -> None:
    p = Path(out_json)
    p.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert Decimal objects to float for JSON serialization
    summary_obj = _convert_decimal_to_float(summary_obj)
    
    with p.open("w", encoding="utf-8") as fh:
        json.dump(summary_obj, fh, ensure_ascii=False, indent=2)
