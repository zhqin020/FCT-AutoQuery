#!/usr/bin/env python3
"""Collect LLM responses for cases in an existing batch output file.

Reads `output/final_log_all.json`, calls `safe_llm_classify` for each case
(using `raw_case_info` to build a concise summary), and writes results to
`output/final_llm_samples.json` for inspection.
"""
import json
import time
import os
from pathlib import Path

OUTPUT_IN = Path("output/final_log_all.json")
OUTPUT_OUT = Path("output/final_llm_samples.json")

# Ensure we can import the project's module (add workspace root to path)
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.fct_analysis.llm import safe_llm_classify
from loguru import logger


def build_summary(raw_case_info: dict) -> str:
    parts = []
    title = raw_case_info.get("style_of_cause") or raw_case_info.get("title") or raw_case_info.get("case_number")
    if title:
        parts.append(f"Title: {title}")
    nature = raw_case_info.get("nature_of_proceeding") or raw_case_info.get("nature")
    if nature:
        parts.append(f"Nature: {nature}")
    # include docket entry summaries
    dockets = raw_case_info.get("docket_entries") or []
    if dockets:
        parts.append("Docket entries:")
        for d in dockets:
            date = d.get("date_filed") or d.get("date") or d.get("dateFiled")
            text = d.get("recorded_entry_summary") or d.get("record_summary") or d.get("summary")
            if date or text:
                parts.append(f"- {date or ''}: {text or ''}")
    return "\n".join(parts)


def main():
    if not OUTPUT_IN.exists():
        logger.error(f"Input file not found: {OUTPUT_IN}")
        return

    data = json.loads(OUTPUT_IN.read_text())
    results = []

    # iterate over groups (e.g., Ongoing)
    for group_name, group in data.items():
        cases = group.get("cases") or []
        for case in cases:
            case_number = case.get("case_number")
            raw_case_info = case.get("raw_case_info") or {}
            summary_text = build_summary(raw_case_info)

            logger.info(f"Calling LLM for {case_number}...")
            try:
                parsed = safe_llm_classify(summary_text, case_number=case_number)
            except Exception as e:
                logger.exception(f"LLM call failed for {case_number}: {e}")
                parsed = {"error": str(e)}

            results.append({
                "case_number": case_number,
                "summary_text": summary_text,
                "llm_result": parsed,
            })

            # Be polite to local Ollama
            time.sleep(1.0)

    OUTPUT_OUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    logger.info(f"Saved LLM samples to {OUTPUT_OUT}")


if __name__ == "__main__":
    main()
