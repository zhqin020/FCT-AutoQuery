# Federal Court Case Scraper - 使用指南
# 联邦法院案件抓取器 - 使用指南

## 程序运行流程

### 1. 程序初始化
```
初始化浏览器 → 设置速率限制器 → 配置日志系统 → 准备抓取服务
```
```
输入URL → 域名验证 → 路径模式匹配 → 案件编号提取 → 验证通过/失败
```

### 3. 案件抓取流程
```
URL验证 → 速率限制检查 → 浏览器导航 → 页面加载等待 → HTML内容提取 → 数据解析 → 案件对象创建

### 4. 数据导出流程
## 从法院网站抓取信息的详细过程

### 网站结构分析
加拿大联邦法院网站 (www.fct-cf.ca) 的案件信息主要位于：
- **英文路径**: `/en/court-files-and-decisions/`
- **案件URL格式**: `https://www.fct-cf.ca/en/court-files-and-decisions/{CASE_NUMBER}`

```python
# 使用URL验证器检查URL有效性
is_valid, reason = URLValidator.validate_case_url(url)

**验证规则**:
- 域名必须是 `www.fct-cf.ca` 或 `fct-cf.ca`
- 路径必须包含 `/en/court-files-and-decisions`
- URL必须是有效的HTTP/HTTPS链接
wait_time = self.rate_limiter.wait_if_needed()
```

**合规措施**:
- 每次请求间隔至少1秒
- 自动计算等待时间

#### 步骤3: 浏览器自动化
driver.get(url)
```

**浏览器配置**:
- 无头模式运行（可选）
- 设置合适的窗口大小
- 禁用GPU加速（服务器环境）

#### 步骤4: 页面内容提取
html_content = driver.page_source
```

**内容提取策略**:
- 获取完整的HTML页面源码
- 包含所有动态加载的内容
- 保留原始格式和编码

