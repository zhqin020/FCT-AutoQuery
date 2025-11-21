"""Case scraping service for Federal Court cases."""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from typing import Optional
from datetime import date
import re

from src.models.case import Case
from src.lib.url_validator import URLValidator
from src.lib.rate_limiter import EthicalRateLimiter
from src.lib.logging_config import get_logger

logger = get_logger()


class CaseScraperService:
    """Service for scraping Federal Court cases."""

    def __init__(self, headless: bool = True, rate_limit_seconds: float = 1.0):
        """Initialize the case scraper service.

        Args:
            headless: Whether to run browser in headless mode
            rate_limit_seconds: Rate limiting interval in seconds
        """
        self.headless = headless
        self.rate_limiter = EthicalRateLimiter(interval_seconds=rate_limit_seconds)
        self._driver: Optional[webdriver.Chrome] = None
        self._emergency_stop = False
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5  # Trigger emergency stop after 5 consecutive errors

    def _setup_driver(self) -> webdriver.Chrome:
        """Setup Chrome WebDriver with appropriate options.

        Returns:
            webdriver.Chrome: Configured Chrome driver
        """
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        logger.info("Chrome WebDriver initialized")
        return driver

    def _get_driver(self) -> webdriver.Chrome:
        """Get or create WebDriver instance.

        Returns:
            webdriver.Chrome: WebDriver instance
        """
        if self._driver is None:
            self._driver = self._setup_driver()
        return self._driver

    def _extract_case_title(self, html_content: str) -> str:
        """Extract case title from HTML content.

        Args:
            html_content: HTML content of the page

        Returns:
            str: Extracted case title
        """
        # Try to extract from title tag first
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
        if title_match:
            return title_match.group(1).strip()

        # Fallback: look for case number in content
        case_match = re.search(r'IMM-[A-Z0-9-]+', html_content, re.IGNORECASE)
        if case_match:
            return f"Case {case_match.group(0).upper()}"

        return "Federal Court Case"

    def _extract_case_number(self, url: str, html_content: str) -> str:
        """Extract case number from URL or HTML content.

        Args:
            url: Case URL
            html_content: HTML content

        Returns:
            str: Case number
        """
        # Try URL first
        case_number = URLValidator.extract_case_number_from_url(url)
        if case_number:
            return case_number

        # Try HTML content
        case_match = re.search(r'IMM-[A-Z0-9-]+', html_content, re.IGNORECASE)
        if case_match:
            return case_match.group(0).upper()

        raise ValueError("Could not extract case number from URL or content")

    def _extract_case_date(self, html_content: str) -> date:
        """Extract case date from HTML content.

        Args:
            html_content: HTML content

        Returns:
            date: Case date (defaults to today if not found)
        """
        # Look for date patterns in HTML
        # This is a simplified implementation - real implementation would need
        # more sophisticated date parsing
        date_patterns = [
            r'(\d{4}-\d{2}-\d{2})',  # YYYY-MM-DD
            r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
            r'(\d{4}/\d{2}/\d{2})',  # YYYY/MM/DD
        ]

        for pattern in date_patterns:
            match = re.search(pattern, html_content)
            if match:
                date_str = match.group(1)
                try:
                    # Simple date parsing - would need more robust implementation
                    if '-' in date_str:
                        y, m, d = date_str.split('-')
                    elif '/' in date_str:
                        parts = date_str.split('/')
                        if len(parts[0]) == 4:  # YYYY/MM/DD
                            y, m, d = parts
                        else:  # MM/DD/YYYY
                            m, d, y = parts
                    else:
                        continue

                    return date(int(y), int(m), int(d))
                except (ValueError, IndexError):
                    continue

        # Default to today's date if no date found
        from datetime import date as date_class
        return date_class.today()

    def scrape_single_case(self, url: str) -> Case:
        """Scrape a single case from the given URL.

        Args:
            url: URL of the case to scrape

        Returns:
            Case: Scraped case data

        Raises:
            ValueError: If URL is invalid or case cannot be scraped
        """
        # Check for emergency stop
        if self._emergency_stop:
            raise RuntimeError("Emergency stop active - scraping operations halted for compliance reasons")

        # Validate URL
        is_valid, reason = URLValidator.validate_case_url(url)
        if not is_valid:
            raise ValueError(f"Invalid case URL: {reason}")

        logger.info(f"Starting scrape of case: {url}")

        # Apply rate limiting
        wait_time = self.rate_limiter.wait_if_needed()
        if wait_time > 0:
            logger.info(".2f")

        try:
            # Get WebDriver
            driver = self._get_driver()

            # Navigate to page
            logger.debug(f"Navigating to: {url}")
            driver.get(url)

            # Wait for page to load (simple implementation)
            import time
            time.sleep(2)  # Would be better with WebDriverWait

            # Get page content
            html_content = driver.page_source
            logger.debug(f"Retrieved HTML content, length: {len(html_content)}")

            # Extract case data
            title = self._extract_case_title(html_content)
            case_number = self._extract_case_number(url, html_content)
            case_date = self._extract_case_date(html_content)

            # Create case object
            case = Case.from_url(
                url=url,
                case_number=case_number,
                title=title,
                court="Federal Court",
                case_date=case_date,
                html_content=html_content
            )

            logger.info(f"Successfully scraped case: {case_number}")
            return case

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"Failed to scrape case {url}: {e}")

            # Check for compliance violations that should trigger emergency stop
            if self._consecutive_errors >= self._max_consecutive_errors:
                logger.error(f"Too many consecutive errors ({self._consecutive_errors}) - triggering emergency stop")
                self.emergency_stop()

            raise
        else:
            # Reset consecutive error counter on successful scrape
            self._consecutive_errors = 0
        finally:
            # Always cleanup after scraping
            self.cleanup()

    def emergency_stop(self) -> None:
        """Trigger emergency stop for compliance violations."""
        self._emergency_stop = True
        logger.warning("Emergency stop triggered - stopping all scraping operations")

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop flag."""
        self._emergency_stop = False
        logger.info("Emergency stop reset - scraping operations can resume")

    def is_emergency_stop_active(self) -> bool:
        """Check if emergency stop is active."""
        return self._emergency_stop

    def cleanup(self) -> None:
        """Clean up WebDriver resources."""
        if self._driver:
            try:
                self._driver.quit()
                logger.info("WebDriver cleaned up")
            except Exception as e:
                logger.warning(f"Error during WebDriver cleanup: {e}")
            finally:
                self._driver = None

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()