"""Database purge helpers.

Implements `db_purge_year` which deletes cases for a target year and cascades
deletes to related tables by issuing explicit deletes. The implementation reads
candidate case ids and performs deletes inside a transaction; it attempts to be
DB-agnostic by performing minimal SQL and doing filtering in Python where needed.
"""
from __future__ import annotations
from src.lib.logging_config import get_logger
logger = get_logger()

from datetime import datetime
from typing import Callable, Dict, List, Any


def _parse_year_from_value(v: Any) -> int | None:
    if v is None:
        return None
    try:
        if hasattr(v, "year"):
            return int(v.year)
        s = str(v)
        # Expect ISO format at the start
        y = int(s[:4])
        return y
    except Exception:
        return None


def _quote(v: object) -> str:
    """Quote values for an SQL IN expression safely for DBs without
    parameterized list support. Keep this minimal and escape single quotes.
    """
    if isinstance(v, int):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def delete_docket_entries_by_ids(cur, ids: List[Any]) -> int:
    """Delete rows in `docket_entries` that reference the supplied case ids.

    The function attempts multiple common FK column names to maintain
    cross-schema compatibility and returns the number of deleted rows when
    known, or -1 if unknown.
    """
    if not ids:
        return 0
    try:
        ids_list = ",".join(_quote(i) for i in ids)
    except Exception:
        return -1

    fk_candidates = ["case_id", "caseid", "id", "case_number"]
    deleted = -1
    # Inspect columns if available and attempt the delete by each fk candidate
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
            deleted = cur.rowcount if hasattr(cur, "rowcount") else -1
            break
        except Exception:
            try:
                conn_obj = getattr(cur, 'connection', None)
                if conn_obj and hasattr(conn_obj, 'rollback'):
                    conn_obj.rollback()
            except Exception:
                pass
            continue
    return deleted


