# Audit schema and NDJSON format

This file documents the minimal audit JSON and NDJSON formats produced by the batch retrieval runs.

1) Summary JSON (`output/audit_<run>.json`)

```json
{
  "run_id": "<uuid>",
  "start_id": 30,
  "end_id": 60,
  "total_attempted": 31,
  "success_count": 25,
  "no_record_count": 5,
  "failed_count": 1,
  "started_at": "2025-11-28T12:00:00Z",
  "finished_at": "2025-11-28T12:10:00Z"
}
```

2) Per-attempt NDJSON (`output/attempts_<run>.ndjson`)

Each line is a JSON object describing a single attempt for a case id. Example line:

```json
{"run_id":"<uuid>","case_id":"IMM-30-25","attempt":1,"outcome":"no-record","status_code":200,"timestamp":"2025-11-28T12:00:01Z","html_path":null}
```

Field definitions:
- `run_id`: string UUID for the run
- `case_id`: string (e.g., `IMM-30-25`)
- `attempt`: integer attempt number (1..N)
- `outcome`: one of `["success","no-record","failed"]`
- `status_code`: HTTP status code if applicable, or null
- `timestamp`: ISO-8601 UTC timestamp
- `error`: optional string with exception/message when `outcome` == `failed`
- `html_path`: optional path to persisted HTML (failure-only by default)

3) Storage locations
- Summary JSON: `output/audit_<run>.json`
- Attempts NDJSON: `output/attempts_<run>.ndjson`
- Failed HTML (default): `output/html_failed/<run>/<case_id>.html`

4) Validation
Add unit tests that validate the summary totals and that NDJSON lines parse and are consistent (sum of outcomes equals total attempts per-run aggregated appropriately).
