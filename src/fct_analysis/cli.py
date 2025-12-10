"""Clean CLI implementation for fct_analysis.

Keeps `analyze(input_path, mode, output_dir)` signature used by tests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from . import parser as _parser
from . import rules as _rules
from . import metrics as _metrics
from . import export as _export
from . import heuristics as _heuristics
from . import llm as _llm
from . import utils as _utils


def analyze(
    input_path: str,
    mode: str = "rule",
    output_dir: Optional[str | Path] = None,
    resume: bool = False,
    sample_audit: int = 0,
    ollama_url: Optional[str] = None,
) -> int:
    output_dir = Path(output_dir or "output/")
    output_dir.mkdir(parents=True, exist_ok=True)

    df = _parser.parse_cases(input_path)

    types = []
    statuses = []

    # simple resume: collect processed case_numbers from checkpoint file
    checkpoint_path = output_dir / "0005_checkpoint.ndjson"
    processed = set()
    if resume and checkpoint_path.exists():
        try:
            with checkpoint_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        obj = __import__("json").loads(line)
                        if obj and isinstance(obj, dict) and obj.get("case_number"):
                            processed.add(obj.get("case_number"))
                    except Exception:
                        continue
        except Exception:
            processed = set()

    samples_written = 0
    audit_failures = Path("logs/0005_llm_audit_failures.ndjson")
    audit_failures.parent.mkdir(parents=True, exist_ok=True)

    for _, row in df.iterrows():
        case_num = row.get("case_number") or row.get("caseNumber")
        # rule-based classification
        res = _rules.classify_case_rule(row.get("raw") or row)

        # LLM mode: try heuristics first, then LLM if missing
        if mode == "llm":
            text = (row.get("raw") or "")
            visa = _heuristics.extract_visa_office_heuristic(text)
            judge = _heuristics.extract_judge_heuristic(text)
            if not visa or not judge:
                # check resume
                if resume and case_num and case_num in processed:
                    # skip LLM call for already processed
                    pass
                else:
                    try:
                        llm_out = _llm.extract_entities_with_ollama(text, ollama_url=ollama_url)
                        if llm_out:
                            visa = visa or llm_out.get("visa_office")
                            judge = judge or llm_out.get("judge")
                            # checkpoint the LLM output for this case
                            if case_num:
                                _utils.write_checkpoint(checkpoint_path, {"case_number": case_num, "visa_office": visa, "judge": judge})
                                processed.add(case_num)
                            # optionally write sample audit entries
                            if sample_audit and samples_written < sample_audit:
                                _utils.write_checkpoint(audit_failures.parent / "0005_llm_audit_samples.ndjson", {"case_number": case_num, "llm": llm_out})
                                samples_written += 1
                    except ConnectionError as exc:
                        # record failure to audit log
                        _utils.write_checkpoint(audit_failures, {"case_number": case_num, "error": str(exc)})

            # attach results to res
            if visa:
                res.setdefault("meta", {})
                res["meta"]["visa_office"] = visa
            if judge:
                res.setdefault("meta", {})
                res["meta"]["judge"] = judge

        types.append(res.get("type"))
        statuses.append(res.get("status"))

    df["type"] = types
    df["status"] = statuses

    df2 = _metrics.compute_durations(df)

    details_path = output_dir / "federal_cases_0005_details.csv"
    summary_path = output_dir / "federal_cases_0005_summary.json"
    _export.write_case_details(df2, str(details_path))
    summary = {"total_cases": int(len(df2)), "rows": int(len(df2))}
    _export.write_summary(summary, str(summary_path))

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(prog="fct_analysis")
    p.add_argument("--input", "-i", required=True)
    p.add_argument("--mode", choices=("rule", "llm"), default="rule")
    p.add_argument("--output-dir", "-o", default="output/")
    p.add_argument("--resume", action="store_true", help="Resume LLM processing using checkpoint file")
    p.add_argument("--sample-audit", type=int, default=0, help="Write sample LLM outputs to audit file (N samples)")
    p.add_argument("--ollama-url", type=str, default=None, help="Custom Ollama base URL (for testing)")
    ns = p.parse_args(argv)
    return analyze(ns.input, ns.mode, ns.output_dir, resume=ns.resume, sample_audit=ns.sample_audit, ollama_url=ns.ollama_url)


if __name__ == "__main__":
    raise SystemExit(main())