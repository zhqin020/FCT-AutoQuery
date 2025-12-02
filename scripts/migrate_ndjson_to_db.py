#!/usr/bin/env python3
"""
Migration script to import historical NDJSON run logs into the database tracking system.

Run this script to migrate existing NDJSON data:
    python scripts/migrate_ndjson_to_db.py [--dry-run] [--since YYYY-MM-DD]
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.lib.config import Config
from src.lib.logging_config import get_logger, setup_logging
from src.services.case_tracking_service import CaseTrackingService

logger = get_logger()

class NDJSONMigrator:
    """Migrates NDJSON run logs to database tracking system."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.tracker = CaseTrackingService()
        self.migrated_runs = set()

    def find_ndjson_files(self, logs_dir: Path, since_date: Optional[datetime] = None) -> List[Path]:
        """Find NDJSON files to migrate."""
        files = []
        
        for file_path in logs_dir.glob("run_*.ndjson"):
            # Extract date from filename
            try:
                date_str = file_path.stem.split("_", 1)[1]  # Remove "run_" prefix
                file_date = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                file_date = file_date.replace(tzinfo=timezone.utc)
                
                if since_date is None or file_date >= since_date:
                    files.append((file_path, file_date))
            except ValueError:
                logger.warning(f"Could not parse date from filename: {file_path}")
                continue
        
        # Sort by date
        files.sort(key=lambda x: x[1])
        return [f[0] for f in files]

    def parse_ndjson_file(self, file_path: Path) -> Dict:
        """Parse a single NDJSON file."""
        data = {
            'run_info': None,
            'cases': [],
            'errors': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        record = json.loads(line)
                        
                        if record.get('type') == 'run_start':
                            data['run_info'] = record
                        elif record.get('type') == 'case':
                            data['cases'].append(record)
                        elif record.get('type') == 'run_end':
                            data['run_info'] = data['run_info'] or {}
                            data['run_info']['end_time'] = record.get('end_time')
                            
                    except json.JSONDecodeError as e:
                        data['errors'].append(f"Line {line_num}: JSON decode error - {e}")
                        
        except Exception as e:
            data['errors'].append(f"File read error - {e}")
        
        return data

    def migrate_run(self, file_path: Path, data: Dict) -> bool:
        """Migrate a single run to the database."""
        if not data['run_info']:
            logger.warning(f"No run info found in {file_path}")
            return False
        
        run_info = data['run_info']
        run_id = run_info['run_id']
        
        # Check if already migrated
        if run_id in self.migrated_runs:
            return True
        
        # Extract run parameters from filename
        filename = file_path.stem
        try:
            date_str = filename.split("_", 1)[1]
            start_time = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
            start_time = start_time.replace(tzinfo=timezone.utc)
        except ValueError:
            start_time = run_info.get('start_time')
            if start_time:
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        
        # Create run record
        if not self.dry_run:
            try:
                # Check if run already exists
                existing_runs = self.tracker.get_recent_runs(days=365)
                if any(r['run_id'] == run_id for r in existing_runs):
                    logger.info(f"Run {run_id} already exists in database, skipping")
                    self.migrated_runs.add(run_id)
                    return True
                
                # Insert run record
                conn = self.tracker.db_config
                import psycopg2
                db_conn = psycopg2.connect(**conn)
                cursor = db_conn.cursor()
                
                cursor.execute("""
                    INSERT INTO processing_runs 
                    (run_id, started_at, completed_at, mode, parameters, metadata, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %completed')
                    ON CONFLICT (run_id) DO NOTHING
                """, (
                    run_id,
                    start_time,
                    run_info.get('end_time'),
                    'migrated',  # Mark as migrated
                    {'source': 'ndjson', 'filename': str(file_path)},
                    {'migrated_at': datetime.now(timezone.utc).isoformat()},
                    'completed'
                ))
                
                db_conn.commit()
                cursor.close()
                db_conn.close()
                
            except Exception as e:
                logger.error(f"Failed to create run record for {run_id}: {e}")
                return False
        
        # Migrate case records
        success_count = 0
        for case_record in data['cases']:
            try:
                self.migrate_case_record(case_record, run_id, start_time)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to migrate case record: {e}")
        
        logger.info(f"Migrated run {run_id}: {success_count}/{len(data['cases'])} cases")
        self.migrated_runs.add(run_id)
        return True

    def migrate_case_record(self, case_record: Dict, run_id: str, default_start_time: datetime):
        """Migrate a single case record."""
        court_file_no = case_record['case_number']
        outcome = case_record['outcome']
        
        # Parse timestamps
        started_at = default_start_time
        completed_at = default_start_time
        
        if 'timestamp' in case_record:
            try:
                completed_at = datetime.fromisoformat(case_record['timestamp'].replace('Z', '+00:00'))
                started_at = completed_at  # NDJSON doesn't have start time
            except ValueError:
                pass
        
        # Map outcome values
        outcome_mapping = {
            'success': 'success',
            'failed': 'failed', 
            'skipped': 'skipped',
            'error': 'error',
            'failed-write': 'failed',
            'parse-error': 'error',
            'no-results': 'failed'
        }
        
        mapped_outcome = outcome_mapping.get(outcome, 'error')
        reason = case_record.get('reason')
        message = case_record.get('message')
        
        if not self.dry_run:
            self.tracker.record_case_processing(
                court_file_no=court_file_no,
                run_id=run_id,
                outcome=mapped_outcome,
                reason=reason,
                message=message,
                started_at=started_at,
                completed_at=completed_at,
                scrape_mode='migrated'
            )

    def migrate_all(self, logs_dir: Path, since_date: Optional[datetime] = None):
        """Migrate all NDJSON files."""
        files = self.find_ndjson_files(logs_dir, since_date)
        
        if not files:
            print("No NDJSON files found to migrate.")
            return
        
        print(f"Found {len(files)} NDJSON files to migrate")
        
        if self.dry_run:
            print("🔍 DRY RUN MODE - No data will be written to database")
        
        for file_path in files:
            print(f"\nProcessing: {file_path.name}")
            
            data = self.parse_ndjson_file(file_path)
            
            if data['errors']:
                print(f"  ⚠️  {len(data['errors'])} parsing errors")
                for error in data['errors'][:3]:  # Show first 3 errors
                    print(f"    {error}")
            
            if data['run_info']:
                run_id = data['run_info']['run_id']
                cases_count = len(data['cases'])
                print(f"  📋 Run {run_id}: {cases_count} cases")
                
                if self.migrate_run(file_path, data):
                    print(f"  ✅ Migrated successfully")
                else:
                    print(f"  ❌ Migration failed")
            else:
                print(f"  ❌ No run info found")

def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description="Migrate NDJSON run logs to database tracking")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be migrated without writing to database")
    parser.add_argument("--since", type=str, 
                       help="Only migrate files since YYYY-MM-DD")
    parser.add_argument("--logs-dir", type=str, default="logs",
                       help="Directory containing NDJSON files (default: logs)")
    
    args = parser.parse_args()
    
    setup_logging(log_level="INFO", log_file="logs/ndjson_migration.log")
    
    # Parse since date
    since_date = None
    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%Y-%m-%d")
            since_date = since_date.replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"Invalid date format: {args.since}. Use YYYY-MM-DD")
            sys.exit(1)
    
    # Check logs directory
    logs_dir = Path(args.logs_dir)
    if not logs_dir.exists():
        print(f"Logs directory not found: {logs_dir}")
        sys.exit(1)
    
    print("FCT AutoQuery - NDJSON to Database Migration")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No data will be written to database")
    if since_date:
        print(f"📅 Migrating files since: {since_date.strftime('%Y-%m-%d')}")
    print(f"📁 Logs directory: {logs_dir}")
    print()
    
    # Run migration
    try:
        migrator = NDJSONMigrator(dry_run=args.dry_run)
        migrator.migrate_all(logs_dir, since_date)
        
        print(f"\nMigration completed!")
        print(f"Runs processed: {len(migrator.migrated_runs)}")
        
        if args.dry_run:
            print("\nTo perform the actual migration, run without --dry-run")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()