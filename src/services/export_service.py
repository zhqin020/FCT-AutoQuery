from __future__ import annotations

import json
import os
import re
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.lib.config import Config


_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_case_number(name: str) -> str:
    s = _SANITIZE_RE.sub("-", name or "")
    s = re.sub(r"-+", "-", s).strip("-_")
    return s or "case"


def _unique_with_suffix(path: Path, max_attempts: int = 100) -> Path:
    if not path.exists():
        return path
    base = path.stem
    suffix = path.suffix
    for i in range(1, max_attempts + 1):
        candidate = path.with_name(f"{base}-{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"No available filename after {max_attempts} attempts: {path}")


def export_case_to_json(case: dict, output_root: Optional[str] = None) -> str:
    """Export a case dict to a per-case JSON file.

    Returns the final file path as a string. Raises on persistent failures.
    """
    output_root = output_root or Config.get_output_dir()
    per_case_subdir = Config.get_per_case_subdir()
    retries = Config.get_export_write_retries()
    base_backoff = Config.get_export_write_backoff_seconds()

    # Year directory
    today = datetime.now(timezone.utc)
    year = today.strftime("%Y")
    date_str = today.strftime("%Y%m%d")

    dir_path = Path(output_root) / per_case_subdir / year
    dir_path.mkdir(parents=True, exist_ok=True)

    case_number = case.get("case_number") or case.get("caseId") or "case"
    safe = _sanitize_case_number(case_number)
    base_name = f"{safe}-{date_str}"
    final_path = dir_path / f"{base_name}.json"
    final_path = _unique_with_suffix(final_path)

    tmp_path = None
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(dir_path))
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(case, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, final_path)
            return str(final_path)
        except Exception as exc:  # pragma: no cover - handle filesystem errors
            last_exc = exc
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            if attempt == retries:
                raise
            # Avoid sleeping during local I/O retries to keep local operations
            # high-throughput; immediately retry instead.
            pass

    # Shouldn't reach here
    raise last_exc or RuntimeError("Failed to export case to JSON")
