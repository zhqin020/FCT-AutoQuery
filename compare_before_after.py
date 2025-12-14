#!/usr/bin/env python3
"""Compare data before and after status filtering."""

from src.fct_analysis.database import DatabaseReader
from psycopg2 import connect
from lib.config import Config

def compare_status_filtering():
    print('=== 比较状态过滤前后的数据量 ===')
    
    db_config = Config.get_db_config()
    
    try:
        with connect(**db_config) as conn:
            with conn.cursor() as cursor:
                # 获取所有案例
                cursor.execute("SELECT COUNT(*) FROM cases WHERE case_number LIKE '%-25'")
                total_2025 = cursor.fetchone()[0]
                
                # 获取success状态的案例
                cursor.execute("SELECT COUNT(*) FROM cases WHERE case_number LIKE '%-25' AND status = 'success'")
                success_2025 = cursor.fetchone()[0]
                
                print(f'2025年案例总数: {total_2025}')
                print(f'2025年success状态案例: {success_2025}')
                print(f'过滤比例: {success_2025/total_2025*100:.1f}%')
                
                # 按状态分布
                cursor.execute("SELECT status, COUNT(*) FROM cases WHERE case_number LIKE '%-25' GROUP BY status")
                status_dist = cursor.fetchall()
                print(f'\n2025年案例状态分布:')
                for status, count in status_dist:
                    print(f'  {status}: {count}')
                    
    except Exception as e:
        print(f'错误: {e}')

if __name__ == "__main__":
    compare_status_filtering()