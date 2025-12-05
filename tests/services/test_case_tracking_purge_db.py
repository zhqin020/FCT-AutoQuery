import sqlite3
import sys
import types

# Provide a lightweight fake psycopg2 module if it's not installed so tests can
# import the service module without requiring system-level dependencies.
if 'psycopg2' not in sys.modules:
    fake_extras = types.SimpleNamespace(RealDictCursor=object)
    fake_psycopg2 = types.SimpleNamespace(connect=lambda **kwargs: None, extras=fake_extras)
    sys.modules['psycopg2'] = fake_psycopg2

from src.services.case_tracking_service import CaseTrackingService


def _create_memory_db():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    # Simple schema: cases with court_file_no primary key, docket_entries referencing it
    cur.execute(
        """
        CREATE TABLE cases (
            court_file_no TEXT PRIMARY KEY,
            scraped_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE docket_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            court_file_no TEXT,
            content TEXT,
            FOREIGN KEY(court_file_no) REFERENCES cases(court_file_no) ON DELETE CASCADE
        )
        """
    )
    # Add snapshots and history tables for testing purge logic
    cur.execute(
        """
        CREATE TABLE case_status_snapshots (
            case_number TEXT PRIMARY KEY,
            court_file_no TEXT,
            last_outcome TEXT,
            last_run_id TEXT,
            last_processed_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE case_processing_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            case_number TEXT,
            court_file_no TEXT,
            processing_mode TEXT,
            outcome TEXT,
            started_at TEXT
        )
        """
    )
    conn.commit()
    return conn


class SQLiteConnWrapper:
    """Wrap sqlite3.Connection to provide a psycopg2-like API used by the code under test."""

    def __init__(self, conn):
        self._conn = conn
        self.autocommit = False

    def cursor(self):
        # Return a cursor wrapper that adapts psycopg2-style '%s' placeholders
        # to sqlite3's '?' parameter style so our tests can work across
        # both DB adapters.
        return SQLiteCursorWrapper(self._conn.cursor())

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        # For testing, do not close the underlying shared sqlite3 connection; allow the
        # test harness to manage the connection lifecycle.
        return None


class SQLiteCursorWrapper:
    """Wrap sqlite3.Cursor to support `%s` placeholders used by psycopg2.

    The wrapper simply replaces '%s' tokens with '?' for sqlite parameter
    substitution and forwards result rows.
    """
    def __init__(self, cur):
        self._cur = cur
        self.rowcount = -1
        self.description = None

    def execute(self, sql, params=None):
        if params is None:
            return self._cur.execute(sql)
        try:
            # Support psycopg2-style '%s' placeholders by translating them to '?'
            if '%s' in sql:
                sql2 = sql.replace('%s', '?')
            else:
                sql2 = sql
            res = self._cur.execute(sql2, params)
            self.rowcount = self._cur.rowcount if hasattr(self._cur, 'rowcount') else -1
            self.description = self._cur.description
            return res
        except Exception:
            # Re-raise to allow caller to attempt fallback
            raise

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def close(self):
        try:
            return self._cur.close()
        except Exception:
            pass


def test_purge_case_number_deletes_docket_entry(monkeypatch):
    svc = CaseTrackingService()
    conn = _create_memory_db()
    cur = conn.cursor()
    # Insert test case and a docket entry
    test_case = "IMM-999-21"
    cur.execute("INSERT INTO cases (court_file_no, scraped_at) VALUES (?, ?)", (test_case, "2021-03-01T00:00:00"))
    cur.execute("INSERT INTO docket_entries (court_file_no, content) VALUES (?, ?)", (test_case, "entry"))
    conn.commit()

    # Monkeypatch psycopg2.connect to return our sqlite connection
    import src.services.case_tracking_service as module

    monkeypatch.setattr(module.psycopg2, "connect", lambda **kwargs: SQLiteConnWrapper(conn))

    # Purge single case
    res = svc.purge_case_number(test_case)
    assert res is True

    # Verify both case and docket entry are removed
    cur.execute("SELECT COUNT(*) FROM cases")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM docket_entries")
    assert cur.fetchone()[0] == 0


def test_purge_year_deletes_docket_entries(monkeypatch):
    svc = CaseTrackingService()
    conn = _create_memory_db()
    cur = conn.cursor()
    # Insert two cases: 2021 and 2022
    case_2021 = "IMM-1-21"
    case_2022 = "IMM-2-22"
    cur.execute("INSERT INTO cases (court_file_no, scraped_at) VALUES (?, ?)", (case_2021, "2021-01-01T00:00:00"))
    cur.execute("INSERT INTO cases (court_file_no, scraped_at) VALUES (?, ?)", (case_2022, "2022-01-01T00:00:00"))
    # Add docket entries for both
    cur.execute("INSERT INTO docket_entries (court_file_no, content) VALUES (?, ?)", (case_2021, "a"))
    cur.execute("INSERT INTO docket_entries (court_file_no, content) VALUES (?, ?)", (case_2022, "b"))
    conn.commit()

    # Monkeypatch psycopg2.connect to return our sqlite connection
    import src.services.case_tracking_service as module
    monkeypatch.setattr(module.psycopg2, "connect", lambda **kwargs: SQLiteConnWrapper(conn))

    # Purge the year 2021
    stats = svc.purge_year(2021)
    # Expect one case and one docket entry deleted for 2021
    assert stats["cases_deleted"] == 1
    assert stats["docket_entries_deleted"] == 1

    # Confirm snapshots and history unaffected for 2022; ensure 2021 snapshot deleted
    cur.execute("SELECT court_file_no FROM case_status_snapshots")
    snapshot_remaining = [r[0] for r in cur.fetchall()]
    # There should be no snapshots for the 2021 case
    assert not any('2021' in s for s in snapshot_remaining)

    # Confirm GA: remaining case is 2022 and its docket entry
    # Re-query with a fresh cursor after the purge to avoid any cursor caching
    cur2 = conn.cursor()
    cur2.execute("SELECT court_file_no FROM cases")
    remaining = [r[0] for r in cur2.fetchall()]
    # debug output removed; assert '-22' suffix is present (two-digit year form)
    assert any("-22" in r for r in remaining)
    cur.execute("SELECT count(*) FROM docket_entries")
    remaining_de = cur.fetchone()[0]
    assert remaining_de == 1


