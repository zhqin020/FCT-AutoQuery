```markdown
# Issue: 0005 - llm-data-analysis

**Summary**

Implement an offline-capable data analysis pipeline for Federal Court immigration cases. The feature will
process exporter JSON (array of `Case.to_dict()` objects), apply a fast rule-based classification mode
and a Phase-2 LLM-assisted extraction mode (local Ollama), compute duration metrics (including Rule 9
wait), and emit CSV/JSON summary artifacts and charts.

**Spec**: `specs/0005-llm-data-analysis/spec.md`

**Acceptance / gating notes (per project constitution)**

- This Issue must exist before code is written. The feature branch name MUST reference the Issue.
- Recommended branch name: `feat/0005-llm-data-analysis` (example). If you prefer numeric prefixing,
  keep the `0005` prefix but use the `feat/` prefix to comply with the constitution.

**Suggested Git commands**

```bash
# create a local branch that references the issue and push it
git checkout -b feat/0005-llm-data-analysis
git push -u origin feat/0005-llm-data-analysis
```

**Files/paths of interest**

- `specs/0005-llm-data-analysis/` (spec, plan, tasks, data-model)
- `src/fct_analysis/` (implementation target)
- `tests/fixtures/0005_cases.json` (fixture; currently local/ignored; decide commit policy)

**Notes / Next steps**

1. Confirm branch naming and create the `feat/0005-llm-data-analysis` branch.
2. Decide whether `tests/fixtures/0005_cases.json` should be committed (force-add) or served via CI.
3. Begin test-first implementation per `specs/0005-llm-data-analysis/tasks.md` after branch/issue alignment.

```
