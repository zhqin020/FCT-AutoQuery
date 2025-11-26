```markdown
# CaseRecord JSON Schema (canonical)

This document defines the canonical JSON keys and types used for per-case exports.

Required fields:
- `case_number` (string) — canonical case identifier, e.g. `IMM-12345-25`
- `style_of_cause` (string | null)
- `nature_of_proceeding` (string | null)
- `parties` (array of objects) — each party: `{ "name": string, "role": string, "representation": string|null }`
- `details` (string | null) — structured summary or HTML snippet reference
- `scrape_timestamp` (string, ISO 8601, timezone-aware) — e.g. `2025-11-25T12:34:56Z`
- `source_url` (string | null)
- `file_path` (string) — relative path to the saved JSON file

Optional fields:
- `filing_date` (string, ISO date) — if available
- `language` (string) — language token, lowercased (`"english"|"french"`)

Filename convention:
- `<case-number>-<YYYYMMDD>.json` (if conflict: `<case-number>-<YYYYMMDD>-<n>.json` where `n` is a numeric suffix)

Notes:
- Field name canonicalization: use `nature_of_proceeding` (not `nature_of_processing`) — align code and tests to this key.
```