#### 步骤5: 数据解析
```python
# 从HTML内容中提取结构化数据
title = self._extract_case_title(html_content)
case_number = self._extract_case_number(url, html_content)
case_date = self._extract_case_date(html_content)

#### 步骤6: 数据验证与对象创建
```python
# 创建标准化的案件数据对象
case = Case.from_url(
    self.emergency_stop()

**保护机制**:
- 连续5次错误触发紧急停止
- 自动记录错误日志
- 资源清理和状态重置

## 实际使用示例

### 命令行运行
```bash
# 单个案件抓取（建议使用模块化入口）
# 使用新的 CLI 子命令接口：
python -m src.cli.main single IMM-12345-22

# 批量抓取（按年份）
python -m src.cli.main batch 2025 --max-cases 50

# 强制重新抓取（当数据库已有记录但需要刷新/覆盖时使用）
python -m src.cli.main batch 2025 --max-cases 50 --force

# 注意：CLI 现在默认只导出 JSON 到 `output/`（CSV 已移除）。
# 批量运行将在 `output/` 目录生成一个审计文件（audit）记录本次运行的摘要，
# 例如: `output/audit_20251125_005505.json`。此文件包含：
# - `timestamp`: 运行时间戳
# - `year`: 抓取的年度
#
```

### 脚本 `scripts/auto_click_more.py`（快速烟雾/手工检查）

该脚本用于快速在界面上搜索并打开案件的“More/Modal”视图，便于调试解析器和生成样例输出。

- **非交互运行**: 使用 `--yes` 或 `--non-interactive` 跳过交互式确认提示（CLI 标志优先于 `AUTO_CONFIRM` 环境变量）。
  - 示例: `python scripts/auto_click_more.py --yes`

- **注入服务类（测试/替代实现）**: 使用 `--service-class <path>` 将一个可实例化的 Service 类注入脚本，脚本会优先调用该类的 `fetch_case_and_docket(case_number, non_interactive)` 方法（如果存在），以获取结构化数据并直接导出 JSON。支持两种路径格式：
  - dotted module: `package.module.ClassName`（在可导入的包路径下）
  - file path: `path/to/file.py:ClassName`（按文件加载，便于在子进程中注入测试实现）
  - 示例（测试用法）: `python scripts/auto_click_more.py --yes --service-class tests/integration/fake_service.py:FakeService`

- **快速测试模式（历史/兼容）**: 脚本仍支持使用环境变量 `AUTO_CONFIRM=1` 来跳过确认提示（早期兼容方式）。CLI 标志 `--yes` 优先于 `AUTO_CONFIRM`。

- **CI 友好说明**: 为了在 CI 中运行无需启动浏览器，我们提供了一个 `FakeService`（见 `tests/integration/fake_service.py`）并通过 `--service-class` 注入；这种方式不会启动 Selenium 或 Chrome。脚本的 JSON 输出会写入 `output/`，文件名包含案件编号和时间戳，例如: `output/IMM-12345-25_20251123_081700.json`。

这些选项使脚本既适合本地交互式调试，也可在自动化/CI 环境中运行而不依赖浏览器。

### Python API使用
```python
from src.services.case_scraper_service import CaseScraperService
from src.services.export_service import ExportService

# 初始化服务
scraper = CaseScraperService()
exporter = ExportService()

# 抓取案件
case = scraper.scrape_single_case("https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22")

# 导出数据
exporter.export_all_formats([case], "case_data")
```

## Pre-commit & Code Quality

This project includes a starter `.pre-commit-config.yaml` with `isort`, `black`, and `flake8` hooks to help keep the codebase formatted and linted locally.

Install and enable hooks in your active environment:

```bash
pip install --upgrade pre-commit black isort flake8
pre-commit install --install-hooks
```

Run hooks across the repo:

```bash
pre-commit run --all-files
```

If you hit a hook you want to bypass temporarily, commit with `--no-verify`:

```bash
git commit --no-verify -m "WIP: skip hooks"
```

Note: the repository currently allows some flake8 warnings to be ignored in the starter config (e.g., long lines). If you want stricter checks, remove the ignored codes from `.pre-commit-config.yaml` and re-install hooks.

## Branch naming and workflow

- Use branch prefixes `feat/`, `fix/`, or `test/` to comply with project checks and CI. Example: `feat/federal-court-scraper`.
- Rename a branch locally and push:

```bash
# Rename current branch
git branch -m feat/your-branch-name
# Push and set upstream
git push origin -u feat/your-branch-name
```


## 输出文件格式

### JSON格式
```json
[
  {
    "case_id": "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22",
    "case_number": "IMM-12345-22",
    "title": "Case Title",
    "court": "Federal Court",
    "date": "2023-06-15",
    "html_content": "<html>...</html>",
    "scraped_at": "2023-06-15T10:30:00"
  }
]
```

### CSV格式
```csv
case_id,case_number,title,court,date,html_content,scraped_at
https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22,IMM-12345-22,Case Title,Federal Court,2023-06-15,<html>...</html>,2023-06-15T10:30:00
```

## 合规性保证

### 道德抓取原则
- **尊重网站**: 遵守robots.txt和使用条款
- **速率控制**: 避免对服务器造成过大负担
- **透明记录**: 完整记录所有操作和时间戳
- **错误恢复**: 优雅处理错误并自动重试

### 法律合规
- **仅用于合法目的**: 学术研究、法律分析等合法用途
- **数据隐私**: 不收集个人信息或敏感数据
- **版权尊重**: 仅提取公开可用的法院文件信息

## 故障排除

### 常见问题

**Q: 浏览器启动失败**
A: 确保已安装Chrome浏览器，或检查webdriver-manager配置

### 新增配置键：`docket_parse_max_errors`

- 目的：当解析 modal 中的 docket 行时，部分行可能因为页面重绘或异步内容导致解析失败。该配置控制在放弃并让上层重试之前，允许的最大解析错误行数。
- 默认值：`3`（见 `src/lib/config.py:DEFAULT_DOCKET_PARSE_MAX_ERRORS`）
- 配置位置：
  - `config.private.toml` / `config.toml` 中的 `[app] docket_parse_max_errors = <n>`，或
  - 环境变量 `FCT_DOCKET_PARSE_MAX_ERRORS`。
- 行为：当解析错误次数超过该阈值时，解析器将中止当前 modal 的解析并抛出异常，CLI 层会重新从搜索页面发起一次新的检索并重试抓取（可配置的重试次数由 `app.max_retries` 管理）。

此设置可减少保存部分/错误数据的风险，并允许在发生暂时性 DOM 问题时通过重新查询恢复。

**Q: URL验证失败**
A: 检查URL格式是否正确，域名是否为www.fct-cf.ca

**Q: 抓取速度太慢**
A: 这是故意设计的速率限制，如需调整请修改rate_limit_seconds参数

**Q: 连续错误触发紧急停止**
A: 检查网络连接，确认目标网站是否可访问

### 日志分析
程序会生成详细的日志文件，帮助诊断问题：
- INFO级别: 正常操作记录
- WARNING级别: 潜在问题提醒
- ERROR级别: 错误详情和堆栈跟踪

### 完整参数索引（逐项）

下面为项目中所有可用的命令行入口与参数做逐项索引，包含默认值和作用说明，便于在脚本和 CI 中精确调用。

1) `python -m src.cli.main` （推荐的主 CLI）

  - 全局选项:
    - `--force` : 全局强制标志，影响 `single` / `batch` 子命令，使其在数据库已存在记录时仍然重新抓取（布尔开关）。

  - 子命令 `single <case_number>` : 抓取单个案件
    - `case_number` (位置参数): 例如 `IMM-12345-25`。
    - `--force` : 强制重新抓取该案件。

  - 子命令 `batch <year>` : 批量抓取
    - `year` (位置参数): 目标年份，例如 `2025`。
    - `--max-cases <n>` : 限制抓取数量
    - `--force` : 强制重新抓取已存在的案件

  - 子命令 `stats` : 显示统计
    - `--year <year>` : 指定年份

  - 子命令 `purge <year>` : 年度清理（破坏性）
    - `year` (位置参数)
    - `--dry-run` : 列出将要删除的项目（不会做任何删除）
    - `--yes` : 非交互式确认（跳过提示）
    - `--backup <path>` : 备份目标路径
    - `--no-backup` : 跳过备份
    - `--files-only` : 仅处理文件系统，不触及数据库
    - `--db-only` : 仅处理数据库，不触及文件系统
    - `--sql-year-filter on|off|auto` : 控制是否在 SQL 查询层使用 YEAR() 过滤（`auto` 默认尝试 SQL；失败回退到 Python 过滤）
    - `--force-files` : 在 DB 删除失败时仍继续删除文件（需谨慎）

  - 典型用法示例：
    ```bash
    # 抓取单个案件
    python -m src.cli.main single IMM-12345-25

    # 批量抓取 2025 年，最多 50 个案件
    python -m src.cli.main batch 2025 --max-cases 50

    # 先做 dry-run 审计，再执行真正删除（非交互）
    python -m src.cli.main purge 2025 --dry-run
    python -m src.cli.main purge 2025 --yes --force-files
    ```

