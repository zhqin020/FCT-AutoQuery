# CaseScraperService Test Plan

Goal
----
Increase unit and integration test coverage for `src/services/case_scraper_service.py` by extracting and testing pure parsing logic, and by providing mocked-driver integration tests for higher-level flows.

Scope
-----
- Unit tests for pure parsing/normalization logic used by the scraper (date parsing, header extraction heuristics, docket table parsing heuristics).
- Integration-style tests that exercise `_extract_case_header` and `_extract_docket_entries` using lightweight HTML fixtures and a small fake `WebElement` wrapper (no real browser required).
- Mocked `CaseScraperService` higher-level flows (e.g., `search_case`, `scrape_case_data`) to assert error handling and retry behavior without hitting the network.

Prioritized Tasks
------------------
1. Extract and test date parsing helpers used in `_extract_case_header` and `_extract_docket_entries`.
   - Tests: ISO, common formats, fuzzy substrings (DD-MMM-YYYY, DD/MM/YYYY), and fallback to `dateutil` when available.
2. Create HTML fixtures for modal content representing common variants:
   - Table-based header (label/value rows)
   - Description-list (dt/dd) header
   - Paragraph/strong labels header
   - Docket table with several rows (various date formats and empty cells)
3. Implement a small `tests/utils/fake_webelement.py` helper that wraps a BeautifulSoup-parsed fragment and exposes the subset of `find_element`/`find_elements`/`text`/`get_attribute` used by the parser functions.
4. Write unit tests that call `_extract_case_header` and `_extract_docket_entries` with the fake element and assert extracted dictionaries and docket entry fields.
5. Create a mocked `CaseScraperService` integration test for `scrape_case_data` where the modal interactions are simulated by prepopulating the fake driver with HTML fragments and verifying the returned `Case` and `DocketEntry` objects.

Implementation Notes
--------------------
- Prefer tests that do not require Selenium/WebDriver to run quickly and reliably in CI.
- Use `tmp_path` fixture for any filesystem writes expected by the code (e.g., logs/ or modal HTML capture); monkeypatch Config flags to disable actual writes when appropriate.
- Organize fixtures under `tests/fixtures/case_modal/` and load them as needed.

Risks
-----
- HTML structure on the live site may change; keep fixtures small and representative, not fragile.
- Some helper heuristics depend on DOM APIs; the fake element must faithfully emulate the limited API surface used by the scraper.

Deliverables (first sprint)
--------------------------
- `tests/utils/fake_webelement.py` — fake WebElement wrapper.
- `tests/fixtures/case_modal/*.html` — several modal fixture variants.
- `tests/test_case_scraper_parsing.py` — unit tests for header and docket parsing.
- Documentation: `docs/testing/case_scraper_service_test_plan.md` (this file).

Estimated effort
----------------
- Implementation + tests for first sprint: ~4-8 hours.

Next immediate action
---------------------
I'll implement the test harness utilities and the first unit test for the date-parsing helper and one header fixture. After that I will run the test suite and update coverage.
