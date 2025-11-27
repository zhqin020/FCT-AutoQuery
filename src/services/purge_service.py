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
        # Load candidate cases (id, scraped_at)
        cur.execute("SELECT id, scraped_at FROM cases")
        rows = cur.fetchall()
        case_ids: List[int] = []
        for r in rows:
            cid = r[0]
            scraped_at = r[1]
            y = _parse_year_from_value(scraped_at)
            if y == year:
                case_ids.append(int(cid))

        result = {
            "year": year,
            "candidate_case_ids": case_ids,
            "cases_deleted": 0,
            "docket_entries_deleted": 0,
        }

        if not case_ids:
            return result

        # Build IN clause safely (ids are ints taken from DB)
        ids_list = ",".join(str(i) for i in case_ids)

        if transactional:
            # Begin explicit transaction if supported
            try:
                cur.execute("BEGIN")
            except Exception:
                pass

        # Delete dependent rows first
        cur.execute(f"DELETE FROM docket_entries WHERE case_id IN ({ids_list})")
        de_count = cur.rowcount if hasattr(cur, "rowcount") else -1
        result["docket_entries_deleted"] = de_count

        # Delete cases
        cur.execute(f"DELETE FROM cases WHERE id IN ({ids_list})")
        c_count = cur.rowcount if hasattr(cur, "rowcount") else -1
        result["cases_deleted"] = c_count

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
