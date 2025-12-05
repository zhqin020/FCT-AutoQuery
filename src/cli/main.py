"""Command-line interface for Federal Court Case Scraper."""

import argparse
import sys
import time
import random
from datetime import datetime, timezone
from typing import Optional

from src.lib.config import Config
from src.lib.logging_config import get_logger, setup_logging
from src.models.case import Case
from src.services.case_scraper_service import CaseScraperService
from src.services.export_service import ExportService
from src.services.url_discovery_service import UrlDiscoveryService
from src.services.batch_service import BatchService
from src.services.case_tracking_service import CaseTrackingService
from src.cli.tracking_integration import TrackingIntegration, create_tracking_integrated_check_exists, create_tracking_integrated_scrape_case
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
            try:
                if not getattr(self.scraper, "_initialized", False):
                    self.scraper.initialize_page()
                else:
                    logger.info("Reusing initialized page; skipping initialize_page()")
            except Exception as e:
                logger.error(f"Failed to initialize page for scraping: {e}")
                raise

            # Search for the case
            found = self.scraper.search_case(case_number)
            if not found:
                logger.warning(f"Case {case_number} not found")
                # record transient failure and backoff
                try:
                    delay = self.rate_limiter.record_failure()
                    time.sleep(delay)
                except Exception:
                    # best-effort small sleep
                    time.sleep(0.1)
                self.consecutive_failures += 1
                
                # Record not found to tracking system (use canonical NO_DATA)
                try:
                    self.tracker.record_case_processing(
                        case_number=case_number,
                        run_id=self.current_run_id,
                        outcome="no_data",
                        error_message="Case not found",
                        processing_mode="single"
                    )
                except Exception as e:
                    logger.warning(f"Failed to record tracking data for {case_number}: {e}")
                
                # 标记为 no_data（只有在页面检测到'No data available in table'时才设置）
                try:
                    from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
                    simplified_tracker = SimplifiedTrackingService()
                    simplified_tracker.mark_case_attempt(case_number, CaseStatus.NO_DATA)
                except Exception as e:
                    logger.warning(f"Failed to mark case no_data for {case_number}: {e}")
                
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
                    case = self.scraper.scrape_case_data(case_number)
                except Exception as e:
                    logger.error(
                        f"Exception during scrape_case_data attempt {attempt} for {case_number}: {e}",
                        exc_info=True,
                    )
                    case = None

                if case:
                    logger.info(f"Successfully scraped case: {case.case_id} (attempt {attempt})")
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
                    time.sleep(delay)
                except Exception:
                    time.sleep(0.1)
                if attempt < max_scrape_attempts:
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
                        run_id=self.current_run_id,
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
                    time.sleep(delay)
                except Exception:
                    time.sleep(0.1)
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
                        run_id=self.current_run_id,
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
            return None
        finally:
            # Do not close the full WebDriver here to enable session reuse
            # across batch operations. Individual modal/page cleanup is
            # performed inside CaseScraperService methods.

            # Check for emergency stop
            if self.consecutive_failures >= self.max_consecutive_failures:
                logger.error(
                    f"Emergency stop triggered after {self.consecutive_failures} consecutive failures"
                )
                self.emergency_stop = True

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
                    case = self.scraper.scrape_case_data(case_number)
                except Exception as e:
                    logger.error(
                        f"Exception during scrape_case_data attempt {attempt} for {case_number}: {e}",
                        exc_info=True,
                    )
                    case = None

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
                    time.sleep(delay)
                except Exception:
                    time.sleep(0.1)
                if attempt < max_scrape_attempts:
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
                        run_id=self.current_run_id,
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
        self, year: int, max_cases: Optional[int] = None, start: Optional[int] = None
    ) -> tuple[list, list]:
        """
        Scrape multiple cases for a given year using exponential probing to find upper bound first.

        Args:
            year: Year to scrape cases for
            max_cases: Maximum number of cases to scrape
            start: Starting number for probing

        Returns:
            List of scraped Case objects
        """
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
            self.scraper = CaseScraperService(headless=self._scraper_headless)

        # Initialize page only if not already initialized (reuse session across batch)
        try:
            if not getattr(self.scraper, "_initialized", False):
                self.scraper.initialize_page()
            else:
                logger.info("Reusing initialized page; skipping initialize_page()")
        except Exception as e:
            logger.error(f"Failed to initialize page for scraping: {e}")
            raise
        
        cases = []
        consecutive_failures = 0
        processed = 0
        skipped = []

        # Start batch run tracking
        batch_run_id = self.tracker.start_run(
            processing_mode="batch_collect",
            parameters={
                "year": year,
                "max_cases": max_cases,
                "start": start
            }
        )

        # Backfill tracking snapshots is no longer needed in the simplified design
        # The system now uses only the cases table without additional snapshot tracking

        # Use the CLI-configured/shared rate limiter for probing/backoff
        rl = getattr(self, "rate_limiter", None) or EthicalRateLimiter(
            interval_seconds=Config.get_rate_limit_seconds(),
            backoff_factor=Config.get_backoff_factor(),
            max_backoff_seconds=Config.get_max_backoff_seconds(),
        )

        # Track cases that were found during probing to avoid duplicate searches
        found_cases = set()
        # Track cases that were confirmed as no_data during this run to avoid re-probing
        no_data_cases = set()
        # Preload recent known no-results from tracking DB to avoid re-probing across runs.
        try:
            recent_no_results = self.tracker.get_cases_with_last_outcome('no_data', year)
            for cn in recent_no_results:
                try:
                    from src.lib.case_utils import canonicalize_case_number
                    cn = canonicalize_case_number(cn)
                except Exception:
                    pass
                no_data_cases.add(cn)
            if recent_no_results:
                logger.info(f"Preloaded {len(recent_no_results)} known no_data cases from tracker for year {year}")
                # Log the specific cases only when the preloaded set is reasonably small
                if len(recent_no_results) <= 20:
                    logger.debug(f"Preloaded no_data cases: {sorted(list(no_data_cases))}")
        except Exception as e:
                logger.debug(f"Failed to preload no_data cases: {e}")

        # Create tracking integration instance for this batch
        integration = TrackingIntegration(self.tracker, batch_run_id)

        # Define check_case_exists function for probing with tracking
        def check_case_exists(case_num: int) -> bool:
            case_number = f"IMM-{case_num}-{year % 100:02d}"
            try:
                # Canonicalize for comparisons with preloaded sets and DB values
                try:
                    from src.lib.case_utils import canonicalize_case_number
                    case_number_cmp = canonicalize_case_number(case_number)
                except Exception:
                    case_number_cmp = case_number
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
                        # When the tracker recommends skipping a case, record it as a
                        # 'skipped' outcome; if the reason is 'exists_in_db' prefer
                        # using the stored DB case value to ensure snapshot joins match.
                        stored_no = None
                        if reason and 'exists_in_db' in reason:
                            stored_no = self.tracker.get_stored_case_case_number(case_number) or case_number
                        self.tracker.record_case_processing(
                            case_number=stored_no or case_number,
                            run_id=batch_run_id,
                            outcome="skipped",
                            reason=reason,
                            processing_mode="batch_probe",
                        )
                    except Exception:
                        pass
                    # If the skip reason is 'exists_in_db' we do NOT mark it found
                    # because found_cases should only contain cases found via web search
                    if "exists_in_db" in reason:
                        return False  # Return False to prevent collection
                    return False

                # Next check if the case already exists in database (unless forcing)
                if not self.force and self.exporter.case_exists(case_number):
                    logger.info(f"Case {case_number} already exists in database, skipping web search")
                    # Do NOT add to found_cases - this should only contain cases found via web search
                    
                    # Record skip to tracking system
                    stored_no = self.tracker.get_stored_case_case_number(case_number) or case_number
                    self.tracker.record_case_processing(
                        case_number=case_number,
                        db_case_number=stored_no,
                        run_id=batch_run_id,
                        outcome="skipped",
                        reason="exists_in_db",
                        processing_mode="batch_probe"
                    )
                    return True
                
                # If not in DB or forcing, do web search
                # If the case was confirmed no-results earlier in this run, skip additional web searches
                if case_number_cmp in no_data_cases:
                    logger.info(f"Skipping repeated probe for {case_number}: already confirmed no_data in this run")
                    return False
                # Apply a randomized, human-like delay before performing web searches
                try:
                    delay_min = Config.get_probe_delay_min()
                    delay_max = Config.get_probe_delay_max()
                    if delay_max > 0:
                        time.sleep(random.uniform(delay_min, delay_max))
                except Exception:
                    pass
                result = self.scraper.search_case(case_number)
                if result:
                    found_cases.add(case_number)
                    
                    # Record successful probe via integration helper
                    integration.record_probe_result(case_number, True)
                else:
                    # Record no results via integration helper
                    integration.record_probe_result(case_number, False)
                    no_data_cases.add(case_number_cmp)
                
                return result
            except Exception as e:
                logger.warning(f"search_case failed for {case_number}: {e}")
                try:
                    integration.record_probe_result(case_number, False, error_message=str(e))
                    # If a rate limiter is provided, inform it of a failure and back off
                    try:
                        if getattr(self, 'rate_limiter', None):
                            delay = self.rate_limiter.record_failure()
                            time.sleep(delay)
                    except Exception:
                        pass
                except Exception:
                    pass
                
                return False

        # Define scrape_case_data function for collection during probing with tracking
        def scrape_case_data(case_num: int) -> Optional[object]:
            case_number = f"IMM-{case_num}-{year % 100:02d}"
            try:
                try:
                    from src.lib.case_utils import canonicalize_case_number
                    case_number_cmp = canonicalize_case_number(case_number)
                except Exception:
                    case_number_cmp = case_number
                # 使用简化的跟踪服务检查是否应该跳过
                should_skip, reason = tracking_service.should_skip_case(case_number, force=self.force)
                if should_skip:
                    logger.info(f"Skipping scrape for {case_number} due to tracking: {reason}")
                    try:
                        # Record as skipped rather than error when skip is intentional
                        integration.record_scrape_result(case_number, False, outcome='skipped', error_message=reason)
                    except Exception:
                        pass
                    return None
                
                # If we already found this case during probing via web search, skip the search and go directly to scraping
                if case_number in found_cases:
                    logger.info(f"Case {case_number} found during probing, proceeding directly to scrape")
                    # Reuse the existing scraper state and go directly to data scraping
                    case = self._scrape_case_data_without_search(case_number)
                elif case_number_cmp in no_data_cases:
                    logger.info(f"Skipping scrape for {case_number} because it was confirmed no_data earlier in this run")
                    return None
                else:
                    case = self.scrape_single_case(case_number)
                
                if case:
                    cases.append(case)
                    
                    # Record successful collection via integration helper
                    integration.record_scrape_result(case_number, True, case_id=getattr(case, "case_id", None))
                    # 标记为成功采集
                    tracking_service.mark_case_attempt(case_number, CaseStatus.SUCCESS)
                    return case
                else:
                    # Check if case was already marked as no_data before treating as failed
                    case_info = tracking_service.get_case_info(case_number)
                    if case_info and case_info.get('status') == CaseStatus.NO_DATA:
                        logger.info(f"Case {case_number} already marked as no_data, not treating as failure")
                        # Record no_data outcome via integration helper to maintain consistency
                        integration.record_scrape_result(case_number, False, outcome='no_data', error_message="Case not found")
                        return None
                    else:
                        # Record failed collection via integration helper
                        integration.record_scrape_result(case_number, False, error_message="Scraping failed")
                        # 标记为失败
                        tracking_service.mark_case_attempt(case_number, CaseStatus.FAILED, "Scraping failed")
            except Exception as e:
                # Log full exception stacktrace to help debug underlying causes
                logger.exception(f"Error scraping case {case_number}: {e}")
                
                # Record error to simplified tracking system
                tracking_service.mark_case_attempt(case_number, CaseStatus.FAILED, str(e))
            
            return None

        # Use exponential probing to find upper bound while collecting data
        logger.info("Starting exponential probing to find upper bound")
        # Enforce upper limit when both start and max_cases are specified
        upper_limit_param = getattr(self, 'max_limit', 100000)
        if start and max_cases:
            try:
                start_num_local = int(start)
                max_cases_local = int(max_cases)
                upper_limit_param = min(upper_limit_param, start_num_local + max_cases_local - 1)
            except Exception:
                pass

        # 导入简化的跟踪服务
        from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
        tracking_service = SimplifiedTrackingService()
        
        # Enhanced fast check that returns detailed status information
        def enhanced_fast_check(n: int):
            """Fast DB check that returns a standardized dict including status and skip_reason.

            This prefers the authoritative `self.tracker` (CaseTrackingService) to ensure
            canonical outcomes (e.g., 'no_data') are respected and to avoid confusing
            retry_count based reasons when the status is 'no_data'.
            """
            if self.force:
                return False

            case_number = f"IMM-{n}-{year % 100:02d}"
            # Use the main CaseTrackingService as the single source of truth
            try:
                should_skip, skip_reason = self.tracker.should_skip_case(case_number, force=self.force, run_id=batch_run_id)
            except Exception:
                try:
                    should_skip, skip_reason = self.tracker.should_skip_case(case_number, force=self.force)
                except Exception:
                    should_skip, skip_reason = (False, '')

            # Query latest status metadata from the DB in a single place
            try:
                status_info = self.tracker.get_case_status(case_number) or {}
                last_outcome = status_info.get('last_outcome', 'unknown')
            except Exception:
                last_outcome = 'unknown'

            return {
                'exists': not should_skip,
                'status': last_outcome,
                'skip_reason': skip_reason,
                'should_skip': should_skip
            }
        
        upper, probes = BatchService.find_upper_bound(
            check_case_exists=check_case_exists,
            fast_check_case_exists=enhanced_fast_check,
            start=start or 1,
            initial_high=getattr(self, 'initial_high', 1000),
            max_limit=upper_limit_param,
            coarse_step=getattr(self, 'coarse_step', 100),
            refine_range=getattr(self, 'refine_range', 200),
            probe_budget=getattr(self, 'probe_budget', Config.get_probe_budget()),
            max_probes=10000,
            rate_limiter=rl,
            collect=True,  # Enable collection during probing
            scrape_case_data=scrape_case_data,
            max_cases=max_cases or 100000,
            format_case_number=lambda n: f"IMM-{n}-{year % 100:02d}",
        )

        logger.info(f"\nProbing completed:")
        logger.info(f"  Approx upper numeric id: {upper}")
        logger.info(f"  Probes used: {probes}")
        logger.info(f"  Cases collected during probing: {len(cases)}")
        # Also log the same information so it is present in file logs
        logger.info(f"Probing completed: upper={upper}, probes={probes}, cases_collected={len(cases)}")

        # Now do linear scan from start to upper to collect any remaining cases
        if upper > 0:
            logger.info(f"Starting linear collection from {start or 1} to {upper}")
            start_num = start or 1
            # If max_cases is provided, ensure the upper bound respects the start + max_cases - 1
            if max_cases:
                try:
                    start_num_int = int(start_num)
                    end_limit = start_num_int + int(max_cases) - 1
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

                # If not forcing, skip if case already exists in DB
                try:
                    # Check tracker skip rules before exporter/db checks or web calls
                    try:
                        should_skip, reason = self.tracker.should_skip_case(case_number, force=self.force, run_id=batch_run_id)
                    except TypeError:
                        should_skip, reason = self.tracker.should_skip_case(case_number, force=self.force)
                    if should_skip:
                        print(f"→ Skipping {case_number}: {reason}")
                        logger.info(f"Skipping {case_number}: {reason}")
                        skipped.append({"case_number": case_number, "status": "skipped", "reason": reason})
                        # record skip via integration helper
                        integration.record_scrape_result(case_number, False, outcome='skipped', error_message=reason)
                        continue
                    if not self.force and self.exporter.case_exists(case_number):
                        print(f"→ Skipping {case_number}: already in database")
                        logger.info(f"Skipping {case_number}: exists_in_db")
                        skipped.append({"case_number": case_number, "status": "skipped"})
                        
                        # Record skip via integration helper
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
                        
                        # Record successful collection via integration helper
                        integration.record_scrape_result(case_number, True, case_id=getattr(case, "case_id", None))
                        # 标记为成功采集
                        try:
                            from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
                            simplified_tracker = SimplifiedTrackingService()
                            simplified_tracker.mark_case_attempt(case_number, CaseStatus.SUCCESS)
                        except Exception as e:
                            logger.warning(f"Failed to mark case success for {case_number}: {e}")
                    else:
                        consecutive_failures += 1
                        
                        # Check if case was already marked as no_data before treating as failed
                        try:
                            from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
                            simplified_tracker = SimplifiedTrackingService()
                            case_info = simplified_tracker.get_case_info(case_number)
                            if case_info and case_info.get('status') == CaseStatus.NO_DATA:
                                logger.info(f"Case {case_number} already marked as no_data, not treating as failure")
                                # Record no_data outcome via integration helper to maintain consistency
                                integration.record_scrape_result(case_number, False, outcome='no_data', error_message="Case not found")
                            else:
                                # Record failed collection via integration helper
                                integration.record_scrape_result(case_number, False, error_message="Scraping failed")
                                # 标记为失败
                                simplified_tracker.mark_case_attempt(case_number, CaseStatus.FAILED, "Scraping failed")
                        except Exception as e:
                            logger.warning(f"Failed to check case status for {case_number}: {e}")
                            # Fallback to treating as failure
                            integration.record_scrape_result(case_number, False, error_message="Scraping failed")
                            simplified_tracker.mark_case_attempt(case_number, CaseStatus.FAILED, "Scraping failed")
                        except Exception as e:
                            logger.warning(f"Failed to mark case failure for {case_number}: {e}")
                        time.sleep(0.1)  # Short pause before retry
                except Exception as e:
                    # Unexpected exception during scrape; record and continue
                    logger.error(f"Unhandled error scraping case {case_number}: {e}")
                    
                    # Record error to tracking system
                    try:
                        integration.record_scrape_result(case_number, False, error_message=str(e))
                    except Exception:
                        pass
                    
                    # 标记为失败
                    try:
                        from src.services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus
                        simplified_tracker = SimplifiedTrackingService()
                        simplified_tracker.mark_case_attempt(case_number, CaseStatus.FAILED, str(e))
                    except Exception as e:
                        logger.warning(f"Failed to mark case failure for {case_number}: {e}")
                    consecutive_failures += 1

                # Progress update every 10 cases
                if processed % 10 == 0:
                    success_rate = len(cases) / processed * 100
                    print(
                        f"Progress: {processed}/{upper} processed, {len(cases)} successful ({success_rate:.1f}%)"
                    )
                    logger.info(f"Progress: processed={processed}, upper={upper}, successful={len(cases)}, success_rate={success_rate:.1f}%")

                # Check if we should skip this year
                if self.discovery.should_skip_year(year, consecutive_failures):
                    logger.info(
                        f"Skipping remaining cases for year {year} due to consecutive failures"
                    )
                    break

                # Stop if we reached the limit
                if max_cases and len(cases) >= max_cases:
                    break

        # Run-level NDJSON logging removed - now using database tracking

        # Emit run-level metrics: duration and failure rate
        run_end_time = datetime.now(timezone.utc)
        try:
                run_duration = time.time() - run_start_ts
                emit_metric("batch.run.duration_seconds", run_duration)
                processed = processed if 'processed' in locals() else 0
                failures = processed - len(cases) if processed else 0
                failure_rate = (failures / processed) if processed else 0.0
                emit_metric("batch.run.failure_rate", float(failure_rate))
        except Exception:
            pass
        finally:
            # End batch run tracking
            try:
                self.tracker.finish_run(batch_run_id, 'completed')
                logger.info(f"Batch run {batch_run_id} completed successfully")
            except Exception as e:
                logger.error(f"Failed to finish batch run tracking: {e}")

        # Display post-run statistics
        post_run_stats = stats_service.calculate_run_statistics(
            year=year,
            start_time=run_start_time,
            end_time=run_end_time,
            upper_bound=upper,
            processed_count=processed if 'processed' in locals() else 0,
            probes_used=probes,
            cases_collected=len(cases),
            run_id=batch_run_id
        )
        stats_service.log_and_display_statistics(post_run_stats, f"本次运行统计信息 (Run Statistics) - {year}")

        # Return scraped cases and skipped list for auditing
        return cases, skipped

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

  # Probe (dry-run; no network calls)
  python -m src.cli.main probe 2025

  # Probe (live; performs HTTP requests — use with caution)
  python -m src.cli.main probe 2025 --live --initial-high 2000

  # Purge dry-run (audit only)
  python -m src.cli.main purge 2024 --dry-run

    # Purge actual run (destructive)
    python -m src.cli.main purge 2024 --yes

