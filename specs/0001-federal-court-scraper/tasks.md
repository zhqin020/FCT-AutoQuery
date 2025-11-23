# Tasks: Federal Court Case Scraper Correction

**Input**: Design documents from `/specs/0001-federal-court-scraper/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are OPTIONAL - not explicitly requested in the feature specification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Database and configuration setup

- [ ] T001 Setup PostgreSQL database schema for cases and docket_entries tables
- [ ] T002 Configure database connection in src/lib/config.py
- [ ] T003 Setup logging configuration in src/lib/logging_config.py

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 [P] Implement rate limiter in src/lib/rate_limiter.py
- [ ] T005 [P] Implement URL validator in src/lib/url_validator.py
- [ ] T006 [P] Setup testing framework (pytest) and coverage tools

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

## Phase 3: User Story 1 - Automate Federal Court Case Search and Scraping via Search Form (Priority: P1) 🎯 MVP

**Goal**: Enable automated searching and scraping of individual cases via search form

**Independent Test**: Can be fully tested by running the scraper on a single known case number and verifying that data is extracted and stored correctly via the search form process.

- [ ] T007 [P] [US1] Create Case model in src/models/case.py
- [ ] T008 [P] [US1] Create DocketEntry model in src/models/docket_entry.py
- [ ] T009 [US1] Implement CaseScraperService in src/services/case_scraper_service.py for page navigation and form interaction
- [ ] T010 [US1] Add modal detection and data extraction logic in case_scraper_service.py
- [ ] T011 [US1] Implement error handling and retry logic for network failures in case_scraper_service.py

## Phase 4: User Story 2 - Handle Batch Case Number Generation and Resume (Priority: P2)

**Goal**: Support batch processing with resume capability

**Independent Test**: Can be tested by starting the scraper and verifying it resumes from the correct case number after interruption.

- [ ] T012 [US2] Implement UrlDiscoveryService in src/services/url_discovery_service.py for case number generation
- [ ] T013 [US2] Add resume logic to query last processed case from database in url_discovery_service.py
- [ ] T014 [US2] Implement year skipping for consecutive no-results in url_discovery_service.py

## Phase 5: User Story 3 - Data Storage and Export (Priority: P3)

**Goal**: Store scraped data and export to files

**Independent Test**: Can be tested by scraping one case and verifying database insertion and JSON file creation.

- [ ] T015 [US3] Implement ExportService in src/services/export_service.py for JSON/CSV export
- [ ] T016 [US3] Add PostgreSQL UPSERT operations for cases and docket_entries in export_service.py
- [ ] T017 [US3] Implement file organization by year in export_service.py

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: Integration, documentation, and final validation

- [ ] T018 Integrate all services in src/cli/main.py
- [ ] T019 Add command-line argument parsing for batch processing in main.py
- [ ] T020 Implement progress tracking and logging in main.py
- [ ] T021 Add emergency stop mechanism for continuous failures
- [ ] T022 Update requirements.txt with all dependencies
- [ ] T023 Update README.md with corrected usage instructions
- [ ] T024 Create database initialization scripts
- [ ] T025 Add troubleshooting guide for common issues
- [ ] T026 Validate all success criteria are met
- [ ] T027 Final code review and constitution compliance check

## Dependencies

**User Story Completion Order**:
1. User Story 1 (P1) - Core scraping functionality
2. User Story 2 (P2) - Batch processing support  
3. User Story 3 (P3) - Data persistence and export

**Task Dependencies**:
- All user story tasks depend on Phase 2 completion
- T009 depends on T007 and T008
- T013 depends on database schema (T001)
- T016 depends on database schema (T001)

## Parallel Execution Examples

**Within User Story 1**:
- T007 and T008 can run in parallel (different model files)
- T009-T011 must run sequentially (service implementation)

**Across Stories**:
- User stories can be implemented in parallel once foundation is complete
- US2 and US3 can start after US1 models are done

## Implementation Strategy

**MVP First**: Start with User Story 1 for basic scraping capability, then incrementally add US2 and US3.

**Incremental Delivery**: Each user story delivers independently testable value.

**Risk Mitigation**: Foundation phase ensures stable base before feature work.</content>
<parameter name="filePath">/home/watson/work/FCT-AutoQuery/specs/0001-federal-court-scraper/tasks.md