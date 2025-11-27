# Draft PR: 0003-yearly-data-purge — Yearly Data Purge

Summary
-------
This branch implements a safe, auditable CLI `purge <YEAR>` command to remove all artifacts for a specified year.

Key capabilities
- `python -m src.cli.main purge <YEAR>` subcommand with flags: `--dry-run`, `--yes`, `--backup`, `--no-backup`, `--files-only`, `--db-only`, `--force-files`, `--sql-year-filter` (auto|on|off).
- Dry-run mode enumerates DB candidates and filesystem artifacts and writes `output/purge_audit_<ts>_<year>.json`.
- Backup helper: archives `output/<YEAR>` to `output/backups/output_backup_<year>_<ts>.tar.gz` by default (skippable via `--no-backup` or `--backup <path>`).
- DB purge: `src/services/purge_service.py::db_purge_year` supports a Postgres-optimized SQL-year-filter (`EXTRACT(YEAR FROM scraped_at)`) with safe SQLite fallback.
- Filesystem purge: atomic rename+delete of `output/<YEAR>` and removal of modal HTML files by filename match.
- Audit JSON summarises timestamp, year, counts, removed items, errors and notes; returned path is printed by the CLI.

Files changed / added
- `src/cli/purge.py` — CLI purge handler, audit writer, integration with files/db helpers
- `src/cli/main.py` — wired `purge` subcommand and flags
- `src/services/purge_service.py` — `db_purge_year` with SQL-year-filter fallback
- `src/services/files_purge.py` — `backup_output_year`, `purge_output_year`, `remove_modal_html_for_year`
- `tests/services/*` — unit tests for dry-run, backup, DB purge (SQLite), filesystem deletion, and `--force-files` behavior
- `.github/workflows/purge-postgres-test.yml` — CI job to run the conditional Postgres test
- `specs/0003-yearly-data-purge/{spec.md,plan.md,tasks.md,PR_DESCRIPTION.md}` — spec, plan, tasks, and this PR draft

Testing performed
- `pytest -q` : 45 passed, 1 skipped locally
- Added conditional Postgres integration test: `tests/services/test_purge_postgres_sql_filter.py` (runs only when `POSTGRES_TEST_DSN` is provided and `psycopg2` present)

How to run locally
1. Run full tests:
```bash
python -m pip install -r requirements.txt
pytest -q
```

2. Try the CLI dry-run (example):
```bash
python -m src.cli.main purge 2023 --dry-run
```

3. Real run with backup (interactively confirm by typing YES when prompted):
```bash
python -m src.cli.main purge 2023 --yes --backup
```

4. Force file purge after DB errors:
```bash
python -m src.cli.main purge 2023 --yes --force-files
```

Open PR from this branch (example using `gh`):
```bash
git checkout 0003-yearly-data-purge
git push origin 0003-yearly-data-purge
gh pr create --title "feat: Yearly Data Purge (0003)" \
  --body-file specs/0003-yearly-data-purge/PR_DESCRIPTION.md \
  --base main --head 0003-yearly-data-purge --draft
```

Notes & follow-ups
- Decide production default for file purge when DB purge fails: currently permissive (file purge proceeds and `--force-files` records intent). Recommend requiring `--force-files` in production; we can flip this before merging.
- Integration test: CI includes a job that runs the Postgres test in a container; please review CI resource/time budgets.
- Docs: `docs/chg-003-yearly-data-purge.md` and `USAGE_GUIDE.md` snippets should be added before final merge.

Recommended reviewers
- Backend/DB owner(s) for schema and cascade behavior
- Devops / CI maintainer to validate Postgres job