Notes:
  - Use `--dry-run` to validate purge actions before running destructive operations.
  - Probe `--live` will perform network calls; respect rate limits and legal constraints.
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
        # Accept --force after the 'batch' subcommand as well
        batch_parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-scraping of cases even if they exist in the database",
        )

        # Probe command: find an approximate upper numeric id for a given year
        probe_parser = subparsers.add_parser(
            "probe",
            help="Probe numeric IDs to discover an approximate upper bound",
            description=(
                "Run an exponential probe to discover an approximate upper numeric id for a year. "
                "By default this is a dry-run (no network). Use --live to perform actual requests (use with caution)."
            ),
        )
        probe_parser.add_argument("year", type=int, help="Year to probe (two-digit suffix used in case numbers)")
        probe_parser.add_argument(
            "--start", type=int, default=1, help="Starting numeric id for probing (default: %(default)s)"
        )
        probe_parser.add_argument(
            "--initial-high",
            type=int,
            default=1000,
            help="Initial high guess for exponential probing (default: %(default)s)",
        )
        probe_parser.add_argument(
            "--probe-budget",
            type=int,
            default=Config.get_probe_budget(),
            help="Maximum exponent n for 2^n steps in probing (default: %(default)s)",
        )
        probe_parser.add_argument(
            "--safe-stop-no-records",
            type=int,
            default=Config.get_safe_stop_no_records(),
            help="Number of consecutive no-records to stop probing (default: %(default)s)",
        )
        probe_parser.add_argument(
            "--max-limit",
            type=int,
            default=100000,
            help="Hard upper limit for numeric ids (default: %(default)s)",
        )
        probe_parser.add_argument(
            "--coarse-step",
            type=int,
            default=100,
            help="Coarse backward scan step (default: %(default)s)",
        )
        probe_parser.add_argument(
            "--refine-range",
            type=int,
            default=200,
            help="Forward refinement window (default: %(default)s)",
        )
        probe_parser.add_argument(
            "--live",
            action="store_true",
            help="Perform live HTTP probing using the scraper (use with caution)",
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
                def _mask_short(val: str) -> str:
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

                scraped_cases, skipped = self.scrape_batch_cases(
                    args.year,
                    args.max_cases,
                    start=getattr(args, "start", None),
                )
            elif args.command == "probe":
                # Enable probe state persistence for probe command
                import os
                os.environ["FCT_PERSIST_PROBE_STATE"] = "true"
                # Probe CLI: will run the probing algorithm. By default this is a dry-run that
                # prints parameters; to perform real HTTP probes pass --live.
                if getattr(args, "live", False):
                    # Live probing: create a scraper and use it to search for constructed case numbers.
                    try:
                        scraper = CaseScraperService(headless=True)
                        # initialize page for faster repeated searches
                        try:
                            scraper.initialize_page()
                        except Exception:
                            pass

                        # Create a real run for probe so records are attributed to a run
                        probe_run_id = None
                        try:
                            probe_run_id = self.tracker.start_run(
                                processing_mode="probe",
                                parameters={
                                    "year": args.year,
                                    "start": getattr(args, "start", 1),
                                    "initial_high": getattr(args, "initial_high", 1000),
                                },
                            )
                            # Also set the current_run_id to be used by methods that reference
                            # self.current_run_id (defensive compatibility)
                            self.current_run_id = probe_run_id
                        except Exception:
                            probe_run_id = None

                        # Use tracking integration to ensure probe results are recorded to DB
                        integration = None
                        if probe_run_id:
                            integration = TrackingIntegration(self.tracker, probe_run_id)

                        def check_case_exists(n: int) -> bool:
                            # Build case number using IMM-<n>-<yy> pattern by default
                            try:
                                yy = str(args.year)[-2:]
                                case_number = f"IMM-{n}-{yy}"
                                logger.debug(f"call [scraper.search_case] for {case_number}")
                                # Respect tracking skip rules before calling out to the
                                # scraper to avoid repeated probing for known no-results
                                should_skip, reason = self.tracker.should_skip_case(case_number, force=self.force, run_id=probe_run_id)
                                if should_skip:
                                    logger.info(f"Skipping {case_number}: {reason}")
                                    try:
                                        if integration:
                                            integration.record_probe_result(case_number, False, 0, f"Skipped: {reason}", outcome='skipped')
                                    except Exception:
                                        pass
                                    return False
                                found = scraper.search_case(case_number)
                                # If we have a tracking integration, record the probe result
                                try:
                                    if integration:
                                        processing_time_ms = 0
                                        integration.record_probe_result(case_number, bool(found), processing_time_ms)
                                except Exception as e:
                                    logger.debug(f"Failed to record probe result for {case_number}: {e}")
                                return bool(found)
                            except Exception:
                                return False

                        print("Starting live probe (this will perform HTTP requests).")
                        logger.info("Starting live probe: live HTTP probing enabled")
                    except Exception as e:
                        print(f"Failed to initialize live scraper for probing: {e}")
                        sys.exit(1)
                else:
                    # Dry-run adapter: warn and create a faux-check that always returns False so
                    # the algorithm will exercise growth behavior without making network calls.
                    def check_case_exists(n: int) -> bool:
                        print(f"[dry-run] would check ID: {n}")
                        return False
                    # Also print at least one dry-run hint even if probe_state exists
                    print(f"[dry-run] would check ID: {getattr(args, 'start', 1)}")
                    logger.info(f"Probe dry-run: would check starting id {getattr(args, 'start', 1)}")

                # Run the probe
                # Use the CLI-configured/shared rate limiter for probing/backoff
                rl = getattr(self, "rate_limiter", None) or EthicalRateLimiter(
                    interval_seconds=Config.get_rate_limit_seconds(),
                    backoff_factor=Config.get_backoff_factor(),
                    max_backoff_seconds=Config.get_max_backoff_seconds(),
                )

                # Enhanced fast check for probe command
                def probe_fast_check(n: int):
                    if self.force:
                        return {'exists': False, 'status': 'unknown', 'skip_reason': 'force enabled'}
                    
                    case_number = f"IMM-{n}-{args.year % 100:02d}"
                    exists = self.exporter.case_exists(case_number)
                    
                    # Get detailed status from tracking service if available
                    try:
                        from src.services.simplified_tracking_service import SimplifiedTrackingService
                        simplified_tracker = SimplifiedTrackingService()
                        case_info = simplified_tracker.get_case_info(case_number)
                        status = case_info.get('status', 'unknown') if case_info else 'unknown'
                        return {
                            'exists': exists,
                            'status': status,
                            'skip_reason': 'already exists' if exists else '',
                            'should_skip': exists
                        }
                    except Exception:
                        return {
                            'exists': exists,
                            'status': 'success' if exists else 'unknown',
                            'skip_reason': 'already exists' if exists else '',
                            'should_skip': exists
                        }
                
                upper, probes = BatchService.find_upper_bound(
                    check_case_exists=check_case_exists,
                    fast_check_case_exists=probe_fast_check,
                    start=getattr(args, "start", 1),
                    initial_high=getattr(args, "initial_high", 1000),
                    max_limit=getattr(args, "max_limit", 100000),
                    coarse_step=getattr(args, "coarse_step", 100),
                    refine_range=getattr(args, "refine_range", 200),
                    probe_budget=getattr(args, "probe_budget", Config.get_probe_budget()),
                    safe_stop=getattr(args, "safe_stop_no_records", Config.get_safe_stop_no_records()),
                    max_probes=10000,
                    rate_limiter=rl,
                    format_case_number=lambda n: f"IMM-{n}-{args.year % 100:02d}",
                )

                print("\nProbe result:")
                print(f"  Approx upper numeric id: {upper}")
                print(f"  Probes used: {probes}")
                logger.info(f"Probe result: upper={upper}, probes={probes}")
                # Stop processing after probe results — do not fall through to batch audit/export logic
                # finish probe run if applicable
                try:
                    if getattr(self, 'current_run_id', None):
                        self.tracker.finish_run(self.current_run_id, 'completed')
                        logger.info(f"Probe run {self.current_run_id} completed")
                except Exception as e:
                    logger.error(f"Failed to finish probe run: {e}")
                return
                if scraped_cases or skipped:
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
                        "skipped_count": len(skipped),
                        "skipped": skipped,
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
                    print(f"  JSON: {export_result.get('json')}")
                    print(f"  Audit: {audit_path}")
                    if export_result.get("database"):
                        print(f"  Database: {export_result['database']}")
                    # Mirror the console output into structured info logs for operators
                    logger.info(
                        f"Batch scrape complete: year={args.year}, cases_scraped={len(scraped_cases)}, json={export_result.get('json')}, audit={audit_path}, database={export_result.get('database')}"
                    )
                else:
                    print(f"\nNo cases found for year {args.year}")
                    logger.info(f"No cases found for year {args.year}")
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
                if not files_only:
                    if not dry_run:
                        logger.info(f"Purging tracking data for year {year}")
                        tracking_stats = self.tracker.purge_year(year)
                        logger.info(f"Tracking purge completed: {tracking_stats}")
                        logger.info(f"Tracking data purged: {tracking_stats.get('cases_deleted', 0)} cases, "
                                f"{tracking_stats.get('docket_entries_deleted', 0)} docket entries, "
                                f"{tracking_stats.get('history_deleted', 0)} history records, "
                                f"{tracking_stats.get('snapshots_deleted', 0)} snapshots, "
                                f"{tracking_stats.get('runs_deleted', 0)} runs")
                    else:
                        logger.info(f"[DRY RUN] Would purge tracking data for year {year}")
                        print("[DRY RUN] Would purge tracking data for year {year}")
                
                logger.info("Purge summary written to:", result.get("audit_path"))

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
