#!/usr/bin/env python3
"""
简化的NDJSON到数据库迁移工具

用于一次性迁移现有NDJSON数据到新的跟踪系统数据库。
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.lib.logging_config import get_logger, setup_logging
from src.services.case_tracking_service import CaseTrackingService

logger = get_logger()


class SimpleNDJSONMigrator:
    """简化的NDJSON迁移器"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.tracker = CaseTrackingService() if not dry_run else None
        self.migrated_runs = set()
    
    def find_ndjson_files(self, logs_dir: str) -> List[Path]:
        """查找所有NDJSON文件"""
        logs_path = Path(logs_dir)
        if not logs_path.exists():
            return []
        
        return list(logs_path.glob("run_*.ndjson"))
    
    def parse_ndjson_file(self, file_path: Path) -> Dict:
        """解析NDJSON文件"""
        data = {
            'run_start': None,
            'run_end': None,
            'cases': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        record = json.loads(line)
                        record_type = record.get('type')
                        
                        if record_type == 'run_start':
                            data['run_start'] = record
                        elif record_type == 'run_end':
                            data['run_end'] = record
                        elif record_type == 'case':
                            data['cases'].append(record)
                        else:
                            logger.warning(f"Unknown record type {record_type} in {file_path}:{line_num}")
                    
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in {file_path}:{line_num}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
        
        return data
    
    def migrate_file(self, file_path: Path) -> bool:
        """迁移单个NDJSON文件"""
        print(f"处理文件: {file_path}")
        
        data = self.parse_ndjson_file(file_path)
        if not data['run_start']:
            logger.warning(f"No run_start record in {file_path}")
            return False
        
        run_start = data['run_start']
        run_id = run_start.get('run_id')
        if not run_id:
            logger.warning(f"No run_id in {file_path}")
            return False
        
        if run_id in self.migrated_runs:
            logger.info(f"Run {run_id} already migrated")
            return True
        
        # 提取运行信息
        start_time = run_start.get('timestamp')
        if start_time:
            try:
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except ValueError:
                start_time = datetime.now(timezone.utc)
        else:
            start_time = datetime.now(timezone.utc)
        
        processing_mode = run_start.get('mode', 'unknown')
        config = run_start.get('config', {})
        
        if self.dry_run:
            print(f"  [DRY RUN] 将创建运行记录: {run_id}")
            print(f"  [DRY RUN] 模式: {processing_mode}, 开始时间: {start_time}")
        else:
            # 创建运行记录
            actual_run_id = self.tracker.start_run(
                processing_mode=processing_mode,
                start_case_number=config.get('start'),
                max_cases=config.get('max_cases'),
                force_mode=config.get('force', False)
            )
        
        # 迁移案例记录
        success_count = 0
        for case_record in data['cases']:
            try:
                self.migrate_case_record(case_record, run_id, start_time)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to migrate case record: {e}")
        
        print(f"  迁移了 {success_count}/{len(data['cases'])} 个案例记录")
        self.migrated_runs.add(run_id)
        return True
    
    def migrate_case_record(self, case_record: Dict, run_id: str, default_start_time: datetime):
        """迁移单个案例记录"""
        court_file_no = case_record['case_number']
        outcome = case_record['outcome']
        
        # 解析时间戳
        processed_at = default_start_time
        if 'timestamp' in case_record:
            try:
                processed_at = datetime.fromisoformat(case_record['timestamp'].replace('Z', '+00:00'))
            except ValueError:
                pass
        
        # 映射结果值
        outcome_mapping = {
            'success': 'success',
            'failed': 'failed',
            'skipped': 'skipped',
            'error': 'error',
            'failed-write': 'failed',
            'parse-error': 'error',
            'no-results': 'failed'
        }
        
        mapped_outcome = outcome_mapping.get(outcome, 'error')
        case_id = case_record.get('case_id')
        details = case_record.get('details')
        error_message = case_record.get('message') or case_record.get('reason')
        
        if self.dry_run:
            print(f"    [DRY RUN] 案例 {court_file_no}: {mapped_outcome}")
        else:
            self.tracker.record_case_processing(
                court_file_no=court_file_no,
                run_id=run_id,
                processing_mode='migrated',
                outcome=mapped_outcome,
                processed_at=processed_at,
                case_id=case_id,
                details=details,
                error_message=error_message
            )
    
    def migrate_all(self, logs_dir: str):
        """迁移所有NDJSON文件"""
        ndjson_files = self.find_ndjson_files(logs_dir)
        
        if not ndjson_files:
            print(f"在 {logs_dir} 中没有找到NDJSON文件")
            return
        
        print(f"找到 {len(ndjson_files)} 个NDJSON文件")
        
        success_count = 0
        for file_path in sorted(ndjson_files):
            if self.migrate_file(file_path):
                success_count += 1
        
        print(f"\n迁移完成: {success_count}/{len(ndjson_files)} 个文件成功")
        print(f"处理的运行记录: {len(self.migrated_runs)}")


def main():
    parser = argparse.ArgumentParser(description="迁移NDJSON日志文件到数据库")
    parser.add_argument("--ndjson-dir", default="logs", help="NDJSON文件目录")
    parser.add_argument("--dry-run", action="store_true", help="仅显示将要执行的操作")
    parser.add_argument("--cleanup", action="store_true", help="迁移完成后清理NDJSON文件")
    parser.add_argument("--backup-dir", default="logs/backup", help="清理时备份目录")
    
    args = parser.parse_args()
    
    setup_logging(log_level="INFO", log_file="logs/ndjson_migration.log")
    
    print("FCT AutoQuery - NDJSON to Database Migration")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 DRY RUN MODE - No data will be written to database")
    
    # 运行迁移
    try:
        migrator = SimpleNDJSONMigrator(dry_run=args.dry_run)
        migrator.migrate_all(args.ndjson_dir)
        
        # 如果指定了清理选项，则执行清理
        if args.cleanup and not args.dry_run:
            print("\n=== 迁移完成，开始清理NDJSON文件 ===")
            from scripts.cleanup_legacy_ndjson import (
                find_ndjson_files, backup_ndjson_files, remove_ndjson_files
            )
            
            ndjson_files = find_ndjson_files(args.ndjson_dir)
            if ndjson_files:
                print(f"找到 {len(ndjson_files)} 个NDJSON文件需要清理")
                
                # 备份文件
                if backup_ndjson_files(ndjson_files, args.backup_dir):
                    print("备份完成")
                    
                    # 删除文件
                    if remove_ndjson_files(ndjson_files):
                        print("NDJSON文件清理完成")
                    else:
                        print("部分文件删除失败")
                else:
                    print("备份失败，跳过删除操作")
            else:
                print("没有找到NDJSON文件")
        
        if args.dry_run:
            print("\n要执行实际迁移，请运行不带 --dry-run 的命令")
            if args.cleanup:
                print("要执行清理，请同时使用 --cleanup 参数（不带 --dry-run）")
    
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()