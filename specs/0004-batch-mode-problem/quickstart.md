```markdown
# Quickstart: Batch retrieve mode

Prerequisites:

- Python 3.12 (project default) inside conda env `fct`
- run `conda activate fct` in any terminal
- `pip install -r requirements.txt` from repo root

Run a short bounded batch (example):

```
python -m src.cli.main batch --year 23 --start 30 --max-cases 50 --safe-stop-no-records 500
```

Probe upper bound for a year (example):

```
python -m src.cli.main probe --year 25 --probe-budget 200
```

Notes:

- For debugging, enable `--persist-html-on-failure` to capture raw HTML for failed attempts.
- Use `--dry-run` to validate configuration without issuing network requests.

```
<!-- end file -->
```