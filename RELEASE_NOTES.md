Release: Save per-case JSON & batch scraping improvements

Summary
-------
Implements per-case JSON export with atomic writes, fsync durability, unique filename suffixing, and retry/backoff. Adds batch scraping optimizations (page initialization reuse, cached search input id, driver liveness + restart policy) and a run-level NDJSON RunLogger. Ensures `Case.to_dict()` serializes `docket_entries` so per-case JSON always contains them.

Files Changed
-------------
- `src/services/export_service.py` — atomic per-case JSON writes, retries/backoff, no duplicate merging
- `src/models/case.py` — `to_dict()` now includes `docket_entries`
- `src/services/case_scraper_service.py` — page init reuse, cached input id, driver restart
- `src/lib/run_logger.py` — run-level NDJSON logger + canonical status labels
- `src/cli/main.py` — reuse scraper session and record canonical statuses
- tests/* — unit + integration tests added/updated

Testing
-------
All tests pass locally inside the project's `fct` Conda environment:

    source /home/watson/miniconda3/etc/profile.d/conda.sh
    conda activate fct
    PYTHONPATH=. pytest -q

Current results: `44 passed` (unit + integration)
