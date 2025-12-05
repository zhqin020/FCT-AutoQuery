"""
Example of how to integrate database-based tracking into batch processing.

This shows how the existing scrape_batch_cases method can be refactored 
to use the new CaseTrackingService instead of relying solely on NDJSON files.
"""

def scrape_batch_cases_with_tracking(self, year: int, start: Optional[int] = None, 
                                   max_cases: Optional[int] = None) -> None:
    """
    Enhanced batch scraping with database-based tracking.
    
    This replaces the original scrape_batch_cases method with proper tracking integration.
    """
    import time
    from datetime import datetime, timezone
    from src.cli.tracking_integration import TrackingIntegration, create_tracking_integrated_check_exists
    from src.services.batch_service import BatchService
    from src.lib.config import Config
    
    # Start tracking run
    run_id = self.tracker.start_run(
        mode='batch',
        parameters={
            'year': year,
            'start': start,
            'max_cases': max_cases,
            'force': self.force
        },
        metadata={
            'scraper_headless': self._scraper_headless,
            'config': {
                'rate_limit_seconds': Config.get_rate_limit_seconds(),
                'backoff_factor': Config.get_backoff_factor(),
                'probe_budget': getattr(self, 'probe_budget', Config.get_probe_budget()),
                'safe_stop_no_records': Config.get_safe_stop_no_records()
            }
        }
    )
    
    # Initialize tracking integration
    tracking = TrackingIntegration(self.tracker, run_id)
    
    try:
        # Initialize variables
        cases = []
        consecutive_failures = 0
        processed = 0
        skipped = []
        run_start_ts = time.time()
        
        # NDJSON logger removed - use CaseTrackingService for DB-backed tracking
        run_logger = None
        
        # Use rate limiter
        rl = getattr(self, "rate_limiter", None) or EthicalRateLimiter(
            interval_seconds=Config.get_rate_limit_seconds(),
            backoff_factor=Config.get_backoff_factor(),
            max_backoff_seconds=Config.get_max_backoff_seconds(),
        )
        
        # Create tracking-integrated check function
        check_case_exists = create_tracking_integrated_check_exists(
            tracking, self.force, year
        )
        
        # Enhanced check_case_exists with web search fallback
        def enhanced_check_case_exists(case_num: int) -> bool:
            court_file_no = f"IMM-{case_num}-{year % 100:02d}"
            
            # First check tracking data
            should_skip, reason = tracking.check_should_skip(court_file_no, self.force)
            if should_skip and reason == "exists_in_db":
                tracking.track_skipped_case(court_file_no, reason)
                return True
            
            # Check probe state
            probe_state = tracking.get_probe_state(case_num, year % 100)
            if probe_state is not None:
                exists = probe_state['exists']
                tracking.record_probe_result(case_num, year % 100, exists)
                return exists
            
            # If no existing data, perform web search
            try:
                result = self.scraper.search_case(court_file_no)
                tracking.record_probe_result(case_num, year % 100, result)
                return result
            except Exception as e:
                logger.warning(f"search_case failed for {court_file_no}: {e}")
                tracking.record_probe_result(case_num, year % 100, False)
                return False
        
        # Enhanced scrape function with tracking
        def enhanced_scrape_case_data(case_num: int) -> Optional[object]:
            court_file_no = f"IMM-{case_num}-{year % 100:02d}"
            
            # Check if should skip
            should_skip, reason = tracking.check_should_skip(court_file_no, self.force)
            if should_skip:
                tracking.track_skipped_case(court_file_no, reason)
                return None
            
            # Start tracking
            started_at = tracking.start_case_processing(court_file_no, 'batch_probe')
            
            try:
                # Check if case already exists in database
                if not self.force and self.exporter.case_exists(court_file_no):
                    tracking.track_skipped_case(court_file_no, "exists_in_db")
                    return None
                
                # Perform scraping
                case = self.scrape_single_case(court_file_no)
                
                if case:
                    tracking.track_successful_scrape(case, started_at, 'batch_probe')
                    cases.append(case)
                else:
                    tracking.track_failed_scrape(court_file_no, started_at, 'No case returned', 'batch_probe')
                
                return case
                
            except Exception as e:
                tracking.track_error_case(court_file_no, str(e), started_at)
                return None
        
        # Run batch processing with tracking
        logger.info("Starting batch processing with database tracking")
        
        upper, probes = BatchService.find_upper_bound(
            check_case_exists=enhanced_check_case_exists,
            start=start or 1,
            initial_high=getattr(self, 'initial_high', 1000),
            max_limit=getattr(self, 'max_limit', 100000),
            coarse_step=getattr(self, 'coarse_step', 100),
            refine_range=getattr(self, 'refine_range', 200),
            probe_budget=getattr(self, 'probe_budget', Config.get_probe_budget()),
            safe_stop=getattr(self, 'safe_stop_no_records', Config.get_safe_stop_no_records()),
            max_probes=10000,
            rate_limiter=rl,
            collect=True,
            scrape_case_data=enhanced_scrape_case_data,
            max_cases=max_cases or 100000,
        )
        
        print(f"\nBatch processing completed:")
        print(f"  Approx upper numeric id: {upper}")
        print(f"  Probes used: {probes}")
        print(f"  Cases collected: {len(cases)}")
        
        # Linear scan for remaining cases (if needed)
        if upper > 0:
            logger.info(f"Starting linear collection from {start or 1} to {upper}")
            start_num = start or 1
            
            for case_num in range(start_num, upper + 1):
                if max_cases and len(cases) >= max_cases:
                    break
                
                if self.emergency_stop:
                    logger.warning("Emergency stop triggered - halting batch processing")
                    break
                
                court_file_no = f"IMM-{case_num}-{year % 100:02d}"
                processed += 1
                
                # Skip if already collected
                if any(case.court_file_no == court_file_no for case in cases):
                    continue
                
                print(f"Processing case {case_num}/{upper}: {court_file_no}")
                
                # Check tracking before processing
                should_skip, reason = tracking.check_should_skip(court_file_no, self.force)
                if should_skip:
                    print(f"→ Skipping {court_file_no}: {reason}")
                    skipped.append({"case_number": court_file_no, "status": "skipped", "reason": reason})
                    continue
                
                # Process case with tracking
                started_at = tracking.start_case_processing(court_file_no, 'batch_linear')
                
                try:
                    case = self.scrape_single_case(court_file_no)
                    if case:
                        cases.append(case)
                        tracking.track_successful_scrape(case, started_at, 'batch_linear')
                        print(f"✓ Successfully scraped case {case.court_file_no}")
                    else:
                        tracking.track_failed_scrape(court_file_no, started_at, 'No case returned', 'batch_linear')
                        
                except Exception as e:
                    tracking.track_error_case(court_file_no, str(e), started_at)
                    logger.error(f"Unhandled error scraping case {court_file_no}: {e}")
                
                # Progress update
                if processed % 10 == 0:
                    success_rate = len(cases) / processed * 100
                    print(f"Progress: {processed}/{upper} processed, {len(cases)} successful ({success_rate:.1f}%)")
        
        # Finish tracking run
        self.tracker.finish_run(run_id, 'completed')
        
        # Export results
        if cases:
            output_file = f"output/batch_results_{year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            self.exporter.export_cases_to_json(cases, output_file)
            print(f"Results exported to: {output_file}")
        
        # Print summary
        print(f"\nBatch Processing Summary:")
        print(f"  Total processed: {processed}")
        print(f"  Successfully collected: {len(cases)}")
        print(f"  Skipped: {len(skipped)}")
        print(f"  Success rate: {len(cases) / processed * 100:.1f}%" if processed > 0 else "N/A")
        print(f"  Run ID: {run_id}")
        
        # No NDJSON logger to finish; DB tracking run is ended by self.tracker.finish_run
        
    except Exception as e:
        # Finish tracking run with error status
        self.tracker.finish_run(run_id, 'failed')
        logger.error(f"Batch processing failed: {e}")
        raise

