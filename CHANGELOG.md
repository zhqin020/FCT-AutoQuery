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

### Added

- Per-case JSON persistence: atomic writes with fsync, numeric suffixing to avoid
  overwrites, and exponential backoff with jitter on transient filesystem errors.
- Batch scraping improvements: reuse initialized search page across multiple
  case lookups, cache discovered search input id for throughput, and implement
  WebDriver liveness checks with restart policy.
- `Case.to_dict()` now always serializes `docket_entries` so per-case JSONs
  contain docket entries by default.
- Run-level NDJSON `RunLogger` to record per-case outcomes and finalize run
  metadata.

### Changed

- Exporter: remove duplicate merging of `docket_entries`; `Case.to_dict()` is
  authoritative.
- Tests: added unit and integration tests covering exporter behavior, CLI
  scraping flow, URL discovery, and session-reuse logic.


---

For full history, create tags and release notes following semantic versioning.
