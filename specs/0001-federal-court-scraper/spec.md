# Feature Specification: Federal Court Case Scraper Correction

**Feature Branch**: `0001-federal-court-scraper`  
**Created**: 2025-11-22  
**Status**: Draft  
**Input**: User description: "经过测试，发现采集数据的方式完全错误，需求不符合原始要求 #file:requirement.md case number 不是通过url 发送的，而是在search form 中。编写specify 文档的时候，应该非常重视 "## 8. 附联邦法院网站查询功能，人工操作流程" 这个清晰地说明查询的过程"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automate Federal Court Case Search and Scraping via Search Form (Priority: P1)

System must automate the process of searching for Federal Court cases using the website's search form, not direct URL access. The system should navigate to the court files page, select the search tab, choose Federal Court, input case numbers in format IMM-{number}-{year}, submit searches, detect results, click "More" for details, extract case information and docket entries, and store data.

**Why this priority**: This is the core functionality required to collect case data automatically, correcting the previous incorrect implementation that used direct URLs.

**Independent Test**: Can be fully tested by running the scraper on a single known case number and verifying that data is extracted and stored correctly via the search form process.

**Acceptance Scenarios**:

1. **Given** the system is initialized, **When** it loads the court files page, **Then** it should automatically switch to "Search by court number" tab and select "Federal Court".
2. **Given** a case number like "IMM-12345-22", **When** entered in the search form and submitted, **Then** the system should detect if results exist or show "No data available".
3. **Given** results exist, **When** "More" is clicked, **Then** the modal should open and case details should be extracted.
4. **Given** extraction is complete, **When** "Close" is clicked, **Then** the modal should close and the system should proceed to the next case.

### User Story 2 - Handle Batch Case Number Generation and Resume (Priority: P2)

System must generate case numbers sequentially from IMM-1-20 to IMM-99999-25, with resume capability from last processed case.

**Why this priority**: Enables efficient batch processing of all target cases without manual intervention.

**Independent Test**: Can be tested by starting the scraper and verifying it resumes from the correct case number after interruption.

**Acceptance Scenarios**:

1. **Given** no previous runs, **When** scraper starts, **Then** it should begin with IMM-1-20.
2. **Given** previous run processed up to IMM-5000-22, **When** restarted, **Then** it should resume from IMM-5001-22.
3. **Given** multiple consecutive no-results, **When** detected, **Then** it should skip to the next year.

### User Story 3 - Data Storage and Export (Priority: P3)

System must store extracted case data in PostgreSQL database and export to JSON files.

**Why this priority**: Ensures data persistence and backup for analysis.

**Independent Test**: Can be tested by scraping one case and verifying database insertion and JSON file creation.

**Acceptance Scenarios**:

1. **Given** case data extracted, **When** stored, **Then** cases table should have new record with all fields.
2. **Given** docket entries, **When** stored, **Then** docket_entries table should have related records.
3. **Given** data stored, **When** exported, **Then** JSON file should be created in ./data/{YEAR}/{CASE_ID}.json format.

### Edge Cases

- What happens when website structure changes (e.g., element IDs)?
- How does system handle network timeouts or 403 errors?
- What if modal fails to open or close?
- How to handle cases with no docket entries?
- What if consecutive cases have no results?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-01**: System MUST load the target URL https://www.fct-cf.ca/en/court-files-and-decisions/court-files and automatically switch to "Search by court number" tab.
- **FR-02**: System MUST select "Federal Court" from the Court dropdown.
- **FR-03**: System MUST generate case numbers in format IMM-{1-99999}-{20-25} and support resume from last processed.
- **FR-04**: System MUST input case number in search form and click Submit.
- **FR-05**: System MUST detect "No data available in table" for no results or "More" link for results.
- **FR-06**: System MUST click "More" to open modal and extract case header information (Court File No., Type, Type of Action, Nature of Proceeding, Filing Date, Office, Style of Cause, Language).
- **FR-07**: System MUST extract docket entries table (ID, Date Filed, Office, Recorded Entry Summary).
- **FR-08**: System MUST click "Close" to close modal and handle failures by refreshing page.
- **FR-09**: System MUST store data in PostgreSQL with UPSERT and export to JSON files.
- **FR-10**: System MUST implement random delays (3-6 seconds) and longer breaks every 100 queries.

