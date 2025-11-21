# Data Model: Federal Court Case Scraper

**Date**: 2025-11-20
**Purpose**: Define data entities for scraped public cases

## Entities

### Case
Represents a scraped public case with metadata and HTML content.

**Attributes**:
- `case_id` (string, unique identifier): URL or generated ID for the case
- `case_number` (string): Case number containing "IMM-"
- `title` (string): Case title
- `court` (string): Court name (Federal Court)
- `date` (date): Case date
- `html_content` (text): Full HTML content of the case
- `scraped_at` (timestamp): When data was collected

**Validation Rules**:
- `case_number` must contain "IMM-"
- `html_content` cannot be empty
- `date` must be within 2023-2025 or ongoing
- `scraped_at` defaults to current timestamp

**Business Rules**:
- Each case must have unique `case_id`
- Only IMM cases are processed
- HTML content preserved as-is for analysis

## Data Flow

1. **Discovery**: Scraper finds case URLs from public lists
2. **Filtering**: Only IMM case cases are selected
3. **Scraping**: HTML content extracted with 1-second intervals
4. **Validation**: Data validated before export
5. **Export**: Data written to CSV and JSON formats

## Export Formats

### CSV Format
- One row per case
- Columns: case_id, case_number, title, court, date, html_content, scraped_at
- HTML content properly escaped

### JSON Format
- One object per case
- Structure matches CSV columns
- HTML content as string

## Performance Considerations

- Process cases sequentially with 1-second delays
- No database storage - direct file export
- Memory usage scales with case size
- Handle large HTML content efficiently