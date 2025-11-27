# Issue 0002 — IMM-33-25 .. IMM-38-25: scrape failures and retry report

Summary

- Date (run): 2025-11-26
- Cases investigated: IMM-33-25, IMM-34-25, IMM-35-25, IMM-36-25, IMM-37-25, IMM-38-25
- Problem reported: those cases previously failed to be collected and were not retried; logs showed `StaleElementReferenceException` in `scrape_case_data`.

What I changed

- Implemented a 3-attempt retry loop in `src/cli/main.py` around `scraper.scrape_case_data(case_number)` with a short backoff and a best-effort `initialize_page()` between attempts.
- Added a small runner script `scripts/run_specific_cases.py` to reproduce the issue quickly.
- Executed the runner inside the `fct` conda environment and observed the following results (all cases succeeded during the run):
  - IMM-33-25: success (entries=10), modal saved to `logs/modal_IMM-33-25_20251127_025648.html`, JSON -> `output/json/2025/IMM-33-25-20251126.json`
  - IMM-34-25: success (entries=9), modal saved to `logs/modal_IMM-34-25_20251127_025655.html`, JSON -> `output/json/2025/IMM-34-25-20251126.json`
  - IMM-35-25: success (entries=18), modal saved to `logs/modal_IMM-35-25_20251127_025704.html`, JSON -> `output/json/2025/IMM-35-25-20251126.json`
  - IMM-36-25: success (entries=12), modal saved to `logs/modal_IMM-36-25_20251127_025711.html`, JSON -> `output/json/2025/IMM-36-25-20251126.json`
  - IMM-37-25: success (entries=11), modal saved to `logs/modal_IMM-37-25_20251127_025719.html`, JSON -> `output/json/2025/IMM-37-25-20251126.json`
  - IMM-38-25: success (entries=1), modal saved to `logs/modal_IMM-38-25_20251127_025726.html`, JSON -> `output/json/2025/IMM-38-25-20251126.json`

Notes

- The root cause in the logs was `selenium.common.exceptions.StaleElementReferenceException` raised when clicking the per-row "More" control. `src/services/case_scraper_service.py` already had limited retries around finding/clicking the control; however, the higher-level caller previously did not retry the entire `scrape_case_data` flow when it returned `None`.
- The CLI-level retry mitigates transient DOM re-renders and should reduce missed cases.

Files changed

- `src/cli/main.py` — added CLI-level retry loop and short backoff
- `scripts/run_specific_cases.py` — small helper to reproduce the run

Recommended next steps

1. Make the retry count configurable via `src.lib.config.Config` instead of the current hard-coded `3`.
2. Add more granular logging on scrape attempt failures (capture exception info per attempt).
3. Add an integration test that simulates a stale element during the click (difficult but valuable).

-- automated note by assistant
