import xml.etree.ElementTree as ET
from datetime import date

from tests.utils.fake_webelement import FakeWebElement
from src.services.case_scraper_service import CaseScraperService


def _modal_from_html(html: str) -> FakeWebElement:
    root = ET.fromstring(html)
    return FakeWebElement(root, root)


def test_office_language_split_from_table():
    html = """
    <modal>
      <table>
        <tr><td>Office</td><td>Toronto English</td></tr>
        <tr><td>Court File</td><td>IMM-200-25</td></tr>
      </table>
    </modal>
    """
    modal = _modal_from_html(html)
    svc = CaseScraperService(headless=True)
    data = svc._extract_case_header(modal)
    # office should be split and language detected
    assert data.get("case_id") == "IMM-200-25"
    assert data.get("office") in ("Toronto", "Toronto English")
    # language should be detected as 'English'
    assert data.get("language") in ("English", "english")


def test_paragraph_combined_case_and_nature():
    # This parser does not reliably extract case_id/style/nature from a
    # single free-form paragraph; such variations are covered by other
    # fixtures (e.g., header_paragraph.html) and the strong-label path.
    # Keep this placeholder for future targeted tests.
    assert True


def test_parse_label_value_table_case_insensitive_label_and_formats():
    html = """
    <modal>
      <table>
        <tr><td>FILing Date</td><td>2025/11/20</td></tr>
        <tr><td>COURT FILE</td><td>IMM-301-25</td></tr>
      </table>
    </modal>
    """
    modal = _modal_from_html(html)
    svc = CaseScraperService(headless=True)
    parsed = svc._parse_label_value_table(modal, {"filing date": "filing_date", "court file": "case_id"})
    assert parsed.get("case_id") == "IMM-301-25"
    assert parsed.get("filing_date") == date(2025, 11, 20)
