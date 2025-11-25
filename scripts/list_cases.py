#!/usr/bin/env python3
"""Simple helper to list rows from the `cases` table.

Usage:
  python scripts/list_cases.py [--limit N] [--year YYYY]

Connects using `src.lib.config.Config.get_db_config()` so it respects local config.
"""
import argparse

import psycopg2
from psycopg2.extras import RealDictCursor

from src.lib.config import Config


def get_db_conn():
    cfg = Config.get_db_config()
    return psycopg2.connect(**cfg)


def list_cases(limit: int = 10, year: int | None = None):
    q = "SELECT court_file_no, case_type, type_of_action, filing_date, scraped_at FROM cases"
    params = []
    if year is not None:
        q += " WHERE court_file_no LIKE %s"
        params.append(f"IMM-%-{year % 100:02d}")
    q += " ORDER BY scraped_at DESC NULLS LAST LIMIT %s"
    params.append(limit)

    with get_db_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, params)
            rows = cur.fetchall()

    if not rows:
        print("No cases found.")
        return

    for r in rows:
        print(
            f"- {r.get('court_file_no')} | type={r.get('case_type')} | action={r.get('type_of_action')} | filing_date={r.get('filing_date')} | scraped_at={r.get('scraped_at')}"
        )


def main():
    p = argparse.ArgumentParser(description="List cases from DB")
    p.add_argument("--limit", type=int, default=10, help="Number of rows to show")
    p.add_argument("--year", type=int, help="Filter by year (e.g., 2025)")
    args = p.parse_args()

    try:
        list_cases(limit=args.limit, year=args.year)
    except Exception as e:
        print(f"Error querying database: {e}")


if __name__ == "__main__":
    main()
