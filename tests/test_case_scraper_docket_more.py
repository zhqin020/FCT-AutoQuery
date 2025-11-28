import xml.etree.ElementTree as ET
from datetime import date

from tests.utils.fake_webelement import FakeWebElement
from src.services.case_scraper_service import CaseScraperService


def _modal_from_html(html: str) -> FakeWebElement:
    root = ET.fromstring(html)
    return FakeWebElement(root, root)


def test_docket_table_selection_prefers_real_table():
    # First table is a placeholder/example row and should be penalized by scoring
    html = """
    <modal>
      <table>
        <thead><tr><th>#</th><th>YYYY-MM-DD</th></tr></thead>
        <tbody>
          <tr><td>#</td><td>YYYY-MM-DD</td></tr>
        </tbody>
      </table>
      <table>
        <thead><tr><th>ID</th><th>Date Filed</th><th>Office</th><th>Recorded Entry Summary</th></tr></thead>
        <tbody>
          <tr><td>1</td><td>2025-11-01</td><td>Toronto</td><td>Application filed</td></tr>
          <tr><td>2</td><td>01-Nov-2025</td><td>Toronto</td><td>Service</td></tr>
        </tbody>
      </table>
    </modal>
    """
    modal = _modal_from_html(html)
    svc = CaseScraperService(headless=True)
    entries = svc._extract_docket_entries(modal, case_id="IMM-900-25")
    # Should pick up 2 entries from the real table (not the placeholder)
    assert len(entries) == 2
    assert entries[0].entry_office == "Toronto"
    assert entries[0].summary == "Application filed"


def test_docket_date_parsing_various_formats():
    html = """
    <modal>
      <table>
        <thead><tr><th>ID</th><th>Date Filed</th><th>Office</th><th>Recorded Entry Summary</th></tr></thead>
        <tbody>
          <tr><td>1</td><td>10-NOV-2025</td><td>Toronto</td><td>Notice</td></tr>
          <tr><td>2</td><td>06-JUN-2025</td><td>Ottawa</td><td>Filing</td></tr>
          <tr><td>3</td><td>2025/11/05</td><td>Vancouver</td><td>Decision</td></tr>
        </tbody>
      </table>
    </modal>
    """
    modal = _modal_from_html(html)
    svc = CaseScraperService(headless=True)
    entries = svc._extract_docket_entries(modal, case_id="IMM-901-25")
    assert len(entries) == 3
    assert entries[0].entry_date == date(2025, 11, 10)
    assert entries[1].entry_date == date(2025, 6, 6)
    assert entries[2].entry_date == date(2025, 11, 5)
