"""Integration tests for single case scraping."""

import pytest
from unittest.mock import patch, MagicMock
from src.services.case_scraper_service import CaseScraperService
from src.models.case import Case


class TestSingleCaseScraping:
    """Integration tests for single case scraping functionality."""

    @patch('src.services.case_scraper_service.webdriver')
    @patch('src.services.case_scraper_service.EthicalRateLimiter')
    def test_single_case_scraping_success(self, mock_rate_limiter, mock_webdriver, sample_case_url):
        """Test successful scraping of a single case."""
        # Setup mocks
        mock_driver = MagicMock()
        mock_webdriver.Chrome.return_value = mock_driver
        mock_rate_limiter.return_value.wait_if_needed.return_value = 0.0

        # Mock page content
        mock_driver.page_source = """
        <html>
        <head><title>IMM-12345-22 - Federal Court Case</title></head>
        <body>
        <h1>Case IMM-12345-22</h1>
        <div class="case-content">
        <p>This is the case content.</p>
        <p>More case details here.</p>
        </div>
        </body>
        </html>
        """

        # Create service
        service = CaseScraperService()

        # Test scraping
        result = service.scrape_single_case(sample_case_url)

        # Assertions
        assert isinstance(result, Case)
        assert result.case_id == sample_case_url
        assert "IMM-12345-22" in result.case_number
        assert result.title == "IMM-12345-22 - Federal Court Case"
        assert result.court == "Federal Court"
        assert result.html_content == mock_driver.page_source

        # Verify browser interactions
        mock_webdriver.Chrome.assert_called_once()
        mock_driver.get.assert_called_once_with(sample_case_url)
        mock_driver.quit.assert_called_once()

    @patch('src.services.case_scraper_service.webdriver')
    @patch('src.services.case_scraper_service.EthicalRateLimiter')
    def test_single_case_scraping_with_rate_limiting(self, mock_rate_limiter, mock_webdriver, sample_case_url):
        """Test that rate limiting is applied during scraping."""
        # Setup mocks
        mock_driver = MagicMock()
        mock_webdriver.Chrome.return_value = mock_driver
        mock_driver.page_source = "<html>Test case content</html>"
        mock_rate_limiter.return_value.wait_if_needed.return_value = 0.5

        # Create service
        service = CaseScraperService()

        # Test scraping
        service.scrape_single_case(sample_case_url)

        # Verify rate limiter was used
        mock_rate_limiter.return_value.wait_if_needed.assert_called_once()

    @patch('src.services.case_scraper_service.webdriver')
    @patch('src.services.case_scraper_service.EthicalRateLimiter')
    def test_single_case_scraping_handles_webdriver_error(self, mock_rate_limiter, mock_webdriver, sample_case_url):
        """Test handling of WebDriver errors during scraping."""
        # Setup mock to raise exception
        mock_webdriver.Chrome.side_effect = Exception("WebDriver error")
        mock_rate_limiter.return_value.wait_if_needed.return_value = 0.0

        # Create service
        service = CaseScraperService()

        # Test scraping - should raise exception
        with pytest.raises(Exception, match="WebDriver error"):
            service.scrape_single_case(sample_case_url)

    @patch('src.services.case_scraper_service.webdriver')
    @patch('src.services.case_scraper_service.EthicalRateLimiter')
    def test_single_case_scraping_invalid_url(self, mock_rate_limiter, mock_webdriver):
        """Test scraping with invalid URL."""
        # Create service
        service = CaseScraperService()

        # Test with invalid URL
        with pytest.raises(ValueError, match="Invalid case URL"):
            service.scrape_single_case("not-a-url")

    @patch('src.services.case_scraper_service.webdriver')
    @patch('src.services.case_scraper_service.EthicalRateLimiter')
    def test_single_case_scraping_non_federal_court_url(self, mock_rate_limiter, mock_webdriver):
        """Test scraping with non-Federal Court URL."""
        # Create service
        service = CaseScraperService()

        # Test with non-Federal Court URL
        with pytest.raises(ValueError, match="Not a Federal Court URL"):
            service.scrape_single_case("https://google.com")

    @patch('src.services.case_scraper_service.webdriver')
    @patch('src.services.case_scraper_service.EthicalRateLimiter')
    def test_single_case_scraping_efile_url(self, mock_rate_limiter, mock_webdriver):
        """Test scraping with E-File URL (should be rejected)."""
        # Create service
        service = CaseScraperService()

        # Test with E-File URL
        with pytest.raises(ValueError, match="Invalid case URL"):
            service.scrape_single_case("https://cas-cdc-www02.cas-satj.gc.ca/efiling/login")

    def test_scraper_service_initialization(self):
        """Test that CaseScraperService can be initialized."""
        service = CaseScraperService()
        assert service is not None
        assert hasattr(service, 'scrape_single_case')
        assert hasattr(service, 'emergency_stop')
        assert hasattr(service, 'reset_emergency_stop')
        assert hasattr(service, 'is_emergency_stop_active')
        assert service.is_emergency_stop_active() is False

    @patch('src.services.case_scraper_service.webdriver')
    @patch('src.services.case_scraper_service.EthicalRateLimiter')
    def test_emergency_stop_functionality(self, mock_rate_limiter, mock_webdriver):
        """Test emergency stop functionality."""
        # Setup mocks
        mock_driver = MagicMock()
        mock_webdriver.Chrome.return_value = mock_driver
        mock_driver.page_source = "<html>Test content</html>"
        mock_rate_limiter.return_value.wait_if_needed.return_value = 0.0

        # Create service
        service = CaseScraperService()

        # Initially emergency stop should be inactive
        assert service.is_emergency_stop_active() is False

        # Trigger emergency stop
        service.emergency_stop()
        assert service.is_emergency_stop_active() is True

        # Try to scrape - should raise RuntimeError
        url = "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
        with pytest.raises(RuntimeError, match="Emergency stop active"):
            service.scrape_single_case(url)

        # Reset emergency stop
        service.reset_emergency_stop()
        assert service.is_emergency_stop_active() is False

        # Now scraping should work (would work if not mocked to fail)
        # We don't test the actual scraping here since it's already tested elsewhere