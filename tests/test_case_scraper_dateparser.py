from datetime import date

from src.services.case_scraper_service import _parse_date_str


def test_parse_date_iso():
    assert _parse_date_str("2025-11-27") == date(2025, 11, 27)


def test_parse_date_long_formats():
    assert _parse_date_str("27 November 2025") == date(2025, 11, 27)
    assert _parse_date_str("November 27, 2025") == date(2025, 11, 27)
    assert _parse_date_str("27/11/2025") == date(2025, 11, 27)
    assert _parse_date_str("27-11-2025") == date(2025, 11, 27)


def test_parse_date_none_and_invalid():
    assert _parse_date_str("") is None
    assert _parse_date_str(None) is None
    # totally invalid
    assert _parse_date_str("not a date") is None
