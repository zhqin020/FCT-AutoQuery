#!/usr/bin/env python3
"""Database restore script for fct_db.

Usage:
    python scripts/restore_database.py <backup_file>

Examples:
    # Restore from custom format backup
    python scripts/restore_database.py backups/backup_fct_db_20260127_120000.backup

    # Restore from SQL file
    python scripts/restore_database.py backups/backup_fct_db_20260127_120000.sql
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
except ImportError:
    print("Error: Unable to import Config. Make sure you're in the project root.")
    sys.exit(1)


def restore_database(backup_file: Path) -> int:
    """Restore the fct_db database from a backup file.

    Args:
        backup_file: Path to the backup file (.backup or .sql)

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    if not backup_file.exists():
        print(f"✗ Error: Backup file not found: {backup_file}")
        return 1

    # Get database config
    db_config = Config.get_db_config()
    
    # Set password in environment
    env = os.environ.copy()
    env["PGPASSWORD"] = db_config["password"]

    print(f"Starting database restore...")
    print(f"Database: {db_config['database']}")
    print(f"Backup file: {backup_file}")
    print("-" * 60)

    # Determine restore method based on file extension
    if backup_file.suffix == ".backup":
        # Use pg_restore for custom format
        cmd = [
            "pg_restore",
            "-h", db_config["host"],
            "-p", str(db_config["port"]),
            "-U", db_config["user"],
            "-d", db_config["database"],
            "--clean",  # Drop existing objects before recreating
            "--if-exists",  # Don't error if objects don't exist
            str(backup_file)
        ]
        tool = "pg_restore"
    else:
        # Use psql for SQL files
        cmd = [
            "psql",
            "-h", db_config["host"],
            "-p", str(db_config["port"]),
            "-U", db_config["user"],
            "-d", db_config["database"],
            "-f", str(backup_file)
        ]
        tool = "psql"

    print(f"Using {tool} to restore database...")
    
    # Ask for confirmation
    response = input(f"\n⚠️  WARNING: This will overwrite the current database content.\nContinue? (yes/no): ")
    if response.lower() not in ("yes", "y"):
        print("Restore cancelled.")
        return 0

    try:
        # Execute restore command
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        
        print(f"✓ Database restored successfully!")
        return 0
            
    except subprocess.CalledProcessError as e:
        print(f"✗ Restore failed with error:")
        if e.stderr:
            print(f"  {e.stderr}")
        if e.stdout:
            print(f"  {e.stdout}")
        return e.returncode
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Restore fct_db database from backup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "backup_file",
        type=Path,
        help="Path to the backup file (.backup or .sql)"
    )

    args = parser.parse_args()

    # Check if required tools are available
    backup_file = args.backup_file
    tool = "pg_restore" if backup_file.suffix == ".backup" else "psql"
    
    try:
        subprocess.run(
            [tool, "--version"],
            capture_output=True,
            check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"Error: {tool} not found. Please install PostgreSQL client tools.")
        return 1

    return restore_database(args.backup_file)


if __name__ == "__main__":
    sys.exit(main())