2) `python main.py` （轻量/演示入口）

  - 位置参数 `url`（可选）: 单个案件 URL，例如 `https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22`。
  - 选项:
    - `--batch <file>` : 指定包含 URL 的文件（每行一个 URL）
    - `--output <dir>` : 输出目录（默认 `./output`）
    - `--format json` : 导出格式（当前仅支持 `json`）
    - `--headless` / `--no-headless` : 控制浏览器是否以无头模式运行（`--headless` 默认为启用）

  - 示例：
    ```bash
    python main.py "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
    python main.py --batch urls.txt --output ./results --format json
    ```

3) 调试脚本 `scripts/auto_click_more.py`

  - 常用参数:
    - `--yes`, `-y` : 非交互式运行，跳过确认提示
    - `--non-interactive` : 与 `--yes` 等价
    - `--service-class <dotted_or_path:Class>` : 注入替代 Service 类（便于在 CI 中使用 FakeService）
      - 支持 `package.module.ClassName` 或 `path/to/file.py:ClassName` 两种格式
    - `--case <case_number>` : 指定要查询的案件编号（覆盖默认）

  - 行为说明：脚本会尝试调用注入服务的 `fetch_case_and_docket(case, non_interactive)`，若实现则直接使用结构化结果并退出；否则使用浏览器驱动流程打开搜索、点击“More”、解析 modal、并把 JSON 写入 `output/`。

4) 环境变量（有用的快捷配置）

  - `AUTO_CONFIRM=1` : 旧的跳过确认方式（被命令行 `--yes` 覆盖）
  - `CASE_NUMBER` : 当使用 `scripts/auto_click_more.py` 时作为默认 case
  - 配置相关的环境变量详见上方配置键一节（例如 `FCT_OUTPUT_DIR`, `FCT_MAX_RETRIES`, `FCT_DOCKET_PARSE_MAX_ERRORS` 等）

说明：以上参数来源于 `src/cli/main.py`、`main.py` 与 `scripts/auto_click_more.py` 的 argparse 定义，已经在本仓库代码中列出并在 docs 中同步。