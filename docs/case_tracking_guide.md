# Case Tracking System Guide

## Overview

The Case Tracking System provides database-based tracking of case processing history, replacing the reliance on分散的NDJSON files. This enables better querying, analysis, and management of case processing history.

## Features

### 1. Database Tables

- **`case_processing_history`**: Detailed history of each case processing attempt
- **`processing_runs`**: Metadata for each processing run/session
- **`case_status_snapshot`**: Current status and statistics for each case
- **`probe_state`**: Persistent probe state to avoid redundant checks

### 2. Key Capabilities

- **Historical Tracking**: Complete processing history for each case
- **Smart Skipping**: Skip cases based on processing history and success rates
- **Run Management**: Track processing runs with statistics and metadata
- **Probe Persistence**: Save probe state between runs to avoid redundant checks
- **Query Interface**: Easy querying of case history and run statistics

## Migration Steps

### Step 1: Set Up Database Schema

```bash
# Run the migration script
python scripts/migrate_tracking_schema.py
```

This creates the necessary tables in your database.

### Step 2: Migrate Existing NDJSON Data (Optional)

```bash
# Dry run to see what would be migrated
python scripts/migrate_ndjson_to_db.py --dry-run

# Actual migration
python scripts/migrate_ndjson_to_db.py

# Migrate only recent data
python scripts/migrate_ndjson_to_db.py --since 2025-11-01
```

### Step 3: Update Code Integration

#### Basic Usage

```python
from src.services.case_tracking_service import CaseTrackingService
from src.cli.tracking_integration import TrackingIntegration

# Initialize tracking
tracker = CaseTrackingService()
run_id = tracker.start_run(mode='batch', parameters={'year': 2025})

# Create tracking integration
tracking = TrackingIntegration(tracker, run_id)

# Check if case should be skipped
should_skip, reason = tracking.check_should_skip('IMM-1-25')
if should_skip:
    print(f"Skipping: {reason}")

# Track case processing
started_at = tracking.start_case_processing('IMM-1-25', 'single')
try:
    case = scraper.scrape_case('IMM-1-25')
    if case:
        tracking.track_successful_scrape(case, started_at)
    else:
        tracking.track_failed_scrape('IMM-1-25', started_at)
except Exception as e:
    tracking.track_error_case('IMM-1-25', str(e), started_at)

# Finish run
tracker.finish_run(run_id, 'completed')
```

#### Batch Processing Integration

```python
# Enhanced batch processing with tracking
def scrape_batch_with_tracking(year, start=None, max_cases=None):
    # Start tracking run
    run_id = tracker.start_run(
        mode='batch',
        parameters={'year': year, 'start': start, 'max_cases': max_cases}
    )
    
    tracking = TrackingIntegration(tracker, run_id)
    
    try:
        # Process cases with tracking
        for case_num in range(start, end):
            court_file_no = f"IMM-{case_num}-{year % 100:02d}"
            
            # Check if should skip
            should_skip, reason = tracking.check_should_skip(court_file_no)
            if should_skip:
                continue
            
            # Process case
            started_at = tracking.start_case_processing(court_file_no, 'batch')
            case = process_case(court_file_no)
            
            if case:
                tracking.track_successful_scrape(case, started_at, 'batch')
            else:
                tracking.track_failed_scrape(court_file_no, started_at, 'batch')
    
    finally:
        tracker.finish_run(run_id, 'completed')
```

## Query Examples

### Get Case History

```python
# Get processing history for a specific case
history = tracker.get_case_history('IMM-1-25', limit=10)
for record in history:
    print(f"{record['started_at']}: {record['outcome']} ({record['scrape_mode']})")

# Get current case status
status = tracker.get_case_status('IMM-1-25')
if status:
    print(f"Last outcome: {status['last_outcome']}")
    print(f"Consecutive failures: {status['consecutive_failures']}")
```

### Get Run Statistics

```python
# Get recent runs
runs = tracker.get_recent_runs(days=7)
for run in runs:
    print(f"{run['run_id']}: {run['total_cases']} cases, "
          f"{run['success_count']} success, {run['failed_count']} failed")
```

