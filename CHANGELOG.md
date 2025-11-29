# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2025-11-25

- Add `--force` CLI flag to allow forcing re-scraping of cases even when they
  already exist in the local PostgreSQL database. Useful to refresh cached
  records or re-run parsing for previously-scraped cases.

- Batch jobs now write an audit summary JSON file to `output/` named
  `audit_YYYYMMDD_HHMMSS.json`. The audit includes a timestamp, year,
  scraped/skipped counts, list of skipped cases, and export metadata.

- CLI: lazy scraper initialization to avoid spawning a browser when all cases
  are skipped by the database-existence check.

- CLI: add global backoff/rate-limiter tuning flags:
  - `--rate-interval` (float) — fixed interval in seconds between requests.
  - `--backoff-factor` (float) — exponential backoff multiplier applied on failures.
  - `--max-backoff-seconds` (float) — maximum backoff delay in seconds.
  These flags allow runtime tuning of `EthicalRateLimiter` for live probing and
  batch operations. (Tests added: `tests/test_cli_backoff_flags.py`)

- Yearly purge: add `purge <YEAR>` CLI to safely remove `output/<YEAR>` and
  related DB records. Supports `--dry-run`, backups, `--files-only`/`--db-only`,
  `--force-files`, and an audit JSON at `output/purge_audit_<TS>_<YEAR>.json`.
  (Spec: `specs/0003-yearly-data-purge/`)

- CLI: improve help text and examples — expanded subcommand descriptions, an
  expanded examples epilog in `src/cli/main.py`, and explicit default values in
  argument help strings (e.g. `--rate-interval`, `--backoff-factor`, `probe` and
  `purge` options). This improves discoverability and safer usage of
  destructive commands such as `purge` (2025-11-29).

- Docs: recorded README and CHANGELOG updates for CLI help improvements (2025-11-29).

---

For full history, create tags and release notes following semantic versioning.
