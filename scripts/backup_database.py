#!/usr/bin/env python3
"""Database backup script for fct_db.

Usage:
    python scripts/backup_database.py [--format sql|custom] [--schema-only]

Examples:
    # Backup full database in custom format (compressed)
    python scripts/backup_database.py

    # Backup as SQL file
    python scripts/backup_database.py --format sql

    # Backup schema only
    python scripts/backup_database.py --schema-only
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add src to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from lib.config import Config
except ImportError:
    print("Error: Unable to import Config. Make sure you're in the project root.")
    sys.exit(1)


def backup_database(
    output_dir: str = "backups",
    format: str = "custom",
    schema_only: bool = False
) -> int:
    """Backup the fct_db database using pg_dump.

    Args:
        output_dir: Directory to save backup files
        format: Backup format - 'sql' or 'custom' (compressed)
        schema_only: If True, only backup schema without data

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Create backup directory
    backup_path = Path(output_dir)
    backup_path.mkdir(parents=True, exist_ok=True)

    # Get database config
    db_config = Config.get_db_config()
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    schema_suffix = "_schema" if schema_only else ""
    
    if format == "custom":
        filename = f"backup_fct_db{schema_suffix}_{timestamp}.backup"
        format_flag = "-F c"  # Custom format (compressed)
    else:
        filename = f"backup_fct_db{schema_suffix}_{timestamp}.sql"
        format_flag = "-F p"  # Plain SQL format

    output_file = backup_path / filename

    # Build pg_dump command
    cmd = [
        "pg_dump",
        "-h", db_config["host"],
        "-p", str(db_config["port"]),
        "-U", db_config["user"],
        "-d", db_config["database"],
    ]
    
    if format == "custom":
        cmd.extend(["-F", "c"])
    
    if schema_only:
        cmd.append("--schema-only")
    
    cmd.extend(["-f", str(output_file)])

    # Set password in environment
    env = os.environ.copy()
    env["PGPASSWORD"] = db_config["password"]

    print(f"Starting database backup...")
    print(f"Database: {db_config['database']}")
    print(f"Format: {format}")
    print(f"Schema only: {schema_only}")
    print(f"Output: {output_file}")
    print("-" * 60)

    try:
        # Execute pg_dump
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Check file was created
        if output_file.exists():
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"✓ Backup completed successfully!")
            print(f"  File: {output_file}")
            print(f"  Size: {size_mb:.2f} MB")
            return 0
        else:
            print(f"✗ Backup failed: File not created")
            return 1
            
    except subprocess.CalledProcessError as e:
        print(f"✗ Backup failed with error:")
        print(f"  {e.stderr}")
        return e.returncode
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Backup fct_db database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--format",
        choices=["sql", "custom"],
        default="custom",
        help="Backup format: 'sql' for plain SQL or 'custom' for compressed (default: custom)"
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Backup schema only, without data"
    )
    parser.add_argument(
        "--output-dir",
        default="backups",
        help="Output directory for backup files (default: backups)"
    )

    args = parser.parse_args()

    # Check if pg_dump is available
    try:
        subprocess.run(
            ["pg_dump", "--version"],
            capture_output=True,
            check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: pg_dump not found. Please install PostgreSQL client tools.")
        return 1

    return backup_database(
        output_dir=args.output_dir,
        format=args.format,
        schema_only=args.schema_only
    )


if __name__ == "__main__":
    sys.exit(main())
