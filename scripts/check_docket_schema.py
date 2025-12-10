#!/usr/bin/env python3
"""
Check docket_entries table structure.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lib.config import Config
from psycopg2 import connect

def check_docket_schema():
    """Check docket_entries table structure."""
    db_config = Config.get_db_config()
    
    try:
        with connect(**db_config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns 
                    WHERE table_name = 'docket_entries' 
                    AND table_schema = 'public'
                    ORDER BY ordinal_position
                """)
                columns = cursor.fetchall()
                print('Docket entries table structure:')
                for col_name, data_type, is_nullable in columns:
                    null_status = "NULL" if is_nullable == "YES" else "NOT NULL"
                print(f'  - {col_name}: {data_type} ({null_status})')
                
                cursor.execute('SELECT COUNT(*) FROM docket_entries')
                count = cursor.fetchone()[0]
                print(f'\nTotal docket entries: {count}')
                
                # Get sample
                cursor.execute('SELECT * FROM docket_entries LIMIT 2')
                rows = cursor.fetchall()
                col_names = [desc[0] for desc in cursor.description]
                print(f'\nSample data:')
                for i, row in enumerate(rows, 1):
                    print(f'  Row {i}: {dict(zip(col_names, row))}')
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_docket_schema()