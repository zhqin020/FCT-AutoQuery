# Feature Specification: [FEATURE NAME]
```markdown
# Feature Specification: Yearly Data Purge

**Feature Branch**: `0003-yearly-data-purge`  
**Created**: 2025-11-26  
**Status**: Draft  
**Input**: User description: "003 年度数据清除功能: 删除数据库记录、output 年度目录、logs run_logger 和 HTML 文件（按年度）"

## Summary

Provide a safe, auditable, and testable `purge` command that removes all data and artifacts for a specified year. Deletion targets include database records for that year, the `output/<YEAR>` directory (per-case JSON and bundle exports), and year-specific log artifacts (run-level NDJSON files and modal HTML files). The feature must support a dry-run mode, require explicit confirmation for destructive operations, produce an audit of the purge action, and allow automated (CI/cron) invocation with a non-interactive confirmation flag.

## Actors, Actions, Data and Constraints

- Actors: System Operator / Admin (CLI user), Automated Job (cron/CI), Support/Forensics team (consuming audit output)
- Actions: Request purge for a given year; preview purge (dry-run); confirm and execute purge; optionally create backup before deletion; emit audit report describing removed items and counts
- Data involved: Database case records (per-case metadata persisted in DB), per-case JSON files in `output/<YEAR>`, run-level NDJSON logs (run_logger output), modal HTML files under `logs/` matching the year, and any derived audit/backup files
- Constraints: Operation is destructive and must be auditable and reversible only via retained backups if enabled. Must be able to run non-interactively (for scheduled jobs) and must complete within reasonable time for a year of data (see Success Criteria)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Purge a year (Priority: P1)

An operator needs to permanently remove all data for year 2023.

**Why this priority**: Data removal is required for compliance/data lifecycle management and to free storage.

**Independent Test**: Run `python -m src.cli.main purge 2023 --dry-run` to verify what would be deleted; then run `python -m src.cli.main purge 2023 --yes` on a test environment and assert that DB rows, `output/2023`, and log artifacts are removed and an audit file exists.

**Acceptance Scenarios**:

1. **Given** a populated DB and `output/2023` and `logs/` entries, **When** the operator runs purge for 2023 with `--dry-run`, **Then** no files or DB rows are deleted and the tool prints a complete list/count of items that would be removed.
2. **Given** the same initial state, **When** the operator runs purge for 2023 with `--yes`, **Then** all DB records for 2023 are deleted, the `output/2023` directory is removed, all run-level NDJSON and modal HTML files for 2023 are removed, and an audit JSON summarizing the purge is written to `output/purge_audit_<timestamp>_2023.json`.

---

### User Story 2 - Non-interactive scheduled purge (Priority: P2)

An automated job should be able to run the purge non-interactively at off-peak hours.

**Why this priority**: Enables regular maintenance without human intervention.

**Independent Test**: Run the CLI with `--yes` and a `--backup` option from a headless environment and assert no interactive prompts are emitted and expected artifacts are removed/archived.

**Acceptance Scenarios**:

1. **Given** the CLI is invoked by a cron job with `--yes` and `--backup`, **When** the job finishes, **Then** the purge completed successfully, backup created at the specified location, and an audit file exists; exit code is 0.

---

### User Story 3 - Limited-scope purge / dry-run (Priority: P3)

Operators sometimes want to purge only files (not DB) or only DB rows; the CLI should support scoped purges.

**Why this priority**: Provides flexibility and reduces risk for partial workflows.

**Independent Test**: Run `purge YEAR --files-only --dry-run` and verify DB is untouched while files listed for deletion match expectations.

**Acceptance Scenarios**:

1. **Given** `output/2022` present and DB rows for 2022, **When** `purge 2022 --files-only --yes` is run, **Then** only filesystem artifacts for 2022 are removed; DB rows remain.

### Edge Cases

- If the `output/<YEAR>` directory does not exist, the tool should still remove DB rows and logs that match the year and report missing directories in the audit, but not fail the whole operation.
- If the DB delete operation partially fails (e.g., network interruption), the tool must stop, report partial failure in the audit, and not attempt to remove filesystem artifacts unless DB removal completed or `--force-files` is explicitly specified.
- If file permissions prevent removal of certain files, the tool must record these failures in the audit and continue with other deletions.

## Requirements *(mandatory)*

### Functional Requirements (testable)

- **FR-001**: CLI MUST provide a `purge <YEAR>` command that accepts flags: `--dry-run`, `--yes` (non-interactive confirm), `--backup <path>`, `--files-only`, `--db-only`, and `--force-files`.
- **FR-002**: The `--dry-run` flag MUST perform all checks and list every DB row and filesystem path that would be deleted, without performing any destructive action.
- **FR-003**: When executed without `--dry-run`, the command MUST require explicit confirmation unless `--yes` is provided.
- **FR-004**: The command MUST produce an audit JSON file summarizing: timestamp, year, lists/counts of DB records removed, filesystem paths removed, files skipped, errors encountered, and whether a backup was created. The audit file path MUST be returned on successful completion.
- **FR-005**: If `--backup` is provided, the command MUST create a backup archive (or export) of the `output/<YEAR>` directory and optionally DB export (see Clarification Q1), and store it at the specified path before deletion.
- **FR-006**: The command MUST delete DB records associated with the specified year. The exact DB tables and selection logic are documented in the Assumptions section and flagged for clarification where required.
- **FR-007**: The command MUST remove filesystem artifacts matching the year: `output/<YEAR>/**` and `logs/` files whose names contain the year or whose metadata indicate they relate to that year (e.g., run_logger NDJSON entries referencing that year). Files not owned/accessible MUST be reported but not cause whole-run failure.
- **FR-008**: The command MUST exit with a non-zero status when critical failures occur (e.g., DB delete partially applied and rollback not possible), and write a partial audit indicating what succeeded/failed.

*Marked unclear requirements (need operator decision):*

- **FR-009**: [NEEDS CLARIFICATION: Backup policy] Should the purge command create a backup by default before deletion, or only when `--backup` is explicitly provided? (See Clarification Q1)
- **FR-010**: [NEEDS CLARIFICATION: DB table scope] Which exact database tables and records must be purged for a given year (e.g., `cases`, `docket_entries`, `attachments`, audit tables)? Provide canonical SQL `WHERE` logic or table list. (See Clarification Q2)
- **FR-011**: [NEEDS CLARIFICATION: Log selection] Should the purge remove only `run_logger` NDJSON files and modal HTML files that encode the year in filename, or should it parse NDJSON to remove only entries referencing that year and keep the file if it contains other years? (See Clarification Q3)

### Key Entities *(include if feature involves data)*

- **CaseRecord (DB)**: Represents a scraped case persisted in the database. Key attributes: `case_id`, `case_number`, `scraped_at` (timestamp), `year` derived from `case_number` or `scraped_at`.
- **PerCaseFile (Filesystem)**: Files under `output/<YEAR>/` containing per-case JSON. Key attributes: filepath, last_modified, size.
- **RunLogFile (Filesystem)**: NDJSON files produced by `RunLogger`, each line contains an event with a timestamp, case_number and outcome.
- **ModalHTML (Filesystem)**: Saved HTML files under `logs/` whose filename convention includes the case number and timestamp.
- **PurgeAudit (Filesystem)**: JSON file created by the purge operation summarizing actions taken and any errors; includes counts and sample paths.

## Constitution Compliance *(mandatory)*

- **CC-001**: Include automated tests covering happy path, `--dry-run`, partial failure (simulated DB failure), permission errors on filesystem, and non-interactive `--yes` runs.
- **CC-002**: Follow project Git workflow: branch `001-yearly-data-purge`, include tests under `tests/services` and update docs (`docs/chg-003-yearly-data-purge.md`).
- **CC-003**: Adhere to coding standards and typing; new code must include docstrings and unit tests where applicable.
- **CC-004**: Start with an issue tracking the purge feature and link it to the branch and PR; include release notes in `CHANGELOG.md`.
- **CC-005**: Ensure the purge implementation is permission-checked (e.g., operator requires a role or capability); document required credentials.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a year with up to 10,000 per-case JSON files and 10,000 DB rows, a full purge (files + DB) completes within 10 minutes on a reasonably-provisioned maintenance host (measured in CI or staging).
- **SC-002**: `--dry-run` reports exactly the set of items that would be removed; when the actual purge runs, 100% of the reported items are removed except for those listed as skipped with documented errors.
- **SC-003**: Audit file is produced for every run and contains: timestamp, operator (or automated job id), year, counts of removed/failed/skipped items, backup path if created.
- **SC-004**: Non-interactive runs with `--yes` return exit code 0 on success and produce an audit file; interactive runs without `--yes` require explicit confirmation.

## Assumptions

- The repository's DB schema includes a `cases` table (and possibly related tables such as `docket_entries`) where each record is associated with a year via `case_number` or `scraped_at`.
- By default, backups are NOT created unless `--backup` is explicitly supplied (this is the safer default); if you prefer backup-by-default, answer Clarification Q1.
- Log files for a year can be identified by filename convention including the year (e.g., `modal_IMM-..._20251126_...html`) or by scanning NDJSON entries; parsing NDJSON for selective deletion is more complex and thus optional depending on Clarification Q3.

## Testing Plan

- Unit tests:
  - `tests/services/test_purge_cli.py` covering argument parsing and behavior toggles (`--dry-run`, `--yes`, `--backup`).
  - `tests/services/test_purge_filesystem.py` simulating an `output/<YEAR>` tree and asserting file deletions and error handling.
  - `tests/services/test_purge_db.py` with a test database fixture to assert DB rows are removed and rollbacks occur on partial failures.

- Integration tests (staging):
  - Run a staging purge on a snapshot dataset for a year and verify audit, backup, and exit codes.

## Rollback & Recovery

- If a backup is created, recovery is performed by restoring the backup archive and re-importing DB data if applicable; recovery steps MUST be documented in `USAGE_GUIDE.md`.
- If no backup exists and purge partially succeeds, the audit must clearly indicate what was deleted to allow manual recovery steps.

## Deliverables

- CLI command implementation and unit tests
- Integration test under `tests/` and instructions to run in staging
- Documentation update `docs/chg-003-yearly-data-purge.md` describing usage and safety considerations

## Clarification Questions (max 3)

### Q1: Backup policy

**Context**: The purge operation is destructive.

**What we need to know**: Should the purge create backups by default before deletion, or only when `--backup` is explicitly provided?

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A      | Backups by default | Safer; increases storage/operation time and complexity; simplifies recovery. |
| B      | Backups only when `--backup` provided (default) | Faster and lower storage cost by default; operator must remember to request backup when needed. |
| C      | Operator-configurable default via `config.toml` | Flexible; requires config and docs. |

**Your choice**: _[Wait for user response]_

### Q2: Database scope

**Context**: The tool will delete DB records for a year, but which tables/columns must be purged?

**What we need to know**: Confirm exact DB tables to delete (e.g., `cases`, `docket_entries`, `attachments`, `run_logs`) and whether deletion must cascade or be done in a specific order.

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A      | Purge `cases` and cascade to related tables (`docket_entries`, attachments)` | Simple for operators; requires DB foreign keys or explicit cascades. |
| B      | Purge only `cases` and leave related tables for manual cleanup | Lower risk to accidentally remove attachments; requires separate housekeeping. |
| C      | Provide a table list in the config and let operator decide per-run | Flexible but requires config management. |

**Your choice**: _[Wait for user response]_

### Q3: Log selection strategy

**Context**: `run_logger` produces NDJSON files that may include multiple years; modal HTML files are per-case files named with timestamps.

**What we need to know**: Should the purge remove entire NDJSON run files when they contain any entries for the year, or selectively remove entries from NDJSON files (and rewrite files) keeping other years' entries?

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A      | Remove entire run files if they contain entries for the year | Simpler, faster, but may remove unrelated years' entries if runs span years. |
| B      | Parse NDJSON and remove only matching lines, rewrite file | More precise, preserves unrelated entries, but more complex and higher-risk; requires tests. |
| C      | Remove modal HTML files by filename only and leave run NDJSON files untouched | Minimal change, simpler to implement; run audit may still reference removed HTML. |

**Your choice**: _[Wait for user response]_

## Final Notes

This specification focuses on WHAT the `purge` command must do and why; it avoids specific implementation details such as ORM choices or exact SQL statements. Once the clarifications above are answered (maximum 3), the spec will be finalized and moved to `/specs/001-yearly-data-purge/spec.md` ready for `/speckit.plan`.

```
