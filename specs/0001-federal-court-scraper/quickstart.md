# Quick Start: Federal Court Case Scraper

**Date**: 2025-11-20
**Purpose**: Get the case scraper running quickly for development and testing

## Prerequisites

- Python 3.11+
- Chrome browser
- Linux/WSL environment

## Installation

1. **Clone and setup**:
   ```bash
   git clone <repo>
   cd FCT-AutoQuery
   git checkout 0001-federal-court-scraper
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/WSL
   ```

3. **Install dependencies**:
   ```bash
   pip install selenium pandas loguru
   ```

## Running the Scraper

### Basic Usage
```bash
python -m src.cli.scraper --year 2023 --output-dir ./output
```

### Multiple Years
```bash
python -m src.cli.scraper --years 2023 2024 2025 --output-dir ./output
```

### Test Mode (Limited)
```bash
python -m src.cli.scraper --year 2023 --max-judgments 5 --output-dir ./output
```

## Parameters

- `--year`, `--years`: Specific year(s) to scrape (2023-2025 and ongoing)
- `--output-dir`: Directory for CSV/JSON output
- `--max-cases`: Limit number of cases for testing
- `--headless`: Run in headless mode (default: true)

## Expected Output

- `cases.csv`: All scraped cases in CSV format
- `cases.json`: All scraped cases in JSON format
- Logs showing progress and any errors

## Important Notes

**Ethical Scraping**:
- Exactly 1-second delay between page accesses
- Only accesses public case pages
- Never accesses E-Filing or non-public content
- Only processes IMM- case numbers

**Legal Compliance**:
- All data is public court information
- No access to restricted systems
- Maintains audit trail of all accesses

## Troubleshooting

**ChromeDriver issues**:
```bash
# Install ChromeDriver
wget https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip
unzip chromedriver_linux64.zip
sudo mv chromedriver /usr/local/bin/
```

**Network issues**:
- Check internet connectivity
- Verify case URLs are accessible
- Scraper will log and continue on individual failures

**Data issues**:
- Ensure output directory is writable
- Check logs for validation errors
- Verify CSV/JSON files are properly formatted

## Development

Run tests:
```bash
pytest tests/
```

Check coverage:
```bash
pytest --cov=src tests/
```