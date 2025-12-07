# Tasks: Federal Court Case Automatic Query System

## Phase 1: Setup

- [x] T001 Setup Python environment with conda 'fct' in environment
- [x] T002 Create requirements.txt with Selenium 4.15+, pandas 2.0+, loguru 0.7+, webdriver-manager 4.0+, psycopg2 in requirements.txt
- [x] T003 Setup PostgreSQL database with schema from database_schema.sql
- [x] T004 Configure rate limiting with random delays (3-6 seconds) and pauses every 100 queries in config
- [x] T005 Implement database-backed tracking for resume capability in database

## Phase 2: Foundational

- [x] T006 [P] Create Case model in src/models/case.py
- [x] T007 [P] Create DocketEntry model in src/models/docket_entry.py
- [x] T008 Create database schema in src/lib/database_schema.sql
- [x] T009 Create config module in src/lib/config.py
- [x] T010 Create logging config in src/lib/logging_config.py
- [x] T011 Create rate limiter in src/lib/rate_limiter.py
- [x] T012 Create storage module in src/lib/storage.py
- [x] T013 Create url validator in src/lib/url_validator.py
- [x] T014 Create case utils in src/lib/case_utils.py
- [x] T015 Create metrics emitter in src/metrics_emitter.py

## Phase 3: User Story 1 (P1) - Browser Automation and Search

### Story Goal
As a user, I want the system to automate browser initialization, navigation to the Federal Court search page, tab selection, court dropdown selection, case number generation, search execution, result determination, and modal management so that I can efficiently query cases in batch.

### Independent Test Criteria
- Browser launches successfully and loads the target URL within 30 seconds
- Search tab and Federal Court option are correctly selected
- Case numbers are generated sequentially from IMM-1-20 to IMM-99999-25
- Search input accepts case numbers and submit works
- Accurately distinguishes between no-data and data-available results
- Modal opens on "More" click and closes properly

### Implementation Tasks
- [x] T016 [US1] Create batch service for case number generation in src/services/batch_service.py
- [x] T017 [US1] Create case scraper service for browser automation in src/services/case_scraper_service.py
- [x] T018 [US1] Implement page initialization (URL load, tab select, court select) in src/services/case_scraper_service.py
- [x] T019 [US1] Implement search execution (input clear, case enter, submit) in src/services/case_scraper_service.py
- [x] T020 [US1] Implement result status determination (no-data vs data detection) in src/services/case_scraper_service.py
- [x] T021 [US1] Implement modal management (More click, wait, close) in src/services/case_scraper_service.py

## Phase 4: User Story 2 (P2) - Data Extraction

### Story Goal
As a user, I want the system to extract case header information and docket entries from the modal dialog so that I can capture all relevant case data accurately.

### Independent Test Criteria
- All header fields (Court Number, Type, Type of Action, Nature of Proceeding, Filing Date, Office, Style of Cause, Language) are extracted correctly
- All docket entries (ID, Date Filed, Office, Recorded Entry Summary) are extracted from the table
- Data extraction handles missing or malformed data gracefully

### Implementation Tasks
- [x] T022 [US2] Implement case header data extraction in src/services/case_scraper_service.py
- [x] T023 [US2] Implement docket entries data extraction in src/services/case_scraper_service.py

## Phase 5: User Story 3 (P3) - Data Storage

### Story Goal
As a user, I want the system to store extracted case data in PostgreSQL database with UPSERT operations and create JSON backup files so that data is persisted reliably and can be backed up.

### Independent Test Criteria
- Case data is inserted/updated in cases table correctly
- Docket entries are inserted in docket_entries table with proper foreign key
- JSON files are created in output/json/{year}/ with correct naming and content
- No data loss occurs during storage operations

### Implementation Tasks
- [x] T024 [US3] Create export service in src/services/export_service.py
- [x] T025 [US3] Implement database storage with UPSERT in src/services/export_service.py
- [x] T026 [US3] Implement JSON file backup creation in src/services/export_service.py

## Phase 6: User Story 4 (P4) - Resume and Error Handling

### Story Goal
As a user, I want the system to track case processing status, resume from the last processed case on restart, handle network errors with retries, and support re-running failed cases so that the batch process is robust and can recover from interruptions.

### Independent Test Criteria
- Case status (pending, success, no_data, failed) is tracked accurately
- On restart, processing resumes from the next unprocessed case
- Network timeouts and page errors trigger retries up to 3 times
- Failed cases can be re-processed selectively
- Retry count is incremented appropriately

### Implementation Tasks
- [x] T027 [US4] Create case tracking service in src/services/case_tracking_service.py
- [x] T028 [US4] Implement status tracking and updates in src/services/case_tracking_service.py
- [x] T029 [US4] Implement resume logic (query highest processed case) in src/services/case_tracking_service.py
- [x] T030 [US4] Implement error handling and retry logic in src/services/case_scraper_service.py

## Phase 7: CLI and Integration

- [x] T031 Create main CLI application in src/cli/main.py
- [x] T032 Create simplified main CLI in src/cli/main_simplified.py
- [x] T033 Create purge CLI in src/cli/purge.py
- [x] T034 Create tracking integration CLI in src/cli/tracking_integration.py

## Final Phase: Polish & Cross-Cutting Concerns

- [x] T035 Create enhanced statistics service in src/services/enhanced_statistics_service.py
- [x] T036 Create files purge service in src/services/files_purge_service.py
- [x] T037 Create purge service in src/services/purge_service.py
- [x] T038 Create simplified tracking service in src/services/simplified_tracking_service.py
- [x] T039 Create url discovery service in src/services/url_discovery_service.py
- [x] T040 Create all __init__.py files for proper package structure

## Dependencies

User Story completion order:
- User Story 1 (Browser Automation) → User Story 2 (Data Extraction) → User Story 3 (Data Storage) → User Story 4 (Resume & Error Handling)

Story dependencies ensure each phase builds on the previous:
- US1 provides the foundation for data extraction (US2)
- US2 provides data for storage (US3)  
- US3 enables status tracking for resume (US4)

## Parallel Execution Examples

Per User Story:

**User Story 1 (Browser Automation):**
- T016 (batch service) can run in parallel with T017 (scraper service setup)
- T018-T021 can be implemented sequentially as they build on each other

**User Story 2 (Data Extraction):**
- T022 and T023 can run in parallel as they extract different data types

**User Story 3 (Data Storage):**
- T025 and T026 can run in parallel (database and JSON are independent)

**User Story 4 (Resume & Error Handling):**
- T027-T030 can be implemented sequentially

## Implementation Strategy

**MVP Scope**: User Story 1 (Browser Automation and Search) - provides core automation capability for manual testing.

**Incremental Delivery**:
1. Phase 1 + Phase 2 + Phase 3: Basic scraping with search and result detection
2. + Phase 4: Add data extraction capabilities  
3. + Phase 5: Add storage layer
4. + Phase 6: Add resume and error handling for production use
5. + Phase 7 + Final: CLI interfaces and polish features

**Risk Mitigation**: Start with US1 for early validation of browser automation approach before investing in data layers.</content>
<parameter name="filePath">/home/watson/work/fct-scraper/specs/simple/tasks.md