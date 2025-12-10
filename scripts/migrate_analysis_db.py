#!/usr/bin/env python3
"""
Database migration script for FCT analysis results.

This script sets up the database schema to support storing and retrieving
analysis results for individual cases.
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fct_analysis.db_schema import AnalysisDBManager

def main():
    """Main migration function."""
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("Starting database migration for FCT analysis...")
    
    # Initialize database manager
    db_manager = AnalysisDBManager()
    
    # Test connection
    if not db_manager.test_connection():
        print("ERROR: Cannot connect to database. Please check your configuration.")
        return 1
    
    print("✓ Database connection successful")
    
    # Check current schema
    schema_status = db_manager.check_analysis_table()
    print("\nCurrent schema status:")
    
    table_exists = schema_status.get('table_exists', False)
    print(f"  {'✓' if table_exists else '✗'} case_analysis table exists")
    
    if table_exists:
        for column, exists in schema_status.items():
            if column != 'table_exists':
                status = "✓" if exists else "✗"
                print(f"  {status} {column}")
    
    # Perform migration
    print("\nPerforming migration...")
    if db_manager.migrate_database(copy_cases=True):
        print("✓ Database migration completed successfully")
        print("✓ Cases copied to analysis table")
        
        # Verify schema after migration
        schema_status = db_manager.check_analysis_table()
        table_exists = schema_status.get('table_exists', False)
        
        if table_exists:
            print("✓ Analysis table is ready")
            return 0
        else:
            print("WARNING: Analysis table creation failed")
            return 1
    else:
        print("✗ Database migration failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())