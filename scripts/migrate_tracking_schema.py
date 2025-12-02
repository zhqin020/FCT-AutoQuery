#!/usr/bin/env python3
"""Create database schema for case tracking system."""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.lib.config import Config
from src.lib.logging_config import get_logger
import psycopg2
from psycopg2.extras import RealDictCursor

logger = get_logger()


def create_tracking_schema():
    """Create the case tracking database schema."""
    
    # SQL statements for creating tables
    sql_statements = [
        # Case processing history table
        """
        CREATE TABLE IF NOT EXISTS case_processing_history (
            id SERIAL PRIMARY KEY,
            court_file_no VARCHAR(50) NOT NULL,
            run_id VARCHAR(50) NOT NULL,
            outcome VARCHAR(20) NOT NULL,
            reason TEXT,
            message TEXT,
            case_id VARCHAR(50),
            started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            completed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            duration_seconds FLOAT,
            attempt_count INTEGER DEFAULT 1,
            scrape_mode VARCHAR(20) DEFAULT 'single',
            metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        
        # Processing runs table
        """
        CREATE TABLE IF NOT EXISTS processing_runs (
            run_id VARCHAR(50) PRIMARY KEY,
            started_at TIMESTAMP WITH TIME ZONE NOT NULL,
            completed_at TIMESTAMP WITH TIME ZONE,
            processing_mode VARCHAR(20) NOT NULL,
            start_case_number INTEGER,
            max_cases INTEGER,
            force_mode BOOLEAN DEFAULT FALSE,
            config JSONB,
            total_cases_processed INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            error_count INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'running',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        # Probe state table (used to cache or persist probe information)
        """
        CREATE TABLE IF NOT EXISTS probe_state (
            case_number INTEGER NOT NULL,
            year_part INTEGER NOT NULL,
            exists BOOLEAN DEFAULT FALSE,
            first_checked_at TIMESTAMP WITH TIME ZONE,
            last_checked_at TIMESTAMP WITH TIME ZONE,
            run_id VARCHAR(50),
            PRIMARY KEY (case_number, year_part)
        );
        """,
        
        # Case status snapshots table
        """
        CREATE TABLE IF NOT EXISTS case_status_snapshots (
            court_file_no VARCHAR(50) PRIMARY KEY,
            last_processed_at TIMESTAMP WITH TIME ZONE,
            last_outcome VARCHAR(20),
            last_run_id VARCHAR(50),
            consecutive_failures INTEGER DEFAULT 0,
            last_success_at TIMESTAMP WITH TIME ZONE,
            total_attempts INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
        
        # Indexes will be created after the schema corrections to avoid failure when
        # running on databases with older schemas.
    ]
    
    config = Config()
    db_config = config.get_db_config()
    
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        logger.info("Creating case tracking database schema...")
        
        for sql in sql_statements:
            try:
                cursor.execute(sql)
                logger.info(f"Executed: {sql.strip().split()[0]} {sql.strip().split()[1] if len(sql.strip().split()) > 1 else ''}")
            except Exception as e:
                logger.error(f"Failed to execute SQL: {sql[:100]}... Error: {e}")
                raise
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info("Case tracking schema created successfully!")
        
        # Verify creation
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('case_processing_history', 'processing_runs', 'case_status_snapshots')
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        logger.info(f"Created/verified tables: {[t[0] for t in tables]}")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to create tracking schema: {e}")
        return False
    finally:
        # Ensure we attempt to add/alter columns that exist in older schema versions.
        try:
            conn = psycopg2.connect(**db_config)
            cursor = conn.cursor()

            # Add missing columns to case_processing_history
            cursor.execute("ALTER TABLE case_processing_history ADD COLUMN IF NOT EXISTS court_file_no VARCHAR(50);")
            cursor.execute("ALTER TABLE case_processing_history ADD COLUMN IF NOT EXISTS reason TEXT;")
            cursor.execute("ALTER TABLE case_processing_history ADD COLUMN IF NOT EXISTS message TEXT;")
            cursor.execute("ALTER TABLE case_processing_history ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE;")
            cursor.execute("ALTER TABLE case_processing_history ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;")
            cursor.execute("ALTER TABLE case_processing_history ADD COLUMN IF NOT EXISTS duration_seconds FLOAT;")
            cursor.execute("ALTER TABLE case_processing_history ADD COLUMN IF NOT EXISTS attempt_count INTEGER DEFAULT 1;")
            cursor.execute("ALTER TABLE case_processing_history ADD COLUMN IF NOT EXISTS scrape_mode VARCHAR(20);")
            cursor.execute("ALTER TABLE case_processing_history ADD COLUMN IF NOT EXISTS metadata JSONB;")

            # Try to populate court_file_no from older case_number column if present
            cursor.execute("\n                DO $$\n                BEGIN\n                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='case_processing_history' AND column_name='case_number') THEN\n                        UPDATE case_processing_history SET court_file_no = case_number WHERE court_file_no IS NULL;\n                    END IF;\n                END$$;\n            ")

            # Ensure processing_runs has consistent names
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS processing_mode VARCHAR(20);")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS start_case_number INTEGER;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS max_cases INTEGER;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS force_mode BOOLEAN;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS config JSONB;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS total_cases_processed INTEGER DEFAULT 0;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS success_count INTEGER DEFAULT 0;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS failed_count INTEGER DEFAULT 0;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS skipped_count INTEGER DEFAULT 0;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS error_count INTEGER DEFAULT 0;")
            cursor.execute("ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'running';")

            cursor.execute("\n                DO $$\n                BEGIN\n                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='processing_runs' AND column_name='start_time') THEN\n                        UPDATE processing_runs SET started_at = start_time WHERE started_at IS NULL;\n                    END IF;\n                END$$;\n            ")

            # case_status_snapshots columns
            cursor.execute("ALTER TABLE case_status_snapshots ADD COLUMN IF NOT EXISTS court_file_no VARCHAR(50);")
            cursor.execute("ALTER TABLE case_status_snapshots ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")
            cursor.execute("ALTER TABLE case_status_snapshots ADD COLUMN IF NOT EXISTS total_attempts INTEGER DEFAULT 0;")
            cursor.execute("ALTER TABLE case_status_snapshots ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMP WITH TIME ZONE;")

            cursor.execute("\n                DO $$\n                BEGIN\n                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='case_status_snapshots' AND column_name='case_number') THEN\n                        UPDATE case_status_snapshots SET court_file_no = case_number WHERE court_file_no IS NULL;\n                    END IF;\n                END$$;\n            ")

            # Ensure unique constraint for case_processing_history (court_file_no, run_id)
            cursor.execute("\n+                DO $$\n+                BEGIN\n+                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uniq_case_run') THEN\n+                        ALTER TABLE case_processing_history ADD CONSTRAINT uniq_case_run UNIQUE (court_file_no, run_id);\n+                    END IF;\n+                END$$;\n+            ")

            # Create probe_state table if missing (for older dbs)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS probe_state (
                    case_number INTEGER NOT NULL,
                    year_part INTEGER NOT NULL,
                    exists BOOLEAN DEFAULT FALSE,
                    first_checked_at TIMESTAMP WITH TIME ZONE,
                    last_checked_at TIMESTAMP WITH TIME ZONE,
                    run_id VARCHAR(50),
                    PRIMARY KEY (case_number, year_part)
                );
            """)

            conn.commit()
            cursor.close()
            conn.close()

            # Create indexes after schema correction to ensure columns exist
            conn = psycopg2.connect(**db_config)
            cursor = conn.cursor()
            index_statements = [
                """
                CREATE INDEX IF NOT EXISTS idx_case_processing_history_run_id ON case_processing_history(run_id);
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_case_processing_history_court_file_no ON case_processing_history(court_file_no);
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_case_processing_history_started_at ON case_processing_history(started_at);
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_processing_runs_started_at ON processing_runs(started_at);
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_case_status_snapshots_last_processed_at ON case_status_snapshots(last_processed_at);
                """,
                """
                CREATE INDEX IF NOT EXISTS idx_case_status_snapshots_last_outcome ON case_status_snapshots(last_outcome);
                """,
            ]

            for sql in index_statements:
                try:
                    cursor.execute(sql)
                    logger.info(f"Executed: {sql.strip().split()[0]} {sql.strip().split()[1] if len(sql.strip().split()) > 1 else ''}")
                except Exception as e:
                    logger.debug(f"Index creation failed (non-fatal): {sql[:100]}... Error: {e}")

            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            # Non-fatal; log and continue
            logger.debug("Non-fatal post-creation schema corrections failed; continuing.")


if __name__ == "__main__":
    success = create_tracking_schema()
    if success:
        print("✅ Case tracking schema created successfully!")
        sys.exit(0)
    else:
        print("❌ Failed to create case tracking schema!")
        sys.exit(1)