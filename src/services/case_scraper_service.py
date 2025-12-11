"""Case scraping service for Federal Court cases using search form."""

import time
import random
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
        self.rate_limiter = EthicalRateLimiter(
            interval_seconds=Config.get_rate_limit_seconds(),
            backoff_factor=Config.get_backoff_factor(),
            max_backoff_seconds=Config.get_max_backoff_seconds(),
        )  # Configurable random delay
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
        # First, try to dismiss maintenance notifications that might block UI
        self._dismiss_maintenance_notifications(driver)
        
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

    def _dismiss_maintenance_notifications(self, driver) -> None:
        """Try to dismiss maintenance notifications that might block UI interactions."""
        # Common maintenance notification selectors
        maintenance_selectors = [
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close')]",
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'fermer')]", 
            "//button[contains(@class, 'close')]",
            "//button[contains(@class, 'modal-close')]",
            "//div[contains(@class, 'modal')]//button[contains(., 'Close')]",
            "//div[contains(@class, 'notification')]//button[contains(., 'Close')]",
            "//div[contains(@class, 'alert')]//button[contains(., 'Close')]",
            "//div[contains(@class, 'maintenance')]//button",
            "//span[@aria-hidden='true' and contains(text(), '×')]",
        ]

        for selector in maintenance_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    try:
                        # Check if element is visible and clickable
                        if element.is_displayed() and element.is_enabled():
                            element_id = element.get_attribute('id') or '<anonymous>'
                            element_class = element.get_attribute('class') or '<no class>'
                            element_text = element.text.strip() or '<no text>'
                            
                            logger.info(f"[UI_ACTION] Found potential maintenance close button (id: {element_id}, class: {element_class}, text: '{element_text}')")
                            
                            # Try JavaScript click first (more reliable for overlays)
                            driver.execute_script("arguments[0].click();", element)
                            logger.info(f"[UI_ACTION] Successfully dismissed maintenance notification using JS click")
                            time.sleep(0.5)
                            return
                    except Exception as e:
                        try:
                            # Fallback to native click
                            element.click()
                            logger.info(f"[UI_ACTION] Successfully dismissed maintenance notification using native click")
                            time.sleep(0.5)
                            return
                        except Exception:
                            continue
            except Exception:
                continue

    def _safe_send_keys(self, driver, element, text: str) -> None:
        """Safely send keys to an element, using JS fallback if necessary."""
        element_id = element.get_attribute('id') or element.get_attribute('name') or '<anonymous>'
        logger.info(f"[UI_ACTION] Typing text '{text}' into input element (id: {element_id})")
        
        try:
            element.clear()
            logger.debug(f"[UI_ACTION] Cleared input element (id: {element_id})")
        except Exception:
            # ignore clear failures
            logger.debug(f"[UI_ACTION] Failed to clear input element (id: {element_id}), continuing")

        try:
            element.send_keys(text)
            logger.info(f"[UI_ACTION] Successfully typed '{text}' using send_keys (id: {element_id})")
            return
        except Exception:
            # Fallback: set value via JS and dispatch input events
            logger.info(f"[UI_ACTION] send_keys failed, trying JavaScript fallback (id: {element_id})")
            try:
                driver.execute_script(
                    "arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input'));",
                    element,
                    text,
                )
                logger.info(f"[UI_ACTION] Successfully typed '{text}' using JavaScript fallback (id: {element_id})")
                return
            except Exception as e:
                logger.error(f"[UI_ACTION] JavaScript fallback failed for typing '{text}' (id: {element_id}): {e}")
                raise

    def _submit_search(self, driver, input_element) -> None:
        """Find and click a submit control related to the input_element, with fallbacks."""
        # Try to find a submit button in the same form
        submit = None
        submit_method = "unknown"
        
        try:
            submit = input_element.find_element(
                By.XPATH, "ancestor::form//button[@type='submit']"
            )
            submit_method = "form_button_submit"
        except Exception:
            try:
                submit = input_element.find_element(
                    By.XPATH, "ancestor::form//input[@type='submit']"
                )
                submit_method = "form_input_submit"
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
                submit_method = "page_search_button"
            except Exception:
                submit = None

        if submit is None:
            # As a last resort, submit the form via JS
            logger.info("[UI_ACTION] No submit button found, trying JavaScript form submission")
            try:
                driver.execute_script(
                    "var f = arguments[0].closest('form'); if(f){f.submit();} else {document.forms[0] && document.forms[0].submit();}",
                    input_element,
                )
                logger.info("[UI_ACTION] Successfully submitted form using JavaScript")
                return
            except Exception as e:
                logger.error(f"[UI_ACTION] JavaScript form submission failed: {e}")
                raise

        # Log submit button details before clicking
        submit_id = submit.get_attribute('id') or submit.get_attribute('name') or '<anonymous>'
        submit_text = submit.text.strip() or submit.get_attribute('value') or '<no text>'
        logger.info(f"[UI_ACTION] Clicking submit button using method: {submit_method} (id: {submit_id}, text: '{submit_text}')")
        
        # Click using JS if normal click fails
        try:
            submit.click()
            logger.info(f"[UI_ACTION] Successfully clicked submit button (id: {submit_id}) using native click")
        except Exception:
            logger.info(f"[UI_ACTION] Native click failed, trying JavaScript click (id: {submit_id})")
            try:
                driver.execute_script("arguments[0].click();", submit)
                logger.info(f"[UI_ACTION] Successfully clicked submit button (id: {submit_id}) using JavaScript")
            except Exception as e:
                logger.error(f"[UI_ACTION] Submit click failed for button (id: {submit_id}): {e}")
                raise
                raise

    def initialize_page(self) -> None:
        """Initialize the court files page and set up search form.

        Raises:
            Exception: If page initialization fails
        """
        driver = self._get_driver()

        try:
            logger.info(f"[UI_ACTION] Loading court files page: {self.BASE_URL}")
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

            # Additional attempt to dismiss any maintenance notifications
            try:
                self._dismiss_maintenance_notifications(driver)
            except Exception:
                logger.debug("Maintenance notification dismissal attempt failed or not needed")

            # Click "Search by court number" tab
            logger.info("[UI_ACTION] Clicking 'Search by court number' tab")
            # Use a stable wait for the tab to become clickable (10s)
            search_tab = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Search by court number"))
            )
            try:
                # Log tab details before clicking
                tab_id = search_tab.get_attribute('id') or '<no id>'
                tab_class = search_tab.get_attribute('class') or '<no class>'
                tab_text = search_tab.text.strip() or '<no text>'
                logger.debug(f"[UI_ACTION] Tab found - id: {tab_id}, class: {tab_class}, text: '{tab_text}'")
                
                search_tab.click()
                logger.info("[UI_ACTION] Successfully clicked 'Search by court number' tab using native click")
                
                # Wait and verify tab is active
                time.sleep(1)
                try:
                    # Check if the tab content is now visible
                    active_tab = driver.find_element(By.ID, "tab02")
                    if active_tab.is_displayed():
                        logger.info("[UI_ACTION] Confirmed 'Search by court number' tab is active and visible")
                    else:
                        logger.warning("[UI_ACTION] Tab clicked but content may not be visible")
                except Exception:
                    logger.debug("[UI_ACTION] Could not verify tab visibility (may be normal)")
                    
            except Exception:
                logger.info("[UI_ACTION] Native click failed, trying JavaScript click for 'Search by court number' tab")
                driver.execute_script("arguments[0].click();", search_tab)
                logger.info("[UI_ACTION] Successfully clicked 'Search by court number' tab using JavaScript")
                
                # Also verify after JavaScript click
                time.sleep(1)
                try:
                    active_tab = driver.find_element(By.ID, "tab02")
                    if active_tab.is_displayed():
                        logger.info("[UI_ACTION] Confirmed 'Search by court number' tab is active and visible (after JS click)")
                except Exception:
                    logger.debug("[UI_ACTION] Could not verify tab visibility after JS click")

            # Wait for tab content to load. The site has changed ids over time
            # so try a small set of likely input ids and accept whichever appears.
            possible_case_inputs = [
                "courtNumber",
                "selectCourtNumber",
                "selectRetcaseCourtNumber",
            ]
            found_case_input = None
            logger.info("[UI_ACTION] Waiting for search input field to appear...")
            for pid in possible_case_inputs:
                try:
                    WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.ID, pid))
                    )
                    found_case_input = pid
                    logger.info(f"[UI_ACTION] Found search input field with id: {pid}")
                    break
                except Exception:
                    logger.debug(f"[UI_ACTION] Input field with id {pid} not found, trying next...")
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

    def _detect_anti_bot_measures(self, driver) -> bool:
        """Detect if anti-bot measures are active (CAPTCHA, rate limiting, etc.).
        
        Returns:
            bool: True if anti-bot measures detected
        """
        try:
            page_source = driver.page_source.lower()
            
            # Common anti-bot indicators
            anti_bot_indicators = [
                'captcha',
                'recaptcha',
                'h-captcha',
                'turnstile',
                'cf-browser-verification',
                'cloudflare',
                'access denied',
                'too many requests',
                'rate limit',
                'blocked',
                'suspicious activity',
                ' automated',
                'bot detected',
                'security check',
                'verification required',
                'please wait',
                'checking your browser',
                'ddos protection',
                'challenge platform',
                'javascript challenge'
            ]
            
            detection_count = sum(1 for indicator in anti_bot_indicators if indicator in page_source)
            
            if detection_count >= 2:
                logger.warning(f"Anti-bot measures detected (indicators: {detection_count})")
                return True
            
            # Check for unusual redirects or status codes
            current_url = driver.current_url.lower()
            if any(indicator in current_url for indicator in ['captcha', 'challenge', 'blocked', 'verify']):
                logger.warning(f"Anti-bot URL detected: {current_url}")
                return True
                
            return False
            
        except Exception as e:
            logger.debug(f"Failed to detect anti-bot measures: {e}")
            return False

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
        
        # Additional verification after initialization to ensure everything is ready
        # This addresses the issue where deep initialization leaves the input in an invalid state
        driver = self._get_driver()
        
        # Verify we're on the correct tab and input is ready
        try:
            # Check if the search tab is active
            logger.info("[UI_ACTION] Verifying page state after initialization")
            
            # Wait a moment for any pending operations to complete
            time.sleep(1)
            
            # Try to find the input field to verify it's ready
            input_found = False
            for cid in ["selectCourtNumber", "courtNumber", "selectRetcaseCourtNumber"]:
                try:
                    input_elem = driver.find_element(By.ID, cid)
                    if input_elem.is_displayed() and input_elem.is_enabled():
                        input_found = True
                        logger.info(f"[UI_ACTION] Verified input field is ready: {cid}")
                        break
                except Exception:
                    continue
            
            if not input_found:
                logger.warning("[UI_ACTION] Input field not ready after initialization, attempting re-initialization")
                self._initialized = False
                self.initialize_page()
            else:
                logger.info("[UI_ACTION] Page state verification successful")
                
        except Exception as verify_err:
            logger.warning(f"[UI_ACTION] Page verification failed: {verify_err}")
            # Try to re-initialize if verification fails
            try:
                self._initialized = False
                self.initialize_page()
                logger.info("[UI_ACTION] Successfully re-initialized after verification failure")
            except Exception:
                logger.error("[UI_ACTION] Re-initialization failed, proceeding anyway")

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
                            # Add smart delay before re-initialization for consecutive failures
                            if not hasattr(self, '_consecutive_search_failures'):
                                self._consecutive_search_failures = 0
                            self._consecutive_search_failures += 1
                            
                            # Progressive delay based on consecutive search failures
                            if self._consecutive_search_failures > 2:
                                retry_delay = random.uniform(3.0, 6.0) + (self._consecutive_search_failures * 1.0)
                                logger.info(f"Applying progressive delay {retry_delay:.1f}s due to {self._consecutive_search_failures} consecutive search failures")
                                time.sleep(retry_delay)
                            
                            self.initialize_page()
                            driver = self._get_driver()
                            continue
                        except Exception:
                            pass
                    else:
                        # Reset counter on successful second attempt
                        if hasattr(self, '_consecutive_search_failures'):
                            self._consecutive_search_failures = 0
                        return False

                # Use robust send keys with JS fallback
                try:
                    if case_input is not None:
                        # Log input details before clearing
                        input_id = case_input.get_attribute('id') or case_input.get_attribute('name') or '<anonymous>'
                        input_class = case_input.get_attribute('class') or '<no class>'
                        input_type = case_input.get_attribute('type') or '<no type>'
                        logger.debug(f"[UI_ACTION] Input element found - id: {input_id}, class: {input_class}, type: {input_type}")
                        
                        # Clear input with verification
                        try:
                            case_input.clear()
                            logger.info(f"[UI_ACTION] Cleared input field (id: {input_id})")
                        except Exception as clear_err:
                            logger.warning(f"[UI_ACTION] Failed to clear input field (id: {input_id}): {clear_err}")
                            # Try JavaScript clear as fallback
                            try:
                                driver.execute_script("arguments[0].value = '';", case_input)
                                logger.info(f"[UI_ACTION] Cleared input field using JavaScript fallback (id: {input_id})")
                            except Exception:
                                logger.error(f"[UI_ACTION] JavaScript clear also failed (id: {input_id})")
                except Exception:
                    logger.warning("[UI_ACTION] case_input is None, cannot clear input field")
                    
                if case_input is not None:
                    self._safe_send_keys(driver, case_input, case_number)

                # Enhanced verification: verify the input was actually set
                input_verified = False
                verification_attempts = 0
                max_verification_attempts = 3
                
                while not input_verified and verification_attempts < max_verification_attempts:
                    verification_attempts += 1
                    
                    # Diagnostic: log the input element state after typing
                    try:
                        cur_val = None
                        placeholder_val = None
                        element_id = None
                        element_name = None
                        is_displayed = None
                        is_enabled = None
                        try:
                            if case_input is not None:
                                cur_val = case_input.get_attribute("value")
                                placeholder_val = case_input.get_attribute('placeholder')
                                element_id = getattr(case_input, 'id', None)
                                element_name = getattr(case_input, 'name', None)
                                is_displayed = case_input.is_displayed()
                                is_enabled = case_input.is_enabled()
                        except Exception:
                            pass
                            
                        logger.info(
                            f"[UI_ACTION] Input verification attempt {verification_attempts}: "
                            f"id={element_id or element_name or '<anonymous>'}, "
                            f"value='{cur_val}', expected='{case_number}', "
                            f"displayed={is_displayed}, enabled={is_enabled}, "
                            f"placeholder={placeholder_val}"
                        )
                        
                        # Check if the value was actually set
                        if cur_val and str(cur_val).strip() == str(case_number).strip():
                            input_verified = True
                            logger.info(f"[UI_ACTION] Input verification successful - value correctly set to '{case_number}'")
                        else:
                            logger.warning(f"[UI_ACTION] Input verification failed - expected '{case_number}', found '{cur_val}'")
                            
                            # Try to re-input the value
                            if verification_attempts < max_verification_attempts:
                                logger.info(f"[UI_ACTION] Retrying input for '{case_number}' (attempt {verification_attempts})")
                                try:
                                    case_input.clear()
                                    self._safe_send_keys(driver, case_input, case_number)
                                    time.sleep(0.5)  # Small delay before retry
                                except Exception as retry_err:
                                    logger.error(f"[UI_ACTION] Retry input failed: {retry_err}")
                                    
                    except Exception as verify_err:
                        logger.error(f"[UI_ACTION] Input verification error on attempt {verification_attempts}: {verify_err}")
                        
                if not input_verified:
                    logger.error(f"[UI_ACTION] CRITICAL: Failed to verify input after {max_verification_attempts} attempts")
                    # Continue anyway but log the critical failure
                else:
                    logger.info(f"[UI_ACTION] Input successfully verified after {verification_attempts} attempts")
                # Small stabilization pause to allow client-side handlers
                # (e.g. input listeners) to process the entered value before
                # submitting. Use random delay to avoid detection.
                stabilization_delay = random.uniform(1.5, 3.0)
                time.sleep(stabilization_delay)

                # Try a tab-specific submit first (more reliable on this site)
                submit_method = None
                try:
                    tab_submit = driver.find_element(By.ID, "tab02Submit")
                    
                    # Log submit button details before clicking
                    submit_id = tab_submit.get_attribute('id') or '<no id>'
                    submit_class = tab_submit.get_attribute('class') or '<no class>'
                    submit_type = tab_submit.get_attribute('type') or '<no type>'
                    submit_text = tab_submit.text.strip() or tab_submit.get_attribute('value') or '<no text>'
                    submit_enabled = tab_submit.is_enabled()
                    submit_displayed = tab_submit.is_displayed()
                    
                    logger.info(f"[UI_ACTION] Found tab submit button - id: {submit_id}, class: {submit_class}, "
                              f"type: {submit_type}, text: '{submit_text}', enabled: {submit_enabled}, displayed: {submit_displayed}")
                    
                    # Check if input field has value before submitting
                    current_input_value = ""
                    try:
                        if case_input is not None:
                            current_input_value = case_input.get_attribute("value") or ""
                    except Exception:
                        pass
                    
                    if not current_input_value.strip():
                        logger.error(f"[UI_ACTION] CRITICAL: Submitting empty input field! Current value: '{current_input_value}'")
                    else:
                        logger.info(f"[UI_ACTION] Submitting with input value: '{current_input_value}'")
                    
                    try:
                        driver.execute_script("arguments[0].click();", tab_submit)
                        submit_method = "tab02Submit(js)"
                        logger.info("[UI_ACTION] Successfully clicked tab02Submit using JavaScript")
                    except Exception:
                        tab_submit.click()
                        submit_method = "tab02Submit(native)"
                        logger.info("[UI_ACTION] Successfully clicked tab02Submit using native click")
                        
                except Exception as find_err:
                    logger.warning(f"[UI_ACTION] Could not find tab02Submit button: {find_err}")
                    # Fall back to the generic submit helper
                    try:
                        self._submit_search(driver, case_input)
                        submit_method = "generic_submit_helper"
                        logger.info("[UI_ACTION] Used generic submit helper")
                    except Exception as submit_err:
                        logger.error(f"[UI_ACTION] All submit attempts failed: {submit_err}")
                        submit_method = "failed_submit"
                        # Continue and let the wait for results determine outcome

                logger.info(f"[UI_ACTION] Submit method used: {submit_method}")

                # Poll for results: check repeatedly for the case row or an explicit
                # 'No data available' marker. Polling is often more reliable than
                # relying on DataTables' async hooks.
                found_row = False
                no_data = False
                no_data_streak = 0
                polls = 0
                td_match_count = 0
                table_row_count = 0

                # Prefer a shorter poll delay by default but keep it consistent
                # with prior behavior; allow a small streak of 'No data'
                # before treating it as stable. Use the configured safe-stop
                # threshold so that probe-level and search-level behavior are
                # consistent.
                max_polls = 60  # Increased from 40 to allow more time for data loading
                poll_delay = 0.5
                no_data_threshold = int(Config.get_safe_stop_no_records())
                
                # Add extra wait for DataTable initialization after search submission
                # Use random delay to appear more human-like
                logger.debug("Waiting for DataTable to initialize after search")
                init_delay = random.uniform(1.5, 2.5)
                time.sleep(init_delay)  # Allow DataTable to reset and start loading
                for i in range(max_polls):
                    polls += 1
                    try:
                        # Additional placeholder phrases for no-results: English + French variants
                        no_data_elems = []
                        placeholder_phrases = [
                            'no data available',
                            'no results',
                            'aucun résultat',
                            'aucun résultat trouvé',
                            'aucune donnée',
                            'aucune donnée disponible',
                            'aucun résultat disponible',
                            # Spanish
                            'sin datos disponibles',
                            'sin datos',
                            'sin resultados',
                            'no hay datos',
                            # Portuguese
                            'sem dados disponíveis',
                            'sem dados',
                            'sem resultados',
                            # Add shorter tokens to be more forgiving on localized phrases
                            'aucun',
                            'aucune',
                            'sin',
                            'sem',
                        ]
                        try:
                            # Build an XPATH that checks for any of these phrases (case-insensitive)
                            xpath_expr = ' or '.join([f"contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{p}')" for p in placeholder_phrases])
                            # Restrict placeholder detection to the candidate results table where possible
                            # to avoid false positives from other page tables (e.g., examples, templates)
                            no_data_elems = []
                            result_table = None
                            try:
                                # Prefer a table which appears to contain results (headers like 'court file' / 'court number')
                                tables = driver.find_elements(By.XPATH, "//table")
                                candidates = []
                                for t in tables:
                                    try:
                                        ths = [h.text.strip().lower() for h in t.find_elements(By.XPATH, ".//th") if h.text and h.text.strip()]
                                        joined = " | ".join(ths)
                                        if any(h in joined for h in ["court file", "court number", "court file no", "court file number"]):
                                            result_table = t
                                            break
                                        candidates.append((len(ths), t))
                                    except Exception:
                                        continue
                                if result_table is None and candidates:
                                    # pick the table with the most header columns as fallback
                                    _, result_table = max(candidates, key=lambda x: x[0])
                            except Exception:
                                result_table = None

                            if result_table is not None:
                                no_data_elems = result_table.find_elements(By.XPATH, f".//td[{xpath_expr}]")
                            else:
                                no_data_elems = driver.find_elements(By.XPATH, f"//td[{xpath_expr}]")
                        except Exception:
                            no_data_elems = driver.find_elements(By.XPATH, "//td[contains(text(), 'No data available')]")
                        # Prefer scoping to a single 'results' table when possible
                        result_table = None
                        try:
                            tables = driver.find_elements(By.XPATH, "//table")
                            candidates = []
                            for t in tables:
                                try:
                                    ths = [h.text.strip().lower() for h in t.find_elements(By.XPATH, ".//th") if h.text and h.text.strip()]
                                    joined = " | ".join(ths)
                                    if any(h in joined for h in ["court file", "court number", "court file no", "court file number"]):
                                        result_table = t
                                        break
                                    candidates.append((len(ths), t))
                                except Exception:
                                    continue
                            if result_table is None and candidates:
                                _, result_table = max(candidates, key=lambda x: x[0])
                        except Exception:
                            result_table = None

                        if result_table is not None:
                            td_matches = result_table.find_elements(By.XPATH, f".//td[contains(normalize-space(.), '{case_number}')]")
                            table_rows = result_table.find_elements(By.XPATH, ".//tbody//tr")
                        else:
                            td_matches = driver.find_elements(By.XPATH, f"//table//td[contains(normalize-space(.), '{case_number}')]")
                            table_rows = driver.find_elements(By.XPATH, "//table//tbody//tr")
                    except Exception:
                        no_data_elems = []
                        td_matches = []
                        table_rows = []

                    if td_matches:
                        # Clear any prior 'no_data' observation: a later poll
                        # that finds matching rows should override earlier
                        # transient 'No data available' markers.
                        no_data = False
                        found_row = True
                        td_match_count = len(td_matches)
                        table_row_count = len(table_rows)
                        logger.debug(f"Poll {i+1}: found {td_match_count} matching td(s) in {table_row_count} table rows")
                        break

                    if no_data_elems:
                        # The page may show 'No data available' at first but then
                        # update with results; increment streak and only consider
                        # stable 'no data' if it persists across multiple polls.
                        # Verify the search input value corresponds to the requested case;
                        # if the input doesn't match, treat 'No data' as stale and
                        # continue polling until the page reflects the current request.
                        try:
                            cur_val = None
                            if case_input is not None and hasattr(case_input, 'get_attribute'):
                                cur_val = case_input.get_attribute('value')
                        except Exception:
                            cur_val = None
                        if cur_val is None or str(cur_val).strip() != str(case_number).strip():
                            logger.debug(f"Detected stale 'No data available' marker but input value indicates search not updated (input={cur_val}) - continuing to poll")
                            # Continue polling to allow the search input/apply to take effect
                            time.sleep(poll_delay)
                            continue
                        no_data_streak += 1
                        td_match_count = len(td_matches)
                        table_row_count = len(table_rows)
                        logger.warning(f"Poll {i+1}: detected 'No data available' (rows={table_row_count} td_matches={td_match_count}, streak={no_data_streak})")
                        # If a placeholder row also indicates 'No data' we can stop early
                        try:
                            sample_row_text = (table_rows[0].text if table_rows and len(table_rows) > 0 and hasattr(table_rows[0], 'text') else None)
                            sample_text_lower = str(sample_row_text).strip().lower() if sample_row_text else ''
                            # If sample row contains any of the known placeholder phrases, stop early
                            try:
                                import unicodedata
                                import re as _re
                                def _strip_accents(s: str) -> str:
                                    nk = unicodedata.normalize('NFD', s)
                                    return ''.join(c for c in nk if unicodedata.category(c) != 'Mn')

                                sample_text_norm = _strip_accents(sample_text_lower)
                                # If sample row looks like a case identifier (IMM-...), treat
                                # it as a data row and skip placeholder early-exit.
                                if sample_row_text and _re.search(r"\bimm[-\s]\d+[-\s]\d{2}\b", sample_row_text, flags=_re.IGNORECASE):
                                    logger.debug(f"Poll {i+1}: sample row looks like a real case (not placeholder); continuing to poll (sample={sample_row_text})")
                                else:
                                    norm_phrases = [_strip_accents(p) for p in placeholder_phrases]
                                    if sample_row_text and (any((p in sample_text_lower) for p in placeholder_phrases) or any((np in sample_text_norm) for np in norm_phrases)):
                                        logger.info(f"Poll {i+1}: detected placeholder in sample row – treating as no-results (early exit) (sample={sample_row_text})")
                                    no_data = True
                                    break
                            except Exception:
                                if sample_row_text and any((p in sample_text_lower) for p in placeholder_phrases):
                                    logger.info(f"Poll {i+1}: detected placeholder in sample row – treating as no-results (early exit) (sample={sample_row_text})")
                                    no_data = True
                                    break
                        except Exception:
                            pass
                        if no_data_streak >= no_data_threshold:
                            no_data = True
                            break
                    # If we have table rows but no td matches, try numeric variant detection
                    if not td_matches and table_rows:
                        try:
                            import re
                            # Try to detect variants: padded zeros, alternate separators, spaces
                            m = re.search(r"IMM-?(\d+)-\d{2}", case_number)
                            if m:
                                num = str(int(m.group(1)))
                                padded_original = m.group(1)
                                sep = r"[-\s–—/]"
                                pattern = re.compile(rf"IMM{sep}0*{num}{sep}\d{{2}}", flags=re.IGNORECASE)
                                for r in table_rows[:5]:
                                    try:
                                        txt = r.text or ''
                                        if (
                                            case_number in txt
                                            or pattern.search(txt)
                                            or f"-{num}-" in txt
                                            or f"-{padded_original}-" in txt
                                        ):
                                            found_row = True
                                            td_match_count = 1
                                            table_row_count = len(table_rows)
                                            logger.info(f"Poll {i+1}: numeric variant match in table rows for {case_number} (rows={table_row_count})")
                                            break
                                    except Exception:
                                        continue
                                if found_row:
                                    break
                        except Exception:
                            logger.debug("Failed numeric variant detection during polling", exc_info=True)
                        else:
                            # If no numeric variant matches, capture a short debug sample of the first row text
                            try:
                                sample_row_text = (table_rows[0].text if table_rows and len(table_rows) > 0 and hasattr(table_rows[0], 'text') else None)
                                logger.debug(f"Poll {i+1}: table rows present but no td match; sample_row_text={sample_row_text}")
                                # If sample row expresses one of the known placeholders,
                                # treat it as a definitive no-results and stop early.
                                sample_text_lower = str(sample_row_text).strip().lower() if sample_row_text else ''
                                try:
                                    import unicodedata as _ud
                                    import re as _re2
                                    sample_text_norm2 = ''.join(c for c in _ud.normalize('NFD', sample_text_lower) if _ud.category(c) != 'Mn')
                                    norm_phrases2 = [''.join(c for c in _ud.normalize('NFD', p) if _ud.category(c) != 'Mn') for p in placeholder_phrases]
                                    # If the sample looks like another case identifier (IMM-...),
                                    # treat it as real data and skip placeholder handling.
                                    if sample_row_text and _re2.search(r"\bimm[-\s]\d+[-\s]\d{2}\b", sample_row_text, flags=_re2.IGNORECASE):
                                        logger.debug(f"Poll {i+1}: sample row looks like a real case (not placeholder); continuing to poll (sample={sample_row_text})")
                                    elif sample_row_text and (any((p in sample_text_lower) for p in placeholder_phrases) or any((np in sample_text_norm2) for np in norm_phrases2)):
                                        logger.info(f"Poll {i+1}: detected placeholder in table sample row for {case_number} — treating as no-results (early exit) (sample={sample_row_text})")
                                        no_data = True
                                        break
                                except Exception:
                                    if sample_row_text and any((p in sample_text_lower) for p in placeholder_phrases):
                                        logger.info(f"Poll {i+1}: detected placeholder in table sample row for {case_number} — treating as no-results (early exit) (sample={sample_row_text})")
                                        no_data = True
                                        break
                            except Exception:
                                pass
                        # else, continue polling to allow data to arrive

                    # periodic debug summary to trace progress (every 5 polls)
                    if (i + 1) % 5 == 0:
                        logger.debug(f"Poll {i+1}: no marker, td_matches={len(td_matches)} table_rows={len(table_rows)}")

                    time.sleep(poll_delay)

                if found_row:
                    # Optionally sample matched cell text for debugging
                    sample_text = None
                    try:
                        sample_text = td_matches[0].text if td_matches else None
                    except Exception:
                        sample_text = None
                    logger.info(f"Results found for case: {case_number} (polls={polls} table_rows={table_row_count} td_matches={td_match_count} sample={sample_text})")
                    return True

                if no_data:
                    # A stable 'No data available' observation indicates the
                    # site returned an explicit no-results state. Do NOT retry
                    # or re-initialize in this case — retries should only be
                    # attempted when a program error, detection failure, or
                    # exception occurred. Return no-results immediately so the
                    # higher-level probing logic can treat it deterministically.
                    logger.warning(
                        f"No results found for case: {case_number} (polls={polls} table_rows={table_row_count} td_matches={td_match_count} submit={submit_method})"
                    )
                    return False

                # As a final fallback, check for any table rows present
                table_rows_final = driver.find_elements(By.XPATH, "//table//tbody//tr")
                if table_rows_final:
                    try:
                        nrows_final = len(table_rows_final)
                    except Exception:
                        nrows_final = 0
                    # If the first row in the final table rows is one of the
                    # localized placeholders (e.g., French 'Aucun résultat'),
                    # treat it as no-results and return False. This captures
                    # cases where earlier placeholder detection did not
                    # trigger due to query differences.
                    try:
                        sample_final = table_rows_final[0].text if table_rows_final and len(table_rows_final) > 0 else ''
                        sample_final_lower = str(sample_final).strip().lower() if sample_final else ''
                        try:
                            import unicodedata as _ud3
                            sample_final_norm = ''.join(c for c in _ud3.normalize('NFD', sample_final_lower) if _ud3.category(c) != 'Mn')
                        except Exception:
                            sample_final_norm = sample_final_lower
                        # If any placeholder phrase (or normalized version) appears, early-exit
                        import re as _re3
                        if sample_final and (not _re3.search(r"\bimm[-\s]\d+[-\s]\d{2}\b", sample_final, flags=_re3.IGNORECASE)) and (any((p in sample_final_lower) for p in placeholder_phrases) or any((p in sample_final_norm) for p in ["aucun resultat", "aucune donnée", "aucune donnée disponible"])):
                            logger.info(f"Detected placeholder in final table sample; treating as no-results (sample={sample_final})")
                            return False
                    except Exception:
                        pass
                    # Try to detect numeric-only matches (e.g., 'IMM-0005-21' in page while searching for 'IMM-5-21')
                    try:
                        import re
                        m = re.search(r"IMM-(\d+)-\d{2}", case_number)
                        numeric_match = False
                        if m:
                            num = str(int(m.group(1)))
                            for r in table_rows_final[:5]:
                                try:
                                    txt = r.text or ''
                                    if case_number in txt or f"-{num}-" in txt:
                                        numeric_match = True
                                        break
                                except Exception:
                                    continue
                        if numeric_match:
                            logger.info(f"Table rows present and numeric variant detected for case: {case_number} (submit={submit_method})")
                            return True
                    except Exception:
                        logger.debug("Failed numeric variant detection for table rows", exc_info=True)
                    logger.info(f"Table rows present ({nrows_final}) but specific case not detected: {case_number} (submit={submit_method})")
                    return True

                # No automatic retry here. Retries should only occur when we
                # detect an explicit failure to operate (e.g., couldn't locate
                # the input element) or an exception is raised which will be
                # handled by the outer exception path. Proceed to diagnostics
                # and return.

                # Check for anti-bot measures before giving up
                if self._detect_anti_bot_measures(driver):
                    logger.warning(f"Anti-bot measures detected while searching for {case_number}")
                
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
                    logger.warning("Failed to save search diagnostics", exc_info=True)

                logger.warning(f"No results table found for case: {case_number}")
                return False
            
            # If we've exhausted all attempts without finding results, return False
            return False

        except Exception as e:
            logger.error(f"Error searching case {case_number}: {e}")
            return False

    def scrape_case_data(self, case_number: str) -> tuple[Optional[Case], Optional[str]]:
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
            logger.info(f"[UI_ACTION] Starting to click 'More' button for case: {case_number}")
            
            # Log current page state before attempting to click More
            try:
                current_url = driver.current_url
                page_title = driver.title
                logger.debug(f"[UI_ACTION] Current page before More click: URL={current_url}, Title='{page_title}'")
            except Exception:
                logger.debug("[UI_ACTION] Could not capture current page info")
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
                        "[UI_ACTION] Attempting fallback: click last-cell button or anchor in the target row"
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
                        last_ctl_id = last_ctl.get_attribute('id') or '<anonymous>'
                        logger.info(f"[UI_ACTION] Using last-cell control as 'More' fallback (id: {last_ctl_id})")
                    else:
                        # Try clicking the row itself (some pages bind click to row)
                        if target_row is not None:
                            try:
                                logger.info("[UI_ACTION] Clicking target row directly as fallback to open modal")
                                driver.execute_script(
                                    "arguments[0].click();", target_row
                                )
                                logger.info("[UI_ACTION] Successfully clicked target row as fallback")
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

            # Wait for table to stabilize before clicking to avoid stale elements
            logger.info("[UI_ACTION] Waiting for table to stabilize before clicking 'More' button")
            time.sleep(1)
            
            # Try normal click first, then JS click fallback. Handle
            # StaleElementReferenceException by re-finding the control and
            # retrying a few times (the page may re-render while we inspect it).
            click_attempts = 4  # Increased from 3
            clicked = False
            for attempt in range(click_attempts):
                try:
                    if more_link is not None:
                        more_link_id = more_link.get_attribute('id') or '<anonymous>'
                        more_link_text = more_link.text.strip() or '<no text>'
                        logger.info(f"[UI_ACTION] Clicking 'More' button (id: {more_link_id}, text: '{more_link_text}') using native click")
                        more_link.click()
                        logger.info(f"[UI_ACTION] Successfully clicked 'More' button (id: {more_link_id})")
                        clicked = True
                        break
                    else:
                        # Try to re-find the element
                        raise Exception("More link is None, attempting to re-find")
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
                        if more_link is not None:
                            more_link_id = more_link.get_attribute('id') or '<anonymous>'
                            logger.info(f"[UI_ACTION] Native click failed, trying JavaScript click for 'More' button (id: {more_link_id})")
                            driver.execute_script("arguments[0].click();", more_link)
                            logger.info(f"[UI_ACTION] Successfully clicked 'More' button (id: {more_link_id}) using JavaScript")
                            clicked = True
                            break
                    except StaleElementReferenceException:
                        logger.info("More element became stale during JS click, retrying")
                        # clear and let the loop re-find
                        more_link = None
                        time.sleep(1)
                        continue
                    except Exception as click_err:
                        if more_link is None:
                            # Try to re-find the element
                            logger.info("More link is None, attempting to re-find element")
                            if target_row is not None:
                                for xp in candidate_xpaths:
                                    try:
                                        more_link = target_row.find_element(By.XPATH, xp)
                                        logger.debug(f"Re-found More element via {xp}")
                                        break
                                    except Exception:
                                        continue
                        else:
                            raise click_err

            if not clicked:
                raise Exception("Failed to click 'More' control after retries")

            # Add delay after clicking More to ensure modal is fully loaded
            logger.info("[UI_ACTION] Waiting 3 seconds after clicking 'More' button for modal to fully load")
            time.sleep(3)

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
            
            # Wait a bit longer for modal content to fully load
            time.sleep(2)
            
            # Try to find the main modal with better selector
            main_modal = None
            try:
                # Look for the main modal dialog
                main_modal = driver.find_element(By.ID, "ModalForm")
                logger.debug("Found main ModalForm dialog")
            except Exception:
                try:
                    # Fallback to any visible modal
                    main_modal = driver.find_element(By.XPATH, "//div[contains(@class, 'modal') and contains(@class, 'show')]")
                    logger.debug("Found visible modal dialog")
                except Exception:
                    logger.debug("Using original modal element")
                    main_modal = modal
            
            # Log modal content for debugging
            try:
                modal_text = main_modal.text
                logger.debug(f"Modal text preview (first 500 chars): {modal_text[:500]}")
                
                # Count tables in modal
                tables = main_modal.find_elements(By.TAG_NAME, "table")
                logger.debug(f"Found {len(tables)} table(s) in modal")
                
                for i, table in enumerate(tables):
                    rows = table.find_elements(By.TAG_NAME, "tr")
                    logger.debug(f"Table {i}: {len(rows)} rows")
                    if rows:
                        first_row_text = rows[0].text
                        logger.debug(f"Table {i} first row: {first_row_text}")
                        
            except Exception as e:
                logger.warning(f"Failed to analyze modal content: {e}")
            
            docket_entries = self._extract_docket_entries(main_modal, case_number)
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
                "case_id",
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

            return case, None

        except StaleElementReferenceException as e:
            logger.error(f"Stale element reference while scraping case {case_number}: {e}")
            # Suggest browser reinitialization due to stale elements
            try:
                self._close_modal()
            except Exception:
                pass
            return None, "stale_element"
        except Exception as e:
            logger.error(f"Error scraping case {case_number}: {e}")
            # Try to close modal if open
            try:
                self._close_modal()
            except Exception:
                pass
            return None, str(e)

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

        # Strategy 4: Extract from modal body paragraphs with <strong> tags (actual structure)
        try:
            modal_body = modal_element.find_element(By.CLASS_NAME, "modal-body")
            
            # Extract case_id from modal title first
            try:
                title_element = modal_element.find_element(By.ID, "modalTitle")
                title_text = title_element.text.strip()
                # Look for case number pattern in title (e.g., "IMM-2000-25")
                import re
                case_match = re.search(r'([A-Z]+-\d+-\d+)', title_text)
                if case_match:
                    data["case_id"] = case_match.group(1)
            except Exception:
                pass
            
            # Find all <strong> elements in the modal body
            strong_elements = modal_body.find_elements(By.TAG_NAME, "strong")
            
            for strong in strong_elements:
                try:
                    label_text = strong.text.strip().rstrip(":")
                    
                    # Get the parent element's text content
                    parent = strong.find_element(By.XPATH, "./..")
                    parent_text = parent.text.strip()
                    
                    # Extract the value after the strong label
                    value_text = ""
                    if strong.text in parent_text:
                        # Split on the strong text and take what comes after
                        parts = parent_text.split(strong.text, 1)
                        if len(parts) > 1:
                            value_text = parts[1].strip(" :\u00a0")  # Also strip non-breaking spaces
                    
                    # Map labels to field names
                    if value_text:
                        label_lower = label_text.lower()
                        if "type of action" in label_lower:
                            data["action_type"] = value_text
                        elif "type" in label_lower and "action" not in label_lower:
                            data["case_type"] = value_text
                        elif "nature of proceeding" in label_lower:
                            data["nature_of_proceeding"] = value_text
                        elif "filing date" in label_lower:
                            data["filing_date"] = _parse_date_str(value_text)
                        elif "office" in label_lower and "language" not in label_lower:
                            data["office"] = value_text
                        elif "language" in label_lower:
                            data["language"] = value_text
                        
                except Exception as e:
                    logger.debug(f"Failed to extract from strong element: {e}")
                    continue
                    
        except Exception as e:
            logger.debug(f"Failed to extract case header from modal body: {e}")

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

    def _parse_label_value_table(self, modal_element, label_variants):
        """Parse table rows where first cell is label and second cell is value."""
        parsed = {}
        try:
            rows = modal_element.find_elements(By.XPATH, ".//table//tr")
            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 2:
                        label = cells[0].text.strip().lower()
                        value = cells[1].text.strip()
                        for key, fld in label_variants.items():
                            if key in label:
                                if fld == "filing_date":
                                    parsed[fld] = _parse_date_str(value)
                                else:
                                    parsed[fld] = value or None
                                break
                except Exception:
                    continue
        except Exception:
            pass
        return parsed

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
            # Avoid treating numeric-only tokens (e.g., '1', '2') as dates, which
            # dateutil would interpret as day in current month; require explicit
            # separators or month names for a valid date.
            import re
            if re.fullmatch(r"\d{1,2}", s):
                return None
            try:
                return date.fromisoformat(s)
            except Exception:
                pass
            # common formats
            fmts = [
                "%Y-%m-%d",
                "%d-%b-%Y",
                "%d-%B-%Y",
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
                "%d-%b-%Y",
                "%d-%B-%Y",
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

                            # prefer day-first parsing where appropriate
                            d = _parse(ds, fuzzy=True, dayfirst=True)
                            return d.date()
                        except Exception:
                            pass
            except Exception:
                pass

            # Fallback: try dateutil on the whole string if available
            try:
                from dateutil.parser import parse as _parse

                # prefer day-first parsing where appropriate (e.g. '10-NOV-2025')
                d = _parse(s, fuzzy=True, dayfirst=True)
                return d.date()
            except Exception:
                return None

        try:
            # Choose the correct table for docket entries: prefer tables with headers matching 'ID' and 'Recorded Entry Summary' or 'Date Filed'
            tables = modal_element.find_elements(By.XPATH, ".//table")
            logger.debug(f"Found {len(tables)} tables in modal for docket extraction")
            
            # Log detailed information about each table
            for i, tbl in enumerate(tables):
                try:
                    tbl_text = tbl.text[:200] if tbl.text else "No text"
                    tbl_class = tbl.get_attribute('class') or "No class"
                    logger.debug(f"Table {i}: class='{tbl_class}', text='{tbl_text}'")
                except Exception as e:
                    logger.debug(f"Failed to analyze table {i}: {e}")
            
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
                                if v0 == "#" or v1.upper() == "YYYY-MM-DD" or v0 == "City":
                                    score -= 200  # Heavily penalize template table
                        except Exception:
                            pass
                    
                    # Prefer tables that have actual numeric IDs (not placeholders)
                    if nrows > 1:
                        try:
                            # Check if first column has numeric values
                            has_numeric_ids = False
                            for row in data_rows[:3]:  # Check first few rows
                                tds = row.find_elements(By.TAG_NAME, "td")
                                if tds:
                                    first_val = (tds[0].text or "").strip()
                                    if first_val.isdigit():
                                        has_numeric_ids = True
                                        break
                            if has_numeric_ids:
                                score += 50
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
                    
                    # Check for table classes that indicate the main data table
                    try:
                        table_class = t.get_attribute('class') or ''
                        if 'table-striped' in table_class and 'table-bordered' in table_class:
                            score += 30
                        logger.debug(f"Table {i} class: {table_class}")
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
                        logger.debug(f"Table {i} headers: {ths}")
                        
                        # High priority for exact match with "recorded entry summary"
                        if "recorded entry summary" in joined:
                            score += 100
                        elif any(
                            k in joined
                            for k in ["recorded entry", "recorded entry summary"]
                        ):
                            score += 40
                            
                        # Check for key column combinations
                        id_date = "id" in joined and ("date filed" in joined or "date" in joined)
                        id_summary = "id" in joined and ("recorded entry" in joined or "summary" in joined)
                        
                        if id_date and id_summary:
                            score += 50  # Perfect match
                        elif id_date:
                            score += 30
                        elif id_summary:
                            score += 25
                            
                        if "recorded" in joined and "summary" in joined:
                            score += 30
                            
                        # Check for office column
                        if "office" in joined:
                            score += 10
                            
                    except Exception:
                        joined = ""

                    # If table has at least one non-placeholder row but was small, give it a small boost
                    if nrows == 1 and score >= 10:
                        score += 5

                    candidates.append((score, t, nrows, i))  # Add index for tie-breaking
                except Exception:
                    continue

            # Choose best scored candidate (highest score); if none, fallback to first table
            if candidates:
                # Sort by score first, then by number of rows (prefer more data), then by table index (prefer later tables)
                candidates.sort(key=lambda it: (it[0], it[1], it[2]), reverse=True)
                best_score, best_table, best_nrows, table_idx = candidates[0]
                
                # If best score is too low (likely all are templates), prefer the table with most rows
                if best_score < 20:
                    try:
                        # Find table with most actual data rows (excluding template rows)
                        best_table_for_data = None
                        max_real_rows = 0
                        for score, table, nrows, idx in candidates:
                            if nrows > max_real_rows:
                                # Check if this table has real data (not just placeholder)
                                has_real_data = False
                                try:
                                    first_row = table.find_element(By.XPATH, ".//tbody//tr[1]")
                                    first_tds = first_row.find_elements(By.TAG_NAME, "td")
                                    if first_tds:
                                        first_val = (first_tds[0].text or "").strip()
                                        if first_val and first_val != "#" and first_val != "City" and first_val.isdigit():
                                            has_real_data = True
                                except Exception:
                                    pass
                                    
                                if has_real_data or nrows > max_real_rows:
                                    best_table_for_data = table
                                    max_real_rows = nrows
                        
                        if best_table_for_data:
                            table = best_table_for_data
                            logger.debug(f"Selected table with most real data rows: {max_real_rows}")
                        else:
                            table = best_table
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
            if table is None:
                logger.warning("No suitable table found for docket entries extraction")
                # As a fallback, try to find any table with content
                if tables:
                    logger.debug("Attempting to use first available table as fallback")
                    
                    # Try to find a table with multiple rows and reasonable content
                    for fallback_idx, fallback_table in enumerate(tables):
                        try:
                            fallback_rows = fallback_table.find_elements(By.TAG_NAME, "tr")
                            logger.debug(f"Fallback table {fallback_idx} has {len(fallback_rows)} rows")
                            
                            # Check if this table has more than just a header row
                            if len(fallback_rows) > 1:
                                # Check if it has actual data (not just placeholders)
                                has_data = False
                                for row_idx, row in enumerate(fallback_rows[1:], 1):
                                    cells = row.find_elements(By.TAG_NAME, "td")
                                    cell_texts = [c.text.strip() for c in cells]
                                    if any(cell_texts and ct != "#" and ct != "YYYY-MM-DD" for ct in cell_texts):
                                        has_data = True
                                        break
                                        
                                if has_data:
                                    logger.debug(f"Using fallback table {fallback_idx} with actual data")
                                    table = fallback_table
                                    break
                        except Exception as e:
                            logger.warning(f"Failed to analyze fallback table {fallback_idx}: {e}")
                            continue
                    
                    # If still no table found, use the first one
                    if table is None:
                        table = tables[0]
                        logger.debug("Using first table as last resort")
                else:
                    return entries
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

            # candidate tokens for columns (updated based on HTML analysis)
            date_keys = [
                "date filed",
                "date",
                "recorded",
                "recorded date",
                "entry date",
                "document date",
            ]
            office_keys = ["office", "registry", "court office", "location", "centre"]
            summary_keys = [
                "recorded entry summary",
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
            logger.debug(f"Found {len(rows)} rows in selected table")
            
            # If header row present, skip it when it contains th elements
            has_th = rows and rows[0].find_elements(By.TAG_NAME, "th")
            start_idx = 1 if has_th else 0
            logger.debug(f"Has header row: {has_th}, starting from index: {start_idx}")

            # Track parsing errors and abort on repeated failures to avoid saving partial/incorrect data
            parse_error_count = 0
            max_parse_errors = Config.get_docket_parse_max_errors()
            
            # Log header information if present
            if has_th:
                try:
                    header_cells = rows[0].find_elements(By.TAG_NAME, "th")
                    header_texts = [h.text.strip() for h in header_cells]
                    logger.debug(f"Table headers: {header_texts}")
                except Exception as e:
                    logger.warning(f"Failed to extract header texts: {e}")

            for r_idx, row in enumerate(rows[start_idx:], 1):
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    cell_texts = [c.text.strip() for c in cells]
                    logger.debug(f"Processing row {r_idx}: {len(cells)} cells, texts: {cell_texts}")
                    
                    # Skip rows with no content or placeholder content
                    if not any(cell_texts):
                        logger.debug(f"Skipping row {r_idx}: no content")
                        continue
                        
                    # Skip placeholder rows like the template row
                    if (len(cell_texts) >= 2 and 
                        (cell_texts[0] == "#" and cell_texts[1].upper() == "YYYY-MM-DD")):
                        logger.debug(f"Skipping row {r_idx}: placeholder/template row")
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

                    logger.debug(f"Creating docket entry: date={entry_date}, office={office}, summary={summary}")
                    
                    # Only create entry if we have at least some meaningful data
                    if summary or entry_date:
                        entry = DocketEntry(
                            case_id=case_id or "",
                            doc_id=r_idx,
                            entry_date=entry_date,
                            entry_office=office,
                            summary=summary,
                        )
                        entries.append(entry)
                        logger.debug(f"Successfully created docket entry {r_idx}")
                    else:
                        logger.debug(f"Skipping entry {r_idx}: no meaningful data (summary or date required)")
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
        logger.info("[UI_ACTION] Starting to close modal dialog")

        try:
            # First try to find the main modal dialog
            main_modal = None
            try:
                main_modal = driver.find_element(By.ID, "ModalForm")
                logger.debug("[UI_ACTION] Found main ModalForm dialog")
            except Exception:
                try:
                    main_modal = driver.find_element(By.XPATH, "//div[contains(@class, 'modal') and contains(@class, 'show')]")
                    logger.debug("[UI_ACTION] Found visible modal dialog")
                except Exception:
                    logger.debug("[UI_ACTION] Could not find specific modal, will search for close buttons globally")

            # Try different close methods with better selectors
            close_selectors = [
                # Try modal-specific close buttons first
                (By.XPATH, "//div[contains(@class, 'modal')]//button[contains(@class, 'close')]"),
                (By.XPATH, "//div[contains(@class, 'modal')]//button[@data-dismiss='modal']"),
                (By.XPATH, "//div[@id='ModalForm']//button[contains(@class, 'close')]"),
                (By.XPATH, "//div[@id='ModalForm']//button[@data-dismiss='modal']"),
                # Try text-based selectors
                (By.XPATH, "//button[contains(text(), 'Close')]"),
                (By.XPATH, "//button[contains(text(), 'Fermer')]"),
                # Try the × symbol
                (By.XPATH, "//span[@aria-hidden='true' and contains(text(), '×')]"),
                (By.XPATH, "//button[contains(@class, 'close')]"),
                # Fallback generic selectors
                (By.CLASS_NAME, "close"),
            ]

            for by, selector in close_selectors:
                try:
                    logger.info(f"[UI_ACTION] Looking for close button using selector: {selector}")
                    close_button = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((by, selector))
                    )
                    close_button_id = close_button.get_attribute('id') or '<anonymous>'
                    close_button_class = close_button.get_attribute('class') or '<no class>'
                    close_button_text = close_button.text.strip() or close_button.get_attribute('title') or '<no text>'
                    
                    # Try JavaScript click first (more reliable for modal buttons)
                    try:
                        driver.execute_script("arguments[0].click();", close_button)
                        logger.info(f"[UI_ACTION] Successfully closed modal using JS click (id: {close_button_id}, class: {close_button_class}, text: '{close_button_text}')")
                        return
                    except Exception:
                        # Fallback to native click
                        close_button.click()
                        logger.info(f"[UI_ACTION] Successfully closed modal using native click (id: {close_button_id}, class: {close_button_class}, text: '{close_button_text}')")
                        return
                except Exception as e:
                    logger.debug(f"[UI_ACTION] Failed to close modal with selector {selector}: {e}")
                    continue

            # Fallback: try pressing ESC key
            try:
                from selenium.webdriver.common.keys import Keys
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                logger.info("[UI_ACTION] Tried to close modal with ESC key")
                time.sleep(1)
                return
            except Exception as e:
                logger.debug(f"[UI_ACTION] ESC key failed: {e}")

            # Final fallback: refresh page
            logger.warning("[UI_ACTION] Could not find any close button, refreshing page to close modal")
            driver.refresh()

        except Exception as e:
            logger.error(f"[UI_ACTION] Error closing modal: {e}")
            logger.info("[UI_ACTION] Refreshing page due to modal close error")
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
