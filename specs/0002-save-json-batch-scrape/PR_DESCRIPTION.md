Title: feat(0002): per-case JSON persistence + batch session reuse

Summary
-------
Implements per-case JSON export with atomic writes, fsync durability, unique filename suffixing,
and retry/backoff. Adds batch scraping optimizations (page initialization reuse, cached
search input id, driver liveness + restart policy) and a run-level NDJSON RunLogger. Also
ensures `Case.to_dict()` serializes `docket_entries` so per-case JSON always contains them.

Files Changed
-------------
- `src/services/export_service.py` — atomic per-case JSON writes, retries/backoff, no duplicate merging
- `src/models/case.py` — `to_dict()` now includes `docket_entries`
- `src/services/case_scraper_service.py` — page init reuse, cached input id, driver restart
- `src/lib/run_logger.py` — run-level NDJSON logger + canonical status labels
- tests/* — unit + integration tests added/updated
- `.github/workflows/ci-fct.yml` — CI workflow to run tests in Conda `fct` env

Testing
-------
All tests pass locally inside the project's `fct` Conda environment:

    source /home/watson/miniconda3/etc/profile.d/conda.sh
    conda activate fct
    PYTHONPATH=. pytest -q

Current results: `37 passed` (unit + integration)

Notes for reviewers
-------------------
- The exporter uses UTC date for filenames and numeric suffixing to avoid overwrites.
- `Case.to_dict()` is authoritative; exporter no longer attempts to merge `docket_entries`.
- RunLogger enforces canonical per-case statuses (e.g., `success`, `error`, `parse-error`).
- Integration tests use lightweight fakes (no real Selenium instances) to validate session reuse and driver restart logic.

Follow-ups (optional)
---------------------
- Add more integration tests to simulate transient modal failures and recovery/backoff.
- Add end-to-end smoke that exercises real Selenium in a gated, optional CI matrix job.
