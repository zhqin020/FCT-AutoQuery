import xml.etree.ElementTree as ET
from datetime import date

from tests.utils.fake_webelement import FakeWebElement
from src.services.case_scraper_service import CaseScraperService


def _load_fixture(path: str) -> FakeWebElement:
    txt = open(path, "r", encoding="utf-8").read()
    root = ET.fromstring(txt)
    return FakeWebElement(root, root)


def test_extract_case_header_from_title_fixture():
    modal = _load_fixture("tests/fixtures/case_modal/header_title.html")
    svc = CaseScraperService(headless=True)
    data = svc._extract_case_header(modal)
    assert data.get("case_id") == "IMM-777-25"
    assert data.get("nature_of_proceeding") == "Judicial Review"


def test_extract_case_header_office_language_split():
    modal = _load_fixture("tests/fixtures/case_modal/header_office_language.html")
    svc = CaseScraperService(headless=True)
    data = svc._extract_case_header(modal)
    # office should be 'Toronto' and language 'English'
    assert data.get("office") == "Toronto"
    assert data.get("language") in ("English", "english", "EN", "en")
