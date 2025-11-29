# Issue 0004: Batch retrieve mode — safe probing and robust scraping fallbacks

## Summary

Implement safe, efficient batch retrieval for `IMM-<number>-<yy>` case ids with:
- a probe mode to detect an upper bound (high-water mark) with low request budgets,
- a bounded traversal that classifies outcomes (`success`, `no-record`, `failed`),
- configurable safe-stop thresholds and polite crawling parameters.

This Issue drives the feature documented in `specs/0004-batch-mode-problem/spec.md` and the implementation plan in `specs/0004-batch-mode-problem/plan.md`.

## Acceptance Criteria

- CLI provides `probe` mode and `batch` mode with `--start` and `--max-cases`.
- Upper-bound detection runs within the configured probe budget and is tested via mocks.
- Final summary audit (JSON) and NDJSON attempt logs are produced under `output/`.
- Tests added cover `find_upper_bound`, classification logic, retry behavior, and summary correctness.

## Notes

- See `specs/0004-batch-mode-problem/tasks.md` for task breakdown and owners.
