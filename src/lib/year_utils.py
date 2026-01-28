"""年份处理工具类，用于从 case_number 提取年份和生成查询模式"""

import re
from typing import Optional


def extract_year_from_case_number(case_number: str) -> int:
    """从 case_number 提取年份
    
    Args:
        case_number: 案例编号，如 'IMM-12345-25'
        
    Returns:
        int: 完整的年份，如 2025；如果无法提取则返回 0
    """
    if not case_number:
        return 0
    
    try:
        # 使用正则表达式匹配案例编号末尾的两位数字
        match = re.search(r'-(\d{2})$', case_number.strip())
        if match:
            year_suffix = int(match.group(1))
            # 转换为完整年份 (假设 20xx 年代)
            return 2000 + year_suffix
    except (ValueError, AttributeError):
        pass
    
    return 0


def get_year_pattern(year: int) -> str:
    """获取数据库查询的年份模式
    
    Args:
        year: 完整年份，如 2025
        
    Returns:
        str: SQL LIKE 模式，如 '%-25'
    """
    year_suffix = year % 100
    return f"%-{year_suffix:02d}"


def validate_year_suffix(year_suffix: int) -> bool:
    """验证年份后缀是否有效
    
    Args:
        year_suffix: 两位数年份，如 21, 22, 23, 24, 25
        
    Returns:
        bool: 是否为有效的年份后缀
    """
    # 假设有效的年份范围是 20xx 年代，从 20 到 29
    return 20 <= year_suffix <= 29


def get_valid_year_range() -> tuple[int, int]:
    """获取支持的年份范围
    
    Returns:
        tuple[int, int]: (起始年份, 结束年份)
    """
    return (2020, 2029)


def is_valid_case_year(case_number: str, target_year: int) -> bool:
    """检查案例编号是否属于指定年份
    
    Args:
        case_number: 案例编号
        target_year: 目标年份
        
    Returns:
        bool: 是否属于目标年份
    """
    extracted_year = extract_year_from_case_number(case_number)
    return extracted_year == target_year


def build_case_number_pattern(prefix: str = "IMM", year: Optional[int] = None, sequence: Optional[str] = None) -> str:
    """构建案例编号模式用于数据库查询
    
    Args:
        prefix: 前缀，默认为 "IMM"
        year: 年份，如果为 None 则使用通配符
        sequence: 序列号，如果为 None 则使用通配符
        
    Returns:
        str: 案例编号模式，如 "IMM-%-25" 或 "IMM-12345-25"
    """
    if sequence:
        # 完整的案例编号
        if year:
            year_suffix = year % 100
            return f"{prefix}-{sequence}-{year_suffix:02d}"
        else:
            return f"{prefix}-{sequence}-%"
    else:
        # 使用通配符
        if year:
            year_suffix = year % 100
            return f"{prefix}-%-{year_suffix:02d}"
        else:
            return f"{prefix}-%-%"