# Example of how to query case history
def query_case_history_example(self, court_file_no: str):
    """Example of querying case processing history."""
    
    # Get case status
    status = self.tracker.get_case_status(court_file_no)
    if status:
        print(f"Current status for {court_file_no}:")
        print(f"  Last outcome: {status['last_outcome']}")
        print(f"  Last processed: {status['last_processed_at']}")
        print(f"  Consecutive failures: {status['consecutive_failures']}")
        print(f"  First seen: {status['first_seen_at']}")
        print(f"  Last success: {status['last_success_at']}")
    
    # Get detailed history
    history = self.tracker.get_case_history(court_file_no, limit=5)
    if history:
        print(f"\nRecent processing history for {court_file_no}:")
        for record in history:
            print(f"  {record['started_at']}: {record['outcome']} ({record['scrape_mode']})")
            if record.get('reason'):
                print(f"    Reason: {record['reason']}")
            if record.get('message'):
                print(f"    Message: {record['message']}")

# Example of getting recent runs
def get_recent_runs_example(self, days: int = 7):
    """Example of querying recent processing runs."""
    runs = self.tracker.get_recent_runs(days=days)
    
    print(f"Recent runs (last {days} days):")
    for run in runs:
        print(f"  {run['run_id']}: {run['mode']} - {run['status']}")
        print(f"    Started: {run['started_at']}")
        print(f"    Cases: {run['total_cases']} (success: {run['success_count']}, failed: {run['failed_count']})")
        if run.get('completed_at'):
            print(f"    Duration: {run['completed_at'] - run['started_at']}")