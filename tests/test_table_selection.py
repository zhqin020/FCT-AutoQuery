import pytest

from selenium.webdriver.common.by import By

from src.services.case_scraper_service import CaseScraperService


class FakeElement:
    def __init__(self, tag="", text="", children=None):
        self.tag = tag
        self.text = text or ""
        self._children = children or []

    def find_elements(self, by, sel):
        # Not used in our simple caption/header/td mocks
        return []


class FakeRow:
    def __init__(self, cell_texts):
        self._cells = [FakeElement(tag="td", text=t) for t in cell_texts]

    def find_elements(self, by, sel):
        if by == By.TAG_NAME and sel == "td":
            return self._cells
        return []


class FakeTable:
    def __init__(self, headers=None, data_rows=None, captions=None):
        self.headers = headers or []
        self.data_rows = data_rows or []  # list of list-of-text
        self.captions = captions or []

    def find_elements(self, by, sel):
        # support XPaths used by _extract_docket_entries
        if by == By.XPATH and sel == ".//tbody//tr":
            return [FakeRow(r) for r in self.data_rows]
        if by == By.XPATH and sel == ".//tr":
            return [FakeRow(r) for r in self.data_rows]
        if by == By.XPATH and sel == ".//caption":
            return [FakeElement(tag="caption", text=c) for c in self.captions]
        if by == By.XPATH and sel in (".//th", ".//thead//th"):
            return [FakeElement(tag="th", text=h) for h in self.headers]
        if by == By.TAG_NAME and sel == "tr":
            return [FakeRow(r) for r in self.data_rows]
        if by == By.TAG_NAME and sel == "th":
            return [FakeElement(tag="th", text=h) for h in self.headers]
        # fallback
        return []


class FakeModal:
    def __init__(self, tables):
        self._tables = tables

    def find_elements(self, by, sel):
        # CaseScraperService asks modal_element.find_elements(By.XPATH, ".//table")
        if by == By.XPATH and sel == ".//table":
            return self._tables
        return []


def test_table_selection_prefers_real_table():
    """Regression test: when a modal contains an example/template table and
    a real data table, the scraper should pick the real table (more rows).
    This test uses fake DOM-like objects and doesn't require a running
    Selenium WebDriver.
    """

    # Template/example table: single placeholder row
    template_table = FakeTable(
        headers=["#", "Date"],
        data_rows=[["#", "YYYY-MM-DD"]],
    )

    # Real table: multiple data rows that should be preferred
    real_table = FakeTable(
        headers=["ID", "Document Date", "Office", "Summary"],
        data_rows=[
            ["1", "06-AUG-2025", "Ottawa", "Real entry A"],
            ["2", "21-MAR-2025", "Ottawa", "Real entry B"],
            ["3", "21-MAR-2025", "Ottawa", "Real entry C"],
        ],
    )

    modal = FakeModal([template_table, real_table])

    svc = CaseScraperService(headless=True)

    entries = svc._extract_docket_entries(modal, case_id="IMM-TEST-1")

    # Should pick the real table and therefore produce three entries
    assert len(entries) == 3
    # verify dates were parsed from the chosen table rows (sanity check)
    dates = [getattr(e.entry_date, 'isoformat', lambda: e.entry_date)() if getattr(e.entry_date, 'isoformat', None) else e.entry_date for e in entries]
    assert any('2025' in (d or '') for d in dates)
