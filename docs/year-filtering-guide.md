# 年份筛选最佳实践指南

## 概述

本指南说明如何在 Federal Court Scraper 项目中正确地根据 `case_number` 中的年份进行筛选，而不是依赖 `filing_date` 字段。

## 核心原则

**始终使用 `case_number` 字段而不是 `filing_date` 字段来按年份筛选案例。**

原因：
1. `case_number` 包含明确的年份信息（末尾两位数字）
2. `filing_date` 可能为 null 或不准确
3. `case_number` 是案例的唯一标识符，不会缺失

## 年份解析工具

### 工具模块位置
`src/lib/year_utils.py`

### 主要功能

#### 1. 从 case_number 提取年份
```python
from src.lib.year_utils import extract_year_from_case_number

year = extract_year_from_case_number("IMM-12345-25")  # 返回 2025
```

#### 2. 生成数据库查询模式
```python
from src.lib.year_utils import get_year_pattern

pattern = get_year_pattern(2025)  # 返回 "%-25"
```

#### 3. 验证案例年份
```python
from src.lib.year_utils import is_valid_case_year

is_valid = is_valid_case_year("IMM-12345-25", 2025)  # 返回 True
```

#### 4. 构建案例编号模式
```python
from src.lib.year_utils import build_case_number_pattern

# 模式匹配所有 2025 年案例
pattern = build_case_number_pattern(year=2025)  # 返回 "IMM-%-25"

# 模式匹配特定案例
pattern = build_case_number_pattern(sequence="12345", year=2025)  # 返回 "IMM-12345-25"
```

## 数据库查询示例

### 基础年份筛选
```sql
-- 查询 2025 年的所有案例
SELECT * FROM cases WHERE case_number LIKE '%-25';

-- 使用参数化查询
SELECT * FROM cases WHERE case_number LIKE %s;
-- 参数: "%-25"
```

### 统计查询
```sql
-- 按年份统计案例数量
SELECT 
    CASE 
        WHEN case_number LIKE '%-21' THEN '2021'
        WHEN case_number LIKE '%-22' THEN '2022'
        WHEN case_number LIKE '%-23' THEN '2023'
        WHEN case_number LIKE '%-24' THEN '2024'
        WHEN case_number LIKE '%-25' THEN '2025'
    END as year,
    COUNT(*) as case_count
FROM cases
GROUP BY 
    CASE 
        WHEN case_number LIKE '%-21' THEN '2021'
        WHEN case_number LIKE '%-22' THEN '2022'
        WHEN case_number LIKE '%-23' THEN '2023'
        WHEN case_number LIKE '%-24' THEN '2024'
        WHEN case_number LIKE '%-25' THEN '2025'
    END
ORDER BY year;
```

### 带统计的年份筛选
```python
from src.lib.config import Config
from src.lib.year_utils import get_year_pattern
import psycopg2

def get_year_statistics(year):
    db_config = Config.get_db_config()
    pattern = get_year_pattern(year)
    
    with psycopg2.connect(**db_config) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    COUNT(*) as total_cases,
                    COUNT(filing_date) as cases_with_filing_date,
                    COUNT(*) - COUNT(filing_date) as cases_without_filing_date,
                    status,
                    COUNT(*) as status_count
                FROM cases 
                WHERE case_number LIKE %s
                GROUP BY status
            """, (pattern,))
            
            return cur.fetchall()
```

## Python 完整示例

### 演示脚本
参考 `demo_year_filtering.py` 脚本，它展示了：
1. 连接数据库（使用 Config 接口）
2. 从 case_number 提取年份
3. 按年份筛选案例
4. 生成统计报告

### 数据库检查脚本
参考 `check_db_via_config.py` 脚本，它演示了：
1. 使用 Config 接口连接数据库
2. 使用 case_number 进行年份筛选
3. 检查 filing_date 字段的完整性

## 避免的反模式

### ❌ 错误做法：使用 filing_date 筛选
```python
# 不要这样做
cur.execute("""
    SELECT * FROM cases 
    WHERE EXTRACT(YEAR FROM filing_date) = 2025
""")
```

### ❌ 错误做法：直接使用环境变量
```python
# 不要这样做
conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    # ...
)
```

### ✅ 正确做法：使用 case_number 和 Config
```python
from src.lib.config import Config
from src.lib.year_utils import get_year_pattern

db_config = Config.get_db_config()
pattern = get_year_pattern(2025)  # "%-25"

with psycopg2.connect(**db_config) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM cases WHERE case_number LIKE %s", (pattern,))
```

## 关键文件

1. **年份工具**: `src/lib/year_utils.py`
2. **配置管理**: `src/lib/config.py`
3. **演示脚本**: `demo_year_filtering.py`
4. **检查脚本**: `check_db_via_config.py`

## 测试验证

运行以下命令来验证年份筛选功能：

```bash
# 激活环境
conda activate fct

# 运行年份筛选演示
python demo_year_filtering.py

# 检查数据库状态
python check_db_via_config.py
```

## 注意事项

1. **年份范围**: 当前支持 2020-2029 年代
2. **案例格式**: 标准格式为 `IMM-{序列号}-{年份后缀}`
3. **配置**: 始终通过 `Config.get_db_config()` 获取数据库配置
4. **安全**: 使用参数化查询避免 SQL 注入

## 集成指南

要在现有代码中集成正确的年份筛选：

1. 导入工具：`from src.lib.year_utils import get_year_pattern`
2. 使用 Config：`from src.lib.config import Config`
3. 生成模式：`pattern = get_year_pattern(year)`
4. 参数化查询：`cur.execute("... WHERE case_number LIKE %s", (pattern,))`

这样可以确保所有年份筛选操作的一致性和可靠性。