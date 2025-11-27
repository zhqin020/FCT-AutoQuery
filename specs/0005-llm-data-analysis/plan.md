# Implementation Plan: [FEATURE]

**Branch**: `[####-feature-name]` | **Date**: [DATE] | **Spec**: [link]
## Summary

Implement an offline-capable data analysis pipeline for Federal Court immigration cases. The pipeline will
take existing JSON case dumps, perform deterministic rule-based classification (fast mode) and an
LLM-assisted extraction (accurate mode) to identify `Visa Office` and `Judge`, compute duration metrics,
and emit CSV/JSON summary artifacts and static charts. The initial MVP focuses on rule-mode processing,
correct metrics, and a simple CLI; Phase 2 adds Ollama LLM integration with checkpointing and audits.
**Input**: Feature specification from `/specs/[####-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary



**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]  
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]  
**Language/Version**: Python 3.9+ (project uses Conda env `fct`)  
**Primary Dependencies**: `pandas`, `numpy`, `requests`, `tqdm`, `pyarrow` (optional for fast I/O)  
**Storage**: Files (CSV/JSON/Excel) under `output/`; no DB required for MVP.  
**Testing**: `pytest` with fixtures in `tests/fixtures/`  
**Target Platform**: Linux developer workstation / CI runner  
**Project Type**: Single Python package under `src/fct_analysis` (CLI + library functions)  
**Performance Goals**: Rule-mode: 5k records < 10s (developer laptop benchmark). LLM-mode: batch processed with checkpointing.  
**Constraints**: Offline-first; prefer local Ollama endpoint for model calls.  
**Scale/Scope**: MVP: single-run batch analysis of up to 50k records; Phase 2: long-running resumable jobs.
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]  
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]  
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [single/web/mobile - determines source structure]  
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]  
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]  
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Ensure testing standards are planned (mandatory coverage, TDD, mocking)
- Git workflow compliance is incorporated (TBD, issue-driven branches)
- Coding standards are followed (type hinting, ethical scraping)
- Issue management strategy is adhered to (mandatory issues, lifecycle)
- Git workflow steps are integrated (test-first, branch naming conventions)
- Environment activation is required (conda activate fct before commands)

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
**Structure Decision**: Choose the single Python package layout. Create `src/fct_analysis/` with submodules:
- `cli.py` — CLI entry using argparse
- `parser.py` — JSON parsing and date normalization
- `rules.py` — rule-based classifier and status extractor
- `llm.py` — thin wrapper for Ollama calls (Phase 2)
- `metrics.py` — duration and aggregate computations
- `export.py` — CSV/Excel/JSON output helpers

Tests under `tests/` with `fixtures/` and unit/integration tests.
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None at present | - | - |

## Phase Plan & Tasks

Phase 0 (MVP research): confirm input shapes, representative sample, and define test fixtures. Owner: dev

Phase 1 (MVP implementation):
- Write parser, rules, and metrics modules.
- Add CLI `analyze --input <file> --mode rule` that writes CSV and summary JSON.
- Add unit tests for parser/rules/metrics and an integration smoke test using `tests/fixtures/0005_cases.json`.

Phase 2 (LLM integration):
- Add `llm.py` to call local Ollama; batch, checkpoint, audit failures to `logs/`.
- Add `--resume` and `--sample-audit N` CLI options.

Phase 3 (Reports & Charts):
- Add plotting utilities using `seaborn`/`matplotlib` to produce PNG charts per spec.

Milestones & Acceptance Criteria:
- M1: Rule-mode pipeline runs end-to-end on fixture and produces `output/federal_cases_0005_details.csv` and `output/federal_cases_0005_summary.json` (automated tests pass).
- M2: LLM-mode implements checkpointing and produces audit log; manual audit reaches target accuracy.

Estimated effort: MVP (Phase1) ≈ 1–2 days of focused work; Phase2 ≈ 2–3 days for LLM integration and audit harness.

## Notes / Next Actions

- Create `tests/fixtures/0005_cases.json` (small representative set). 
- Implement scaffolding under `src/fct_analysis/` and tests.
- Update `requirements.txt` to include MVP dependencies.

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
