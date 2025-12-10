"""CLI entrypoint for fct_analysis feature.

Provides a minimal `analyze` command stub wired to the library functions.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import parser as _parser
from . import rules as _rules
from . import metrics as _metrics
from . import export as _export


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="fct_analysis")
    sub = p.add_subparsers(dest="command")

    analyze = sub.add_parser("analyze", help="Run analysis pipeline")
    analyze.add_argument("--input", "-i", required=True, help="Path to exporter JSON file")
    analyze.add_argument("--mode", choices=("rule", "llm"), default="rule")
    analyze.add_argument("--output-dir", "-o", default="output/")

    sub.add_parser("version", help="Show package version")
    return p


def analyze(input_path: str, mode: str = "rule", output_dir: str | Path | None = None) -> int:
    output_dir = Path(output_dir or "output/")
    output_dir.mkdir(parents=True, exist_ok=True)
    data = _parser.parse_cases(input_path)
    if mode == "rule":
        classified = data.apply(_rules.classify_case_rule, axis=1)
        df = _metrics.compute_durations(data)
        _export.write_case_details(df, output_dir / "federal_cases_0005_details.csv")
        _export.write_summary({"rows": len(df)}, output_dir / "federal_cases_0005_summary.json")
    else:
        # LLM mode not implemented in stub
        print("LLM mode not yet implemented; fallback to rule mode.")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = build_parser()
    ns = p.parse_args(argv)
    if ns.command == "analyze":
        return analyze(ns.input, ns.mode, ns.output_dir)
    if ns.command == "version":
        print(__import__("fct_analysis").__version__)
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
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
from . import llm as llm_module
from . import heuristics as heuristics_module
import json


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

    if ns.mode == "llm":
        # apply rule-based classification first
        types = []
        statuses = []
        for _, row in df.iterrows():
            res = classify_case_rule(row.get("raw") or {})
            types.append(res.get("type"))
            statuses.append(res.get("status"))
        df["type"] = types
        df["status"] = statuses

        # prepare checkpointing so long runs can resume
        progress_file = Path(ns.output_dir) / "llm_progress.json"
        progress = {}
        if progress_file.exists():
            try:
                progress = json.loads(progress_file.read_text(encoding="utf-8"))
            except Exception:
                progress = {}

        visa_offices = []
        judges = []

        for _, row in df.iterrows():
            raw = row.get("raw") or {}
            case_id = raw.get("case_number") or raw.get("case_id")

            # resume from progress if present
            if case_id and str(case_id) in progress:
                rec = progress[str(case_id)]
                visa_offices.append(rec.get("visa_office"))
                judges.append(rec.get("judge"))
                continue

            # try heuristics first
            text_blob = "\n".join([raw.get("title", "") or ""] + [(de.get("summary") or "") for de in (raw.get("docket_entries") or [])])
            vo = heuristics_module.extract_visa_office_heuristic(text_blob)
            jg = heuristics_module.extract_judge_heuristic(text_blob)

            # fallback to LLM only when heuristics fail
            if not vo or not jg:
                try:
                    ent = llm_module.extract_entities_with_ollama(text_blob)
                    vo = vo or ent.get("visa_office")
                    jg = jg or ent.get("judge")
                except ConnectionError:
                    # Ollama not available — keep heuristics results (may be None)
                    pass

            visa_offices.append(vo)
            judges.append(jg)

            # update progress
            if case_id:
                progress[str(case_id)] = {"visa_office": vo, "judge": jg}
                try:
                    progress_file.parent.mkdir(parents=True, exist_ok=True)
                    progress_file.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    # ignore checkpoint write errors
                    pass

        df["visa_office"] = visa_offices
        df["judge"] = judges

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
