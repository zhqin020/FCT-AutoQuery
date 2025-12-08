# Memory Management Configuration

The Federal Court scraper includes memory management features to help optimize performance during batch processing.

## Configuration Options

Add these settings to your `config.toml` file:

```toml
[app]
# Enable or disable memory management features
enable_memory_management = true

# Number of cases to process before triggering garbage collection
memory_cleanup_interval = 50

# Maximum number of skipped case records to keep in memory
max_skipped_log = 100

# Report skip statistics every N skipped cases
skip_report_interval = 100
```

Or set as environment variables:

```bash
export FCT_ENABLE_MEMORY_MANAGEMENT=true
export FCT_MEMORY_CLEANUP_INTERVAL=50
export FCT_MAX_SKIPPED_LOG=100
export FCT_SKIP_REPORT_INTERVAL=100
```

## Default Values

- `enable_memory_management`: `true` (enabled by default)
- `memory_cleanup_interval`: `50` (trigger GC every 50 cases)
- `max_skipped_log`: `100` (keep only last 100 skipped records)
- `skip_report_interval`: `100` (report stats every 100 skips)

## Skip Record Management

To prevent memory issues during large batch jobs with many skipped cases:

1. **Automatic Truncation**: Only the last N skipped records are kept in memory
2. **Periodic Reporting**: Skip statistics are reported at regular intervals
3. **Memory Optimization**: Skipped records don't accumulate indefinitely

Example log output:
```
2025-01-01 12:00:00 | INFO | Skip statistics: 1500 total cases skipped so far
2025-01-01 12:00:00 | DEBUG | Skipped list truncated to 100 most recent records
2025-01-01 12:30:00 | INFO | 跳过案例总数: 2500
2025-01-01 12:30:00 | INFO | 内存中保留的跳过记录数: 100 (显示最近 100 条)
```

## Memory Management Features

### 1. Automatic Garbage Collection
- Triggers Python's garbage collector at regular intervals during batch processing
- Helps free up memory from no-longer-needed objects
- Configurable interval to balance performance vs. memory usage

### 2. Memory Usage Reporting
- Reports memory usage after batch completion (if `psutil` is installed)
- Helps monitor memory consumption during large batch jobs
- Optional dependency - script works without it

### 3. Memory Cleanup
- Clears processed case objects from memory after batch completion
- Prevents memory leaks during long-running processes
- Cases are already saved to database/JSON files, so clearing is safe

## Installing psutil (Optional)

For memory usage reporting, install psutil:

```bash
pip install psutil
```

Or add to requirements.txt:
```
psutil>=5.8.0
```

## Performance Impact

Memory management adds minimal overhead:
- Garbage collection: ~10-50ms per trigger
- Memory reporting: ~1-5ms (if psutil installed)
- Overall impact: <1% of total processing time

The benefits typically outweigh the costs, especially for:
- Large batch jobs (1000+ cases)
- Long-running processes
- Memory-constrained environments

## When to Disable

Consider disabling memory management if:
- You have very limited CPU resources
- Processing small batches (<100 cases)
- Running in environments where memory is abundant
- You prefer to manage memory manually

Disable with:
```toml
[app]
enable_memory_management = false
```

## Monitoring

When enabled, memory management logs:
- Garbage collection triggers and results
- Memory usage statistics (if psutil available)
- Cleanup completion status

Example log output:
```
2025-01-01 12:00:00 | DEBUG | Memory management: Garbage collection triggered after 50 cases: 1234 objects collected
2025-01-01 12:30:00 | INFO  | Memory management: Garbage collection completed: 5678 objects collected
2025-01-01 12:30:00 | INFO  | Memory management: Memory usage after cleanup: 245.67 MB
2025-01-01 12:30:00 | INFO  | Memory management: Clearing 1500 case objects from memory
```