def delete_docket_entries_by_case_pattern(cur, case_pattern: str) -> int:
    """Delete rows in `docket_entries` for cases matching the given
    `case_number` pattern (e.g. IMM-%-21) and return the deleted count.

    The function first tries the common `case_number` column, then falls
    back to deleting by `case_id` referencing `cases.id` where the
    `case_number` matches the pattern.
    """
    deleted = -1
    try:
        # Try parameterized delete using the standard psycopg2 '%s' style.
        cur.execute("DELETE FROM docket_entries WHERE case_number LIKE %s", (case_pattern,))
        deleted = cur.rowcount if hasattr(cur, "rowcount") else -1
        return deleted
    except Exception:
        try:
            # Fallback to string interpolation in case the DB driver uses ? param style (e.g., sqlite)
            safe = case_pattern.replace("'", "''")
            cur.execute(f"DELETE FROM docket_entries WHERE case_number LIKE '{safe}'")
            deleted = cur.rowcount if hasattr(cur, "rowcount") else -1
            return deleted
        except Exception:
            # Try numeric FK fallback: delete by referencing cases(id)
            try:
                cur.execute("DELETE FROM docket_entries WHERE case_id IN (SELECT id FROM cases WHERE case_number LIKE %s)", (case_pattern,))
                deleted = cur.rowcount if hasattr(cur, "rowcount") else -1
                return deleted
            except Exception:
                try:
                    cur.execute(f"DELETE FROM docket_entries WHERE case_id IN (SELECT id FROM cases WHERE case_number LIKE '{safe}')")
                    deleted = cur.rowcount if hasattr(cur, "rowcount") else -1
                    return deleted
                except Exception:
                    # No viable delete path found
                    return 0
    


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
                # SQL path: fetch case id and the case identifier column and
                # derive the year from the identifier in Python. We do this to
                # avoid relying on scraped/filing timestamps and ensure the
                # purge decision is based solely on the case id as requested.
                # Try common column names for the court-file identifier.
                cur.execute("SELECT id, case_number FROM cases")
                rows = cur.fetchall()
                case_ids = []
                for r in rows:
                    cid = r[0]
                    cf = r[1] if len(r) > 1 else None
                    if cf:
                        s = str(cf)
                        import re

                        m4 = re.search(r"-(\d{4})$", s)
                        if m4 and int(m4.group(1)) == year:
                            case_ids.append(cid)
                            continue
                        m2 = re.search(r"-(\d{2})$", s)
                        if m2 and (2000 + int(m2.group(1))) == year:
                            case_ids.append(cid)
                            continue
                used_sql_filter = True
            except Exception:
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

            id_candidates = ["id", "case_id", "caseid", "case_number", "case_no", "case_number"]
            scraped_candidates = ["scraped_at", "scraped", "created_at", "created"]

            id_col = next((c for c in id_candidates if c in cols), None)
            scraped_col = next((c for c in scraped_candidates if c in cols), None)

            if id_col is None:
                raise RuntimeError("Could not determine primary id column for 'cases' table")

            if scraped_col is None:
                # If there's no scraped timestamp column we cannot determine
                # per-year membership safely; abort with an informative error.
                raise RuntimeError("No scraped/created timestamp column found in 'cases' table to filter by year")

            # Read candidate columns and filter in Python. Prefer explicit
            # filing date or a case identifier-derived year over the scraped
            # timestamp to determine case-year membership. Only use
            # `scraped_at` as a last resort when no other info is available.
            # Detect optional columns if present in the table.
            filing_candidates = ["filing_date", "filed_at", "date_filed", "filing"]
            court_candidates = ["case_number", "case_number", "case_no", "caseid", "case_id"]

            filing_col = next((c for c in filing_candidates if c in cols), None)
            court_col = next((c for c in court_candidates if c in cols), None)

            select_cols = [id_col]
            if scraped_col:
                select_cols.append(scraped_col)
            if filing_col and filing_col not in select_cols:
                select_cols.append(filing_col)
            if court_col and court_col not in select_cols:
                select_cols.append(court_col)

            cur.execute(f"SELECT {', '.join(select_cols)} FROM cases")
            rows = cur.fetchall()

            # Build column name -> index map from cursor description
            desc = [d[0] for d in cur.description] if cur.description else []
            name_to_idx = {n: i for i, n in enumerate(desc)}

            for r in rows:
                cid = r[name_to_idx[id_col]] if id_col in name_to_idx else r[0]

                # 1) Prefer filing_date if present
                included = False
                if filing_col and filing_col in name_to_idx:
                    try:
                        filing_val = r[name_to_idx[filing_col]]
                        fy = _parse_year_from_value(filing_val)
                        if fy == year:
                            case_ids.append(cid)
                            included = True
                    except Exception:
                        pass
                if included:
                    continue

                # 2) Prefer derive from court file number / case identifier
                parse_found = False
                if court_col and court_col in name_to_idx:
                    try:
                        cf = r[name_to_idx[court_col]]
                        s = str(cf or "")
                        import re

                        m = re.search(r"-(\d{4})$", s)
                        if m:
                            parse_found = True
                            y4 = int(m.group(1))
                            if y4 == year:
                                case_ids.append(cid)
                                continue
                            else:
                                # Case identifier explicitly indicates a different
                                # case-year; do not include based on scraped_at.
                                continue
                        m2 = re.search(r"-(\d{2})$", s)
                        if m2:
                            parse_found = True
                            yy = int(m2.group(1))
                            derived = 2000 + yy
                            if derived == year:
                                case_ids.append(cid)
                                continue
                            else:
                                # Explicit two-digit year found but differs -> skip
                                continue
                    except Exception:
                        pass

                # 3) Last resort: use scraped_at only when we have no filing
                # date and no parseable court-file year. If a court identifier
                # exists but did not include a year (parse_found == False), we
                # may safely use scraped_at as fallback (tests rely on this).
                if scraped_col and scraped_col in name_to_idx and not included:
                    # Only allow scraped_at when filing_col absent and either
                    # no court identifier exists or it was not parseable.
                    if (not filing_col) and (not court_col or not parse_found):
                        try:
                            scraped_at = r[name_to_idx[scraped_col]]
                            y = _parse_year_from_value(scraped_at)
                            if y == year:
                                case_ids.append(cid)
                                continue
                        except Exception:
                            pass

        result = {
            "year": year,
            "candidate_case_ids": case_ids,
            "cases_deleted": 0,
            "docket_entries_deleted": 0,
        }
        logger.debug(f"db_purge_year candidates: {case_ids} id_col={id_col} scraped_col={scraped_col} filing_col={filing_col} court_col={court_col}")

        if not case_ids:
            return result

        # Build IN clause safely (ids may be ints or strings). Quote string
        # values as needed for SQL.
        ids_list = ",".join(_quote(i) for i in case_ids)

        if transactional:
            # Begin explicit transaction if supported
            try:
                cur.execute("BEGIN")
            except Exception:
                pass

        # Delete dependent docket_entries first using the helper
        try:
            deleted_de = delete_docket_entries_by_ids(cur, case_ids)
            result["docket_entries_deleted"] = deleted_de
        except Exception:
            # Best-effort; leave as 0 if deletion cannot be performed
            result["docket_entries_deleted"] = 0

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
