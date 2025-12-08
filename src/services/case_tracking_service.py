"""Service for tracking case processing history and status."""

import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
import psycopg2
try:
    from psycopg2.extras import RealDictCursor
except Exception:
    # Tests or environments may not have psycopg2 extras available. Provide a
    # lightweight fallback to ensure imports succeed during unit tests.
    class RealDictCursor(object):
        pass

from src.lib.config import Config
from src.lib.case_utils import canonicalize_case_number
from src.lib.logging_config import get_logger
from src.services.purge_service import delete_docket_entries_by_case_pattern

logger = get_logger()


class CaseTrackingService:
    """Service for tracking case processing history and status using only cases table."""

    def __init__(self):
        self.config = Config()
        self.db_config = self.config.get_db_config()

    def start_run(self, mode: Optional[str] = None, parameters: Optional[Dict] = None, metadata: Optional[Dict] = None, **kwargs) -> str:
        """Start a new processing run and return run_id.
        Simplified version that only generates run_id without DB storage.
        """
        # backward compatibility: allow processing_mode kwarg
        processing_mode = kwargs.get('processing_mode')
        if processing_mode and not mode:
            mode = processing_mode
        if not mode:
            mode = 'unknown'

        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + str(hash(str(parameters)))[-6:]
        
        # Log run start for observability
        logger.info(f"Started processing run: {run_id} (mode: {mode})")
        
        return run_id

    def finish_run(self, run_id: str, status: str = 'completed'):
        """Finish a processing run and log completion.
        Simplified version that only logs completion without DB storage.
        """
        logger.info(f"Finished processing run: {run_id} (status: {status})")
        print(f'\nRun Summary:')
        print(f'  Run ID: {run_id}')
        print(f'  Status: {status}')
        print(f'  Completed at: {datetime.now(timezone.utc)}')

    def record_case_processing(
        self,
        case_number: str,
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
        db_case_number: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """Record a case processing event.
        Simplified version that only logs the event without DB storage.
        """
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
        
        # Normalize outcome for consistent logging and storage
        try:
            outcome = self._normalize_outcome(outcome)
        except Exception:
            pass

        # Log the processing event
        logger.info(f"Case processing: {case_number} -> {outcome} ({duration_seconds:.2f}s)")
        if reason:
            logger.debug(f"  Reason: {reason}")
        if message:
            logger.debug(f"  Message: {message}")

    def _normalize_outcome(self, outcome) -> str:
        """Normalize common outcome string variants into canonical outcomes.

        For backward compatibility and loose input forms, normalize hyphenated
        variants (e.g. 'no-results') into canonical 'no_data' where appropriate.
        """
        if not outcome:
            return str(outcome) if outcome is not None else ""
        o = str(outcome).strip().lower()
        # Normalize common hyphen/underscore inconsistencies
        # Common pass-through values; we treat 'no_data' as the canonical value
        # for the 'no results' condition. Do not treat 'no_results' as a
        # synonym — inputs should explicitly pass 'no_data' where appropriate.
        if o in ('success', 'failed', 'error', 'skipped', 'no_data'):
            return o
        # Unknown variants - collapse hyphens/whitespace to underscores
        return o.replace('-', '_').replace(' ', '_')

    def _get_case_info(self, case_number: str) -> Optional[Dict[str, Any]]:
        """Get case information from the cases table."""
        try:
            canonical = canonicalize_case_number(case_number) if case_number else case_number
        except Exception:
            canonical = case_number
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute("SELECT case_number, status, error_message, retry_count, last_attempt_at, scraped_at FROM cases WHERE case_number = %s LIMIT 1", (canonical,))
            result = cursor.fetchone()
            if result:
                return {
                    'case_number': result[0],
                    'status': result[1],
                    'error_message': result[2],
                    'retry_count': result[3] if len(result) > 3 else None,
                    'last_attempt_at': result[4] if len(result) > 4 else None,
                    'scraped_at': result[5] if len(result) > 5 else None,
                }
            # try original value if canonical and original differ
            if not result and canonical != case_number:
                cursor.execute("SELECT case_number, status, error_message, retry_count, last_attempt_at, scraped_at FROM cases WHERE case_number = %s LIMIT 1", (case_number,))
                result = cursor.fetchone()
                if result:
                    return {
                        'case_number': result[0],
                        'status': result[1],
                        'error_message': result[2],
                        'retry_count': result[3] if len(result) > 3 else None,
                        'last_attempt_at': result[4] if len(result) > 4 else None,
                        'scraped_at': result[5] if len(result) > 5 else None,
                    }
            # attempt regex/LIKE match for zero padded variants (supports sqlite fallback)
            if not result:
                try:
                    import re
                    m = re.search(r"IMM[-\D]*(\d+)[-\\D]*(\d{2})", canonical)
                    if m:
                        zero_padded = f"IMM-{int(m.group(1)):03d}-{int(m.group(2)):02d}"
                        cursor.execute("SELECT case_number, status, error_message FROM cases WHERE case_number = %s LIMIT 1", (zero_padded,))
                        result = cursor.fetchone()
                        if result:
                            return {
                                'case_number': result[0],
                                'status': result[1],
                                'error_message': result[2]
                            }
                except Exception:
                    pass
            cursor.close()
            conn.close()
            return None
        except Exception as e:
            logger.error(f"Database error checking case {case_number}: {e}")
            return None

    def _case_exists_in_db(self, case_number: str) -> bool:
        """Return True if the case exists in the `cases` table."""
        try:
            canonical = canonicalize_case_number(case_number) if case_number else case_number
        except Exception:
            canonical = case_number
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM cases WHERE case_number = %s LIMIT 1", (canonical,))
            exists = cursor.fetchone() is not None
            # try original value if canonical and original differ
            if not exists and canonical != case_number:
                cursor.execute("SELECT 1 FROM cases WHERE case_number = %s LIMIT 1", (case_number,))
                exists = cursor.fetchone() is not None
            # attempt regex/LIKE match for zero padded variants (supports sqlite fallback)
            if not exists:
                try:
                    import re
                    m = re.search(r"IMM[-\D]*(\d+)[-\D]*(\d{2})", canonical)
                    if m:
                        seq = int(m.group(1))
                        yy = m.group(2)
                        # Try a LIKE query to work in sqlite: broad match then narrow by regex in Python
                        like_pattern = f"%IMM%{seq}%{yy}%"
                        cursor.execute("SELECT case_number FROM cases WHERE case_number LIKE %s LIMIT 50", (like_pattern,))
                        # Some DB cursor implementations (test fakes) may not implement fetchall.
                        # If fetchall is not present, attempt a final regex operator fallback.
                        if hasattr(cursor, 'fetchall'):
                            candidates = cursor.fetchall()
                            pattern = re.compile(rf"^IMM\D*0*{seq}\D*{yy}$", flags=re.IGNORECASE)
                            for crow in candidates:
                                if crow and pattern.search(str(crow[0])):
                                    exists = True
                                    break
                        else:
                            # Attempt Postgres regex match directly as fallback for minimal cursors
                            try:
                                pattern = re.compile(rf"^IMM\D*0*{seq}\D*{yy}$", flags=re.IGNORECASE)
                                cursor.execute("SELECT 1 FROM cases WHERE case_number ~* %s LIMIT 1", (pattern.pattern,))
                                exists = cursor.fetchone() is not None
                            except Exception:
                                pass
                except Exception:
                    pass
            cursor.close()
            conn.close()
            return exists
        except Exception as e:
            logger.debug(f"_case_exists_in_db check failed for {case_number}: {e}")
            return False

    def get_stored_case_case_number(self, case_number: str) -> Optional[str]:
        """Return the exact `cases.case_number` stored in DB that corresponds to the given case value."""
        try:
            canonical = canonicalize_case_number(case_number) if case_number else case_number
        except Exception:
            canonical = case_number
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            # Try direct match on canonical badge first
            cursor.execute("SELECT case_number FROM cases WHERE case_number = %s LIMIT 1", (canonical,))
            row = cursor.fetchone()
            if row:
                stored = row[0]
                cursor.close(); conn.close();
                return stored
            # Try original
            cursor.execute("SELECT case_number FROM cases WHERE case_number = %s LIMIT 1", (case_number,))
            row = cursor.fetchone()
            if row:
                stored = row[0]
                cursor.close(); conn.close();
                return stored
            # Lastly attempt fuzzy padded regex search similar to _case_exists_in_db
            try:
                import re
                m = re.search(r"IMM[-\D]*(\d+)[-\D]*(\d{2})", canonical)
                if m:
                    seq = int(m.group(1))
                    yy = m.group(2)
                    # Build a SQL-friendly LIKE pattern that works in both sqlite and Postgres
                    like_pattern = f"%IMM%{seq}%{yy}%"
                    cursor.execute("SELECT case_number FROM cases WHERE case_number LIKE %s LIMIT 1", (like_pattern,))
                    candidates = cursor.fetchall()
                    # Match the strongest regex against returned candidates to ensure we find zero-padded variants
                    pattern = re.compile(rf"^IMM\D*0*{seq}\D*{yy}$", flags=re.IGNORECASE)
                    for crow in candidates:
                        if crow and pattern.search(str(crow[0])):
                            stored = crow[0]
                            cursor.close(); conn.close();
                            return stored
                    # If we didn't find by LIKE, attempt Postgres regex match if available
                    try:
                        cursor.execute("SELECT case_number FROM cases WHERE case_number ~* %s LIMIT 1", (pattern.pattern,))
                        row = cursor.fetchone()
                        if row:
                            stored = row[0]
                            cursor.close(); conn.close();
                            return stored
                    except Exception:
                        # If regex operator isn't available (sqlite), ignore and fall through
                        pass
            except Exception:
                pass
            cursor.close(); conn.close()
            return None
        except Exception as e:
            logger.debug(f"get_stored_case_case_number failed for {case_number}: {e}")
            return None

    def should_skip_case(self, case_number: str, force: bool = False, 
                        max_consecutive_failures: int = 5, run_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Determine if a case should be skipped based on whether it exists in the cases table.
        
        Returns:
            (should_skip, reason)
        """
        if force:
            return False, ""
        
        # Preserve original input for DB fallback checks, then canonicalize the main input
        orig_case_no = case_number
        try:
            case_number = canonicalize_case_number(case_number) if case_number else case_number
        except Exception:
            pass

        # Prefer high-level status (`get_case_status`) which provides normalized
        # 'last_outcome' and consecutive counters. This is used heavily by unit
        # tests and higher-level logic. Fall back to raw _get_case_info for
        # existence checks if get_case_status returns None.
        # Check if case exists in the cases table and get its status
        try:
            # Prefer checking using canonical form first; if not found, check original input as stored in DB
            case_status = self.get_case_status(case_number)
            if not case_status and orig_case_no and orig_case_no != case_number:
                case_status = self.get_case_status(orig_case_no)

            # When get_case_status is not available, fall back to low-level DB info
            case_info = None
            if not case_status:
                case_info = self._get_case_info(case_number)
                if not case_info and orig_case_no and orig_case_no != case_number:
                    case_info = self._get_case_info(orig_case_no)
            
            logger.debug(f"should_skip_case: case_exists_in_db({case_number}) -> {case_info is not None or case_status is not None}")
            # If get_case_status is not present, attempt to detect repeated 'no_data'
            # history via the case_processing_history table and use a 'safe stop'
            # threshold to skip repeated no-data cases without a DB snapshot.
            if not case_status:
                try:
                    recent_no = self._count_recent_no_results(case_number, limit=Config.get_safe_stop_no_records())
                    if recent_no >= Config.get_safe_stop_no_records():
                        reason = f'no_data_repeated ({recent_no})'
                        logger.info(f"Skipping {case_number}: {reason}")
                        return True, reason
                except Exception:
                    pass

            # If no snapshot exists but a case record exists in DB, annotate it
            # as skipped so that historical runs show the reason for skipping.
            if not case_status and not case_info:
                try:
                    if self._case_exists_in_db(case_number):
                        stored_no = self.get_stored_case_case_number(case_number) or case_number
                        # Best-effort to record a 'skipped' snapshot for visibility
                        try:
                            self.record_case_processing(
                                case_number=stored_no,
                                run_id=run_id,
                                outcome='skipped',
                                reason='exists_in_db',
                                processing_mode='db_skip'
                            )
                        except Exception:
                            pass
                        return True, 'exists_in_db'
                except Exception:
                    pass
            if case_status:
                status = case_status.get('last_outcome', 'unknown')
                retry_count = case_status.get('consecutive_failures', case_status.get('consecutive_no_data', 0))
                last_attempt_at = case_status.get('last_processed_at')
                # Annotate discovery for visibility in tracking history
                try:
                    stored_no = self.get_stored_case_case_number(case_number) or case_number
                    self.record_case_processing(
                        case_number=stored_no,
                        run_id=run_id,
                        outcome='skipped',
                        reason='exists_in_db',
                        processing_mode='db_skip'
                    )
                except Exception:
                    pass
            elif case_info:
                # If there's a DB entry but no high-level snapshot, check status first
                status = case_info.get('status', 'unknown')
                retry_count = case_info.get('retry_count', case_info.get('consecutive_failures', case_info.get('consecutive_no_data', 0))) if isinstance(case_info, dict) else 0
                last_attempt_at = case_info.get('last_attempt_at')
                
                # If status is pending or failed, treat as uncollected and don't skip
                if status in ('pending', 'failed'):
                    try:
                        stored_no = self.get_stored_case_case_number(case_number) or case_number
                        self.record_case_processing(
                            case_number=stored_no,
                            run_id=run_id,
                            outcome='proceed',
                            reason=f"exists_in_db (status: {status}, retry_count: {retry_count}), will collect",
                            processing_mode='db_check'
                        )
                    except Exception:
                        pass
                    return False, f"exists_in_db but status is {status}, will collect (retry_count: {retry_count})"
                
                if not case_status:
                    try:
                        stored_no = self.get_stored_case_case_number(case_number) or case_number
                        self.record_case_processing(
                            case_number=stored_no,
                            run_id=run_id,
                            outcome='skipped',
                            reason=f"exists_in_db (status: {status}, retry_count: {retry_count})",
                            processing_mode='db_skip'
                        )
                    except Exception:
                        pass
                    reason = f"exists_in_db (status: {status}, retry_count: {retry_count})"
                    return True, reason
                status = case_info.get('status', 'unknown')
                retry_count = case_info.get('retry_count', case_info.get('consecutive_failures', case_info.get('consecutive_no_data', 0))) if isinstance(case_info, dict) else 0
                last_attempt_at = case_info.get('last_attempt_at')
                # Record a DB-driven annotation so that monitoring shows why the
                # case was considered for skipping/probe/collection.
                try:
                    stored_no = self.get_stored_case_case_number(case_number) or case_number
                    self.record_case_processing(
                        case_number=stored_no,
                        run_id=run_id,
                        outcome='skipped',
                        reason='exists_in_db',
                        processing_mode='db_skip'
                    )
                except Exception:
                    pass
            else:
                status = 'unknown'
                retry_count = 0
                last_attempt_at = None

            # If we have a 'success' or 'no_data' recorded, skip permanently
            # for this run (unless TTLs later indicate we should refresh).
            if status in ('success', 'no_data'):
                # For 'no_data', apply TTL check below to control refreshing.
                if status == 'no_data':
                    ttl_days = Config.get_no_results_ttl_days()
                    # If we don't have a timestamp for last no-data result, assume
                    # it was recent and skip; a timestamp-less snapshot is treated
                    # as canonical no_data that shouldn't be re-collected.
                    if last_attempt_at is None:
                        reason = f'exists_in_db (status: {status}, retry_count: {retry_count})'
                        logger.info(f"Skipping {case_number}: {reason}")
                        return True, reason
                    if ttl_days is not None and last_attempt_at is not None:
                        try:
                            now = datetime.now(timezone.utc)
                            if last_attempt_at.tzinfo is None:
                                last_attempt_at = last_attempt_at.replace(tzinfo=timezone.utc)
                            age_days = (now - last_attempt_at).days
                            if age_days > ttl_days:
                                # TTL expired; allow re-collection
                                pass
                            else:
                                reason = f'exists_in_db (status: {status}, retry_count: {retry_count})'
                                logger.info(f"Skipping {case_number}: {reason}")
                                return True, reason
                        except Exception:
                            # If any error evaluating TTL, default to skipping
                            reason = f'exists_in_db (status: {status}, retry_count: {retry_count})'
                            logger.info(f"Skipping {case_number}: {reason}")
                            return True, reason
                else:
                    reason = f'exists_in_db (status: {status}, retry_count: {retry_count})'
                    logger.info(f"Skipping {case_number}: {reason}")
                    return True, reason
                # Do not skip based on stored DB retry_count. A DB status of 'failed'
                # should not cause the case to be skipped; we must attempt re-collection
                # and manage any in-memory retry counters separately. Continue to
                # allow re-collection unless the last_attempt cooldown forbids it.
                # If the last attempt was within cooldown, skip
                if last_attempt_at:
                    try:
                        if last_attempt_at.tzinfo is None:
                            now_local = datetime.now()
                            time_diff = (now_local - last_attempt_at).total_seconds()
                        else:
                            now = datetime.now(timezone.utc)
                            last_attempt_at_utc = last_attempt_at.astimezone(timezone.utc)
                            time_diff = (now - last_attempt_at_utc).total_seconds()
                        if time_diff < Config.get_retry_cooldown_seconds():
                            reason = f'recently_attempted ({int(time_diff/60)} minutes ago)'
                            logger.info(f"Skipping {case_number}: {reason}")
                            return True, reason
                    except Exception:
                        pass
                # Otherwise allow re-collection for failed or unknown status
                reason = f'exists_in_db but status is {status}, will re-collect (retry_count: {retry_count})'
                logger.info(f"Not skipping {case_number}: {reason}")
                return False, reason
        except Exception as e:
            logger.warning(f"Failed to check case existence for {case_number}: {e}")

        # Default to not skipping (no record found or error occurred)
        # If we computed a `status` above but returned without a `reason`,
        # ensure we return a sensible message instead of an empty string.
        try:
            if 'status' in locals() and status:
                return False, f'exists_in_db but status is {status}, will re-collect (retry_count: {retry_count})'
        except Exception:
            pass
        return False, ""

    def _count_recent_no_results(self, case_number: str, limit: int = 10) -> int:
        """Count recent 'no_data' occurrences in the processing history for a case.

        This method is intentionally simple for unit tests and if the DB is not
        available it will return 0 to indicate no recent 'no_data' history.
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM case_processing_history WHERE case_number = %s AND outcome = %s", (case_number, 'no_data'))
            row = cursor.fetchone()
            cursor.close(); conn.close()
            if row:
                # limit to provided cap
                return min(int(row[0]), limit)
            return 0
        except Exception:
            # DB not available or table missing -> treat as no recent no_results
            return 0

    def get_case_status(self, case_number: str) -> Optional[Dict[str, Any]]:
        """Get case status from cases table.
        Simplified version that returns basic status info.
        """
        try:
            canonical = canonicalize_case_number(case_number) if case_number else case_number
        except Exception:
            canonical = case_number
        
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT case_number, status, retry_count, last_attempt_at, scraped_at, error_message
                FROM cases 
                WHERE case_number = %s 
                LIMIT 1
            """, (canonical,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if row:
                # Map DB status to a canonical last_outcome
                case_no = row[0]
                status = row[1] if len(row) > 1 else None
                retry_count = row[2] if len(row) > 2 else None
                last_attempt_at = row[3] if len(row) > 3 else None
                scraped_at = row[4] if len(row) > 4 else None
                error_message = row[5] if len(row) > 5 else None
                last_outcome = status or 'unknown'
                # Provide additional metadata used by higher-level logic/tests
                return {
                    'case_number': case_no,
                    'created_at': None,  # Not available in current schema
                    'updated_at': last_attempt_at,  # Use last_attempt_at as updated_at
                    'last_outcome': last_outcome,
                    'last_processed_at': last_attempt_at,
                    'consecutive_failures': retry_count if (status == 'failed' and retry_count is not None) else 0,
                    'consecutive_no_data': retry_count if (status == 'no_data' and retry_count is not None) else 0,
                    'error_message': error_message,
                    'scraped_at': scraped_at,
                }
            return None
        except Exception as e:
            logger.debug(f"get_case_status failed for {case_number}: {e}")
            return None

    def get_cases_with_last_outcome(self, outcome: str, year: Optional[int] = None) -> List[str]:
        """Return a list of case_numbers with last known outcome/status matching `outcome`.

        Args:
            outcome: canonical outcome (e.g. 'no_data', 'success', 'failed')
            year: optional year to restrict matching to case numbers in that year

        Returns:
            List[str]: list of case_number strings
        """
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            # Treat older outcome variants (e.g. 'no_results') as synonyms for 'no_data'
            # to ensure we don't miss pre-existing DB rows recorded with legacy values.
            alt_statuses = []
            if outcome == 'no_data':
                alt_statuses = ['no_results']
            if year is not None:
                yy = int(year) % 100
                like_pattern = f"%-{yy:02d}"
                if alt_statuses:
                    cursor.execute(
                        "SELECT case_number FROM cases WHERE (status = %s OR status IN %s) AND case_number LIKE %s",
                        (outcome, tuple(alt_statuses), f"%{like_pattern}"),
                    )
                else:
                    cursor.execute(
                        "SELECT case_number FROM cases WHERE status = %s AND case_number LIKE %s",
                        (outcome, f"%{like_pattern}"),
                    )
            else:
                if alt_statuses:
                    cursor.execute("SELECT case_number FROM cases WHERE status = %s OR status IN %s", (outcome, tuple(alt_statuses)))
                else:
                    cursor.execute("SELECT case_number FROM cases WHERE status = %s", (outcome,))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return [r[0] for r in rows if r and r[0]]
        except Exception as e:
            logger.debug(f"get_cases_with_last_outcome failed for outcome={outcome}: {e}")
            return []