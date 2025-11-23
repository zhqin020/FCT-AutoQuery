# Data Model: Federal Court Case Scraper

**Date**: 2025-11-22
**Purpose**: Define data entities for scraped public cases based on web page fields

## Entities

### Case
Represents a scraped public case with header information from the modal.

**Attributes**:
- `case_id` (string, unique identifier): Court File No. (e.g., IMM-12345-25)
- `case_type` (string): Type (e.g., Immigration Matters)
- `action_type` (string): Type of Action
- `nature_of_proceeding` (text): Nature of Proceeding (long text)
- `filing_date` (date): Filing Date
- `office` (string): Office (e.g., Toronto)
- `style_of_cause` (text): Style of Cause (long text, parties)
- `language` (string): Language
- `scraped_at` (timestamp): When data was collected

**Relationships**:
- One-to-many with DocketEntry (via case_id)

**Validation Rules**:
- `case_id` must contain "IMM-"
- `filing_date` must be within 2020-2025
- `scraped_at` defaults to current timestamp

**Business Rules**:
- Each case must have unique `case_id`
- Only IMM cases are processed
- All header fields extracted from modal

### DocketEntry
Represents individual recorded entries from the docket table.

**Attributes**:
- `id` (serial, primary key): Auto-incrementing ID
- `case_id` (string, foreign key): References Case.case_id
- `doc_id` (integer): ID (sequence number from table)
- `entry_date` (date): Date Filed
- `entry_office` (string): Office (submission location)
- `summary` (text): Recorded Entry Summary

**Relationships**:
- Many-to-one with Case (via case_id)

**Validation Rules**:
- `case_id` must exist in cases table
- Unique constraint on (case_id, doc_id) to prevent duplicates

**Business Rules**:
- All entries for a case collected from Recorded Entries table
- Summary contains full text content

## Data Flow

1. **Search**: Generate case numbers and submit search forms
2. **Detection**: Check for results or "No data available"
3. **Modal Extraction**: Click "More", extract header fields and docket table
4. **Storage**: Insert/update cases and docket_entries with UPSERT
5. **Export**: Generate JSON files per case

## Export Formats

### JSON Format (per case)
```json
{
  "case_id": "IMM-12345-25",
  "case_type": "Immigration Matters",
  "action_type": "Application for Judicial Review",
  "nature_of_proceeding": "Long description text...",
  "filing_date": "2025-01-15",
  "office": "Toronto",
  "style_of_cause": "Applicant v Respondent",
  "language": "English",
  "scraped_at": "2025-11-22T10:00:00Z",
  "docket_entries": [
    {
      "doc_id": 1,
      "entry_date": "2025-01-20",
      "entry_office": "Toronto",
      "summary": "Entry summary text..."
    }
  ]
}
```

## Performance Considerations

- Batch database operations for efficiency
- Index on case_id for fast lookups
- Handle large text fields appropriately
- Process cases sequentially with rate limiting