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
python main.py "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
```

#### 批量抓取
```bash
# 使用包含多个URL的文件
python main.py --batch example_cases.txt
```

#### 指定输出格式和目录
```bash
# 只导出JSON格式
python main.py --format json --output ./results "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"

# 只导出CSV格式
python main.py --format csv --output ./results "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"

# 同时导出两种格式（默认）
python main.py --output ./results "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
```

#### 显示浏览器窗口（调试用）
```bash
python main.py --no-headless "https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22"
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

### 批量处理示例

创建包含多个URL的文件 `cases.txt`：
```
https://www.fct-cf.ca/en/court-files-and-decisions/IMM-12345-22
https://www.fct-cf.ca/en/court-files-and-decisions/IMM-67890-23
https://www.fct-cf.ca/en/court-files-and-decisions/IMM-11111-24
```

运行批量抓取：
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

## 📞 联系方式

- 项目维护者: [zhqin020](https://github.com/zhqin020)
- 项目主页: https://github.com/zhqin020/FCT-AutoQuery
- 问题反馈: [Issues](https://github.com/zhqin020/FCT-AutoQuery/issues)

---

**最后更新**: 2025年11月21日
**版本**: v1.0.0 (功能完整实现)
