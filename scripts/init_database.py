#!/usr/bin/env python3
"""Database initialization script for fct_db.

This script will:
1. Create the database and user if they don't exist
2. Set up proper permissions
3. Initialize database schema (tables, indexes, constraints)
4. Optionally load initial data

Usage:
    python scripts/init_database.py [--drop] [--schema-only]

Examples:
    # Initialize database with all tables
    python scripts/init_database.py

    # Drop existing database and recreate (DESTRUCTIVE!)
    python scripts/init_database.py --drop

    # Only create schema without data
    python scripts/init_database.py --schema-only
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Add src to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from lib.config import Config
    from lib.db import get_connection
except ImportError as e:
    print(f"Error: Unable to import required modules: {e}")
    print("Make sure you're in the project root and dependencies are installed.")
    sys.exit(1)


def run_sql_as_postgres(sql: str) -> tuple[bool, str]:
    """Execute SQL as postgres superuser.
    
    Args:
        sql: SQL command to execute
        
    Returns:
        Tuple of (success, output/error message)
    """
    try:
        # Connect as postgres user to create database/user
        result = subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-c", sql],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def create_database_and_user(db_config: dict, drop_existing: bool = False) -> bool:
    """Create database and user with proper permissions.
    
    Args:
        db_config: Database configuration dict
        drop_existing: If True, drop existing database before creating
        
    Returns:
        True if successful, False otherwise
    """
    db_name = db_config["database"]
    db_user = db_config["user"]
    db_password = db_config["password"]
    
    print("=" * 60)
    print("STEP 1: Creating Database and User")
    print("=" * 60)
    
    # Drop database if requested
    if drop_existing:
        print(f"⚠️  Dropping existing database: {db_name}")
        success, msg = run_sql_as_postgres(f"DROP DATABASE IF EXISTS {db_name};")
        if not success:
            print(f"  Warning: {msg}")
        else:
            print(f"  ✓ Database dropped")
        
        print(f"⚠️  Dropping existing user: {db_user}")
        success, msg = run_sql_as_postgres(f"DROP USER IF EXISTS {db_user};")
        if not success:
            print(f"  Warning: {msg}")
        else:
            print(f"  ✓ User dropped")
    
    # Create user
    print(f"Creating user: {db_user}")
    sql = f"CREATE USER {db_user} WITH PASSWORD '{db_password}';"
    success, msg = run_sql_as_postgres(sql)
    if not success:
        if "already exists" in msg.lower():
            print(f"  ℹ️  User already exists")
        else:
            print(f"  ✗ Failed to create user: {msg}")
            return False
    else:
        print(f"  ✓ User created")
    
    # Create database
    print(f"Creating database: {db_name}")
    sql = f"CREATE DATABASE {db_name} OWNER {db_user};"
    success, msg = run_sql_as_postgres(sql)
    if not success:
        if "already exists" in msg.lower():
            print(f"  ℹ️  Database already exists")
        else:
            print(f"  ✗ Failed to create database: {msg}")
            return False
    else:
        print(f"  ✓ Database created")
    
    # Grant privileges
    print(f"Granting privileges...")
    sqls = [
        f"GRANT ALL PRIVILEGES ON DATABASE {db_name} TO {db_user};",
        f"ALTER DATABASE {db_name} OWNER TO {db_user};"
    ]
    
    for sql in sqls:
        success, msg = run_sql_as_postgres(sql)
        if not success:
            print(f"  ✗ Failed: {msg}")
        else:
            print(f"  ✓ Privileges granted")
    
    return True


def initialize_schema(db_config: dict) -> bool:
    """Initialize database schema (tables, indexes, etc).
    
    Args:
        db_config: Database configuration dict
        
    Returns:
        True if successful, False otherwise
    """
    print("\n" + "=" * 60)
    print("STEP 2: Initializing Database Schema")
    print("=" * 60)
    
    # Check for SQL schema file
    schema_file = Path("scripts/schema.sql")
    if schema_file.exists():
        print(f"Found schema file: {schema_file}")
        return load_sql_file(db_config, schema_file)
    
    # Otherwise, use Python ORM to create tables
    print("Creating tables using ORM...")
    
    try:
        from lib.models import Base
        from sqlalchemy import create_engine
        
        # Create engine
        db_url = (
            f"postgresql://{db_config['user']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        )
        engine = create_engine(db_url)
        
        # Create all tables
        print("Creating tables...")
        Base.metadata.create_all(engine)
        print("  ✓ All tables created successfully")
        
        # Grant schema permissions
        with engine.connect() as conn:
            conn.execute("GRANT ALL ON SCHEMA public TO {db_config['user']};")
            conn.execute(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {db_config['user']};")
            conn.execute(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {db_config['user']};")
            conn.commit()
            print("  ✓ Schema permissions granted")
        
        return True
        
    except ImportError:
        print("  ✗ Error: Unable to import database models")
        print("  Please ensure SQLAlchemy and models are properly set up")
        return False
    except Exception as e:
        print(f"  ✗ Error creating schema: {e}")
        return False


def load_sql_file(db_config: dict, sql_file: Path) -> bool:
    """Load SQL file into database.
    
    Args:
        db_config: Database configuration dict
        sql_file: Path to SQL file
        
    Returns:
        True if successful, False otherwise
    """
    print(f"Loading SQL file: {sql_file}")
    
    env = os.environ.copy()
    env["PGPASSWORD"] = db_config["password"]
    
    cmd = [
        "psql",
        "-h", db_config["host"],
        "-p", str(db_config["port"]),
        "-U", db_config["user"],
        "-d", db_config["database"],
        "-f", str(sql_file)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        print("  ✓ SQL file loaded successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Failed to load SQL file:")
        print(f"    {e.stderr}")
        return False


def verify_connection(db_config: dict) -> bool:
    """Verify database connection.
    
    Args:
        db_config: Database configuration dict
        
    Returns:
        True if connection successful, False otherwise
    """
    print("\n" + "=" * 60)
    print("STEP 3: Verifying Connection")
    print("=" * 60)
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✓ Connection successful!")
        print(f"  PostgreSQL version: {version.split(',')[0]}")
        
        # List tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        if tables:
            print(f"\n  Created tables ({len(tables)}):")
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table[0]};")
                count = cursor.fetchone()[0]
                print(f"    - {table[0]} ({count} rows)")
        else:
            print("  ℹ️  No tables found (schema may need to be created)")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Initialize fct_db database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing database before creating (DESTRUCTIVE!)"
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only create schema, skip data loading"
    )
    parser.add_argument(
        "--skip-create",
        action="store_true",
        help="Skip database/user creation (useful if already exists)"
    )

    args = parser.parse_args()

    # Get database config
    db_config = Config.get_db_config()
    
    print(f"\nDatabase Initialization")
    print(f"Database: {db_config['database']}")
    print(f"User: {db_config['user']}")
    print(f"Host: {db_config['host']}:{db_config['port']}")
    
    # Confirm if dropping
    if args.drop:
        print("\n⚠️  WARNING: This will DELETE all existing data!")
        response = input("Continue? (yes/no): ")
        if response.lower() not in ("yes", "y"):
            print("Initialization cancelled.")
            return 0
    
    # Step 1: Create database and user
    if not args.skip_create:
        if not create_database_and_user(db_config, drop_existing=args.drop):
            print("\n✗ Failed to create database/user")
            return 1
    else:
        print("Skipping database/user creation...")
    
    # Step 2: Initialize schema
    if not initialize_schema(db_config):
        print("\n✗ Failed to initialize schema")
        return 1
    
    # Step 3: Verify connection
    if not verify_connection(db_config):
        print("\n✗ Failed to verify connection")
        return 1
    
    print("\n" + "=" * 60)
    print("✓ Database initialization completed successfully!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
