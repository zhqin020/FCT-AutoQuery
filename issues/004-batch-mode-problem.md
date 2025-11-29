---
title: "004 - Batch mode: efficient upper-bound probing for IMM case IDs"
labels:
  - enhancement
  - scraping
  - spec
assignees: []
---

Summary
-------
The batch-mode scraper currently iterates sequentially over numeric IMM case IDs and can perform many unnecessary requests when the last available case number is far below the scan limit. This issue tracks implementing a safer, low-probe algorithm to discover an approximate upper numeric id per-year before running bulk scraping.

Related
-------
- Spec: `specs/0004-batch-mode-problem/spec.md`
- Branch: `chg/004-batch-mode-problem`

Problem Statement
-----------------
- Unbounded sequential scanning can trigger remote rate limits and wastes requests.
- There are sparse or gapped numeric ranges; naive heuristics misclassify holes as end-of-data.
- We need a configurable, auditable probe that minimizes requests while reliably finding a working upper bound.

Acceptance Criteria
-------------------
- Add a `probe` CLI command that returns an approximate upper numeric id and probe count.
- Probe defaults to dry-run (no network). `--live` enables real probing and must be opt-in.
- Implement exponential probing + conservative backward scan + forward refinement (see spec).
- Add unit tests for the probe algorithm and integration tests for the CLI using mocks.
- Add `--start` to `batch` to allow resuming from a given numeric id.

Design & Implementation Notes
-----------------------------
- Implementation lives in `src/services/batch_service.py` (`BatchService.find_upper_bound`).
- CLI wiring is on `src/cli/main.py` with `probe` subcommand (dry-run by default).
- Defaults: `initial_high=1000`, `probe_budget=200`, `max_limit=100000` (configurable via CLI flags).
- Tests: `tests/test_batch_service.py` covers dense, sparse, budget and max_limit scenarios.

Risks & Mitigations
--------------------
- Live probing may trigger rate limits; mitigated by requiring `--live` and keeping conservative defaults.
- Browser-based search is slower; consider a lightweight HEAD/GET path if available from the remote service.

Next Steps
----------
1. Review the spec and tests in `specs/0004-batch-mode-problem/` and `tests/test_batch_service.py`.
2. Add integration tests that mock `CaseScraperService` to assert `probe --live` wiring.
3. Prepare PR for `chg/004-batch-mode-problem` once the integration tests and documentation are reviewed.

References
----------
- `docs/chg-004-batch-mode-problem.md`
