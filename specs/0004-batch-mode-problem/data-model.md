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