### Key Entities *(include if feature involves data)*

- **Case**: Represents a court case with attributes like case_id, style_of_cause, nature_of_proceeding, filing_date, office, case_type, action_type, crawled_at.
- **Docket Entry**: Represents historical records for a case with case_id, doc_id, entry_date, entry_office, summary.

## Constitution Compliance *(mandatory)*

- **CC-001**: Feature MUST align with Testing Standard: Include tests covering happy path, edge cases, and network failures with mocking.
- **CC-002**: Feature MUST comply with Git Workflow & Branching Strategy: Follow trunk-based development and test-first policy.
- **CC-003**: Feature MUST adhere to Coding Standards: Use type hinting, Google docstrings, ethical scraping with random delays.
- **CC-004**: Feature MUST meet Issue Management Strategy: Ensure feature starts with a mandatory GitHub issue.
- **CC-005**: Feature MUST address Git Workflow: Follow issue-driven branching and PR merge process.
- **CC-006**: Feature MUST require environment activation: Run commands after `conda activate fct`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: System can successfully search and extract data for at least 90% of valid case numbers.
- **SC-002**: System processes 100 cases per hour without errors.
- **SC-003**: Data accuracy matches manual extraction in 100% of tested cases.
- **SC-004**: System handles website changes with minimal downtime (under 1 hour to adapt).
- **SC-005**: Database contains complete case and docket data for all processed cases.

## Assumptions

- Federal Court website structure remains stable for the duration of implementation.
- PostgreSQL database is available and configured.
- No IP blocking occurs during normal operation with implemented delays.
- Case numbers follow the specified format and range.

## Dependencies

- Access to Federal Court website without restrictions.
- PostgreSQL database setup.
- Python environment with required packages.

## Risks

- Website changes could break scraping logic.
- IP blocking if delays are insufficient.
- Data quality issues if website data is incomplete.

## DOM Structures

To ensure accurate implementation, the following DOM structures are provided for key pages. These were captured using browser developer tools (F12) and represent the HTML structure as of November 22, 2025.

### 1. Search Page (Initial Entry Page)
**File:** `docs/page-dom/searchpage.html`  
**URL:** https://www.fct-cf.ca/en/court-files-and-decisions/court-files  
**Description:** The initial page loaded for court files search. Contains navigation and search tabs.

**Key Elements:**
- Navigation: `<nav class="navbar navbar-expand-lg align-self-center">`
- Search tabs: Located in the main content area, includes "Search by court number" tab
- Court dropdown: `<select>` element for selecting court type (Federal Court, etc.)
- Input field: `<input>` for case number entry
- Submit button: `<button>` or `<input type="submit">` for form submission

### 2. Search Results Page
**File:** `docs/page-dom/search-result.html`  
**URL:** Same as above, after switching to "Search by court number" tab and submitting search for "IMM-12334-25"  
**Description:** Page showing search results after submitting a case number query.

**Key Elements:**
- Results table: `<table class="table table-striped table-bordered">` with columns: Court Number, Style of Cause, Nature of Processing, Parties, More
- "More" button/link: In the "More" column, triggers modal popup
- No results message: "No data available in table" when no matches found

### 3. Detail Modal Page
**File:** `docs/page-dom/detail.html`  
**URL:** Same as above, after clicking "More" on a search result  
**Description:** Modal popup containing detailed case information and docket entries.

**Key Elements:**
- Modal container: `<div class="modal fade right show" id="ModalForm">`
- Close button: `<button type="button" class="close" data-dismiss="modal">` with × symbol
- Case header info: `<div class="modal-body">` containing labels like "Type:", "Nature of Proceeding:", "Office:", "Filing Date:", etc.
- Docket entries table: `<table class="table table-striped table-bordered">` with columns: ID, Date Filed, Office, Recorded Entry Summary
- Modal footer: `<div class="modal-footer">` with Close button

**Implementation Notes:**
- Use CSS selectors or XPath to locate elements reliably
- Wait for modal visibility before extracting data
- Handle bilingual text (English/French) in close buttons and labels
- Ensure proper waiting strategies for dynamic content loading
