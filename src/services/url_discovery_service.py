"""URL discovery service for finding Federal Court case URLs."""

import requests
from typing import List, Optional
from urllib.parse import urljoin, urlparse
import re
from bs4 import BeautifulSoup

from src.lib.url_validator import URLValidator
from src.lib.logging_config import get_logger

logger = get_logger()


class CaseURLDiscoverer:
    """Service for discovering Federal Court case URLs."""

    # Base URLs for case searches
    BASE_SEARCH_URLS = [
        "https://cas-cdc-www02.cas-satj.gc.ca/portal/page/portal/fc_cf_en",
        "https://www.cas-satj.gc.ca/portal/page/portal/fc_cf_en",
    ]

    def __init__(self, timeout: int = 30):
        """Initialize the URL discoverer.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })

    def discover_case_urls_for_year(self, year: int, max_cases: Optional[int] = None) -> List[str]:
        """Discover case URLs for a specific year.

        Args:
            year: Year to search for cases
            max_cases: Maximum number of cases to return (None for all)

        Returns:
            List[str]: List of valid case URLs
        """
        logger.info(f"Discovering case URLs for year {year}")

        case_urls = []

        for base_url in self.BASE_SEARCH_URLS:
            try:
                urls = self._search_year_at_base_url(base_url, year, max_cases)
                case_urls.extend(urls)

                if max_cases and len(case_urls) >= max_cases:
                    break

            except Exception as e:
                logger.warning(f"Failed to search at {base_url}: {e}")
                continue

        # Remove duplicates and validate
        unique_urls = list(set(case_urls))
        valid_urls = [url for url in unique_urls if URLValidator.is_case_url(url)]

        if max_cases:
            valid_urls = valid_urls[:max_cases]

        logger.info(f"Discovered {len(valid_urls)} valid case URLs for year {year}")
        return valid_urls

    def _search_year_at_base_url(self, base_url: str, year: int, max_cases: Optional[int]) -> List[str]:
        """Search for cases at a specific base URL.

        Args:
            base_url: Base search URL
            year: Year to search
            max_cases: Maximum cases to return

        Returns:
            List[str]: Case URLs found
        """
        # This is a simplified implementation
        # Real implementation would need to:
        # 1. Navigate to search page
        # 2. Fill search form with year criteria
        # 3. Submit search
        # 4. Parse results page for case links
        # 5. Handle pagination

        # For now, return mock URLs for testing
        # In real implementation, this would scrape actual search results

        mock_urls = []
        for i in range(min(max_cases or 10, 10)):  # Mock up to 10 cases
            case_number = "02d"
            mock_url = f"{base_url}/case/IMM-{case_number}-{year % 100:02d}"
            mock_urls.append(mock_url)

        return mock_urls

    def discover_case_urls_for_years(self, years: List[int], max_cases_per_year: Optional[int] = None) -> List[str]:
        """Discover case URLs for multiple years.

        Args:
            years: List of years to search
            max_cases_per_year: Maximum cases per year

        Returns:
            List[str]: Combined list of case URLs
        """
        all_urls = []

        for year in years:
            year_urls = self.discover_case_urls_for_year(year, max_cases_per_year)
            all_urls.extend(year_urls)

        # Remove duplicates
        unique_urls = list(set(all_urls))

        logger.info(f"Total unique case URLs discovered: {len(unique_urls)}")
        return unique_urls

    def validate_discovered_urls(self, urls: List[str]) -> tuple[List[str], List[str]]:
        """Validate a list of discovered URLs.

        Args:
            urls: URLs to validate

        Returns:
            tuple: (valid_urls, invalid_urls)
        """
        valid_urls = []
        invalid_urls = []

        for url in urls:
            is_valid, _ = URLValidator.validate_case_url(url)
            if is_valid:
                valid_urls.append(url)
            else:
                invalid_urls.append(url)

        logger.info(f"URL validation: {len(valid_urls)} valid, {len(invalid_urls)} invalid")
        return valid_urls, invalid_urls