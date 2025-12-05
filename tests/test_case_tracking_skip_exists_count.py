import sqlite3
import types
import sys
from src.services.case_tracking_service import CaseTrackingService


def _create_memory_db():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    # Create minimal schema: cases, case_status_snapshots, processing_runs
    cur.execute("""
        CREATE TABLE cases (
            court_file_no TEXT PRIMARY KEY,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE case_status_snapshots (
            case_number TEXT PRIMARY KEY,
            court_file_no TEXT,
            last_outcome TEXT,
            last_run_id TEXT,
            last_processed_at TEXT,
            consecutive_failures INTEGER DEFAULT 0,
            first_seen_at TEXT,
            last_success_at TEXT,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE processing_runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
            completed_at TEXT,
            processing_mode TEXT,
            start_case_number TEXT,
            max_cases INTEGER,
            total_cases_processed INTEGER,
            success_count INTEGER,
            failed_count INTEGER,
            skipped_count INTEGER,
            error_count INTEGER,
            status TEXT
        )
    """)
    conn.commit()
    return conn


class SQLiteConnWrapper:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return SQLiteCursorWrapper(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        # Do not close the underlying sqlite connection; the test harness
        # manages the lifecycle of the shared in-memory connection.
        return None


class SQLiteCursorWrapper:
    def __init__(self, cur):
        self._cur = cur
        self.rowcount = -1

    def execute(self, sql, params=None):
        if params is None:
            return self._cur.execute(sql)
        sql2 = sql.replace('%s', '?') if '%s' in sql else sql
        res = self._cur.execute(sql2, params)
        self.rowcount = getattr(self._cur, 'rowcount', -1)
        return res

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def close(self):
        try:
            return self._cur.close()
        except Exception:
            pass


def test_skip_exists_count_uses_stored_case_value(monkeypatch):
    svc = CaseTrackingService()
    conn = _create_memory_db()
    cur = conn.cursor()
    # Insert a case that uses padded variant in DB
    stored_case = 'IMM-0004-21'
    cur.execute("INSERT INTO cases (court_file_no, created_at) VALUES (?, ?)", (stored_case, '2021-01-01T00:00:00'))
    conn.commit()

    # monkeypatch psycopg2.connect to use our sqlite connection wrapper
    import src.services.case_tracking_service as module
    monkeypatch.setattr(module.psycopg2, 'connect', lambda **kwargs: SQLiteConnWrapper(conn))

    # Start a run and record a skip using the non-padded input (should use stored_no internally)
    # Create a processing_runs row that matches what finish_run expects
    import uuid
    run_id = 'test_run_' + uuid.uuid4().hex[:10]
    cur.execute("INSERT INTO processing_runs (run_id, started_at, processing_mode, max_cases, total_cases_processed, success_count, failed_count, skipped_count, error_count, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, '2025-01-01T00:00:00', 'batch_collect', 1, 0, 0, 0, 0, 0, 'running'))
    conn.commit()
    # Simulate detection of exists_in_db: should store snapshot with stored_case
    stored_no = svc.get_stored_case_court_file_no('IMM-4-21') or 'IMM-4-21'
    print('stored_no before record:', stored_no)
    svc.record_case_processing(court_file_no=stored_no, run_id=run_id, outcome='skipped', reason='exists_in_db')
    # Inspect snapshot row inserted/updated by record_case_processing
    cur.execute("SELECT case_number, court_file_no, last_outcome, last_run_id FROM case_status_snapshots WHERE last_run_id = ?", (run_id,))
    snap_rows = cur.fetchall()
    print('snapshot rows:', snap_rows)

    # Call finish_run which updates processing_runs and computes counts
    svc.finish_run(run_id, 'completed')

    # Now query processing_runs to verify skipped_count is 1
    cur.execute("SELECT skipped_count FROM processing_runs WHERE run_id = ?", (run_id,))
    val = cur.fetchone()
    assert val is not None
    assert val[0] == 1

    # Verify the skip existed due to exists_in_db join
    # Count joined rows manually
    cur.execute("SELECT COUNT(*) FROM case_status_snapshots ss JOIN cases c ON c.court_file_no = ss.court_file_no WHERE ss.last_run_id = ? AND ss.last_outcome = 'skipped'", (run_id,))
    count_join = cur.fetchone()[0]
    assert count_join == 1
