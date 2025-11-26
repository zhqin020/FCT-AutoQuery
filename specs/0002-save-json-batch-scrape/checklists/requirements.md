# Requirements Quality Checklist — Save JSON & Batch Scrape

Purpose: Unit Tests for Requirements
Created: 2025-11-26
Audience: Author
Depth: Standard
Feature: specs/0002-save-json-batch-scrape/spec.md

## Requirement Completeness
- [ ] CHK001 - Are per-case JSON persistence requirements explicitly stated for all scrape modes (single, batch, interactive)? [Completeness, Spec §FR-001]
- [ ] CHK002 - Are filename and directory conventions (year directory, `<case-number>-<YYYYMMDD>.json`) fully specified, including time zone for `YYYYMMDD` and scrape timestamp source? [Completeness, Spec §FR-002]
 - [ ] CHK002 - Are filename and directory conventions (year directory, `<case-number>-<YYYYMMDD>.json`) fully specified, including time zone for `YYYYMMDD` and scrape timestamp source? [Completeness, Spec §FR-002] [Gap]
- [ ] CHK003 - Are the exact fields that must appear in the per-case JSON documented (minimum fields enumerated) or referenced to a schema? [Completeness, Spec §FR-001]
 - [ ] CHK003 - Are the exact fields that must appear in the per-case JSON documented (minimum fields enumerated) or referenced to a schema? [Completeness, Spec §FR-001] [Gap]
- [ ] CHK004 - Are error outcome categories and their required logged fields defined for every failure mode (failed-write, parse-error, no-results)? [Completeness, Spec §FR-005]
 - [ ] CHK004 - Are error outcome categories and their required logged fields defined for every failure mode (failed-write, parse-error, no-results)? [Completeness, Spec §FR-005] [Gap]
- [ ] CHK005 - Is the run-level audit output shape specified (fields in `ScrapeRun` and per-case entries)? [Completeness, Spec §Key Entities]

## Requirement Clarity
- [ ] CHK006 - Is "atomic" file write behavior defined with an explicit algorithm (temp file + fsync + atomic rename) or is this left ambiguous? [Clarity, Spec §FR-006]
 - [ ] CHK006 - Is "atomic" file write behavior defined with an explicit algorithm (temp file + fsync + atomic rename) or is this left ambiguous? [Clarity, Spec §FR-006] [Gap: spec mentions temp+rename but omits fsync/flush detail]
- [ ] CHK007 - Is the retry/backoff policy for transient failures quantified (max retries, base/backoff strategy, jitter)? [Clarity, Spec §FR-008]
 - [ ] CHK007 - Is the retry/backoff policy for transient failures quantified (max retries, base/backoff strategy, jitter)? [Clarity, Spec §FR-008] [Gap]
- [ ] CHK008 - Is the meaning of "avoid silent overwrite" for same-day duplicates specified (numeric suffix vs timestamp) and the exact naming convention for suffixes described? [Clarity, Spec §FR-002, Edge Cases]
 - [ ] CHK008 - Is the meaning of "avoid silent overwrite" for same-day duplicates specified (numeric suffix vs timestamp) and the exact naming convention for suffixes described? [Clarity, Spec §FR-002, Edge Cases] [Gap: spec mentions both options but does not choose a canonical rule]
- [ ] CHK009 - Are success/failure states and allowed status values for per-case records enumerated for the run log (`updated`, `failed-write`, `skipped`, etc.)? [Clarity, Spec §FR-005]
 - [ ] CHK009 - Are success/failure states and allowed status values for per-case records enumerated for the run log (`updated`, `failed-write`, `skipped`, etc.)? [Clarity, Spec §FR-005] [Gap: spec uses mixed terminology in examples (e.g., `updated` vs `success`)]

## Requirement Consistency
- [ ] CHK010 - Are file naming conventions consistent between per-case files and export/aggregate filenames referenced elsewhere (`export.json` vs per-case)? [Consistency, Spec §FR-002]
 - [ ] CHK010 - Are file naming conventions consistent between per-case files and export/aggregate filenames referenced elsewhere (`export.json` vs per-case)? [Consistency, Spec §FR-002] [Gap]
- [ ] CHK011 - Do the behavior expectations for interactive/manual mode match the batch-mode flow, or are there deliberate differences documented? [Consistency, Spec §FR-003, FR-004, User Story 3]
- [ ] CHK012 - Are retry limits and their effect on run-level outcome counts (e.g., retry then mark failed) consistent between write retries and DOM/parse retries? [Consistency, Spec §FR-006, FR-008]
 - [ ] CHK012 - Are retry limits and their effect on run-level outcome counts (e.g., retry then mark failed) consistent between write retries and DOM/parse retries? [Consistency, Spec §FR-006, FR-008] [Gap]

## Acceptance Criteria Quality (Measurability)
- [ ] CHK013 - Are measurable SLAs defined for per-case persistence (e.g., "JSON file exists within 30s for 95% of cases") and are they tied to test or monitoring plans? [Measurability, Success Criteria SC-001]
- [ ] CHK014 - Is the criterion for session reuse (e.g., "same browser process for 95% of 100-case run") testable and are the exact measurement points defined (PID observed at start/end)? [Measurability, SC-002]
 - [ ] CHK014 - Is the criterion for session reuse (e.g., "same browser process for 95% of 100-case run") testable and are the exact measurement points defined (PID observed at start/end)? [Measurability, SC-002] [Gap: measurement method not specified]
