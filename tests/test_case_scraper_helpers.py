import xml.etree.ElementTree as ET
from datetime import date

from tests.utils.fake_webelement import FakeWebElement
from src.services.case_scraper_service import CaseScraperService


def _load_fixture(path: str) -> FakeWebElement:
    txt = open(path, "r", encoding="utf-8").read()
    root = ET.fromstring(txt)
    return FakeWebElement(root, root)


def test_parse_label_value_table_from_table_fixture():
    modal = _load_fixture("tests/fixtures/case_modal/header_table.html")
    svc = CaseScraperService(headless=True)
    label_variants = {
        "court file": "case_id",
        "court file no": "case_id",
        "court file number": "case_id",
        "type": "case_type",
        "type of action": "action_type",
        "nature of proceeding": "nature_of_proceeding",
        "filing date": "filing_date",
        "office": "office",
        "style of cause": "style_of_cause",
        "language": "language",
    }

    parsed = svc._parse_label_value_table(modal, label_variants)
    assert parsed.get("case_id") == "IMM-123-25"
    assert parsed.get("style_of_cause") == "John Doe v. Minister"
    assert parsed.get("filing_date") == date(2025, 11, 27)


def test_extract_case_header_from_dt_dd_fixture():
    modal = _load_fixture("tests/fixtures/case_modal/header_dt_dd.html")
    svc = CaseScraperService(headless=True)
    data = svc._extract_case_header(modal)
    assert data.get("case_id") == "IMM-999-25"
    assert data.get("style_of_cause") == "Acme Inc v. Minister"
    # filing date parsed from '27 November 2025'
    assert data.get("filing_date") == date(2025, 11, 27)


def test_extract_case_header_from_paragraph_fixture():
    modal = _load_fixture("tests/fixtures/case_modal/header_paragraph.html")
    svc = CaseScraperService(headless=True)
    data = svc._extract_case_header(modal)
    assert data.get("case_id") == "IMM-555-25"
    assert data.get("style_of_cause") == "Foo Bar v. Baz"
    assert data.get("filing_date") == date(2025, 11, 20)
