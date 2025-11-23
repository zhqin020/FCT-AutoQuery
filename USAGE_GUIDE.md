# Federal Court Case Scraper - 使用指南
# 联邦法院案件抓取器 - 使用指南

## 程序运行流程

### 1. 程序初始化
```
初始化浏览器 → 设置速率限制器 → 配置日志系统 → 准备抓取服务
```

### 2. URL验证流程
```
输入URL → 域名验证 → 路径模式匹配 → 案件编号提取 → 验证通过/失败
```

### 3. 案件抓取流程
```
URL验证 → 速率限制检查 → 浏览器导航 → 页面加载等待 → HTML内容提取 → 数据解析 → 案件对象创建
```

### 4. 数据导出流程
```
案件数据验证 → 格式转换 → 文件写入 → 完整性检查 → 导出完成
```

## 从法院网站抓取信息的详细过程

### 网站结构分析
加拿大联邦法院网站 (www.fct-cf.ca) 的案件信息主要位于：
- **英文路径**: `/en/court-files-and-decisions/`
- **案件URL格式**: `https://www.fct-cf.ca/en/court-files-and-decisions/{CASE_NUMBER}`

### 抓取步骤详解

#### 步骤1: URL验证
```python
# 使用URL验证器检查URL有效性
is_valid, reason = URLValidator.validate_case_url(url)
```

**验证规则**:
- 域名必须是 `www.fct-cf.ca` 或 `fct-cf.ca`
- 路径必须包含 `/en/court-files-and-decisions`
- URL必须是有效的HTTP/HTTPS链接

#### 步骤2: 速率限制控制
```python
# 实现1秒间隔的请求限制
wait_time = self.rate_limiter.wait_if_needed()
```

**合规措施**:
- 每次请求间隔至少1秒
- 自动计算等待时间
- 记录所有请求时间戳

#### 步骤3: 浏览器自动化
```python
# 使用Selenium WebDriver控制Chrome浏览器
driver = webdriver.Chrome(service=service, options=options)
driver.get(url)
```

**浏览器配置**:
- 无头模式运行（可选）
- 设置合适的窗口大小
- 配置用户代理字符串
- 禁用GPU加速（服务器环境）

#### 步骤4: 页面内容提取
```python
# 等待页面加载完成后获取HTML内容
time.sleep(2)  # 简单的等待实现
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
```

**解析方法**:
- **标题提取**: 优先从`<title>`标签提取，其次从内容中查找案件编号
- **案件编号**: 从URL路径或HTML内容中正则匹配 `IMM-[A-Z0-9-]+` 模式
- **日期提取**: 识别多种日期格式 (YYYY-MM-DD, MM/DD/YYYY, YYYY/MM/DD)

#### 步骤6: 数据验证与对象创建
```python
# 创建标准化的案件数据对象
case = Case.from_url(
    url=url,
    case_number=case_number,
    title=title,
    court="Federal Court",
    case_date=case_date,
    html_content=html_content
)
```

**数据验证**:
- 案件编号格式验证
- HTML内容非空检查
- 日期格式标准化
- 数据完整性检查

#### 步骤7: 错误处理与紧急停止
```python
# 监控连续错误并触发保护机制
if self._consecutive_errors >= self._max_consecutive_errors:
    self.emergency_stop()
```

**保护机制**:
- 连续5次错误触发紧急停止
- 自动记录错误日志
- 资源清理和状态重置

## 实际使用示例

### 命令行运行
```bash
# 单个案件抓取
python main.py "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"

# 批量抓取
python main.py --batch example_cases.txt

# 指定输出格式和目录
python main.py --format json --output ./results "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
```

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