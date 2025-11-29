# Feature: Batch Mode Problem (0004)

## Overview / Context
Brief: Batch-mode runs intermittently hang or fail during page initialization and scraping. This feature tracks investigation and fixes to make batch runs reliable, observable, and gracefully stoppable. The scope focuses on the batch runner behavior, job lifecycle, retries, checkpointing, and signal handling.

## Functional Requirements (each with acceptance criteria)
- user-can-run-batch-jobs
  - Description: System accepts and executes batch scraping jobs from CLI or scheduled runs.
  - Acceptance: `fct-scraper --batch --config <cfg>` starts a run; run terminates normally and exit code is 0 on success.

- batch-job-retries
  - Description: Per-job transient failures trigger retry attempts with exponential backoff.
  - Acceptance: Retries occur up to `max_retries` (default 3), with backoff factor configurable; verify via test that a transient failure is retried and final state is success if intermittent error resolved.

- fr-final-summary (FR-004)
  - Description: Batch runs produce a canonical run-level summary (JSON and/or console) that includes totals, durations, and error samples. This is the single authoritative requirement for run reporting and replaces any duplicate entries.
  - Acceptance: After run completes (or is stopped), a `report-<timestamp>.json` or console summary is produced with keys `run_id`, `start`, `end`, `total`, `succeeded`, `no_record`, `failed`, `duration_seconds`, `errors` (sample). This requirement is referenced as `FR-004` in the plan.

- graceful-shutdown
  - Description: On SIGTERM/SIGINT, the runner finishes/pauses current job(s), writes checkpoint(s), and exits within `graceful_shutdown_timeout` (default 30s).
  - Acceptance: Sending SIGTERM to a running batch results in exit within timeout and presence of checkpoint files/state.

- per-job-timeout
  - Description: Each job may be configured with a maximum runtime; jobs exceeding timeout are killed and marked failed with retry rules applied.
  - Acceptance: A job that exceeds `job_timeout` is stopped and treated as a failure for retry logic.
  - Default: `job_timeout` = 300  # seconds (5 minutes). Tests should assert timeout behavior and cleanup.

## Non-Functional Requirements
- performance (measurable): Default concurrency `concurrency=4`. System must complete 100 small jobs in under 10 minutes on a defined runner profile (see below) for CI benchmarking.
- observability (measurable): Logs include `batch.run.start`, `batch.job.start`, `batch.job.end`, `batch.run.end` events at INFO. Emit metrics: `batch.run.duration_seconds`, `batch.job.duration_seconds`, `batch.job.retry_count`, `batch.run.failure_rate`.
- reliability (measurable): For short runs (<10 minutes), target success rate >= 99% when executed on the defined runner profile.
- configurability: `max_retries`, `concurrency`, `job_timeout`, `graceful_shutdown_timeout` must be configurable via existing config (e.g., `config.toml` or env vars).

### CI Runner Profile (for measurable NFRs)
- `os`: Ubuntu-latest (GitHub Actions / CI equivalent)
- `cpu`: 2 vCPU
- `memory`: 4 GB RAM
- `network`: CI default network conditions (no special bandwidth guarantees)

Use this runner profile as the baseline for any benchmark acceptance tests and document any deviations when reporting performance numbers.

## User Stories (with acceptance)
- As an operator, I can start a batch run and receive a report when it completes.
  - Acceptance: CLI command exists and writes `report-*.json` with expected keys.

- As an operator, I can stop a batch run and see checkpointed progress.
  - Acceptance: SIGTERM triggers checkpoint; restart resumes from checkpoint.

- As a developer, I can reproduce the hang in a test harness.
  - Acceptance: A deterministic test simulates transient network errors and verifies retry and checkpoint behaviors.

## Edge Cases / Failure Modes
- Flaky network: ensure retries, exponential backoff, and circuit-breaker-style protection to avoid infinite retries.
- Partial write/atomicity: checkpointing must ensure atomic state updates (temporary-file then rename).
- Very long single-job durations: ensure per-job timeout enforces resource limits; allow operator override.
- Resource leak in browser drivers: ensure drivers/processes are always cleaned up even on failure.

