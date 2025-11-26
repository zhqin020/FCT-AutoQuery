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

---

For full history, create tags and release notes following semantic versioning.
