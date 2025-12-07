# Quick Start Guide: Federal Court Case Scraper

## Prerequisites

- Python 3.11+
- PostgreSQL database
- Conda environment (fct)

## Environment Setup

1. Activate the conda environment:
   ```bash
   conda activate fct
   ```

2. Install dependencies (if not already installed):
   ```bash
   pip install -r requirements.txt
   ```

## Database Setup

1. Create PostgreSQL database and user as configured in `config.toml` or environment variables.

2. Run the database schema:
   ```bash
   psql -h <host> -U <user> -d <database> -f src/lib/database_schema.sql
   ```

## Configuration

Configure the scraper in `config.toml` (recommended) or environment variables:

```toml
[app]
rate_limit_seconds = 1.0
max_retries = 3
timeout_seconds = 30
output_dir = "output"
json_filename = "cases.json"
export_json_only = true
headless = true
browser = "chrome"

[database]
host = "localhost"
port = 5432
name = "fct_db"
user = "fct_user"
password = "fctpass"
```

## Running the Scraper

### Basic Run
```bash
python -m src.cli.main
```

### Simplified Version
```bash
python src/cli/main_simplified.py
```

### With Custom Configuration
```bash
FCT_OUTPUT_DIR="/custom/path" python -m src.cli.main
```

## Monitoring Progress

- Check logs in `logs/scraper-1.log`
- Monitor database for case status updates
- JSON files created in `output/json/{year}/`

## Resume and Re-run

The scraper automatically resumes from the last processed case. To re-run failed cases:

```bash
python src/cli/tracking_integration.py
```

## Troubleshooting

- **Browser issues**: Ensure Chrome/Chromium is installed
- **Database connection**: Verify PostgreSQL is running and credentials are correct
- **Rate limiting**: Adjust `rate_limit_seconds` if blocked
- **Network timeouts**: Increase `timeout_seconds` for slow connections

## Output

- Database tables: `cases` and `docket_entries`
- JSON backups: `output/json/{year}/IMM-{seq}-{year}-{date}.json`