### Check Skip Logic

```python
# Check if a case should be skipped
should_skip, reason = tracker.should_skip_case('IMM-1-25')
if should_skip:
    print(f"Should skip: {reason}")
```

## Configuration

### Environment Variables

```bash
# Enable/disable tracking
FCT_ENABLE_TRACKING=true

# Configure skip logic
FCT_MAX_CONSECUTIVE_FAILURES=5
FCT_SKIP_RECENT_DAYS=7

# Configure probe state persistence
FCT_PERSIST_PROBE_STATE=true
FCT_PROBE_STATE_FILE=output/probe_state.json
```

### Database Configuration

The tracking system uses the same database configuration as the main application:

```toml
[database]
host = "localhost"
port = 5432
database = "fct_autoquery"
user = "your_username"
password = "your_password"
```

## Benefits Over NDJSON

### 1. Centralized Data
- All tracking data in one place
- Easy to query and analyze
- No scattered files

### 2. Rich Metadata
- Run-level statistics
- Case processing history
- Performance metrics

### 3. Smart Decision Making
- Skip cases based on history
- Avoid redundant processing
- Track failure patterns

### 4. Better Analytics
- Success rates over time
- Processing performance trends
- Error pattern analysis

## Maintenance

### Cleanup Old Records

```python
# Clean up records older than 90 days
tracker.cleanup_old_records(days_to_keep=90)
```

### Monitoring

Monitor tracking table sizes:

```sql
-- Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname = 'public' 
    AND tablename LIKE '%processing%' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## Troubleshooting

### Common Issues

1. **Migration fails**: Check database connection and permissions
2. **Missing data**: Verify NDJSON files are correctly formatted
3. **Performance**: Add indexes on frequently queried columns
4. **Storage**: Regular cleanup of old records

### Debug Queries

```sql
-- Check recent runs
SELECT * FROM processing_runs 
ORDER BY started_at DESC 
LIMIT 10;

-- Check case processing history
SELECT * FROM case_processing_history 
WHERE court_file_no = 'IMM-1-25'
ORDER BY started_at DESC;

-- Check case status snapshot
SELECT * FROM case_status_snapshot 
WHERE court_file_no = 'IMM-1-25';
```

## API Reference

### CaseTrackingService

#### Methods

- `start_run(mode, parameters, metadata) -> str`
- `finish_run(run_id, status)`
- `record_case_processing(court_file_no, run_id, outcome, ...)`
- `get_case_history(court_file_no, limit) -> List[Dict]`
- `get_case_status(court_file_no) -> Optional[Dict]`
- `should_skip_case(court_file_no, force, max_consecutive_failures) -> Tuple[bool, str]`
- `record_probe_state(case_number, year_part, exists, run_id)`
- `get_probe_state(case_number, year_part) -> Optional[Dict]`
- `get_recent_runs(days, limit) -> List[Dict]`
- `cleanup_old_records(days_to_keep)`

### TrackingIntegration

#### Methods

- `start_case_processing(court_file_no, scrape_mode) -> datetime`
- `record_case_result(court_file_no, outcome, started_at, ...)`
- `check_should_skip(court_file_no, force) -> Tuple[bool, str]`
- `track_successful_scrape(case, started_at, scrape_mode)`
- `track_failed_scrape(court_file_no, started_at, error, scrape_mode)`
- `track_skipped_case(court_file_no, reason)`
- `track_error_case(court_file_no, error, started_at)`

## Migration Timeline

1. **Phase 1**: Set up database schema (immediate)
2. **Phase 2**: Migrate existing NDJSON data (optional, immediate)
3. **Phase 3**: Update batch processing code (next release)
4. **Phase 4**: Deprecate NDJSON logging (future release)
5. **Phase 5**: Remove NDJSON dependencies (future release)

## Support

For issues or questions about the tracking system:

1. Check the logs: `logs/migration.log`, `logs/ndjson_migration.log`
2. Verify database connectivity
3. Check table permissions
4. Review the troubleshooting section above