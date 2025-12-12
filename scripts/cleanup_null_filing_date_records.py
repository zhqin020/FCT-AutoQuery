#!/usr/bin/env python3
"""
将所有 filing_date IS NULL AND status='success' 的记录的 status 改为 'failed'，
并删除该记录相关的 docket_entries 记录

这个脚本执行不可逆的数据清理操作，请谨慎使用！
"""

import psycopg2
from datetime import datetime
from typing import Dict, List, Tuple
from pathlib import Path

from src.lib.config import Config


def get_database_connection():
    """获取数据库连接"""
    db_config = Config.get_db_config()
    return psycopg2.connect(**db_config)


def analyze_affected_records() -> Tuple[int, List[Dict]]:
    """
    分析将要影响的记录
    
    Returns:
        Tuple[int, List[Dict]]: (总记录数, 记录详情列表)
    """
    conn = get_database_connection()
    cur = conn.cursor()
    
    try:
        print("=== 分析将要影响的记录 ===")
        
        # 查询符合条件的记录
        cur.execute("""
            SELECT 
                c.case_number,
                c.case_type,
                c.filing_date,
                c.scraped_at,
                c.status,
                COUNT(de.id) as docket_count
            FROM cases c
            LEFT JOIN docket_entries de ON c.case_number = de.case_number
            WHERE c.filing_date IS NULL AND c.status = 'success'
            GROUP BY c.case_number, c.case_type, c.filing_date, c.scraped_at, c.status
            ORDER BY c.case_number
            LIMIT 10
        """)
        
        records = []
        for row in cur.fetchall():
            records.append({
                'case_number': row[0],
                'case_type': row[1],
                'filing_date': row[2],
                'scraped_at': row[3],
                'status': row[4],
                'docket_count': row[5]
            })
        
        # 获取总数
        cur.execute("""
            SELECT COUNT(*)
            FROM cases 
            WHERE filing_date IS NULL AND status = 'success'
        """)
        total_count = cur.fetchone()[0]
        
        # 获取将要删除的 docket_entries 总数
        cur.execute("""
            SELECT COUNT(DISTINCT de.id)
            FROM cases c
            INNER JOIN docket_entries de ON c.case_number = de.case_number
            WHERE c.filing_date IS NULL AND c.status = 'success'
        """)
        total_docket_count = cur.fetchone()[0]
        
        print(f"找到 {total_count} 条 case 记录需要更新")
        print(f"将要删除 {total_docket_count} 条 docket_entries 记录")
        print("\n前 10 条记录示例:")
        for i, record in enumerate(records[:10], 1):
            print(f"  {i}. {record['case_number']} | {record['case_type']} | "
                  f"docket_count: {record['docket_count']} | scraped_at: {record['scraped_at']}")
        
        if len(records) < total_count:
            print(f"  ... 还有 {total_count - len(records)} 条记录")
        
        return total_count, records
        
    finally:
        cur.close()
        conn.close()


