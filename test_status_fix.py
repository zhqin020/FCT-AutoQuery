#!/usr/bin/env python3
"""
测试批处理服务状态显示修复
验证 status=unknown 问题是否已解决
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.services.case_tracking_service import CaseTrackingService
from src.lib.case_utils import canonicalize_case_number

def test_get_case_status():
    """测试 get_case_status 方法"""
    print("=== 测试 get_case_status 方法 ===")
    
    tracker = CaseTrackingService()
    
    # 测试已知存在且状态为 success 的案例
    test_cases = [
        'IMM-1-21',  # 状态应为 success
        'IMM-2-21',  # 状态应为 success  
        'IMM-18-21', # 状态应为 no_data
    ]
    
    for case_number in test_cases:
        print(f"\n测试案例: {case_number}")
        
        # 测试规范化
        canonical = canonicalize_case_number(case_number)
        print(f"  规范化后: {canonical}")
        
        # 测试 get_case_status
        status_info = tracker.get_case_status(case_number)
        if status_info:
            print(f"  状态信息: {status_info}")
            print(f"  最终状态: {status_info.get('last_outcome', 'UNKNOWN')}")
        else:
            print(f"  状态信息: None (未找到)")
        
        # 测试 should_skip_case
        try:
            should_skip, reason = tracker.should_skip_case(case_number)
            print(f"  应跳过: {should_skip}, 原因: {reason}")
        except Exception as e:
            print(f"  should_skip_case 错误: {e}")

def test_enhanced_fast_check():
    """测试 enhanced_fast_check 函数逻辑"""
    print("\n=== 测试 enhanced_fast_check 逻辑 ===")
    
    # 模拟 enhanced_fast_check 的核心逻辑
    tracker = CaseTrackingService()
    
    def simulate_enhanced_fast_check(n: int, year: int = 21):
        """模拟 enhanced_fast_check 函数"""
        case_number = f"IMM-{n}-{year % 100:02d}"
        
        # 模拟 should_skip_case 调用
        try:
            should_skip, skip_reason = tracker.should_skip_case(case_number)
        except Exception:
            should_skip, skip_reason = (False, '')
        
        # 获取状态信息
        try:
            status_info = tracker.get_case_status(case_number) or {}
            last_outcome = status_info.get('last_outcome', 'unknown')
        except Exception:
            last_outcome = 'unknown'
        
        result = {
            'exists': not should_skip,
            'status': last_outcome,
            'skip_reason': skip_reason,
            'should_skip': should_skip
        }
        
        print(f"案例 {case_number}:")
        print(f"  exists={result['exists']}, status={result['status']}, reason='{result['skip_reason']}'")
        
        return result
    
    # 测试几个案例
    test_numbers = [1, 2, 18]
    for num in test_numbers:
        simulate_enhanced_fast_check(num)

if __name__ == "__main__":
    print("测试批处理服务状态显示修复")
    print("=" * 50)
    
    test_get_case_status()
    test_enhanced_fast_check()
    
    print("\n" + "=" * 50)
    print("测试完成")