import pytest

from selenium.webdriver.common.by import By

from src.services.case_scraper_service import CaseScraperService


class FakeElement:
    def __init__(self, tag="", text="", children=None):
        self.tag = tag
        self.text = text or ""
        self._children = children or []

    def find_elements(self, by, sel):
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
        self.data_rows = data_rows or []
        self.captions = captions or []

    def find_elements(self, by, sel):
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
        return []


class FakeModal:
    def __init__(self, tables):
        self._tables = tables

    def find_elements(self, by, sel):
        if by == By.XPATH and sel == ".//table":
            return self._tables
        return []


def test_table_selection_prefers_real_table():
    template_table = FakeTable(
        headers=["#", "Date"],
        data_rows=[["#", "YYYY-MM-DD"]],
    )

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

    assert len(entries) == 3
    dates = [getattr(e.entry_date, 'isoformat', lambda: e.entry_date)() if getattr(e.entry_date, 'isoformat', None) else e.entry_date for e in entries]
    assert any('2025' in (d or '') for d in dates)
