# Spec Quality Checklist — 0005-llm-data-analysis
**Created:** 2025-11-27

Purpose: concise acceptance criteria, tests, and validation steps for the `llm-data-analysis` feature.

- **Scope verified**: spec located at `specs/0005-llm-data-analysis/spec.md` matches PRD `docs/feat-005-data-mining.md`.

- **Inputs & parsing**:
  - JSON input accepted: array of case objects. Parser must support nested `docket_entries`.
  - Date fields normalized to `YYYY-MM-DD`. Records without `filing_date` are flagged and excluded from duration metrics.

- **Functional acceptance (P0)**:
  - Rule-mode classification: for a provided test set (see `tests/fixtures/0005_cases.json`), keyword-based rules correctly label `Mandamus` for title/docket summary containing `Mandamus|compel|delay` with >= 95% precision.
  - Status extraction priority: `Discontinued` > `Granted/Allowed` > `Dismissed` > `Ongoing`. Unit tests must cover each case.
  - Duration metrics: `Time to Close`, `Age of Case`, `Rule 9 wait` computed and aggregated (mean, median, min, max).

- **LLM integration (P1)**:
  - Visa Office extraction: LLM must extract a standardized visa-office string (e.g., `Beijing`, `New Delhi`) from docket text.
  - Judge extraction: LLM must return judge name or empty if none.
  - Validation target: on a sample audit set (n=100), LLM extractions for Visa Office and Judge must reach >= 90% human-agreed accuracy. Record failures to `logs/0005_llm_audit_failures.ndjson`.
  - LLM calls: must be rate-limited and checkpointed (see Resumability below).

- **Performance & non-functional**:
  - Rule mode: process 5,000 case records in < 10s on typical developer laptop (document environment used for measurement).
  - LLM mode: support resumability (checkpoint file with processed IDs), and configurable batch size.
  - Logging: summary audit written to `output/llm_analysis_0005_summary.json` and per-run log to `logs/`.

- **Resumability / Checkpointing**:
  - Implement a checkpoint file path (default `output/0005_checkpoint.ndjson`) containing processed `case_number` and `status`.
  - On start, CLI accepts `--resume` to continue from the checkpoint.

- **Outputs & artifacts**:
  - Case details CSV: `output/federal_cases_0005_details.csv` with required columns: `case_number,title,filing_date,court_office,visa_office,type,status,outcome_date,duration_days,judge`.
  - Summary report JSON and optional Excel: `output/federal_cases_0005_summary.json` and `output/federal_cases_0005_summary.xlsx`.

- **Tests (automated)**:
  - Unit tests for parser, rule-classifier, status-extractor, metrics calculator in `tests/test_0005_*.py`.
  - Integration test that runs full pipeline on `tests/fixtures/0005_cases.json` and asserts outputs exist and metrics are computed.
  - Add CI job entry to run these tests on PR (if project CI exists).

- **Manual review**:
  - Provide a `--sample-audit N` option that writes `N` LLM-parsed cases to `logs/` for quick human review.

- **Security & privacy**:
  - Ensure no external LLM calls leak data outside allowed hosts; prefer local Ollama endpoint.
  - Strip PII from logs where not needed.

- **Developer notes**:
  - Suggested libraries: `pandas`, `numpy`, `requests` for Ollama, `tqdm` for progress, `pytest` for tests.
  - CLI entrypoint: `python -m fct_analysis.cli analyze --input data/cases.json --mode rule|llm` (implementation TBD in `src/`).

---

Acceptance: when all P0 criteria pass automated tests, LLM extraction meets audit threshold, and outputs are produced in `output/` per above.
