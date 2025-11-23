# FCT-AutoQuery
联邦法院案件自动查询系统

[![Tests](https://img.shields.io/badge/tests-49%20passed-brightgreen)](https://github.com/zhqin020/FCT-AutoQuery)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

一个用于自动查询和导出加拿大联邦法院案件信息的专业工具，采用测试驱动开发(TDD)方法构建，具有完整的合规性和数据导出功能。

## ✨ 主要特性

### 🔍 智能案件查询
- 自动化的网络爬虫技术
- 支持加拿大联邦法院网站数据抓取
- 智能URL验证和发现机制

### 🛡️ 合规性与道德设计
- **速率限制**: 1秒间隔的请求限制，保护目标服务器
- **紧急停止**: 实时监控和紧急停止功能
- **URL验证**: 严格的联邦法院域名验证
- **日志记录**: 完整的审计日志记录所有操作

### 📊 结构化数据导出
- **JSON格式**: 结构化数据导出，支持复杂数据类型
- **CSV格式**: 兼容Excel的CSV导出，自动处理特殊字符
- **数据验证**: 导出前完整的数据完整性检查
- **批量导出**: 支持同时导出为多种格式

### 🧪 全面测试覆盖
- **49个测试用例**，100%通过率
- 合同测试、集成测试、单元测试
- 端到端测试验证完整工作流程

## 🏗️ 系统架构

```
src/
├── models/
│   └── case.py              # 案件数据模型
├── services/
│   ├── case_scraper_service.py    # 案件抓取服务
│   ├── export_service.py          # 数据导出服务
│   └── url_discovery_service.py   # URL发现服务
└── lib/
    └── url_validator.py           # URL验证工具

tests/
├── contract/                 # 合同测试
├── integration/             # 集成测试
└── unit/                    # 单元测试

specs/                       # 项目规格和任务管理
├── 0001-federal-court-scraper/
│   ├── spec.md             # 功能规格说明
│   ├── plan.md            # 技术实现计划
│   ├── tasks.md           # 任务跟踪
│   └── contracts/         # API合同定义
```

## 🚀 快速开始

### 环境要求
- Python 3.11+
- Chrome浏览器（用于Selenium自动化）

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

4. **运行测试验证安装**
   ```bash
   python -m pytest tests/ -v
   ```

## 📖 使用指南

### 命令行使用

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
```

#### 查看统计信息
```bash
# 查看所有年份的总案件数
python -m src.cli.main stats

# 查看特定年份的统计
python -m src.cli.main stats --year 2025
```

### Python API使用

```python
from src.cli.main import FederalCourtScraperCLI

# 初始化CLI
cli = FederalCourtScraperCLI()

# 抓取单个案件
case = cli.scrape_single_case("IMM-12345-25")

# 批量抓取
cases = cli.scrape_batch_cases(2025, max_cases=10)

# 导出数据
export_result = cli.export_cases(cases, "federal_court_cases")
```

### 批量处理示例

运行批量抓取2025年的案件：
```bash
python -m src.cli.main batch 2025
```

这将：
1. 从上次中断处继续（如果有的话）
2. 使用搜索表单查找案件
3. 提取案件详情和法庭记录
4. 保存到PostgreSQL数据库
5. 导出为JSON和CSV文件
```bash
python main.py --batch cases.txt
```

### 运行演示脚本

项目包含一个演示脚本，可以快速了解程序功能：

```bash
# 运行演示脚本（无需真实URL）
python demo.py
```

演示脚本会：
- 验证URL格式
- 创建模拟案例数据
- 演示JSON/CSV导出功能
- 生成示例输出文件

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

项目采用规范化的开发流程：

- **功能规格**: `specs/0001-federal-court-scraper/spec.md`
- **技术计划**: `specs/0001-federal-court-scraper/plan.md`
- **任务跟踪**: `specs/0001-federal-court-scraper/tasks.md`
- **API合同**: `specs/0001-federal-court-scraper/contracts/`

## 🔧 开发工具

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

---

**最后更新**: 2025年11月21日
**版本**: v1.0.0 (功能完整实现)
