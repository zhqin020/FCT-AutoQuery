"""Database schema and migration utilities for FCT analysis.

Provides table definitions and migration scripts to support analysis result storage.
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List, Optional
from psycopg2 import connect, DatabaseError, OperationalError
from psycopg2.extras import RealDictCursor

from lib.config import Config

logger = logging.getLogger(__name__)


class AnalysisDBManager:
    """Manages database schema for analysis results."""
    
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
    
    def create_analysis_table(self) -> bool:
        """Create dedicated analysis table to store case analysis results."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS case_analysis (
            id SERIAL PRIMARY KEY,
            case_id VARCHAR(50) NOT NULL,
            case_number VARCHAR(50),
            title TEXT,
            court VARCHAR(100),
            filing_date DATE,
            year INTEGER,  -- Extracted from case_number (e.g., IMM-123-25 -> 2025)
            
            -- Analysis results
            case_type VARCHAR(50),
            case_status VARCHAR(50),
            visa_office VARCHAR(200),
            judge VARCHAR(200),
            
            -- Duration metrics
            time_to_close INTEGER,
            age_of_case INTEGER,
            rule9_wait INTEGER,
            outcome_date DATE,
            memo_response_time INTEGER,
            memo_to_outcome_time INTEGER,
            reply_memo_time INTEGER,
            reply_to_outcome_time INTEGER,
            -- DOJ and applicant memo dates
            doj_memo_date DATE,
            reply_memo_date DATE,
            has_hearing BOOLEAN,
            
            -- Analysis metadata
            analysis_mode VARCHAR(20) NOT NULL DEFAULT 'rule',
            analysis_version VARCHAR(20) DEFAULT '1.0',
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            analysis_data JSONB,  -- Store additional analysis data including docket_entries
            
            -- Foreign key reference (optional, for data consistency)
            -- Can be populated if original case_number exists in cases table
            original_case_id VARCHAR(50),
            
            -- Constraints and indexes
            CONSTRAINT case_analysis_unique UNIQUE (case_id, analysis_mode),
            CONSTRAINT case_analysis_check 
                CHECK (analysis_mode IN ('rule', 'llm', 'smart'))
        )
        """
        
        index_sql = [
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_case_id ON case_analysis(case_id)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_mode ON case_analysis(analysis_mode)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_type ON case_analysis(case_type)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_status ON case_analysis(case_status)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_visa_office ON case_analysis(visa_office)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_analyzed_at ON case_analysis(analyzed_at)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_filing_date ON case_analysis(filing_date)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_year ON case_analysis(year)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_reply_memo_time ON case_analysis(reply_memo_time)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_dojo_memo_date ON case_analysis(doj_memo_date)",
            "CREATE INDEX IF NOT EXISTS idx_case_analysis_reply_memo_date ON case_analysis(reply_memo_date)"
        ]
        
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Create main table
                    cursor.execute(create_table_sql)
                    
                    # Create indexes
                    for sql in index_sql:
                        cursor.execute(sql)
                    
                    conn.commit()
                    logger.info("Case analysis table created successfully")
                    return True
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to create analysis table: {e}")
            return False
    
    def copy_cases_to_analysis_table(self, batch_size: int = 1000) -> bool:
        """Copy cases from original table to analysis table for preparation.
        
        Args:
            batch_size: Number of cases to copy in each batch
            
        Returns:
            True if copy was successful
        """
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Check if analysis table needs population
                    cursor.execute("SELECT COUNT(*) FROM case_analysis")
                    analysis_count = cursor.fetchone()[0]
                    
                    if analysis_count > 0:
                        logger.info(f"Analysis table already has {analysis_count} records, skipping copy")
                        return True
                    
                    # Get total cases to copy (cases with docket entries)
                    cursor.execute("""
                        SELECT COUNT(DISTINCT c.case_number) 
                        FROM cases c
                        INNER JOIN docket_entries d ON c.case_number = d.case_number
                    """)
                    total_cases = cursor.fetchone()[0]
                    
                    if total_cases == 0:
                        logger.warning("No cases with docket entries found to copy")
                        return True
                    
                    logger.info(f"Copying {total_cases} cases with docket entries to analysis table...")
                    
                    # Copy cases in batches
                    offset = 0
                    copied = 0
                    
                    while copied < total_cases:
                        copy_sql = """
                        INSERT INTO case_analysis 
                        (case_id, case_number, title, court, filing_date, year,
                         original_case_id, analysis_data, analysis_mode)
                        SELECT DISTINCT
                            c.case_number, c.case_number, c.style_of_cause, c.office, c.filing_date, c.year,
                            c.case_number, jsonb_build_object(
                                'case_type', c.case_type,
                                'type_of_action', c.type_of_action,
                                'nature_of_proceeding', c.nature_of_proceeding,
                                'language', c.language,
                                'html_content', c.html_content,
                                'scraped_at', c.scraped_at,
                                'status', c.status,
                                'docket_entries', (
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
                                )
                            ), 'rule' as analysis_mode
                        FROM cases c
                        INNER JOIN docket_entries d ON c.case_number = d.case_number
                        WHERE c.case_number NOT IN (
                            SELECT DISTINCT case_id FROM case_analysis
                        )
                        ORDER BY c.case_number
                        LIMIT %s
                        ON CONFLICT (case_id, analysis_mode) DO NOTHING
                        """
                        
                        cursor.execute(copy_sql, (batch_size,))
                        batch_copied = cursor.rowcount
                        copied += batch_copied
                        
                        conn.commit()
                        logger.info(f"Copied {copied}/{total_cases} cases...")
                        
                        if batch_copied == 0:
                            break
                    
                    logger.info(f"Successfully copied {copied} cases to analysis table")
                    return True
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to copy cases to analysis table: {e}")
            return False
            
    def clear_analysis_by_year(self, year: int) -> bool:
        """Clear analysis results for a specific year from the analysis table.
        
        Args:
            year: Year to clear (extracted from case_number suffix)
            
        Returns:
            True if clear was successful
        """
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Clear cases for specific year using case_id suffix (format: -YY)
                    # Note: case_id in case_analysis usually matches case_number (e.g., IMM-1234-25)
                    year_suffix = f"-{year % 100:02d}"
                    delete_sql = """
                    DELETE FROM case_analysis 
                    WHERE case_id LIKE %s OR case_number LIKE %s
                    """
                    pattern = f"%{year_suffix}"
                    cursor.execute(delete_sql, (pattern, pattern))
                    deleted_count = cursor.rowcount
                    conn.commit()
                    logger.info(f"Successfully cleared {deleted_count} analysis records for year {year} (suffix {year_suffix})")
                    return True
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to clear analysis results for year {year}: {e}")
            return False
    
    def check_analysis_table(self) -> Dict[str, bool]:
        """Check if analysis table and required columns exist."""
        required_columns = [
            'id', 'case_id', 'case_type', 'case_status', 'visa_office', 'judge',
            'analysis_mode', 'analyzed_at', 'analysis_version',
            'time_to_close', 'age_of_case', 'rule9_wait', 'outcome_date',
            'memo_response_time', 'memo_to_outcome_time', 'reply_memo_time', 
            'reply_to_outcome_time', 'doj_memo_date', 'reply_memo_date'
            'reply_to_outcome_time', 'doj_memo_date', 'reply_memo_date'
        ]
        
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Check if table exists
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'case_analysis' 
                            AND table_schema = 'public'
                        )
                    """)
                    table_exists = cursor.fetchone()[0]
                    
                    if not table_exists:
                        return {col: False for col in required_columns}
                    
                    # Get table columns
                    cursor.execute("""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = 'case_analysis' 
                        AND table_schema = 'public'
                    """)
                    existing_columns = {row[0] for row in cursor.fetchall()}
                    
                    result = {}
                    for col in required_columns:
                        result[col] = col in existing_columns
                    
                    result['table_exists'] = True
                    return result
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to check analysis table: {e}")
            result = {col: False for col in required_columns}
            result['table_exists'] = False
            return result
    
    def migrate_database(self, copy_cases: bool = True) -> bool:
        """Perform database migration to support analysis results.
        
        Args:
            copy_cases: Whether to copy existing cases to analysis table
            
        Returns:
            True if migration was successful
        """
        if not self.test_connection():
            logger.error("Cannot migrate database: connection failed")
            return False
        
        # Add year field to cases table
        logger.info("Adding year field to cases table...")
        if not self._add_year_to_cases_table():
            return False
        
        # Check current schema
        schema_status = self.check_analysis_table()
        
        if not schema_status.get('table_exists', False):
            logger.info("Creating analysis table...")
            if not self.create_analysis_table():
                return False
        else:
            # Apply schema updates to existing table
            logger.info("Updating existing analysis table schema...")
            self._update_table_schema()
        
        # Copy existing cases if requested
        if copy_cases:
            logger.info("Copying existing cases to analysis table...")
            if not self.copy_cases_to_analysis_table():
                return False
        
        logger.info("Database migration completed successfully")
        return True
    
    def _update_table_schema(self) -> bool:
        """Update existing table schema with longer field lengths."""
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Update varchar field lengths
                    updates = [
                        "ALTER TABLE case_analysis ALTER COLUMN visa_office TYPE VARCHAR(200)",
                        "ALTER TABLE case_analysis ALTER COLUMN judge TYPE VARCHAR(200)",
                        # Add new duration fields if they don't exist
                        "ALTER TABLE case_analysis ADD COLUMN IF NOT EXISTS memo_response_time INTEGER",
                        "ALTER TABLE case_analysis ADD COLUMN IF NOT EXISTS memo_to_outcome_time INTEGER", 
                        "ALTER TABLE case_analysis ADD COLUMN IF NOT EXISTS reply_memo_time INTEGER",
                        "ALTER TABLE case_analysis ADD COLUMN IF NOT EXISTS reply_to_outcome_time INTEGER",
                        "ALTER TABLE case_analysis ADD COLUMN IF NOT EXISTS doj_memo_date DATE",
                        "ALTER TABLE case_analysis ADD COLUMN IF NOT EXISTS reply_memo_date DATE",
                        "ALTER TABLE case_analysis ADD COLUMN IF NOT EXISTS has_hearing BOOLEAN",
                        "ALTER TABLE case_analysis ADD COLUMN IF NOT EXISTS year INTEGER",
                    ]
                    
                    for sql in updates:
                        try:
                            cursor.execute(sql)
                            logger.info(f"Applied schema update: {sql}")
                        except DatabaseError as e:
                            # Column might already have the correct length or other issues
                            if "already exists" in str(e) or "does not exist" in str(e):
                                logger.info(f"Schema update skipped: {e}")
                            else:
                                logger.warning(f"Schema update failed: {e}")
                    
                    conn.commit()
                    return True
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to update table schema: {e}")
            return False
    
    def _add_year_to_cases_table(self) -> bool:
        """Add year field to cases table and populate it from case_number."""
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Add year column if it doesn't exist
                    cursor.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS year INTEGER")
                    logger.info("Added year column to cases table")
                    
                    # Create index on year field
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cases_year ON cases(year)")
                    logger.info("Created index on cases.year")
                    
                    # Populate year field from case_number
                    # Case number format: IMM-123-25 (where 25 represents 2025)
                    cursor.execute("""
                        UPDATE cases 
                        SET year = 2000 + CAST(SPLIT_PART(case_number, '-', 3) AS INTEGER)
                        WHERE year IS NULL 
                        AND case_number ~ '^[A-Z]+-[0-9]+-[0-9]{2}$'
                    """)
                    
                    updated_rows = cursor.rowcount
                    logger.info(f"Populated year field for {updated_rows} cases")
                    
                    conn.commit()
                    return True
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to add year field to cases table: {e}")
            return False


