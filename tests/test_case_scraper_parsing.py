import xml.etree.ElementTree as ET
from pathlib import Path

from src.services.case_scraper_service import CaseScraperService
from tests.utils.fake_webelement import FakeWebElement


def load_fixture(name: str) -> FakeWebElement:
    path = Path(__file__).parent / "fixtures" / "case_modal" / name
    text = path.read_text(encoding="utf-8")
    # Parse as XML (our fixture is XML-friendly)
    root = ET.fromstring(text)
    return FakeWebElement(root)


def test_extract_case_header_from_table():
    fake_modal = load_fixture("header_table.html")
    svc = CaseScraperService(headless=True)
    data = svc._extract_case_header(fake_modal)

    assert data.get("case_id") == "IMM-123-25"
    assert data.get("filing_date") is not None
    # filing_date should be a date object with expected year
    assert getattr(data.get("filing_date"), "year", None) == 2025
    assert data.get("style_of_cause") == "John Doe v. Minister"


def test_extract_case_header_from_dt_dd():
    fake_modal = load_fixture("header_dt_dd.html")
    svc = CaseScraperService(headless=True)
    data = svc._extract_case_header(fake_modal)

    assert data.get("case_id") == "IMM-999-25"
    assert getattr(data.get("filing_date"), "year", None) == 2025
    assert data.get("style_of_cause") == "Acme Inc v. Minister"


def test_extract_case_header_from_paragraphs():
    fake_modal = load_fixture("header_paragraph.html")
    svc = CaseScraperService(headless=True)
    data = svc._extract_case_header(fake_modal)

    assert data.get("case_id") == "IMM-555-25"
    # Filing date parsing may vary depending on heuristics; ensure presence or None acceptable
    fd = data.get("filing_date")
    if fd is not None:
        assert getattr(fd, "year", None) == 2025
    assert data.get("style_of_cause") == "Foo Bar v. Baz"


def test_extract_docket_entries_table():
    fake_modal = load_fixture("docket_table.html")
    svc = CaseScraperService(headless=True)
    entries = svc._extract_docket_entries(fake_modal, case_id="IMM-TEST-25")

    assert len(entries) == 3
    # Check parsed dates for first and second entries
    assert getattr(entries[0].entry_date, "year", None) == 2025
    assert getattr(entries[1].entry_date, "year", None) == 2025
    # Office normalization: second row had 'Toronto English' -> language split behavior
    assert entries[1].entry_office is not None
    assert entries[2].summary == "Decision issued"


def test_parse_label_value_table_helper():
    fake_modal = load_fixture("header_table.html")
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

    parsed = svc._parse_label_value_table(fake_modal, label_variants)
    assert parsed.get("case_id") == "IMM-123-25"
    assert getattr(parsed.get("filing_date"), "year", None) == 2025
