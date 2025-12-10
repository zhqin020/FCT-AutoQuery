# FCT Analysis 程序修改说明

## 修改概述

根据 issue 0051 的要求，对 FCT 数据分析程序进行了以下关键修改：

### 1. 参数集中管理

**新增配置模块集成**：
- 使用现有的 `src/lib/config.py` 模块集中管理所有参数
- 支持 TOML 配置文件（`config.toml`、`config.private.toml`）
- 支持环境变量覆盖

**新增配置项**：
```toml
[analysis]
input_format = "database"  # database, directory, file
output_subdir = "analysis"  
json_subdir = "json"
mode = "rule"  # rule, llm
ollama_url = "http://localhost:11434"
sample_audit = 0

[database]
host = "localhost"
port = 5432
database = "fct_db"
user = "fct_user"  
password = "fctpass"
```

### 2. 数据源优先级

**新的数据源优先级**：
1. **数据库**（最高优先级）
2. **目录结构**（备选）
3. **单一文件**（传统方式，最低优先级）

**数据库访问**：
- 支持 PostgreSQL 数据库
- 自动连接测试和故障转移
- 按年份过滤支持

### 3. 年度目录结构

**新的JSON文件组织方式**：
```
output/
├── analysis/
│   └── simple/
│       ├── federal_cases_simple_details.csv
│       └── federal_cases_simple_summary.json
└── json/
    ├── 2021/
    │   ├── IMM-1000-21-20210101.json
    │   ├── IMM-10-21-20210101.json
    │   └── ...
    ├── 2022/
    │   ├── IMM-1000-22-20220101.json
    │   └── ...
    └── 2023/
        └── ...
```

**文件命名规则**：
- 格式：`{case_number}-{date}.json`
- 日期格式：`YYYYMMDD`
- 按年份分组存储

### 4. CLI 接口增强

**新增命令行选项**：
```bash
# 数据源选择
--input-format {database,directory,file}  # 覆盖配置文件设置
--input <file_path>                        # 传统文件输入

# 年度过滤
--year <year>                             # 按年份过滤数据

# 其他选项（现在都有配置文件默认值）
--mode {rule,llm}                         # 分析模式
--output-dir <path>                       # 输出目录
--ollama-url <url>                        # Ollama地址
--sample-audit <number>                   # 审计采样数量
```

### 5. 向后兼容性

**保持兼容的功能**：
- 原有的 `--input` 文件方式仍然支持
- 所有原有参数仍然可用
- 测试用例无需修改

**新的默认行为**：
- 如果不指定任何输入选项，优先尝试数据库
- 数据库不可用时自动降级到目录方式
- 配置文件提供默认值

## 使用示例

### 基本用法（使用配置文件）

```bash
# 使用默认配置（优先数据库）
python -m fct_analysis.cli

# 指定年度过滤
python -m fct_analysis.cli --year 2021
```

### 覆盖配置文件设置

```bash
# 强制使用目录方式
python -m fct_analysis.cli --input-format directory --year 2022

# 使用传统文件方式
python -m fct_analysis.cli --input cases.json --mode llm
```

### 高级用法

```bash
# LLM模式 + 审计采样
python -m fct_analysis.cli --mode llm --sample-audit 10 --year 2021

# 自定义输出目录和Ollama地址
python -m fct_analysis.cli --output-dir custom_output --ollama-url http://192.168.1.100:11434
```

## 配置文件设置

### 1. 复制配置模板
```bash
cp config.example.analysis.toml config.toml
```

### 2. 编辑配置
```toml
# 数据库配置（如使用数据库作为数据源）
[database]
host = "your_db_host"
port = 5432
database = "fct_db"
user = "your_username"
password = "your_password"

# 分析程序配置
[analysis]
input_format = "database"  # 优先级：database > directory > file
mode = "rule"
ollama_url = "http://localhost:11434"
sample_audit = 0
```

## 数据源迁移

### 从文件到年度目录结构

使用提供的转换脚本：
```bash
python scripts/generate_yearly_json.py input_cases.json output/
```

这将：
1. 读取现有的JSON文件
2. 根据案件编号或日期确定年份
3. 按年度目录结构重新组织文件
4. 生成规范的文件名

### 导入数据库

数据库表结构应包含以下字段：
```sql
CREATE TABLE cases (
    case_id TEXT PRIMARY KEY,
    case_number TEXT,
    title TEXT,
    court TEXT,
    date DATE,
    case_type TEXT,
    action_type TEXT,
    nature_of_proceeding TEXT,
    filing_date DATE,
    office TEXT,
    style_of_cause TEXT,
    language TEXT,
    url TEXT,
    html_content TEXT,
    scraped_at TIMESTAMP,
    docket_entries JSONB  -- PostgreSQL JSONB类型
);
```

## 新增工具脚本

### 1. `scripts/generate_yearly_json.py`
- 将现有JSON文件转换为年度目录结构
- 自动提取年份信息
- 生成规范的文件名

### 2. `config.example.analysis.toml`
- 配置文件模板
- 包含所有新配置项的说明

## 故障排除

### 常见问题

**1. 数据库连接失败**
- 程序会自动降级到目录方式
- 检查数据库配置和网络连接
- 查看日志获取详细错误信息

**2. 找不到年度目录**
- 确认 `output/json/` 目录存在
- 检查年度目录命名（4位数字）
- 运行转换脚本生成正确结构

**3. 年度过滤不工作**
- 确认文件中的 `filing_date` 字段格式正确
- 检查案件编号中的年份标识
- 使用数据库方式可获得更精确的过滤

### 调试技巧

**查看详细日志**：
```bash
python -m fct_analysis.cli --input-format directory --year 2021
```

**测试数据源**：
```bash
# 测试数据库连接
python -c "from src.fct_analysis.database import DatabaseReader; print(DatabaseReader().test_connection())"

# 测试目录读取
python -c "from src.fct_analysis.database import FileReader; print(len(FileReader().read_directory(2021)))"
```

## 测试验证

所有原有测试继续通过：
```bash
python -m pytest tests/unit/test_*_0005.py tests/integration/test_pipeline_0005.py -v
```

新增功能测试：
```bash
# 测试年度目录结构
python -m fct_analysis.cli --input-format directory --year 2021 --output-dir test_output

# 测试数据库连接（需要数据库配置）
python -m fct_analysis.cli --input-format database --year 2021
```

这些修改使FCT分析程序更加灵活、可配置，同时保持了完全的向后兼容性。