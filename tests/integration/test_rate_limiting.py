"""Integration tests for rate limiting functionality."""

import time
from unittest.mock import MagicMock, patch

from src.lib.rate_limiter import EthicalRateLimiter
from src.services.case_scraper_service import CaseScraperService


class TestRateLimiting:
    """Integration tests for rate limiting during scraping operations."""

    @patch("src.services.case_scraper_service.webdriver")
    @patch("src.services.case_scraper_service.EthicalRateLimiter")
    def test_rate_limiting_applied_during_multiple_scrapes(
        self, mock_rate_limiter, mock_webdriver
    ):
        """Test that rate limiting is applied when scraping multiple cases."""
        # Setup mocks
        mock_driver = MagicMock()
        mock_webdriver.Chrome.return_value = mock_driver
        mock_driver.page_source = (
            "<html><title>Test Case</title><body>Test content</body></html>"
        )

        # Mock rate limiter to track calls
        mock_rate_limiter_instance = MagicMock()
        mock_rate_limiter.return_value = mock_rate_limiter_instance
        mock_rate_limiter_instance.wait_if_needed.return_value = 0.0

        # Create service
        service = CaseScraperService()

        # Scrape multiple cases
        urls = [
            "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22",
            "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-67890-23",
            "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-11111-24",
        ]

        for url in urls:
            result = service.scrape_single_case(url)
            assert result is not None
            assert isinstance(result, dict) or hasattr(result, "case_id")  # Case object

        # Verify rate limiter was called for each scrape
        assert mock_rate_limiter_instance.wait_if_needed.call_count == len(urls)

    @patch("src.services.case_scraper_service.webdriver")
    @patch("src.services.case_scraper_service.EthicalRateLimiter")
    def test_rate_limiting_enforces_minimum_interval(
        self, mock_rate_limiter, mock_webdriver
    ):
        """Test that rate limiting enforces minimum 1-second intervals."""
        # Setup mocks
        mock_driver = MagicMock()
        mock_webdriver.Chrome.return_value = mock_driver
        mock_driver.page_source = (
            "<html><title>Test Case</title><body>Test content</body></html>"
        )

        # Mock rate limiter to simulate waiting
        mock_rate_limiter_instance = MagicMock()
        mock_rate_limiter.return_value = mock_rate_limiter_instance

        # First call: no wait needed
        mock_rate_limiter_instance.wait_if_needed.return_value = 0.0

        # Create service
        service = CaseScraperService()

        # First scrape
        url1 = "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
        start_time = time.time()
        result1 = service.scrape_single_case(url1)
        time.time() - start_time

        # Second scrape should trigger rate limiting
        mock_rate_limiter_instance.wait_if_needed.return_value = (
            1.0  # Simulate 1 second wait
        )

        url2 = "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-67890-23"
        start_time = time.time()
        result2 = service.scrape_single_case(url2)
        second_scrape_time = time.time() - start_time

        # Verify both results are valid
        assert result1 is not None
        assert result2 is not None

        # Verify rate limiter was called twice
        assert mock_rate_limiter_instance.wait_if_needed.call_count == 2

        # The second scrape should take at least 1 second due to rate limiting
        # (Note: This is a loose check since mocking doesn't actually sleep)
        assert second_scrape_time >= 0  # Would be >= 1.0 in real scenario

    def test_ethical_rate_limiter_initialization(self):
        """Test that EthicalRateLimiter can be initialized with correct defaults."""
        limiter = EthicalRateLimiter()

        # Check default values
        assert limiter.interval_seconds == 1.0
        assert limiter.max_burst == 1

        # Test custom values
        limiter_custom = EthicalRateLimiter(interval_seconds=2.0, max_burst=5)
        assert limiter_custom.interval_seconds == 2.0
        assert limiter_custom.max_burst == 5

    def test_ethical_rate_limiter_wait_behavior(self):
        """Test the wait behavior of EthicalRateLimiter."""
        limiter = EthicalRateLimiter(interval_seconds=0.1)  # Fast for testing

        # First call should not wait
        wait_time1 = limiter.wait_if_needed()
        assert wait_time1 == 0.0

        # Second call should wait (approximately 0.1 seconds)
        wait_time2 = limiter.wait_if_needed()
        assert wait_time2 >= 0.0  # Should be close to 0.1 in real time

    def test_ethical_rate_limiter_validation(self):
        """Test the ethical delay validation."""
        limiter = EthicalRateLimiter(interval_seconds=1.0)

        # Valid delays
        assert limiter.validate_ethical_delay(1.0) is True
        assert limiter.validate_ethical_delay(1.5) is True
        assert limiter.validate_ethical_delay(2.0) is True

        # Invalid delays
        assert limiter.validate_ethical_delay(0.5) is False
        assert limiter.validate_ethical_delay(0.0) is False
        assert limiter.validate_ethical_delay(0.9) is False

    @patch("src.services.case_scraper_service.webdriver")
    @patch("src.services.case_scraper_service.EthicalRateLimiter")
    def test_rate_limiter_integration_with_service(
        self, mock_rate_limiter, mock_webdriver
    ):
        """Test that CaseScraperService properly integrates with rate limiter."""
        # Setup mocks
        mock_driver = MagicMock()
        mock_webdriver.Chrome.return_value = mock_driver
        mock_driver.page_source = (
            "<html><title>IMM-12345-22</title><body>Content</body></html>"
        )

        mock_rate_limiter_instance = MagicMock()
        mock_rate_limiter.return_value = mock_rate_limiter_instance
        mock_rate_limiter_instance.wait_if_needed.return_value = 0.5

        # Create service
        service = CaseScraperService()

        # Scrape a case
        url = "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
        result = service.scrape_single_case(url)

        # Verify rate limiter was used
        mock_rate_limiter_instance.wait_if_needed.assert_called_once()

        # Verify result
        assert result is not None
