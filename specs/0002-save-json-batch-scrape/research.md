# Research: Save JSON Files & Batch Scrape Optimization (Phase 0)

This document records the research decisions and findings required to implement
per-case JSON persistence and safe browser session reuse for batch scraping.

## Goals

1. Decide a safe, atomic write strategy for per-case JSON files that avoids
   partial/write-corruption and supports retries.
2. Choose filename sanitization and unique-suffix policy to avoid accidental
   overwrites in same-day runs.
3. Define retry/backoff defaults for write operations.
4. Identify a WebDriver lifecycle and session-reuse pattern that is robust and
   recoverable.

## Findings & Decisions

1. Atomic write strategy

   - Decision: Use Python's `tempfile.mkstemp()` (or `NamedTemporaryFile(delete=False)`) to
     write the JSON content into a same-directory temporary file, then call
     `os.replace(temp_path, final_path)` to atomically move it into place.
   - Rationale: `os.replace` is atomic on POSIX when source and target are on
     the same filesystem; `mkstemp` ensures we get a safe temporary filename
     and avoids TOCTOU race conditions.
   - Edge cases: If the final directory does not exist, create it with
     `os.makedirs(..., exist_ok=True)` before mkstemp. Ensure permissions are
     correct and handle disk-full / permission errors explicitly.

2. Filename sanitization and uniqueness

   - Decision: Build filenames using `<case_number>-<YYYYMMDD>.json`, where
     `case_number` is sanitized by replacing unsafe characters with `-` and
     collapsing repeated `-` characters. If the target filename already
     exists, append a numeric suffix `-1`, `-2`, ... until an unused name is
     found (limit e.g. 100 tries before failing).
   - Rationale: Human-readable filenames are preferred for operators; suffix
     approach avoids overwriting earlier successful runs in the same day.

3. Retry & backoff policy for writes

   - Decision: Default to 3 write attempts with exponential backoff starting
     at 1 second (1s, 2s, 4s). Make both `retries` and `base_backoff_seconds`
     configurable via `src/lib/config.py` and `config.example.toml` keys
     `app.export_write_retries` and `app.export_write_backoff_seconds`.
   - Rationale: Handles transient filesystem/IO hiccups and reduces noise for
     occasional transient issues.

4. WebDriver/session reuse strategy

   - Decision: Maintain a single WebDriver instance per batch run. Provide a
     `BatchRunner` (or adapt existing CLI) that creates the driver once,
     processes case numbers sequentially, and performs per-case cleanup
     (closing modals, clearing inputs) between cases. Expose a `shutdown()`
     method that gracefully quits the driver at the end of the run or on
     unrecoverable errors.
   - Failure handling: On per-case unrecoverable errors (e.g., DOM changed,
     driver crash), attempt a soft restart of the driver up to N times (config
     option `app.max_driver_restarts` default 1) before aborting the batch.

5. Tests to add

   - Unit tests for `export_case_to_json`:
     - Verify file is created with correct contents and path.
     - Verify atomic write semantics (use temp dir and simulate partial writes).
     - Verify uniqueness suffixing behavior.
     - Verify retry/backoff logic (simulate mkstemp or os.replace failures).

   - Integration/smoke test for batch runner:
     - Simulate or run a short batch (e.g., 10 case numbers) verifying the
       WebDriver process id remains the same across cases and per-case JSONs
       are written.

6. Configuration changes

   - Add to `config.example.toml` (and read from private config or env):

     ```toml
     [app]
     per_case_subdir = "json"
     export_write_retries = 3
     export_write_backoff_seconds = 1
     max_driver_restarts = 1
     output_dir = "output"
     ```

7. CLI/UX considerations

   - Provide a `--dry-run` flag for the batch runner to validate flow without
     writing files.
   - Provide a `--force-overwrite` flag to allow overwriting existing files if
     operator explicitly requests.

## Unresolved / NEEDS CLARIFICATION

- Concurrency model: current plan assumes single-instance batch runs (default
  `max concurrent browser instances = 1`). If concurrent runs are required we
  must document coordination/locking for the output directory (outside this
  feature scope).
- Error reporting: decide whether failed per-case writes should mark the
  entire run as partially failed or be retriable-only. Plan defaults to
  marking case as failed and continuing the batch after configured retries.

## Example pseudocode for export flow

```py
def export_case_to_json(case_dict, output_root, retries=3, backoff=1):
    year = datetime.utcnow().strftime("%Y")
    dir_path = Path(output_root) / 'json' / year
    dir_path.mkdir(parents=True, exist_ok=True)
    base_name = sanitize(case_dict['case_number']) + '-' + datetime.utcnow().strftime('%Y%m%d')
    final_path = dir_path / f"{base_name}.json"
    final_path = unique_with_suffix(final_path)

    for attempt in range(1, retries+1):
        try:
            fd, tmp = mkstemp(dir=str(dir_path))
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(case_dict, f, ensure_ascii=False, indent=2)
            os.replace(tmp, final_path)
            return str(final_path)
        except OSError:
            if attempt == retries:
                raise
            sleep(backoff * (2 ** (attempt-1)))
```

## Commands to run locally (examples)

Run unit tests (from repo root, requires `fct` env):

```bash
./scripts/run-in-fct.sh pytest -q tests/test_export_service.py
```

Run batch (example):

```bash
./scripts/run-in-fct.sh python -m src.cli.main batch 2025 --max-cases 20
```

## Conclusion

Research resolves the main technical unknowns: atomic writes, filename
uniqueness, retry/backoff policy, and a robust WebDriver reuse pattern. Next
step is to author `data-model.md` and implement `export_case_to_json` and the
batch-runner changes with unit tests.
