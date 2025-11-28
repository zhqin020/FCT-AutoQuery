import xml.etree.ElementTree as ET

from tests.utils.fake_webelement import FakeWebElement
from src.services.case_scraper_service import CaseScraperService


def test_extract_case_id_from_modal_title():
    xml = '<modal><h5 id="modalTitle">Recorded Entry Information - IMM-777-25</h5></modal>'
    root = ET.fromstring(xml)
    modal = FakeWebElement(root, root)
    svc = CaseScraperService(headless=True)
    data = svc._extract_case_header(modal)
    assert data.get("case_id") == "IMM-777-25"
