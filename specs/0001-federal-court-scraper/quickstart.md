# Quickstart: Federal Court Case Scraper

**Date**: 2025-11-22  
**Phase**: 1 (Design & Contracts)  
**Status**: Complete

## Overview

This guide provides step-by-step instructions to set up and run the Federal Court case scraper. The scraper automates searching for cases using the website's search form and extracts case information and docket entries.

## Prerequisites

- Python 3.11+
- PostgreSQL database
- Chrome browser installed
- Conda environment `fct` activated

## Setup

1. **Activate environment**:
   ```bash
   conda activate fct
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up database**:
   ```bash
   python scripts/init_database.py
   ```

4. **Configure database connection**:
   Update `src/lib/config.py` with your PostgreSQL credentials.

## Running the Scraper

### Basic Usage

Run the scraper from the project root:

```bash
python -m src.cli.main
```

This will:
- Start from case IMM-1-20
- Process cases sequentially
- Store data in PostgreSQL
- Export to JSON files in `./data/`

### Command Line Options

```bash
python -m src.cli.main --help
```

Available options:
- `--start-year`: Starting year (default: 20)
- `--end-year`: Ending year (default: 25)
- `--start-number`: Starting case number (default: 1)
- `--end-number`: Ending case number (default: 99999)
- `--output-dir`: Output directory for JSON files (default: ./data)
- `--resume`: Resume from last processed case (default: true)

### Examples

**Scrape specific year range**:
```bash
python -m src.cli.main --start-year 22 --end-year 23
```

**Resume from specific case**:
```bash
python -m src.cli.main --start-number 5000 --start-year 22
```

**Custom output directory**:
```bash
python -m src.cli.main --output-dir /path/to/output
```

## Monitoring Progress

The scraper provides real-time logging:
- Access attempts and results
- Extraction success/failure
- Database operations
- Rate limiting status

Logs are written to console and `logs/scraper.log`.

## Output

### Database Tables

- `cases`: Case header information
- `docket_entries`: Process history records

### JSON Files

Files are created in `./data/{YEAR}/{CASE_ID}.json` format:

```json
{
  "url": "https://www.fct-cf.ca/...",
  "court_file_no": "IMM-12345-25",
  "case_type": "Immigration Matters",
  "type_of_action": "Application for Judicial Review",
  "nature_of_proceeding": "Long description...",
  "filing_date": "2025-01-15",
  "office": "Toronto",
  "style_of_cause": "Applicant v Respondent",
  "language": "English",
  "html_content": "<div>...</div>",
  "scraped_at": "2025-11-22T10:00:00Z",
  "docket_entries": [
    {
      "id_from_table": 1,
      "date_filed": "2025-01-20",
      "office": "Toronto",
      "recorded_entry_summary": "Entry summary..."
    }
  ]
}
```

## Troubleshooting

### Common Issues

**Chrome WebDriver not found**:
- Ensure Chrome browser is installed
- WebDriver is managed automatically by selenium-manager

**Database connection failed**:
- Check PostgreSQL is running
- Verify credentials in `config.py`

**No cases found**:
- Check network connectivity
- Verify website is accessible
- Review logs for error details

**Rate limiting errors**:
- The scraper implements automatic delays
- If blocked, wait and retry later

### Logs and Debugging

Check `logs/scraper.log` for detailed error information. Enable debug logging by setting environment variable:

```bash
LOG_LEVEL=DEBUG python -m src.cli.main
```

## Performance

- Processes ~100 cases per hour with implemented delays
- Handles up to 100,000+ cases with resume capability
- Stores data efficiently with UPSERT operations

## Safety

- Respects website terms and robots.txt
- Implements ethical scraping delays
- Only accesses public case information
- Includes circuit breaker for reliability