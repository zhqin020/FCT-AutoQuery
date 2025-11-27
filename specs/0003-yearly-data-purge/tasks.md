---
description: "Task list for Yearly Data Purge feature"
---

# Tasks: Yearly Data Purge

**Input**: Design documents from `/specs/0003-yearly-data-purge/`
**Prerequisites**: `plan.md`, `spec.md`

## Phase 1: Setup (Project wiring)

- [ ] T001 Create `purge` CLI subcommand wiring in `src/cli/main.py`
- [ ] T002 Create CLI handler scaffold `src/cli/purge.py` that exposes `purge_year(year, args)`
- [ ] T003 [P] Add basic CLI unit tests `tests/services/test_purge_cli.py` for flag parsing and confirmation behavior

---

## Phase 2: Foundational (Blocking prerequisites)

- [ ] T004 Implement DB purge service scaffold in `src/services/purge_service.py` with `db_purge_year(year, conn, **kwargs)`
- [ ] T005 [P] Implement filesystem helpers scaffold in `src/services/files_purge.py` with `backup_output_year`, `purge_output_year`, `remove_modal_html_for_year`
- [ ] T006 [P] Add/verify DB test fixtures and helper in `tests/conftest.py` or `tests/fixtures/db.py` to provide a disposable SQLite/Postgres fixture for tests
- [ ] T007 [P] Add logging/audit helper `src/services/purge_audit.py` (simple JSON writer) to centralize audit creation

---

## Phase 3: User Story 1 - Purge a year (Priority: P1) 🎯 MVP

**Goal**: Provide a safe, auditable CLI `purge <YEAR>` that supports `--dry-run`, `--yes`, `--backup/--no-backup`, and removes DB rows + filesystem artifacts for the year.

**Independent Test**: `purge <YEAR> --dry-run` lists all candidate DB rows and filesystem paths and writes `output/purge_audit_<ts>_<year>.json`; `purge <YEAR> --yes` performs backup (if enabled), deletes DB rows and filesystem artifacts, and writes final audit.

### Implementation

- [ ] T008 [US1] Implement dry-run enumeration of DB candidates in `src/services/purge_service.py::enumerate_cases_for_year(year, conn)` and return candidate IDs and sample rows
- [ ] T009 [US1] Implement filesystem enumeration for `output/<YEAR>` and `logs/` modal HTML matches in `src/services/files_purge.py::enumerate_files_for_year(year, output_dir, logs_dir)`
- [ ] T010 [US1] Implement `PurgeAudit` writer in `src/services/purge_audit.py` and ensure dry-run produces `output/purge_audit_<ts>_<year>.json`
- [ ] T011 [US1] Add unit test `tests/services/test_purge_dry_run.py` asserting enumeration and audit contents (temporary FS + test DB)
- [ ] T012 [US1] Implement backup helper `src/services/files_purge.py::backup_output_year(output_dir, year, dest_dir=None)` (tar.gz of `output/<YEAR>`) and tests `tests/services/test_purge_backup.py`
- [ ] T013 [US1] Implement transactional DB deletion `src/services/purge_service.py::db_purge_year(year, conn)` with explicit deletes for related tables and tests `tests/services/test_purge_db.py` (SQLite)
- [ ] T014 [US1] Implement filesystem purge `src/services/files_purge.py::purge_output_year(output_dir, year)` and `remove_modal_html_for_year(logs_dir, year)` with atomic rename+delete semantics and tests `tests/services/test_purge_filesystem_delete.py`
- [ ] T015 [US1] Integrate flow in `src/cli/purge.py::purge_year`: validate flags -> (dry-run or confirm) -> backup (if enabled) -> db_purge_year (unless `--files-only`) -> purge_output_year/remove_modal_html (unless `--db-only`) -> write final audit
- [ ] T016 [US1] Add CLI integration test `tests/services/test_purge_integration.py` that runs the end-to-end flow in a temp environment (dry-run and actual with `--yes`)

---

## Phase 4: User Story 2 - Non-interactive scheduled purge (Priority: P2)

**Goal**: Allow cron/CI to run `purge <YEAR> --yes --backup` non-interactively and receive a deterministic audit file and exit code.

**Independent Test**: Run CLI with `--yes --backup` in a non-interactive process and assert exit code 0 and presence of audit + backup file.

### Implementation

- [ ] T017 [US2] Ensure `src/cli/purge.py` honors `--yes` to skip interactive confirmation and returns suitable exit codes
- [ ] T018 [US2] Add tests `tests/services/test_purge_noninteractive.py` simulating non-interactive invocation and verifying backup and audit
- [ ] T019 [US2] Add optional `--backup <path>` handling in `src/services/files_purge.py` and make backup location configurable via `config.example.toml`

---

## Phase 5: User Story 3 - Scoped purge (Priority: P3)

**Goal**: Support `--files-only` and `--db-only` modes and `--force-files` for proceeding with files deletion after DB failure (explicit operator override).

**Independent Test**: Run `purge <YEAR> --files-only --yes` and assert DB untouched and files removed; run `purge <YEAR> --db-only --yes` and assert files untouched.

### Implementation

- [ ] T020 [US3] Implement `--files-only` and `--db-only` flags handling in `src/cli/purge.py`
- [ ] T021 [US3] Implement `--force-files` behavior in `src/cli/purge.py` and `src/services/purge_service.py` (only run file purge after DB failure if `--force-files` provided)
- [ ] T022 [US3] Add unit tests `tests/services/test_purge_scoped_flags.py` covering `--files-only`, `--db-only`, and `--force-files` semantics

---

## Final Phase: Polish & Cross-Cutting Concerns

- [ ] T023 Update documentation `docs/chg-003-yearly-data-purge.md` with usage examples, recovery steps, and backup/restore instructions
- [ ] T024 [P] Add changelog entry in `CHANGELOG.md` describing the feature and default behaviors
- [ ] T025 [P] Add CI job/scenario in repository CI config to run `tests/services/test_purge_*` suite (or include in existing test stage)
- [ ] T026 [P] Performance: Add DB delete chunking or SQL-optimized path for Postgres in `src/services/purge_service.py` guarded by env/config and tests/integration notes
- [ ] T027 [P] Security: Document required operator credentials and add permission checks/documentation in `USAGE_GUIDE.md`

---

## Dependencies

- Phase execution order: Setup (Phase 1) -> Foundational (Phase 2) -> User Stories (Phase 3+) -> Final Phase
- Story completion order (recommended): **US1 (P1)** -> US2 (P2) -> US3 (P3)

## Parallel Execution Examples

- Implement `T003`, `T005`, `T006`, and `T024` in parallel (different files, no dependency)
- While `T012` (backup) runs, another engineer can implement `T013` (DB purge) independently and test locally

## Implementation Strategy

- MVP: Deliver US1 only (Phase 1, Phase 2, Phase 3) with backups defaulting per spec decision; validate with unit/integration tests before expanding to US2/US3
- Incremental: After US1 validation, enable US2 by ensuring `--yes` semantics and CI scheduling; then deliver US3 flags and force behavior

## Output

- Generated tasks file: `/specs/0003-yearly-data-purge/tasks.md`
- Total tasks: 27 (T001–T027)

All tasks follow the checklist format with Task IDs, optional `[P]` marker for parallelizable tasks, and `[USn]` labels for user story-specific tasks.
