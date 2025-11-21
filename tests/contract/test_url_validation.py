"""Contract tests for URL validation utilities."""

import pytest
from src.lib.url_validator import URLValidator


class TestURLValidator:
    """Contract tests for URL validation functionality."""

    def test_is_federal_court_url_valid_domains(self):
        """Test valid Federal Court domains are recognized."""
        valid_urls = [
            "https://www.fct-cf.ca/en/court-files-and-decisions/court-files",
            "https://fct-cf.ca/en/court-files-and-decisions",
            "https://www.fct-cf.ca/fr/dossiers-et-decisions",
            "http://fct-cf.ca/some/path",
            "https://www.fct-cf.ca/another/path",
        ]

        for url in valid_urls:
            assert URLValidator.is_federal_court_url(url), f"URL should be valid: {url}"

    def test_is_federal_court_url_invalid_domains(self):
        """Test invalid domains are rejected."""
        invalid_urls = [
            "https://google.com",
            "https://courts.ca",
            "https://cas-satj.gc.ca.invalid",
            "https://fake-fct-cf.ca",
            "not-a-url",
            "",
        ]

        for url in invalid_urls:
            assert not URLValidator.is_federal_court_url(url), f"URL should be invalid: {url}"

    def test_is_case_url_valid_patterns(self):
        """Test valid case URL patterns are recognized."""
        valid_case_urls = [
            "https://www.fct-cf.ca/en/court-files-and-decisions/court-files",
            "https://fct-cf.ca/en/court-files-and-decisions",
            "https://www.fct-cf.ca/fr/dossiers-et-decisions",
            "https://fct-cf.ca/en/court-files-and-decisions/IMM-12345-22",
            "https://www.fct-cf.ca/fr/dossiers-et-decisions/public-case",
        ]

        for url in valid_case_urls:
            assert URLValidator.is_case_url(url), f"URL should be valid case URL: {url}"

    def test_is_case_url_invalid_patterns(self):
        """Test invalid case URL patterns are rejected."""
        invalid_case_urls = [
            "https://www.fct-cf.ca/other/path",
            "https://www.fct-cf.ca/admin",
            "https://google.com/en/court-files-and-decisions",
            "https://www.fct-cf.ca/secure/login",
        ]

        for url in invalid_case_urls:
            assert not URLValidator.is_case_url(url), f"URL should be invalid case URL: {url}"

    def test_is_public_case_url_valid_public(self):
        """Test valid public case URLs are recognized."""
        valid_public_urls = [
            "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22",
            "https://fct-cf.ca/en/court-files-and-decisions/case-details",
            "https://www.fct-cf.ca/fr/dossiers-et-decisions/public-case",
        ]

        for url in valid_public_urls:
            assert URLValidator.is_public_case_url(url), f"URL should be public case URL: {url}"

    def test_is_public_case_url_efiling_rejected(self):
        """Test E-Filing URLs are rejected as non-public."""
        efiling_urls = [
            "https://www.fct-cf.ca/efiling/login",
            "https://www.fct-cf.ca/e-filing/submit",
            "https://fct-cf.ca/en/court-files-and-decisions/efiling",
            "https://www.fct-cf.ca/secure/login",
            "https://www.fct-cf.ca/auth/private",
        ]

        for url in efiling_urls:
            assert not URLValidator.is_public_case_url(url), f"E-Filing URL should be rejected: {url}"

    def test_extract_case_number_from_url_valid_cases(self):
        """Test case number extraction from valid URLs."""
        test_cases = [
            ("https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22", "IMM-12345-22"),
            ("https://fct-cf.ca/en/court-files-and-decisions/imm-abc123-23", "IMM-ABC123-23"),
            ("https://www.fct-cf.ca/fr/dossiers-et-decisions/IMM-XYZ-99-24", "IMM-XYZ-99-24"),
        ]

        for url, expected in test_cases:
            result = URLValidator.extract_case_number_from_url(url)
            assert result == expected, f"Expected {expected}, got {result} for URL: {url}"

    def test_extract_case_number_from_url_no_case_number(self):
        """Test case number extraction returns None when no case number present."""
        urls_without_case_numbers = [
            "https://www.fct-cf.ca/en/court-files-and-decisions",
            "https://fct-cf.ca/en/court-files-and-decisions/search",
            "https://www.fct-cf.ca/fr/dossiers-et-decisions/list",
        ]

        for url in urls_without_case_numbers:
            result = URLValidator.extract_case_number_from_url(url)
            assert result is None, f"Expected None, got {result} for URL: {url}"

    def test_validate_case_url_valid_cases(self):
        """Test comprehensive validation of valid case URLs."""
        valid_urls = [
            "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22",
            "https://fct-cf.ca/en/court-files-and-decisions/IMM-ABC-23",
            "https://www.fct-cf.ca/fr/dossiers-et-decisions/IMM-XYZ-24",
        ]

        for url in valid_urls:
            is_valid, reason = URLValidator.validate_case_url(url)
            assert is_valid, f"URL should be valid: {url}, reason: {reason}"
            assert reason == "Valid public case URL", f"Unexpected reason: {reason}"

    def test_validate_case_url_invalid_cases(self):
        """Test comprehensive validation rejects invalid URLs."""
        invalid_cases = [
            ("", "URL is empty"),
            ("not-a-url", "Not a Federal Court URL"),
            ("https://google.com", "Not a Federal Court URL"),
            ("https://www.fct-cf.ca/other/path", "Not a case page URL"),
            ("https://www.fct-cf.ca/efiling/login", "Not a case page URL"),
            ("https://www.fct-cf.ca/en/court-files-and-decisions/secure", "URL appears to be E-Filing or non-public"),
        ]

        for url, expected_reason in invalid_cases:
            is_valid, reason = URLValidator.validate_case_url(url)
            assert not is_valid, f"URL should be invalid: {url}"
            assert expected_reason in reason, f"Expected '{expected_reason}' in reason, got: {reason}"