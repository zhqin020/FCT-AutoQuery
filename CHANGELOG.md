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

- Yearly purge: add `purge <YEAR>` CLI to safely remove `output/<YEAR>` and
  related DB records. Supports `--dry-run`, backups, `--files-only`/`--db-only`,
  `--force-files`, and an audit JSON at `output/purge_audit_<TS>_<YEAR>.json`.
  (Spec: `specs/0003-yearly-data-purge/`)

---

For full history, create tags and release notes following semantic versioning.
