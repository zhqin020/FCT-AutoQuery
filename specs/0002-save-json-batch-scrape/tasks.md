---

description: "Tasks for feature Save JSON Files & Batch Scrape Optimization"

---

# Tasks: Save JSON Files & Batch Scrape Optimization

**Feature**: `0002-save-json-batch-scrape`
**Design docs**: `/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/`

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 [P] Create configuration entries `app.per_case_subdir`, `app.export_write_retries`, `app.export_write_backoff_seconds`, `app.max_driver_restarts` in `src/lib/config.py` and document defaults in `config.example.toml`
- [ ] T002 [P] Add default output path creation helper in `src/services/export_service.py` to ensure `output/json/<YYYY>/` exists when exporter runs (`Path(...).mkdir(parents=True, exist_ok=True)`) and add `output/` to `.gitignore` if not present (`.gitignore`)
- [ ] T003 [P] Verify or add Conda wrapper `scripts/run-in-fct.sh` and document usage in `specs/0002-save-json-batch-scrape/quickstart.md` (create file if missing)

---

## Phase 2: Foundational (Blocking Prerequisites)

- [ ] T004 Implement core exporter in `src/services/export_service.py` with atomic write (mkstemp in same dir, write+fsync, os.replace), unique filename suffixing on conflict, and configurable retries/backoff (read from `src/lib/config.py`)
- [ ] T005 [P] Add unit tests for exporter behavior in `tests/test_export_service.py` covering: sanitizer, atomic write, unique suffix, retry/backoff on transient write failure
- [ ] T006 Update `config.example.toml` with the new keys and an example section `# Exporter` (file: `config.example.toml`)
- [ ] T007 [P] Add `specs/0002-save-json-batch-scrape/data-model.md` describing `CaseRecord` JSON schema (fields, types, required/optional) so tests and validation can reference it

---

## Phase 3: User Story 1 - Save per-case JSON on scrape (Priority: P1) 🎯 MVP

**Goal**: Ensure every successfully scraped case produces an atomic per-case JSON file under `output/json/<YYYY>/` with filename pattern `<case-number>-<YYYYMMDD>.json` and suffixing to avoid overwrite.

**Independent Test**: Single-case scrape writes a JSON to `output/json/<YYYY>/` and file validates against `specs/.../data-model.md`.

- [ ] T008 [US1] Create `specs/0002-save-json-batch-scrape/data-model.md` (if not already created in T007) containing canonical CaseRecord schema
- [ ] T009 [US1] Implement `export_case_to_json(case: CaseRecord, output_root: Optional[str]=None) -> str` in `src/services/export_service.py` (atomic write + unique suffix + timestamp field) and ensure it returns final filepath
- [ ] T010 [US1] [P] Wire exporter into CLI: verify `src/cli/main.py` calls `ExportService.export_case_to_json(case)` after scrape and logs the returned path
- [ ] T011 [US1] Add integration/smoke test `tests/integration/test_single_case_export.py` that simulates a successful scrape (or uses a small fixture) and asserts JSON file exists and matches schema
- [ ] T012 [US1] [P] Add schema validation test `tests/test_schema_validation.py` that loads the saved JSON and validates required fields per `data-model.md`

---

## Phase 4: User Story 2 - Batch scraping without reinitializing browser (Priority: P2)

**Goal**: Ensure batch runs reuse a single browser/session, perform per-case cleanup (close dialogs, clear inputs), and recover from transient failures via a restart policy.

**Independent Test**: A 20-case smoke run uses the same browser process (same PID) across cases; per-case JSON files are written.

- [ ] T013 [US2] Update `src/services/case_scraper_service.py` to (a) expose a stable driver instance used across the batch, (b) add a soft-restart policy honoring `app.max_driver_restarts` and logging restarts to `logs/scraper.log`
- [ ] T014 [US2] [P] Add helper method `CaseScraperService._cleanup_after_case()` to close modals and reset page state between cases (`src/services/case_scraper_service.py`)
- [ ] T015 [US2] Implement recovery tests `tests/integration/test_batch_driver_reuse.py` that run a short batch (20) against a deterministic fixture and assert driver PID unchanged across most cases and JSON outputs exist
- [ ] T016 [US2] [P] Add unit tests for restart/recovery logic in `tests/test_case_scraper_recovery.py` that simulate driver exceptions and assert restart attempts up to configured limit

---

## Phase 5: User Story 3 - Manual/interactive scrape parity (Priority: P3)

**Goal**: Ensure interactive mode produces the same artifacts and logs as automated runs.

**Independent Test**: Manual lookup produces per-case JSON and matching log entry.

- [ ] T017 [US3] Ensure `src/cli/main.py` interactive path (`single` command) writes per-case JSON using the same exporter code path (`src/cli/main.py`)
- [ ] T018 [US3] Add a manual QA checklist to `specs/0002-save-json-batch-scrape/quickstart.md` describing steps to perform a manual check and verify outputs

---

## Final Phase: Polish & Cross-Cutting Concerns

- [ ] T019 Update `README.md` and `USAGE_GUIDE.md` with quickstart instructions that include `scripts/run-in-fct.sh` usage and location of per-case JSON files (`README.md`, `USAGE_GUIDE.md`)
- [ ] T020 [P] Add CI workflow `.github/workflows/ci.yml` to run `scripts/check_constitution.sh` and `pytest -q` on push/PR
- [ ] T021 [P] Add `.gitignore` entries for `output/` (if not already present) and document how to back up per-case JSONs
- [ ] T022 [P] Add a small integration test job example and instructions in `specs/0002-save-json-batch-scrape/quickstart.md` for running local smoke tests with `conda run -n fct pytest tests/integration/ -q`

---

# Additional required tasks (constitution compliance & run-level logging)

- [ ] T023 [P] Add run-level logging task: implement `RunLogger` that writes NDJSON per-run entries to `logs/run_<run_id>.ndjson` (records `run_id`, `start_time`, `end_time`, `browser_session_id`, case outcome entries). Add tests `tests/test_run_logger.py`.
- [ ] T024 [US2] [P] Ensure every modified module has a corresponding unit test file (TDD): `tests/test_case_scraper_service_unit.py`, `tests/test_cli_wiring.py`, `tests/test_config_accessors.py`. These tests must be added before code changes are merged (constitution compliance).

---

## Dependencies

- Setup (Phase 1) tasks should be completed before Foundational (Phase 2). Foundational tasks block user-story implementation.
- User Story phases (US1 → US2 → US3) follow priority order but are independently testable once Foundational tasks are complete.

## Parallel Execution Examples

- While T004 (exporter core) is in progress, T005 (exporter unit tests) and T006 (config.example) can be implemented in parallel.
- T009 (exporter implementation) and T010 (CLI wiring) can be worked on in parallel by separate engineers because they modify different files.
- T013 (driver reuse) and T014 (per-case cleanup) can be parallel tasks as they operate on different methods in `src/services/case_scraper_service.py`.

## Implementation Strategy

- MVP: Complete Foundational tasks T004-T007 and User Story 1 tasks (T008-T012). Validate via unit tests and a single-case smoke test. Release MVP.
- Incremental: After MVP, implement User Story 2 (T013-T016) and add integration tests. Finally, polish documentation and CI (T019-T022).

## File to which this tasks list was written

`/home/watson/work/FCT-AutoQuery/specs/0002-save-json-batch-scrape/tasks.md`
