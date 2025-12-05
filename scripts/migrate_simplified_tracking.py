#!/usr/bin/env python3
"""
简化跟踪功能的数据库迁移脚本
在 cases 表中添加状态跟踪字段，替代复杂的跟踪表结构
"""

import psycopg2
import sys
import os
from datetime import datetime

# 添加 src 目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from lib.config import Config


def add_tracking_columns():
    """在 cases 表中添加跟踪字段"""
    db_config = {
        'host': Config.get_db_host(),
        'port': Config.get_db_port(),
        'database': Config.get_db_name(),
        'user': Config.get_db_user(),
        'password': Config.get_db_password()
    }
    
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        print("Adding tracking columns to cases table...")
        
        # 添加状态跟踪字段
        columns_to_add = [
            ("status", "VARCHAR(20) DEFAULT 'pending'"),
            ("last_attempt_at", "TIMESTAMP"),
            ("retry_count", "INTEGER DEFAULT 0"),
            ("error_message", "TEXT")
        ]
        
        for col_name, col_def in columns_to_add:
            try:
                cursor.execute(f"""
                    ALTER TABLE cases 
                    ADD COLUMN IF NOT EXISTS {col_name} {col_def}
                """)
                print(f"  ✓ Added column: {col_name}")
            except psycopg2.Error as e:
                if "already exists" not in str(e):
                    print(f"  ✗ Failed to add {col_name}: {e}")
        
        # 创建索引以提高查询性能
        indexes = [
            ("idx_cases_status", "status"),
            ("idx_cases_last_attempt", "last_attempt_at"),
            ("idx_cases_retry_count", "retry_count")
        ]
        
        for idx_name, col_name in indexes:
            try:
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS {idx_name} ON cases ({col_name})
                """)
                print(f"  ✓ Created index: {idx_name}")
            except psycopg2.Error as e:
                print(f"  ✗ Failed to create index {idx_name}: {e}")
        
        conn.commit()
        print("\n✓ Migration completed successfully!")
        
        # 显示更新后的表结构
        cursor.execute("""
            SELECT column_name, data_type, column_default 
            FROM information_schema.columns 
            WHERE table_name = 'cases' 
            ORDER BY ordinal_position
        """)
        columns = cursor.fetchall()
        
        print("\nUpdated cases table structure:")
        for col in columns:
            default = f" DEFAULT {col[2]}" if col[2] else ""
            print(f"  {col[0]}: {col[1]}{default}")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def cleanup_legacy_tables():
    """清理旧的跟踪表（可选）"""
    db_config = {
        'host': Config.get_db_host(),
        'port': Config.get_db_port(),
        'database': Config.get_db_name(),
        'user': Config.get_db_user(),
        'password': Config.get_db_password()
    }
    
    legacy_tables = [
        'case_processing_history',
        'probe_state', 
        'processing_runs',
        'case_status_snapshots'
    ]
    
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        
        print("\nCleaning up legacy tracking tables...")
        for table in legacy_tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                print(f"  ✓ Dropped table: {table}")
            except psycopg2.Error as e:
                print(f"  ✗ Failed to drop {table}: {e}")
        
        conn.commit()
        print("\n✓ Legacy tables cleanup completed!")
        
    except Exception as e:
        print(f"Cleanup failed: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    print("Starting simplified tracking migration...")
    add_tracking_columns()
    
    # 询问是否清理旧表
    response = input("\nDo you want to drop legacy tracking tables? (y/N): ").strip().lower()
    if response in ['y', 'yes']:
        cleanup_legacy_tables()
    
    print("\nMigration completed!")