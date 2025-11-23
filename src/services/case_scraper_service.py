"""Case scraping service for Federal Court cases using search form."""

import time
from datetime import date
from typing import Optional, Tuple

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from src.lib.logging_config import get_logger
from src.lib.rate_limiter import EthicalRateLimiter
from src.lib.url_validator import URLValidator
from src.models.case import Case
from src.models.docket_entry import DocketEntry

logger = get_logger()


class CaseScraperService:
    """Service for scraping Federal Court cases using search form."""

    BASE_URL = "https://www.fct-cf.ca/en/court-files-and-decisions/court-files"

    def __init__(self, headless: bool = True):
        """Initialize the case scraper service.

        Args:
            headless: Whether to run browser in headless mode
        """
        self.headless = headless
        self.rate_limiter = EthicalRateLimiter()  # 3-6s random delay
        self._driver: Optional[webdriver.Chrome] = None
        self._initialized = False

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
        options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        )

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

    def initialize_page(self) -> None:
        """Initialize the court files page and set up search form.

        Raises:
            Exception: If page initialization fails
        """
        driver = self._get_driver()

        try:
            logger.info("Loading court files page")
            driver.get(self.BASE_URL)

            # Wait for page to load
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Click "Search by court number" tab
            logger.info("Switching to search tab")
            search_tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Search by court number"))
            )
            search_tab.click()

            # Wait for tab content to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "courtNumber"))
            )

            # Select "Federal Court" in dropdown
            logger.info("Selecting Federal Court")
            court_select = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "court"))
            )
            court_select.click()

            # Wait for options and select Federal Court
            federal_option = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//option[@value='Federal Court']")
                )
            )
            federal_option.click()

            self._initialized = True
            logger.info("Page initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize page: {e}")
            raise

    def search_case(self, case_number: str) -> bool:
        """Search for a specific case number.

        Args:
            case_number: Case number to search (e.g., IMM-12345-25)

        Returns:
            bool: True if case found, False if no results
        """
        if not self._initialized:
            self.initialize_page()

        driver = self._get_driver()

        try:
            # Apply rate limiting
            self.rate_limiter.wait_if_needed()

            # Clear and input case number
            logger.info(f"Searching for case: {case_number}")
            case_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "courtNumber"))
            )
            case_input.clear()
            case_input.send_keys(case_number)

            # Click submit
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit']"))
            )
            submit_button.click()

            # Wait for results
            time.sleep(2)  # Brief wait for results to load

            # Check for "No data available"
            try:
                no_data = driver.find_element(
                    By.XPATH, "//td[contains(text(), 'No data available')]"
                )
                logger.info(f"No results found for case: {case_number}")
                return False
            except NoSuchElementException:
                pass

            # Check for results table
            try:
                results_table = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//table"))
                )
                logger.info(f"Results found for case: {case_number}")
                return True
            except TimeoutException:
                logger.warning(f"No results table found for case: {case_number}")
                return False

        except Exception as e:
            logger.error(f"Error searching case {case_number}: {e}")
            return False

    def scrape_case_data(
        self, case_number: str
    ) -> Tuple[Optional[Case], list[DocketEntry]]:
        """Scrape case data from the modal after clicking More.

        Args:
            case_number: Case number being scraped

        Returns:
            Tuple of (Case, list of DocketEntry) or (None, []) if failed
        """
        driver = self._get_driver()

        try:
            # Click the "More" link
            logger.info(f"Clicking More for case: {case_number}")
            more_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "More"))
            )
            more_link.click()

            # Wait for modal to appear
            modal = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "modal-content"))
            )

            # Extract header information
            case_data = self._extract_case_header(modal)

            # Extract docket entries
            docket_entries = self._extract_docket_entries(modal)

            # Create Case object
            case = Case(case_id=case_number, **case_data)

            # Close modal
            self._close_modal()

            logger.info(f"Successfully scraped case: {case_number}")
            return case, docket_entries

        except Exception as e:
            logger.error(f"Error scraping case {case_number}: {e}")
            # Try to close modal if open
            try:
                self._close_modal()
            except:
                pass
            return None, []

    def _extract_case_header(self, modal_element) -> dict:
        """Extract case header information from modal.

        Args:
            modal_element: Modal element

        Returns:
            dict: Case header data
        """
        data = {}

        # Field mappings: label text -> field name
        field_mappings = {
            "Court File No.": "case_id",  # But we already have it
            "Type": "case_type",
            "Type of Action": "action_type",
            "Nature of Proceeding": "nature_of_proceeding",
            "Filing Date": "filing_date",
            "Office": "office",
            "Style of Cause": "style_of_cause",
            "Language": "language",
        }

        for label_text, field_name in field_mappings.items():
            try:
                # Find label and get following element
                label = modal_element.find_element(
                    By.XPATH, f".//label[contains(text(), '{label_text}')]"
                )
                # Get the next sibling or associated input/value
                value_element = label.find_element(By.XPATH, "following-sibling::*[1]")
                value = value_element.text.strip() if value_element.text else ""

                if field_name == "filing_date" and value:
                    # Parse date
                    try:
                        data[field_name] = date.fromisoformat(value)
                    except:
                        data[field_name] = None
                else:
                    data[field_name] = value if value else None

            except NoSuchElementException:
                data[field_name] = None
                logger.debug(f"Could not find field: {label_text}")

        return data

    def _extract_docket_entries(self, modal_element) -> list[DocketEntry]:
        """Extract docket entries from modal table.

        Args:
            modal_element: Modal element

        Returns:
            list: List of DocketEntry objects
        """
        entries = []

        try:
            # Find the Recorded Entries table
            table = modal_element.find_element(By.XPATH, ".//table")

            # Get table rows (skip header)
            rows = table.find_elements(By.TAG_NAME, "tr")[1:]

            for i, row in enumerate(rows, 1):
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 4:
                        doc_id = i  # Use row index as doc_id
                        entry_date_str = cells[0].text.strip()
                        entry_office = cells[1].text.strip()
                        summary = cells[2].text.strip()

                        # Parse date
                        entry_date = None
                        if entry_date_str:
                            try:
                                entry_date = date.fromisoformat(entry_date_str)
                            except:
                                pass

                        entry = DocketEntry(
                            case_id="",  # Will be set later
                            doc_id=doc_id,
                            entry_date=entry_date,
                            entry_office=entry_office if entry_office else None,
                            summary=summary if summary else None,
                        )
                        entries.append(entry)

                except Exception as e:
                    logger.warning(f"Error parsing docket entry row {i}: {e}")
                    continue

        except NoSuchElementException:
            logger.warning("No docket entries table found")

        return entries

    def _close_modal(self) -> None:
        """Close the modal dialog."""
        driver = self._get_driver()

        try:
            # Try different close methods
            close_selectors = [
                (By.CLASS_NAME, "close"),
                (By.XPATH, "//button[contains(text(), 'Close')]"),
                (By.XPATH, "//button[contains(text(), 'Fermer')]"),
                (By.XPATH, "//span[@aria-hidden='true' and contains(text(), '×')]"),
            ]

            for by, selector in close_selectors:
                try:
                    close_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((by, selector))
                    )
                    close_button.click()
                    logger.debug("Modal closed successfully")
                    return
                except:
                    continue

            # Fallback: refresh page
            logger.warning("Could not close modal, refreshing page")
            driver.refresh()

        except Exception as e:
            logger.error(f"Error closing modal: {e}")
            driver.refresh()

    def scrape_single_case(self, url: str) -> Case:
        """Scrape a single case from the given URL.

        Args:
            url: The case URL to scrape

        Returns:
            Case: The scraped case data

        Raises:
            ValueError: If URL is invalid
        """
        if not URLValidator.validate_case_url(url)[0]:
            raise ValueError("Invalid case URL")

        self.rate_limiter.wait_if_needed()

        driver = self._get_driver()
        driver.get(url)

        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "title"))
        )

        # Extract data from page
        title = driver.title
        html_content = driver.page_source

        # Extract case number from URL
        case_number = URLValidator.extract_case_number_from_url(url)
        if not case_number:
            raise ValueError("Could not extract case number from URL")

        # Create case
        case = Case.from_url(
            url=url,
            case_number=case_number,
            title=title,
            court="Federal Court",
            case_date=date.today(),  # Placeholder
            html_content=html_content,
        )

        return case

    def is_emergency_stop_active(self) -> bool:
        """Check if emergency stop is active.

        Returns:
            bool: True if emergency stop is active
        """
        return False

    def close(self) -> None:
        """Close the WebDriver."""
        if self._driver:
            self._driver.quit()
            self._driver = None
            logger.info("WebDriver closed")
