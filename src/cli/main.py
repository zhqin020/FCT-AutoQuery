"""Command-line interface for Federal Court Case Scraper."""

import argparse
import sys
import time
import random
import os
import json
from datetime import datetime, timezone
from typing import Optional

# Add the project root to Python path for proper imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from src.lib.config import Config
from src.lib.logging_config import get_logger, setup_logging
from src.models.case import Case
from src.services.case_scraper_service import CaseScraperService
from src.services.export_service import ExportService
from src.services.url_discovery_service import UrlDiscoveryService
from src.services.batch_service import BatchService
from src.services.case_tracking_service import CaseTrackingService
from src.cli.tracking_integration import TrackingIntegration, create_tracking_integrated_check_exists, create_tracking_integrated_scrape_case
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
try:
    from metrics_emitter import emit_metric  # type: ignore
except Exception:
    # Provide a no-op fallback for test environments lacking metrics_emitter
    def emit_metric(*_args, **_kwargs):
        return None
from src.cli.purge import purge_year
from src.lib.rate_limiter import EthicalRateLimiter

logger = get_logger()


class FederalCourtScraperCLI:
    """Command-line interface for the Federal Court Case Scraper."""

    def __init__(self):
        """Initialize the CLI."""
        # Setup logging to console and file (respect configured log level)
        setup_logging(log_level=Config.get_log_level(), log_file="logs/scraper.log")

        self.config = Config()
        # Prefer non-headless in CLI runs to match interactive harness behavior
        # and avoid client-side rendering differences seen in headless mode.
        # Lazily initialize the scraper to avoid launching a browser when all
        # cases are already present in the DB.
        self.scraper = None
        self._scraper_headless = False
        self.discovery = UrlDiscoveryService(self.config)
        self.exporter = ExportService(self.config)
        self.tracker = CaseTrackingService()
        self.current_run_id = None
        self.emergency_stop = False
        self.consecutive_failures = 0
        self.max_consecutive_failures = 10  # Emergency stop threshold
        # Track cases processed for periodic browser reinitialization
        self.cases_processed_since_restart = 0
        self.max_cases_before_restart = 500  # Deep restart every 500 cases
        # Rate limiter used across CLI operations to apply backoff on transient failures
        self.rate_limiter = EthicalRateLimiter(
            interval_seconds=Config.get_rate_limit_seconds(),
            backoff_factor=Config.get_backoff_factor(),
            max_backoff_seconds=Config.get_max_backoff_seconds(),
        )
        # Force flag determines whether existing DB records should be re-scraped
        self.force = False

    def scrape_single_case(self, case_number: str) -> Optional[Case]:
        """
        Scrape a single case by case number.

        Args:
            case_number: Case number to scrape (e.g., IMM-12345-25)

        Returns:
            Case object if successful, None otherwise
        """
        
        if self.emergency_stop:
            logger.warning("Emergency stop active - skipping case scrape")
            return None

        logger.info(f"Starting scrape of case: {case_number}")
        # Emit job start metric (timestamped) and record start time for duration
        job_start_ts = time.time()
        try:
            emit_metric("batch.job.start", job_start_ts)
        except Exception:
            pass

        try:
            # Lazily create scraper if not initialized
            if self.scraper is None:
                self.scraper = CaseScraperService(headless=self._scraper_headless)

            # Initialize page only if not already initialized (reuse session across batch)
            # But ensure we're on the correct search tab
            try:
                if not getattr(self.scraper, "_initialized", False):
                    self.scraper.initialize_page()
                else:
                    logger.info("[UI_ACTION] Reusing initialized page; ensuring search tab is active")
                    # Even if page is initialized, ensure we're on the search tab
                    self._ensure_search_tab()
            except Exception as e:
                logger.error(f"Failed to initialize page for scraping: {e}")
                raise

            # Search for the case
            found = self.scraper.search_case(case_number)
            if not found:
                # Check if page contains 'No data available in table'
                driver = self.scraper._get_driver()
                page_text = driver.page_source
                is_no_data = 'No data available in table' in page_text
                
                if is_no_data:
                    logger.warning(f"Case {case_number} has no data available in table")
                    # Record as no_data
                    try:
                        self.tracker.record_case_processing(
                            case_number=case_number,
                            run_id=self.current_run_id or "unknown",
                            outcome="no_data",
                            error_message="No data available in table",
                            processing_mode="single"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record tracking data for {case_number}: {e}")
                    
                    # 标记为 no_data
                    try:
                        from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
                        simplified_tracker = SimplifiedTrackingService()
                        simplified_tracker.mark_case_attempt(case_number, CaseStatus.NO_DATA)
                    except Exception as e:
                        logger.warning(f"Failed to mark case no_data for {case_number}: {e}")
                    
                    return None
                else:
                    logger.warning(f"Case {case_number} not found")
                    # record transient failure and backoff
                    try:
                        delay = self.rate_limiter.record_failure()
                        # Add extra random jitter for consecutive failures
                        jitter = random.uniform(0.5, 2.0) if self.consecutive_failures > 3 else 0
                        time.sleep(delay + jitter)
                    except Exception:
                        # best-effort small sleep with jitter
                        base_sleep = 0.1
                        if self.consecutive_failures > 3:
                            base_sleep = random.uniform(1.0, 2.0)
                        time.sleep(base_sleep)
                    self.consecutive_failures += 1
                    
                    # Record not found to tracking system as failed
                    try:
                        self.tracker.record_case_processing(
                            case_number=case_number,
                            run_id=self.current_run_id or "unknown",
                            outcome="failed",
                            error_message="Case not found",
                            processing_mode="single"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record tracking data for {case_number}: {e}")
                    
                    return None

            # Scrape the case data with retries that re-run the search page
            case = None
            # Use runtime-configurable retry count from Config
            try:
                max_scrape_attempts = int(Config.get_max_retries())
            except Exception:
                max_scrape_attempts = 3
            for attempt in range(1, max_scrape_attempts + 1):
                try:
                    case, error_type = self.scraper.scrape_case_data(case_number)
                except Exception as e:
                    logger.error(
                        f"Exception during scrape_case_data attempt {attempt} for {case_number}: {e}",
                        exc_info=True,
                    )
                    case = None
                    error_type = str(e)
                
                # Check if we need browser reinitialization due to stale elements
                if error_type == "stale_element":
                    logger.warning(f"Stale element detected for {case_number}, triggering browser deep initialization")
                    try:
                        self._deep_reinitialize_browser()
                    except Exception as init_err:
                        logger.error(f"Failed to deep reinitialize browser after stale element: {init_err}")
                    
                    # After deep reinitialization, we must re-run the search
                    # because the page has been cleared
                    logger.info(f"Re-searching case {case_number} after browser reinitialization")
                    try:
                        found = self.scraper.search_case(case_number)
                        if not found:
                            logger.error(f"Case {case_number} not found after reinitialization")
                            # Try to check if it's a no_data case
                            driver = self.scraper._get_driver()
                            page_text = driver.page_source
                            is_no_data = 'No data available in table' in page_text
                            if is_no_data:
                                error_type = "no_data"
                            else:
                                error_type = "not_found"
                    except Exception as search_err:
                        logger.error(f"Failed to search case {case_number} after reinitialization: {search_err}")
                        error_type = "search_failed"
                    
                    # Reset attempt counter to retry after reinitialization
                    continue

                if case:
                    logger.info(f"Successfully scraped case: {case.case_id} (attempt {attempt})")
                    self.consecutive_failures = 0
                    self.cases_processed_since_restart += 1
                    
                    # Periodic deep reinitialization to prevent long-running issues
                    if self.cases_processed_since_restart >= self.max_cases_before_restart:
                        logger.info(f"Periodic deep browser reinitialization after {self.cases_processed_since_restart} cases")
                        try:
                            self._deep_reinitialize_browser()
                            self.cases_processed_since_restart = 0
                            logger.info("Periodic browser reinitialization completed")
                        except Exception as init_err:
                            logger.error(f"Failed periodic browser reinitialization: {init_err}")
                    try:
                        self.rate_limiter.reset_failures()
                    except Exception:
                        pass
                    # Emit job success metrics: duration and retry count
                    try:
                        emit_metric("batch.job.duration_seconds", time.time() - job_start_ts)
                        emit_metric("batch.job.retry_count", float(attempt))
                    except Exception:
                        pass
                    break
                logger.warning(f"Scrape attempt {attempt} failed for case: {case_number}")
                # record failure/backoff before retrying
                try:
                    delay = self.rate_limiter.record_failure()
                    # Add progressive delay for consecutive failures
                    progressive_delay = delay + (self.consecutive_failures * random.uniform(0.5, 1.5))
                    time.sleep(progressive_delay)
                except Exception:
                    # Fallback with progressive delay
                    fallback_delay = min(5.0, 0.1 + (self.consecutive_failures * 0.5))
                    time.sleep(fallback_delay)
                if attempt < max_scrape_attempts:
                    # Add a longer delay before retry to allow server state to settle
                    logger.info(f"Waiting before retry attempt {attempt+1}")
                    time.sleep(3)
                    
                    # Re-initialize the page to recover from transient DOM state
                    try:
                        logger.info("Re-initializing page before retry (without search mode)")
                        try:
                            self.scraper.initialize_page()
                        except Exception as e:
                            logger.debug(f"initialize_page during retry failed: {e}", exc_info=True)
                            # If initialization fails, try to search for the case first
                            try:
                                logger.info(f"Attempting to re-search case {case_number} before retry")
                                found = self.scraper.search_case(case_number)
                                if not found:
                                    logger.debug(f"Re-search did not find the case; will re-initialize again")
                                    try:
                                        self.scraper.initialize_page()
                                    except Exception:
                                        pass
                            except Exception as e:
                                logger.error(f"Exception during search_case retry for {case_number}: {e}", exc_info=True)
                    except Exception as e:
                        logger.debug(f"Error during retry recovery: {e}", exc_info=True)
                    time.sleep(1)
                if attempt < max_scrape_attempts:
                    # Re-run the search from the search page to recover from transient DOM state
                    try:
                        logger.info("Re-running search on search page before retry")
                        # Re-initialize the page if necessary, then search
                        try:
                            if not getattr(self.scraper, "_initialized", False):
                                self.scraper.initialize_page()
                        except Exception as e:
                            logger.debug(f"initialize_page during retry failed: {e}", exc_info=True)

                        try:
                            found = self.scraper.search_case(case_number)
                        except Exception as e:
                            logger.error(
                                f"Exception during search_case retry for {case_number}: {e}",
                                exc_info=True,
                            )
                            found = False

                        if not found:
                            logger.debug(
                                "Re-search did not find the case; will re-initialize and retry",
                                exc_info=False,
                            )
                            try:
                                self.scraper.initialize_page()
                            except Exception:
                                pass
                    except Exception as e:
                        logger.debug(f"Error during retry search: {e}", exc_info=True)
                    time.sleep(1)

            if case:
                # Immediately export per-case JSON and save to DB to ensure
                # artifacts exist even if a later failure occurs.
                try:
                    json_path = self.exporter.export_case_to_json(case)
                    logger.info(f"Per-case JSON written: {json_path}")
                except Exception as e:
                    logger.error(f"Failed to write per-case JSON for {case_number}: {e}")

                try:
                    status, msg = self.exporter.save_case_to_database(case)
                    logger.info(f"Database save status for {case_number}: {status}")
                except Exception as e:
                    logger.error(f"Failed to save case {case_number} to database: {e}")

                # Record successful processing to tracking system
                try:
                    self.tracker.record_case_processing(
                        case_number=case_number,
                        run_id=self.current_run_id or "unknown",
                        outcome="success",
                        case_id=getattr(case, 'case_id', None),
                        processing_mode="single"
                    )
                except Exception as e:
                    logger.warning(f"Failed to record tracking data for {case_number}: {e}")
                
                # 标记为成功采集
                try:
                    from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
                    simplified_tracker = SimplifiedTrackingService()
                    simplified_tracker.mark_case_attempt(case_number, CaseStatus.SUCCESS)
                except Exception as e:
                    logger.warning(f"Failed to mark case success for {case_number}: {e}")

                return case
            else:
                logger.warning(f"Failed to scrape case after {max_scrape_attempts} attempts: {case_number}")
                # record failure/backoff
                try:
                    delay = self.rate_limiter.record_failure()
                    # Add progressive delay for consecutive failures
                    progressive_delay = delay + (self.consecutive_failures * random.uniform(0.5, 1.5))
                    time.sleep(progressive_delay)
                except Exception:
                    # Fallback with progressive delay
                    fallback_delay = min(5.0, 0.1 + (self.consecutive_failures * 0.5))
                    time.sleep(fallback_delay)
                self.consecutive_failures += 1
                # Emit job failure metrics: duration and retry count
                try:
                    emit_metric("batch.job.duration_seconds", time.time() - job_start_ts)
                    emit_metric("batch.job.retry_count", float(max_scrape_attempts))
                except Exception:
                    pass
                
                # Record failed processing to tracking system
                try:
                    self.tracker.record_case_processing(
                        case_number=case_number,
                        run_id=self.current_run_id or "unknown",
                        outcome="failed",
                        error_message=f"Failed after {max_scrape_attempts} attempts",
                        processing_mode="single"
                    )
                except Exception as e:
                    logger.warning(f"Failed to record tracking data for {case_number}: {e}")
                
                # 标记为失败
                try:
                    from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
                    simplified_tracker = SimplifiedTrackingService()
                    simplified_tracker.mark_case_attempt(case_number, CaseStatus.FAILED, f"Failed after {max_scrape_attempts} attempts")
                except Exception as e:
                    logger.warning(f"Failed to mark case failure for {case_number}: {e}")
                
                return None

        except Exception as e:
            logger.error(f"Error scraping case {case_number}: {e}")
            self.consecutive_failures += 1
            # Record as error state to distinguish from failed scraping
            try:
                from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
                simplified_tracker = SimplifiedTrackingService()
                simplified_tracker.mark_case_attempt(case_number, CaseStatus.ERROR, str(e))
            except Exception:
                pass
            return None
        finally:
            # Do not close the full WebDriver here to enable session reuse
            # across batch operations. Individual modal/page cleanup is
            # performed inside CaseScraperService methods.
            
            # Memory cleanup for individual case (if enabled)
            if Config.get_enable_memory_management():
                try:
                    import gc
                    # Trigger garbage collection after each case to free up memory
                    collected = gc.collect()
                    logger.debug(f"Memory cleanup after case {case_number}: {collected} objects collected")
                except Exception:
                    pass

            # Check for emergency stop
            if self.consecutive_failures >= self.max_consecutive_failures:
                logger.error(
                    f"Emergency stop triggered after {self.consecutive_failures} consecutive failures"
                )
                self.emergency_stop = True
                # Perform deep browser reinitialization before stopping
                try:
                    self._deep_reinitialize_browser()
                except Exception as e:
                    logger.error(f"Failed to deep reinitialize browser: {e}")

    def _ensure_search_tab(self) -> None:
        """Ensure we're on the 'Search by court number' tab before searching."""
        if self.scraper is None:
            logger.error("[UI_ACTION] Scraper not initialized, cannot ensure search tab")
            return
            
        driver = self.scraper._get_driver()
        try:
            # Try to find and click the search tab
            logger.info("[UI_ACTION] Ensuring 'Search by court number' tab is active")
            search_tab = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "Search by court number"))
            )
            # Check if the tab is already active by looking for the input field
            input_found = False
            for input_id in ["selectCourtNumber", "courtNumber", "selectRetcaseCourtNumber"]:
                try:
                    driver.find_element(By.ID, input_id)
                    input_found = True
                    break
                except Exception:
                    continue
            
            if not input_found:
                # Click the tab to ensure search input is visible
                logger.info("[UI_ACTION] Search input not found, clicking 'Search by court number' tab")
                try:
                    search_tab.click()
                    logger.info("[UI_ACTION] Successfully clicked 'Search by court number' tab")
                except Exception:
                    driver.execute_script("arguments[0].click();", search_tab)
                    logger.info("[UI_ACTION] Successfully clicked 'Search by court number' tab using JavaScript")
            else:
                logger.debug("[UI_ACTION] Search input already visible, tab appears to be active")
                
        except Exception as e:
            logger.warning(f"[UI_ACTION] Failed to ensure search tab is active: {e}")
            # If ensuring tab fails, fall back to full page initialization
            try:
                self.scraper._initialized = False
                self.scraper.initialize_page()
                logger.info("[UI_ACTION] Fell back to full page initialization")
            except Exception as init_err:
                logger.error(f"[UI_ACTION] Fallback initialization failed: {init_err}")
                raise

    def _deep_reinitialize_browser(self) -> None:
        """
        Perform deep browser reinitialization to clear caches, cookies, and session state.
        This is called when consecutive failures suggest the browser session is corrupted
        or periodically to prevent long-running issues.
        """
        logger.info("Performing deep browser reinitialization")
        
        try:
            if self.scraper and hasattr(self.scraper, '_driver') and self.scraper._driver:
                driver = self.scraper._driver
                
                # Aggressive cleanup for long-running sessions
                cleanup_commands = [
                    # Clear cookies and session data
                    "document.cookie.split(';').forEach(function(c) { document.cookie = c.replace(/^ +/, '').replace(/=.*/, '=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/'); });",
                    "window.localStorage.clear();",
                    "window.sessionStorage.clear();",
                    # Clear IndexedDB
                    "if (window.indexedDB) { indexedDB.databases().then(dbs => dbs.forEach(db => indexedDB.deleteDatabase(db.name))); }",
                    # Clear WebSQL
                    "if (window.openDatabase) { try { window.openDatabase('', '', '', '', 1).transaction(function(tx) { tx.executeSql('DELETE FROM __WebKitDatabaseInfoTable__'); }); } catch(e) {} }",
                    # Force garbage collection
                    "if (window.gc) { window.gc(); } else if (performance.memory) { performance.memory.usedJSHeapSize = 0; }",
                    # Clear application cache
                    "if ('caches' in window) { caches.keys().then(names => names.forEach(name => caches.delete(name))); }",
                    # Reset any potential event listeners that might interfere
                    "if (window.stop) { window.stop(); }",
                ]
                
                for cmd in cleanup_commands:
                    try:
                        driver.execute_script(cmd)
                        time.sleep(0.1)  # Small delay between commands
                    except Exception as e:
                        logger.debug(f"Cleanup command failed: {e}")
                
                # Traditional cookie clearing as backup
                try:
                    driver.delete_all_cookies()
                    logger.info("Cleared all browser cookies")
                except Exception as e:
                    logger.debug(f"Failed to clear cookies: {e}")
                
                # Extended wait to allow all cleanup operations
                logger.info("Waiting for browser cleanup to complete")
                time.sleep(random.uniform(3.0, 6.0))
                
                # Force restart the driver completely
                if hasattr(self.scraper, '_restart_driver'):
                    # Reset restart count to allow immediate restart
                    original_count = getattr(self.scraper, '_restart_count', 0)
                    self.scraper._restart_count = 0
                    self.scraper._restart_driver()
                    self.scraper._restart_count = original_count + 1
                    logger.info("Browser driver restarted completely")
                
                # Re-initialize the page with extended delay and fresh state
                if hasattr(self.scraper, 'initialize_page'):
                    time.sleep(random.uniform(4.0, 7.0))
                    # Reset initialization state before calling initialize_page
                    self.scraper._initialized = False
                    self.scraper.initialize_page()
                    logger.info("Browser page reinitialized with fresh state")
                    
        except Exception as e:
            logger.error(f"Error during deep browser reinitialization: {e}")
            # As a fallback, try to recreate the entire scraper
            try:
                self.scraper = None  # Force recreation on next use
                time.sleep(random.uniform(5.0, 8.0))
                logger.info("Recreated scraper instance as fallback")
            except Exception:
                pass

    def _scrape_case_data_without_search(self, case_number: str) -> Optional[Case]:
        """
        Scrape case data without performing a search first.
        This is used when we already know the case exists from probing.
        
        Args:
            case_number: Case number to scrape (e.g., IMM-12345-25)
        
        Returns:
            Case object if successful, None otherwise
        """
        # Ensure that a run ID exists when scraping without search: some callers
        # (e.g. manual invocation or internal probe scrapers) may call this helper
        # directly and not have started a run. Start one for compatibility so
        # that tracking calls are always attributed to a run.
        if not hasattr(self, 'current_run_id') or self.current_run_id is None:
            try:
                self.current_run_id = self.tracker.start_run(
                    processing_mode="single",
                    parameters={"case_number": case_number},
                )
            except Exception:
                # best-effort: allow scraping to continue even if DB errors occur
                self.current_run_id = None

        if self.emergency_stop:
            logger.warning("Emergency stop active - skipping case scrape")
            return None

        logger.info(f"Scraping case data without search: {case_number}")
        job_start_ts = time.time()
        try:
            emit_metric("batch.job.start", job_start_ts)
        except Exception:
            pass

        try:
            # Ensure scraper is initialized
            if self.scraper is None:
                self.scraper = CaseScraperService(headless=self._scraper_headless)

            # Initialize page if needed
            try:
                if not getattr(self.scraper, "_initialized", False):
                    self.scraper.initialize_page()
            except Exception as e:
                logger.error(f"Failed to initialize page for scraping: {e}")
                raise

            # Scrape the case data with retries
            case = None
            try:
                max_scrape_attempts = int(Config.get_max_retries())
            except Exception:
                max_scrape_attempts = 3
                
            for attempt in range(1, max_scrape_attempts + 1):
                try:
                    case, error_type = self.scraper.scrape_case_data(case_number)
                except Exception as e:
                    logger.error(
                        f"Exception during scrape_case_data attempt {attempt} for {case_number}: {e}",
                        exc_info=True,
                    )
                    case = None
                    error_type = str(e)
                
                # Check if we need browser reinitialization due to stale elements
                if error_type == "stale_element":
                    logger.warning(f"Stale element detected for {case_number}, triggering browser deep initialization")
                    try:
                        self._deep_reinitialize_browser()
                    except Exception as init_err:
                        logger.error(f"Failed to deep reinitialize browser after stale element: {init_err}")
                    
                    # After deep reinitialization, we must re-run the search
                    # because the page has been cleared
                    logger.info(f"Re-searching case {case_number} after browser reinitialization")
                    try:
                        found = self.scraper.search_case(case_number)
                        if not found:
                            logger.error(f"Case {case_number} not found after reinitialization")
                            # Try to check if it's a no_data case
                            driver = self.scraper._get_driver()
                            page_text = driver.page_source
                            is_no_data = 'No data available in table' in page_text
                            if is_no_data:
                                error_type = "no_data"
                            else:
                                error_type = "not_found"
                    except Exception as search_err:
                        logger.error(f"Failed to search case {case_number} after reinitialization: {search_err}")
                        error_type = "search_failed"
                    
                    # Reset attempt counter to retry after reinitialization
                    continue

                if case:
                    logger.info(f"Successfully scraped case data without search: {case.case_id} (attempt {attempt})")
                    self.consecutive_failures = 0
                    try:
                        self.rate_limiter.reset_failures()
                    except Exception:
                        pass
                    # Emit job success metrics: duration and retry count
                    try:
                        emit_metric("batch.job.duration_seconds", time.time() - job_start_ts)
                        emit_metric("batch.job.retry_count", float(attempt))
                    except Exception:
                        pass
                    break
                logger.warning(f"Scrape attempt {attempt} failed for case: {case_number}")
                # record failure/backoff before retrying
                try:
                    delay = self.rate_limiter.record_failure()
                    # Add progressive delay for consecutive failures
                    progressive_delay = delay + (self.consecutive_failures * random.uniform(0.5, 1.5))
                    time.sleep(progressive_delay)
                except Exception:
                    # Fallback with progressive delay
                    fallback_delay = min(5.0, 0.1 + (self.consecutive_failures * 0.5))
                    time.sleep(fallback_delay)
                if attempt < max_scrape_attempts:
                    # Add a longer delay before retry to allow server state to settle
                    logger.info(f"Waiting before retry attempt {attempt+1}")
                    time.sleep(3)
                    
                    # Re-initialize the page to recover from transient DOM state
                    try:
                        logger.info("Re-initializing page before retry (without search mode)")
                        try:
                            self.scraper.initialize_page()
                        except Exception as e:
                            logger.debug(f"initialize_page during retry failed: {e}", exc_info=True)
                            # If initialization fails, try to search for the case first
                            try:
                                logger.info(f"Attempting to re-search case {case_number} before retry")
                                found = self.scraper.search_case(case_number)
                                if not found:
                                    logger.debug(f"Re-search did not find the case; will re-initialize again")
                                    try:
                                        self.scraper.initialize_page()
                                    except Exception:
                                        pass
                            except Exception as e:
                                logger.error(f"Exception during search_case retry for {case_number}: {e}", exc_info=True)
                    except Exception as e:
                        logger.debug(f"Error during retry recovery: {e}", exc_info=True)
                    time.sleep(1)

            if case:
                # Immediately export per-case JSON and save to DB
                try:
                    json_path = self.exporter.export_case_to_json(case)
                    logger.info(f"Per-case JSON written: {json_path}")
                except Exception as e:
                    logger.error(f"Failed to write per-case JSON for {case_number}: {e}")

                try:
                    status, msg = self.exporter.save_case_to_database(case)
                    logger.info(f"Database save status for {case_number}: {status}")
                except Exception as e:
                    logger.error(f"Failed to save case {case_number} to database: {e}")

                # Record successful processing to tracking system
                try:
                    self.tracker.record_case_processing(
                        case_number=case_number,
                        run_id=self.current_run_id or "unknown",
                        outcome="success",
                        case_id=getattr(case, 'case_id', None),
                        processing_mode="single"
                    )
                except Exception as e:
                    logger.warning(f"Failed to record tracking data for {case_number}: {e}")
                
                # 标记为成功采集
                try:
                    from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
                    simplified_tracker = SimplifiedTrackingService()
                    simplified_tracker.mark_case_attempt(case_number, CaseStatus.SUCCESS)
                except Exception as e:
                    logger.warning(f"Failed to mark case success for {case_number}: {e}")

                return case
            else:
                logger.warning(f"Failed to scrape case data after {max_scrape_attempts} attempts: {case_number}")
                self.consecutive_failures += 1
                return None

        except Exception as e:
            logger.error(f"Error scraping case data {case_number}: {e}")
            self.consecutive_failures += 1
            return None

    def shutdown(self) -> None:
        """Shutdown resources (close scraper)"""
        try:
            if self.scraper:
                self.scraper.close()
        except Exception:
            pass
    def scrape_batch_cases(
        self, year: int, max_cases: Optional[int] = None, start: Optional[int] = None, max_exponent: Optional[int] = None
    ) -> tuple[list, dict]:
        """
        Scrape multiple cases for a given year using exponential probing with collection, then linear collection.

        Args:
            year: Year to scrape cases for
            max_cases: Maximum number of cases to scrape
            start: Starting number for probing
            max_exponent: Maximum exponent for exponential probing (2^i steps)

        Returns:
            List of scraped Case objects
        """
        logger.info(f"=== 开始批处理采集任务 ===")
        logger.info(f"参数: year={year}, max_cases={max_cases}, start={start}")
        logger.debug(f"系统状态: force={self.force}, emergency_stop={self.emergency_stop}")

        # Import enhanced statistics service
        from src.services.enhanced_statistics_service import EnhancedStatisticsService
        stats_service = EnhancedStatisticsService()

        # Display pre-run statistics
        pre_run_stats = stats_service.get_year_statistics(year)
        stats_service.log_and_display_statistics(pre_run_stats, f"采集前统计信息 (Pre-Run Statistics) - {year}")

        logger.info(f"Starting batch scrape for year {year}")
        run_start_ts = time.time()
        run_start_time = datetime.now(timezone.utc)
        try:
            emit_metric("batch.run.start", run_start_ts)
        except Exception:
            pass

        # Ensure scraper is initialized
        if self.scraper is None:
            logger.debug("初始化CaseScraperService...")
            self.scraper = CaseScraperService(headless=self._scraper_headless)
            logger.debug("CaseScraperService初始化完成")

        # Initialize page only if not already initialized (reuse session across batch)
        try:
            if not getattr(self.scraper, "_initialized", False):
                logger.debug("初始化浏览器页面...")
                self.scraper.initialize_page()
                logger.debug("浏览器页面初始化完成")
            else:
                logger.info("Reusing initialized page; skipping initialize_page()")
        except Exception as e:
            logger.error(f"Failed to initialize page for scraping: {e}")
            raise

        cases = []
        consecutive_failures = 0
        processed = 0
        skipped = []  # Will be truncated to prevent memory accumulation
        max_skipped_log = Config.get_max_skipped_log()  # Maximum skipped records to keep in memory
        skip_report_interval = Config.get_skip_report_interval()  # Report interval for skip statistics
        skipped_counter = 0  # Track total skipped cases for reporting
        last_skipped_report = 0  # Track last time we reported skipped stats

        # Start batch run tracking
        logger.debug("启动批处理运行跟踪...")
        batch_run_id = self.tracker.start_run(
            processing_mode="batch_collect",
            parameters={
                "year": year,
                "max_cases": max_cases,
                "start": start
            }
        )
        logger.info(f"批处理运行ID: {batch_run_id}")

        # Use the CLI-configured/shared rate limiter for probing/backoff
        rl = getattr(self, "rate_limiter", None) or EthicalRateLimiter(
            interval_seconds=Config.get_rate_limit_seconds(),
            backoff_factor=Config.get_backoff_factor(),
            max_backoff_seconds=Config.get_max_backoff_seconds(),
        )
        logger.debug(f"速率限制器配置: interval={Config.get_rate_limit_seconds()}s, backoff_factor={Config.get_backoff_factor()}")

        # Create tracking integration instance for this batch
        integration = TrackingIntegration(self.tracker, batch_run_id)
        logger.debug("TrackingIntegration实例创建完成")

        # Define check_case_exists function for probing with tracking
        def check_case_exists(case_num: int) -> bool:
            case_number = f"IMM-{case_num}-{year % 100:02d}"
            try:
                # First, check if this case should be skipped based on tracking rules
                try:
                    should_skip, reason = self.tracker.should_skip_case(case_number, force=self.force, run_id=batch_run_id)
                except TypeError:
                    # Backwards compatibility with tests that stub should_skip_case without run_id kwarg
                    should_skip, reason = self.tracker.should_skip_case(case_number, force=self.force)
                if should_skip:
                    logger.info(f"Skipping {case_number}: {reason}")
                    # Record as a skipped probe to tracking (no network call)
                    try:
                        self.tracker.record_case_processing(
                            case_number=case_number,
                            run_id=batch_run_id,
                            outcome="skipped",
                            reason=reason,
                            processing_mode="batch_probe",
                        )
                    except Exception:
                        pass
                    # If the skip reason is 'exists_in_db' we do NOT mark it found
                    if "exists_in_db" in reason:
                        return False  # Return False to prevent collection
                    return False

                # Next check if the case already exists in database (unless forcing)
                if not self.force and self.exporter.case_exists(case_number):
                    logger.info(f"Case {case_number} already exists in database, skipping web search")
                    # Record skip to tracking system
                    self.tracker.record_case_processing(
                        case_number=case_number,
                        run_id=batch_run_id,
                        outcome="skipped",
                        reason="exists_in_db",
                        processing_mode="batch_probe"
                    )
                    return True

                # If not in DB or forcing, do web search
                if self.scraper is None:
                    self.scraper = CaseScraperService(headless=self._scraper_headless)
                result = self.scraper.search_case(case_number)
                if result:
                    # Record successful probe via integration helper
                    integration.record_probe_result(case_number, True)
                else:
                    # Record no results via integration helper
                    integration.record_probe_result(case_number, False)

                return result
            except Exception as e:
                logger.warning(f"search_case failed for {case_number}: {e}")
                try:
                    integration.record_probe_result(case_number, False, error_message=str(e))
                except Exception:
                    pass
                return False

        # Define scrape_case_data function for collection during probing with tracking
        def scrape_case_data(case_num: int) -> Optional[object]:
            case_number = f"IMM-{case_num}-{year % 100:02d}"
            try:
                # Check if this case should be skipped based on tracking rules
                should_skip, reason = self.tracker.should_skip_case(case_number, force=self.force, run_id=batch_run_id)
                if should_skip:
                    logger.info(f"Skipping scrape for {case_number} due to tracking: {reason}")
                    try:
                        integration.record_scrape_result(case_number, False, outcome='skipped', error_message=reason)
                    except Exception:
                        pass
                    return None

                # Scrape the case data
                case = self.scrape_single_case(case_number)

                if case:
                    cases.append(case)
                    # Record successful collection via integration helper
                    integration.record_scrape_result(case_number, True, case_id=getattr(case, "case_id", None))
                    return case
                else:
                    # Check if case was already marked as no_data before treating as failed
                    case_info = self.tracker.get_case_status(case_number)
                    if case_info and case_info.get('last_outcome') == 'no_data':
                        logger.info(f"Case {case_number} already marked as no_data, not treating as failure")
                        integration.record_scrape_result(case_number, False, outcome='no_data', error_message="Case not found")
                        return None
                    else:
                        integration.record_scrape_result(case_number, False, error_message="Scraping failed")
            except Exception as e:
                logger.exception(f"Error scraping case {case_number}: {e}")
                try:
                    integration.record_scrape_result(case_number, False, error_message=str(e))
                except Exception:
                    pass
            return None

        # Enhanced fast check that returns detailed status information
        def enhanced_fast_check(n: int):
            """Fast DB check that returns a standardized dict including status and skip_reason."""
            if self.force:
                return {
                    'exists': False,
                    'db_exists': False,
                    'status': 'unknown',
                    'skip_reason': '',
                    'should_skip': False
                }

            case_number = f"IMM-{n}-{year % 100:02d}"
            try:
                should_skip, skip_reason = self.tracker.should_skip_case(case_number, force=self.force, run_id=batch_run_id)
            except Exception:
                try:
                    should_skip, skip_reason = self.tracker.should_skip_case(case_number, force=self.force)
                except Exception:
                    should_skip, skip_reason = (False, '')

            try:
                status_info = self.tracker.get_case_status(case_number) or {}
                last_outcome = status_info.get('last_outcome', 'unknown')
            except Exception:
                last_outcome = 'unknown'

            db_exists = 'exists_in_db' in skip_reason

            return {
                'exists': db_exists,
                'db_exists': db_exists,
                'status': last_outcome,
                'skip_reason': skip_reason,
                'should_skip': should_skip
            }

        # Phase 1: Exponential probing to find upper bound
        logger.info("Starting exponential probing to find upper bound")
        print("开始指数探测阶段...")
        logger.info("=== 指数探测阶段配置 ===")
        logger.info(f"start: {start or 1}")
        logger.info(f"max_exponent: {getattr(self, 'max_exponent', Config.get_max_exponent())}")
        logger.info(f"max_cases: {max_cases or 100000}")

        upper, probes, collected_cases = BatchService.exponential_probe_and_collect(
            check_case_exists=check_case_exists,
            fast_check_case_exists=enhanced_fast_check,
            start=start or 1,
            max_exponent=getattr(self, 'max_exponent', Config.get_max_exponent()),
            rate_limiter=rl,
            scrape_case_data=scrape_case_data,
            max_cases=max_cases or 100000,
            format_case_number=lambda n: f"IMM-{n}-{year % 100:02d}",
        )

        # 将收集的案例添加到主列表中
        cases.extend(collected_cases)
        cases_collected = len(collected_cases)
        
        print(f"✓ 指数探测完成: 上边界={upper}, 探测次数={probes}")
        logger.info(f"\nExponential probing completed:")
        logger.info(f"  Approx upper numeric id: {upper}")
        logger.info(f"  Probes used: {probes}")
        logger.info(f"Probing completed: upper={upper}, probes={probes}")
        logger.info(f"=== 指数探测阶段结果 ===")
        logger.info(f"找到的上边界: {upper}")
        logger.info(f"使用的探测次数: {probes}")

        # Phase 2: Linear collection from start to upper to collect any remaining cases
        if upper > 0:
            print(f"开始线性收集阶段: 从 {start or 1} 到 {upper}")
            logger.info(f"Starting linear collection from {start or 1} to {upper}")
            logger.info("=== 线性收集阶段配置 ===")
            logger.info(f"start_num: {start or 1}")
            logger.info(f"upper: {upper}")
            logger.info(f"max_cases: {max_cases}")
            logger.info(f"force: {self.force}")
            logger.info(f"emergency_stop: {self.emergency_stop}")
            logger.info(f"batch_run_id: {batch_run_id}")
            logger.info(f"year: {year}")
            logger.info(f"cases_already_collected: {len(cases)}")
            logger.info(f"collected_case_ids: {[case.case_id for case in cases]}")

            start_num = start or 1
            if max_cases:
                try:
                    start_num_int = int(start_num)
                    end_limit = start_num_int + int(max_cases)
                    if upper > end_limit:
                        logger.info(f"Limiting linear scan upper bound to {end_limit} due to --max-cases={max_cases}")
                        upper = end_limit
                except Exception:
                    pass

            for case_num in range(start_num, upper + 1):
                if max_cases and len(cases) >= max_cases:
                    break

                if self.emergency_stop:
                    logger.warning("Emergency stop triggered - halting batch processing")
                    break

                case_number = f"IMM-{case_num}-{year % 100:02d}"
                processed += 1
                logger.info(f"Processing loop progress: case_num={case_num}/{upper}, processed={processed}, collected={len(cases)}")

                # Skip if already collected during probing
                if any(case.case_id == case_number for case in cases):
                    continue

                print(f"Processing case {case_num}/{upper}: {case_number}")
                logger.info(f"Processing case {case_num}/{upper}: {case_number}")

                # Check tracker skip rules
                try:
                    should_skip, reason = self.tracker.should_skip_case(case_number, force=self.force, run_id=batch_run_id)
                    if should_skip:
                        print(f"→ Skipping {case_number}: {reason}")
                        logger.info(f"Skipping {case_number}: {reason}")
                        # Add to skipped list with automatic truncation
                        skipped.append({"case_number": case_number, "status": "skipped", "reason": reason})
                        skipped_counter += 1
                        if len(skipped) > max_skipped_log:
                            skipped = skipped[-max_skipped_log:]  # Keep only the last N records
                            logger.debug(f"Skipped list truncated to {max_skipped_log} most recent records")
                        
                        # Report skipped statistics periodically
                        if skipped_counter - last_skipped_report >= skip_report_interval:
                            logger.info(f"Skip statistics: {skipped_counter} total cases skipped so far")
                            last_skipped_report = skipped_counter
                        integration.record_scrape_result(case_number, False, outcome='skipped', error_message=reason)
                        continue
                    if not self.force and self.exporter.case_exists(case_number):
                        print(f"→ Skipping {case_number}: already in database")
                        logger.info(f"Skipping {case_number}: exists_in_db")
                        # Add to skipped list with automatic truncation
                        skipped.append({"case_number": case_number, "status": "skipped", "reason": "exists_in_db"})
                        skipped_counter += 1
                        if len(skipped) > max_skipped_log:
                            skipped = skipped[-max_skipped_log:]  # Keep only the last N records
                            logger.debug(f"Skipped list truncated to {max_skipped_log} most recent records")
                        
                        # Report skipped statistics periodically
                        if skipped_counter - last_skipped_report >= skip_report_interval:
                            logger.info(f"Skip statistics: {skipped_counter} total cases skipped so far")
                            last_skipped_report = skipped_counter
                        integration.record_scrape_result(case_number, False, outcome='skipped', error_message="exists_in_db")
                        continue
                except Exception:
                    logger.debug(f"Existence check failed for {case_number}; attempting scrape")

                try:
                    case = self.scrape_single_case(case_number)
                    if case:
                        cases.append(case)
                        consecutive_failures = 0
                        try:
                            self.rate_limiter.reset_failures()
                        except Exception:
                            pass
                        print(f"✓ Successfully scraped case {case.case_id}")
                        logger.info(f"Successfully scraped case {case.case_id}")
                        integration.record_scrape_result(case_number, True, case_id=getattr(case, "case_id", None))
                        
                        # Memory management: trigger garbage collection at configured interval
                        if Config.get_enable_memory_management():
                            cleanup_interval = Config.get_memory_cleanup_interval()
                            if len(cases) % cleanup_interval == 0:
                                import gc
                                collected = gc.collect()
                                logger.debug(f"Garbage collection triggered after {len(cases)} cases: {collected} objects collected")
                    else:
                        consecutive_failures += 1
                        case_info = self.tracker.get_case_status(case_number)
                        if case_info and case_info.get('last_outcome') == 'no_data':
                            logger.info(f"Case {case_number} already marked as no_data, not treating as failure")
                            integration.record_scrape_result(case_number, False, outcome='no_data', error_message="Case not found")
                        else:
                            # Don't double-record failure - scrape_single_case already recorded it
                            logger.info(f"Case {case_number} already recorded as failed by scrape_single_case")
                            integration.record_scrape_result(case_number, False, outcome='failed', error_message="Scraping failed")
                        # Add progressive delay for consecutive failures in batch processing
                        if consecutive_failures > 2:
                            batch_delay = random.uniform(1.0, 3.0) + (consecutive_failures * 0.5)
                            time.sleep(batch_delay)
                        else:
                            time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Unhandled error scraping case {case_number}: {e}")
                    try:
                        # Check if failure was already recorded by scrape_single_case
                        case_info = self.tracker.get_case_status(case_number)
                        if case_info and case_info.get('last_outcome') in ['failed', 'error']:
                            logger.info(f"Case {case_number} failure already recorded by scrape_single_case")
                            integration.record_scrape_result(case_number, False, outcome='failed', error_message=str(e))
                        else:
                            integration.record_scrape_result(case_number, False, error_message=str(e))
                    except Exception:
                        pass
                    consecutive_failures += 1
                    # Add progressive delay for consecutive failures in batch processing
                    if consecutive_failures > 2:
                        batch_delay = random.uniform(2.0, 4.0) + (consecutive_failures * 0.8)
                        time.sleep(batch_delay)

                # Log final outcome for this case
                if any(case.case_id == case_number for case in cases):
                    logger.info(f"Case {case_number} outcome: collected_during_probing")
                elif case_number in [s['case_number'] for s in skipped]:
                    reason = next((s['reason'] for s in skipped if s['case_number'] == case_number), "unknown")
                    logger.info(f"Case {case_number} outcome: skipped - {reason}")
                elif 'case' in locals() and case:
                    logger.info(f"Case {case_number} outcome: scraped")
                else:
                    logger.info(f"Case {case_number} outcome: failed_or_no_data")

                # Progress update every 10 cases
                if processed % 10 == 0:
                    success_rate = len(cases) / processed * 100
                    print(f"Progress: {processed}/{upper} processed, {len(cases)} successful ({success_rate:.1f}%)")
                    logger.info(f"Progress: processed={processed}, upper={upper}, successful={len(cases)}, success_rate={success_rate:.1f}%")

                # Check if we should skip this year
                if self.discovery.should_skip_year(year, consecutive_failures):
                    logger.info(f"Skipping remaining cases for year {year} due to consecutive failures")
                    break

                # Stop if we reached the limit
                if max_cases and len(cases) >= max_cases:
                    break
        else:
            logger.warning("指数探测没有找到有效的上边界，跳过线性收集阶段")

        # Emit run-level metrics
        run_end_time = datetime.now(timezone.utc)
        try:
                run_duration = time.time() - run_start_ts
                emit_metric("batch.run.duration_seconds", run_duration)
                processed = processed if 'processed' in locals() else 0
                failures = processed - len(cases) if processed else 0
                failure_rate = (failures / processed) if processed else 0.0
                emit_metric("batch.run.failure_rate", float(failure_rate))
                logger.debug("=== 运行指标统计 ===")
                logger.debug(f"运行持续时间: {run_duration:.2f}秒")
                logger.debug(f"处理案例数: {processed}")
                logger.debug(f"失败案例数: {failures}")
                logger.debug(f"失败率: {failure_rate:.2f}%")
        except Exception:
            pass
        finally:
            try:
                self.tracker.finish_run(batch_run_id, 'completed')
                logger.info(f"Batch run {batch_run_id} completed successfully")
            except Exception as e:
                logger.error(f"Failed to finish batch run tracking: {e}")

        # Calculate actual processed count (includes both exponential probing and linear collection)
        # processed only tracks linear collection, so we need to estimate total processing
        # For simplicity, we'll use the maximum of processed and a reasonable estimate from probing
        processed_estimate = processed
        if processed_estimate == 0 and len(cases) > 0:
            # If processed is 0 but we have cases, they were collected during probing
            # Estimate based on probes and success rate
            processed_estimate = max(probes, len(cases))
        
        # Display post-run statistics
        post_run_stats = stats_service.calculate_run_statistics(
            year=year,
            start_time=run_start_time,
            end_time=run_end_time,
            upper_bound=upper,
            processed_count=processed_estimate,
            probes_used=probes,
            cases_collected=len(cases),
            run_id=batch_run_id
        )
        stats_service.log_and_display_statistics(post_run_stats, f"本次运行统计信息 (Run Statistics) - {year}")
        
        # Display final summary (concise)
        logger.info("=== 最终运行摘要 ===")
        logger.info(f"处理案例数: {processed_estimate} | 探测次数: {probes} | 收集案例数: {len(cases)}")
        if skipped_counter > 0:
            logger.info(f"跳过案例总数: {skipped_counter} (内存保留: {len(skipped)} 条)")
        if len(skipped) > 0:
            logger.debug(f"最近跳过的案例: {skipped[-10:]}")  # Show only last 10 for brevity

        # Optional: Generate batch summary export if cases were collected (database-only mode)
        case_count = len(cases)
        if case_count > 0:
            try:
                logger.info(f"Processing {case_count} collected cases for database save")
                # Only save to database, avoid duplicate JSON export
                # Cases are already saved individually during scraping
                saved_count = 0
                failed_count = 0
                
                for case in cases:
                    try:
                        # Check if case already exists in database to avoid duplicate saves
                        if not self.exporter.case_exists(case.case_number):
                            status, msg = self.exporter.save_case_to_database(case)
                            if status == "success":
                                saved_count += 1
                            else:
                                failed_count += 1
                                logger.warning(f"Failed to save {case.case_number}: {msg}")
                        else:
                            logger.debug(f"Case {case.case_number} already exists in database, skipping")
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"Error saving case {case.case_number}: {e}")
                
                logger.info(f"Batch database save completed: {saved_count} new cases saved, {failed_count} failed")
                
                # Generate a minimal batch report (not full data export)
                batch_report = {
                    "year": year,
                    "processed_cases": case_count,
                    "new_cases_saved": saved_count,
                    "failed_saves": failed_count,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "run_id": batch_run_id
                }
                
                report_filename = f"batch_report_{year}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
                report_path = os.path.join(self.exporter.output_dir, report_filename)
                
                with open(report_path, 'w', encoding='utf-8') as f:
                    json.dump(batch_report, f, indent=2, ensure_ascii=False)
                
                logger.info(f"Batch report saved to: {report_path}")
                
            except Exception as e:
                logger.warning(f"Failed to process batch database save: {e}")

        # Memory cleanup after batch completion (if enabled)
        if Config.get_enable_memory_management():
            logger.info("Performing memory cleanup after batch completion")
            try:
                import gc
                
                # Force garbage collection
                collected = gc.collect()
                logger.info(f"Garbage collection completed: {collected} objects collected")
                
                # Try to report memory usage if psutil is available
                try:
                    import psutil
                    process = psutil.Process(os.getpid())
                    memory_info = process.memory_info()
                    memory_mb = memory_info.rss / 1024 / 1024
                    logger.info(f"Memory usage after cleanup: {memory_mb:.2f} MB")
                except ImportError:
                    logger.debug("psutil not available, skipping memory usage reporting")
                
                # Clear large objects from memory
                try:
                    # Clear the cases list to free memory (since they're already saved)
                    logger.info(f"Clearing {case_count} case objects from memory")
                    cases.clear()
                except Exception as e:
                    logger.warning(f"Failed to clear cases list: {e}")
            except Exception as e:
                logger.warning(f"Memory cleanup failed: {e}")
        else:
            logger.info("Memory management is disabled")

        # Return scraped cases and skipped info for auditing
        skipped_info = {
            "total_skipped": skipped_counter,
            "recent_skipped": skipped,
            "max_stored": max_skipped_log
        }
        return [], skipped_info  # Return empty list since cases were cleared from memory

    def show_stats(self, year: Optional[int] = None) -> None:
        """
        Show scraping statistics.

        Args:
            year: Optional year to show stats for
        """
        if year:
            stats = self.discovery.get_processing_stats(year)
            print(f"\nStatistics for year {year}:")
            print(f"  Total cases: {stats['total_cases']}")
            print(f"  Last scraped: {stats['last_scraped'] or 'Never'}")
            logger.info(f"Statistics for year {year}: total_cases={stats['total_cases']}, last_scraped={stats['last_scraped']}")
        else:
            total_cases = self.exporter.get_case_count_from_database()
            print(f"\nTotal cases in database: {total_cases}")
            logger.info(f"Total cases in database: {total_cases}")

    def run(self) -> None:
        """Run the CLI application."""
        parser = argparse.ArgumentParser(
            description="Federal Court Case Scraper",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples (expanded):
  # Scrape a single case (force re-scrape)
  python -m src.cli.main single IMM-12345-25 --force

  # Batch: start from numeric id 30 and scrape up to 10 cases
  python -m src.cli.main batch 2025 --start 30 --max-cases 10

  # Batch with tuned rate and backoff (faster but polite)
  python -m src.cli.main batch 2025 --max-cases 100 --rate-interval 0.5 --backoff-factor 1.5

  # Batch with custom max exponent for exponential probing
  python -m src.cli.main batch 2025 --max-cases 50 --max-exponent 15

  # Purge dry-run (audit only)
  python -m src.cli.main purge 2024 --dry-run

    # Purge actual run (destructive)
    python -m src.cli.main purge 2024 --yes

Notes:
  - Use `--dry-run` to validate purge actions before running destructive operations.
  - Batch mode uses exponential probing to efficiently find the upper bound of case numbers.
""",
        )

        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Single case command
        single_parser = subparsers.add_parser(
            "single",
            help="Scrape a single case",
            description=(
                "Scrape a single Federal Court case by case number (e.g., IMM-12345-25). "
                "This command initializes the scraper lazily and will export/save the result. "
                "Use --force to re-scrape even if the case exists in the database."
            ),
        )
        single_parser.add_argument(
            "case_number", help="Case number (e.g., IMM-12345-25)"
        )
        # Allow --force after the 'single' subcommand as well
        single_parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-scraping of this case even if it exists in the database",
        )

        # Global force flag
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-scraping of cases even if they exist in the database",
        )

        # Optional tracker backfill flags
        # No user-facing flag for tracker backfill — we backfill snapshots unconditionally

        # Rate limiter / backoff tuning (global)
        parser.add_argument(
            "--rate-interval",
            type=float,
            default=Config.get_rate_limit_seconds(),
            help="Fixed interval in seconds between requests (default: %(default)s)",
        )
        parser.add_argument(
            "--backoff-factor",
            type=float,
            default=Config.get_backoff_factor(),
            help="Exponential backoff base multiplier for failures (default: %(default)s)",
        )
        parser.add_argument(
            "--max-backoff-seconds",
            type=float,
            default=Config.get_max_backoff_seconds(),
            help="Maximum backoff delay in seconds (default: %(default)s)",
        )

        # Batch command
        batch_parser = subparsers.add_parser(
            "batch",
            help="Scrape multiple cases for a year",
            description=(
                "Batch-scrape multiple cases for a given year. The discovery service will "
                "generate case numbers; use --start and --max-cases to bound the run. "
                "Defaults are read from configuration where applicable."
            ),
        )
        batch_parser.add_argument("year", type=int, help="Year to scrape cases for")
        batch_parser.add_argument(
            "--max-cases", type=int, help="Maximum number of cases to scrape"
        )
        batch_parser.add_argument(
            "--start",
            type=int,
            default=1,
            help="Start numeric id (default: %(default)s). Example: --start 30 starts at IMM-30-<yy>",
        )
        batch_parser.add_argument(
            "--safe-stop-no-records",
            type=int,
            default=Config.get_safe_stop_no_records(),
            help="Number of consecutive no-records to stop probing/collection (default: %(default)s)",
        )
        batch_parser.add_argument(
            "--max-exponent",
            type=int,
            default=Config.get_max_exponent(),
            help="Maximum exponent for exponential probing (2^i steps, default: %(default)s)",
        )
        # Accept --force after the 'batch' subcommand as well
        batch_parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-scraping of cases even if they exist in the database",
        )

        # Stats command
        stats_parser = subparsers.add_parser(
            "stats",
            help="Show scraping statistics",
            description=(
                "Show scraping statistics. If --year is provided, show stats for that year; otherwise show overall counts."
            ),
        )
        stats_parser.add_argument(
            "--year",
            type=int,
            help="Year to show stats for (shows total if not specified)",
        )

        # Purge command
        purge_parser = subparsers.add_parser(
            "purge",
            help="Purge data for a given year (destructive)",
            description=(
                "Purge data for a given year. This is a destructive operation that deletes files and/or DB records. "
                "Use --dry-run to perform an audit-only run. If performing a real purge, pass --yes."
            ),
        )
        purge_parser.add_argument("year", type=int, help="Year to purge")
        purge_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List items that would be deleted without performing deletion",
        )
        purge_parser.add_argument(
            "--yes",
            action="store_true",
            default=True,
            help="Non-interactive confirmation to proceed with purge",
        )
        # NOTE: backup option removed by operator request; default behavior is to NOT perform backups.
        purge_parser.add_argument(
            "--no-backup",
            action="store_true",
            default=True,
            help="Skip backup creation (default true)",
        )
        purge_parser.add_argument(
            "--files-only",
            action="store_true",
            help="Only operate on filesystem artifacts, not DB",
        )
        # `--db-only` removed by operator request (we focus on file + tracking purges)
        purge_parser.add_argument(
            "--sql-year-filter",
            choices=("auto", "on", "off"),
            default="auto",
            help=(
                "Control SQL-year-filter behavior: 'auto' try SQL then fallback, 'on' force SQL, 'off' force Python filter (default: %(default)s)"
            ),
        )
        purge_parser.add_argument(
            "--force-files",
            action="store_true",
            default=True,
            help="If DB purge fails, proceed with filesystem purge; default is TRUE",
        )

        args = parser.parse_args()

        # Log program startup details so operators can see invocation and inputs
        try:
            logger.info(f"Program invocation: {' '.join(sys.argv)}")
            try:
                logger.info(f"Parsed args: {vars(args)}")
            except Exception:
                logger.info("Parsed args: <unserializable>")

                try:
                    logger.info(
                        f"Config: rate_interval={getattr(args, 'rate_interval', Config.get_rate_limit_seconds())} backoff_factor={getattr(args, 'backoff_factor', Config.get_backoff_factor())} max_backoff_seconds={getattr(args, 'max_backoff_seconds', Config.get_max_backoff_seconds())} enable_run_logger={Config.get_enable_run_logger()} write_audit={Config.get_write_audit()}"
                    )
                except Exception:
                    # best-effort logging; do not fail startup if config access errors
                    pass
            # Log a small, masked snapshot of environment and process info for diagnostics
            try:
                import os
                from datetime import datetime as _dt, timezone as _tz

                def _mask(val: str) -> str:
                    if val is None:
                        return ""
                    s = str(val)
                    if len(s) > 128:
                        s = s[:128] + "..."
                    return s

                sensitive_keys = ("KEY", "SECRET", "PASSWORD", "TOKEN", "AWS", "GITHUB", "SSH")

                env_snapshot = {}
                for k, v in os.environ.items():
                    if any(sk in k.upper() for sk in sensitive_keys):
                        env_snapshot[k] = "<redacted>"
                    else:
                        env_snapshot[k] = _mask(v)

                proc_info = {
                    "pid": os.getpid(),
                    "uid": getattr(os, "getuid", lambda: None)(),
                    "cwd": os.getcwd(),
                    "python": _mask(sys.executable),
                    "started_at": _dt.now(_tz.utc).isoformat(),
                }

                # Log concise summaries (not flooding logs with full env unless needed).
                logger.info(f"Process info: pid={proc_info['pid']} uid={proc_info['uid']} cwd={proc_info['cwd']} python={proc_info['python']} started_at={proc_info['started_at']}")
                # Log a short subset of environment vars (keys only) to help debugging
                try:
                    keys_list = ",".join(list(env_snapshot.keys())[:30])
                    logger.info(f"Env keys (first 30): {keys_list}")
                except Exception:
                    logger.debug("Failed to log environment keys summary")
            except Exception:
                pass

            # Friendly Initialization Config summary (ordered, masked where needed)
            try:
                def _mask_short(val) -> str:
                    if val is None:
                        return ""
                    s = str(val)
                    if len(s) > 64:
                        return s[:61] + "..."
                    return s

                db_cfg = Config.get_db_config()
                db_cfg_masked = dict(db_cfg)
                if "password" in db_cfg_masked and db_cfg_masked["password"]:
                    db_cfg_masked["password"] = "<redacted>"

                init_items = [
                    ("rate_limit_seconds", _mask_short(getattr(args, "rate_interval", Config.get_rate_limit_seconds()))),
                    ("backoff_factor", _mask_short(getattr(args, "backoff_factor", Config.get_backoff_factor()))),
                    ("max_backoff_seconds", _mask_short(getattr(args, "max_backoff_seconds", Config.get_max_backoff_seconds()))),
                    ("max_retries", _mask_short(Config.get_max_retries())),
                    ("timeout_seconds", _mask_short(Config.get_timeout_seconds())),
                    ("output_dir", _mask_short(Config.get_output_dir())),
                    ("per_case_subdir", _mask_short(Config.get_per_case_subdir())),
                    ("export_json_only", _mask_short(Config.get_export_json_only())),
                    ("headless", _mask_short(Config.get_headless())),
                    ("browser", _mask_short(Config.get_browser())),
                    ("log_level", _mask_short(Config.get_log_level())),
                    ("log_file", _mask_short(Config.get_log_file())),
                    ("enable_run_logger", _mask_short(Config.get_enable_run_logger())),
                    ("write_audit", _mask_short(Config.get_write_audit())),
                    ("db_host", _mask_short(db_cfg_masked.get("host"))),
                    ("db_port", _mask_short(db_cfg_masked.get("port"))),
                    ("db_name", _mask_short(db_cfg_masked.get("database"))),
                    ("db_user", _mask_short(db_cfg_masked.get("user"))),
                    ("db_password", _mask_short(db_cfg_masked.get("password"))),
                ]

                # Emit a compact, readable block
                logger.info("Initialization config:")
                for k, v in init_items:
                    logger.info(f"  - {k}: {v}")
            except Exception:
                logger.debug("Failed to produce initialization config summary")
        except Exception:
            # swallowing any logging errors to avoid interfering with CLI behavior
            pass

        # Set force flag on CLI object
        if getattr(args, "force", False):
            self.force = True

        # Reconfigure the shared rate limiter with CLI-provided tuning values
        try:
            self.rate_limiter = EthicalRateLimiter(
                interval_seconds=getattr(args, "rate_interval", Config.get_rate_limit_seconds()),
                backoff_factor=getattr(args, "backoff_factor", Config.get_backoff_factor()),
                max_backoff_seconds=getattr(args, "max_backoff_seconds", Config.get_max_backoff_seconds()),
            )
        except Exception:
            # best-effort: retain existing limiter if reconfiguration fails
            pass

        if not args.command:
            parser.print_help()
            return

        try:
            if args.command == "single":
                # If not forcing, skip if case already exists in DB (avoid duplicate scraping)
                try:
                    if not self.force and self.exporter.case_exists(args.case_number):
                        print(f"→ Skipping {args.case_number}: already in database")
                        return
                except Exception:
                    # If existence check failed, proceed with scrape (best-effort)
                    logger.debug(f"Existence check failed for {args.case_number}; proceeding to scrape")

                case = self.scrape_single_case(args.case_number)
                if case:
                    # Export the case and save to DB
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    base_filename = f"federal_court_cases_{timestamp}"
                    export_result = self.exporter.export_and_save([case], base_filename)
                    print(f"\nCase scraped and exported:")
                    print(f"  JSON: {export_result.get('json')}")
                    if export_result.get("database"):
                        print(f"  Database: {export_result['database']}")
                else:
                    print(f"\nCase {args.case_number} not found or failed to scrape")
                    if self.emergency_stop:
                        print(
                            "Emergency stop was triggered due to consecutive failures"
                        )
                    sys.exit(1)

            elif args.command == "batch":
                if self.emergency_stop:
                    print("Cannot start batch processing - emergency stop is active")
                    sys.exit(1)

                scraped_cases, skipped_info = self.scrape_batch_cases(
                    args.year,
                    args.max_cases,
                    start=getattr(args, "start", None),
                    max_exponent=getattr(args, "max_exponent", None),
                )
                
                # Extract skip data for compatibility
                if isinstance(skipped_info, dict):
                    total_skipped = skipped_info.get("total_skipped", 0)
                    recent_skipped = skipped_info.get("recent_skipped", [])
                else:
                    # Backward compatibility for old format
                    total_skipped = len(skipped_info) if skipped_info else 0
                    recent_skipped = skipped_info if skipped_info else []
                
                if scraped_cases or total_skipped > 0:
                    # Export scraped cases and save to DB (only if there are scraped cases)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    base_filename = f"federal_court_cases_{timestamp}"
                    if scraped_cases:
                        export_result = self.exporter.export_and_save(
                            scraped_cases, base_filename
                        )
                    else:
                        export_result = {"json": None, "database": None}

                    # Build audit report
                    audit = {
                        "timestamp": timestamp,
                        "year": args.year,
                        "scraped_count": len(scraped_cases),
                        "skipped_count": total_skipped,
                        "skipped_summary": {
                            "total": total_skipped,
                            "recent_count": len(recent_skipped),
                            "max_stored": skipped_info.get("max_stored", 100) if isinstance(skipped_info, dict) else 100,
                            "recent_items": recent_skipped
                        },
                        "export": export_result,
                    }

                    # Write audit file to output/ (configurable)
                    if Config.get_write_audit():
                        import json
                        from pathlib import Path

                        out_dir = Path("output")
                        out_dir.mkdir(parents=True, exist_ok=True)
                        audit_path = out_dir / f"audit_{timestamp}.json"
                        with audit_path.open("w", encoding="utf-8") as fh:
                            json.dump(audit, fh, indent=2)
                    else:
                        audit_path = None

                    print(f"\nBatch scrape complete:")
                    print(f"  Cases scraped: {len(scraped_cases)}")
                    print(f"  Cases skipped: {total_skipped}")
                    print(f"  JSON: {export_result.get('json')}")
                    print(f"  Audit: {audit_path}")
                    if export_result.get("database"):
                        print(f"  Database: {export_result['database']}")
                    # Mirror the console output into structured info logs for operators
                    logger.info(
                        f"Batch scrape complete: year={args.year}, cases_scraped={len(scraped_cases)}, cases_skipped={total_skipped}, json={export_result.get('json')}, audit={audit_path}, database={export_result.get('database')}"
                    )
                else:
                    print(f"\nNo cases processed for year {args.year}")
                    logger.info(f"No cases processed for year {args.year}")
                    if self.emergency_stop:
                        print("Emergency stop was triggered during processing")
                        sys.exit(1)

            elif args.command == "stats":
                self.show_stats(args.year)
            elif args.command == "purge":
                # Purge flow: do dry-run first or ask for confirmation
                year = args.year
                dry_run = getattr(args, "dry_run", False)
                # default to not backing up (backup option removed)
                no_backup = getattr(args, "no_backup", True)
                backup = None
                files_only = getattr(args, "files_only", False)
                # db-only option removed; default to regular behavior
                db_only = False

                if not dry_run and not args.yes:
                    # Interactive confirmation required
                    resp = input(
                        f"This will permanently delete data for year {year}. Type 'YES' to continue: "
                    )
                    if resp.strip() != "YES":
                        print("Purge cancelled")
                        return

                # Original purge for files and main case data
                result = purge_year(
                    year,
                    dry_run=dry_run,
                    no_backup=no_backup,
                    files_only=files_only,
                    sql_year_filter=(None if args.sql_year_filter == "auto" else (True if args.sql_year_filter == "on" else False)),
                    force_files=getattr(args, "force_files", True),
                )
                
                # Additional purge for tracking data (if not files_only)
                # TODO: Implement purge_year method in CaseTrackingService
                # if not files_only:
                #     if not dry_run:
                #         logger.info(f"Purging tracking data for year {year}")
                #         tracking_stats = self.tracker.purge_year(year)
                #         logger.info(f"Tracking purge completed: {tracking_stats}")
                #         logger.info(f"Tracking data purged: {tracking_stats.get('cases_deleted', 0)} cases, "
                #                 f"{tracking_stats.get('docket_entries_deleted', 0)} docket entries, "
                #                 f"{tracking_stats.get('history_deleted', 0)} history records, "
                #                 f"{tracking_stats.get('snapshots_deleted', 0)} snapshots, "
                #                 f"{tracking_stats.get('runs_deleted', 0)} runs")
                #     else:
                #         logger.info(f"[DRY RUN] Would purge tracking data for year {year}")
                #         print("[DRY RUN] Would purge tracking data for year {year}")
                
                # Enhanced logging for purge results
                audit_path = result.get("audit_path")
                logger.info(f"Purge summary written to: {audit_path}")
                
                # Log detailed results
                if dry_run:
                    logger.info("[DRY RUN] Purge simulation completed - no data was actually deleted")
                else:
                    logger.info("Purge operation completed successfully")
                
                # Log file deletion results
                files_removed = result.get("files_removed", {})
                if files_removed:
                    output_info = files_removed.get("output", {})
                    modal_info = files_removed.get("modal_html", {})
                    logger.info(f"Files deleted: {output_info.get('removed_files', 0)} files, "
                               f"{output_info.get('removed_dirs', 0)} directories, "
                               f"{modal_info.get('removed_files', 0)} modal HTML files")
                
                # Log database deletion results
                db_result = result.get("db", {})
                if isinstance(db_result, dict):
                    if "deleted_rows" in db_result:
                        logger.info(f"Database rows deleted: {db_result['deleted_rows']}")
                    elif "cases_selected_count" in db_result:
                        if dry_run:
                            logger.info(f"[DRY RUN] Database rows that would be deleted: {db_result['cases_selected_count']}")
                        else:
                            logger.info(f"Database rows selected for deletion: {db_result['cases_selected_count']}")
                    elif "error" in db_result:
                        logger.error(f"Database purge error: {db_result['error']}")
                
                # Log any errors
                notes = result.get("notes", [])
                if notes:
                    for note in notes:
                        logger.info(f"Purge note: {note}")
                
                # Print summary to console as well
                print(f"\n=== Purge {'DRY RUN - ' if dry_run else ''}Summary ===")
                print(f"Audit file: {audit_path}")
                if files_removed:
                    output_info = files_removed.get("output", {})
                    modal_info = files_removed.get("modal_html", {})
                    print(f"Files deleted: {output_info.get('removed_files', 0)} files, {output_info.get('removed_dirs', 0)} dirs, {modal_info.get('removed_files', 0)} modal files")
                if isinstance(db_result, dict) and "deleted_rows" in db_result:
                    print(f"Database rows deleted: {db_result['deleted_rows']}")
                elif isinstance(db_result, dict) and "cases_selected_count" in db_result:
                    action = "would be deleted" if dry_run else "selected for deletion"
                    print(f"Database rows {action}: {db_result['cases_selected_count']}")
                print("=" * 40)

        except KeyboardInterrupt:
            logger.info("Operation cancelled by user")
            print("\nOperation cancelled")
            sys.exit(1)
        except Exception as e:
            logger.error(f"CLI error: {e}")
            print(f"Error: {e}")
            sys.exit(1)
        finally:
            # Ensure resources are cleaned up (close shared WebDriver)
            try:
                self.shutdown()
            except Exception:
                pass


def main():
    """Main entry point."""
    cli = FederalCourtScraperCLI()
    cli.run()


if __name__ == "__main__":
    main()
