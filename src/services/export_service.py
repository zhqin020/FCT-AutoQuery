"""Export service for structured data export in CSV, JSON, and database formats."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import psycopg2
from psycopg2.extras import execute_values

from src.lib.config import Config
from src.lib.logging_config import get_logger
from src.models.case import Case
from src.models.docket_entry import DocketEntry

logger = get_logger()


class ExportService:
    """Service for exporting case data to CSV, JSON, and database formats."""

    def __init__(self, config: Config, output_dir: str = "output"):
        """
        Initialize the export service.

        Args:
            config: Application configuration
            output_dir: Directory to save exported files (default: "output")
        """
        self.config = config
        self.db_config = Config.get_db_config()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"ExportService initialized with output directory: {self.output_dir}"
        )

    def export_to_json(self, cases: List[Case], filename: Optional[str] = None) -> str:
        """
        Export cases to JSON format.

        Args:
            cases: List of Case objects to export
            filename: Optional filename (default: auto-generated with timestamp)

        Returns:
            Path to the exported JSON file

        Raises:
            ValueError: If cases list is empty or contains invalid data
        """
        if not cases:
            raise ValueError("Cannot export empty case list")

        # Validate cases before export
        self._validate_cases(cases)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"cases_export_{timestamp}.json"

        file_path = self.output_dir / filename

        try:
            # Convert cases to dictionaries
            case_dicts = [case.to_dict() for case in cases]

            # Write to JSON file
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(case_dicts, f, indent=2, ensure_ascii=False, default=str)

            logger.info(
                f"Successfully exported {len(cases)} cases to JSON: {file_path}"
            )
            return str(file_path)

        except Exception as e:
            logger.error(f"Failed to export cases to JSON: {e}")
            raise

    def export_to_csv(self, cases: List[Case], filename: Optional[str] = None) -> str:
        """
        Export cases to CSV format.

        Args:
            cases: List of Case objects to export
            filename: Optional filename (default: auto-generated with timestamp)

        Returns:
            Path to the exported CSV file

        Raises:
            ValueError: If cases list is empty or contains invalid data
        """
        raise AttributeError("CSV export removed; use JSON export only")

    def export_all_formats(
        self, cases: List[Case], base_filename: Optional[str] = None
    ) -> dict:
        """
        Export cases to both JSON and CSV formats.

        Args:
            cases: List of Case objects to export
            base_filename: Optional base filename (timestamp will be added)

        Returns:
            Dictionary with paths to exported files:
            {"json": json_file_path, "csv": csv_file_path}

        Raises:
            ValueError: If cases list is empty or contains invalid data
        """
        if not cases:
            raise ValueError("Cannot export empty case list")

        if base_filename is None:
            from datetime import datetime

            base_filename = f"cases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        try:
            json_path = self.export_to_json(cases, f"{base_filename}.json")
            logger.info(f"Exported {len(cases)} cases to JSON")
            return {"json": json_path}

        except Exception as e:
            logger.error(f"Failed to export cases to JSON: {e}")
            raise

    def _validate_cases(self, cases: List[Case]) -> None:
        """
        Validate cases before export.

        Args:
            cases: List of Case objects to validate

        Raises:
            ValueError: If any case is invalid
        """
        for i, case in enumerate(cases):
            if not isinstance(case, Case):
                raise ValueError(f"Case at index {i} is not a Case instance")

            # Check required fields
            if not case.court_file_no:
                raise ValueError(f"Case at index {i} has empty case_id")

            # Validate case_id format (should be IMM-XXXXX-YY)
            if (
                not case.court_file_no.startswith("IMM-")
                or len(case.court_file_no.split("-")) != 3
            ):
                logger.warning(
                    f"Case at index {i} has non-standard court_file_no format: {case.court_file_no}"
                )

    def get_export_history(self) -> List[str]:
        """
        Get list of all exported files in the output directory.

        Returns:
            List of exported file paths (JSON and CSV files)
        """
        export_files = [str(f) for f in self.output_dir.glob("*.json")]
        return sorted(export_files)

    def cleanup_old_exports(self, keep_recent: int = 10) -> int:
        """
        Clean up old export files, keeping only the most recent ones.

        Args:
            keep_recent: Number of most recent files to keep (default: 10)

        Returns:
            Number of files deleted
        """
        export_files = list(self.output_dir.glob("*.json"))

        # Sort by modification time (newest first)
        export_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # Keep only the most recent files
        files_to_delete = export_files[keep_recent:]

        deleted_count = 0
        for file_path in files_to_delete:
            try:
                file_path.unlink()
                logger.info(f"Deleted old export file: {file_path}")
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete {file_path}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old export files")

        return deleted_count

    def save_case_to_database(self, case: Case) -> bool:
        """
        Save a single case to the database using UPSERT.

        Args:
            case: Case object to save

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # UPSERT case data
            cursor.execute(
                """
                INSERT INTO cases (
                    court_file_no, case_type, type_of_action, nature_of_proceeding,
                    filing_date, office, style_of_cause, language, scraped_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (court_file_no) DO UPDATE SET
                    case_type = EXCLUDED.case_type,
                    type_of_action = EXCLUDED.type_of_action,
                    nature_of_proceeding = EXCLUDED.nature_of_proceeding,
                    filing_date = EXCLUDED.filing_date,
                    office = EXCLUDED.office,
                    style_of_cause = EXCLUDED.style_of_cause,
                    language = EXCLUDED.language,
                    scraped_at = EXCLUDED.scraped_at
            """,
                (
                    case.court_file_no,
                    getattr(case, "case_type", None),
                    getattr(case, "action_type", None),
                    getattr(case, "nature_of_proceeding", None),
                    getattr(case, "filing_date", None),
                    getattr(case, "office", None),
                    getattr(case, "style_of_cause", None),
                    getattr(case, "language", None),
                    datetime.now(),
                ),
            )

            # Save docket entries if they exist
            if hasattr(case, "docket_entries") and case.docket_entries:
                self._save_docket_entries(
                    cursor, case.court_file_no, case.docket_entries
                )

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"Successfully saved case {case.court_file_no} to database")
            return True

        except Exception as e:
            logger.error(f"Failed to save case {case.court_file_no} to database: {e}")
            return False

    def case_exists(self, court_file_no: str) -> bool:
        """Return True if a case with given `court_file_no` exists in the database."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM cases WHERE court_file_no = %s LIMIT 1", (court_file_no,)
            )
            exists = cursor.fetchone() is not None
            cursor.close()
            conn.close()
            return exists
        except Exception as e:
            logger.warning(f"Failed to check existence for {court_file_no}: {e}")
            return False

    def save_cases_to_database(self, cases: List[Case]) -> Tuple[int, int]:
        """
        Save multiple cases to the database using batch UPSERT.

        Args:
            cases: List of Case objects to save

        Returns:
            Tuple[int, int]: (successful_saves, failed_saves)
        """
        successful = 0
        failed = 0

        for case in cases:
            if self.save_case_to_database(case):
                successful += 1
            else:
                failed += 1

        logger.info(f"Database save complete: {successful} successful, {failed} failed")
        return successful, failed

    def _save_docket_entries(
        self, cursor, case_id: str, docket_entries: List[DocketEntry]
    ) -> None:
        """
        Save docket entries for a case.

        Args:
            cursor: Database cursor
            case_id: Case ID
            docket_entries: List of docket entries
        """
        if not docket_entries:
            return

        # Prepare data for batch insert
        entries_data = []
        for entry in docket_entries:
            entries_data.append(
                (
                    case_id,
                    entry.doc_id,
                    entry.entry_date,
                    entry.entry_office,
                    entry.summary,
                )
            )

        # Batch insert with ON CONFLICT DO NOTHING (since docket entries are immutable)
        execute_values(
            cursor,
            """
            INSERT INTO docket_entries (court_file_no, id_from_table, date_filed, office, recorded_entry_summary)
            VALUES %s
            ON CONFLICT (court_file_no, id_from_table) DO NOTHING
        """,
            entries_data,
        )

        logger.debug(f"Saved {len(docket_entries)} docket entries for case {case_id}")

    def export_and_save(
        self, cases: List[Case], base_filename: Optional[str] = None
    ) -> dict:
        """
        Export cases to files and save to database.

        Args:
            cases: List of Case objects to export and save
            base_filename: Optional base filename for files

        Returns:
            Dictionary with export results
        """
        results = {}

        try:
            # Export to files
            file_results = self.export_all_formats(cases, base_filename)
            results.update(file_results)

            # Save to database
            successful, failed = self.save_cases_to_database(cases)
            results["database"] = {"successful": successful, "failed": failed}

            logger.info(f"Export and save complete for {len(cases)} cases")
            return results

        except Exception as e:
            logger.error(f"Failed to export and save cases: {e}")
            results["error"] = str(e)
            return results

    def get_case_count_from_database(self) -> int:
        """
        Get total number of cases in the database.

        Returns:
            int: Number of cases
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM cases")
            count = cursor.fetchone()[0]

            cursor.close()
            conn.close()

            return count

        except Exception as e:
            logger.error(f"Failed to get case count from database: {e}")
            return 0

    def get_cases_by_year_from_database(self, year: int) -> List[dict]:
        """
        Get all cases for a specific year from the database.

        Args:
            year: Year to query

        Returns:
            List[dict]: List of case dictionaries
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM cases
                WHERE court_file_no LIKE %s
                ORDER BY court_file_no
            """,
                (f"IMM-%-{year % 100:02d}",),
            )

            columns = [desc[0] for desc in cursor.description]
            cases = [dict(zip(columns, row)) for row in cursor.fetchall()]

            cursor.close()
            conn.close()

            logger.info(f"Retrieved {len(cases)} cases for year {year}")
            return cases

        except Exception as e:
            logger.error(f"Failed to get cases for year {year}: {e}")
            return []
