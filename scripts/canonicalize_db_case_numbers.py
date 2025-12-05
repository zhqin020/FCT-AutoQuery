#!/usr/bin/env python3
"""DB migration script to canonicalize case numbers and merge duplicates.

This script is conservative and supports a dry-run mode. It will:
 - Find all case numbers in `cases` table that match IMM- pattern
 - For each, compute canonical format (IMM-<seq>-YY)
 - If there are multiple variants mapping to same canonical, report (and optionally merge) them

Usage:
  python scripts/canonicalize_db_case_numbers.py --dry-run
  python scripts/canonicalize_db_case_numbers.py --apply

Important: run with a DB backup or in a transaction. This script is opinionated
— verify outputs before applying.
"""
import argparse
import os
import sys
import re
from collections import defaultdict

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.lib.config import Config
from src.lib.case_utils import canonicalize_case_number
import psycopg2


def gather_variants(conn):
    cur = conn.cursor()
    cur.execute("SELECT court_file_no FROM cases WHERE court_file_no ILIKE 'IMM-%-%'")
    rows = [r[0] for r in cur.fetchall()]
    cur.close()
    groups = defaultdict(list)
    for v in rows:
        groups[canonicalize_case_number(v)].append(v)
    return groups


def apply_merge(conn, canonical, variants):
    cur = conn.cursor()
    # If canonical exists and has multiple variants, move histories and snapshots to canonical
    # Steps: update case_processing_history, case_status_snapshots, cases table
    # 1) Find canonical existing
    cur.execute("SELECT 1 FROM cases WHERE court_file_no = %s LIMIT 1", (canonical,))
    canonical_exists = bool(cur.fetchone())

    to_merge = [v for v in variants if v != canonical]
    if not to_merge:
        return

    for v in to_merge:
        print(f"Merging {v} -> {canonical}")
        # Update case_processing_history
        cur.execute("UPDATE case_processing_history SET court_file_no = %s WHERE court_file_no = %s", (canonical, v))
        # Update snapshots: if canonical exists we remove v's snapshot, else rename
        if canonical_exists:
            cur.execute("DELETE FROM case_status_snapshots WHERE court_file_no = %s", (v,))
        else:
            cur.execute("UPDATE case_status_snapshots SET court_file_no = %s WHERE court_file_no = %s", (canonical, v))
        # For main cases table: if canonical doesn't exist, rename row to canonical; else delete variant row
        if canonical_exists:
            cur.execute("DELETE FROM cases WHERE court_file_no = %s", (v,))
        else:
            cur.execute("UPDATE cases SET court_file_no = %s WHERE court_file_no = %s", (canonical, v))
    conn.commit()
    cur.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='Apply changes')
    args = parser.parse_args()

    cfg = Config.get_db_config()
    print(f"DB: {cfg.get('host')}:{cfg.get('port')}/{cfg.get('database')}")
    conn = psycopg2.connect(**cfg)
    groups = gather_variants(conn)
    corrections = {k: v for k, v in groups.items() if len(set(v)) > 1}
    print(f"Found {len(corrections)} canonical groups with variants")
    for c, variants in corrections.items():
        print(c, variants)
    if args.apply:
        # careful apply
        for c, variants in corrections.items():
            apply_merge(conn, c, variants)
        print('Applied canonicalization changes')
    else:
        print('Dry-run only, no changes applied')
    conn.close()


if __name__ == '__main__':
    main()
