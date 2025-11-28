# Implementation Plan: [FEATURE]

**Branch**: `[####-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[####-feature-name]/spec.md`

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
**Primary Dependencies**: `requests`, `beautifulsoup4`, `pydantic` (for lightweight validation), `loguru` (logging), `pytest`, `pytest-mock`
**Storage**: Files + JSON audit artifacts under `output/` (reuse existing repository storage API). No DB required for initial implementation.
**Testing**: `pytest` with network calls mocked via `pytest-mock` or `responses`.
**Target Platform**: Linux server (Ubuntu/Debian CI runners)
**Project Type**: Single CLI + library (fits repo layout under `src/`)
**Performance Goals**: Conservative crawl: goal is correctness and low probe count. Probe budget default 200; aim to detect high-water mark with <50 probes in common cases.
**Constraints**: Must enforce polite crawling: randomized delays, backoff on 429/503; storage and logging must be audit-friendly. Must follow ethical/legal guidance in repo constitution.
**Scale/Scope**: Designed to handle up to 100k case ids per year, but typical datasets are far smaller; algorithms must avoid O(N) probing beyond the discovered upper bound.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Ensure testing standards are planned (mandatory coverage, TDD, mocking): PASS — tests required for `find_upper_bound`, crawl loop, retry logic; CI tests will be added.
- Git workflow compliance is incorporated (TBD, issue-driven branches): PASS — feature branch `chg/004-batch-mode-problem` exists and plan was recorded; will open an Issue to link to the PR per constitution.
- Coding standards are followed (type hinting, ethical scraping): PASS — plan mandates type hints, log levels, and polite crawling.
- Issue management strategy is adhered to (mandatory issues, lifecycle): NEEDS ACTION — create an issue file under `issues/` (skipped here; next step).
- Git workflow steps are integrated (test-first, branch naming conventions): PARTIAL — branch name does not use numeric prefix convention; we created a numeric spec dir `0004-...` to satisfy tools. Justification: repo's automation requires numeric prefixes; branch will remain `chg/004-batch-mode-problem` per request but the team should align naming before merge.
- Environment activation is required (conda activate fct before commands): PASS — noted in quickstart and constitution.

GATE DECISION: Proceed with Phase 0 and Phase 1 outputs. Remaining action: create an Issue file under `issues/` to fully satisfy the Issue Management gate before PR.

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
