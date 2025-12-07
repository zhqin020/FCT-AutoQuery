"""Integration utilities for case tracking system."""

from typing import Callable, Optional
from datetime import datetime, timezone

from src.services.case_tracking_service import CaseTrackingService
from src.lib.logging_config import get_logger

logger = get_logger()


class TrackingIntegration:
    """Helper class for integrating case tracking into existing operations."""
    
    def __init__(self, tracker: CaseTrackingService, run_id: str):
        self.tracker = tracker
        self.run_id = run_id
    
    def record_probe_result(self, case_number: str, exists: bool,
                           processing_time_ms: Optional[int] = None,
                           error_message: Optional[str] = None,
                           outcome: Optional[str] = None):
        """Record a probe result to tracking system."""
        # If the caller provides an explicit outcome, use that. If an error message
        # is present, prefer recording 'error' so it isn't confused with 'no_data'.
        if outcome:
            final_outcome = outcome
        elif error_message:
            final_outcome = 'error'
        else:
            final_outcome = "success" if exists else "no_data"
        
        # Use stored DB value if exists to preserve matching for joins
        try:
            stored_no = self.tracker.get_stored_case_case_number(case_number) or case_number
        except Exception:
            stored_no = case_number
        self.tracker.record_case_processing(
            case_number=case_number,
            db_case_number=stored_no,
            run_id=self.run_id,
            outcome=final_outcome,
            processing_mode="batch_probe",
            error_message=error_message,
            processing_duration_ms=processing_time_ms
        )
        
        logger.debug(f"Recorded probe: {case_number} -> {final_outcome}")
    
    def record_scrape_result(self, case_number: str, success: bool,
                           case_id: Optional[str] = None,
                           processing_time_ms: Optional[int] = None,
                           error_message: Optional[str] = None,
                           outcome: Optional[str] = None):
        """Record a scrape result to tracking system."""
        if outcome:
            final_outcome = outcome
        elif error_message:
            final_outcome = 'error'
        else:
            final_outcome = "success" if success else "failed"
        
        # Use stored DB value if exists to preserve matching for joins
        try:
            stored_no = self.tracker.get_stored_case_case_number(case_number) or case_number
        except Exception:
            stored_no = case_number
        self.tracker.record_case_processing(
            case_number=case_number,
            db_case_number=stored_no,
            run_id=self.run_id,
            outcome=final_outcome,
            processing_mode="batch_collect",
            case_id=case_id,
            error_message=error_message,
            processing_duration_ms=processing_time_ms
        )
        
        logger.debug(f"Recorded scrape: {case_number} -> {final_outcome}")


def create_tracking_integrated_check_exists(cli_instance, run_id: str, year: int = 2025) -> Callable[[int], bool]:
    """
    Create a check_case_exists function that integrates with tracking system.
    
    Args:
        cli_instance: FederalCourtScraperCLI instance
        run_id: Current run ID for tracking
        
    Returns:
        Function that can be used as check_case_exists parameter
    """
    integration = TrackingIntegration(cli_instance.tracker, run_id)
    
    def tracked_check_exists(number: int) -> bool:
        """Check if case exists and record result to tracking system."""
        case_number = f"IMM-{number}-{year % 100:02d}"
        
        # Check if we should skip this case
        try:
            should_skip, reason = cli_instance.tracker.should_skip_case(case_number, force=cli_instance.force, run_id=run_id)
        except TypeError:
            should_skip, reason = cli_instance.tracker.should_skip_case(case_number, force=cli_instance.force)
        if should_skip:
            logger.info(f"Skipping {case_number}: {reason}")
            integration.record_probe_result(case_number, False, error_message=f"Skipped: {reason}", outcome='skipped')
            return False
        
        # Perform the actual check
        start_time = datetime.now(timezone.utc)
        try:
            # Use existing scraper to check existence
            if cli_instance.scraper is None:
                cli_instance.scraper = cli_instance.scraper_class(headless=cli_instance._scraper_headless)
            
            exists = cli_instance.scraper.search_case(case_number)
            
            # Record processing time
            processing_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Record result
            integration.record_probe_result(case_number, exists, processing_time_ms)
            
            return exists
            
        except Exception as e:
            processing_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            error_msg = f"Check failed: {str(e)}"
            integration.record_probe_result(case_number, False, processing_time_ms, error_msg)
            logger.error(f"Failed to check case {case_number}: {e}")
            return False
    
    return tracked_check_exists


def create_tracking_integrated_scrape_case(cli_instance, run_id: str, year: int = 2025) -> Callable[[int], Optional[object]]:
    """
    Create a scrape_case_data function that integrates with tracking system.
    
    Args:
        cli_instance: FederalCourtScraperCLI instance
        run_id: Current run ID for tracking
        
    Returns:
        Function that can be used as scrape_case_data parameter
    """
    integration = TrackingIntegration(cli_instance.tracker, run_id)
    
    def tracked_scrape_case(number: int) -> Optional[object]:
        """Scrape case data and record result to tracking system."""
        case_number = f"IMM-{number}-{year % 100:02d}"
        
        # Check if we should skip this case
        try:
            should_skip, reason = cli_instance.tracker.should_skip_case(case_number, force=cli_instance.force, run_id=run_id)
        except TypeError:
            should_skip, reason = cli_instance.tracker.should_skip_case(case_number, force=cli_instance.force)
        if should_skip:
            logger.info(f"Skipping scrape {case_number}: {reason}")
            integration.record_scrape_result(case_number, False, error_message=f"Skipped: {reason}", outcome='skipped')
            return None
        
        # Perform the actual scraping
        start_time = datetime.now(timezone.utc)
        try:
            if cli_instance.scraper is None:
                cli_instance.scraper = cli_instance.scraper_class(headless=cli_instance._scraper_headless)
            
            case = cli_instance.scraper.scrape_case_data(case_number)
            
            # Record processing time
            processing_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            
            # Record result
            if case:
                integration.record_scrape_result(
                    case_number, True, 
                    case_id=getattr(case, 'case_id', None),
                    processing_time_ms=processing_time_ms
                )
            else:
                integration.record_scrape_result(case_number, False, processing_time_ms, "No case data returned")
            
            return case
            
        except Exception as e:
            processing_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            error_msg = f"Scrape failed: {str(e)}"
            integration.record_scrape_result(case_number, False, processing_time_ms, error_msg)
            logger.error(f"Failed to scrape case {case_number}: {e}")
            return None
    
    return tracked_scrape_case