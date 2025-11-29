import xml.etree.ElementTree as ET
from datetime import date

import pytest

from tests.utils.fake_webelement import FakeWebElement
from src.services.case_scraper_service import CaseScraperService
from src.lib.config import Config


def _load_fixture(path: str) -> FakeWebElement:
    txt = open(path, "r", encoding="utf-8").read()
    root = ET.fromstring(txt)
    return FakeWebElement(root, root)


def test_extract_docket_entries_headerless_table():
    modal = _load_fixture("tests/fixtures/case_modal/docket_table.html")
    svc = CaseScraperService(headless=True)
    entries = svc._extract_docket_entries(modal, case_id="IMM-123-25")
    # fixture has 3 rows
    assert len(entries) == 3
    assert entries[0].entry_date == date(2025, 11, 1)


def test_extract_docket_entries_malformed_dates():
    # Build a small modal with varied date formats including DD-MMM-YYYY
    text = """
<modal>
  <table>
    <tbody>
      <tr><td>1</td><td>10-NOV-2025</td><td>Toronto</td><td>Filed</td></tr>
      <tr><td>2</td><td>invalid date</td><td>Montreal</td><td>Served</td></tr>
    </tbody>
  </table>
</modal>
"""
    modal = FakeWebElement(ET.fromstring(text), ET.fromstring(text))
    svc = CaseScraperService(headless=True)
    entries = svc._extract_docket_entries(modal, case_id="IMM-456-25")
    assert len(entries) == 2
    # entry_date should be parsed to some November 2025 date for the first row
    assert entries[0].entry_date is not None
    assert entries[0].entry_date.year == 2025 and entries[0].entry_date.month == 11
    # second row may or may not be parsed by the fuzzy parser; accept either None or Nov 2025
    if entries[1].entry_date is not None:
        assert entries[1].entry_date.year == 2025 and entries[1].entry_date.month == 11


def test_extract_docket_entries_parse_error_escalation(monkeypatch):
    # Build a modal where table rows raise on access to simulate parsing errors
    class BadRow:
        def find_elements(self, by, selector):
            raise Exception("row parse failed")

    class BadTable:
        def find_elements(self, by, selector):
            # return one bad row
            return [BadRow(), BadRow(), BadRow()]

    class BadModal:
        def find_elements(self, by, selector):
            # return one table
            if selector == ".//table":
                return [BadTable()]
            raise Exception("not found")

    modal = BadModal()
    svc = CaseScraperService(headless=True)

    # Force low threshold so escalation happens quickly
    monkeypatch.setattr(Config, "get_docket_parse_max_errors", classmethod(lambda cls: 1))

    with pytest.raises(Exception):
        svc._extract_docket_entries(modal, case_id="IMM-000-25")
