"""Command-line interface for Federal Court Case Scraper."""

import argparse
import sys
from datetime import datetime
from typing import Optional

from src.lib.config import Config
from src.lib.logging_config import get_logger, setup_logging
from src.models.case import Case
from src.services.case_scraper_service import CaseScraperService
from src.services.export_service import ExportService
from src.services.url_discovery_service import UrlDiscoveryService

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

            # Initialize page
            try:
                self.scraper.initialize_page()
            except Exception as e:
                logger.error(f"Failed to initialize page for scraping: {e}")
                raise

            # Search for the case
            found = self.scraper.search_case(case_number)
            if not found:
                logger.warning(f"Case {case_number} not found")
                self.consecutive_failures += 1
                return None

            # Scrape the case data
            case = self.scraper.scrape_case_data(case_number)

            if case:
                logger.info(f"Successfully scraped case: {case.case_id}")
                self.consecutive_failures = 0  # Reset on success
                return case
            else:
                logger.warning(f"Failed to scrape case: {case_number}")
                self.consecutive_failures += 1
                return None

        except Exception as e:
            logger.error(f"Error scraping case {case_number}: {e}")
            self.consecutive_failures += 1
            return None
        finally:
            # Close the scraper page but keep the scraper object for reuse
            try:
                if self.scraper:
                    self.scraper.close()
            except Exception:
                pass

            # Check for emergency stop
            if self.consecutive_failures >= self.max_consecutive_failures:
                logger.error(
                    f"Emergency stop triggered after {self.consecutive_failures} consecutive failures"
                )
                self.emergency_stop = True

    def scrape_batch_cases(
        self, year: int, max_cases: Optional[int] = None
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

        # Get case numbers to process
        case_numbers = self.discovery.generate_case_numbers_from_last(year, max_cases)
        total_to_process = len(case_numbers)

        print(f"Processing {total_to_process} case numbers for year {year}...")

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

            case = self.scrape_single_case(case_number)
            if case:
                cases.append(case)
                consecutive_failures = 0
                print(f"✓ Successfully scraped case {case.case_id}")
            else:
                consecutive_failures += 1
                print(f"✗ Failed to scrape case {case_number}")

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

        # Global force flag
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-scraping of cases even if they exist in the database",
        )

        # Batch command
        batch_parser = subparsers.add_parser(
            "batch", help="Scrape multiple cases for a year"
        )
        batch_parser.add_argument("year", type=int, help="Year to scrape cases for")
        batch_parser.add_argument(
            "--max-cases", type=int, help="Maximum number of cases to scrape"
        )

        # Stats command
        stats_parser = subparsers.add_parser("stats", help="Show scraping statistics")
        stats_parser.add_argument(
            "--year",
            type=int,
            help="Year to show stats for (shows total if not specified)",
        )

        args = parser.parse_args()

        # Set force flag on CLI object
        if getattr(args, "force", False):
            self.force = True

        if not args.command:
            parser.print_help()
            return

        try:
            if args.command == "single":
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
                    args.year, args.max_cases
                )
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

                    # Write audit file to output/
                    import json
                    from pathlib import Path

                    out_dir = Path("output")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    audit_path = out_dir / f"audit_{timestamp}.json"
                    with audit_path.open("w", encoding="utf-8") as fh:
                        json.dump(audit, fh, indent=2)

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

        except KeyboardInterrupt:
            logger.info("Operation cancelled by user")
            print("\nOperation cancelled")
            sys.exit(1)
        except Exception as e:
            logger.error(f"CLI error: {e}")
            print(f"Error: {e}")
            sys.exit(1)


def main():
    """Main entry point."""
    cli = FederalCourtScraperCLI()
    cli.run()


if __name__ == "__main__":
    main()
