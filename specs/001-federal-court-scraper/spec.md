# Feature: Federal Court Case Automatic Query System

## Overview

The Federal Court Case Automatic Query System automates the process of accessing the Canadian Federal Court website to batch query immigration (IMM) cases for the years 2020-2025. The system simulates manual user operations to search for case numbers, extract basic case information and detailed docket entries from modal dialogs, and persist the data to a PostgreSQL database and JSON files. It includes features for resume-on-interrupt, rate limiting to avoid detection, and error handling for network issues.

## User Scenarios & Testing

### Primary User Scenario: Automated Case Data Collection

**Given** the system is configured with database and output paths  
**When** the user runs the scraper script  
**Then** the system:
1. Initializes the browser and navigates to the court search page
2. Selects the "Search by court number" tab and "Federal Court" option
3. Generates case numbers sequentially from IMM-1-20 to IMM-99999-25
4. For each case:
   - Enters the case number and submits the search
   - If "No data available" appears, marks as no_data and continues
   - If results appear, clicks "More" to open the detail modal
   - Extracts header information and docket entries from the modal
   - Closes the modal and stores data
5. Implements random delays (3-6 seconds) between queries and longer pauses every 100 queries
6. Resumes from the last processed case on restart
7. Handles network timeouts and page errors with retries

### Testing Scenarios

- **Initialization Test**: Verify browser launches, page loads, tab selection, and court dropdown works
- **Search Test**: Test with known existing case (e.g., IMM-1-21) and non-existing case
- **Data Extraction Test**: Verify header fields and docket table parsing accuracy
- **Storage Test**: Confirm database UPSERT and JSON file creation
- **Error Recovery Test**: Simulate network failure, verify retry logic and status tracking
- **Resume Test**: Interrupt run, restart, verify continues from correct case number

## Functional Requirements

### FR-01: Page Initialization
The system must load the target URL (https://www.fct-cf.ca/en/court-files-and-decisions/court-files), click the "Search by court number" tab, and select "Federal Court" from the court dropdown.

### FR-02: Case Number Generation and Resume
Generate case numbers in format IMM-{sequence}-{year} where sequence is 1-99999 and year is 20-25. On startup, query database for the highest processed case number and resume from the next one.

### FR-03: Search Execution
Clear the search input, enter the current case number, and click the Submit button.

### FR-04: Result Status Determination
After submission, wait for page response and:
- If "No data available in table" appears, mark case as no_data
- If "More" link appears, proceed to data extraction
- If multiple consecutive cases show no data, skip to next year
- On network/page errors, retry up to 3 times, then mark as failed

### FR-05: Modal Management
After clicking "More", wait for modal to appear, extract data, then click "Close"/"Fermer"/"×" to close. On close failure, refresh page and reinitialize.

### FR-06: Case Header Data Extraction
From the modal header, extract: Court Number, Type, Type of Action, Nature of Proceeding, Filing Date, Office, Style of Cause, Language.

### FR-07: Docket Entries Data Extraction
From the "Recorded Entry Information" table, extract all rows with: ID, Date Filed, Office, Recorded Entry Summary.

### FR-08: Database Storage
Store case data in `cases` table and docket entries in `docket_entries` table using UPSERT operations. Update status (success, no_data, failed) and retry counts.

### FR-09: JSON File Backup
Create JSON files in output/json/{year}/ directory with naming pattern IMM-{seq}-{year}-{date}.json containing all extracted data.

### FR-30: Re-run Support
Track case status (pending, success, no_data, failed). On re-run, skip success/no_data cases, retry failed cases, and continue from last pending.

## Success Criteria

- **Startup Success**: Program launches in WSL environment without errors and completes page initialization within 30 seconds
- **Initialization Accuracy**: System correctly selects search tab and Federal Court option in 100% of runs
- **Result Discrimination**: Accurately identifies no-data vs data-available cases with 100% accuracy
- **Data Extraction Completeness**: For cases with data, extracts all header fields and all docket entries with 100% accuracy
- **Storage Integrity**: All extracted data is correctly written to database tables and JSON files with no data loss
- **Error Resilience**: Handles network timeouts and page errors by retrying or skipping, maintaining >99% uptime during normal operation
- **Resume Capability**: On restart, resumes processing from the exact next case number with no duplicates or skips
- **Performance**: Processes at least 100 cases per hour under normal network conditions

## Key Entities

### Case
- case_number (string, primary key): IMM-{seq}-{year}
- case_type (string): e.g., "Immigration Matters"
- type_of_action (string)
- nature_of_proceeding (text)
- filing_date (date)
- office (string): e.g., "Toronto"
- style_of_cause (text)
- language (string)
- status (string): pending/success/no_data/failed
- retry_count (integer)
- error_message (text)
- scraped_at (timestamp)

### Docket Entry
- id (serial, primary key)
- case_number (string, foreign key)
- id_from_table (integer)
- date_filed (date)
- office (string)
- recorded_entry_summary (text)

## Assumptions

- The Federal Court website HTML structure and modal implementation remain stable during the scraping period
- No IP-based blocking occurs during operation with implemented delays
- PostgreSQL database is available and properly configured
- Chrome browser and Selenium WebDriver are installed and compatible
- Network connectivity is stable with occasional timeouts handled by retries
- Case numbers follow the expected format and range
- Modal dialogs load completely within reasonable timeouts

## Dependencies

- Python 3.8+
- Selenium WebDriver
- Chrome browser (headless mode)
- psycopg2-binary for PostgreSQL connection
- PostgreSQL database server
- Linux environment (WSL) with bash shell

## Out of Scope

- Scraping other court types (Federal Court of Appeal, Both)
- Processing non-IMM prefixed case numbers
- Real-time case monitoring or alerts
- Data analysis or reporting beyond storage
- Multi-threading or parallel processing
- Authentication or login requirements
- API integrations beyond database storage

## Open Questions

None identified at this time.