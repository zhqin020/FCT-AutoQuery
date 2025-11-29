import xml.etree.ElementTree as ET
from datetime import date

from tests.utils.fake_webelement import FakeWebElement
from src.services.case_scraper_service import CaseScraperService


def _load_fixture(path: str) -> FakeWebElement:
    txt = open(path, "r", encoding="utf-8").read()
    root = ET.fromstring(txt)
    return FakeWebElement(root, root)


def test_extract_docket_entries_from_table_fixture():
    modal = _load_fixture("tests/fixtures/case_modal/docket_table.html")
    svc = CaseScraperService(headless=True)
    entries = svc._extract_docket_entries(modal, case_id="IMM-000-25")

    assert len(entries) == 3

    dates = [e.entry_date for e in entries]
    assert dates[0] == date(2025, 11, 1)
    assert dates[1] == date(2025, 11, 1)
    assert dates[2] == date(2025, 11, 10)

    offices = [e.entry_office for e in entries]
    assert offices[0] == "Toronto"
    assert offices[1] == "Toronto English" or offices[1] == "Toronto"
    assert offices[2] == "#"

    summaries = [e.summary for e in entries]
    assert summaries[0] == "Application filed"
    assert "Service" in summaries[1]
    assert "Decision" in summaries[2]


def test_parse_label_value_table_with_empty_value():
    xml = """
    <modal>
      <table>
        <tr><td>Filing Date</td><td></td></tr>
        <tr><td>Court File</td><td>IMM-321-25</td></tr>
      </table>
    </modal>
    """
    root = ET.fromstring(xml)
    modal = FakeWebElement(root, root)
    svc = CaseScraperService(headless=True)
    label_variants = {
        "court file": "case_id",
        "filing date": "filing_date",
    }

    parsed = svc._parse_label_value_table(modal, label_variants)
    assert parsed.get("case_id") == "IMM-321-25"
    assert parsed.get("filing_date") is None
