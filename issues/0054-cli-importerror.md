# Issue: CLI ImportError (attempted relative import with no known parent package)

## Description
When running `python src/fct_analysis/cli.py --help`, an `ImportError` occurs:
`ImportError: attempted relative import with no known parent package`

This is because `cli.py` uses relative imports (e.g., `from . import parser as _parser`), which are not supported when a script is executed directly by Python.

## Reproduction Steps
1. Navigate to the project root.
2. Activate the virtual environment: `conda activate fct`
3. Run: `python src/fct_analysis/cli.py --help`

## Expected Behavior
The help message should be displayed.

## Current Status
Closed

## Resolution
Modified `src/fct_analysis/cli.py` to:
1. Automatically add the source root (two levels up from the file) to `sys.path` when executed as a script.
2. Use a `try-except` block to attempt relative imports first (for module execution) and fallback to absolute imports (for direct script execution).
3. These changes allow both `python src/fct_analysis/cli.py` and `python -m src.fct_analysis.cli` to work correctly.

## Related Files
- `src/fct_analysis/cli.py`


## Owner
Antigravity

## Expected Fix Time
2026-03-25
