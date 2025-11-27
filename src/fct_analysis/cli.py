"""CLI entrypoint for fct_analysis feature (minimal).

Provides `analyze` command supporting `--mode rule` for MVP.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parser import parse_cases
from .rules import classify_case_rule
from .metrics import compute_durations
from .export import write_case_details, write_summary


def analyze(args: list | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fct_analysis.analyze")
    parser.add_argument("--input", required=True)
    parser.add_argument("--mode", choices=["rule", "llm"], default="rule")
    parser.add_argument("--output-dir", default="output/")
    ns = parser.parse_args(args=args)

    df = parse_cases(ns.input)

    if ns.mode == "rule":
        # apply classification
        types = []
        statuses = []
        for _, row in df.iterrows():
            res = classify_case_rule(row.get("raw") or {})
            types.append(res.get("type"))
            statuses.append(res.get("status"))
        df["type"] = types
        df["status"] = statuses

    # metrics
    df2 = compute_durations(df)

    out_dir = Path(ns.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    details_csv = out_dir / "federal_cases_0005_details.csv"
    summary_json = out_dir / "federal_cases_0005_summary.json"

    write_case_details(df2, str(details_csv))

    # simple summary
    summary = {
        "total_cases": int(len(df2)),
        "types": df2["type"].value_counts().to_dict() if "type" in df2 else {},
    }
    write_summary(summary, str(summary_json))

    return 0


def main() -> None:
    rc = analyze()
    sys.exit(rc)


if __name__ == "__main__":
    main()