"""Export service for structured data export in CSV, JSON, and database formats."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import re

import psycopg2
from psycopg2.extras import execute_values

from src.lib.config import Config
from src.lib.logging_config import get_logger
from src.lib.year_utils import get_year_pattern
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
        # Respect configured output dir when caller passes default placeholder
        if output_dir == "output":
            output_dir = Config.get_output_dir()
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

    def export_case_to_json(self, case: Case, date_str: Optional[str] = None) -> str:
        """
        Export a single case to a per-case JSON file under `output/json/<YYYY>/`.

        Args:
            case: Case object to export
            date_str: Optional date string to use in filename (YYYYMMDD). If not
                      provided, uses today's date.

        Returns:
            Path to the exported JSON file as string

        Raises:
            Exception on failure
        """
        if not isinstance(case, Case):
            raise ValueError("export_case_to_json requires a Case instance")

        # Determine date for filename
        from datetime import datetime

        if date_str is None:
            # Derive year from the case number when possible. Case numbers are
            # formatted as IMM-<seq>-YY where YY indicates the two-digit year.
            # Prefer this over filing_date to ensure per-case JSON lives under
            # the case-year folder (user expectation).
            year = None
            try:
                cf = getattr(case, "case_number", None) or getattr(case, "case_id", None) or ""
                import re

                m = re.search(r"IMM-\d+-([0-9]{2})$", str(cf))
                if m:
                    yy = int(m.group(1))
                    # assume 2000-based years (e.g. '24' -> 2024)
                    year = 2000 + yy
            except Exception:
                year = None

            if year is None:
                # Fall back to filing_date/scraped_at if present
                date_from_case = None
                try:
                    if getattr(case, "filing_date", None):
                        date_from_case = str(getattr(case, "filing_date"))
                    elif getattr(case, "scraped_at", None):
                        date_from_case = str(getattr(case, "scraped_at"))
                except Exception:
                    date_from_case = None

                if date_from_case:
                    m2 = re.search(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", date_from_case)
                    if m2:
                        date_str = f"{m2.group(1)}{m2.group(2)}{m2.group(3)}"
                        year = int(date_str[:4])
                if year is None:
                    from datetime import datetime

                    date_str = datetime.now().strftime("%Y%m%d")
                    year = int(date_str[:4])
            else:
                # Use January 1st for filename date when deriving from case number
                date_str = f"{year}0101"

        else:
            year = date_str[:4]

        # Build directory: output/<per_case_subdir>/<YYYY>/
        # Use configured subdirectory name for per-case JSON (default 'json')
        per_case_subdir = Config.get_per_case_subdir()
        json_dir = self.output_dir / per_case_subdir / str(year)
        json_dir.mkdir(parents=True, exist_ok=True)

        # Base filename: <case-number>-<YYYYMMDD>.json
        safe_case = getattr(case, "case_number", None) or getattr(case, "case_id", None) or "case"
        # sanitize filename characters
        safe_case = re.sub(r"[^A-Za-z0-9._-]", "_", str(safe_case))
        base_name = f"{safe_case}-{date_str}.json"
        final_path = json_dir / base_name
        # Overwrite existing file with same case/date to avoid leaving stale/incorrect files

        # Atomic write: write to a temp file in same directory then rename
        import tempfile

        max_retries = Config.get_export_write_retries()
        backoff = Config.get_export_write_backoff_seconds()
        attempt = 0
        while True:
            attempt += 1
            try:
                fd, tmp_path = tempfile.mkstemp(dir=str(json_dir), prefix="tmp_", suffix=".json")
                with open(fd, "w", encoding="utf-8") as tf:
                    import json as _json

                    # Build payload from case.to_dict() and include docket_entries
                    payload = case.to_dict()
                    if hasattr(case, "docket_entries") and case.docket_entries:
                        try:
                            payload["docket_entries"] = [
                                e.to_dict() if hasattr(e, "to_dict") else e for e in case.docket_entries
                            ]
                        except Exception:
                            # Fallback: include raw objects if serialization fails
                            payload["docket_entries"] = list(case.docket_entries)

                    _json.dump(payload, tf, indent=2, ensure_ascii=False, default=str)

                # Use os.replace to ensure atomic move
                import os

                os.replace(tmp_path, str(final_path))

                logger.info(f"Exported case {safe_case} to JSON: {final_path}")
                return str(final_path)

            except Exception as e:
                logger.warning(f"Attempt {attempt}: failed to write per-case JSON for {safe_case}: {e}")
                if attempt >= max_retries:
                    logger.error(f"Exceeded max retries ({max_retries}) writing JSON for {safe_case}")
                    raise
                else:
                    # Avoid sleeping during local I/O retries to keep local operations
                    # high-throughput; continue immediately and retry.
                    pass

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
            if not case.case_number:
                raise ValueError(f"Case at index {i} has empty case_id")

            # Validate case_id format (should be IMM-XXXXX-YY)
            if (
                not case.case_number.startswith("IMM-")
                or len(case.case_number.split("-")) != 3
            ):
                logger.warning(
                    f"Case at index {i} has non-standard case_number format: {case.case_number}"
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

    def save_case_to_database(self, case: Case) -> Tuple[str, Optional[str]]:
        """
        Save a single case to the database using UPSERT and return per-case status.

        Args:
            case: Case object to save

        Returns:
            Tuple[str, Optional[str]]: (status, message) where status is one of
            'new', 'updated', or 'failed'. Message contains error details if failed.
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Determine if this is a new case or update
            cursor.execute(
                "SELECT 1 FROM cases WHERE case_number = %s LIMIT 1",
                (case.case_number,),
            )
            exists = cursor.fetchone() is not None

            # UPSERT case data with tracking status
            cursor.execute(
                """
                INSERT INTO cases (
                    case_number, case_type, type_of_action, nature_of_proceeding,
                    filing_date, office, style_of_cause, language, scraped_at,
                    status, last_attempt_at, retry_count, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NULL)
                ON CONFLICT (case_number) DO UPDATE SET
                    case_type = EXCLUDED.case_type,
                    type_of_action = EXCLUDED.type_of_action,
                    nature_of_proceeding = EXCLUDED.nature_of_proceeding,
                    filing_date = EXCLUDED.filing_date,
                    office = EXCLUDED.office,
                    style_of_cause = EXCLUDED.style_of_cause,
                    language = EXCLUDED.language,
                    scraped_at = EXCLUDED.scraped_at,
                    status = EXCLUDED.status,
                    last_attempt_at = EXCLUDED.last_attempt_at,
                    retry_count = 0,
                    error_message = NULL
            """,
                (
                    case.case_number,
                    getattr(case, "case_type", None),
                    getattr(case, "action_type", None),
                    getattr(case, "nature_of_proceeding", None),
                    getattr(case, "filing_date", None),
                    getattr(case, "office", None),
                    getattr(case, "style_of_cause", None),
                    getattr(case, "language", None),
                    datetime.now(),
                    'success',  # 标记为成功采集
                    datetime.now(),  # 记录尝试时间
                ),
            )

            # Save docket entries if they exist
            if hasattr(case, "docket_entries") and case.docket_entries:
                self._save_docket_entries(
                    cursor, case.case_number, case.docket_entries
                )

            conn.commit()
            cursor.close()
            conn.close()

            status = "updated" if exists else "new"
            logger.info(f"Successfully saved case {case.case_number} to database ({status})")
            return status, None

        except Exception as e:
            logger.error(f"Failed to save case {case.case_number} to database: {e}")
            return "failed", str(e)

    def case_exists(self, case_number: str) -> bool:
        """Return True if a case with given `case_number` exists in the database."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM cases WHERE case_number = %s AND status = 'success' LIMIT 1", (case_number,)
            )
            exists = cursor.fetchone() is not None
            cursor.close()
            conn.close()
            return exists
        except Exception as e:
            logger.warning(f"Failed to check existence for {case_number}: {e}")
            return False

    def save_cases_to_database(self, cases: List[Case]) -> Tuple[int, int, List[dict]]:
        """
        Save multiple cases to the database using batch UPSERT.

        Args:
            cases: List of Case objects to save

        Returns:
            Tuple[int, int]: (successful_saves, failed_saves)
        """
        successful = 0
        failed = 0
        per_case = []

        for case in cases:
            status, message = self.save_case_to_database(case)
            per_case.append({"case_number": case.case_number, "status": status, "message": message})
            if status == "failed":
                failed += 1
            else:
                successful += 1

        logger.info(f"Database save complete: {successful} successful, {failed} failed")
        return successful, failed, per_case

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
            INSERT INTO docket_entries (case_number, id_from_table, date_filed, office, recorded_entry_summary)
            VALUES %s
            ON CONFLICT (case_number, id_from_table) DO NOTHING
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
            successful, failed, per_case = self.save_cases_to_database(cases)
            results["database"] = {"successful": successful, "failed": failed}
            results["per_case"] = per_case

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
                WHERE case_number LIKE %s
                ORDER BY case_number
            """,
                (get_year_pattern(year),),
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
