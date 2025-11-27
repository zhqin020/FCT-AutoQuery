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
                # SQL path: fetch case id and the case identifier column and
                # derive the year from the identifier in Python. We do this to
                # avoid relying on scraped/filing timestamps and ensure the
                # purge decision is based solely on the case id as requested.
                # Try common column names for the court-file identifier.
                cur.execute("SELECT id, court_file_no FROM cases")
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

            # Read candidate columns and filter in Python. Prefer explicit
            # filing date or a case identifier-derived year over the scraped
            # timestamp to determine case-year membership. Only use
            # `scraped_at` as a last resort when no other info is available.
            # Detect optional columns if present in the table.
            filing_candidates = ["filing_date", "filed_at", "date_filed", "filing"]
            court_candidates = ["court_file_no", "case_number", "case_no", "caseid", "case_id"]

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