class AnalysisResultStorage:
    """Stores and retrieves analysis results from the dedicated analysis table."""
    
    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        self.db_config = db_config or Config.get_db_config()
    
    def is_analyzed(self, case_id: str, mode: str) -> Optional[Dict[str, Any]]:
        """Check if case has been analyzed with specified mode.
        
        Args:
            case_id: Case identifier
            mode: Analysis mode ('rule' or 'llm')
            
        Returns:
            Analysis result dict if analyzed, None otherwise
        """
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT case_type, case_status, visa_office, judge,
                               analysis_mode, analyzed_at, analysis_version,
                               time_to_close, age_of_case, rule9_wait, outcome_date,
                               memo_response_time, memo_to_outcome_time, reply_memo_time,
                               reply_to_outcome_time, doj_memo_date, reply_memo_date,
                               analysis_data, title, court, filing_date
                        FROM case_analysis 
                        WHERE case_id = %s AND analysis_mode = %s
                    """, (case_id, mode))
                    
                    result = cursor.fetchone()
                    return dict(result) if result else None
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to check analysis status for {case_id}: {e}")
            return None
    
    def save_analysis_result(self, case_id: str, analysis_result: Dict[str, Any], 
                           mode: str, version: str = "1.0") -> bool:
        """Save analysis result to the dedicated analysis table.
        
        Args:
            case_id: Case identifier
            analysis_result: Dictionary containing analysis results
            mode: Analysis mode ('rule' or 'llm')
            version: Analysis version for tracking
            
        Returns:
            True if saved successfully
        """
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    # Prepare fields for upsert with length limits
                    field_mapping = {
                        'type': ('case_type', 50),
                        'status': ('case_status', 50),
                        'visa_office': ('visa_office', 200),
                        'judge': ('judge', 200),
                        'time_to_close': ('time_to_close', None),
                        'age_of_case': ('age_of_case', None),
                        'rule9_wait': ('rule9_wait', None),
                        'outcome_date': ('outcome_date', None),
                        'memo_response_time': ('memo_response_time', None),
                        'memo_to_outcome_time': ('memo_to_outcome_time', None),
                        'reply_memo_time': ('reply_memo_time', None),
                        'reply_to_outcome_time': ('reply_to_outcome_time', None),
                        'doj_memo_date': ('doj_memo_date', None),
                        'reply_memo_date': ('reply_memo_date', None),
                        'title': ('title', None),
                        'court': ('court', 100),
                        'filing_date': ('filing_date', None),
                        'has_hearing': ('has_hearing', None)
                    }
                    
                    # Build INSERT and UPDATE clauses
                    insert_fields = ['case_id', 'analysis_mode', 'analysis_version']
                    insert_values = [case_id, mode, version]
                    update_fields = ['analysis_version = EXCLUDED.analysis_version', 
                                    'analyzed_at = CURRENT_TIMESTAMP']
                    
                    for field_name, (db_field, max_length) in field_mapping.items():
                        if field_name in analysis_result and analysis_result[field_name] is not None:
                            value = analysis_result[field_name]
                            
                            # Truncate string values to prevent database errors
                            if max_length and isinstance(value, str) and len(value) > max_length:
                                value = value[:max_length]
                                logger.debug(f"Truncated {field_name} for case {case_id} to {max_length} characters")
                            
                            insert_fields.append(db_field)
                            insert_values.append(value)
                            update_fields.append(f"{db_field} = EXCLUDED.{db_field}")
                    
                    # Store additional analysis data as JSON
                    analysis_data = {k: v for k, v in analysis_result.items() 
                                   if k not in field_mapping}
                    if analysis_data:
                        insert_fields.append('analysis_data')
                        insert_values.append(json.dumps(analysis_data))
                        update_fields.append('analysis_data = EXCLUDED.analysis_data')
                    
                    # Build UPSERT query
                    placeholders = ', '.join(['%s'] * len(insert_values))
                    sql = f"""
                        INSERT INTO case_analysis ({', '.join(insert_fields)})
                        VALUES ({placeholders})
                        ON CONFLICT (case_id, analysis_mode) 
                        DO UPDATE SET {', '.join(update_fields)}
                    """
                    
                    cursor.execute(sql, insert_values)
                    conn.commit()
                    
                    logger.debug(f"Saved analysis result for case {case_id} (mode: {mode})")
                    return True
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to save analysis result for {case_id}: {e}")
            return False
    
    def get_analyzed_cases(self, mode: Optional[str] = None, 
                          limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve analyzed cases from the analysis table.
        
        Args:
            mode: Filter by analysis mode (optional)
            limit: Maximum number of cases to return (optional)
            
        Returns:
            List of analyzed case dictionaries
        """
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    sql = """
                        SELECT case_id, case_number, title, court, filing_date,
                               case_type, case_status, visa_office, judge,
                               analysis_mode, analyzed_at, analysis_version,
                               time_to_close, age_of_case, rule9_wait, outcome_date,
                               analysis_data
                        FROM case_analysis 
                        WHERE case_type IS NOT NULL OR case_status IS NOT NULL
                    """
                    
                    params = []
                    if mode:
                        sql += " AND analysis_mode = %s"
                        params.append(mode)
                    
                    sql += " ORDER BY analyzed_at DESC"
                    
                    if limit:
                        sql += f" LIMIT {limit}"
                    
                    cursor.execute(sql, params)
                    results = cursor.fetchall()
                    
                    return [dict(row) for row in results]
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to retrieve analyzed cases: {e}")
            return []
    
    def get_analysis_statistics(self) -> Dict[str, Any]:
        """Get overall analysis statistics from the analysis table."""
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    # Overall statistics
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_cases,
                            COUNT(CASE WHEN case_type = 'Mandamus' THEN 1 END) as mandamus_cases,
                            COUNT(CASE WHEN case_type = 'Other' THEN 1 END) as other_cases,
                            COUNT(CASE WHEN case_status = 'Discontinued' THEN 1 END) as discontinued_cases,
                            COUNT(CASE WHEN case_status = 'Granted' THEN 1 END) as granted_cases,
                            COUNT(CASE WHEN case_status = 'Dismissed' THEN 1 END) as dismissed_cases,
                            COUNT(CASE WHEN case_status = 'Ongoing' THEN 1 END) as ongoing_cases,
                            COUNT(CASE WHEN analyzed_at IS NOT NULL THEN 1 END) as analyzed_cases
                        FROM case_analysis
                    """)
                    
                    overall = dict(cursor.fetchone())
                    
                    # Mode-specific statistics
                    cursor.execute("""
                        SELECT 
                            analysis_mode,
                            COUNT(*) as count,
                            AVG(time_to_close) as avg_time_to_close,
                            AVG(age_of_case) as avg_age_of_case
                        FROM case_analysis 
                        WHERE case_type IS NOT NULL
                        GROUP BY analysis_mode
                    """)
                    
                    by_mode = [dict(row) for row in cursor.fetchall()]
                    
                    # Visa office statistics
                    cursor.execute("""
                        SELECT 
                            visa_office,
                            COUNT(*) as count,
                            AVG(time_to_close) as avg_time_to_close,
                            AVG(age_of_case) as avg_age_of_case
                        FROM case_analysis 
                        WHERE visa_office IS NOT NULL AND visa_office != ''
                        GROUP BY visa_office
                        ORDER BY count DESC
                        LIMIT 20
                    """)
                    
                    by_visa_office = [dict(row) for row in cursor.fetchall()]
                    
                    return {
                        'overall': overall,
                        'by_mode': by_mode,
                        'by_visa_office': by_visa_office
                    }
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to get analysis statistics: {e}")
            return {'overall': {}, 'by_mode': [], 'by_visa_office': []}
    
    def get_cases_for_analysis(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get cases that need analysis from the analysis table.
        
        Args:
            limit: Maximum number of cases to return (optional)
            
        Returns:
            List of cases that need analysis
        """
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    sql = """
                        SELECT case_id, case_number, title, court, filing_date,
                               analysis_data, original_case_id
                        FROM case_analysis 
                        WHERE case_type IS NULL AND case_status IS NULL
                        ORDER BY filing_date DESC
                    """
                    
                    if limit:
                        sql += f" LIMIT {limit}"
                    
                    cursor.execute(sql)
                    results = cursor.fetchall()
                    
                    return [dict(row) for row in results]
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to get cases for analysis: {e}")
            return []
    
    def add_case_from_original(self, original_case: Dict[str, Any]) -> bool:
        """Add a case from the original cases table to the analysis table.
        
        Args:
            original_case: Case data from original table
            
        Returns:
            True if added successfully
        """
        try:
            with connect(**self.db_config) as conn:
                with conn.cursor() as cursor:
                    sql = """
                        INSERT INTO case_analysis 
                        (case_id, case_number, title, court, filing_date, 
                         original_case_id, analysis_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (case_id, analysis_mode) DO NOTHING
                    """
                    
                    values = [
                        original_case.get('case_id'),
                        original_case.get('case_number'),
                        original_case.get('title'),
                        original_case.get('court'),
                        original_case.get('filing_date'),
                        original_case.get('case_id'),
                        json.dumps({k: v for k, v in original_case.items() 
                                  if k not in ['case_id', 'case_number', 'title', 'court', 'filing_date']})
                    ]
                    
                    cursor.execute(sql, values)
                    conn.commit()
                    
                    return True
                    
        except (OperationalError, DatabaseError) as e:
            logger.error(f"Failed to add case to analysis table: {e}")
            return False