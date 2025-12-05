#!/usr/bin/env python3
"""
测试简化的跟踪功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from services.simplified_tracking_service import SimplifiedTrackingService
from lib.config import Config

def test_tracking():
    """测试跟踪功能"""
    print("=== 测试简化跟踪功能 ===")
    
    tracking = SimplifiedTrackingService()
    
    # 测试案例
    test_cases = ['IMM-5-21', 'IMM-9-21', 'IMM-10-21']
    
    print("\n1. 测试 should_skip_case (首次运行)")
    for case in test_cases:
        should_skip, reason = tracking.should_skip_case(case)
        print(f"  {case}: should_skip={should_skip}, reason='{reason}'")
    
    print("\n2. 测试标记案例状态")
    # 标记 IMM-5-21 为无数据 (对应页面 'No data available in table')
    tracking.mark_case_attempt('IMM-5-21', 'no_data')
    print("  标记 IMM-5-21 为 no_data")
    
    # 标记 IMM-9-21 为成功
    tracking.mark_case_attempt('IMM-9-21', 'success')
    print("  标记 IMM-9-21 为 success")
    
    # 标记 IMM-10-21 为失败
    tracking.mark_case_attempt('IMM-10-21', 'failed', '连接超时')
    print("  标记 IMM-10-21 为 failed (连接超时)")
    
    print("\n3. 再次测试 should_skip_case")
    for case in test_cases:
        should_skip, reason = tracking.should_skip_case(case)
        print(f"  {case}: should_skip={should_skip}, reason='{reason}'")
    
    print("\n4. 测试获取统计信息")
    stats = tracking.get_statistics()
    print(f"  总案例数: {stats['total_cases']}")
    print("  按状态分布:")
    for status, data in stats['by_status'].items():
        print(f"    {status}: {data['count']} (最大重试次数: {data['max_retries']})")
    
    print("\n5. 测试获取需要重试的案例")
    failed_cases = tracking.get_failed_cases_for_retry()
    print(f"  需要重试的失败案例: {failed_cases}")
    
    print("\n6. 测试多次失败后的重试限制")
    # 模拟多次失败
    for i in range(4):
        tracking.mark_case_attempt('IMM-11-21', 'failed', f'第{i+1}次失败')
    
    should_skip, reason = tracking.should_skip_case('IMM-11-21')
    print(f"  IMM-11-21 (4次失败后): should_skip={should_skip}, reason='{reason}'")
    
    print("\n✅ 测试完成!")

if __name__ == "__main__":
    test_tracking()