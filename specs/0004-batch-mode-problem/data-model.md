# Data Model: Batch Job & Checkpoint

## Job record (in-memory / persisted)
- `job_id` (string): unique job id (e.g., uuid4).
- `url` (string): target URL to scrape.
- `params` (object): job-specific parameters (e.g., selectors, max_depth).
- `state` (enum): one of `pending`, `running`, `succeeded`, `failed`.
- `attempts` (int): number of attempts made so far.
- `last_error` (object|null): last error object with `type`, `message`, `ts`.
- `created_at` (iso8601): timestamp.

Example JSON:
{
  "job_id": "6f1d7b7a-...",
  "url": "https://example.example/case/123",
  "params": {"timeout": 60},
  "state": "pending",
  "attempts": 0,
  "last_error": null,
  "created_at": "2025-11-28T08:00:00Z"
}

## Checkpoint file (run-level snapshot)
- `run_id` (string): unique run id.
- `cursor` (object): pointer showing processed job index or last job id.
- `jobs` (list of job summaries): each with `job_id`, `state`, `attempts`, `last_error`.
- `worker_state` (optional): small metadata to resume open worker (if needed).
- `updated_at` (iso8601)

Example:
{
  "run_id": "run-2025-11-28T08:00:00Z",
  "cursor": {"last_job_id": "6f1d7b7a-..."},
  "jobs": [
    {"job_id":"6f1d7b7a-...","state":"succeeded","attempts":1}
  ],
  "updated_at":"2025-11-28T08:12:00Z"
}

## Storage & Atomicity
- Write checkpoint to a temp file `checkpoint.json.tmp` then rename `checkpoint.json` (atomic on POSIX).
- Use `fsync` where possible before rename to reduce risk of partial writes.

## Checkpoint resume semantics
- Checkpoints are the authoritative run snapshot and MUST be written atomically using the temp-file-then-rename pattern. Implementations MUST follow this sequence: write to `checkpoint.json.tmp`, `fsync` the file, then `rename` to `checkpoint.json`.
- Resume semantics: on startup, the runner MUST read the latest checkpoint and resume from the `cursor` value. The runner MUST treat any job marked `succeeded` as completed and MUST NOT re-run it. Jobs with state `running` at checkpoint-time SHOULD be considered `pending` on resume (increment `attempts` before retrying) to avoid lost work or double-processing.
- Checkpoint granularity: prefer per-job summaries in the `jobs` array (one entry per job_id) and maintain a light-weight `cursor` for fast forward progress (e.g., `last_job_index` or `last_job_id`). Implementations MUST ensure the `jobs` list and `cursor` remain consistent in the same checkpoint file.
- Concurrency: if multiple runner processes may touch the same checkpoint location, implement a lock (file-lock or coordinating storage) or use distinct run-specific checkpoint directories (`output/checkpoints/<run_id>/`) to avoid races. Document chosen strategy in the plan.


## Schema Evolution
- Add `schema_version` at top-level for forward/backwards compatibility.

## Acceptance Criteria
- Checkpoint read/write round-trips under unit test.
- Resuming from checkpoint continues from `cursor.last_job_id` and does not re-run `succeeded` jobs.
```markdown
# Data Model: Batch retrieve mode

## Entities

- **CaseIdentifier**
  - `id` (string): canonical case string, e.g., `IMM-231-25`
  - `year` (string): two-digit year suffix, e.g., `25`
  - `number` (integer): numeric case id, e.g., `231`

- **CrawlResult**
  - `case_identifier` (CaseIdentifier)
  - `outcome` (enum): `success`, `no-record`, `failed`
  - `attempts` (int)
  - `last_error` (string|null)
  - `saved_path` (string|null) — path to stored record if `success`
  - `html_snapshot` (string|null) — path to saved raw HTML when persisted
  - `timestamp` (ISO8601)

- **CrawlStats**
  - `start_id` (CaseIdentifier or integer)
  - `end_id` (CaseIdentifier or integer)
  - `total_attempted` (int)
  - `success_count` (int)
  - `no_record_count` (int)
  - `failed_count` (int)

## Storage

- Audit outputs: write per-run `audit_{YYYYMMDD_HHMMSS}.json` and optional `attempts_{...}.ndjson` in `output/` (consistent with existing outputs).
- Persist successful parsed records in existing storage format (reuse repository APIs under `src/`), do not duplicate storage layout.

## Validation rules

- `CaseIdentifier.number` must be >= 0 and <= 99999
- `year` must be two digits
- `attempts` >= 1

```
<!-- end file -->
```