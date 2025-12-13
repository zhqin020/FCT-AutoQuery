# FCT-AutoQuery
联邦法院案件自动查询系统 (Federal Court Case Scraper)

## 🚀 快速开始

**新用户？请查看 [快速开始指南](QUICKSTART.md)**

```bash
# 1. 激活环境
conda activate fct

# 2. 测试单个案例
python -m src.cli.main single IMM-12345-25

# 3. 批量采集
python -m src.cli.main batch 2025 --max-cases 50
```

**需要详细操作指南？查看 [操作手册](docs/operations-manual.md)**

## 项目概述

FCT-AutoQuery 是一个自动化的联邦法院案件数据采集系统，专门用于从加拿大联邦法院网站高效地采集案件信息和档案历史记录。系统采用智能探测算法和批量处理能力，能够安全、高效地处理大规模案件数据采集任务。

### 主要特性

- 🔍 **智能探测算法**：使用指数探测+线性采集的组合算法，快速确定案件编号边界
- 📊 **数据完整性**：采集案件基本信息和完整的docket条目历史记录
- 💾 **多格式输出**：支持JSON文件和PostgreSQL数据库双重存储
- 🔄 **断点续采**：支持跳过已采集的案例，实现增量采集
- 📈 **统计监控**：提供详细的采集统计和数据质量分析
- 🛡️ **安全机制**：内置速率限制、错误重试和紧急停止机制
- 🧹 **数据清理**：提供数据质量检查和清理工具
- 📝 **完整日志**：详细的操作日志和审计跟踪

## 系统架构

```
FCT-AutoQuery/
├── src/
│   ├── cli/                    # 命令行接口
│   │   ├── main.py            # 主要CLI程序
│   │   └── purge.py           # 数据清理工具
│   ├── services/              # 核心服务
│   │   ├── case_scraper_service.py      # 案例采集服务
│   │   ├── batch_service.py              # 批量处理服务
│   │   ├── export_service.py            # 数据导出服务
│   │   ├── case_tracking_service.py      # 案例跟踪服务
│   │   └── enhanced_statistics_service.py # 统计分析服务
│   ├── models/                # 数据模型
│   │   ├── case.py           # 案例数据模型
│   │   └── docket_entry.py  # 档案条目模型
│   └── lib/                  # 工具库
│       ├── config.py          # 配置管理
│       ├── logging_config.py  # 日志配置
│       └── rate_limiter.py   # 速率限制器
├── docs/                     # 文档
├── logs/                     # 日志文件
├── output/                   # 输出文件
└── tests/                    # 测试文件
```

## 快速开始

### 环境要求

- Python 3.8+
- PostgreSQL 数据库
- Chrome 浏览器 (用于 Selenium WebDriver)

### 安装依赖

```bash
# 激活环境
conda activate fct

# 安装依赖
pip install -r requirements.txt
```

### 配置数据库

系统使用PostgreSQL数据库存储采集数据。请确保：

1. 创建数据库 `fct_db`
2. 创建用户 `fct_user` 并设置适当权限
3. 更新配置文件中的数据库连接参数

### 基本使用

#### 1. 单个案例采集

```bash
# 采集单个案例
python -m src.cli.main single IMM-12345-25

# 强制重新采集（即使已存在）
python -m src.cli.main single IMM-12345-25 --force
```

#### 2. 批量采集

```bash
# 基本批量采集（2025年）
python -m src.cli.main batch 2025

# 从指定编号开始，最多采集100个案例
python -m src.cli.main batch 2025 --start 100 --max-cases 100

# 调整采集参数（更快的采集速度）
python -m src.cli.main batch 2025 --max-cases 50 --rate-interval 0.5 --backoff-factor 1.5

# 自定义指数探测参数
python -m src.cli.main batch 2025 --max-exponent 15 --max-cases 200
```

#### 3. 统计信息查看

```bash
# 查看整体统计
python -m src.cli.main stats

# 查看特定年份统计
python -m src.cli.main stats --year 2025
```

#### 4. 数据清理

```bash
# 预览清理操作（不实际删除）
python -m src.cli.main purge 2024 --dry-run

# 执行实际清理操作
python -m src.cli.main purge 2024 --yes
```

## 核心算法

### 指数探测 + 线性采集

系统采用两阶段算法实现高效采集：

#### 阶段1：指数探测
- **目标**：快速确定案件编号的上边界
- **方法**：从起始编号开始，按 `2^i` 步长递增探测
- **示例**：12000, 12001, 12002, 12004, 12008, 12016, 12032, ...

#### 阶段2：线性采集  
- **目标**：完整采集确定范围内的所有案例
- **方法**：从起始编号到上边界，按步长1进行顺序采集
- **优势**：避免重复采集，确保数据完整性

### 跳过机制

系统能智能跳过以下情况：
- ✅ 已成功采集的案例
- ✅ 确认为无数据的案例 (`No data available`)
- ❌ 采集失败的案例（可配置重试）

## 输出格式

### JSON 文件结构

每个案例都会生成独立的JSON文件：

```json
{
  "case_number": "IMM-12345-25",
  "case_type": "Immigration Matters",
  "filing_date": "2025-01-15",
  "office": "Toronto",
  "style_of_cause": "案例标题",
  "language": "English",
  "status": "success",
  "scraped_at": "2025-01-12T10:30:00Z",
  "docket_entries": [
    {
      "id": 1,
      "date_filed": "2025-01-15",
      "office": "Toronto",
      "recorded_entry_summary": "文件摘要"
    }
  ]
}
```

