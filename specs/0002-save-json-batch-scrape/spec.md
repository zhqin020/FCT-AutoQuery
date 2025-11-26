```markdown
# Feature Specification: Save JSON Files & Batch Scrape Optimization

**Feature Branch**: `0002-save-json-batch-scrape`  
**Created**: 2025-11-25  
**Status**: Draft  
**Input**: User description: "Fix critical issues: always save per-case JSON files (year-based dirs, filename <case-number>-<updatedate>.json) and optimize batch scraping to reuse browser/session instead of reinitializing for each case. See docs/chg-002-critical-issues.md for manual steps and examples."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Save per-case JSON on scrape (Priority: P1)

As an operator running a scrape for a court number, when the scraper displays the case details (the "More" dialog), the system MUST save a JSON file containing all collected fields for that case into a year-based directory using the filename pattern `<case-number>-<YYYYMMDD>.json` (e.g. `IMM-1-25-20251125.json`).

**Why this priority**: Persisting structured JSON per case is critical for auditability, downstream processing, and to fix the current bug where JSON files were not created.

**Independent Test**: Run a single-case scrape; verify a JSON file is created under `output/json/2025/` (or configured output path) with the required filename pattern and that its contents include the fields shown in the UI.

**Acceptance Scenarios**:

1. **Given** a valid case number returned by the search, **When** the details dialog is opened and scraping completes, **Then** a JSON file is written to `output/json/<YYYY>/` with the filename `<case-number>-<YYYYMMDD>.json` and contains all expected data fields.
2. **Given** the system is unable to write the JSON file (disk full or permission error), **When** the scrape completes, **Then** the system logs an error and retries the write up to 2 times, then marks the case as failed in the run log.

---

### User Story 2 - Batch scraping without reinitializing browser (Priority: P2)

As an operator performing bulk queries, when multiple case numbers are processed in sequence, the scraper MUST reuse the existing browser/session between cases: after finishing a case the scraper closes any open dialog boxes, clears the case number field, inputs the next number, submits, and proceeds—without fully restarting the browser between records.

**Why this priority**: Reinitializing the browser per case dramatically reduces throughput and is operationally impractical for large batches.

**Independent Test**: Run a batch of 20 case numbers and verify the browser process ID remains the same across cases and no full browser restart occurs; verify each case still results in a saved JSON file and successful completion or a logged failure.

**Acceptance Scenarios**:

1. **Given** a list of case numbers, **When** the batch run starts, **Then** the scraper processes each case sequentially while retaining the same browser session for the entire run.
2. **Given** a transient page dialog or modal error for a single case, **When** it is closed or the case is skipped, **Then** the batch continues to the next case without restarting the browser.

---

### User Story 3 - Manual/interactive scrape (Priority: P3)

As an operator using the interactive mode, I want each manual lookup to produce the same JSON file artifacts and logging as an automated run so that manual QA or ad-hoc lookups remain consistent with batch behavior.

**Why this priority**: Ensures parity between manual and automated operations and simplifies debugging and manual verification.

**Independent Test**: Manually perform a lookup and verify JSON output and logs match the fields and structure described in the requirements.

**Acceptance Scenarios**:

1. **Given** an operator performs a single lookup and closes dialogs as usual, **When** the scrape finishes, **Then** a JSON file is created and the run log records success or failure with a timestamp.

---

### Edge Cases

 - No results for a case number: scraper must create no-case JSON manifest indicating zero results (not an empty failure) and continue.
 - Duplicate case numbers or repeated runs within the same day: the system must not overwrite an existing JSON file created earlier that day; instead append a suffix (`-1`, `-2`, ...) or include a timestamp to avoid data loss.
 - Dialog or modal fails to appear or close: mark the case as retriable up to 2 times, then skip and log the failure.
 - Changes in page layout: scraper logs the parsing error and halts the run with a clear message for operator intervention.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST persist a per-case JSON file after successfully scraping the "More" details for a case. The JSON MUST include the fields visible in the UI (at minimum: `court_number`, `style_of_cause`, `nature_of_processing`, `parties`, full `details` text or HTML) and a scrape `timestamp`.
- **FR-002**: The per-case JSON files MUST be stored under a year directory using the pattern `output/json/<YYYY>/<case-number>-<YYYYMMDD>.json`. If a file with the same name already exists, the system MUST avoid silent overwrite (see Edge Cases) and instead create a unique filename.
- **FR-003**: In batch mode, the scraper MUST reuse the same browser/session across multiple case numbers and MUST NOT reinitialize the browser between individual cases.
- **FR-004**: The scraper MUST close any open dialog/modal after scraping a case, clear the case number input, enter the next case number, submit, and proceed automatically for the list provided.
- **FR-005**: The scraper MUST log per-case outcomes (success, failed-write, parse-error, no-results) with timestamps and a concise error message.
- **FR-006**: Writes of JSON files MUST be atomic (write to a temp file then rename) to avoid partial/ corrupted files if interrupted.
- **FR-007**: The system MUST expose configuration for `output directory`, `retry counts` for writes, and `max concurrent browser instances` (default: 1) as operational settings in the run configuration.
- **FR-008**: The scraper MUST include a retry/backoff policy for transient failures (e.g., network, temporary DOM issues) and limit retries to a configurable number (default: 2).

### Key Entities *(include if feature involves data)*

 - **CaseRecord**: Represents a single scraped court case. Key attributes: `case_number`, `style_of_cause`, `nature_of_processing`, `parties` (list), `details` (string or structured), `scrape_timestamp`, `source_url`, `file_path`.
 - **ScrapeRun**: Represents a batch or single run. Key attributes: `run_id`, `start_time`, `end_time`, `operator`, `cases_processed` (counts of success/failure), `browser_session_id`.
 - **Party**: Represents a party in the case. Key attributes: `name`, `role`, `representation`.

## Constitution Compliance *(mandatory)*

- **CC-001**: Feature MUST align with Testing Standard: include tests covering happy path, edge cases, and error conditions for file writes and dialog handling.
- **CC-002**: Feature MUST comply with Git Workflow & Branching Strategy: changes must be developed on `0002-save-json-batch-scrape` and follow repository PR process.
- **CC-003**: Feature MUST adhere to Coding Standards: use existing repository linting, type hints, and test practices.
- **CC-004**: Feature MUST meet Issue Management Strategy: link the feature to the originating issue or changelog entry `docs/chg-002-critical-issues.md`.
- **CC-005**: Feature MUST address Git Workflow: include tests and update documentation for run modes and configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For each successfully scraped case, a JSON file exists in the correct year directory within 30 seconds of completion for 95% of cases.
- **SC-002**: A batch run of 100 cases completes using a single browser/session without restarting the browser process for at least 95% of the run (excluding crashes), demonstrating session reuse.
- **SC-003**: At least 95% of completed cases produce a JSON file that passes a schema validation check (fields present and well-formed JSON).
- **SC-004**: In batch mode, average per-case processing time (from submit to JSON write) is reduced compared to the current baseline; measurable target: complete 100-case sample run with median per-case time under 20 seconds.

## Assumptions

- Default output root is `output/json/` unless overridden in run configuration.
- Date format for `updatedate` is `YYYYMMDD` and `updatedate` for filenames is the scrape date.
- The UI fields listed in the manual steps are stable; changes to UI will surface as parse errors that require maintenance.
- If multiple runs produce the same case on the same day, the system will add a numeric suffix to avoid overwriting.

## Notes

- This spec focuses on WHAT the system must do (persist JSON and reuse browser session). Implementation details (e.g., which browser automation library) are intentionally omitted.

```
