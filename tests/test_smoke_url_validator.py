import pytest

from src.lib import url_validator


def test_validate_case_url_examples():
    # valid public case URL example (domain + path)
    ok, reason = url_validator.URLValidator.validate_case_url(
        "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-123-25"
    )
    assert isinstance(ok, bool)
    assert isinstance(reason, str)


def test_validate_case_number_formats():
    assert url_validator.URLValidator.validate_case_number("IMM-1-25")
    assert url_validator.URLValidator.validate_case_number("IMM-12345-25")
    assert not url_validator.URLValidator.validate_case_number("INVALID-123")
