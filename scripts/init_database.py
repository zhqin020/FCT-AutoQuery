#!/usr/bin/env python3
"""Database initialization script for Federal Court Case Scraper."""

import sys
import psycopg2
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.lib.config import Config
from src.lib.logging_config import get_logger

logger = get_logger()


def init_database():
    """Initialize the PostgreSQL database with required tables."""
    config = Config()
    db_config = config.database

    try:
        # Connect to database
        conn = psycopg2.connect(**db_config.__dict__)
        conn.autocommit = True
        cursor = conn.cursor()

        logger.info("Connected to database, initializing schema...")

        # Read schema file
        schema_path = Path(__file__).parent.parent / "src" / "lib" / "database_schema.sql"
        with open(schema_path, 'r') as f:
            schema_sql = f.read()

        # Execute schema
        cursor.execute(schema_sql)

        logger.info("Database schema initialized successfully")

        # Verify tables exist
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('cases', 'docket_entries')
            ORDER BY table_name
        """)

        tables = cursor.fetchall()
        table_names = [row[0] for row in tables]

        if 'cases' in table_names and 'docket_entries' in table_names:
            logger.info("✓ All required tables created: cases, docket_entries")
        else:
            logger.error(f"✗ Missing tables. Found: {table_names}")
            return False

        cursor.close()
        conn.close()

        logger.info("Database initialization complete")
        return True

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def main():
    """Main entry point."""
    print("Federal Court Case Scraper - Database Initialization")
    print("=" * 50)

    success = init_database()

    if success:
        print("\n✓ Database initialized successfully!")
        print("\nYou can now run the scraper:")
        print("  python -m src.cli.main single IMM-12345-25")
        print("  python -m src.cli.main batch 2025")
    else:
        print("\n✗ Database initialization failed!")
        print("Please check your database configuration and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()