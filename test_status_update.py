#!/usr/bin/env python3
"""测试status更新逻辑"""

import sys
sys.path.append('/home/watson/work/FCT-AutoQuery/src')

from services.simplified_tracking_service import SimplifiedTrackingService, CaseStatus

def test_status_update():
    """测试status更新是否正常工作"""
    tracker = SimplifiedTrackingService()
    
    # 测试案例编号
    case_number = "IMM-2-21"
    
    print(f"测试案例: {case_number}")
    
    # 1. 检查当前状态
    try:
        conn = tracker.db_config
        import psycopg2
        conn_obj = psycopg2.connect(**conn)
        cursor = conn_obj.cursor()
        cursor.execute("SELECT status, retry_count, error_message FROM cases WHERE case_number = %s", (case_number,))
        result = cursor.fetchone()
        if result:
            print(f"当前状态: {result[0]}, 重试次数: {result[1]}, 错误信息: {result[2]}")
        else:
            print("案例不存在于数据库中")
        cursor.close()
        conn_obj.close()
    except Exception as e:
        print(f"检查状态失败: {e}")
    
    # 2. 标记为成功
    try:
        tracker.mark_case_attempt(case_number, CaseStatus.SUCCESS)
        print("✓ 成功标记为 SUCCESS")
    except Exception as e:
        print(f"✗ 标记 SUCCESS 失败: {e}")
    
    # 3. 再次检查状态
    try:
        conn = tracker.db_config
        import psycopg2
        conn_obj = psycopg2.connect(**conn)
        cursor = conn_obj.cursor()
        cursor.execute("SELECT status, retry_count, error_message FROM cases WHERE case_number = %s", (case_number,))
        result = cursor.fetchone()
        if result:
            print(f"更新后状态: {result[0]}, 重试次数: {result[1]}, 错误信息: {result[2]}")
        cursor.close()
        conn_obj.close()
    except Exception as e:
        print(f"检查更新后状态失败: {e}")
    
    # 4. 测试should_skip_case逻辑
    try:
        should_skip, reason = tracker.should_skip_case(case_number)
        print(f"是否应该跳过: {should_skip}, 原因: {reason}")
    except Exception as e:
        print(f"测试跳过逻辑失败: {e}")

if __name__ == "__main__":
    test_status_update()