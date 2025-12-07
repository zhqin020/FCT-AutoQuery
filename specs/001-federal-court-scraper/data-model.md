# Data Model

## Entities

### Case
Represents a Federal Court case with header information and processing status.

**Fields:**
- `case_number` (string, primary key): Format IMM-{sequence}-{year} (e.g., IMM-1-21)
- `case_type` (string): Type of case (e.g., "Immigration Matters")
- `type_of_action` (string): Legal action type
- `nature_of_proceeding` (text): Description of proceeding nature
- `filing_date` (date): When the case was filed
- `office` (string): Court office location (e.g., "Toronto")
- `style_of_cause` (text): Case style description
- `language` (string): Case language
- `status` (string): Processing status - one of: 'pending', 'success', 'no_data', 'failed'
- `retry_count` (integer): Number of retry attempts (default 0)
- `error_message` (text): Last error message if failed
- `scraped_at` (timestamp): When the case was last scraped

**Validation Rules:**
- `case_number` must match pattern `IMM-\d+-\d{2}`
- `status` must be one of the allowed values
- `retry_count` >= 0
- `filing_date` must be valid date if present

**Relationships:**
- One-to-many with DocketEntry (via case_number)

**State Transitions:**
- `pending` → `success` (when data extracted successfully)
- `pending` → `no_data` (when "No data available" shown)
- `pending` → `failed` (on error after retries)
- `failed` → `pending` (on re-run if retry conditions met)

### DocketEntry
Represents individual docket entries within a case.

**Fields:**
- `id` (serial, primary key): Auto-incrementing ID
- `case_number` (string, foreign key): References Case.case_number
- `entry_id` (string): ID from the docket table
- `date_filed` (date): When the entry was filed
- `office` (string): Office that filed the entry
- `recorded_entry_summary` (text): Summary of the recorded entry

**Validation Rules:**
- `case_number` must exist in Case table
- `entry_id` must be unique per case
- `date_filed` must be valid date if present

**Relationships:**
- Many-to-one with Case (via case_number)

## Database Schema

```sql
-- Cases table
CREATE TABLE cases (
    case_number VARCHAR PRIMARY KEY,
    case_type VARCHAR,
    type_of_action VARCHAR,
    nature_of_proceeding TEXT,
    filing_date DATE,
    office VARCHAR,
    style_of_cause TEXT,
    language VARCHAR,
    status VARCHAR CHECK (status IN ('pending', 'success', 'no_data', 'failed')),
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    scraped_at TIMESTAMP
);

-- Docket entries table
CREATE TABLE docket_entries (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR REFERENCES cases(case_number),
    entry_id VARCHAR,
    date_filed DATE,
    office VARCHAR,
    recorded_entry_summary TEXT,
    UNIQUE(case_number, entry_id)
);
```

## Indexes

- Primary key indexes on cases.case_number and docket_entries.id
- Foreign key index on docket_entries.case_number
- Status index on cases.status for efficient querying
- Composite index on (case_number, entry_id) for uniqueness