def create_backup() -> str:
    """
    创建备份数据
    
    Returns:
        str: 备份文件路径
    """
    backup_dir = Path("output/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"null_filing_date_cleanup_backup_{timestamp}.json"
    
    conn = get_database_connection()
    cur = conn.cursor()
    
    try:
        print(f"\n=== 创建备份数据到 {backup_file} ===")
        
        # 查询所有要删除的 docket_entries
        cur.execute("""
            SELECT 
                de.id,
                de.case_number,
                de.id_from_table,
                de.date_filed,
                de.office,
                de.recorded_entry_summary
            FROM docket_entries de
            INNER JOIN cases c ON de.case_number = c.case_number
            WHERE c.filing_date IS NULL AND c.status = 'success'
            ORDER BY de.case_number, de.date_filed
        """)
        
        docket_columns = [desc[0] for desc in cur.description]
        docket_entries = []
        for row in cur.fetchall():
            docket_entries.append(dict(zip(docket_columns, row)))
        
        # 查询所有要更新的 cases
        cur.execute("""
            SELECT 
                case_number,
                case_type,
                type_of_action,
                nature_of_proceeding,
                filing_date,
                office,
                style_of_cause,
                language,
                html_content,
                scraped_at,
                status,
                last_attempt_at,
                retry_count,
                error_message
            FROM cases 
            WHERE filing_date IS NULL AND status = 'success'
            ORDER BY case_number
        """)
        
        case_columns = [desc[0] for desc in cur.description]
        cases = []
        for row in cur.fetchall():
            case_data = dict(zip(case_columns, row))
            # 处理 html_content 大小
            if case_data.get('html_content') and len(case_data['html_content']) > 1000:
                case_data['html_content_preview'] = case_data['html_content'][:1000] + '...'
                case_data['html_content_length'] = len(case_data['html_content'])
                del case_data['html_content']
            cases.append(case_data)
        
        # 保存备份文件
        import json
        backup_data = {
            "backup_timestamp": datetime.now().isoformat(),
            "operation": "null_filing_date_cleanup",
            "description": "Backup before updating case status to 'failed' and deleting docket_entries",
            "cases_to_update": {
                "count": len(cases),
                "data": cases
            },
            "docket_entries_to_delete": {
                "count": len(docket_entries),
                "data": docket_entries
            }
        }
        
        with backup_file.open('w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"备份完成:")
        print(f"  - Cases: {len(cases)} 条记录")
        print(f"  - Docket entries: {len(docket_entries)} 条记录")
        print(f"  - 文件大小: {backup_file.stat().st_size / 1024 / 1024:.2f} MB")
        
        return str(backup_file)
        
    finally:
        cur.close()
        conn.close()


def execute_cleanup(backup_file: str) -> Dict[str, int]:
    """
    执行清理操作
    
    Args:
        backup_file: 备份文件路径
        
    Returns:
        Dict[str, int]: 操作结果统计
    """
    conn = get_database_connection()
    cur = conn.cursor()
    
    try:
        print("\n=== 执行清理操作 ===")
        
        # 开始事务
        conn.autocommit = False
        
        try:
            # 1. 首先删除相关的 docket_entries
            print("删除相关的 docket_entries 记录...")
            cur.execute("""
                DELETE FROM docket_entries 
                WHERE case_number IN (
                    SELECT case_number FROM cases 
                    WHERE filing_date IS NULL AND status = 'success'
                )
            """)
            docket_deleted = cur.rowcount
            print(f"删除了 {docket_deleted} 条 docket_entries 记录")
            
            # 2. 更新 cases 的 status 为 'failed'
            print("更新 cases 的 status 为 'failed'...")
            cur.execute("""
                UPDATE cases 
                SET status = 'failed',
                    last_attempt_at = NOW(),
                    error_message = 'Status changed to failed due to null filing_date cleanup operation'
                WHERE filing_date IS NULL AND status = 'success'
            """)
            cases_updated = cur.rowcount
            print(f"更新了 {cases_updated} 条 cases 记录")
            
            # 提交事务
            conn.commit()
            print("事务已提交")
            
            # 验证结果
            cur.execute("""
                SELECT COUNT(*)
                FROM cases 
                WHERE filing_date IS NULL AND status = 'success'
            """)
            remaining_count = cur.fetchone()[0]
            
            result = {
                'cases_updated': cases_updated,
                'docket_entries_deleted': docket_deleted,
                'remaining_null_filing_date_success': remaining_count,
                'backup_file': backup_file
            }
            
            print(f"\n=== 操作完成 ===")
            print(f"更新的 cases: {cases_updated}")
            print(f"删除的 docket_entries: {docket_deleted}")
            print(f"剩余的 null filing_date & success 记录: {remaining_count}")
            print(f"备份文件: {backup_file}")
            
            return result
            
        except Exception as e:
            # 回滚事务
            conn.rollback()
            print(f"操作失败，已回滚: {e}")
            raise
            
    finally:
        cur.close()
        conn.close()


def confirm_operation(total_cases: int, total_dockets: int) -> bool:
    """
    确认操作
    
    Args:
        total_cases: 将要更新的 case 数量
        total_dockets: 将要删除的 docket 数量
        
    Returns:
        bool: 用户是否确认操作
    """
    print(f"\n⚠️  警告：此操作将不可逆地修改数据库！")
    print(f"   - 将更新 {total_cases} 条 case 记录的状态从 'success' 改为 'failed'")
    print(f"   - 将删除 {total_dockets} 条 docket_entries 记录")
    print(f"   - 系统将自动创建备份文件")
    
    while True:
        response = input("\n确认执行此操作吗？(yes/no): ").strip().lower()
        if response in ['yes', 'y']:
            return True
        elif response in ['no', 'n']:
            print("操作已取消")
            return False
        else:
            print("请输入 'yes' 或 'no'")


def main():
    """主函数"""
    print("=== Null Filing Date 清理工具 ===")
    print("此工具将把 filing_date IS NULL AND status='success' 的记录:")
    print("1. status 改为 'failed'")
    print("2. 删除相关的 docket_entries 记录")
    print()
    
    # 1. 分析影响的记录
    total_cases, sample_records = analyze_affected_records()
    
    if total_cases == 0:
        print("没有找到需要处理的记录")
        return
    
    # 2. 查询将要删除的 docket_entries 数量
    conn = get_database_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT de.id)
        FROM cases c
        INNER JOIN docket_entries de ON c.case_number = de.case_number
        WHERE c.filing_date IS NULL AND c.status = 'success'
    """)
    total_dockets = cur.fetchone()[0]
    cur.close()
    conn.close()
    
    # 3. 确认操作
    if not confirm_operation(total_cases, total_dockets):
        return
    
    # 4. 创建备份
    backup_file = create_backup()
    
    # 5. 执行清理操作
    result = execute_cleanup(backup_file)
    
    print("\n操作摘要:")
    for key, value in result.items():
        if key != 'backup_file':
            print(f"  {key}: {value}")
    print(f"  backup_file: {result['backup_file']}")


if __name__ == "__main__":
    main()