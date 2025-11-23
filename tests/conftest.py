"""Pytest configuration and fixtures."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    return MagicMock()


@pytest.fixture
def sample_case_data():
    """Sample case data for testing."""
    from datetime import date

    return {
        "url": "https://www.fct-cf.ca/en/court-files-and-decisions/sample-case",
        "court_file_no": "IMM-12345-22",
        "case_title": "Sample Immigration Case",
        "court_name": "Federal Court",
        "case_date": date(2023, 6, 15),
        "html_content": "<html><body><h1>Sample Case Content</h1></body></html>",
    }


@pytest.fixture
def sample_case_url():
    """Sample case URL for testing."""
    return "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"


@pytest.fixture
def invalid_urls():
    """Invalid URLs for testing URL validation."""
    return [
        "",
        "not-a-url",
        "https://google.com",
        "https://www.fct-cf.ca/efiling/login",
        "https://www.fct-cf.ca/en/court-files-and-decisions/login",
    ]
