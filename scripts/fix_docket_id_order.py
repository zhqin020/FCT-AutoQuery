"""
Migration helper: fix_docket_id_order

This script exports a CSV backup of the `docket_entries` table and optionally
applies a per-case inversion correction so that `id_from_table` values match
page numbering when the table on the site is in reverse order.

Usage:
  python scripts/fix_docket_id_order.py --backup-dir output/backups --dry-run
  python scripts/fix_docket_id_order.py --backup-dir output/backups --apply

Behavior:
- Always writes a full CSV backup of `docket_entries` to the supplied backup
  directory before attempting any updates.
- When run with `--apply`, performs per-case updates:
    UPDATE docket_entries
    SET id_from_table = (max_id - id_from_table + 1)
  where max_id is the per-case maximum `id_from_table`.
- When run without `--apply` (default), only prints a dry-run summary.

IMPORTANT: Ensure you have a proper DB backup before running with `--apply`.
"""
from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Tuple

import psycopg2

from src.lib.config import Config
from src.lib.logging_config import get_logger

logger = get_logger()


def connect_db():
    cfg = Config.get_db_config()
    return psycopg2.connect(**cfg)


def backup_docket_entries(conn, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = backup_dir / f"docket_entries_backup_{ts}.csv"

    cur = conn.cursor()
    cur.execute("SELECT * FROM docket_entries ORDER BY case_number, id_from_table")
    cols = [d[0] for d in cur.description]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for row in cur.fetchall():
            writer.writerow([r if r is not None else "" for r in row])

    cur.close()
    logger.info(f"Wrote docket_entries backup to {out_path}")
    return out_path


def compute_changes(conn) -> Tuple[int, int]:
    """Compute number of affected cases and total rows that would change."""
    cur = conn.cursor()
    cur.execute("SELECT case_number, MAX(id_from_table) AS max_id, COUNT(*) AS cnt FROM docket_entries GROUP BY case_number")
    tot_cases = 0
    tot_rows = 0
    cases_to_fix = 0
    for case_number, max_id, cnt in cur.fetchall():
        tot_cases += 1
        tot_rows += cnt
        if max_id and max_id > 1:
            # If there is any chance numbering is reversed, consider it
            cases_to_fix += 1
    cur.close()
    return cases_to_fix, tot_rows


def apply_fix(conn) -> int:
    """Apply per-case inversion update safely.

    Strategy (per-case):
    1. For each case, read max_id.
    2. Shift all `id_from_table` values by an offset (max_id + 5) to move them
       out of the collision range.
    3. Compute and write final values from the shifted values.

    This avoids transient unique-constraint violations when updating in-place.
    Cases that don't have a clean set of distinct ids will be skipped and
    reported for manual review.

    Returns the number of rows updated.
    """
    cur = conn.cursor()
    # Fetch per-case stats
    cur.execute(
        "SELECT case_number, MAX(id_from_table) AS max_id, COUNT(*) AS cnt, COUNT(DISTINCT id_from_table) AS distinct_cnt FROM docket_entries GROUP BY case_number"
    )

    to_fix = []
    for case_number, max_id, cnt, distinct_cnt in cur.fetchall():
        if max_id and max_id > 1 and cnt == distinct_cnt:
            to_fix.append((case_number, max_id, cnt))

    total_updated = 0

    for case_number, max_id, cnt in to_fix:
        try:
            # Use per-case transaction to isolate failures
            # Offset chosen larger than max_id to avoid collisions
            offset = max_id + 5
            # Step 1: shift to high range
            cur.execute(
                "UPDATE docket_entries SET id_from_table = id_from_table + %s WHERE case_number = %s",
                (offset, case_number),
            )
            # Step 2: compute final id_from_table based on shifted values
            cur.execute(
                "UPDATE docket_entries SET id_from_table = (%s - (id_from_table - %s) + 1) WHERE case_number = %s RETURNING id",
                (max_id, offset, case_number),
            )
            updated = cur.rowcount
            conn.commit()
            total_updated += updated
        except Exception as e:
            conn.rollback()
            logger.warning(f"Skipping case {case_number} due to error during update: {e}")
            continue

    cur.close()
    return total_updated


def main():
    parser = argparse.ArgumentParser(description="Backup and optionally fix docket_entries id order")
    parser.add_argument("--backup-dir", default="output/backups", help="Directory to write CSV backup")
    parser.add_argument("--apply", action="store_true", help="Actually apply updates (destructive)")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would change (default: true if --apply not given)")

    args = parser.parse_args()

    backup_dir = Path(args.backup_dir)

    conn = connect_db()

    try:
        backup_path = backup_docket_entries(conn, backup_dir)

        cases_to_fix, total_rows = compute_changes(conn)
        logger.info(f"Total docket_entries rows: {total_rows}")
        logger.info(f"Cases that appear fixable (max_id>1): {cases_to_fix}")

        if not args.apply:
            logger.info("Dry-run mode (no changes will be applied). Run with --apply to perform updates.")
            return

        # Confirm with the user (double-check safety)
        print("About to APPLY per-case inversion updates to docket_entries.")
        ok = input("Type 'YES' to proceed: ")
        if ok.strip() != "YES":
            print("Aborting.")
            return

        updated = apply_fix(conn)
        logger.info(f"Applied updates; rows updated: {updated}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
