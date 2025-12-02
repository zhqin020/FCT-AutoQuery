"""Service for tracking case processing history and status."""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

from src.lib.config import Config
from src.lib.logging_config import get_logger

logger = get_logger()


class CaseTrackingService:
    """Service for tracking case processing history and status in database."""

    def __init__(self):
        self.config = Config()
        self.db_config = self.config.get_db_config()

    def start_run(self, mode: Optional[str] = None, parameters: Optional[Dict] = None, metadata: Optional[Dict] = None, **kwargs) -> str:
        """Start a new processing run and return run_id.
        Accepts both `mode` and `processing_mode` as aliases for backward compatibility.
        """
        # backward compatibility: allow processing_mode kwarg
        processing_mode = kwargs.get('processing_mode')
        if processing_mode and not mode:
            mode = processing_mode
        if not mode:
            mode = 'unknown'

        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + str(hash(str(parameters)))[-6:]
        
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO processing_runs 
                (run_id, started_at, start_time, processing_mode, start_case_number, max_cases, force_mode, config, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'running')
                ON CONFLICT (run_id) DO UPDATE SET
                    started_at = EXCLUDED.started_at,
                    processing_mode = EXCLUDED.processing_mode,
                    start_case_number = EXCLUDED.start_case_number,
                    max_cases = EXCLUDED.max_cases,
                    force_mode = EXCLUDED.force_mode,
                    config = EXCLUDED.config,
                    status = 'running'
            """, (
                run_id,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
                mode,
                parameters.get('start_case_number') if parameters and isinstance(parameters, dict) else None,
                parameters.get('max_cases') if parameters and isinstance(parameters, dict) else None,
                parameters.get('force') if parameters and isinstance(parameters, dict) else False,
                json.dumps(metadata) if metadata else None
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Started new processing run: {run_id} (mode: {mode})")
            return run_id
        except Exception as e:
            # If database is unavailable or the schema isn't set up in tests, continue
            logger.error(f"Failed to start processing run (DB error ignored): {e}")
            return run_id

    def finish_run(self, run_id: str, status: str = 'completed'):
        """Finish a processing run and update statistics."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Calculate statistics
            cursor.execute("""
                UPDATE processing_runs SET 
                    completed_at = %s,
                    status = %s,
                    total_cases_processed = (
                        SELECT COUNT(*) FROM case_processing_history 
                        WHERE run_id = %s
                    ),
                    success_count = (
                        SELECT COUNT(*) FROM case_processing_history 
                        WHERE run_id = %s AND outcome = 'success'
                    ),
                    failed_count = (
                        SELECT COUNT(*) FROM case_processing_history 
                        WHERE run_id = %s AND outcome = 'failed'
                    ),
                    skipped_count = (
                        SELECT COUNT(*) FROM case_processing_history 
                        WHERE run_id = %s AND outcome = 'skipped'
                    ),
                    error_count = (
                        SELECT COUNT(*) FROM case_processing_history 
                        WHERE run_id = %s AND outcome = 'error'
                    )
                WHERE run_id = %s
            """, (
                datetime.now(timezone.utc),
                status,
                run_id, run_id, run_id, run_id, run_id, run_id
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Finished processing run: {run_id} (status: {status})")
            
        except Exception as e:
            logger.error(f"Failed to finish processing run {run_id}: {e}")

    def record_case_processing(
        self,
        court_file_no: str,
        run_id: str,
        outcome: str,
        reason: Optional[str] = None,
        message: Optional[str] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        attempt_count: int = 1,
        scrape_mode: str = 'single',
        processing_mode: Optional[str] = None,
        processing_duration_ms: Optional[int] = None,
        case_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """Record a case processing event."""
        if processing_mode:
            scrape_mode = processing_mode
        if error_message:
            message = error_message
        if started_at is None:
            started_at = datetime.now(timezone.utc)
        if completed_at is None:
            completed_at = datetime.now(timezone.utc)
        
        # Accept processing_duration_ms (int ms) as an alternative input
        if processing_duration_ms is not None:
            duration_seconds = float(processing_duration_ms) / 1000.0
        else:
            duration_seconds = (completed_at - started_at).total_seconds()
        
        # Defensive: ensure run_id is present. Some code paths may call this
        # method without a run id (for example, if the CLI failed to start a
        # run or tests call the method directly). Enforce a fallback to a
        # generated run id so the DB constraint is not violated.
        if not run_id:
            try:
                fallback_run_id = self.start_run(processing_mode=processing_mode or scrape_mode, parameters={}, metadata={'generated_fallback': True})
                logger.warning(f"Missing run_id while recording case {court_file_no}; created fallback run_id: {fallback_run_id}")
                run_id = fallback_run_id
            except Exception as _:
                # As a last resort, generate a timestamp-based run id so at least
                # a non-null string is recorded even if DB inserts fail.
                import time
                run_id = f"fallback_{int(time.time())}"

        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            # Attempt insert; if unique conflict occurs, update existing row instead
            try:
                cursor.execute("""
                    INSERT INTO case_processing_history 
                    (court_file_no, case_number, run_id, outcome, reason, message, case_id,
                     started_at, completed_at, duration_seconds, 
                     attempt_count, scrape_mode, processing_mode, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    court_file_no, court_file_no, run_id, outcome, reason, message, case_id,
                    started_at, completed_at, duration_seconds,
                    attempt_count, scrape_mode, scrape_mode,
                    json.dumps(metadata) if metadata else None
                ))
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                cursor.execute("""
                    UPDATE case_processing_history SET
                        outcome = %s,
                        reason = %s,
                        message = %s,
                        case_id = %s,
                        completed_at = %s,
                        duration_seconds = %s,
                        attempt_count = %s,
                        scrape_mode = %s,
                        processing_mode = %s,
                        metadata = %s
                    WHERE court_file_no = %s AND run_id = %s
                """, (
                    outcome, reason, message, case_id, completed_at, duration_seconds, attempt_count, scrape_mode, scrape_mode, json.dumps(metadata) if metadata else None, court_file_no, run_id
                ))

            # Update case status snapshot (insert or update)
            cursor.execute("""
                INSERT INTO case_status_snapshots 
                (case_number, court_file_no, last_outcome, last_run_id, last_processed_at,
                 consecutive_failures, first_seen_at, last_success_at, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (case_number) DO UPDATE SET
                    last_outcome = EXCLUDED.last_outcome,
                    last_run_id = EXCLUDED.last_run_id,
                    last_processed_at = EXCLUDED.last_processed_at,
                    consecutive_failures = CASE 
                        WHEN EXCLUDED.last_outcome = 'failed' THEN 
                            case_status_snapshots.consecutive_failures + 1
                        ELSE 0
                    END,
                    last_success_at = CASE 
                        WHEN EXCLUDED.last_outcome = 'success' THEN EXCLUDED.last_processed_at
                        ELSE case_status_snapshots.last_success_at
                    END,
                    is_active = EXCLUDED.is_active
            """, (
                    court_file_no, court_file_no, outcome, run_id, completed_at,
                    1 if outcome == 'failed' else 0,
                    started_at,
                    completed_at if outcome == 'success' else None,
                    True
            ))

            # Also update consecutive_no_results for 'no_results' outcomes if DB supports the column.
            # Use a separate update to avoid hard failures if DB schema isn't patched yet.
            try:
                cursor.execute("""
                    UPDATE case_status_snapshots SET
                        consecutive_no_results = CASE
                            WHEN last_outcome = 'no_results' THEN COALESCE(consecutive_no_results, 0) + 1
                            ELSE 0
                        END
                    WHERE court_file_no = %s
                """, (court_file_no,))
            except Exception:
                # Column may not exist on older schema; ignore updating it.
                pass

            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            logger.error(f"Failed to record case processing for {court_file_no}: {e}")

    def get_case_history(self, court_file_no: str, limit: int = 10) -> List[Dict]:
        """Get processing history for a specific case."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT h.*, r.processing_mode as mode, r.status as run_status
                FROM case_processing_history h
                LEFT JOIN processing_runs r ON h.run_id = r.run_id
                WHERE h.court_file_no = %s
                ORDER BY h.started_at DESC
                LIMIT %s
            """, (court_file_no, limit))
            
            results = [dict(row) for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get case history for {court_file_no}: {e}")
            return []

    def get_case_status(self, court_file_no: str) -> Optional[Dict]:
        """Get current status snapshot for a case."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT * FROM case_status_snapshots 
                WHERE court_file_no = %s
            """, (court_file_no,))
            
            row = cursor.fetchone()
            result = dict(row) if row else None
            
            cursor.close()
            conn.close()
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get case status for {court_file_no}: {e}")
            return None

    def _count_recent_no_results(self, court_file_no: str, limit: int = 5) -> int:
        """Count how many of the most recent processing events for a case are 'no_results'.

        This looks at the case_processing_history table in descending order of started_at,
        stopping early when a non-no_results outcome is encountered. It returns the count
        of consecutive 'no_results' at the top of the history.
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT outcome FROM case_processing_history
                WHERE court_file_no = %s
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (court_file_no, limit),
            )
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            count = 0
            for row in rows:
                if row and row[0] == 'no_results':
                    count += 1
                else:
                    break
            return count
        except Exception as e:
            logger.debug(f"Error counting recent no_results for {court_file_no}: {e}")
            return 0

    def should_skip_case(self, court_file_no: str, force: bool = False, 
                        max_consecutive_failures: int = 5) -> Tuple[bool, str]:
        """
        Determine if a case should be skipped based on processing history.
        
        Returns:
            (should_skip, reason)
        """
        if force:
            return False, ""
        
        # Check if case exists in cases table
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 1 FROM cases WHERE court_file_no = %s LIMIT 1
            """, (court_file_no,))
            
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return True, "exists_in_db"
                
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.warning(f"Failed to check case existence for {court_file_no}: {e}")
        
        # Check processing status
        status = self.get_case_status(court_file_no)
        # If snapshot doesn't exist, fall back to computing consecutive no_results
        if not status:
            try:
                safe_no_records = int(self.config.get_safe_stop_no_records())
            except Exception:
                safe_no_records = 3
            try:
                cons_nr = self._count_recent_no_results(court_file_no, safe_no_records)
                if cons_nr >= safe_no_records:
                    return True, f"no_results_repeated ({cons_nr})"
            except Exception:
                pass
        if status:
            if status.get('consecutive_failures', 0) >= max_consecutive_failures:
                return True, f"too_many_failures ({status['consecutive_failures']})"
            
            # New behavior: avoid repeatedly probing cases that repeatedly return `no_results`.
            try:
                safe_no_records = int(self.config.get_safe_stop_no_records())
            except Exception:
                safe_no_records = 3

            # If snapshot has no column for consecutive_no_results, or it's 0,
            # attempt to compute the streak from historical case processing
            # history. This ensures the logic works even if the DB schema
            # migration hasn't been applied yet.
            cons_nr = status.get('consecutive_no_results')
            if not cons_nr:
                try:
                    cons_nr = self._count_recent_no_results(court_file_no, safe_no_records)
                except Exception:
                    cons_nr = 0

            if cons_nr >= safe_no_records:
                return True, f"no_results_repeated ({status.get('consecutive_no_results')})"

            if status.get('last_outcome') == 'success':
                last_success = status.get('last_success_at')
                if last_success:
                    # If successfully processed recently, skip
                    time_since_success = (datetime.now(timezone.utc) - last_success).days
                    if time_since_success < 7:  # Skip if processed within last 7 days
                        return True, f"recently_processed ({time_since_success} days ago)"

                # New behavior: avoid repeatedly probing cases that repeatedly return `no_results`.
                try:
                    safe_no_records = int(self.config.get_safe_stop_no_records())
                except Exception:
                    safe_no_records = 3

                cons_nr2 = status.get('consecutive_no_results')
                if not cons_nr2:
                    try:
                        cons_nr2 = self._count_recent_no_results(court_file_no, safe_no_records)
                    except Exception:
                        cons_nr2 = 0

                if cons_nr2 >= safe_no_records:
                    return True, f"no_results_repeated ({status.get('consecutive_no_results')})"
        
        return False, ""

    def record_probe_state(self, case_number: int, year_part: int, 
                          exists: bool, run_id: Optional[str] = None):
        """Record probe state for a case number."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO probe_state 
                (case_number, year_part, exists, first_checked_at, run_id)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (case_number, year_part) DO UPDATE SET
                    exists = EXCLUDED.exists,
                    last_checked_at = NOW(),
                    run_id = EXCLUDED.run_id
            """, (
                case_number, year_part, exists, 
                datetime.now(timezone.utc), run_id
            ))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to record probe state for {case_number}-{year_part}: {e}")

    def get_probe_state(self, case_number: int, year_part: int) -> Optional[Dict]:
        """Get probe state for a case number."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT * FROM probe_state 
                WHERE case_number = %s AND year_part = %s
            """, (case_number, year_part))
            
            row = cursor.fetchone()
            result = dict(row) if row else None
            
            cursor.close()
            conn.close()
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get probe state for {case_number}-{year_part}: {e}")
            return None

    def get_recent_runs(self, days: int = 7, limit: int = 50) -> List[Dict]:
        """Get recent processing runs."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT * FROM processing_runs 
                WHERE started_at >= NOW() - INTERVAL '%s days'
                ORDER BY started_at DESC
                LIMIT %s
            """, (days, limit))
            
            results = [dict(row) for row in cursor.fetchall()]
            
            cursor.close()
            conn.close()
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get recent runs: {e}")
            return []

    def cleanup_old_records(self, days_to_keep: int = 90):
        """Clean up old processing records."""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            cutoff_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_date = cutoff_date - timedelta(days=days_to_keep)

            # Clean old processing history
            cursor.execute("""
                DELETE FROM case_processing_history 
                WHERE started_at < %s
            """, (cutoff_date,))

            # Clean old runs
            cursor.execute("""
                DELETE FROM processing_runs 
                WHERE started_at < %s
            """, (cutoff_date,))

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"Cleaned up processing records older than {cutoff_date}")

        except Exception as e:
            logger.error(f"Failed to cleanup old records: {e}")
    def purge_year(self, year: int) -> Dict[str, int]:
        """Purge all data for a specific year.

        Args:
            year: The year to purge (e.g., 2023)

        Returns:
            Dict with statistics of what was deleted
        """
        stats = {
            'cases_deleted': 0,
            'history_deleted': 0,
            'snapshots_deleted': 0,
            'runs_deleted': 0
        }
        
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Start transaction
            conn.autocommit = False
            
            # Pattern for case numbers in the specified year
            year_suffix = year % 100
            case_pattern = f"IMM-%-{year_suffix:02d}"
            
            logger.info(f"Purging data for year {year} (pattern: {case_pattern})")
            
            # 1. Delete from case_processing_history
            cursor.execute("""
                DELETE FROM case_processing_history 
                WHERE court_file_no LIKE %s
            """, (case_pattern,))
            stats['history_deleted'] = cursor.rowcount
            
            # 2. Delete from case_status_snapshots
            cursor.execute("""
                DELETE FROM case_status_snapshots 
                WHERE court_file_no LIKE %s
            """, (case_pattern,))
            stats['snapshots_deleted'] = cursor.rowcount
            
            # 3. Delete from processing_runs (runs that only processed cases from this year)
            cursor.execute("""
                DELETE FROM processing_runs 
                WHERE run_id IN (
                    SELECT DISTINCT run_id 
                    FROM case_processing_history 
                    WHERE court_file_no LIKE %s
                )
            """, (case_pattern,))
            stats['runs_deleted'] = cursor.rowcount
            
            # 4. Delete from cases table (main case data)
            cursor.execute("""
                DELETE FROM cases 
                WHERE court_file_no LIKE %s
            """, (case_pattern,))
            stats['cases_deleted'] = cursor.rowcount
            
            # Commit transaction
            conn.commit()
            logger.info(f"Successfully purged year {year}: {stats}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to purge year {year}: {e}")
            if 'conn' in locals():
                conn.rollback()
            raise
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()
    
    def purge_case_number(self, case_number: str) -> bool:
        """
        Purge all data for a specific case number.
        
        Args:
            case_number: The case number to purge
            
        Returns:
            True if successful, False otherwise
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            # Start transaction
            conn.autocommit = False
            
            logger.info(f"Purging data for case {case_number}")
            
            # Delete from all tracking tables
            cursor.execute("DELETE FROM case_processing_history WHERE court_file_no = %s", (case_number,))
            cursor.execute("DELETE FROM case_status_snapshots WHERE court_file_no = %s", (case_number,))
            
            # Delete from main cases table
            cursor.execute("DELETE FROM cases WHERE court_file_no = %s", (case_number,))
            
            # Commit transaction
            conn.commit()
            logger.info(f"Successfully purged case {case_number}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to purge case {case_number}: {e}")
            if 'conn' in locals():
                conn.rollback()
            return False
        finally:
            if 'cursor' in locals():
                cursor.close()
            if 'conn' in locals():
                conn.close()