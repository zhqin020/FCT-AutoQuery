#!/usr/bin/env python3
"""Normalize outcome values across tracking tables.

This script finds rows where people used 'no-results' or other variants and converts
these to the canonical 'no_data' term to avoid mismatches and ensure the code
can consistently rely on one outcome token.

Usage:
    python scripts/normalize_outcome_values.py --dry-run
    python scripts/normalize_outcome_values.py --apply

"""
import argparse
import psycopg2
from src.lib.config import Config

OUTCOME_VARIANTS = [
    'no-results',
    'no results',
    'noresults',
    'no_result',
    'no_results',
]
CANONICAL = 'no_data'


def get_db_conn():
    cfg = Config.get_db_config()
    return psycopg2.connect(**cfg)


def count_variants(conn):
    cur = conn.cursor()
    total = 0
    for var in OUTCOME_VARIANTS:
        q = "SELECT COUNT(*) FROM case_processing_history WHERE outcome = %s"
        cur.execute(q, (var,))
        c = cur.fetchone()[0]
        print(f"case_processing_history rows with outcome={var}: {c}")
        total += c
    cur.close()
    return total


def preview_updates(conn):
    cur = conn.cursor()
    print("Samples for case_processing_history needing normalization:")
    cur.execute("SELECT id, court_file_no, run_id, outcome FROM case_processing_history WHERE outcome = ANY(%s) LIMIT 10", (OUTCOME_VARIANTS,))
    for r in cur.fetchall():
        print(r)
    cur.close()


def apply_updates(conn):
    cur = conn.cursor()
    # Update processing history
    cur.execute("UPDATE case_processing_history SET outcome = %s WHERE outcome = ANY(%s)", (CANONICAL, OUTCOME_VARIANTS))
    print(f"Updated case_processing_history rows: {cur.rowcount}")
    # Update snapshots (if last_outcome uses variants)
    cur.execute("UPDATE case_status_snapshots SET last_outcome = %s WHERE last_outcome = ANY(%s)", (CANONICAL, OUTCOME_VARIANTS))
    print(f"Updated case_status_snapshots rows: {cur.rowcount}")
    conn.commit()
    cur.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    conn = get_db_conn()
    try:
        total = count_variants(conn)
        preview_updates(conn)
        if args.apply:
            print('Applying updates...')
            apply_updates(conn)
        else:
            print('Dry-run: no changes applied. Use --apply to perform updates.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
