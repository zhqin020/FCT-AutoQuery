"""Command-line interface for Federal Court Case Scraper."""

import argparse
import sys
import time
from datetime import datetime
from typing import Optional

from src.lib.config import Config
from src.lib.logging_config import get_logger, setup_logging
from src.models.case import Case
from src.services.case_scraper_service import CaseScraperService
from src.services.export_service import ExportService
from src.services.url_discovery_service import UrlDiscoveryService
from src.services.batch_service import BatchService
from src.lib.run_logger import RunLogger
from src.cli.purge import purge_year
from src.lib.rate_limiter import EthicalRateLimiter

logger = get_logger()


class FederalCourtScraperCLI:
    """Command-line interface for the Federal Court Case Scraper."""

    def __init__(self):
        """Initialize the CLI."""
        # Setup logging to console and file
        setup_logging(log_level="INFO", log_file="logs/scraper.log")

        self.config = Config()
        # Prefer non-headless in CLI runs to match interactive harness behavior
        # and avoid client-side rendering differences seen in headless mode.
        # Lazily initialize the scraper to avoid launching a browser when all
        # cases are already present in the DB.
        self.scraper = None
        self._scraper_headless = False
        self.discovery = UrlDiscoveryService(self.config)
        self.exporter = ExportService(self.config)
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
                    break
                logger.warning(f"Scrape attempt {attempt} failed for case: {case_number}")
                # record failure/backoff before retrying
                try:
                    delay = self.rate_limiter.record_failure()
                    time.sleep(delay)
                except Exception:
                    time.sleep(0.1)
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
        Scrape multiple cases for a given year.

        Args:
            year: Year to scrape cases for
            max_cases: Maximum number of cases to scrape

        Returns:
            List of scraped Case objects
        """
        logger.info(f"Starting batch scrape for year {year}")

        cases = []
        consecutive_failures = 0
        processed = 0
        skipped = []

        # Run-level logger to record per-case outcomes (configurable)
        run_logger = RunLogger() if Config.get_enable_run_logger() else None
        if run_logger:
            run_logger.start()

        # Get case numbers to process. If a start index is provided and the discovery
        # service supports generation from a start, use that method.
        if start is not None and hasattr(self.discovery, "generate_case_numbers_from_start"):
            case_numbers = self.discovery.generate_case_numbers_from_start(year, start, max_cases)
        else:
            case_numbers = self.discovery.generate_case_numbers_from_last(year, max_cases)
        total_to_process = len(case_numbers)

        print(f"Processing {total_to_process} case numbers for year {year}...")

        try:
            for i, case_number in enumerate(case_numbers, 1):
                if self.emergency_stop:
                    logger.warning("Emergency stop triggered - halting batch processing")
                    break

                print(f"Processing case {i}/{total_to_process}: {case_number}")

                # If not forcing, skip if case already exists in DB (avoid duplicate scraping)
                try:
                    if not self.force and self.exporter.case_exists(case_number):
                        print(f"→ Skipping {case_number}: already in database")
                        skipped.append({"case_number": case_number, "status": "skipped"})
                        if run_logger:
                            try:
                                run_logger.record_case(case_number, outcome="skipped", reason="exists_in_db")
                            except Exception:
                                pass
                        # still count as processed but not as a success
                        processed += 1
                        # Progress update every 10 cases
                        if processed % 10 == 0:
                            success_rate = len(cases) / processed * 100
                            print(
                                f"Progress: {processed}/{total_to_process} processed, {len(cases)} successful ({success_rate:.1f}%)"
                            )
                        # Check if we should skip this year
                        if self.discovery.should_skip_year(year, consecutive_failures):
                            logger.info(
                                f"Skipping remaining cases for year {year} due to consecutive failures"
                            )
                        # Stop if we reached the limit
                        if max_cases and len(cases) >= max_cases:
                            break
                        continue
                except Exception:
                    logger.debug(
                        f"Existence check failed for {case_number}; attempting scrape"
                    )

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
                        if run_logger:
                            try:
                                run_logger.record_case(case_number, outcome="success", case_id=getattr(case, "case_id", None))
                            except Exception:
                                pass
                    else:
                        # record transient failure/backoff
                        try:
                            delay = self.rate_limiter.record_failure()
                            time.sleep(delay)
                        except Exception:
                            time.sleep(0.1)
                        consecutive_failures += 1
                        print(f"✗ Failed to scrape case {case_number}")
                        if run_logger:
                            try:
                                run_logger.record_case(case_number, outcome="failed")
                            except Exception:
                                pass
                except Exception as e:
                    # Unexpected exception during scrape; record and continue
                    logger.error(f"Unhandled error scraping case {case_number}: {e}")
                    if run_logger:
                        try:
                            run_logger.record_case(case_number, outcome="error", message=str(e))
                        except Exception:
                            pass
                    consecutive_failures += 1

                processed += 1

                # Progress update every 10 cases
                if processed % 10 == 0:
                    success_rate = len(cases) / processed * 100
                    print(
                        f"Progress: {processed}/{total_to_process} processed, {len(cases)} successful ({success_rate:.1f}%)"
                    )

                # Check if we should skip this year
                if self.discovery.should_skip_year(year, consecutive_failures):
                    logger.info(
                        f"Skipping remaining cases for year {year} due to consecutive failures"
                    )
                    break

                # Stop if we reached the limit
                if max_cases and len(cases) >= max_cases:
                    break

        finally:
            if run_logger:
                try:
                    run_logger.finish()
                    logger.info(f"Run-level NDJSON written: {run_logger.path}")
                except Exception:
                    pass

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
        else:
            total_cases = self.exporter.get_case_count_from_database()
            print(f"\nTotal cases in database: {total_cases}")

    def run(self) -> None:
        """Run the CLI application."""
        parser = argparse.ArgumentParser(
            description="Federal Court Case Scraper",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Scrape a single case
  python -m src.cli.main single IMM-12345-25
            # Do not initialize browser here; initialize lazily in `scrape_single_case`
  # Scrape batch cases for 2025
  python -m src.cli.main batch 2025 --max-cases 10

  # Show statistics
  python -m src.cli.main stats --year 2025
            """,
        )

        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Single case command
        single_parser = subparsers.add_parser("single", help="Scrape a single case")
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

        # Rate limiter / backoff tuning (global)
        parser.add_argument(
            "--rate-interval",
            type=float,
            default=Config.get_rate_limit_seconds(),
            help="Fixed interval in seconds between requests (default from config)",
        )
        parser.add_argument(
            "--backoff-factor",
            type=float,
            default=Config.get_backoff_factor(),
            help="Exponential backoff base multiplier for failures (default from config)",
        )
        parser.add_argument(
            "--max-backoff-seconds",
            type=float,
            default=Config.get_max_backoff_seconds(),
            help="Maximum backoff delay in seconds (default from config)",
        )

        # Batch command
        batch_parser = subparsers.add_parser(
            "batch", help="Scrape multiple cases for a year"
        )
        batch_parser.add_argument("year", type=int, help="Year to scrape cases for")
        batch_parser.add_argument(
            "--max-cases", type=int, help="Maximum number of cases to scrape"
        )
        batch_parser.add_argument(
            "--start",
            type=int,
            default=1,
            help="Start numeric id (default 1). Example: --start 30 starts at IMM-30-<yy>",
        )
        # Accept --force after the 'batch' subcommand as well
        batch_parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-scraping of cases even if they exist in the database",
        )

        # Probe command: find an approximate upper numeric id for a given year
        probe_parser = subparsers.add_parser(
            "probe", help="Probe numeric IDs to discover an approximate upper bound"
        )
        probe_parser.add_argument("year", type=int, help="Year to probe (two-digit suffix used in case numbers)")
        probe_parser.add_argument(
            "--start", type=int, default=1, help="Starting numeric id for probing (default: 1)"
        )
        probe_parser.add_argument(
            "--initial-high",
            type=int,
            default=1000,
            help="Initial high guess for exponential probing (default: 1000)",
        )
        probe_parser.add_argument(
            "--probe-budget",
            type=int,
            default=200,
            help="Maximum number of probes allowed (default: 200)",
        )
        probe_parser.add_argument(
            "--max-limit",
            type=int,
            default=100000,
            help="Hard upper limit for numeric ids (default: 100000)",
        )
        probe_parser.add_argument(
            "--coarse-step",
            type=int,
            default=100,
            help="Coarse backward scan step (default: 100)",
        )
        probe_parser.add_argument(
            "--refine-range",
            type=int,
            default=200,
            help="Forward refinement window (default: 200)",
        )
        probe_parser.add_argument(
            "--live",
            action="store_true",
            help="Perform live HTTP probing using the scraper (use with caution)",
        )

        # Stats command
        stats_parser = subparsers.add_parser("stats", help="Show scraping statistics")
        stats_parser.add_argument(
            "--year",
            type=int,
            help="Year to show stats for (shows total if not specified)",
        )

        # Purge command
        purge_parser = subparsers.add_parser(
            "purge", help="Purge data for a given year (destructive)"
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
            help="Non-interactive confirmation to proceed with purge",
        )
        purge_parser.add_argument(
            "--backup",
            help="Optional backup path (if not provided, default backup location used)",
        )
        purge_parser.add_argument(
            "--no-backup",
            action="store_true",
            help="Skip backup creation even if backups are enabled by default",
        )
        purge_parser.add_argument(
            "--files-only",
            action="store_true",
            help="Only operate on filesystem artifacts, not DB",
        )
        purge_parser.add_argument(
            "--db-only",
            action="store_true",
            help="Only operate on database records, not filesystem artifacts",
        )
        purge_parser.add_argument(
            "--sql-year-filter",
            choices=("auto", "on", "off"),
            default="auto",
            help=(
                "Control SQL-year-filter behavior: 'auto' try SQL then fallback, 'on' force SQL, 'off' force Python filter"
            ),
        )
        purge_parser.add_argument(
            "--force-files",
            action="store_true",
            help="If DB purge fails, proceed with filesystem purge when set (use with caution)",
        )

        args = parser.parse_args()

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
                    args.year, args.max_cases, start=getattr(args, "start", None)
                )
            elif args.command == "probe":
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

                        def check_case_exists(n: int) -> bool:
                            # Build case number using IMM-<n>-<yy> pattern by default
                            try:
                                yy = str(args.year)[-2:]
                                case_number = f"IMM-{n}-{yy}"
                                found = scraper.search_case(case_number)
                                return bool(found)
                            except Exception:
                                return False

                        print("Starting live probe (this will perform HTTP requests).")
                    except Exception as e:
                        print(f"Failed to initialize live scraper for probing: {e}")
                        sys.exit(1)
                else:
                    # Dry-run adapter: warn and create a faux-check that always returns False so
                    # the algorithm will exercise growth behavior without making network calls.
                    def check_case_exists(n: int) -> bool:
                        print(f"[dry-run] would check ID: {n}")
                        return False

                # Run the probe
                # Use the CLI-configured/shared rate limiter for probing/backoff
                rl = getattr(self, "rate_limiter", None) or EthicalRateLimiter(
                    interval_seconds=Config.get_rate_limit_seconds(),
                    backoff_factor=Config.get_backoff_factor(),
                    max_backoff_seconds=Config.get_max_backoff_seconds(),
                )

                upper, probes = BatchService.find_upper_bound(
                    check_case_exists=check_case_exists,
                    start=getattr(args, "start", 1),
                    initial_high=getattr(args, "initial_high", 1000),
                    max_limit=getattr(args, "max_limit", 100000),
                    coarse_step=getattr(args, "coarse_step", 100),
                    refine_range=getattr(args, "refine_range", 200),
                    probe_budget=getattr(args, "probe_budget", 200),
                    rate_limiter=rl,
                )

                print("\nProbe result:")
                print(f"  Approx upper numeric id: {upper}")
                print(f"  Probes used: {probes}")
                # Stop processing after probe results — do not fall through to batch audit/export logic
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
                else:
                    print(f"\nNo cases found for year {args.year}")
                    if self.emergency_stop:
                        print("Emergency stop was triggered during processing")
                    sys.exit(1)

            elif args.command == "stats":
                self.show_stats(args.year)
            elif args.command == "purge":
                # Purge flow: do dry-run first or ask for confirmation
                year = args.year
                dry_run = getattr(args, "dry_run", False)
                no_backup = getattr(args, "no_backup", False)
                backup = getattr(args, "backup", None)
                files_only = getattr(args, "files_only", False)
                db_only = getattr(args, "db_only", False)

                if not dry_run and not args.yes:
                    # Interactive confirmation required
                    resp = input(
                        f"This will permanently delete data for year {year}. Type 'YES' to continue: "
                    )
                    if resp.strip() != "YES":
                        print("Purge cancelled")
                        return

                result = purge_year(
                    year,
                    dry_run=dry_run,
                    backup=backup,
                    no_backup=no_backup,
                    files_only=files_only,
                    db_only=db_only,
                    sql_year_filter=(None if args.sql_year_filter == "auto" else (True if args.sql_year_filter == "on" else False)),
                    force_files=getattr(args, "force_files", False),
                )
                print("Purge summary written to:", result.get("audit_path"))

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
