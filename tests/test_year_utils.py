#!/usr/bin/env python3
"""测试年份工具模块"""

import sys
import os

# 添加 src 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lib.year_utils import (
    extract_year_from_case_number,
    get_year_pattern,
    validate_year_suffix,
    get_valid_year_range,
    is_valid_case_year,
    build_case_number_pattern
)

def test_extract_year_from_case_number():
    """测试从案例编号提取年份"""
    print("测试 extract_year_from_case_number...")
    
    # 正常情况
    assert extract_year_from_case_number("IMM-12345-25") == 2025
    assert extract_year_from_case_number("IMM-1-21") == 2021
    assert extract_year_from_case_number("IMM-99999-20") == 2020
    
    # 边界情况
    assert extract_year_from_case_number("") == 0
    assert extract_year_from_case_number(None) == 0
    assert extract_year_from_case_number("INVALID") == 0
    assert extract_year_from_case_number("IMM-12345") == 0
    
    print("✓ extract_year_from_case_number 测试通过")

def test_get_year_pattern():
    """测试获取年份模式"""
    print("测试 get_year_pattern...")
    
    assert get_year_pattern(2025) == "%-25"
    assert get_year_pattern(2021) == "%-21"
    assert get_year_pattern(2000) == "%-00"
    
    print("✓ get_year_pattern 测试通过")

def test_validate_year_suffix():
    """测试验证年份后缀"""
    print("测试 validate_year_suffix...")
    
    # 有效年份
    assert validate_year_suffix(20) == True
    assert validate_year_suffix(25) == True
    assert validate_year_suffix(29) == True
    
    # 无效年份
    assert validate_year_suffix(19) == False
    assert validate_year_suffix(30) == False
    assert validate_year_suffix(99) == False
    
    print("✓ validate_year_suffix 测试通过")

def test_get_valid_year_range():
    """测试获取有效年份范围"""
    print("测试 get_valid_year_range...")
    
    start, end = get_valid_year_range()
    assert start == 2020
    assert end == 2029
    
    print("✓ get_valid_year_range 测试通过")

def test_is_valid_case_year():
    """测试验证案例年份"""
    print("测试 is_valid_case_year...")
    
    # 匹配的情况
    assert is_valid_case_year("IMM-12345-25", 2025) == True
    assert is_valid_case_year("IMM-1-21", 2021) == True
    
    # 不匹配的情况
    assert is_valid_case_year("IMM-12345-25", 2024) == False
    assert is_valid_case_year("IMM-1-21", 2022) == False
    
    # 无效案例编号
    assert is_valid_case_year("", 2025) == False
    assert is_valid_case_year("INVALID", 2025) == False
    
    print("✓ is_valid_case_year 测试通过")

def test_build_case_number_pattern():
    """测试构建案例编号模式"""
    print("测试 build_case_number_pattern...")
    
    # 完整案例编号
    assert build_case_number_pattern(sequence="12345", year=2025) == "IMM-12345-25"
    
    # 只有年份
    assert build_case_number_pattern(year=2025) == "IMM-%-25"
    assert build_case_number_pattern(year=2021) == "IMM-%-21"
    
    # 只有序列号
    assert build_case_number_pattern(sequence="12345") == "IMM-12345-%"
    
    # 全通配符
    assert build_case_number_pattern() == "IMM-%-%"
    
    # 自定义前缀
    assert build_case_number_pattern(prefix="T", year=2025) == "T-%-25"
    
    print("✓ build_case_number_pattern 测试通过")

def run_all_tests():
    """运行所有测试"""
    print("=== 开始测试年份工具模块 ===\n")
    
    test_extract_year_from_case_number()
    test_get_year_pattern()
    test_validate_year_suffix()
    test_get_valid_year_range()
    test_is_valid_case_year()
    test_build_case_number_pattern()
    
    print("\n=== 所有测试通过！ ===")

if __name__ == "__main__":
    run_all_tests()