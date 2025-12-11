import glob
from datetime import date

import pytest

from src.services.case_scraper_service import CaseScraperService


class DummyModal:
    def __init__(self, text: str):
        self.text = text


def find_latest_modal(path_pattern: str):
    files = glob.glob(path_pattern)
    if not files:
        pytest.skip(f"No modal HTML files found matching: {path_pattern}")
    # Prefer the most recent modal that contains case header tokens (avoid maintenance notices)
    files.sort()
    for f in reversed(files):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                txt = fh.read()
            # Prefer files that include the filing date or the recorded entry header or the case id
            if ("Filing Date" in txt) or ("Recorded Entry Information" in txt) or ("IMM-1-25" in txt):
                return f
        except Exception:
            continue
    # if none of the saved modal files contain header tokens, return None so tests can use a sample fixture
    return None


def load_modal_text(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as fh:
        return fh.read()


def test_modal_fallback_parses_headers():
    """Ensure the modal-text fallback extracts filing_date, office, and language."""
    # Use an embedded sample modal text to validate parsing deterministically
    text = (
        "Recorded Entry Information :   IMM-1-25\n"
        "Type :  Immigration Matters\n"
        "Nature of Proceeding :  Imm - Appl. for leave & jud. review - IRB - Refugee Appeal Division\n"
        "Office :  Montréal     Language :  English\n"
        "Type of Action :  Immigration Matters\n"
        "Filing Date :  2025-01-01\n"
        "Information about the court file\n"
    )

    # The fallback only needs a `.text` property on the modal element
    dummy = DummyModal(text)

    svc = CaseScraperService(headless=True)

    data = {
        "case_id": None,
        "case_type": None,
        "action_type": None,
        "nature_of_proceeding": None,
        "filing_date": None,
        "office": None,
        "style_of_cause": None,
        "language": None,
    }

    # Run fallback parser
    svc._fallback_extract_headers_from_modal_text(dummy, data)

    # Debug output on failure: print the parsed data
    print("PARSED DATA:", data)

    assert data["filing_date"] == date(2025, 1, 1)
    assert data["office"] is not None
    assert "montr" in data["office"].lower()  # accept Montréal/Montréal variants
    assert data["language"] is not None
