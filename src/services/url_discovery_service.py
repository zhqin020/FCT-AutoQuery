"""Case number generation service for Federal Court case scraping."""

from typing import List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from src.lib.config import Config
from src.lib.logging_config import get_logger

logger = get_logger()


class UrlDiscoveryService:
    """Service for generating case numbers and managing scraping progress."""

    def __init__(self, config: Config):
        """Initialize the discovery service.

        Args:
            config: Application configuration
        """
        self.config = config
        self.db_config = Config.get_db_config()

    def get_last_processed_case(self, year: int) -> Optional[str]:
        """Get the last processed case number for a given year.

        Args:
            year: Year to check

        Returns:
            Optional[str]: Last processed case number, or None if none found
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Query for the highest case number in the given year
            cursor.execute(
                """
                SELECT case_number
                FROM cases
                WHERE case_number LIKE %s
                ORDER BY case_number DESC
                LIMIT 1
            """,
                (f"IMM-%-{year % 100:02d}",),
            )

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if result:
                return result["case_number"]
            return None

        except Exception as e:
            logger.error(f"Error querying last processed case for year {year}: {e}")
            return None

    def generate_case_numbers_from_last(
        self, year: int, max_cases: Optional[int] = None
    ) -> List[str]:
        """Generate case numbers starting from the last processed one.

        Args:
            year: Year to generate cases for
            max_cases: Maximum number of case numbers to generate

        Returns:
            List[str]: List of case numbers to process
        """
        last_case = self.get_last_processed_case(year)

        if last_case:
            # Parse the last case number
            try:
                # Format: IMM-XXXXX-YY
                parts = last_case.split("-")
                if len(parts) == 3 and parts[0] == "IMM":
                    last_num = int(parts[1])
                    start_num = last_num + 1
                    logger.info(f"Resuming from case number {last_num} for year {year}")
                else:
                    raise ValueError(f"Invalid case format: {last_case}")
            except (ValueError, IndexError) as e:
                logger.warning(
                    f"Could not parse last case {last_case}: {e}. Starting from 1."
                )
                start_num = 1
        else:
            start_num = 1
            logger.info(f"No previous cases found for year {year}, starting from 1")

        # Generate case numbers
        case_numbers = []
        year_suffix = f"{year % 100:02d}"

        for num in range(start_num, start_num + (max_cases or 1000)):
            case_num = f"IMM-{num}-{year_suffix}"
            case_numbers.append(case_num)

            if max_cases and len(case_numbers) >= max_cases:
                break

        logger.info(
            f"Generated {len(case_numbers)} case numbers starting from {case_numbers[0]}"
        )
        return case_numbers

    def generate_case_numbers_for_year(
        self, year: int, start_num: int = 1, max_cases: Optional[int] = None
    ) -> List[str]:
        """Generate case numbers for a specific year.

        Args:
            year: Year to generate cases for
            start_num: Starting case number
            max_cases: Maximum number of cases to generate

        Returns:
            List[str]: List of case numbers
        """
        case_numbers = []
        year_suffix = f"{year % 100:02d}"

        for num in range(start_num, start_num + (max_cases or 10000)):
            case_num = f"IMM-{num}-{year_suffix}"
            case_numbers.append(case_num)

            if max_cases and len(case_numbers) >= max_cases:
                break

        logger.info(f"Generated {len(case_numbers)} case numbers for year {year}")
        return case_numbers

    def should_skip_year(self, year: int, consecutive_failures: int) -> bool:
        """Determine if a year should be skipped due to consecutive failures.

        Args:
            year: Year to check
            consecutive_failures: Number of consecutive cases with no results

        Returns:
            bool: True if year should be skipped
        """
        # Skip if more than 100 consecutive failures (likely no more cases in this year)
        if consecutive_failures >= 100:
            logger.info(
                f"Skipping year {year} due to {consecutive_failures} consecutive failures"
            )
            return True
        return False

    def mark_case_processed(self, case_id: str) -> None:
        """Mark a case as processed (for resume functionality).

        Note: This is handled by the ExportService when cases are saved,
        but this method can be used for tracking progress.

        Args:
            case_id: Case ID that was processed
        """
        # This could be used to maintain a separate progress table if needed
        logger.debug(f"Case {case_id} marked as processed")

    def get_processing_stats(self, year: int) -> dict:
        """Get processing statistics for a year.

        Args:
            year: Year to get stats for

        Returns:
            dict: Statistics about processed cases
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Count cases for this year
            cursor.execute(
                """
                SELECT COUNT(*) as total_cases,
                       MAX(scraped_at) as last_scraped
                FROM cases
                WHERE case_number LIKE %s
            """,
                (f"IMM-%-{year % 100:02d}",),
            )

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            return {
                "year": year,
                "total_cases": result["total_cases"] if result else 0,
                "last_scraped": result["last_scraped"] if result else None,
            }

        except Exception as e:
            logger.error(f"Error getting processing stats for year {year}: {e}")
            return {
                "year": year,
                "total_cases": 0,
                "last_scraped": None,
                "error": str(e),
            }