### 数据库结构

#### Cases 表
- `case_number`: 案例编号 (主键)
- `case_type`: 案例类型
- `filing_date`: 立案日期
- `office`: 办公室
- `status`: 采集状态
- `scraped_at`: 采集时间
- `html_content`: 原始HTML内容

#### Docket Entries 表
- `id`: 条目ID (主键)
- `case_number`: 关联的案例编号
- `date_filed`: 文件日期
- `office`: 办公室
- `recorded_entry_summary`: 条目摘要

## 高级功能

### 数据质量分析

系统提供多种数据质量检查工具：

```python
# 检查缺失filing_date的记录
python analyze_null_filing_date_cases.py

# 导出问题数据用于分析
python export_null_filing_date_cases.py
```

### 性能优化

- **速率限制**：可配置的请求间隔，默认1秒
- **退避策略**：指数退避算法处理失败请求
- **内存管理**：定期垃圾回收，防止内存泄漏
- **浏览器重置**：定期重新初始化浏览器，避免长时间运行问题

### 错误处理

- **自动重试**：最多3次重试，支持智能退避
- **状态跟踪**：详细记录每次采集的结果
- **紧急停止**：连续失败达到阈值时自动停止
- **浏览器恢复**：检测到stale元素时自动重置

## 配置参数

### 核心配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `rate_interval` | 1.0 | 请求间隔（秒） |
| `backoff_factor` | 1.0 | 退避因子 |
| `max_backoff_seconds` | 60.0 | 最大退避时间（秒） |
| `max_retries` | 3 | 最大重试次数 |
| `max_exponent` | 20 | 指数探测最大指数 |
| `safe_stop_no_records` | 20 | 安全停止阈值 |

### 命令行参数

#### 批量采集参数
- `--start`: 起始编号（默认：1）
- `--max-cases`: 最大采集案例数
- `--max-exponent`: 指数探测最大指数（默认：20）
- `--safe-stop-no-records`: 安全停止阈值

#### 通用参数
- `--force`: 强制重新采集
- `--rate-interval`: 请求间隔
- `--backoff-factor`: 退避因子
- `--max-backoff-seconds`: 最大退避时间

## 日志和监控

### 日志系统

系统提供多级别日志：
- `INFO`: 正常操作信息
- `WARNING`: 警告信息
- `ERROR`: 错误信息
- `DEBUG`: 调试信息

### 日志文件位置
- 主日志：`logs/scraper.log`
- 按日期轮转：`logs/scraper-1.log`, `logs/scraper-2.log` 等

### 统计信息

系统自动生成详细的采集统计：
- 采集前后案例数量对比
- 按状态分类的统计
- 失败率和重试统计
- 时间和性能指标

## 故障排除

### 常见问题

#### 1. 浏览器启动失败
```bash
# 检查Chrome安装
google-chrome --version

# 更新webdriver
pip install --upgrade webdriver-manager
```

#### 2. 数据库连接错误
```bash
# 检查PostgreSQL服务
sudo systemctl status postgresql

# 测试连接
psql -h localhost -U fct_user -d fct_db
```

#### 3. 采集速度慢
```bash
# 调整速率参数（谨慎使用）
python -m src.cli.main batch 2025 --rate-interval 0.5 --backoff-factor 1.2
```

### 调试模式

启用详细日志进行调试：
```bash
# 设置日志级别为DEBUG
export LOG_LEVEL=DEBUG
python -m src.cli.main batch 2025 --max-cases 5
```

## 数据管理

### 备份和恢复

系统提供完整的数据备份机制：

```bash
# 自动备份（执行清理操作前）
python -m src.cli.main purge 2024 --dry-run

# 恢复数据（使用备份文件）
# 参考 docs/null-filing-date-cleanup-summary.md
```

### 数据清理

定期清理问题数据：

```bash
# 清理无效记录
python cleanup_null_filing_date_records.py

# 生成清理报告
python analyze_null_filing_date_cases.py
```

## 开发和测试

### 运行测试

```bash
# 激活环境
conda activate fct

# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_case_scraper.py -v
```

### 代码规范

项目遵循以下规范：
- Python PEP 8 编码规范
- 类型提示 (Type Hints)
- 文档字符串 (Docstrings)
- 单元测试覆盖

## 更新日志

### 最新更新 (v2.0+)

- ✅ 新增智能探测算法，大幅提升采集效率
- ✅ 优化UI交互时间，单案例采集时间缩短至4-5秒
- ✅ 增强数据质量检查和清理功能
- ✅ 完善日志输出和统计信息
- ✅ 添加断点续采和增量更新能力
- ✅ 改进错误处理和自动恢复机制

### 已知问题

- 🔄 某些案例可能需要多次重试才能成功采集
- 📊 大规模数据导出可能需要较长时间
- 🌐 网络不稳定时可能触发紧急停止机制

## 贡献指南

欢迎提交问题报告和功能请求：

1. 在 `issues/` 目录下创建详细的问题文档
2. 提供复现步骤和环境信息
3. 确保所有测试通过
4. 更新相关文档

## 许可证

本项目采用 [LICENSE](LICENSE) 文件中指定的许可证。

---

**联系方式**: 如有技术问题，请查看 `docs/` 目录下的详细文档或在 `issues/` 目录下创建问题报告。