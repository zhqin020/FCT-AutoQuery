Title: Safe batch probing, improved test harness, and backoff integration

Summary
-------
This PR implements a safe, low-probe algorithm for discovering the upper numeric
bound of IMM case IDs, extracts and hardens parsing helpers for deterministic
unit testing, extends the test harness, and integrates exponential backoff and
rate-limiting across probing and scraping flows.

Key changes
-----------
- Implemented `BatchService.find_upper_bound(...)` with exponential probing,
  conservative backward scan, and bounded forward refinement. Accepts an
  optional `rate_limiter` to apply backoff on transient failures.
- Added CLI `probe` wiring that instantiates an `EthicalRateLimiter` and passes
  it to the probe algorithm (uses `Config` getters). Dry-run and `--live`
  modes supported.
- Introduced `src/lib/rate_limiter.py` (and `EthicalRateLimiter`) with
  configurable `backoff_factor` and `max_backoff_seconds`, plus helpers
  `record_failure()` and `reset_failures()`.
- Integrated the rate limiter into:
  - `src/services/batch_service.py` (probe flow)
  - `src/cli/main.py` (CLI probe and batch-level backoff)
  - `src/services/case_scraper_service.py` (scraper-level rate limiter)
- Added unit and integration tests:
  - `tests/test_rate_limit_backoff.py` (backoff unit tests)
  - `tests/test_batch_service_backoff.py` (integration: transient exceptions)
  - Smoke stubs for constitution compliance: `tests/test_smoke_url_validator.py`, `tests/test_smoke_logging_config.py`.
- Updated feature artifacts:
  - `specs/0004-batch-mode-problem/spec.md` (canonical defaults + constitution note)
  - `specs/0004-batch-mode-problem/plan.md` (concrete metadata, deps)
  - `specs/0004-batch-mode-problem/tasks.md` (added T11/T12 and acceptance criteria for probing)

Tests
-----
- Ran full test suite: 108 passed, 1 skipped (local run).
- Added targeted tests for backoff and probe integration; smoke tests added for modules previously missing tests.

Configuration
-------------
New config getters and defaults (in `src/lib/config.py`):
- `get_backoff_factor()` (default: 1.0)
- `get_max_backoff_seconds()` (default: 60.0)

These values are used to configure `EthicalRateLimiter` instances created by
the CLI and services. They can be overridden via `config.toml` or environment
variables (`FCT_BACKOFF_FACTOR`, `FCT_MAX_BACKOFF_SECONDS`).

Notes for reviewers
-------------------
- The probe algorithm treats exceptions from `check_case_exists` as transient
  and will call `rate_limiter.record_failure()` when a `rate_limiter` is
  provided; callers should ensure `check_case_exists` raises only for
  transient conditions (network/timeouts) to avoid masking logic errors.
- Per the repository constitution, any `src/*` modules missing tests must
  include minimal smoke stubs; I added two smoke tests and added `tasks.md`
  T11 to create stubs for any remaining missing tests.

Next steps
----------
1. Optionally expose CLI flags to tune: `--rate-interval`, `--backoff-factor`, `--max-backoff`.
2. Integrate `record_failure(status_code)` semantics where HTTP status codes
   are available to provide stronger backoff signals on 429/503.
3. Optionally extend the fake WebElement harness to fully emulate XPath axes
   for exact in-row XPath unit tests (T9), or accept the higher-level
   fallback tests which are more stable.

Files changed (high level)
- src/lib/rate_limiter.py (+tests)
- src/services/batch_service.py (+integration with rate limiter)
- src/cli/main.py (probe wiring + CLI behavior)
- src/services/case_scraper_service.py (rate limiter config)
- src/lib/config.py (new getters)
- specs/0004-batch-mode-problem/{spec.md,plan.md,tasks.md}
- tests/* (new tests and smoke stubs)

If you'd like, I can (a) add CLI flags to tune rate/backoff params, (b)
update the PR description on GitHub, or (c) extend the fake harness for exact
XPath testing — which of these should I do next?
