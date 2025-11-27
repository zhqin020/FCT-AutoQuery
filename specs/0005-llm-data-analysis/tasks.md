# Tasks: 0005-llm-data-analysis

**Input**: Design documents from `/specs/0005-llm-data-analysis/` (`spec.md`, `plan.md`, `checklist.md`) 

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure required by the feature

- [ ] T001 Create Python package `src/fct_analysis/__init__.py` and folder structure `src/fct_analysis/` (path: `src/fct_analysis/`)
- [ ] T002 Add CLI entrypoint module at `src/fct_analysis/cli.py` and make `src/fct_analysis` importable
- [ ] T003 [P] Create tests directory and fixture folder `tests/fixtures/` (path: `tests/fixtures/`)
- [ ] T004 [P] Add basic CI/test settings stub if missing (update `pytest.ini` or add `tox.ini`) (path: `pytest.ini`)
- [ ] T005 Update `requirements.txt` to include MVP deps: `pandas`, `numpy`, `tqdm` (path: `requirements.txt`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story work

- [ ] T006 Implement JSON parser utilities in `src/fct_analysis/parser.py` (path: `src/fct_analysis/parser.py`)
- [ ] T007 Implement date normalization helpers in `src/fct_analysis/parser.py` (path: `src/fct_analysis/parser.py`)
- [ ] T008 [P] Implement rule-based classifier skeleton in `src/fct_analysis/rules.py` (path: `src/fct_analysis/rules.py`)
- [ ] T009 Implement metrics computation module `src/fct_analysis/metrics.py` (path: `src/fct_analysis/metrics.py`)
- [ ] T010 Implement export helpers `src/fct_analysis/export.py` to write CSV/JSON/Excel (path: `src/fct_analysis/export.py`)
- [ ] T011 [P] Add logging and checkpoint helper `src/fct_analysis/utils.py` (path: `src/fct_analysis/utils.py`)
- [ ] T012 Setup basic unit test harness and add `tests/conftest.py` (path: `tests/conftest.py`)

**Checkpoint**: Foundational modules present and importable — tests may run but fail until implementations complete

---

## Phase 3: User Story 1 - Rule-mode pipeline & basic reports (Priority: P1) 🎯 MVP

**Goal**: Provide a fast, deterministic pipeline that parses raw JSON, applies keyword rules to classify case type/status, computes duration metrics, and emits CSV + summary JSON.

**Independent Test**: Run CLI with `--mode rule` on `tests/fixtures/0005_cases.json` and verify `output/federal_cases_0005_details.csv` and `output/federal_cases_0005_summary.json` are produced and contain expected columns.

### Tests (write first)

- [ ] T013 [P] [US1] Add fixture `tests/fixtures/0005_cases.json` with 8-12 representative cases (path: `tests/fixtures/0005_cases.json`)
- [ ] T014 [P] [US1] Add unit tests for parser: `tests/unit/test_parser_0005.py` (path: `tests/unit/test_parser_0005.py`)
- [ ] T015 [P] [US1] Add unit tests for rules: `tests/unit/test_rules_0005.py` (path: `tests/unit/test_rules_0005.py`)
- [ ] T016 [P] [US1] Add integration smoke test `tests/integration/test_pipeline_0005.py` that runs `cli.analyze` in rule mode (path: `tests/integration/test_pipeline_0005.py`)

### Implementation

- [ ] T017 [US1] Implement `parse_cases(input_path)` in `src/fct_analysis/parser.py` to load JSON and normalize `filing_date` (path: `src/fct_analysis/parser.py`)
- [ ] T018 [US1] Implement `classify_case_rule(case_obj)` in `src/fct_analysis/rules.py` using keyword rules for `Mandamus|compel|delay` and status priority (path: `src/fct_analysis/rules.py`)
- [ ] T019 [US1] Implement metrics: `compute_durations(df)` in `src/fct_analysis/metrics.py` producing `time_to_close`, `age_of_case`, `rule9_wait` fields (path: `src/fct_analysis/metrics.py`)
- [ ] T020 [US1] Implement exporter: `write_case_details(df, out_csv)` and `write_summary(summary_obj, out_json)` in `src/fct_analysis/export.py` (path: `src/fct_analysis/export.py`)
- [ ] T021 [US1] Implement CLI command `analyze --input <file> --mode rule --output-dir output/` in `src/fct_analysis/cli.py` wiring parser→rules→metrics→export (path: `src/fct_analysis/cli.py`)
- [ ] T022 [US1] Add logging and exit codes for CLI in `src/fct_analysis/cli.py` (path: `src/fct_analysis/cli.py`)
- [ ] T023 [US1] Ensure outputs are written to `output/federal_cases_0005_details.csv` and `output/federal_cases_0005_summary.json` (path: `output/`)

**Checkpoint**: MVP Rule-mode pipeline produces expected outputs and unit/integration tests pass

---

## Phase 4: User Story 2 - LLM Integration (Priority: P2)

**Goal**: Use local Ollama to extract `Visa Office` and `Judge` fields and to refine case-type/status when rules are ambiguous. Support checkpointing/resume.

**Independent Test**: Run CLI with `--mode llm` on small fixture and assert `visa_office` and `judge` fields are populated or logged as empty; verify checkpoint file is created when `--resume` used.

### Tests

- [ ] T024 [P] [US2] Add tests for LLM wrapper stubs `tests/unit/test_llm_0005.py` (path: `tests/unit/test_llm_0005.py`)
- [ ] T025 [P] [US2] Add integration test `tests/integration/test_llm_pipeline_0005.py` that runs in a dry-run mode (path: `tests/integration/test_llm_pipeline_0005.py`)

### Implementation

- [ ] T026 [US2] Implement `src/fct_analysis/llm.py` with a local Ollama HTTP client wrapper and retry/backoff (path: `src/fct_analysis/llm.py`)
- [ ] T027 [US2] Implement `extract_visa_office(text)` and `extract_judge(text)` functions that call the LLM wrapper (path: `src/fct_analysis/llm.py`)
- [ ] T028 [US2] Add checkpointing logic: `output/0005_checkpoint.ndjson` with processed `case_number` and `status` (path: `output/0005_checkpoint.ndjson`)
- [ ] T029 [US2] Add CLI flags `--mode llm --resume --sample-audit N` and wire to LLM flow in `src/fct_analysis/cli.py` (path: `src/fct_analysis/cli.py`)
- [ ] T030 [US2] Log LLM extraction failures to `logs/0005_llm_audit_failures.ndjson` (path: `logs/0005_llm_audit_failures.ndjson`)

**Checkpoint**: LLM-mode runs locally, supports resume, and records audit failures

---

## Phase 5: User Story 3 - Reports & Visualizations (Priority: P3)

**Goal**: Produce required charts (stacked bar, boxplot, donut, heatmap) as PNGs for inclusion in reports.

**Independent Test**: Run CLI `--mode rule` then `make-charts` command and confirm PNGs exist in `output/charts/`.

### Implementation

- [ ] T031 [US3] Implement plotting utilities `src/fct_analysis/plots.py` to generate: stacked bar chart, box plot, donut chart, heatmap (path: `src/fct_analysis/plots.py`)
- [ ] T032 [US3] Add CLI subcommand `report-charts --input output/federal_cases_0005_details.csv --out-dir output/charts/` (path: `src/fct_analysis/cli.py`)
- [ ] T033 [US3] Add integration test `tests/integration/test_charts_0005.py` that asserts PNG files are generated (path: `tests/integration/test_charts_0005.py`)

---

## Final Phase: Polish & Cross-Cutting Concerns

- [ ] T034 [P] Update `README.md` with quickstart steps for the feature and sample commands (path: `specs/0005-llm-data-analysis/quickstart.md` or project `README.md`)
- [ ] T035 [P] Add example output files to `output/` for demo (path: `output/`)
- [ ] T036 [P] Add `--sample-audit N` documentation and developer notes in `specs/0005-llm-data-analysis/checklist.md` (path: `specs/0005-llm-data-analysis/checklist.md`)
- [ ] T037 [P] Run full test suite and fix issues (path: repository root)

---

## Dependencies & Execution Order

- Setup tasks (T001-T005) must be completed first. Foundational tasks (T006-T012) block user stories.
- User Story 1 (T013-T023) is MVP and highest priority; User Story 2 and 3 may follow in parallel after foundational tasks complete.

## Parallel Execution Examples

- While T006 and T008 are implementation tasks in different files they can run in parallel (both marked [P]).
- Tests T014 and T015 can be written in parallel with T017 implementation (test-first approach).

## Implementation Strategy (MVP first)

- Deliver US1 fully (rule-mode pipeline + CSV/JSON outputs) as MVP.
- Add US2 (LLM) with checkpointing and audit next.
- Add US3 (charts) last and ensure charts are reproducible from `output/federal_cases_0005_details.csv`.

---

**Files created by these tasks (summary)**
- `src/fct_analysis/cli.py`
- `src/fct_analysis/parser.py`
- `src/fct_analysis/rules.py`
- `src/fct_analysis/metrics.py`
- `src/fct_analysis/export.py`
- `src/fct_analysis/llm.py` (Phase 2)
- `src/fct_analysis/plots.py` (Phase 3)
- `tests/fixtures/0005_cases.json`
- `tests/unit/test_parser_0005.py`, `tests/unit/test_rules_0005.py`
- `tests/integration/test_pipeline_0005.py`, `tests/integration/test_llm_pipeline_0005.py`, `tests/integration/test_charts_0005.py`
- `output/federal_cases_0005_details.csv`, `output/federal_cases_0005_summary.json`
