#!/usr/bin/env python3
"""Quick diagnostic tool to check if a case has been recorded in case_processing_history
and case_status_snapshots tables.

Usage:
  python scripts/check_case_tracking.py IMM-5-21

This tool uses the repository Config to connect to the database and prints
the relevant rows for the given case number and its canonical form.
"""
import sys
import os
import json
import psycopg2


def main():
    if len(sys.argv) < 2:
        print("Usage: check_case_tracking.py <CASE_NUMBER>")
        sys.exit(1)

    case_input = sys.argv[1]
    # Ensure repository root is on sys.path for imports
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    # local imports after sys.path adjustment
    from src.lib.config import Config
    from src.lib.case_utils import canonicalize_case_number

    case_canon = canonicalize_case_number(case_input)

    db_cfg = Config.get_db_config()
    print(f"Connecting to DB: {db_cfg.get('host')}:{db_cfg.get('port')}/{db_cfg.get('database')}")
    try:
        conn = psycopg2.connect(**db_cfg)
        cursor = conn.cursor()

        print(f"Checking 'case_processing_history' for canonical case: {case_canon}")
        cursor.execute(
            "SELECT run_id, outcome, reason, message, started_at, completed_at FROM case_processing_history WHERE court_file_no = %s ORDER BY started_at DESC LIMIT 20",
            (case_canon,)
        )
        rows = cursor.fetchall()
        print("--- case_processing_history rows (canonical):")
        for r in rows:
            print(r)

        if case_input != case_canon:
            print(f"Checking 'case_processing_history' for raw input: {case_input}")
            cursor.execute(
                "SELECT run_id, outcome, reason, message, started_at, completed_at FROM case_processing_history WHERE court_file_no = %s ORDER BY started_at DESC LIMIT 20",
                (case_input,)
            )
            rows_raw = cursor.fetchall()
            print("--- case_processing_history rows (raw):")
            for r in rows_raw:
                print(r)

        # snapshot
        print(f"Checking 'case_status_snapshots' for canonical: {case_canon}")
        cursor.execute(
            "SELECT * FROM case_status_snapshots WHERE court_file_no = %s",
            (case_canon,)
        )
        ss = cursor.fetchall()
        print("--- case_status_snapshots (canonical):")
        for r in ss:
            print(r)

        if case_input != case_canon:
            print(f"Checking 'case_status_snapshots' for raw: {case_input}")
            cursor.execute(
                "SELECT * FROM case_status_snapshots WHERE court_file_no = %s",
                (case_input,)
            )
            ss_raw = cursor.fetchall()
            print("--- case_status_snapshots (raw):")
            for r in ss_raw:
                print(r)

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"DB error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