## Test/Validation Scenarios
- Unit tests for retry/backoff logic.
- Integration test that simulates SIGTERM and verifies checkpoint and resume.
- Load test for 100 jobs with concurrency=4 measuring run time and failure rate.
```markdown
# Feature Specification: Batch retrieve mode (0004-batch-mode-problem)

**Feature Branch**: `chg/004-batch-mode-problem`  
**Created**: 2025-11-27  
**Status**: Draft  
**Input**: User description from `docs/chg-004-batch-mode-problem.md`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run a bounded batch retrieval (Priority: P1)

A developer or operator runs a batch job to collect case records for a specific year range using a numeric case-id pattern (e.g., `IMM-<number>-<yy>`), with support for `--start` and `--max-cases` parameters.

**Why this priority**: This is the primary use-case: automated bulk collection with controlled boundaries and minimal invalid requests.

**Independent Test**: Run the CLI command with a short `--max-cases` and verify the tool:
- produces expected results for existing IDs
- produces a stats summary containing start, end, total, success, no-record, failed
- skips previously-collected IDs when the storage contains them

**Acceptance Scenarios**:

1. Given a start `30` and `--max-cases 50` for year `23`, When the tool runs, Then it queries `IMM-30-23` through `IMM-60-23` inclusive and outputs a stats summary with counts: start, end, total, success, no-records, failed.
2. Given some IDs are already saved, When the tool runs, Then the saved IDs are skipped (not re-requested) and only missing/failed IDs are re-attempted according to retry policy.

---

### User Story 2 - Find the upper boundary quickly (Priority: P1)

As an operator, I want the system to detect the current maximum case number for the target year with very few requests, so that full-range traversal avoids querying far beyond the dataset and reduces invalid requests.

**Why this priority**: Prevents large numbers of invalid requests and reduces the chance of being rate-limited or blocked.

**Independent Test**: Run the upper-bound detection mode against a controlled target/test endpoint (or mock) and verify the detected high-water mark is within a small delta of the real maximum with fewer than 50 probe requests.

**Acceptance Scenarios**:

1. Given an environment where the maximum valid case id is 5600, When the boundary detection runs, Then it returns a maximum id in the range [actual-200, actual+0] using O(log N) probes plus a bounded local scan.

---

### User Story 3 - Resume, retry, and error classification (Priority: P2)

As an operator, I need failed requests to be classified (no-record vs. transient failure), retried up to a configurable limit, and re-queued for later if still failing, so the batch can resume without losing progress.

**Why this priority**: Reliability and correctness of the dataset depend on distinguishing real empty results from transient network/server errors.

**Independent Test**: Simulate transient network failures and verify that the system retries the configured number of times, records the failure if retry limit reached, and continues processing other IDs.

**Acceptance Scenarios**:

1. Given a transient HTTP timeout on a case request, When retries are attempted, Then the system retries up to `N` times and only counts as `failed` after `N` unsuccessful attempts.
2. Given a response that clearly indicates “no records”, When detected, Then the system counts that ID under `no-record` and does not retry.

---

### Edge Cases

- Very long sparse gaps (many consecutive no-records) — the system should have a configurable safe-stop threshold to avoid infinite traversal.
- Server rate-limiting or WAF blocks — the system should implement exponential backoff and stop if blocking is detected.
- Dynamic form tokens / ViewState required by the search page — the collector must be capable of retrieving and including required tokens when present.
- Partial results or paginated search results — collector must detect and handle multi-row results for a single case id if the site returns a list.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST detect the approximate upper bound (high water mark) for a given year using an efficient probe strategy (exponential growth + conservative local refinement) to minimize probe count.
- **FR-002**: System MUST traverse the case id range from `start` to `end` (determined by `--start` and `--max-cases` or upper bound) and request each case id exactly once unless retries or resume is required.
- **FR-003**: System MUST classify outcomes per-case into: `success`, `no-record` (explicitly no case for that id), or `failed` (transient error after max retries).
- **FR-004**: System MUST produce a final summary (start id, end id, total attempted, success count, no-record count, failed count) at job completion or termination.
- **FR-005**: System MUST skip case ids already collected and saved in persistent storage (a discovery check) to avoid redundant requests.
- **FR-006**: System MUST support configurable retry attempts and per-request timeout, and apply retries only to transient failures, not to confirmed `no-record` responses.
- **FR-007**: System MUST accept `--start` (default 1) and `--max-cases` parameters and compute the correct end id when `--start` is provided.
- **FR-008**: System MUST enforce polite crawling policies: configurable per-request delay, randomized jitter, and exponential backoff on repeated failures or server-side rate-limiting signals.
- **FR-009**: System MUST support a configurable safe-stop condition (e.g., consecutive `K` no-records or `K_fail` transient failures) that halts the job to avoid further invalid probing.
- **FR-010**: System MUST log per-case metadata (id, timestamp, outcome, attempts, notes) and produce audit-friendly artifacts (summary JSON and optional NDJSON log lines for each attempt).
- **FR-011**: System MUST surface errors and final stats through CLI exit codes and machine-readable output (JSON) for integration into pipelines.

### Key Entities

- **CaseIdentifier**: { `year`: string, `number`: integer } — represents a case id like `IMM-231-25`.
- **CrawlResult**: { `case_identifier`, `outcome` in [success,no-record,failed], `attempts`, `last_error`, `saved_path?` }.
- **CrawlStats**: { `start_id`, `end_id`, `total_attempted`, `success_count`, `no_record_count`, `failed_count` }.
- **CrawlConfig**: { `start`, `max_cases`, `retry_limit`, `delay_min`, `delay_max`, `safe_stop_consecutive_no_record`, `safe_stop_consecutive_fail` }.

## Constitution Compliance *(mandatory)*

- **CC-001**: Include automated tests covering the upper-bound detection, the main traversal loop, the retry behavior, and classification of responses.
- **CC-002**: Follow repository Git Workflow & Branching Strategy: work in `chg/004-batch-mode-problem` and open a PR when ready.
- **CC-003**: Adhere to coding standards: add types, clear docstrings, and log levels.
- **CC-004**: Ensure the feature is driven by an issue describing the desired dataset, and include a changelog entry describing the new CLI options and behaviors.
- **CC-005**: Include an audit output format consistent with the repository's existing `output/audit_*.json` artifacts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Upper-bound detection locates the high-water mark within at most 50 probe requests for typical year datasets (empirical target; testable against a known dataset or mock).
- **SC-002**: Final stats report is accurate: success + no-record + failed == total attempted for any run.
- **SC-003**: Skipping previously collected ids prevents redundant requests — verified by running twice: the second run must not re-request already-saved ids.
- **SC-004**: Retried transient failures succeed at a configurable rate: with retry_limit=3, at least 70% of transient network failures resolve on retry in test harness (testable via fault injection).
- **SC-005**: The tool limits probing beyond the real dataset — runs should not issue more than 2x the number of real items in the worst-case detection path (verifiable on test data).

## Assumptions

- Target site responds with explicit signals that distinguish `no records` (search result empty) from server/network errors. If not, heuristics are required.
- The repository already contains code to persist successful case data; this feature will reuse the same storage API to check for existing ids.

## Decisions

1. Safe-stop threshold: the safe-stop threshold is configurable via CLI and defaults to `500` consecutive `no-record` responses. CLI flag: `--safe-stop-no-records` (default `500`). Tests will include lower thresholds (e.g., `100`) to validate behavior under sparse datasets.

2. Raw HTML persistence: by default persist raw HTML only for failed attempts. Provide CLI toggle `--persist-raw-html` to enable full persistence of successful fetches. Failure-only persistence will save files to `output/html_failed/<run>/<case_id>.html` and the audit NDJSON will record the path.

3. Probe budget and detection goal: expose a configurable `probe_budget` (default `200`) as an upper bound for probe attempts; the empirical typical-case goal for high-water detection is ≤50 probes. Tests should assert typical-case behavior while enforcing the configured `probe_budget` as the hard upper limit.

## Configuration Defaults (canonical)

The following canonical defaults are authoritative for this feature and should be referenced by implementation and tests. Tests and tasks MUST reference these values rather than re-stating ad-hoc numbers.

- `safe_stop_no_records`: 500 (default consecutive `no-record` responses to trigger safe-stop)
- `probe_budget`: 200 (hard upper limit on probe attempts during upper-bound detection)
- `probe_typical_goal`: 50 (typical-case target for probe attempts; not a hard limit but used for acceptance tests)
- `persist_raw_html`: false (default; raw HTML persisted only for failures unless CLI toggled)

Per the project constitution, every `src/*` module MUST have corresponding tests. If any `src/*` module is missing test coverage at merge time, the following remediation task will be required (see `tasks.md` T11): create minimal test stubs that assert importability and critical public API surface to satisfy the constitution. This is a required step and not optional.
## Testing / User Scenarios (expanded)

- Unit tests for `find_upper_bound` using a mocked endpoint that returns `no-record`/`has-record` patterns.
- Integration test: run a short `--max-cases` batch against a controlled test server and assert the stats and artifacts.
- Fault injection tests: simulate timeouts, 500 errors and assert retry behavior and classification.

```
<!-- end file -->
```