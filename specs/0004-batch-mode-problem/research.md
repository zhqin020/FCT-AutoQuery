```markdown
# Research: Batch retrieve mode — resolved clarifications

## Decision: Safe-stop threshold

- Decision: Make the safe-stop threshold configurable per-run with a default of 500 consecutive `no-record` responses.
- Rationale: 500 is conservative and matches the current working assumption in the spec; making it configurable allows operators to tighten thresholds for sparse datasets without code changes.
- Alternatives considered:
  - Fixed 100: Quicker stop but higher risk of missing far-out valid ids in sparse datasets.
  - Fixed 500: Safer but may cause more wasted probes in extremely sparse cases.

## Decision: Persist raw HTML

- Decision: Persist raw HTML only for failed attempts by default; add a CLI flag to persist raw HTML for all successes when explicitly requested (`--persist-html`).
- Rationale: Storing HTML for failed attempts aids debugging while limiting default storage usage and legal/exposure risk. Operators can enable full persistence when necessary for audits or debugging.
- Alternatives considered:
  - Persist all HTML: Best for debugging but high storage and potential privacy/compliance concerns.
  - Do not persist any HTML: Minimal storage but makes debugging failures harder.

## Probe strategy confirmation

- Decision: Use exponential probing to establish an upper bound (high-water mark), then a conservative backward scan followed by a bounded forward refinement (per the spec's algorithm). Implement configurable maximum probe budget (default 200 probes) to avoid runaway probing.
- Rationale: This balances accuracy and request economy.

## Heuristics for `no-record` vs transient failure

- Decision: Implement deterministic checks for `no-record` signals (page text, missing result table), and treat non-200 responses or timeouts as transient. Provide an override mapping in config for site-specific signals.

## Default CLI flags (recommended)

- `--start N` (default `1`)
- `--max-cases M` (optional)
- `--safe-stop-no-records K` (default `500`)
- `--safe-stop-failures F` (default `100`)
- `--retry-limit R` (default `3`)
- `--delay-min S` and `--delay-max T` (default `1.0` and `3.0` seconds)
- `--persist-html-on-failure` (default enabled)
- `--persist-html-all` (opt-in flag)

## Operational guidance

- Use `--max-cases` together with `--start` for bounded runs. For boundary discovery runs, use probe mode which respects `--probe-budget` to limit probes.
- Add exponential backoff and adaptive sleeping when repeated 429/503 responses are observed.

## Next steps from research

1. Implement the CLI flags and configuration options above.
2. Add unit tests for the probe algorithm using a mocked HTTP server.
3. Add an integration test for the full bounded run using a small test dataset.

```
<!-- end file -->
```