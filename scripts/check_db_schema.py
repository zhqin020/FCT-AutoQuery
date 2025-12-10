#!/usr/bin/env python3
"""
Check database schema to understand actual table structure.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lib.config import Config
from psycopg2 import connect, DatabaseError, OperationalError

def check_schema():
    """Check actual database schema."""
    db_config = Config.get_db_config()
    
    try:
        with connect(**db_config) as conn:
            with conn.cursor() as cursor:
                # List all tables
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
                tables = [row[0] for row in cursor.fetchall()]
                print("Available tables:")
                for table in tables:
                    print(f"  - {table}")
                
                # Check cases table structure
                if 'cases' in tables:
                    cursor.execute("""
                        SELECT column_name, data_type, is_nullable
                        FROM information_schema.columns 
                        WHERE table_name = 'cases' 
                        AND table_schema = 'public'
                        ORDER BY ordinal_position
                    """)
                    columns = cursor.fetchall()
                    print(f"\nCases table structure:")
                    for col_name, data_type, is_nullable in columns:
                        print(f"  - {col_name}: {data_type} ({'NULL' if is_nullable == 'YES' else 'NOT NULL'})")
                
                # Get sample data count
                cursor.execute("SELECT COUNT(*) FROM cases")
                count = cursor.fetchone()[0]
                print(f"\nTotal cases: {count}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_schema()