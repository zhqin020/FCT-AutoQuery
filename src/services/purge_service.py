"""Database purge helpers.

Implements `db_purge_year` which deletes cases for a target year and cascades
deletes to related tables by issuing explicit deletes. The implementation reads
candidate case ids and performs deletes inside a transaction; it attempts to be
DB-agnostic by performing minimal SQL and doing filtering in Python where needed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List, Any


def _parse_year_from_value(v: Any) -> int | None:
    if v is None:
        return None
    # Accept datetime, date, or ISO string
    try:
        if hasattr(v, "year"):
            return int(v.year)
        s = str(v)
        # Expect ISO format at the start
        y = int(s[:4])
        return y
    except Exception:
        return None


def db_purge_year(
    year: int,
    get_connection: Callable[[], Any],
    transactional: bool = True,
    sql_year_filter: bool | None = None,
) -> Dict[str, Any]:
    """Purge DB rows for `year` using a supplied connection factory.

    Args:
        year: target year to purge
        get_connection: callable that returns a DB connection with `cursor()`
                        supporting `execute()` and `fetchall()` and `commit()` / `rollback()`.
        transactional: whether to run deletes inside a transaction

    Returns:
        dict with counts and lists for audit
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Attempt an SQL-year-filter first when requested or auto-detect.
        # Some DBs (Postgres) support EXTRACT(YEAR FROM <ts>); SQLite does not.
        case_ids: List[int] = []
        used_sql_filter = False
        try_sql = True if sql_year_filter is None or sql_year_filter is True else False

        if try_sql:
            try:
                # Use SQL EXTRACT; if DB doesn't support it this will raise and we'll
                # fall back to DB-agnostic enumeration.
                cur.execute(f"SELECT id FROM cases WHERE EXTRACT(YEAR FROM scraped_at) = {int(year)}")
                rows = cur.fetchall()
                case_ids = [int(r[0]) for r in rows]
                used_sql_filter = True
            except Exception:
                # Fall back to DB-agnostic approach below. If the DB raised an
                # error (for example a syntax/feature error) the connection may
                # be left in a failed transaction state (Postgres). Roll back
                # so subsequent queries will succeed on the same connection.
                try:
                    conn.rollback()
                except Exception:
                    pass
                used_sql_filter = False

        if not used_sql_filter:
            # Load candidate cases dynamically: detect primary/id column and
            # the scraped timestamp column so we can filter in Python. This
            # makes the purge logic resilient to slight schema differences
            # (e.g. `id` vs `case_id` vs `case_number`).
            cur.execute("SELECT * FROM cases LIMIT 1")
            cols = [d[0] for d in cur.description] if cur.description else []

            id_candidates = ["id", "case_id", "caseid", "case_number", "case_no", "court_file_no"]
            scraped_candidates = ["scraped_at", "scraped", "created_at", "created"]

            id_col = next((c for c in id_candidates if c in cols), None)
            scraped_col = next((c for c in scraped_candidates if c in cols), None)

            if id_col is None:
                raise RuntimeError("Could not determine primary id column for 'cases' table")

            if scraped_col is None:
                # If there's no scraped timestamp column we cannot determine
                # per-year membership safely; abort with an informative error.
                raise RuntimeError("No scraped/created timestamp column found in 'cases' table to filter by year")

            # Read id + scraped values and filter in Python
            cur.execute(f"SELECT {id_col}, {scraped_col} FROM cases")
            rows = cur.fetchall()
            for r in rows:
                cid = r[0]
                scraped_at = r[1]
                y = _parse_year_from_value(scraped_at)
                if y == year:
                    case_ids.append(cid)

        result = {
            "year": year,
            "candidate_case_ids": case_ids,
            "cases_deleted": 0,
            "docket_entries_deleted": 0,
        }

        if not case_ids:
            return result

        # Build IN clause safely (ids may be ints or strings). Quote string
        # values as needed for SQL.
        def _quote(v: object) -> str:
            if isinstance(v, int):
                return str(v)
            s = str(v).replace("'", "''")
            return f"'{s}'"

        ids_list = ",".join(_quote(i) for i in case_ids)

        if transactional:
            # Begin explicit transaction if supported
            try:
                cur.execute("BEGIN")
            except Exception:
                pass

        # Delete dependent rows first. Avoid executing statements that will
        # certainly fail by checking available columns on `docket_entries`.
        deleted_de = -1
        fk_candidates = ["case_id", "caseid", id_col, "case_number"]

        # Inspect docket_entries columns (DB-agnostic fallback)
        try:
            cur.execute("SELECT * FROM docket_entries LIMIT 1")
            de_cols = [d[0] for d in cur.description] if cur.description else []
        except Exception:
            de_cols = []

        for fk in fk_candidates:
            if not fk or (de_cols and fk not in de_cols):
                continue
            try:
                cur.execute(f"DELETE FROM docket_entries WHERE {fk} IN ({ids_list})")
                deleted_de = cur.rowcount if hasattr(cur, "rowcount") else -1
                result["docket_entries_deleted"] = deleted_de
                break
            except Exception:
                # ensure connection is usable for further attempts
                try:
                    conn.rollback()
                except Exception:
                    pass
                continue

        # Delete cases using the detected id column
        try:
            cur.execute(f"DELETE FROM cases WHERE {id_col} IN ({ids_list})")
            c_count = cur.rowcount if hasattr(cur, "rowcount") else -1
            result["cases_deleted"] = c_count
        except Exception:
            result["cases_deleted"] = -1

        if transactional:
            conn.commit()

        return result
    except Exception:
        if transactional:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
