<!-- Sync Impact Report
Version change: 1.1.0 → 1.2.0
List of modified principles: None
Added sections: Environment Activation Requirement
Removed sections: None
Templates requiring updates: plan-template.md (add to constitution check)
Follow-up TODOs: None
-->
# FCT-AutoQuery Constitution
## Project Overview (项目概况)
**Name:** FCT-AutoQuery (Federal Court Case Auto-Query System)
**Mission:** To automate the retrieval, parsing, storage, and statistical analysis of case information from the Federal Court (Canada) website.
**Core Value:** Provide efficient, automated tracking of legal cases for analysis and reporting.

## Core Principles

### I. Testing Standard (Highest Priority)
* **Mandatory Coverage:** Every module (`src/*`) MUST have a corresponding test file in `tests/`.
* **No Test, No Merge:** Logic without tests is considered incomplete and cannot be merged.
* **Scenarios:** Tests must cover:
    1.  Happy path (Standard success).
    2.  Edge cases (Empty data, malformed HTML).
    3.  Network failures (Mocking network calls is required).
* **Tooling:** Use `pytest` and `unittest.mock` (or `pytest-mock`).

### II. Git Workflow & Branching Strategy (Strict TBD)
**We strictly follow Trunk-Based Development with a Test-First Policy.**

### Workflow Steps:
1.  **Branch:** Create a short-lived branch from `main` (e.g., `feat/search-parser`).
2.  **Test (TDD):** **Write the test FIRST.** The test must fail initially (Red).
3.  **Code:** Write the implementation code to pass the test (Green).
4.  **Refactor:** Clean up the code while keeping tests passing.
5.  **Merge:** Merge to `main` ONLY if all tests pass.
6.  **Delete:** **Immediately delete the feature branch** after merging.

### Branch Naming:
* `feat/description` (New features)
* `fix/issue-description` (Bug fixes)
* `test/description` (Adding missing tests)

### III.Coding Standards (编码规范)
1. **Testing (Highest Priority)**
* **Coverage:** 100% coverage for the specific Issue scope.
* **Regression:** If the Issue is a bug, the new test must prevent this bug from reappearing.
* **Mocking:** Network calls must be mocked.

2. **Python Standards**
* Type Hinting, Google Docstrings, `loguru` for logging.
* **Ethical Scraping:** Random delays, respect `robots.txt`.
 

### Issue Management Strategy (Issue 管理策略) - NEW
**Policy: Zero Open Defects. Every code change must start with an Issue.**

1.  **Mandatory Issue:** No code is written without an open GitHub Issue (Feature Request or Bug Report).
2.  **Issues Folder and Naming:** All issues are stored in the `issues/` folder. Naming should be clear and concise (e.g., `feature/0001-case-search.md`).

3.  **Issue Lifecycle:**
    * **Open:** Describe the requirement or bug.
    * **In Progress:** Branch created and linked.
    * **Closed:** Automatically closed via Pull Request (using "Closes #ID").
4.  **Labeling:** Use `bug`, `feature`, `test-gap`, `tech-debt`.

### V. Environment Activation Requirement
**必须在 fct 虚拟环境下运行各项命令。运行命令前，需要先运行: conda activate fct**

## Git Workflow (Strict TBD + Issue Driven)
**Workflow: Issue -> Branch -> Test -> Code -> Merge -> Close.**

### Steps:
1.  **Issue:** Create an Issue (e.g., #42 "Parse Hearing Date").
2.  **Branch:** Create branch **referencing the Issue ID**:
    * `feat/0042-parse-hearing-date`
    * `fix/0045-handle-timeout`
3.  **Test (TDD):** Write a failing test that reproduces the Issue (for bugs) or verifies the spec (for features).
4.  **Code:** Implement logic to pass the test.
5.  **PR & Merge:** Open a PR with description **"Closes #0042"**.
6.  **Cleanup:** Merge to `main` (ensure CI passes) and delete the branch. Issue #0042 is auto-closed.

## Governance
This constitution supersedes all other project guidelines. Amendments require consensus from core contributors and must include a migration plan. All pull requests must verify compliance with these principles. Use this constitution as the basis for decision-making in development.

**Version**: 1.2.0 | **Ratified**: 2025-11-19 | **Last Amended**: 2025-11-22
