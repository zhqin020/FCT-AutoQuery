#!/usr/bin/env python3
"""Lightweight analysis script for quick testing without pandas.

Usage:
  python scripts/analysis_simple.py --input output/json/2021 --output-dir output/analysis/simple

This script implements rule-based classification and basic duration metrics
using only the Python standard library so it can run in minimal environments.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, date
from pathlib import Path
import re
import csv
from statistics import mean, median
from typing import Any, List, Dict


MANDAMUS_RE = re.compile(r"\b(mandamus|compel|delay)\b", re.I)
DISCONTINUED_RE = re.compile(r"notice of discontinuance", re.I)
GRANTED_RE = re.compile(r"\b(granted|allowed)\b", re.I)
DISMISSED_RE = re.compile(r"\b(dismissed)\b", re.I)


def load_cases(path: Path) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    if path.is_dir():
        for p in sorted(path.iterdir()):
            if p.is_file() and p.suffix.lower() == ".json":
                try:
                    with open(p, "r", encoding="utf-8") as fh:
                        obj = json.load(fh)
                        if isinstance(obj, list):
                            cases.extend(obj)
                        else:
                            cases.append(obj)
                except Exception:
                    continue
    else:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                cases.extend(data)
            else:
                cases.append(data)
    return cases


def _text_from_case(case: Dict[str, Any]) -> str:
    parts = []
    parts.append(case.get("style_of_cause", "") or "")
    parts.append(case.get("title", "") or "")
    for de in case.get("docket_entries") or []:
        parts.append(de.get("summary") or "")
    return "\n".join([p for p in parts if p])


def classify_case(case: Dict[str, Any]) -> Dict[str, str]:
    text = _text_from_case(case)
    if MANDAMUS_RE.search(text):
        typ = "Mandamus"
    else:
        typ = "Other"

    if DISCONTINUED_RE.search(text):
        status = "Discontinued"
    elif GRANTED_RE.search(text):
        status = "Granted"
    elif DISMISSED_RE.search(text):
        status = "Dismissed"
    else:
        status = "Ongoing"

    return {"type": typ, "status": status}


def iso_date(s: Any) -> str | None:
    if not s:
        return None
    if isinstance(s, str):
        try:
            # Try to parse common formats and return YYYY-MM-DD
            dt = datetime.fromisoformat(s)
            return dt.date().isoformat()
        except Exception:
            # fallback try date only
            try:
                return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
            except Exception:
                return None
    return None


def days_between(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        da = datetime.fromisoformat(a).date()
        db = datetime.fromisoformat(b).date()
        return (db - da).days
    except Exception:
        return None


def analyze(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    today = date.today().isoformat()
    details: List[Dict[str, Any]] = []
    durations: List[int] = []

    type_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}

    for case in cases:
        cn = case.get("case_number") or case.get("case_id")
        filing = iso_date(case.get("filing_date") or case.get("date"))
        de = case.get("docket_entries") or []

        cl = classify_case(case)
        typ = cl["type"]
        status = cl["status"]

        type_counts[typ] = type_counts.get(typ, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1

        outcome = case.get("outcome_date") or case.get("decision_date")
        outcome = iso_date(outcome)
        time_to_close = days_between(filing, outcome) if outcome else None
        age_of_case = days_between(filing, today) if (filing and not outcome) else None

        if time_to_close is not None:
            durations.append(time_to_close)

        details.append({
            "case_number": cn,
            "filing_date": filing,
            "type": typ,
            "status": status,
            "outcome_date": outcome,
            "time_to_close": time_to_close,
            "age_of_case": age_of_case,
        })

    summary: Dict[str, Any] = {
        "total_cases": len(cases),
        "types": type_counts,
        "statuses": status_counts,
    }

    if durations:
        summary["durations"] = {
            "mean": mean(durations),
            "median": median(durations),
            "min": min(durations),
            "max": max(durations),
        }
    else:
        summary["durations"] = None

    return {"summary": summary, "details": details}


def write_outputs(out_dir: Path, result: Dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # write summary
    with open(out_dir / "federal_cases_simple_summary.json", "w", encoding="utf-8") as fh:
        json.dump(result["summary"], fh, ensure_ascii=False, indent=2)

    # write details CSV
    keys = ["case_number", "filing_date", "type", "status", "outcome_date", "time_to_close", "age_of_case"]
    with open(out_dir / "federal_cases_simple_details.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for row in result["details"]:
            w.writerow({k: row.get(k) for k in keys})


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analysis_simple")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default="output/analysis/simple")
    ns = parser.parse_args(argv)

    path = Path(ns.input)
    cases = load_cases(path)
    result = analyze(cases)
    write_outputs(Path(ns.output_dir), result)
    print(json.dumps(result["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