def test_purge_year_deletes_snapshots_and_history(monkeypatch):
    svc = CaseTrackingService()
    conn = _create_memory_db()
    cur = conn.cursor()
    # Insert two cases: 2021 and 2022
    case_2021 = "IMM-10-21"
    case_2022 = "IMM-11-22"
    cur.execute("INSERT INTO cases (court_file_no, scraped_at) VALUES (?, ?)", (case_2021, "2021-01-01T00:00:00"))
    cur.execute("INSERT INTO cases (court_file_no, scraped_at) VALUES (?, ?)", (case_2022, "2022-01-01T00:00:00"))
    # Add snapshots and history entries for both
    cur.execute("INSERT INTO case_status_snapshots (case_number, court_file_no, last_outcome, last_run_id, last_processed_at) VALUES (?, ?, ?, ?, ?)", (case_2021, case_2021, 'skipped', 'r1', '2021-02-01T00:00:00'))
    cur.execute("INSERT INTO case_status_snapshots (case_number, court_file_no, last_outcome, last_run_id, last_processed_at) VALUES (?, ?, ?, ?, ?)", (case_2022, case_2022, 'success', 'r2', '2022-02-01T00:00:00'))
    cur.execute("INSERT INTO case_processing_history (run_id, case_number, processing_mode, outcome, started_at) VALUES (?, ?, ?, ?, ?)", ('r1', case_2021, 'batch', 'skipped', '2021-02-01T00:00:00'))
    cur.execute("INSERT INTO case_processing_history (run_id, case_number, processing_mode, outcome, started_at) VALUES (?, ?, ?, ?, ?)", ('r2', case_2022, 'batch', 'success', '2022-02-01T00:00:00'))
    conn.commit()

    import src.services.case_tracking_service as module
    monkeypatch.setattr(module.psycopg2, "connect", lambda **kwargs: SQLiteConnWrapper(conn))

    stats = svc.purge_year(2021)
    assert stats["cases_deleted"] == 1
    assert stats["history_deleted"] >= 1
    assert stats["snapshots_deleted"] >= 1
    # Ensure 2022 case left intact
    # Re-query with a fresh cursor after the purge to avoid cursor caching issues
    cur2 = conn.cursor()
    cur2.execute("SELECT court_file_no FROM cases")
    remaining = [r[0] for r in cur2.fetchall()]
    assert any('-22' in r for r in remaining)


def test_should_not_skip_on_stale_snapshot_when_case_missing(monkeypatch):
    svc = CaseTrackingService()
    conn = _create_memory_db()
    cur = conn.cursor()

    # Insert a snapshot for a case that is NOT present in cases table
    missing_case = 'IMM-999-21'
    cur.execute("INSERT INTO case_status_snapshots (case_number, court_file_no, last_outcome, last_run_id, last_processed_at) VALUES (?, ?, ?, ?, ?)", (missing_case, missing_case, 'skipped', 'r_missing', '2021-02-01T00:00:00'))
    conn.commit()

    import src.services.case_tracking_service as module
    monkeypatch.setattr(module.psycopg2, "connect", lambda **kwargs: SQLiteConnWrapper(conn))

    should_skip, reason = svc.should_skip_case(missing_case, force=False)
    assert should_skip is False
    assert reason == '' or 'no_data' not in reason


def test_should_not_skip_if_recent_success_but_case_missing(monkeypatch):
    svc = CaseTrackingService()
    conn = _create_memory_db()
    cur = conn.cursor()

    # Insert a snapshot with last_outcome 'success' but no corresponding cases entry
    missing_case = 'IMM-7-21'
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    cur.execute("INSERT INTO case_status_snapshots (case_number, court_file_no, last_outcome, last_run_id, last_processed_at, last_success_at) VALUES (?, ?, ?, ?, ?, ?)", (missing_case, missing_case, 'success', 'r_success', now, now))
    conn.commit()

    import src.services.case_tracking_service as module
    monkeypatch.setattr(module.psycopg2, "connect", lambda **kwargs: SQLiteConnWrapper(conn))

    should_skip, reason = svc.should_skip_case(missing_case, force=False)
    # Should NOT skip since the case is not present in the `cases` table
    assert should_skip is False
    assert reason == ''