- [ ] CHK015 - Are acceptance checks for JSON schema validation (fields, types) specified and is a schema file referenced or included? [Measurability, SC-003]
 - [ ] CHK015 - Are acceptance checks for JSON schema validation (fields, types) specified and is a schema file referenced or included? [Measurability, SC-003] [Gap]

## Scenario Coverage
- [ ] CHK016 - Are primary, alternate, exception, and recovery flows enumerated for scraping a single case and for batch runs? [Coverage, Spec §User Scenarios]
 - [ ] CHK016 - Are primary, alternate, exception, and recovery flows enumerated for scraping a single case and for batch runs? [Coverage, Spec §User Scenarios] [Gap: recovery flows could be elaborated (operator actions, automated retries)]
- [ ] CHK017 - Is the expected behavior for "no results" (zero-results manifest) explicitly defined and example payload provided? [Coverage, Edge Cases]
- [ ] CHK018 - Are partial data scenarios (e.g., missing party fields, truncated detail HTML) addressed with expected JSON representations and acceptance criteria? [Coverage, Gap]
 - [ ] CHK018 - Are partial data scenarios (e.g., missing party fields, truncated detail HTML) addressed with expected JSON representations and acceptance criteria? [Coverage, Gap] [Gap]
- [ ] CHK019 - Are concurrent-run interactions (what happens when two runs target the same case daily) specified with respect to file creation and run logs? [Coverage, Edge Cases]
 - [ ] CHK019 - Are concurrent-run interactions (what happens when two runs target the same case daily) specified with respect to file creation and run logs? [Coverage, Edge Cases] [Gap]

## Edge Case Coverage
- [ ] CHK020 - Are disk-full, permission-denied, and other persistent I/O failures classified with required operator-facing messages and retry/abort rules? [Edge Case, Spec §FR-006]
 - [ ] CHK020 - Are disk-full, permission-denied, and other persistent I/O failures classified with required operator-facing messages and retry/abort rules? [Edge Case, Spec §FR-006] [Gap: operator-facing messaging requirements not specified]
- [ ] CHK021 - Are page-layout drift and parsing failures described with a clear operator escalation path (halt run vs. skip case) and required log contents? [Edge Case, Spec §Notes]
- [ ] CHK022 - Are duplicate-case handling rules for same-day runs specified (when to append suffix vs. treat as idempotent update)? [Edge Case, Spec §Assumptions]
 - [ ] CHK022 - Are duplicate-case handling rules for same-day runs specified (when to append suffix vs. treat as idempotent update)? [Edge Case, Spec §Assumptions] [Gap]

## Non-Functional Requirements
- [ ] CHK023 - Are performance targets defined for batch throughput and per-case latency, and are measurement methods specified? [Performance, SC-004]
- [ ] CHK024 - Are security requirements (sensitive data handling, local disk encryption, access control for output directory) documented or intentionally out-of-scope? [Security, NFR]
 - [ ] CHK024 - Are security requirements (sensitive data handling, local disk encryption, access control for output directory) documented or intentionally out-of-scope? [Security, NFR] [Gap]
- [ ] CHK025 - Are operational requirements defined for browser automation (desired browsers/versions, driver restart strategy limits, resource constraints) and their observability? [Reliability, Spec §FR-003]
 - [ ] CHK025 - Are operational requirements defined for browser automation (desired browsers/versions, driver restart strategy limits, resource constraints) and their observability? [Reliability, Spec §FR-003] [Gap]
- [ ] CHK026 - Are accessibility or UI-parity expectations for the manual mode documented (so manual lookups produce identical JSON)? [Accessibility/UX, User Story 3]

## Dependencies & Assumptions
- [ ] CHK027 - Are external dependencies (third-party site availability, API rate-limits, driver binaries) listed and their required contractual or operational guarantees documented? [Dependencies, Assumptions]
 - [ ] CHK027 - Are external dependencies (third-party site availability, API rate-limits, driver binaries) listed and their required contractual or operational guarantees documented? [Dependencies, Assumptions] [Gap]
- [ ] CHK028 - Is the assumption "default output root is `output/json/`" recorded with guidance for overriding and how relative vs absolute paths are resolved? [Assumption, Spec §Assumptions]
- [ ] CHK029 - Is traceability defined (IDs on requirements and acceptance criteria pointing to tasks/tests) and is an ID scheme mandated? [Traceability, Constraint CC-001]
 - [ ] CHK029 - Is traceability defined (IDs on requirements and acceptance criteria pointing to tasks/tests) and is an ID scheme mandated? [Traceability, Constraint CC-001] [Gap]

## Ambiguities & Conflicts
 - [ ] CHK030 - Are ambiguous terms such as "prominent", "fast", or "transient" quantified or flagged for definition in the spec? [Ambiguity] [Gap]
 - [ ] CHK031 - Do any requirements conflict (for example, "do not overwrite" vs "updated" semantics in per-case exports)? If so, are resolution rules provided? [Conflict] [Gap: examples in spec use mixed terminology]
 - [ ] CHK032 - Are operator rollback/recovery responsibilities defined in the event of partial run completion or corrupted exports? [Ambiguity/Recovery] [Gap]

---

Notes:
- Traceability: Where a spec section exists we reference it (e.g., `Spec §FR-001`). Items marked `[Gap]` indicate an explicit missing requirement that should be added to the spec.
- File created as a new checklist run; do not overwrite previous checklists in `checklists/`.
