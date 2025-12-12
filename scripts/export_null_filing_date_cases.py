#!/usr/bin/env python3
"""
导出所有 filing_date IS NULL AND status='success' 的记录到 JSON 文件
包括 case 信息和最后一个 docket_entries 记录
"""

import json
import psycopg2
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.lib.config import Config


def get_database_connection():
    """获取数据库连接"""
    db_config = Config.get_db_config()
    return psycopg2.connect(**db_config)


def export_null_filing_date_cases(output_file: str = "output/null_filing_date_cases.json") -> None:
    """
    导出所有 filing_date IS NULL AND status='success' 的记录
    
    Args:
        output_file: 输出 JSON 文件路径
    """
    conn = get_database_connection()
    cur = conn.cursor()
    
    try:
        # 查询符合条件的 cases
        print("查询符合条件的 cases...")
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
        
        cases = cur.fetchall()
        print(f"找到 {len(cases)} 条符合条件的记录")
        
        # 获取列名
        column_names = [desc[0] for desc in cur.description]
        
        exported_data = []
        
        for i, case_row in enumerate(cases):
            case_dict = dict(zip(column_names, case_row))
            case_number = case_dict['case_number']
            
            print(f"处理第 {i+1}/{len(cases)} 条记录: {case_number}")
            
            # 查询该 case 的最后一个 docket_entries
            cur.execute("""
                SELECT 
                    id,
                    case_number,
                    id_from_table,
                    date_filed,
                    office,
                    recorded_entry_summary
                FROM docket_entries 
                WHERE case_number = %s
                ORDER BY date_filed DESC, id DESC
                LIMIT 1
            """, (case_number,))
            
            docket_row = cur.fetchone()
            docket_data = None
            
            if docket_row:
                docket_columns = [desc[0] for desc in cur.description]
                docket_data = dict(zip(docket_columns, docket_row))
            
            # 将 docket 数据添加到 case 数据中
            case_dict['docket_entry'] = docket_data
            
            # 移除可能过大的 html_content 字段（如果需要的话）
            if 'html_content' in case_dict and case_dict['html_content']:
                # 只保留前 1000 个字符作为预览
                html_content = case_dict['html_content']
                if len(html_content) > 1000:
                    case_dict['html_content_preview'] = html_content[:1000] + '...'
                    case_dict['html_content_length'] = len(html_content)
                    del case_dict['html_content']
            
            exported_data.append(case_dict)
        
        # 确保输出目录存在
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入 JSON 文件
        print(f"写入 JSON 文件到: {output_path}")
        export_result = {
            "export_timestamp": datetime.now().isoformat(),
            "total_records": len(exported_data),
            "query_condition": "filing_date IS NULL AND status = 'success'",
            "cases": exported_data
        }
        
        with output_path.open('w', encoding='utf-8') as f:
            json.dump(export_result, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"导出完成！")
        print(f"- 总记录数: {len(exported_data)}")
        print(f"- 输出文件: {output_path}")
        print(f"- 文件大小: {output_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        # 显示一些统计信息
        with_docket = sum(1 for case in exported_data if case['docket_entry'] is not None)
        print(f"- 有 docket_entries 的记录: {with_docket}")
        print(f"- 无 docket_entries 的记录: {len(exported_data) - with_docket}")
        
        # 按年份统计
        year_stats = {}
        for case in exported_data:
            case_num = case['case_number']
            if '-' in case_num:
                year_suffix = case_num.split('-')[-1]
                try:
                    year = 2000 + int(year_suffix)
                    year_stats[year] = year_stats.get(year, 0) + 1
                except ValueError:
                    pass
        
        print(f"\n按年份统计:")
        for year in sorted(year_stats.keys()):
            print(f"  {year}: {year_stats[year]} 条记录")
        
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    export_null_filing_date_cases()