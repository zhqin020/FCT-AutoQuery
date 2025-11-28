"""Case scraping service for Federal Court cases using search form."""

import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from src.lib.logging_config import get_logger
from src.lib.config import Config
from selenium.common.exceptions import WebDriverException
from src.lib.rate_limiter import EthicalRateLimiter
from src.lib.url_validator import URLValidator
from src.models.case import Case
from src.models.docket_entry import DocketEntry

logger = get_logger()


def _parse_date_str(s: str):
    """Parse a date string into a date object or return None.

    This function mirrors the parsing logic previously embedded inside
    `_extract_case_header` and is extracted to allow unit testing.
    """
    if not s:
        return None
    s = s.strip()
    # Try ISO first
    try:
        return date.fromisoformat(s)
    except Exception:
        pass

    # Try common formats
    fmts = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%B %d, %Y",
        "%d %B %Y",
        "%Y/%m/%d",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue

    return None


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
        # Restart tracking
        self._restart_count = 0
        self._max_restarts = Config.get_max_driver_restarts()
        # search_mode: 'court_number' uses the courtNumber input; 'generic' uses the site-wide search input
        self._search_mode: str = "court_number"

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
        # Reduce blocking time on driver.get by returning after DOMContentLoaded
        try:
            options.page_load_strategy = "eager"
        except Exception:
            # Older selenium versions may not support attribute assignment
            options.set_capability("pageLoadStrategy", "eager")

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

        # Quick liveness check: try a cheap property access
        try:
            # Accessing current_window_handle is a lightweight way to detect
            # if the session has been terminated.
            _ = self._driver.current_window_handle
            return self._driver
        except Exception as exc:
            logger.warning(f"WebDriver appears dead or unresponsive (attempting restart): {exc}")
            try:
                return self._restart_driver()
            except Exception:
                # If restart failed, re-raise original exception
                raise

    def _dismiss_cookie_banner(self, driver) -> None:
        """Try common cookie/consent banner selectors and dismiss them.

        This is best-effort: we try several common XPaths and click the
        first clickable match using a JS click to avoid overlay blocking.
        """
        # Common button texts and simple heuristics (case-insensitive)
        xpaths = [
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept all')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'i accept')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]",
            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]",
            "//button[contains(@id, 'cookie') or contains(@class, 'cookie')]",
            "//*[contains(@class, 'cookie') and (self::button or self::a)]",
        ]

        # Fast, best-effort approach: scan for matching elements without long waits.
        for xp in xpaths:
            try:
                els = driver.find_elements(By.XPATH, xp)
                for el in els:
                    try:
                        # Prefer JS click to avoid overlay issues
                        driver.execute_script("arguments[0].click();", el)
                        logger.info(f"Dismissed cookie/consent banner using xpath: {xp}")
                        time.sleep(0.2)
                        return
                    except Exception:
                        try:
                            el.click()
                            logger.info(f"Dismissed cookie/consent banner using xpath (native click): {xp}")
                            time.sleep(0.2)
                            return
                        except Exception:
                            continue
            except Exception:
                continue

    def _safe_send_keys(self, driver, element, text: str) -> None:
        """Safely send keys to an element, using JS fallback if necessary."""
        try:
            element.clear()
        except Exception:
            # ignore clear failures
            pass

        try:
            element.send_keys(text)
            return
        except Exception:
            # Fallback: set value via JS and dispatch input events
            try:
                driver.execute_script(
                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input'));",
                    element,
                    text,
                )
                return
            except Exception as e:
                logger.debug(f"_safe_send_keys JS fallback failed: {e}")
                raise

    def _submit_search(self, driver, input_element) -> None:
        """Find and click a submit control related to the input_element, with fallbacks."""
        # Try to find a submit button in the same form
        try:
            submit = input_element.find_element(
                By.XPATH, "ancestor::form//button[@type='submit']"
            )
        except Exception:
            try:
                submit = input_element.find_element(
                    By.XPATH, "ancestor::form//input[@type='submit']"
                )
            except Exception:
                submit = None

        if submit is None:
            # Try common clickable submit elements on the page
            try:
                submit = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//button[@type='submit' or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'search') or contains(@class, 'search')] | //input[@type='submit']",
                        )
                    )
                )
            except Exception:
                submit = None

        if submit is None:
            # As a last resort, submit the form via JS
            try:
                driver.execute_script(
                    "var f = arguments[0].closest('form'); if(f){f.submit();} else {document.forms[0] && document.forms[0].submit();}",
                    input_element,
                )
                return
            except Exception as e:
                logger.debug(f"JS form submit fallback failed: {e}")
                raise

        # Click using JS if normal click fails
        try:
            submit.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", submit)
            except Exception as e:
                logger.debug(f"Submit click failed: {e}")
                raise

    def initialize_page(self) -> None:
        """Initialize the court files page and set up search form.

        Raises:
            Exception: If page initialization fails
        """
        driver = self._get_driver()

        try:
            logger.info("Loading court files page")
            driver.get(self.BASE_URL)

            # Wait up to 30s for the page body to be present (restore stable behavior)
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Best-effort: dismiss cookie/consent banners that may block clicks
            try:
                self._dismiss_cookie_banner(driver)
            except Exception:
                # Non-fatal if dismissal fails
                logger.debug("Cookie dismissal attempt failed or not needed")

            # Click "Search by court number" tab
            logger.info("Switching to search tab")
            # Use a stable wait for the tab to become clickable (10s)
            search_tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Search by court number"))
            )
            try:
                search_tab.click()
            except Exception:
                driver.execute_script("arguments[0].click();", search_tab)

            # Wait for tab content to load. The site has changed ids over time
            # so try a small set of likely input ids and accept whichever appears.
            possible_case_inputs = [
                "courtNumber",
                "selectCourtNumber",
                "selectRetcaseCourtNumber",
            ]
            found_case_input = None
            for pid in possible_case_inputs:
                try:
                    WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.ID, pid))
                    )
                    found_case_input = pid
                    break
                except Exception:
                    continue

            # Persist discovered case input id and mark initialized to avoid
            # repeated page initialization on subsequent searches.
            try:
                if found_case_input:
                    # Cache the input id for potential later use and mark as initialized
                    self._case_input_id = found_case_input
                    # Default search mode is court_number when a dedicated input is found
                    self._search_mode = "court_number" if found_case_input != "searchd" else "generic"
                    self._initialized = True
                    logger.info(f"Initialized search tab using input id: {found_case_input}")
                else:
                    # No specific case input found yet; leave initialization
                    # state unset so fallback/exception handling can run.
                    logger.debug("No dedicated case input detected during initialize_page")
            except Exception:
                # Non-fatal; proceed without caching if something goes wrong
                logger.debug("Failed to persist initialization state", exc_info=True)
    

        except Exception as e:
            # Capture diagnostics: page source and screenshot to help debug failures
            try:
                import os
                from datetime import datetime as _dt
                from datetime import timezone as _tz
                from pathlib import Path

                ts = _dt.now(_tz.utc).strftime("%Y%m%d_%H%M%S")
                log_dir = Path("logs")
                os.makedirs(log_dir, exist_ok=True)

                screenshot_path = log_dir / f"initialize_page_{ts}.png"
                page_source_path = log_dir / f"initialize_page_{ts}.html"

                try:
                    driver.save_screenshot(str(screenshot_path))
                    with open(page_source_path, "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    logger.error(f"Saved screenshot to {screenshot_path}")
                    logger.error(f"Saved page source to {page_source_path}")
                except Exception as write_err:
                    logger.error(f"Failed to write diagnostic artifacts: {write_err}")

                # Log some driver details
                try:
                    caps = driver.capabilities
                    logger.error(f"Driver capabilities: {caps}")
                except Exception:
                    pass
            except Exception:
                # Best-effort diagnostics; don't mask original exception
                pass

            logger.error(f"Failed to initialize page: {e}")

            # Fallback: try site-wide search page which contains a simpler search input (`#searchd`)
            try:
                fallback_url = "https://www.fct-cf.ca/en/search"
                logger.info(f"Attempting fallback to {fallback_url}")
                driver.get(fallback_url)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "searchd"))
                )
                # Use generic search mode
                self._search_mode = "generic"
                self._initialized = True
                logger.info(
                    "Fallback: initialized using generic search input (#searchd)"
                )
                return
            except Exception as fallback_exc:
                logger.error(f"Fallback initialize failed: {fallback_exc}")
                raise

    def _restart_driver(self) -> webdriver.Chrome:
        """Attempt to restart the WebDriver up to configured limit.

        Returns a fresh WebDriver instance or raises if the max restarts
        have been exceeded.
        """
        # Quit existing driver if present
        try:
            if self._driver is not None:
                try:
                    self._driver.quit()
                except Exception:
                    logger.debug("Existing driver quit failed during restart", exc_info=True)
                finally:
                    self._driver = None
        except Exception:
            # best-effort
            self._driver = None

        self._restart_count += 1
        if self._restart_count > self._max_restarts:
            logger.error(f"Exceeded max WebDriver restart attempts ({self._max_restarts})")
            raise RuntimeError("Exceeded max WebDriver restart attempts")

        logger.info(f"Restarting WebDriver (attempt {self._restart_count}/{self._max_restarts})")
        # Small backoff before creating a new driver
        time.sleep(1)
        try:
            self._driver = self._setup_driver()
            # Reset initialization flag so callers can re-run page init if needed
            self._initialized = False
            return self._driver
        except Exception as e:
            logger.exception(f"Failed to restart WebDriver: {e}")
            raise

    def _parse_label_value_table(self, modal_element, label_variants: dict) -> dict:
        """Parse tables where first cell is label and second cell is value.

        Returns a dict of canonical fields found.
        """
        data_out = {}
        try:
            tables = modal_element.find_elements(By.XPATH, ".//table")
            for t in tables:
                try:
                    rows = t.find_elements(By.TAG_NAME, "tr")
                    for r in rows:
                        try:
                            cells = r.find_elements(By.TAG_NAME, "td")
                            if len(cells) >= 2:
                                label = cells[0].text.strip().lower()
                                val = cells[1].text.strip()
                                for key, fld in label_variants.items():
                                    if key in label:
                                        if fld == "filing_date":
                                            data_out[fld] = _parse_date_str(val)
                                        else:
                                            data_out[fld] = val or None
                                        break
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass

        return data_out

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
            # Try the search up to two times: initial attempt, then one retry
            # that re-initializes the page. This mirrors the harness retry
            # strategy for flaky client-side population.
            for attempt in range(2):
                # Apply rate limiting
                self.rate_limiter.wait_if_needed()

                # Clear and input case number
                logger.info(
                    f"Searching for case: {case_number} (attempt {attempt + 1})"
                )
                # Prefer the dedicated court number input, but fall back to the generic site search.
                possible_case_inputs = [
                    "courtNumber",
                    "selectCourtNumber",
                    "selectRetcaseCourtNumber",
                    "searchd",
                ]
                case_input = None
                for cid in possible_case_inputs:
                    try:
                        case_input = WebDriverWait(driver, 2).until(
                            EC.presence_of_element_located((By.ID, cid))
                        )
                        break
                    except Exception:
                        continue
                if case_input is None:
                    # As a last resort try to find any text input inside the search tab
                    try:
                        case_input = WebDriverWait(driver, 3).until(
                            EC.presence_of_element_located(
                                (By.XPATH, "//input[@type='text']")
                            )
                        )

                    except Exception:
                        case_input = None
                # Dismiss any overlay that appeared just before interacting
                try:
                    self._dismiss_cookie_banner(driver)
                except Exception:
                    pass

                if case_input is None:
                    logger.debug(f"Could not locate a search input for attempt {attempt + 1}")
                    # If this was the first attempt, re-initialize and retry
                    if attempt == 0:
                        try:
                            self.initialize_page()
                            driver = self._get_driver()
                            continue
                        except Exception:
                            pass
                    return False

                # Use robust send keys with JS fallback
                self._safe_send_keys(driver, case_input, case_number)

                # Small stabilization pause to allow client-side handlers
                # (e.g. input listeners) to process the entered value before
                # submitting. Matches the harness behavior which waits after
                # typing the case number.
                time.sleep(2)

                # Try a tab-specific submit first (more reliable on this site)
                try:
                    tab_submit = driver.find_element(By.ID, "tab02Submit")
                    try:
                        driver.execute_script("arguments[0].click();", tab_submit)
                        logger.debug("Clicked tab02Submit")
                    except Exception:
                        tab_submit.click()
                except Exception:
                    # Fall back to the generic submit helper
                    try:
                        self._submit_search(driver, case_input)
                    except Exception as submit_err:
                        logger.warning(f"Submit attempt failed: {submit_err}")
                        # Continue and let the wait for results determine outcome

                # Poll for results: check repeatedly for the case row or an explicit
                # 'No data available' marker. Polling is often more reliable than
                # relying on DataTables' async hooks.
                found_row = False
                no_data = False
                for _ in range(40):
                    if driver.find_elements(
                        By.XPATH, "//td[contains(text(), 'No data available')]"
                    ):
                        no_data = True
                        break
                    if driver.find_elements(
                        By.XPATH,
                        f"//table//td[contains(normalize-space(.), '{case_number}')]",
                    ):
                        found_row = True
                        break
                    time.sleep(0.5)

                if no_data:
                    logger.info(f"No results found for case: {case_number}")
                    return False

                if found_row:
                    logger.info(f"Results found for case: {case_number}")
                    return True

                # As a final fallback, check for any table rows present
                if driver.find_elements(By.XPATH, "//table//tbody//tr"):
                    logger.info(f"Table rows present but specific case not detected: {case_number}")
                    return True

                # If first attempt failed, re-initialize and retry
                if attempt == 0:
                    try:
                        logger.info(
                            "Retrying search: re-initializing page and retrying"
                        )
                        self.initialize_page()
                        driver = self._get_driver()
                        continue
                    except Exception:
                        pass

                # Save diagnostics before giving up
                try:
                    logs = Path("logs")
                    logs.mkdir(parents=True, exist_ok=True)
                    from datetime import timezone as _tz

                    ts = datetime.now(_tz.utc).strftime("%Y%m%d_%H%M%S")
                    page_path = logs / f"search_no_rows_{case_number}_{ts}.html"
                    with open(page_path, "w", encoding="utf-8") as fh:
                        fh.write(driver.page_source)
                    try:
                        png_path = logs / f"search_no_rows_{case_number}_{ts}.png"
                        driver.save_screenshot(str(png_path))
                    except Exception:
                        pass
                    logger.info(f"Saved diagnostics to {page_path}")
                except Exception:
                    logger.debug("Failed to save search diagnostics", exc_info=True)

                logger.warning(f"No results table found for case: {case_number}")
                return False

        except Exception as e:
            logger.error(f"Error searching case {case_number}: {e}")
            return False

    def scrape_case_data(self, case_number: str) -> Optional[Case]:
        """Scrape case data from the modal after clicking More.

        Args:
            case_number: Case number being scraped

        Returns:
            Case object on success, or None on failure. The returned Case will
            have a dynamic attribute `docket_entries` (list) attached when
            entries were extracted to preserve downstream access.
        """
        driver = self._get_driver()

        try:
            # Click the "More" link — prefer locating the control inside the
            # result row that contains the case_number. This is more robust
            # against pages that show many results or render 'More' controls per-row.
            logger.info(f"Clicking More for case: {case_number}")
            more_link = None
            # If a fallback (row click) causes the modal to appear without a
            # clickable per-row control, we capture that here and continue
            # the flow without needing to click `more_link`.
            prefound_modal = None

            # First, try to find the target row containing the case number
            try:
                rows = driver.find_elements(By.XPATH, "//table//tbody//tr")
                target_row = None
                for r in rows:
                    try:
                        first = r.find_element(By.TAG_NAME, "td")
                        if case_number in (first.text or ""):
                            target_row = r
                            break
                    except Exception:
                        continue
            except Exception:
                target_row = None

                # Instrumentation: save current page HTML and a snippet for this
                # target row to `logs/` to help diagnose failures where the CLI
                # cannot find/click the per-row "More" control.
                # Wait for the client-side DataTable to populate the target row
                try:
                    WebDriverWait(driver, 12).until(
                        EC.presence_of_element_located(
                            (
                                By.XPATH,
                                f"//table//td[contains(normalize-space(.), '{case_number}')]",
                            )
                        )
                    )
                except Exception:
                    # If the wait fails, continue — downstream logic will handle missing row
                    logger.debug(f"Timed out waiting for case row to appear: {case_number}")

                # Locate the target row containing the case number (again, after wait)
                try:
                    rows = driver.find_elements(By.XPATH, "//table//tbody//tr")
                    target_row = None
                    for r in rows:
                        try:
                            first = r.find_element(By.TAG_NAME, "td")
                            if case_number in (first.text or ""):
                                target_row = r
                                break
                        except Exception:
                            continue
                except Exception:
                    target_row = None

                # Instrumentation: save current page HTML and a snippet for this
                # target row to `logs/` to help diagnose failures where the CLI
                # cannot find/click the per-row "More" control. Save these after
                # waiting for the table to populate to avoid empty snippets.
                try:
                    logs = Path("logs")
                    logs.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    # full page
                    page_path = logs / f"cli_page_{case_number}_{ts}.html"
                    try:
                        with open(page_path, "w", encoding="utf-8") as fh:
                            fh.write(driver.page_source)
                        logger.info(f"Saved full page HTML to {page_path}")
                    except Exception:
                        logger.debug("Failed to save full page HTML", exc_info=True)

                    # row snippet — use outerHTML on the located WebElement to avoid
                    # extracting from the raw page_source which may be stale.
                    snippet_path = logs / f"row_snippet_{case_number}_{ts}.html"
                    try:
                        snippet_html = ""
                        if target_row is not None:
                            snippet_html = target_row.get_attribute("outerHTML") or ""
                        else:
                            try:
                                el = driver.find_element(
                                    By.XPATH,
                                    f"//td[contains(normalize-space(.), '{case_number}')]",
                                )
                                tr = el.find_element(By.XPATH, "ancestor::tr[1]")
                                snippet_html = tr.get_attribute("outerHTML") or ""
                            except Exception:
                                snippet_html = ""

                        with open(snippet_path, "w", encoding="utf-8") as fh:
                            fh.write("<html><body>\n")
                            fh.write(snippet_html)
                            fh.write("\n</body></html>")
                        logger.info(f"Saved row snippet HTML to {snippet_path}")
                    except Exception:
                        logger.debug("Failed to save row snippet", exc_info=True)
                    # also try to save a screenshot for visual debugging
                    try:
                        png_path = logs / f"screenshot_{case_number}_{ts}.png"
                        driver.save_screenshot(str(png_path))
                        logger.info(f"Saved screenshot to {png_path}")
                    except Exception:
                        logger.debug("Failed to save screenshot", exc_info=True)
                except Exception:
                    logger.debug("Instrumentation write failed", exc_info=True)

            # Pre-click extraction from the target row (case id, style, nature)
            pre_click_case = None
            pre_click_style = None
            pre_click_nature = None
            try:
                if target_row is not None:
                    try:
                        table_el = target_row.find_element(By.XPATH, "ancestor::table")
                    except Exception:
                        table_el = None

                    headers = []
                    try:
                        if table_el is not None:
                            headers = [
                                h.text.strip().lower()
                                for h in table_el.find_elements(
                                    By.XPATH, ".//thead//th"
                                )
                                if h.text and h.text.strip()
                            ]
                    except Exception:
                        headers = []

                    cols = target_row.find_elements(By.TAG_NAME, "td")
                    texts = [c.text.strip() for c in cols]

                    def get_by_header(names):
                        for n in names:
                            for i, h in enumerate(headers):
                                if n in h:
                                    if i < len(texts):
                                        return texts[i]
                        return None

                    pre_click_case = get_by_header(
                        [
                            "court file",
                            "court number",
                            "court no",
                            "court file no",
                            "court number",
                        ]
                    ) or (texts[0] if len(texts) > 0 else None)
                    pre_click_style = get_by_header(
                        ["style", "style of cause", "style of cause/"]
                    ) or (texts[1] if len(texts) > 1 else None)
                    pre_click_nature = get_by_header(
                        ["nature", "nature of proceeding"]
                    ) or (texts[2] if len(texts) > 2 else None)

                    logger.debug(f"Pre-click extracted: case={pre_click_case} style={pre_click_style} nature={pre_click_nature}")
            except Exception:
                logger.debug("Pre-click extraction failed", exc_info=True)

            # candidate xpaths to find More control within a row
            candidate_xpaths = [
                ".//button[@id='re']",
                ".//a[@id='re']",
                ".//button[@id='more']",
                ".//a[@id='more']",
                ".//button[.//i[contains(@class,'fa-search-plus')]]",
                ".//a[.//i[contains(@class,'fa-search-plus')]]",
                ".//button[.//i[contains(@class,'fa-search')]]",
                ".//a[.//i[contains(@class,'fa-search')]]",
                ".//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]",
                ".//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]",
                ".//button[contains(@data-target, 'Modal') or contains(@data-toggle, 'modal')]",
                ".//a[contains(@href, 'javascript') or contains(@href, '#') or contains(@data-target, 'Modal')]",
            ]

            if target_row is not None:
                for xp in candidate_xpaths:
                    try:
                        more_link = target_row.find_element(By.XPATH, xp)
                        logger.info(f"Found More element in row via: {xp}")
                        break
                    except Exception:
                        continue

            # If not found in-row, fall back to the previous global strategies
            if more_link is None:
                try:
                    more_link = WebDriverWait(driver, 6).until(
                        EC.element_to_be_clickable((By.LINK_TEXT, "More"))
                    )
                except Exception:
                    # Try case-insensitive xpath for anchors or buttons containing "more"
                    try:
                        more_link = WebDriverWait(driver, 6).until(
                            EC.element_to_be_clickable(
                                (
                                    By.XPATH,
                                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]",
                                )
                            )
                        )
                    except Exception:
                        # As a last resort try any link with title or aria-label 'more'
                        try:
                            more_link = WebDriverWait(driver, 6).until(
                                EC.element_to_be_clickable(
                                    (
                                        By.XPATH,
                                        "//a[@title and contains(translate(@title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')] | //*[(@aria-label) and contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]",
                                    )
                                )
                            )
                        except Exception:
                            more_link = None

            # If still not found, attempt a couple of quick retries (handle race conditions)
            if more_link is None and target_row is not None:
                logger.info(
                    "More control not found initially; retrying within target row"
                )
                for attempt in range(2):
                    time.sleep(0.5)
                    for xp in candidate_xpaths:
                        try:
                            more_link = target_row.find_element(By.XPATH, xp)
                            logger.info(f"Found More element in row on retry {attempt + 1} via: {xp}")
                            break
                        except Exception:
                            continue
                    if more_link is not None:
                        break

            # Last-resort fallback: try clicking the last cell's button/link or the whole row
            if more_link is None:
                try:
                    logger.info(
                        "Attempting fallback: click last-cell button or anchor in the target row"
                    )
                    last_ctl = None
                    if target_row is not None:
                        try:
                            last_ctl = target_row.find_element(
                                By.XPATH, ".//td[last()]//button | .//td[last()]//a"
                            )
                        except Exception:
                            last_ctl = None

                    if last_ctl is not None:
                        more_link = last_ctl
                        logger.info("Using last-cell control as More fallback")
                    else:
                        # Try clicking the row itself (some pages bind click to row)
                        if target_row is not None:
                            try:
                                driver.execute_script(
                                    "arguments[0].click();", target_row
                                )
                                logger.info("Clicked target row as fallback")
                                # Give page a short moment for modal to appear
                                time.sleep(0.5)
                                # Quick check: maybe the row-click already opened the
                                # modal. If so, capture it and continue without
                                # requiring an explicit more_link click.
                                try:
                                    prefound_modal = WebDriverWait(driver, 1).until(
                                        EC.presence_of_element_located(
                                            (By.CLASS_NAME, "modal-content")
                                        )
                                    )
                                    logger.info(
                                        "Modal detected immediately after row-click fallback"
                                    )
                                except Exception:
                                    prefound_modal = None
                            except Exception:
                                logger.info("Row click fallback did not trigger modal")
                except Exception:
                    logger.debug("Fallback attempt failed", exc_info=True)

            # If we still don't have a clickable element and the fallback did
            # not already open the modal, treat this as a failure.
            if more_link is None and prefound_modal is None:
                raise Exception("Could not find 'More' link/button for case")

            # Try normal click first, then JS click fallback. Handle
            # StaleElementReferenceException by re-finding the control and
            # retrying a few times (the page may re-render while we inspect it).
            click_attempts = 3
            clicked = False
            for attempt in range(click_attempts):
                try:
                    more_link.click()
                    clicked = True
                    break
                except StaleElementReferenceException:
                    logger.info(f"More element became stale on click attempt {attempt+1}, retrying")
                    # Re-find the element before retrying
                    more_link = None
                    if target_row is not None:
                        for xp in candidate_xpaths:
                            try:
                                more_link = target_row.find_element(By.XPATH, xp)
                                logger.debug(f"Re-found More element via {xp}")
                                break
                            except Exception:
                                continue
                    if more_link is None:
                        try:
                            more_link = WebDriverWait(driver, 3).until(
                                EC.element_to_be_clickable((By.LINK_TEXT, "More"))
                            )
                        except Exception:
                            try:
                                more_link = WebDriverWait(driver, 3).until(
                                    EC.element_to_be_clickable(
                                        (
                                            By.XPATH,
                                            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]|//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more')]",
                                        )
                                    )
                                )
                            except Exception:
                                more_link = None
                    time.sleep(1)
                    continue
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", more_link)
                        clicked = True
                        break
                    except StaleElementReferenceException:
                        logger.info("More element became stale during JS click, retrying")
                        # clear and let the loop re-find
                        more_link = None
                        time.sleep(1)
                        continue
                    except Exception as click_err:
                        raise click_err

            if not clicked:
                raise Exception("Failed to click 'More' control after retries")

            # Wait for modal to appear. Accept several common modal patterns
            modal = None
            # If the fallback already produced the modal, reuse it.
            if prefound_modal is not None:
                modal = prefound_modal
            else:
                modal_selectors = [
                    (By.CLASS_NAME, "modal-content"),
                    (By.CLASS_NAME, "modal-body"),
                    (By.XPATH, "//div[@role='dialog']"),
                ]
                for by, sel in modal_selectors:
                    try:
                        modal = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((by, sel))
                        )
                        break
                    except Exception:
                        continue

            if modal is None:
                raise Exception("Modal did not appear after clicking More")

            # Extract header information
            # allow a short stabilization so dynamically-inserted modal content
            # (labels, caption, and tables) have time to render — the harness
            # pauses 5s; here a short sleep reduces missing header fields.
            try:
                time.sleep(1)
            except Exception:
                pass
            logger.debug("Extracting case header from modal")
            case_data = self._extract_case_header(modal)
            # Merge pre-click extracted values into modal header when modal lacks them
            try:
                if not case_data.get("case_id") and pre_click_case:
                    case_data["case_id"] = pre_click_case
                if not case_data.get("style_of_cause") and pre_click_style:
                    case_data["style_of_cause"] = pre_click_style
                if not case_data.get("nature_of_proceeding") and pre_click_nature:
                    case_data["nature_of_proceeding"] = pre_click_nature
            except Exception:
                pass
            logger.debug(f"Raw extracted header: {case_data}")

            # Extract docket entries (pass case_number so entries get case_id)
            logger.debug("Extracting docket entries from modal")
            docket_entries = self._extract_docket_entries(modal, case_number)
            logger.debug(f"Extracted {len(docket_entries)} docket entries")

            # Normalize and create Case object
            # Ensure we don't pass duplicate case_id kwarg
            header_case_id = case_data.pop("case_id", None) or case_number
            # Ensure we have basic metadata: url and modal HTML
            try:
                if not case_data.get("url"):
                    case_data["url"] = driver.current_url
            except Exception:
                case_data["url"] = None

            try:
                # capture modal outerHTML to a separate file under logs/
                from datetime import timezone as _tz

                logs = Path("logs")
                logs.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(_tz.utc).strftime("%Y%m%d_%H%M%S")
                safe_id = (header_case_id or case_number).replace("/", "_")
                modal_path = logs / f"modal_{safe_id}_{ts}.html"
                try:
                    # Respect configuration: allow disabling modal HTML capture
                    from src.lib.config import Config

                    if Config.get_save_modal_html():
                        html = (
                            modal.get_attribute("outerHTML")
                            or modal.get_attribute("innerHTML")
                            or ""
                        )
                        with open(modal_path, "w", encoding="utf-8") as mf:
                            mf.write(html)
                        case_data["html_path"] = str(modal_path)
                        logger.info(f"Saved modal HTML to {modal_path}")
                    else:
                        case_data["html_path"] = None
                except Exception:
                    case_data["html_path"] = None
            except Exception:
                case_data["html_path"] = None

            # If style_of_cause missing, attempt to extract it from the
            # previously-located target_row (search results row) which often
            # contains the style in the second cell.
            try:
                if not case_data.get("style_of_cause") and target_row is not None:
                    try:
                        tds = target_row.find_elements(By.TAG_NAME, "td")
                        if len(tds) >= 2:
                            so = (tds[1].text or "").strip()
                            if so:
                                case_data["style_of_cause"] = so
                    except Exception:
                        pass
            except Exception:
                pass
            # Remove any unexpected keys before passing to Case
            allowed = {
                "case_type",
                "action_type",
                "nature_of_proceeding",
                "filing_date",
                "office",
                "style_of_cause",
                "language",
                "url",
                # do not include large HTML content inline in the Case object;
                # modal HTML is saved to logs/ and referenced by `html_path`.
            }
            filtered = {k: v for k, v in case_data.items() if k in allowed}

            case = Case(case_id=header_case_id, **filtered)

            logger.info(f"Successfully scraped case: {header_case_id} (entries={len(docket_entries)})")

            # Build structured payload matching scripts/auto_click_more.py format
            try:
                import json
                from datetime import timezone as _tz

                # Build a clean copy of the header for payload export. Remove
                # the `html_content` key if present and instead include
                # `html_path` (which points to the saved modal HTML file).
                cd = dict(case_data)
                if "html_content" in cd:
                    cd.pop("html_content", None)
                # normalize filing_date to ISO if it's a date object
                try:
                    if (
                        not isinstance(cd.get("filing_date"), str)
                        and cd.get("filing_date") is not None
                    ):
                        cd["filing_date"] = cd["filing_date"].isoformat()
                except Exception:
                    pass

                de_list = []
                for e in docket_entries:
                    if hasattr(e, "to_dict"):
                        try:
                            de_list.append(e.to_dict())
                        except Exception:
                            de_list.append(
                                {
                                    "doc_id": getattr(e, "doc_id", None),
                                    "case_id": getattr(e, "case_id", None),
                                    "entry_date": (
                                        getattr(e, "entry_date", None).isoformat()
                                        if getattr(e, "entry_date", None)
                                        else None
                                    ),
                                    "entry_office": getattr(e, "entry_office", None),
                                    "summary": getattr(e, "summary", None),
                                }
                            )
                    else:
                        de_list.append(
                            {
                                "doc_id": getattr(e, "doc_id", None),
                                "case_id": getattr(e, "case_id", None),
                                "entry_date": (
                                    getattr(e, "entry_date", None).isoformat()
                                    if getattr(e, "entry_date", None)
                                    else None
                                ),
                                "entry_office": getattr(e, "entry_office", None),
                                "summary": getattr(e, "summary", None),
                            }
                        )

                payload = {
                    "case": cd,
                    "docket_entries": de_list,
                    "scraped_at": datetime.now(_tz.utc).isoformat(),
                }

                # Log the structured JSON payload (pretty-printed) to the main log
                logger.info(f"Scraped payload:\n{json.dumps(payload, indent=2, ensure_ascii=False)}")
            except Exception:
                # Non-fatal if logging the payload fails
                logger.debug(
                    "Failed to serialize/log structured payload", exc_info=True
                )

            # Close modal
            self._close_modal()

            # Attach docket entries to the Case object for downstream use
            try:
                case.docket_entries = docket_entries
            except Exception:
                # Best-effort, non-fatal
                pass

            # Log structured output for later inspection
            try:
                logger.debug(f"Case summary: {case.to_dict()}")
            except Exception:
                logger.debug("Case summary not serializable")

            return case

        except Exception as e:
            logger.error(f"Error scraping case {case_number}: {e}")
            # Try to close modal if open
            try:
                self._close_modal()
            except Exception:
                pass
            return None

    def _extract_case_header(self, modal_element) -> dict:
        """Extract case header information from modal.

        Args:
            modal_element: Modal element

        Returns:
            dict: Case header data
        """
        data = {
            "case_id": None,
            "case_type": None,
            "action_type": None,
            "nature_of_proceeding": None,
            "filing_date": None,
            "office": None,
            "style_of_cause": None,
            "language": None,
        }

        # Common label variations -> field name
        label_variants = {
            "court file": "case_id",
            "court file no": "case_id",
            "court file number": "case_id",
            "type": "case_type",
            "type of action": "action_type",
            "nature of proceeding": "nature_of_proceeding",
            "filing date": "filing_date",
            "office": "office",
            "style of cause": "style_of_cause",
            "language": "language",
        }

        # Use module-level date parser for consistency and testability
        from src.services.case_scraper_service import _parse_date_str  # type: ignore

        # Strategy 1: look for table rows where first cell is label and second cell is value
        try:
            parsed = self._parse_label_value_table(modal_element, label_variants)
            for k, v in parsed.items():
                data[k] = v
        except Exception:
            pass

        # Strategy 2: description lists (dt/dd)
        try:
            dts = modal_element.find_elements(By.TAG_NAME, "dt")
            for dt_el in dts:
                try:
                    key_text = dt_el.text.strip().lower()
                    dd = dt_el.find_element(By.XPATH, "following-sibling::dd[1]")
                    val = dd.text.strip()
                    for key, fld in label_variants.items():
                        if key in key_text:
                            if fld == "filing_date":
                                data[fld] = _parse_date_str(val)
                            else:
                                data[fld] = val or None
                            break
                except Exception:
                    continue
        except Exception:
            pass

        # Strategy 3: look for <h5 id="modalTitle"> or a heading containing the case id
        try:
            try:
                title_el = modal_element.find_element(By.ID, "modalTitle")
            except Exception:
                title_el = modal_element.find_element(
                    By.XPATH,
                    ".//h5[contains(., 'Recorded Entry Information') or contains(., 'Recorded Entry')]",
                )

            if title_el:
                # Extract IMM-... pattern from title text
                import re

                txt = title_el.text or ""
                m = re.search(r"(IMM[-–—]\S+\-?\d{2,})", txt)
                if m:
                    data["case_id"] = m.group(1)
        except Exception:
            pass

        # Strategy 4: find <strong>Label :</strong> inside paragraphs and take parent paragraph's text after removing strong texts
        try:
            strongs = modal_element.find_elements(By.XPATH, ".//p//strong")
            # prefer longer label keys first to avoid short-key collisions (e.g., 'type' vs 'type of action')
            sorted_labels = sorted(label_variants.items(), key=lambda kv: -len(kv[0]))
            for s in strongs:
                try:
                    label = s.text.strip().strip(":").lower()
                    parent = s.find_element(By.XPATH, "ancestor::p[1]")
                    full = parent.text.strip()
                    # remove all strong texts inside this parent to leave the value(s)
                    strong_texts = [
                        st.text
                        for st in parent.find_elements(By.XPATH, ".//strong")
                        if st.text
                    ]
                    sval = full
                    for st in strong_texts:
                        sval = sval.replace(st, "")
                    sval = sval.strip(" :\u00a0")

                    # match label to our canonical keys (longest-first)
                    for key, fld in sorted_labels:
                        if key == label or key in label:
                            if fld == "filing_date":
                                data[fld] = _parse_date_str(sval)
                            else:
                                data[fld] = sval or None
                            break
                except Exception:
                    continue
        except Exception:
            pass

        # Strategy 5: some modals render case id, style of cause, and nature on the same paragraph/line
        try:
            import re

            paras = modal_element.find_elements(By.TAG_NAME, "p")
            # prefer paragraphs containing the case id or the phrase 'court file'
            candidate_para = None
            for p in paras:
                try:
                    txt = p.text.strip()
                    if not txt:
                        continue
                    # if it contains the case id we previously found, prefer it
                    if data.get("case_id") and data["case_id"] in txt:
                        candidate_para = txt
                        break
                    # or contains 'court file' label
                    if re.search(r"(?i)court\s*file|court\s*file\s*(no|number)", txt):
                        candidate_para = txt
                        break
                except Exception:
                    continue

            # If paragraph search didn't find it, search all elements for one containing the case id
            if not candidate_para and data.get("case_id"):
                try:
                    elems = modal_element.find_elements(
                        By.XPATH, ".//*[contains(., '%s')]" % data["case_id"]
                    )
                    for el in elems:
                        try:
                            txt = el.text.strip()
                            if not txt:
                                continue
                            candidate_para = txt
                            # prefer ones that also contain nature_of_proceeding if we have it
                            if (
                                data.get("nature_of_proceeding")
                                and data["nature_of_proceeding"] in txt
                            ):
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            # As a final fallback, scan modal text line-by-line and look for a line containing both case id and nature
            if not candidate_para:
                try:
                    all_text = modal_element.text or ""
                    for line in all_text.splitlines():
                        if data.get("case_id") and data["case_id"] in line:
                            if data.get("nature_of_proceeding"):
                                if data["nature_of_proceeding"] in line:
                                    candidate_para = line.strip()
                                    break
                            else:
                                candidate_para = line.strip()
                                break
                except Exception:
                    pass

            if candidate_para:
                # try to extract labeled values
                # 1) style of cause (explicit label)
                m_style = re.search(
                    r"(?i)style of cause\s*[:\-–]?\s*(.+?)(?:\s{2,}|$|\n|(?i)nature of proceeding)",
                    candidate_para,
                )
                if m_style and not data.get("style_of_cause"):
                    data["style_of_cause"] = m_style.group(1).strip()

                # 2) nature of proceeding if missing
                if not data.get("nature_of_proceeding"):
                    m_nature = re.search(
                        r"(?i)nature of proceeding\s*[:\-–]?\s*(.+)$", candidate_para
                    )
                    if m_nature:
                        data["nature_of_proceeding"] = m_nature.group(1).strip()

                # 3) fallback: if we have nature already and no style, attempt to infer style as text between case_id and nature
                if (
                    data.get("case_id")
                    and data.get("nature_of_proceeding")
                    and not data.get("style_of_cause")
                ):
                    ci = data["case_id"]
                    nat = data["nature_of_proceeding"]
                    if ci in candidate_para and nat in candidate_para:
                        # extract substring between ci and nat
                        try:
                            start = candidate_para.index(ci) + len(ci)
                            end = candidate_para.index(nat)
                            mid = candidate_para[start:end].strip(" -:\t\n\r")
                            if mid:
                                # remove common label prefixes
                                mid = re.sub(
                                    r"(?i)style of cause\s*[:\-–]?\s*", "", mid
                                ).strip()
                                if mid:
                                    data["style_of_cause"] = mid
                        except Exception:
                            pass

        except Exception:
            pass

        # Post-process combined fields: some modals include office and language in one
        try:
            import re

            # Normalize excessive whitespace
            for k in ("office", "language"):
                if data.get(k) and isinstance(data[k], str):
                    data[k] = re.sub(r"\s+", " ", data[k]).strip()

            # Language whitelist to detect language tokens (lowercase)
            lang_whitelist = {"english", "french", "en", "fr"}

            # If office contains both office and language separated by multiple spaces or a newline or single space where last token is a language, split them
            office_val = data.get("office")
            if office_val and isinstance(office_val, str):
                # First try the obvious split on two+ spaces or newline
                parts = re.split(r"\s{2,}|\n", office_val)
                parts = [p.strip() for p in parts if p and p.strip()]
                if len(parts) >= 2:
                    data["office"] = parts[0]
                    if not data.get("language"):
                        data["language"] = parts[-1]
                else:
                    # fallback: if last token looks like a language, split on last space
                    tokens = office_val.split()
                    if len(tokens) >= 2 and tokens[-1].lower() in lang_whitelist:
                        data["office"] = " ".join(tokens[:-1])
                        if not data.get("language"):
                            data["language"] = tokens[-1]

            # If language present but contains both values (e.g., 'Toronto English'), try splitting
            lang_val = data.get("language")
            if lang_val and isinstance(lang_val, str):
                # normalize then check
                lv = re.sub(r"\s+", " ", lang_val).strip()
                tokens = lv.split()
                if len(tokens) >= 2:
                    # if last token is a language, set language to it and office to the rest (if missing)
                    if tokens[-1].lower() in lang_whitelist:
                        if not data.get("office"):
                            data["office"] = " ".join(tokens[:-1])
                        data["language"] = tokens[-1]

            # Try to extract style_of_cause from headings or standalone paragraphs if missing
            if not data.get("style_of_cause"):
                try:
                    el = None
                    try:
                        el = modal_element.find_element(
                            By.XPATH,
                            ".//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'style of cause') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'style of cause:') ]",
                        )
                    except Exception:
                        el = None

                    if el:
                        txt = el.text or ""
                        # remove label prefix if present
                        txt = re.sub(r"(?i)style of cause\s*[:\-\u2013]?\s*", "", txt)
                        txt = txt.strip()
                        if txt:
                            data["style_of_cause"] = txt
                except Exception:
                    pass

        except Exception:
            # non-fatal post-process failure
            pass

        return data

    def _extract_docket_entries(
        self, modal_element, case_id: Optional[str] = None
    ) -> list[DocketEntry]:
        """Extract docket entries from modal table.

        Args:
            modal_element: Modal element

        Returns:
            list: List of DocketEntry objects
        """
        entries = []

        def try_parse_date(s: str):
            if not s:
                return None
            s = s.strip()
            try:
                return date.fromisoformat(s)
            except Exception:
                pass
            # common formats
            fmts = [
                "%Y-%m-%d",
                "%d-%m-%Y",
                "%d/%m/%Y",
                "%B %d, %Y",
                "%d %B %Y",
                "%Y/%m/%d",
            ]
            for f in fmts:
                try:
                    return datetime.strptime(s, f).date()
                except Exception:
                    continue
            # Try some additional common formats
            extra = [
                "%b %d, %Y",
                "%d %b %Y",
                "%d %B, %Y",
            ]
            for f in extra:
                try:
                    return datetime.strptime(s, f).date()
                except Exception:
                    continue

            # Extract common date-like substrings inside the text (e.g., '10-NOV-2025', '06-JUN-2025', '10/11/2025')
            try:
                import re

                # Patterns to match DD-MMM-YYYY or DD-MON-YYYY (month letters), or numeric dates
                patterns = [
                    r"\b\d{1,2}[-/]\w{3,9}[-/]\d{4}\b",
                    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b",
                    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
                ]
                for pat in patterns:
                    m = re.search(pat, s)
                    if m:
                        ds = m.group(0)
                        # Try several parse formats for the extracted substring
                        try_fmts = [
                            "%d-%b-%Y",
                            "%d-%B-%Y",
                            "%d/%m/%Y",
                            "%Y-%m-%d",
                            "%d-%m-%Y",
                            "%Y/%m/%d",
                            "%d %b %Y",
                        ]
                        for tf in try_fmts:
                            try:
                                return datetime.strptime(ds, tf).date()
                            except Exception:
                                continue
                        # as last resort try dateutil on substring
                        try:
                            from dateutil.parser import parse as _parse

                            d = _parse(ds, fuzzy=True)
                            return d.date()
                        except Exception:
                            pass
            except Exception:
                pass

            # Fallback: try dateutil on the whole string if available
            try:
                from dateutil.parser import parse as _parse

                d = _parse(s, fuzzy=True)
                return d.date()
            except Exception:
                return None

        try:
            # Choose the correct table for docket entries: prefer tables with headers matching 'ID' and 'Recorded Entry Summary' or 'Date Filed'
            tables = modal_element.find_elements(By.XPATH, ".//table")
            table = None
            # Score candidate tables and pick the best match. Heuristics:
            #  - Prefer tables with multiple data rows
            #  - Penalize tables that look like the example/template ("#" / "YYYY-MM-DD")
            #  - Reward tables with captions or ancestor headings indicating 'information about the court file'
            #  - Reward tables with header tokens like 'recorded entry' / 'date'
            candidates = []
            for t in tables:
                try:
                    score = 0
                    # Count data rows (tbody tr) excluding header rows
                    try:
                        data_rows = [
                            r for r in t.find_elements(By.XPATH, ".//tbody//tr")
                        ]
                    except Exception:
                        data_rows = [
                            r
                            for r in t.find_elements(By.XPATH, ".//tr")
                            if not r.find_elements(By.TAG_NAME, "th")
                        ]

                    nrows = len(data_rows) if data_rows is not None else 0
                    score += nrows * 10

                    # Check for obvious placeholder/example single-row pattern
                    if nrows == 1:
                        try:
                            first_td = data_rows[0].find_elements(By.TAG_NAME, "td")
                            if first_td and len(first_td) >= 2:
                                v0 = (first_td[0].text or "").strip()
                                v1 = (first_td[1].text or "").strip()
                                if v0 == "#" or v1.upper() == "YYYY-MM-DD":
                                    score -= 100
                        except Exception:
                            pass

                    # Caption / ancestor headers
                    try:
                        caps = [
                            c.text.strip().lower()
                            for c in t.find_elements(By.XPATH, ".//caption")
                            if c.text and c.text.strip()
                        ]
                        if any("information about the court file" in c for c in caps):
                            score += 50
                    except Exception:
                        pass

                    try:
                        anc = t.find_elements(
                            By.XPATH,
                            "ancestor::*[.//h4[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'information about the court file')]]",
                        )
                        if anc:
                            score += 40
                    except Exception:
                        pass

                    # Header tokens
                    try:
                        ths = [
                            h.text.strip().lower()
                            for h in t.find_elements(By.XPATH, ".//th")
                            if h.text and h.text.strip()
                        ]
                        joined = " | ".join(ths)
                        if any(
                            k in joined
                            for k in ["recorded entry", "recorded entry summary"]
                        ):
                            score += 40
                        if "id" in joined and (
                            "date filed" in joined or "date" in joined
                        ):
                            score += 30
                        if "recorded" in joined and "summary" in joined:
                            score += 30
                    except Exception:
                        joined = ""

                    # If table has at least one non-placeholder row but was small, give it a small boost
                    if nrows == 1 and score >= 10:
                        score += 5

                    candidates.append((score, t, nrows))
                except Exception:
                    continue

            # Choose best scored candidate (highest score); if none, fallback to first table
            if candidates:
                # Prefer highest score, but if all scores are non-positive
                # choose the candidate with the most data rows (more likely real data)
                candidates.sort(key=lambda it: it[0], reverse=True)
                best_score, best_table, best_nrows = candidates[0]
                if best_score <= 0:
                    # choose the candidate that has the most rows as a better fallback
                    try:
                        _, table, _ = max(candidates, key=lambda it: it[2])
                    except Exception:
                        try:
                            table = modal_element.find_element(By.XPATH, ".//table")
                        except Exception:
                            table = None
                else:
                    table = best_table
            else:
                try:
                    table = modal_element.find_element(By.XPATH, ".//table")
                except Exception:
                    table = None
            # Determine header mapping if present
            headers = []
            try:
                thead = table.find_elements(By.XPATH, ".//thead//th")
                if thead:
                    headers = [h.text.strip().lower() for h in thead]
                else:
                    # try first row th
                    first_row_th = table.find_elements(By.XPATH, ".//tr[1]/th")
                    headers = (
                        [h.text.strip().lower() for h in first_row_th]
                        if first_row_th
                        else []
                    )
            except Exception:
                headers = []

            # normalization helper
            def norm(s: str) -> str:
                return (s or "").strip().lower()

            # candidate tokens for columns
            date_keys = [
                "date",
                "recorded",
                "recorded date",
                "entry date",
                "document date",
            ]
            office_keys = ["office", "registry", "court office", "location", "centre"]
            summary_keys = [
                "document",
                "description",
                "summary",
                "particulars",
                "details",
                "event",
                "action",
                "document description",
            ]

            # helper to find header index matching tokens
            def find_index_by_keys(keys):
                for i, h in enumerate(headers):
                    for k in keys:
                        if k in h:
                            return i
                return None

            date_idx_header = find_index_by_keys(date_keys)
            office_idx_header = find_index_by_keys(office_keys)
            summary_idx_header = find_index_by_keys(summary_keys)

            rows = table.find_elements(By.TAG_NAME, "tr")
            # If header row present, skip it when it contains th elements
            start_idx = 1 if rows and rows[0].find_elements(By.TAG_NAME, "th") else 0

            # Track parsing errors and abort on repeated failures to avoid saving partial/incorrect data
            parse_error_count = 0
            max_parse_errors = Config.get_docket_parse_max_errors()

            for r_idx, row in enumerate(rows[start_idx:], 1):
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    cell_texts = [c.text.strip() for c in cells]
                    if not any(cell_texts):
                        continue

                    entry_date = None
                    office = None
                    summary = None

                    # If header mapping available, use it to pick cells
                    if date_idx_header is not None and date_idx_header < len(
                        cell_texts
                    ):
                        entry_date = try_parse_date(cell_texts[date_idx_header])
                    if office_idx_header is not None and office_idx_header < len(
                        cell_texts
                    ):
                        office = cell_texts[office_idx_header] or None
                    if summary_idx_header is not None and summary_idx_header < len(
                        cell_texts
                    ):
                        summary = cell_texts[summary_idx_header] or None

                    # If header mapping wasn't available, try to detect a date cell among columns
                    if entry_date is None:
                        for idx, txt in enumerate(cell_texts):
                            d = try_parse_date(txt)
                            if d:
                                entry_date = d
                                date_idx = idx
                                break
                        else:
                            date_idx = None

                    # For summary/office heuristics: if still unknown, choose longest for summary, shortest for office
                    if not summary or not office:
                        # build list of candidate texts excluding the date cell
                        candidates = []
                        for idx, txt in enumerate(cell_texts):
                            if idx == (date_idx if "date_idx" in locals() else None):
                                continue
                            if txt:
                                candidates.append((idx, txt))

                        if candidates:
                            # pick longest text as summary
                            longest = max(candidates, key=lambda it: len(it[1]))
                            # pick shortest as office (but prefer known office tokens)
                            shortest = min(candidates, key=lambda it: len(it[1]))
                            if not summary:
                                summary = longest[1]
                            if not office:
                                # if the shortest looks like a language token or '#', prefer next shortest
                                cand_off = shortest[1]
                                if len(cand_off) <= 3 or cand_off.strip() == "#":
                                    # try to pick next shortest
                                    if len(candidates) > 1:
                                        cand_off = sorted(
                                            candidates, key=lambda it: len(it[1])
                                        )[1][1]
                                office = cand_off

                    entry = DocketEntry(
                        case_id=case_id or "",
                        doc_id=r_idx,
                        entry_date=entry_date,
                        entry_office=office,
                        summary=summary,
                    )
                    entries.append(entry)
                except Exception as e:
                    # If element became stale, abort so higher-level logic can re-run the search and retry
                    if isinstance(e, StaleElementReferenceException):
                        logger.warning(f"StaleElementReference while parsing docket row {r_idx}: {e}")
                        raise
                    # Count other parsing errors and escalate if too many occur
                    parse_error_count += 1
                    logger.warning(f"Error parsing docket entry row {r_idx}: {e} (count={parse_error_count})")
                    if parse_error_count >= max_parse_errors:
                        raise Exception(f"Too many docket parsing errors ({parse_error_count}), aborting to allow retry")
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
