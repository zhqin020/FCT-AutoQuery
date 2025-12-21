#!/usr/bin/env python3
"""
Script to copy cases from original table to analysis table.

This script copies case records from the original 'cases' table to the 
dedicated 'case_analysis' table for analysis purposes.
"""

import sys
import logging
from pathlib import Path
from typing import Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fct_analysis.db_schema import AnalysisDBManager, AnalysisResultStorage
from lib.config import Config

def main(batch_size: Optional[int] = None, dry_run: bool = False):
    """Main copy function.
    
    Args:
        batch_size: Number of cases to copy in each batch (default: 1000)
        dry_run: If True, only show counts without copying
    """
    
    if batch_size is None:
        batch_size = 1000
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(__name__)
    
    print("Starting case copy to analysis table...")
    
    if dry_run:
        print("DRY RUN MODE - No data will be copied")
    
    # Initialize database manager
    db_manager = AnalysisDBManager()
    
    # Test connection
    if not db_manager.test_connection():
        print("ERROR: Cannot connect to database. Please check your configuration.")
        return 1
    
    print("✓ Database connection successful")
    
    # Check analysis table status
    schema_status = db_manager.check_analysis_table()
    if not schema_status.get('table_exists', False):
        print("ERROR: Analysis table does not exist. Please run migration first.")
        return 1
    
    print("✓ Analysis table exists")
    
    # Get database connection for direct queries
    try:
        from psycopg2 import connect, DatabaseError, OperationalError
        
        db_config = Config.get_db_config()
        with connect(**db_config) as conn:
            with conn.cursor() as cursor:
                # Count cases in original table with docket entries
                cursor.execute("""
                    SELECT COUNT(DISTINCT c.case_number) 
                    FROM cases c
                    INNER JOIN docket_entries d ON c.case_number = d.case_number
                """)
                total_cases = cursor.fetchone()[0]
                
                # Count cases already in analysis table
                cursor.execute("SELECT COUNT(*) FROM case_analysis")
                analysis_cases = cursor.fetchone()[0]
                
                # Count uncopied cases
                cursor.execute("""
                    SELECT COUNT(DISTINCT c.case_number) 
                    FROM cases c
                    INNER JOIN docket_entries d ON c.case_number = d.case_number
                    WHERE c.case_number NOT IN (SELECT DISTINCT case_number FROM case_analysis)
                """)
                uncopied_cases = cursor.fetchone()[0]
                
                print(f"\nCase counts:")
                print(f"  Original table (with docket entries): {total_cases:,}")
                print(f"  Analysis table: {analysis_cases:,}")
                print(f"  Not yet copied: {uncopied_cases:,}")
                
                if uncopied_cases == 0:
                    print("\n✓ All cases have been copied to analysis table")
                    return 0
                
                if dry_run:
                    print(f"\nWould copy {uncopied_cases:,} cases to analysis table")
                    return 0
                
                # Perform copy
                print(f"\nCopying {uncopied_cases:,} cases to analysis table...")
                
                copied = 0
                
                while copied < uncopied_cases:
                    cursor.execute("""
                        INSERT INTO case_analysis 
                        (case_number, title, court, filing_date, 
                         original_case_id, analysis_data, analysis_mode)
                        SELECT DISTINCT
                            c.case_number, c.style_of_cause, c.office, c.filing_date,
                            c.case_number, jsonb_build_object(
                                'case_type', c.case_type,
                                'type_of_action', c.type_of_action,
                                'nature_of_proceeding', c.nature_of_proceeding,
                                'language', c.language,
                                'html_content', c.html_content,
                                'scraped_at', c.scraped_at,
                                'status', c.status,
                                'docket_entries', (
                                    SELECT jsonb_agg(
                                        jsonb_build_object(
                                            'id', d.id_from_table,
                                            'case_id', d.case_number,
                                            'doc_id', d.id_from_table,
                                            'entry_date', d.date_filed,
                                            'entry_office', d.office,
                                            'summary', d.recorded_entry_summary
                                        )
                                    )
                                    FROM docket_entries d
                                    WHERE d.case_number = c.case_number
                                )
                            ), 'rule' as analysis_mode
                        FROM cases c
                        INNER JOIN docket_entries d ON c.case_number = d.case_number
                        WHERE c.case_number NOT IN (
                            SELECT DISTINCT case_number FROM case_analysis
                        )
                        ORDER BY c.case_number
                        LIMIT %s
                        ON CONFLICT (case_number) DO NOTHING
                    """, (batch_size,))
                    
                    batch_copied = cursor.rowcount
                    copied += batch_copied
                    conn.commit()
                    
                    print(f"  Copied {copied:,}/{uncopied_cases:,} cases...")
                    
                    if batch_copied == 0:
                        break
                
                print(f"\n✓ Successfully copied {copied:,} cases to analysis table")
                
                # Verify final count
                cursor.execute("SELECT COUNT(*) FROM case_analysis")
                final_count = cursor.fetchone()[0]
                print(f"✓ Analysis table now contains {final_count:,} cases")
                
                return 0
                
    except (OperationalError, DatabaseError) as e:
        logger.error(f"Database error: {e}")
        print(f"ERROR: Database operation failed: {e}")
        return 1

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Copy cases to analysis table")
    parser.add_argument("--batch-size", type=int, default=1000,
                       help="Batch size for copying (default: 1000)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show counts without copying data")
    
    args = parser.parse_args()
    
    sys.exit(main(batch_size=args.batch_size, dry_run=args.dry_run))