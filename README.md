# FCT-AutoQuery
联邦法院案件自动查询与分析系统

[![Tests](https://img.shields.io/badge/tests-49%20passed-brightgreen)](https://github.com/zhqin020/FCT-AutoQuery)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

一个专业的加拿大联邦法院案件自动查询、智能分析和数据导出系统，采用测试驱动开发(TDD)方法构建，具备完整的合规性、智能分析和企业级数据处理功能。

## ✨ 主要特性

### 🔍 智能案件查询
- 自动化的网络爬虫技术
- 支持加拿大联邦法院网站数据抓取
- 智能URL验证和发现机制
- 断点续抓和智能去重

### 🤖 智能数据分析
- **规则分析模式**: 快速准确的案件分类
- **LLM分析模式**: 基于大语言模型的智能分析
- **混合模式**: 规则优先，LLM增强的策略
- **实体提取**: 自动识别签证办公室、法官信息
- **状态分析**: 案件处理状态智能判断

### 📊 多源数据支持
- **数据库模式**: PostgreSQL存储，支持年份和状态过滤
- **目录模式**: 按年份组织的JSON文件批量处理
- **文件模式**: 传统单文件处理（JSON/CSV）
- **智能过滤**: 基于案件编号的年份过滤和状态筛选

### 🛡️ 合规性与道德设计
- **速率限制**: 1秒间隔的请求限制，保护目标服务器
- **紧急停止**: 实时监控和紧急停止功能
- **URL验证**: 严格的联邦法院域名验证
- **完整审计**: 完整的操作日志和LLM分析审计

### 📈 高级分析功能
- **检查点机制**: 支持大批量处理断点续处理
- **智能统计**: 按案件类型、状态、时长等多维度统计
- **时长分析**: 自动计算案件处理时长、等待时间等指标
- **质量监控**: LLM分析质量评估和错误追踪

## 🏗️ 系统架构

```
src/
├── cli/                           # 数据抓取CLI
│   ├── main.py                   # 批量/单个案件抓取
│   └── purge.py                  # 数据清理
├── fct_analysis/                 # 案件分析模块 (主程序)
│   ├── cli.py                   # 分析CLI (主入口)
│   ├── nlp_engine.py            # NLP处理引擎
│   ├── rules.py                 # 规则分析引擎
│   ├── llm.py                   # LLM接口
│   ├── database.py              # 数据库接口
│   ├── metrics.py               # 统计分析
│   ├── export.py                # 结果导出
│   └── parser.py                # 数据解析
├── services/                     # 业务服务
│   ├── case_scraper_service.py  # 案件抓取服务
│   ├── export_service.py        # 数据导出服务
│   └── url_discovery_service.py # URL发现服务
├── models/                       # 数据模型
│   ├── case.py                  # 案件数据模型
│   └── docket_entry.py          # 案卷条目模型
└── lib/                          # 工具库
    ├── config.py                # 配置管理
    ├── logging_config.py       # 日志配置
    ├── rate_limiter.py          # 速率限制
    └── url_validator.py         # URL验证工具

tests/                            # 测试套件
├── contract/                     # 合同测试
├── integration/                   # 集成测试
└── unit/                        # 单元测试

specs/                            # 项目规格和任务管理
├── 0001-federal-court-scraper/
│   ├── spec.md                  # 功能规格说明
│   ├── plan.md                 # 技术实现计划
│   ├── tasks.md                # 任务跟踪
│   └── contracts/              # API合同定义
└── 0005-llm-data-analysis/      # LLM分析功能规格
```

## 🚀 快速开始

### 环境要求
- Python 3.11+
- PostgreSQL (推荐用于数据存储)
- Chrome浏览器（用于Selenium自动化，仅数据抓取需要）

### 安装步骤

1. **克隆项目**
   ```bash
   git clone https://github.com/zhqin020/FCT-AutoQuery.git
   cd FCT-AutoQuery
   ```

2. **创建虚拟环境**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 或
   venv\Scripts\activate     # Windows
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置文件设置**
   ```bash
   # 复制配置模板
   cp config.example.toml config.toml
   cp config.example.analysis.toml config.analysis.toml
   
   # 如需LLM功能，复制LLM配置
   cp config.llm.toml config.llm.toml
   ```

5. **数据库初始化** (可选，但推荐)
   ```bash
   # 创建本地数据库
   chmod +x scripts/create_local_db.sh
   ./scripts/create_local_db.sh
   
   # 创建私有配置文件 config.private.toml
   # 填入数据库连接信息
   
   # 运行数据库迁移 (分析功能必需)
   python -m src.fct_analysis.cli --migrate-db
   ```

6. **运行测试验证安装**
   ```bash
   python -m pytest tests/ -v
   ```

### 快速体验

**数据抓取** (抓取单个案件):
```bash
python -m src.cli.main single IMM-12345-25
```

**智能分析** (分析已抓取的数据):
```bash
# 规则模式 - 快速分析
python -m src.fct_analysis.cli --mode rule --year 2025

# LLM模式 - 智能分析 (需要Ollama)
python -m src.fct_analysis.cli --mode llm --year 2025
```

### Pre-commit & Formatting

- **Starter config**: This repository includes a starter `.pre-commit-config.yaml` enabling `isort`, `black` and `flake8` hooks used for local formatting and linting.
- **Install hooks and tools**:
  ```bash
  pip install --upgrade pre-commit black isort flake8
  pre-commit install --install-hooks
  ```
- **Run hooks manually**:
  ```bash
  # Run all configured hooks on the repository
  pre-commit run --all-files
  ```

### Branch naming

- The repository enforces a branch naming convention for pull requests and automated checks. Prefer `feat/`, `fix/`, or `test/` prefixes, for example:
   - `feat/add-user-auth`
   - `fix/login-bug`
   - `test/user-validation`


## 📖 使用指南

FCT-AutoQuery包含两个主要功能模块：**数据抓取**和**智能分析**。

### 🔍 数据抓取 (src/cli/main.py)

#### 单个案件抓取
```bash
python -m src.cli.main single IMM-12345-25
```

#### 批量抓取
```bash
# 抓取2025年的案件（从上次中断处继续）
python -m src.cli.main batch 2025

# 限制抓取数量
python -m src.cli.main batch 2025 --max-cases 50

# 强制重新抓取（覆盖已有数据）
python -m src.cli.main batch 2025 --force
```

#### 数据管理
```bash
# 查看所有年份的总案件数
python -m src.cli.main stats

# 查看特定年份的统计
python -m src.cli.main stats --year 2025

# 清理特定年份的数据（干运行）
python -m src.cli.main purge 2025 --dry-run

# 确认清理
python -m src.cli.main purge 2025
```

### 🤖 智能分析 (src/fct_analysis/cli.py) - 主程序

#### 基础分析命令

**规则模式** (快速、准确):
```bash
# 分析数据库中2025年的成功状态案件
python -m src.fct_analysis.cli --mode rule --year 2025

# 分析特定目录的数据
python -m src.fct_analysis.cli --mode rule --input-format directory --year 2024

# 分析单个文件
python -m src.fct_analysis.cli --mode rule --input cases.json
```

**LLM模式** (智能分析、实体提取):
```bash
# LLM智能分析2025年案件
python -m src.fct_analysis.cli --mode llm --year 2025

# 带检查点恢复的LLM分析
python -m src.fct_analysis.cli --mode llm --year 2025 --resume

# LLM样本审计
python -m src.fct_analysis.cli --mode llm --sample-audit 10
```

#### 高级功能

**智能跳过已分析案件**:
```bash
# 智能模式：跳过已分析，仅处理新案件
python -m src.fct_analysis.cli --mode llm --skip-analyzed --update-mode smart

# 强制模式：重新分析所有案件
python -m src.fct_analysis.cli --mode llm --skip-analyzed --update-mode force

# 仅跳过模式：只处理未分析案件
python -m src.fct_analysis.cli --mode llm --skip-analyzed --update-mode skip
```

**自定义配置**:
```bash
# 指定输出目录
python -m src.fct_analysis.cli --mode llm --year 2025 --output-dir ./custom_output

# 自定义Ollama URL
python -m src.fct_analysis.cli --mode llm --ollama-url http://192.168.1.100:11434

# 数据库迁移
python -m src.fct_analysis.cli --migrate-db
```

### 📊 数据源支持

系统支持三种数据源，按优先级自动选择：

1. **数据库模式** (推荐)
   ```bash
   python -m src.fct_analysis.cli --input-format database --year 2025
   ```
   - 自动过滤`status = 'success'`的案件
   - 支持年份过滤：`case_number LIKE '%-25'`
   - 支持断点续处理和智能去重

2. **目录模式**
   ```bash
   python -m src.fct_analysis.cli --input-format directory --year 2025
   ```
   - 按年份组织的JSON文件：`output/2025/`
   - 自动读取目录下所有JSON文件

3. **文件模式**
   ```bash
   python -m src.fct_analysis.cli --input cases.json
   ```
   - 传统单文件处理
   - 支持JSON和CSV格式

### 📈 输出文件说明

分析完成后，会生成以下文件：

```
analysis_output_2025/
├── federal_cases_0005_details.csv      # 详细案件数据
├── federal_cases_0005_summary.json     # 摘要报告
├── federal_cases_0005_statistics.json  # 详细统计
├── 0005_checkpoint.ndjson              # LLM检查点文件
└── logs/                               # 分析日志
```

**关键字段说明**:
- `case_id`/`case_number`: 案件编号 (系统关键字段，用于唯一标识和年份过滤)
- `title`: 案件标题/案由
- `court`: 审理法院/办公室
- `type`: 案件类型 (通过规则/LLM分析，如 Mandamus、Other 等)
- `status`: 案件状态 (成功/驳回/中止/进行中等)
- `visa_office`: 签证办公室 (LLM提取，如 Ottawa Immigration、Vancouver Office 等)
- `judge`: 法官姓名 (LLM提取)
- `time_to_close`: 案件处理时长 (天)
- `age_of_case`: 案件年龄 (从立案到现在的天数)
- `rule9_wait`: Rule 9等待时间 (天)
- `filing_date`: 立案日期

### ⚙️ 配置文件

**主配置** (`config.toml`):
```toml
[app]
output_dir = "output"
headless = true
max_retries = 3

[database]
host = "localhost"
port = 5432
name = "fct_db"
user = "fct_user"
```

**分析配置** (`config.analysis.toml`):
```toml
[analysis]
input_format = "database"    # database/directory/file
mode = "llm"                # rule/llm
skip_analyzed = true
update_mode = "smart"       # smart/force/skip

[analysis.llm]
ollama_url = "http://localhost:11434"
ollama_model = "qwen2.5-7b-instruct"
timeout = 120
```

### 🐳 Docker部署 (可选)

```bash
# 构建镜像
docker build -t fct-autoquery .

# 运行容器
docker run -v $(pwd)/output:/app/output fct-autoquery
```

## 🧪 测试

### 运行所有测试
```bash
python -m pytest tests/
```

### 运行特定测试类型
```bash
# 合同测试
python -m pytest tests/contract/

# 集成测试
python -m pytest tests/integration/

# 带覆盖率报告
python -m pytest tests/ --cov=src --cov-report=html
```

### 测试覆盖情况
- **合同测试**: 验证数据格式和API接口
- **集成测试**: 验证完整的工作流程
- **单元测试**: 验证单个组件功能

## 📋 项目规格
## 🗄️ 数据库初始化

本项目默认使用 PostgreSQL 存储已抓取的案件和案卷条目（用于断点续抓、统计和去重）。仓库已包含一个辅助脚本用于在本地创建数据库和导入 schema：`scripts/create_local_db.sh`。

快速步骤（本地开发）:

1. 运行脚本创建用户与数据库（脚本会提示输入密码）：
```bash
chmod +x scripts/create_local_db.sh
./scripts/create_local_db.sh
```

2. 在项目根创建本地配置文件 `config.private.toml`（该文件已在 `.gitignore` 中）：
```toml
[database]
host = "localhost"
port = 5432
name = "fct_db"
user = "fct_user"
password = "<your_password_here>"
```

3. 使用 `fct` 虚拟环境运行 CLI 的统计或初始化命令：
```bash
conda run -n fct python -m src.cli.main stats --year 2025
# 或通过 Python 脚本方式初始化（脚本会使用 Config 中的 DB 配置）
conda run -n fct python scripts/init_database.py
```

非交互方式（一次性）:
```bash
FCT_DB_PASSWORD='your_password' ./scripts/create_local_db.sh
```

排错要点：
- 如果出现认证失败（`password authentication failed`），请确认 `config.private.toml` 中的 `user`/`password` 是否正确，或使用 `.pgpass` 避免将密码暴露在命令行历史中。
- 如果 Postgres 未运行，先通过 `sudo systemctl start postgresql` 启动服务。

安全建议：不要将含密码的 `config.private.toml` 提交到版本库；生产环境请使用 secret manager 或环境级凭据管理。


项目采用规范化的开发流程：

- **功能规格**: `specs/0001-federal-court-scraper/spec.md`
- **技术计划**: `specs/0001-federal-court-scraper/plan.md`
- **任务跟踪**: `specs/0001-federal-court-scraper/tasks.md`
- **API合同**: `specs/0001-federal-court-scraper/contracts/`

## 🔧 开发工具

## 📝 Recent changes

The project includes a few recent improvements relevant to command-line workflows and auditing:

- Add `--force` CLI flag to allow forcing re-scraping of cases even when they already
   exist in the local PostgreSQL database. Use this when you want to refresh cached
   records or re-run parsing for specific cases.

- Batch runs now write an audit summary file into the `output/` directory when a
   batch job executes. The audit filename is `audit_YYYYMMDD_HHMMSS.json` and contains:
   - `timestamp`, `year`
   - `scraped_count` and `skipped_count`
   - a `skipped` list for cases that were already present in the DB
   - an `export` object with the JSON export path and a simple database summary when
      cases were scraped and exported

Example:
```bash
# Force re-scrape and produce an audit file
python -m src.cli.main batch 2025 --max-cases 50 --force

# Typical audit file: output/audit_20251125_005505.json
```


### 代码质量
- **Black**: 代码格式化
- **Flake8**: 代码风格检查
- **MyPy**: 类型检查
- **Pre-commit hooks**: 提交前检查

### 运行代码质量检查
```bash
# 格式化代码
black src/ tests/

# 检查代码风格
flake8 src/ tests/

# 类型检查
mypy src/
```

## 🤝 贡献指南

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feat/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feat/amazing-feature`)
5. 创建 Pull Request

### 开发规范
- 遵循TDD（测试驱动开发）原则
- 所有新功能都需要相应的测试
- 代码需要通过所有质量检查
- 提交信息遵循[Conventional Commits](https://conventionalcommits.org/)格式

## 📋 详细文档

- **[USAGE_GUIDE.md](USAGE_GUIDE.md)** - 完整的使用指南和程序运行流程详解
- **[CODING_STANDARDS.md](CODING_STANDARDS.md)** - 代码规范和开发标准
- **[GIT_WORKFLOW.md](GIT_WORKFLOW.md)** - Git工作流程和分支管理

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## ⚠️ 重要声明

**合规使用声明**: 本工具仅用于合法的数据收集和研究目的。请遵守加拿大联邦法院的使用条款和法律法规。使用者需自行承担使用风险和法律责任。

**道德使用指南**:
- 仅在必要时进行数据收集
- 遵守网站的robots.txt和使用条款
- 避免对目标网站造成过大负担
- 用于合法的研究和分析目的

## 🔧 故障排除

### 常见问题

#### Chrome WebDriver 问题
**问题**: `WebDriverException: Message: 'chromedriver' executable needs to be in PATH`

**解决方法**:
```bash
# 安装 WebDriver Manager
pip install webdriver-manager

# 或手动下载 ChromeDriver
# 1. 检查 Chrome 版本: chrome://version
# 2. 下载对应版本: https://chromedriver.chromium.org/downloads
# 3. 添加到 PATH 或项目目录
```

#### 数据库连接问题
**问题**: `psycopg2.OperationalError: could not connect to server`

**解决方法**:
```bash
# 确保 PostgreSQL 运行
sudo systemctl status postgresql

# 检查数据库配置 in src/lib/config.py
# 运行数据库初始化
python scripts/init_database.py
```

#### 案件搜索失败
**问题**: 连续多个案件搜索失败

**解决方法**:
- 检查案件编号格式: `IMM-XXXXX-YY`
- 确认年份在有效范围内 (2020-2025)
- 查看日志中的详细错误信息
- 可能触发了紧急停止机制

#### 内存不足
**问题**: 大批量处理时内存不足

**解决方法**:
- 减少 `--max-cases` 参数
- 分批处理不同年份
- 增加系统内存或使用 swap

#### 网络超时
**问题**: `TimeoutException` 频繁出现

**解决方法**:
- 检查网络连接
- 增加超时设置 in config.py
- 减少并发请求 (当前设计为单线程)

### 调试模式

启用详细日志:
```bash
# 设置日志级别
export LOGURU_LEVEL=DEBUG

# 运行时查看详细输出
python -m src.cli.main single IMM-12345-25
```

### 性能优化

- 使用 SSD 存储数据库
- 定期运行 `VACUUM` 维护 PostgreSQL
- 监控磁盘空间使用情况

## 📞 联系方式

- 项目维护者: [zhqin020](https://github.com/zhqin020)
- 项目主页: https://github.com/zhqin020/FCT-AutoQuery
- 问题反馈: [Issues](https://github.com/zhqin020/FCT-AutoQuery/issues)

## 🔧 故障排除

### 常见问题

**Q: 分析报告显示 case_number 为 NULL**
```bash
# 检查数据库中的 NULL 值
python check_null_status.py

# 修复 case_number 字段
python fix_case_number.py
```

**Q: LLM分析失败或连接超时**
```bash
# 检查 Ollama 服务状态
curl http://localhost:11434/api/tags

# 如使用远程 Ollama，更新配置
python -m src.fct_analysis.cli --mode llm --ollama-url http://your-server:11434
```

**Q: 数据库连接错误**
```bash
# 测试数据库连接
python -c "from fct_analysis.db_schema import AnalysisDBManager; print(AnalysisDBManager().test_connection())"

# 运行数据库迁移
python -m src.fct_analysis.cli --migrate-db
```

**Q: 大量已分析案件跳过处理**
```bash
# 强制重新分析所有案件
python -m src.fct_analysis.cli --mode llm --skip-analyzed --update-mode force

# 或只处理新案件
python -m src.fct_analysis.cli --mode llm --skip-analyzed --update-mode skip
```

---

**最后更新**: 2025年12月15日
**版本**: v2.0.1 (关键字段修复和文档更新)

## 🎯 核心改进说明

### v2.0.0 重大更新
- **新增智能分析模块** (`src/fct_analysis/cli.py` 作为主程序入口)
- **支持LLM驱动的案件分析**，包括案件类型识别、状态分析和实体提取
- **多数据源支持**：数据库、目录、文件三种输入模式
- **智能过滤系统**：基于案件编号的年份过滤和状态筛选
- **检查点机制**：支持大批量处理断点续处理
- **详细统计分析**：多维度案件统计和时长分析
- **混合分析模式**：规则优先、LLM增强的智能策略

### 技术栈升级
- **数据库**：PostgreSQL集成，支持复杂查询和统计分析
- **NLP引擎**：规则引擎 + Ollama LLM混合架构
- **配置管理**：模块化配置系统，支持环境变量覆盖
- **日志系统**：基于Loguru的结构化日志和进度跟踪
- **导出系统**：CSV、JSON多格式导出和统计报告生成

### 企业级特性
- **断点续抓**：数据抓取中断后可从上次位置继续
- **智能去重**：避免重复抓取和分析相同案件
- **质量监控**：LLM分析质量评估和错误追踪
- **审计日志**：完整的操作记录和合规性支持
- **扩展性设计**：模块化架构支持功能扩展和定制
