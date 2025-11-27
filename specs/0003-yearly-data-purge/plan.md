# Implementation Plan: Yearly Data Purge

## Overview

This plan breaks the `0003-yearly-data-purge` feature into small, testable tasks and delivers a minimal safe implementation (dry-run, confirm, audit) followed by backups and DB/file deletion. The goal is to provide iterative checkpoints so the feature can be reviewed and deployed safely.

## Milestones & Tasks

1. Draft CLI skeleton and argument parsing (P1, 1d)
   - Add `purge` subcommand to `src/cli/main.py` with flags: `--dry-run`, `--yes`, `--backup`, `--no-backup`, `--files-only`, `--db-only`, `--force-files`.
   - Add stub handler `purge_year(year, args)` in `src/cli/purge.py` (new file) that returns structured summary.
   - Unit tests: `tests/services/test_purge_cli.py` for argument parsing and basic behavior.

2. Implement safe dry-run and audit generation (P1, 1d)
   - Implement dry-run mode that enumerates DB rows (via `ExportService` / DB helper) and filesystem artifacts (`output/<YEAR>`, `logs/` modal HTML matching year) but does not delete.
   - Produce `PurgeAudit` JSON summarizing counts and paths; write to `output/purge_audit_<ts>_<year>.json` even for dry-run.
   - Unit tests with temp filesystem and a test DB fixture.

3. Implement backup-by-default support (P1, 1d)
   - Add helper `backup_output_year(year, target_path)` to archive `output/<YEAR>` (tar.gz) and optionally export DB rows to `output/backup_<ts>_<year>.json`.
   - Honor `--no-backup` to skip; honor explicit `--backup <path>`.
   - Tests: verify backup created and archive contents.

4. Implement DB purge with cascade (P1, 1d)
   - Implement `db_purge_year(year, conn, transactional=True)` that deletes `cases` for year and relies on FK cascade or explicit deletes for related tables; run inside transaction; rollback on error and report partial-state in audit.
   - Tests: simulate DB failures and assert rollback/audit.

5. Implement filesystem purge (P1, 1d)
   - Remove `output/<YEAR>` atomically (move to tmp then delete) and remove modal HTML files by filename match for year. Leave run NDJSON files untouched per decision.
   - Record any permission/IO errors in audit and continue other deletions.

6. Integrate all steps into `purge_year` handler (P1, 0.5d)
   - Flow: validate args -> dry-run enumeration (if requested) -> backup (if enabled) -> DB purge -> file purge -> write final audit -> exit code.
   - Ensure non-interactive `--yes` bypasses prompt; otherwise ask for explicit `YES` typed confirmation in interactive mode.

7. Tests & CI (P1, 1d)
   - Add unit tests: `test_purge_filesystem.py`, `test_purge_db.py`, mocking DB and filesystem.
   - Add an integration test (staging) checklist in `docs/` and a small script to run a staging scenario locally.

8. Documentation & Release (P2, 0.5d)
   - Update `USAGE_GUIDE.md` and `docs/chg-003-yearly-data-purge.md` with usage examples and safety notes.
   - Update `CHANGELOG.md` with feature summary.

## Acceptance Criteria (for merge)

- CLI `purge YEAR --dry-run` lists exact items to be removed and writes a dry-run audit file.
- Non-interactive `purge YEAR --yes` with default backups completes and writes final audit file; exit code 0 on success.
- DB deletions are transactional; partial failures rollback and a partial-audit is produced with non-zero exit code.
- Filesystem removals record any skipped files and continue; modal HTML files for the year are removed.
- Unit tests cover the main flows and run in CI.

## Risks & Mitigations

- Risk: accidental data loss. Mitigation: backups by default, `--dry-run`, confirmation prompt.
- Risk: long-running deletes/timeouts. Mitigation: implement progress logging and chunked deletes for DB; enforce maintenance window.
- Risk: large backups. Mitigation: allow `--no-backup` and configurable backup location; document storage expectations.

## Deliverables

- `src/cli/purge.py` (new), CLI wiring in `src/cli/main.py`
- DB helper `src/services/purge_service.py` with `db_purge_year`
- Filesystem helper `src/services/files_purge.py` with `backup_output_year` and `purge_output_year`
- Tests under `tests/services/` for CLI, DB, and filesystem
- `specs/0003-yearly-data-purge/plan.md` (this file)

## Timeline Estimate

Total: ~6–7 workdays for a single developer to deliver feature with tests and docs.
