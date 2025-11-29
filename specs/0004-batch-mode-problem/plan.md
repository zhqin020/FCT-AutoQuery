# Plan: Batch Mode Problem (0004)

## Goal
Make batch runs reliable and safely interruptible with clear observability and measurable SLAs.

## Architecture / Stack
- Language: Python 3.12 (project).
- Components:
  - `batch_runner`: Orchestrates job queue, workers, concurrency, and signal handling.
  - `job_worker`: Executes a single job (browser init, scrape, store).
  - `checkpoint_store`: Writes/reads checkpoint state to disk (JSON) or configured storage.
  - `metrics_emitter`: Reuse existing run_logger/metrics modules (see `src/.../run_logger.py`).
- Use existing modules: `run_logger`, `rate_limiter`, `url_validator` where applicable.

## Data Model References
- See `data-model.md` for job and checkpoint schema.

## Phases & Tasks (minimal, actionable)
Phase 1 — Reproduce & Instrument
- P1-T1: Add additional logging around page init and browser startup (`batch_runner` & `job_worker`). (file: `src/batch_service.py` or existing module)
- P1-T2: Add test harness to reproduce hang locally (tests/harness/test_hang_repro.py).

Phase 2 — Implement Fixes
- P2-T1: Implement `max_retries` + exponential backoff in `job_worker`.
- P2-T2: Implement per-job timeout and forced cleanup.
- P2-T3: Implement graceful shutdown: SIGTERM handler in `batch_runner` to checkpoint and stop accepting new jobs.

Phase 3 — Tests & Validation
- P3-T1: Unit tests for retry/backoff.
- P3-T2: Integration test for SIGTERM checkpoint/resume.
- P3-T3: Benchmark test for 100-job run.

Phase 4 — Docs & Release
- P4-T1: Publish `docs/chg-004-batch-mode-problem.md`.
- P4-T2: Update README/USAGE_GUIDE for new flags/config.

## Technical Constraints and Decisions
- Prefer non-blocking concurrency model (threadpool/process pool or asyncio with workers) consistent with existing code style.
- Reuse existing logging/metrics APIs; do not introduce new external backends.
- Checkpoint files should be placed under `output/checkpoints/feature-0004/`.

## Risks & Mitigations
- Risk: Retry storms on systemic failures — Mitigation: Add global circuit breaker if failure rate above threshold (e.g., stop the run).
- Risk: Existing tests flake — Mitigation: Add deterministic mocks to integration tests for network/browser.

## Files to Change (specific)
- `src/batch_service.py` (or repo equivalent) — core runner changes.
- `src/worker.py` (or job execution module) — retry, timeout.
- `src/checkpoint.py` — atomic checkpoint write/read.
- `tests/test_batch_retry.py`, `tests/test_sigterm_checkpoint.py`
- `docs/chg-004-batch-mode-problem.md`
## Implementation Plan: 0004-batch-mode-problem

**Branch**: `feat/0004-batch-mode-problem` | **Date**: 2025-11-28 | **Spec**: `specs/0004-batch-mode-problem/spec.md`
**Input**: Feature specification from `/specs/0004-batch-mode-problem/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement a safe, efficient batch retrieval mode for `IMM-<number>-<yy>` case ids.
The feature will provide a probe mode to quickly discover an approximate upper bound
for a given year (exponential probing + conservative local refinement), then
run a bounded traversal from `--start` to computed `end` (or `--start + --max-cases`),
classifying results as `success`, `no-record`, or `failed`, with configurable
retry, delay, and safe-stop thresholds. Artifacts: per-run audit JSON and optional
NDJSON of attempts in `output/`.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.11
**Primary Dependencies**: `selenium`, `webdriver-manager`, `python-dateutil`, `requests` (for optional mock endpoints), `beautifulsoup4` (where needed), `pydantic` (optional validation), `loguru` (logging), `pytest`, `pytest-mock`
**Storage**: Files + JSON audit artifacts under `output/` (reuse existing repository storage API). No DB required for initial implementation.
**Testing**: `pytest` with network calls mocked via `pytest-mock` or `responses`.
**Target Platform**: Linux server (Ubuntu/Debian CI runners)
**Project Type**: Single CLI + library (fits repo layout under `src/`)
**Performance Goals**: Conservative crawl: goal is correctness and low probe count. Probe budget default 200; aim to detect high-water mark with <50 probes in common cases.
**Constraints**: Must enforce polite crawling: randomized delays, backoff on 429/503; storage and logging must be audit-friendly. Must follow ethical/legal guidance in repo constitution.
**Scale/Scope**: Designed to handle up to 100k case ids per year, but typical datasets are far smaller; algorithms must avoid O(N) probing beyond the discovered upper bound.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Ensure testing standards are planned (mandatory coverage, TDD, mocking): PASS — tests required for `find_upper_bound`, crawl loop, retry logic; CI tests will be added. Per constitution, any missing `src/*` tests will be created as minimal stubs (see `tasks.md` T11) before merge.
- Git workflow compliance is incorporated (TBD, issue-driven branches): PASS — numeric-prefixed spec dir `0004-batch-mode-problem` is used and branch name in this plan is `0004-batch-mode-problem` to remain compatible with automation. If branch naming deviates, update `.specify` scripts accordingly.
- Coding standards are followed (type hinting, ethical scraping): PASS — plan mandates type hints, log levels, and polite crawling.
- Issue management strategy is adhered to (mandatory issues, lifecycle): NEEDS ACTION — create an issue file under `issues/` (skipped here; next step).
- Git workflow steps are integrated (test-first, branch naming conventions): PARTIAL — branch name does not use numeric prefix convention; we created a numeric spec dir `0004-...` to satisfy tools. Justification: repo's automation requires numeric prefixes; branch will remain `chg/004-batch-mode-problem` per request but the team should align naming before merge.
- Environment activation is required (conda activate fct before commands): PASS — noted in quickstart and constitution.

GATE DECISION: Proceed with Phase 0 and Phase 1 outputs. Remaining action: create an Issue file under `issues/` to fully satisfy the Issue Management gate before PR.

## Additional Implementation Tasks

- Implement a dedicated rate-limiting and backoff task that covers 429/503 behavior, configurable randomized delays and exponential backoff, and tests that simulate server-side throttling.

## Template cleanup
The plan header and metadata were updated to use concrete values and today's date. Remove any remaining template placeholders when iterating further.

## Project Structure

### Documentation (this feature)

```text
specs/[####-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
