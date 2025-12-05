#!/usr/bin/env python3
"""
Compact/Archive `case_processing_history` into snapshots and optionally archive the table.
This script: 
 - Backs up the entire `case_processing_history` table to a JSON file (for safekeeping)
 - For each case, ensures a `case_status_snapshots` row exists with the latest outcome
 - Optionally renames `case_processing_history` to `case_processing_history_archived`

Usage:
  python scripts/compact_case_history.py [--execute]

"""
import argparse
import json
from datetime import datetime, timezone
import psycopg2
from src.lib.config import Config
from src.lib.case_utils import canonicalize_case_number


def dump_history(conn, outpath: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM case_processing_history ORDER BY created_at ASC")
    rows = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]
    payload = [dict(zip(colnames, r)) for r in rows]
    with open(outpath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, default=str, indent=2)
    cur.close()
    return len(payload)


def upsert_snapshots_from_history(conn):
    cur = conn.cursor()
    # For each case_number, find latest record and upsert into snapshots
    cur.execute("""
        SELECT DISTINCT ON (court_file_no) * FROM case_processing_history ORDER BY court_file_no, started_at DESC
    """)
    rows = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]
    created = 0
    for r in rows:
        rec = dict(zip(colnames, r))
        court_file_no = canonicalize_case_number(rec.get('court_file_no'))
        last_outcome = rec.get('outcome')
        last_run_id = rec.get('run_id')
        last_processed_at = rec.get('completed_at') or rec.get('processed_at') or datetime.now(timezone.utc)
        # Basic upsert snapshot
        try:
            cur.execute("""
                INSERT INTO case_status_snapshots (case_number, court_file_no, last_outcome, last_run_id, last_processed_at, created_at, updated_at, is_active)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW(), TRUE)
                ON CONFLICT (case_number) DO UPDATE SET
                    last_outcome = EXCLUDED.last_outcome,
                    last_run_id = EXCLUDED.last_run_id,
                    last_processed_at = EXCLUDED.last_processed_at,
                    is_active = TRUE,
                    updated_at = NOW()
            """, (court_file_no, court_file_no, last_outcome, last_run_id, last_processed_at))
            created += 1
        except Exception:
            conn.rollback()
            continue
    conn.commit()
    cur.close()
    return created


def archive_history_table(conn, execute: bool = False):
    cur = conn.cursor()
    if execute:
        cur.execute("ALTER TABLE case_processing_history RENAME TO case_processing_history_archived")
        conn.commit()
        cur.close()
        return True
    else:
        cur.close()
        return False


def main():
    parser = argparse.ArgumentParser(description="Compact and optionally archive case_processing_history")
    parser.add_argument('--execute', action='store_true', help='Perform DB rename to archive')
    parser.add_argument('--backup', default='output/case_processing_history_backup.json', help='Backup JSON file path')
    args = parser.parse_args()

    cfg = Config.get_db_config()
    conn = psycopg2.connect(**cfg)
    print('Dumping history...')
    count = dump_history(conn, args.backup)
    print(f'Wrote {count} history rows to {args.backup}')
    print('Upserting snapshots...')
    created = upsert_snapshots_from_history(conn)
    print(f'Upserted/updated {created} snapshots')
    if args.execute:
        print('Archiving history table...')
        archived = archive_history_table(conn, execute=True)
        print('Archived' if archived else 'No archive performed')
    else:
        print('Dry-run: no archive performed. Re-run with --execute to rename the table.')
    conn.close()


if __name__ == '__main__':
    main()
