"""URL validation utilities for Federal Court scraper."""

import re
from urllib.parse import urlparse
from typing import Optional


class URLValidator:
    """Validates URLs for Federal Court case scraping."""

    # Federal Court domain patterns
    FEDERAL_COURT_DOMAINS = {
        "www.fct-cf.ca",  # Current Federal Court domain
        "fct-cf.ca",      # Alternative without www
    }

    # Case URL patterns
    CASE_URL_PATTERNS = [
        r"/en/court-files-and-decisions",  # English court files
        r"/fr/dossiers-et-decisions",      # French court files (assuming)
    ]

    @staticmethod
    def is_federal_court_url(url: str) -> bool:
        """Check if URL belongs to Federal Court website.

        Args:
            url: URL to validate

        Returns:
            bool: True if URL is from Federal Court domain
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc in URLValidator.FEDERAL_COURT_DOMAINS
        except Exception:
            return False

    @staticmethod
    def is_case_url(url: str) -> bool:
        """Check if URL points to a case page.

        Args:
            url: URL to validate

        Returns:
            bool: True if URL appears to be a case page
        """
        if not URLValidator.is_federal_court_url(url):
            return False

        path = urlparse(url).path.lower()
        return any(pattern in path for pattern in URLValidator.CASE_URL_PATTERNS)

    @staticmethod
    def is_public_case_url(url: str) -> bool:
        """Check if URL is a public case page (not E-Filing).

        Args:
            url: URL to validate

        Returns:
            bool: True if URL is public case page
        """
        if not URLValidator.is_case_url(url):
            return False

        # Check for E-Filing indicators
        url_lower = url.lower()
        e_filing_indicators = [
            "efiling",
            "e-filing",
            "login",
            "auth",
            "secure",
            "private",
        ]

        return not any(indicator in url_lower for indicator in e_filing_indicators)

    @staticmethod
    def extract_case_number_from_url(url: str) -> Optional[str]:
        """Extract case number from URL if present.

        Args:
            url: Case URL

        Returns:
            Optional[str]: Case number if found, None otherwise
        """
        # Look for IMM- pattern in URL
        imm_match = re.search(r"IMM-[A-Z0-9-]+", url, re.IGNORECASE)
        if imm_match:
            return imm_match.group(0).upper()

        return None

    @staticmethod
    def validate_case_url(url: str) -> tuple[bool, str]:
        """Comprehensive validation of case URL.

        Args:
            url: URL to validate

        Returns:
            tuple[bool, str]: (is_valid, reason)
        """
        if not url or not url.strip():
            return False, "URL is empty"

        if not URLValidator.is_federal_court_url(url):
            return False, "Not a Federal Court URL"

        if not URLValidator.is_case_url(url):
            return False, "Not a case page URL"

        if not URLValidator.is_public_case_url(url):
            return False, "URL appears to be E-Filing or non-public"

        return True, "Valid public case URL"

    @staticmethod
    def validate_case_number(case_number: str) -> bool:
        """Validate case number format.

        Args:
            case_number: Case number to validate (e.g., IMM-12345-25)

        Returns:
            bool: True if valid format
        """
        if not case_number or not isinstance(case_number, str):
            return False

        # Pattern: IMM-{1-5 digits}-{20-25}
        pattern = r"^IMM-\d{1,5}-(20|21|22|23|24|25)$"
        return bool(re.match(pattern, case_number.strip()))
