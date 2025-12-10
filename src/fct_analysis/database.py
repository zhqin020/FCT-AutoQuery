"""Database access module for FCT analysis.

Supports reading case data from PostgreSQL database with fallback to file-based input.
"""
from __future__ import annotations

import json
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

import pandas as pd
from psycopg2 import connect, DatabaseError, OperationalError
from psycopg2.extras import RealDictCursor

from lib.config import Config

logger = logging.getLogger(__name__)


class DatabaseReader:
    """Reads case data from PostgreSQL database."""
    
    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        self.db_config = db_config or Config.get_db_config()
        
    def test_connection(self) -> bool:
        """Test database connection."""
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            return True
        except (OperationalError, DatabaseError) as e:
            logger.warning(f"Database connection failed: {e}")
            return False
    
    def fetch_cases(self, year: Optional[int] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch cases from database.
        
        Args:
            year: Filter by case year (extracted from case_number)
            limit: Maximum number of cases to fetch
            
        Returns:
            List of case dictionaries
        """
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Build query
                    query = """
                        SELECT 
                            case_number as case_id,
                            case_number,
                            style_of_cause as title,
                            office as court,
                            case_type,
                            type_of_action as action_type,
                            nature_of_proceeding,
                            filing_date,
                            office,
                            style_of_cause,
                            language,
                            html_content,
                            scraped_at,
                            status,
                            (
                                SELECT jsonb_agg(
                                    jsonb_build_object(
                                        'id', d.id_from_table,
                                        'case_id', d.case_number,
                                        'doc_id', d.id_from_table,
                                        'entry_date', d.date_filed,
                                        'entry_office', d.office,
                                        'summary', d.recorded_entry_summary
                                    )
                                )
                                FROM docket_entries d
                                WHERE d.case_number = c.case_number
                            ) as docket_entries
                        FROM cases c
                        WHERE 1=1
                    """
                    params = []
                    
                    if year:
                        query += " AND EXTRACT(YEAR FROM filing_date) = %s"
                        params.append(year)
                    
                    query += " ORDER BY filing_date DESC"
                    
                    if limit:
                        query += f" LIMIT {limit}"
                    
                    cursor.execute(query, params)
                    results = cursor.fetchall()
                    
                    # Convert RealDictRow to regular dicts
                    cases = [dict(row) for row in results]
                    
                    # Parse docket_entries from JSON if needed
                    for case in cases:
                        if isinstance(case.get('docket_entries'), str):
                            try:
                                case['docket_entries'] = json.loads(case['docket_entries'])
                            except json.JSONDecodeError:
                                case['docket_entries'] = []
                        elif case.get('docket_entries') is None:
                            case['docket_entries'] = []
                    
                    logger.info(f"Fetched {len(cases)} cases from database")
                    return cases
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to fetch cases from database: {e}")
            raise


class FileReader:
    """Reads case data from JSON files with year-based directory structure support."""
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Config.get_analysis_json_path()
        
    def read_directory(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """Read cases from year-based directory structure.
        
        Directory structure:
        output/json/
        ├── 2021/
        │   ├── IMM-1000-21-20210101.json
        │   └── ...
        ├── 2022/
        └── ...
        
        Args:
            year: Filter by specific year directory
            
        Returns:
            List of case dictionaries
        """
        if not self.base_path.exists():
            logger.warning(f"JSON directory not found: {self.base_path}")
            return []
        
        cases = []
        
        # Determine which year directories to process
        if year:
            year_dirs = [self.base_path / str(year)]
            if not year_dirs[0].exists():
                logger.warning(f"Year directory not found: {year_dirs[0]}")
                return []
        else:
            year_dirs = [d for d in self.base_path.iterdir() if d.is_dir() and d.name.isdigit()]
        
        for year_dir in sorted(year_dirs):
            if not year_dir.exists():
                continue
                
            logger.info(f"Reading cases from year directory: {year_dir.name}")
            
            for json_file in sorted(year_dir.glob("*.json")):
                try:
                    with json_file.open('r', encoding='utf-8') as f:
                        case = json.load(f)
                        if isinstance(case, dict):
                            cases.append(case)
                        elif isinstance(case, list):
                            cases.extend(case)
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Failed to read {json_file}: {e}")
                    continue
        
        logger.info(f"Read {len(cases)} cases from JSON files")
        return cases
    
    def read_single_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Read cases from a single JSON file containing array of cases."""
        try:
            with file_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                return [data]
            else:
                logger.error(f"Invalid JSON format in {file_path}")
                return []
                
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return []


def get_data_source(format_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get case data from configured source.
    
    Args:
        format_type: Override for input format ('database', 'directory', 'file')
        
    Returns:
        List of case dictionaries
    """
    format_type = format_type or Config.get_analysis_input_format()
    
    if format_type == "database":
        db_reader = DatabaseReader()
        if db_reader.test_connection():
            return db_reader.fetch_cases()
        else:
            logger.warning("Database not available, falling back to file input")
            format_type = "directory"
    
    if format_type == "directory":
        file_reader = FileReader()
        return file_reader.read_directory()
    
    elif format_type == "file":
        # Fallback to current behavior - expect a single file path
        # This would need to be handled by the calling code
        raise ValueError("File format requires explicit file path")
    
    else:
        raise ValueError(f"Unsupported input format: {format_type}")