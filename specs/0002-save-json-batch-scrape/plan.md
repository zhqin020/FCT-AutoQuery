tests/
# Implementation Plan: Save JSON Files & Batch Scrape Optimization

**Branch**: `0002-save-json-batch-scrape` | **Date**: 2025-11-25
**Spec**: `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/spec.md`
**Input**: Feature specification: `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/spec.md`

## Summary

Deliver a durable per-case JSON export and improve batch-scrape throughput by
reusing the browser session between cases. Implementation will add an atomic
per-case writer, configuration for output directory and retry/backoff, and
refactor the batch runner to keep the WebDriver instance open across cases.

## Technical Context

**Language/Version**: Python 3.10+ (repository already targets Python; `python3` used in scripts)
**Primary Dependencies**: Selenium (webdriver-manager), tomllib / toml for config, pytest for tests
**Storage**: File-based JSON artifacts under configured `output` directory (default: `output/json/`)
**Testing**: `pytest` unit tests (existing project uses pytest), small integration tests for batch runner
**Target Platform**: Linux (developer and CI); local desktop for interactive runs
**Project Type**: Single Python project (services/cli based)
**Performance Goals**: Batch runs should retain a single browser process across at least 95% of cases in a 100-case run; median per-case time target < 20s for a 100-case sample
**Constraints**: Must obey project Constitution (conda `fct` env, test-first, pre-commit checks); avoid changing public CLI contract

## Constitution Check

GATE: This plan ensures the following before Phase 0 research begins:

- **Testing**: Unit tests will be added for the new exporter logic (atomic writes, unique filenames, retries). Integration-style test will confirm session reuse. (Plan: add `tests/test_export_service.py` and `tests/test_batch_runner.py`.)
- **Git workflow**: Work done on `0002-save-json-batch-scrape` branch (current). Feature will include spec and tests before merging.
- **Coding standards**: New code will use type hints consistent with repo. Linting unchanged; use existing pytest conventions.
- **Issue management**: Link changes to `docs/chg-002-critical-issues.md` in PR description.
- **Environment**: All commands run in `conda` env `fct` (pre-commit hooks and scripts enforce this).

If any of the above cannot be satisfied, the plan documents the justification and mitigation.

## Project Structure (selected)

This feature lives within the existing single-project layout:

 - `src/services/` — place exporter and any helper functions (`export_service.py`) here
 - `src/cli/` — batch runner and CLI orchestrator (`main.py`) updated to reuse browser
 - `src/lib/config.py` — add accessors for per-case subdir and retry/backoff settings
 - `tests/` — unit tests for exporter and batch session reuse

## Phase 0: Outline & Research (deliverable: `research.md`)

Goals:
1. Confirm safe filename sanitization and atomic write strategy (tempfile + os.replace) for JSON files.
2. Choose retry/backoff defaults and failure semantics (how many retries, exponential or linear backoff).
3. Validate WebDriver lifecycle patterns to allow safe reuse between cases and a graceful shutdown.

Phase 0 Tasks (implementable):
- Task 0.1: Document current behavior and gaps in `research.md` at `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/research.md`.
- Task 0.2: Research atomic-write patterns in Python (tempfile.mkstemp + os.replace) and list alternatives.
 - Task 0.3: Decide retry/backoff defaults (Chosen default: 2 retries, backoff base 1s exponential) and document rationale (align with `spec.md`).
- Task 0.4: Identify WebDriver reuse approach (keep single driver instance in `BatchRunner`, handle per-case cleanup) and document failure modes.

Outputs:
- `research.md` (resolves any NEEDS CLARIFICATION items)

## Phase 1: Design & Contracts (deliverables: `data-model.md`, `contracts/`, `quickstart.md`)

Prerequisite: `research.md` complete.

Phase 1 Tasks:
1. Data model: create `data-model.md` describing `CaseRecord` JSON schema (fields, types, optional vs required) at `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/data-model.md`.
2. API/CLI contracts: document CLI flags and behavior for `batch` and `interactive` modes; produce sample OpenAPI-like contract or plain text contract under `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/contracts/`.
3. Quickstart: write `quickstart.md` showing how to run batch and interactive modes, how to use `./scripts/run-in-fct.sh`, and where per-case JSON files appear.
4. Update `src/lib/config.py` and `config.example.toml` to include `app.per_case_subdir`, `app.export_write_retries`, `app.export_write_backoff_seconds`.

Outputs:
- `data-model.md`, `contracts/*`, `quickstart.md`

## Phase 2: Implementation (code changes & tests)

Tasks (implementation order):
1. Implement `src/services/export_service.py::export_case_to_json(case: CaseRecord)` with atomic write, unique filename suffixing, and configurable retries/backoff.
2. Update `src/cli/main.py` batch runner to reuse a single WebDriver instance for the run; add `shutdown()` for graceful teardown.
3. Add unit tests: `tests/test_export_service.py` (atomic write, suffixing, retry behavior) and `tests/test_batch_runner.py` (session reuse smoke tests; may be marked integration).
4. Run local tests under `fct` env and iterate until passing.

## Phase 3: Release & Documentation

Tasks:
1. Update `README.md`/`USAGE_GUIDE.md` with quickstart and wrapper usage.
2. Prepare PR linking `specs/0002-save-json-batch-scrape/spec.md` and implementation changes; include changelog reference.
3. Add CI job or update existing pipeline to run `scripts/check_constitution.sh` and pytest.

## Risks & Mitigations

- Risk: Browser process leaks or state drift across many cases causing flakiness.  
  Mitigation: Add per-case state cleanup (close dialogs, clear inputs) and soft restart mechanism after N failures.
- Risk: File write collisions on concurrent runs.  
  Mitigation: Add unique suffixing and ensure atomic rename; recommend `max concurrent browser instances` default = 1.
- Risk: Pre-commit hook blocks commits because unrelated src changes lack tests.  
  Mitigation: Document how to temporarily skip hook (`--no-verify`) and prefer adding tests; keep pre-commit informative.

## Acceptance Criteria (implementation verification)

- Unit tests for `export_case_to_json` pass and cover edge cases.  
- Batch runner retains a single browser process for a 20-case local smoke test.  
- Per-case JSON files appear under `output/json/<YYYY>/` with expected filename pattern and content matching `data-model.md`.

## Artifacts & Paths

- Feature spec: `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/spec.md`  
- Implementation plan: `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/plan.md`  
- Research: `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/research.md`  
- Data model: `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/data-model.md`  
- Quickstart: `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/quickstart.md`  
- Contracts dir: `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/contracts/`

## Next Actions (immediate)

1. Create and save `research.md` (Phase 0).  
2. Implement exporter and tests (Phase 2, tasks 1-3).  
3. Iterate on tests and documentation; open PR once tests pass.
