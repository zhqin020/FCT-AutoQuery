"""Export service for structured data export in CSV and JSON formats."""

import json
import csv
import os
from typing import List, Optional
from pathlib import Path
from loguru import logger

from src.models.case import Case


class ExportService:
    """Service for exporting case data to CSV and JSON formats."""

    def __init__(self, output_dir: str = "output"):
        """
        Initialize the export service.

        Args:
            output_dir: Directory to save exported files (default: "output")
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        logger.info(f"ExportService initialized with output directory: {self.output_dir}")

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
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"cases_export_{timestamp}.json"

        file_path = self.output_dir / filename

        try:
            # Convert cases to dictionaries
            case_dicts = [case.to_dict() for case in cases]

            # Write to JSON file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(case_dicts, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Successfully exported {len(cases)} cases to JSON: {file_path}")
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
        if not cases:
            raise ValueError("Cannot export empty case list")

        # Validate cases before export
        self._validate_cases(cases)

        if filename is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"cases_export_{timestamp}.csv"

        file_path = self.output_dir / filename

        try:
            # Write to CSV file
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Write header
                writer.writerow([
                    "case_id", "case_number", "title", "court",
                    "date", "html_content", "scraped_at"
                ])

                # Write data rows
                for case in cases:
                    writer.writerow(case.to_csv_row())

            logger.info(f"Successfully exported {len(cases)} cases to CSV: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Failed to export cases to CSV: {e}")
            raise

    def export_all_formats(self, cases: List[Case], base_filename: Optional[str] = None) -> dict:
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
            csv_path = self.export_to_csv(cases, f"{base_filename}.csv")

            logger.info(f"Successfully exported {len(cases)} cases to both formats")
            return {"json": json_path, "csv": csv_path}

        except Exception as e:
            logger.error(f"Failed to export cases to all formats: {e}")
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
            if not case.case_id:
                raise ValueError(f"Case at index {i} has empty case_id")

            if not case.case_number:
                raise ValueError(f"Case at index {i} has empty case_number")

            if not case.title:
                raise ValueError(f"Case at index {i} has empty title")

            # Validate URL format
            if not case.case_id.startswith("https://www.fct-cf.ca/"):
                logger.warning(f"Case {case.case_number} has non-standard case_id: {case.case_id}")

    def get_export_history(self) -> List[str]:
        """
        Get list of all exported files in the output directory.

        Returns:
            List of exported file paths (JSON and CSV files)
        """
        export_files = []
        for ext in ['*.json', '*.csv']:
            export_files.extend([str(f) for f in self.output_dir.glob(ext)])

        return sorted(export_files)

    def cleanup_old_exports(self, keep_recent: int = 10) -> int:
        """
        Clean up old export files, keeping only the most recent ones.

        Args:
            keep_recent: Number of most recent files to keep (default: 10)

        Returns:
            Number of files deleted
        """
        export_files = []
        for ext in ['*.json', '*.csv']:
            export_files.extend(list(self.output_dir.glob(ext)))

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