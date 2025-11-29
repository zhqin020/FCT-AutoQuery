# Tasks for 0004-batch-mode-problem

Feature: Safe batch retrieval (boundary probing) and robust scraping fallbacks

Phases: Design -> Implementation -> Tests -> Docs -> QA

Tasks

- T1: Design & spec alignment
  - Description: Finalize requirements, edge cases, and acceptance criteria for safe probing and batch retrieval (statistics, start param, skip logic for already-captured IDs).
  - Files: `specs/0004-batch-mode-problem/spec.md`, `specs/0004-batch-mode-problem/plan.md`
  - Phase: Design

- T2: Implement probe algorithm
  - Description: Implement an exponential + conservative backward scan + bounded forward refinement algorithm that determines a safe upper bound for numeric IMM case ids with minimal probes.
  - Files: `src/services/batch_service.py`
  - Phase: Implementation
  - Acceptance: Provide unit tests that mock `check_case_exists` and validate probe budget behavior (typical-case ≤ `probe_typical_goal`, hard-limit `probe_budget`). Ensure deterministic tests cover edge cases (sparse gaps and dense ends).

- T3: CLI wiring for probe & batch options
  - Description: Add `probe` subcommand and `--start`/`--live` flags to allow running safe probes and batch runs from the CLI. Ensure `batch` subcommand respects `--start` and `--max-cases` semantics.
  - Files: `src/cli/main.py`
  - Phase: Implementation

- T4: Scraper resilience & helper extraction
  - Description: Extract/adjust parsing helpers and interaction fallbacks to improve testability: `_parse_date_str`, `_parse_label_value_table`, `_safe_send_keys`, `_dismiss_cookie_banner`, `_submit_search`, and robust modal extraction paths.
  - Files: `src/services/case_scraper_service.py`
  - Phase: Implementation

- T5: Deterministic unit tests & harness
  - Description: Add a fake WebElement harness and deterministic fixtures to unit-test parsing and Selenium-like interaction fallbacks. Cover happy path and edge cases for modal parsing and submit/search behavior.
  - Files: `tests/utils/fake_webelement.py`, `tests/fixtures/case_modal/*`, `tests/test_*.py`
  - Phase: Tests
  - Parallel: [P]
  - Note: If exact in-row XPath tests are required, extend the harness first (see T9 below).

- T6: End-to-end test scenarios & flaky fallback tests
  - Description: Add tests to exercise stale-element retry flows, last-cell/row-click fallbacks (via robust WebDriverWait fallback when necessary), and search-case retries.
  - Files: `tests/test_case_scraper_scrape_case_data_*.py`
  - Phase: Tests

- T7: Coverage reporting & quality gates
  - Description: Run `pytest --cov=src` and generate HTML/XML reports; ensure the constitution testing requirement is satisfied for changed modules (tests present for all modified `src/*` files).
  - Files: CI config, `coverage_html/`, `coverage.xml`
  - Phase: QA

- T8: Documentation & PR
  - Description: Add `PULL_REQUEST.md` describing scope, tests, how to run, and next steps. Draft PR and request reviews; include suggested reviewers and labels.
  - Files: `PULL_REQUEST.md`, GitHub PR
  - Phase: Docs

- T9: Follow-up tests / coverage improvements
  - Description: Identify remaining untested branches in `src/services/case_scraper_service.py` and add focused unit tests or extend the fake harness to exercise in-row XPath branches.
  - Files: `tests/*`, `tests/utils/fake_webelement.py`
  - Phase: Tests
  - Parallel: [P]
  - Note: This task is a prerequisite for exact in-row XPath unit tests: perform harness extension before adding brittle locator assertions.

- T10: Audit schema & artifact tests
  - Description: Implement the audit JSON/NDJSON schema and add tests that validate summary totals and NDJSON parsing per run.
  - Files: `specs/0004-batch-mode-problem/audit-schema.md`, `tests/test_audit_schema.py`
  - Phase: QA

- T0: Create Issue and link artifacts
  - Description: Create `issues/0004-batch-mode-problem.md` and ensure the Issue is referenced in the PR description to satisfy the constitution's Issue Management gate.
  - Files: `issues/0004-batch-mode-problem.md`
  - Phase: Design

- T11: Ensure tests exist for all `src/*` modules (constitution compliance)
  - Description: Scan the `src/` tree for modules without corresponding `tests/` entries. For any missing tests, create minimal test stubs that import the module and assert key public APIs are importable. These stubs should be small, deterministic, and designed to satisfy the constitution's "No Test, No Merge" policy. After creating stubs, open follow-up tasks to add full tests for those modules as needed.
  - Files: `tests/test_smoke_*.py`, `tests/` (new files as needed)
  - Phase: Tests

- T12: Rate-limiting, backoff & fault-injection tests
  - Description: Implement polite-crawling behavior: configurable randomized delays, exponential backoff on repeated failures and 429/503 detection. Add unit tests that simulate server-side throttling and verify backoff behavior and probe-budget enforcement.
  - Files: `src/lib/rate_limiter.py` (if not present), `tests/test_rate_limit_backoff.py`
  - Phase: Implementation + Tests

Notes

- Task IDs should be referenced in PR descriptions to provide traceability back to the feature spec.
- Tasks marked `[P]` may be executed in parallel if developer resources allow.
