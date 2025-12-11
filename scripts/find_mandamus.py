#!/usr/bin/env python3
"""Scan a directory of JSON case files and list cases classified as 'Mandamus'.

Usage: python scripts/find_mandamus.py [PATH]

Defaults to `output/json`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable


def scan_json_dir(dirpath: Path) -> int:
    try:
        from fct_analysis.rules import classify_case_rule
    except Exception as e:
        print("Failed to import classifier from fct_analysis.rules:", e, file=sys.stderr)
        return 2

    if not dirpath.exists():
        print("Path not found:", dirpath, file=sys.stderr)
        return 1

    matches = 0
    for p in sorted(dirpath.rglob("*.json")):
        try:
            with p.open("r", encoding="utf-8") as fh:
                obj = json.load(fh)
        except Exception:
            # skip malformed JSON
            continue

        items: Iterable[dict] = obj if isinstance(obj, list) else [obj]
        for case in items:
            try:
                cls = classify_case_rule(case)
            except Exception:
                continue
            if cls.get("type") == "Mandamus":
                case_no = case.get("case_number") or case.get("case_id") or ""
                title = (case.get("title") or case.get("style_of_cause") or "").replace("\n", " ")
                status = cls.get("status") or ""
                print(f"{p}\t{case_no}\t{title}\t{status}")
                matches += 1

    if matches == 0:
        print("No Mandamus cases found.")
    else:
        print(f"Found {matches} Mandamus case(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output/json")
    raise SystemExit(scan_json_dir(path))
