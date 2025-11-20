这份文档是基于您提供的**人工操作流程**、**数据截图**以及**技术方案**整理而成的详细软件需求规格说明书 (SRS)。它可以作为项目开发、测试和验收的基准文档。

---

# 软件需求规格说明书 (SRS)

**项目名称**：联邦法院案件自动查询系统 (FCT-AutoQuery)
**版本号**：V1.0
**日期**：2025-11-20
**运行环境**：Windows Subsystem for Linux (WSL) / Python

---

## 1. 引言 (Introduction)

### 1.1 目的
本系统旨在自动化访问加拿大联邦法院 (Federal Court) 官方网站，批量查询指定年份范围内的移民类 (IMM) 案件。系统需模拟人工操作流程，抓取案件的基础信息及详细审理记录 (Docket Entries)，并将数据持久化存储至 PostgreSQL 数据库及 JSON 文件中。

### 1.2 范围
*   **数据源**：[Federal Court Files](https://www.fct-cf.ca/en/court-files-and-decisions/court-files)
*   **目标数据**：2020年至2025年间，编号 1-99999 的所有 `IMM` 开头案件。
*   **核心功能**：自动化搜索、模态框(Modal)数据提取、断点续传、防封控休眠。

---

## 2. 业务流程描述 (Business Process)

系统需完全模拟以下人工操作路径：

1.  **初始化**：打开网页 -> 点击 "Search by court number" 标签页 -> 下拉菜单选择 "Federal Court"。
2.  **循环查询**：
    *   输入案号 (如 `IMM-1234-25`) -> 点击 Submit。
    *   **判断**：
        *   若显示 "No data available" -> 记录无结果 -> 进入下一案号。
        *   若显示结果表格 -> 点击 "More" 链接。
3.  **详情抓取**：
    *   等待详情模态框 (Modal) 弹出。
    *   抓取顶部案件元数据 (Header)。
    *   抓取底部历史记录表格 (Recorded Entry Information)。
4.  **收尾**：点击 "Close" 关闭模态框 -> 随机休眠 -> 准备下一查询。

---

## 3. 功能性需求 (Functional Requirements)

### 3.1 搜索配置与初始化模块
*   **FR-01 页面初始化**：
    *   系统启动时，必须加载目标 URL。
    *   **自动切换标签**：定位并点击 `Search by court number` Tab。
    *   **自动选择法院**：在 Court 下拉列表中选中 `Federal Court` (排除 Appeal Court)。
*   **FR-02 案号生成器**：
    *   格式规则：`IMM-{流水号}-{年份}`。
    *   流水号：`1` 至 `99999` 。
    *   年份：`20` 至 `25`。
    *   **断点续传**：程序启动时，应查询数据库中已存在的最大流水号，从下一号开始运行，避免重复工作。

### 3.2 自动化交互模块
*   **FR-03 搜索执行**：
    *   在输入框清空并填入当前案号。
    *   点击 `Submit` 按钮。
*   **FR-04 结果状态判定**：
    *   系统需智能等待页面响应（Wait Strategy）。
    *   **分支 A (无记录)**：若页面出现 "No data available in table"，标记该案号不存在。
    *   **分支 B (有记录)**：若页面出现 "More" 按钮/链接，触发点击操作。
    *   **分支 C (连续无记录)**：如果出现连续几个号码都无记录，系统应自动跳到下一个年份。
*   **FR-05 模态框(Modal)管理**：
    *   点击 "More" 后，必须等待模态框 DOM 元素可见。
    *   数据抓取完成后，必须定位并点击 "Close" / "Fermer" / "×" 按钮。
    *   **异常处理**：若关闭失败，系统需执行页面刷新 (`driver.refresh()`) 并重新执行 FR-01 的初始化步骤，以防止遮罩层阻挡后续搜索。

### 3.3 数据采集模块 (基于截图)
系统需从详情模态框中提取以下两类数据：

*   **FR-06 案件基础信息 (Header)**：
    *   `Court File No.` (案号)
    *   `Type` (案件类型，如 Immigration Matters)
    *   `Type of Action` (行动类型)
    *   `Nature of Proceeding` (程序性质，长文本)
    *   `Filing Date` (立案日期)
    *   `Office` (办事处，如 Toronto)
    *   `Style of Cause` (当事人，长文本)
    *   `Language` (语言)
    *   *注：需通过 Label 文本定位其后的值。*

*   **FR-07 历史审理记录 (Recorded Entries Table)**：
    *   遍历表格所有行，提取：
        *   `ID` (序号)
        *   `Date Filed` (提交日期)
        *   `Office` (提交地)
        *   `Recorded Entry Summary` (摘要内容)

### 3.4 数据存储模块
*   **FR-08 数据库存储 (PostgreSQL)**：
    *   数据写入 `cases` 表 (主键为案号)。
    *   历史记录写入 `docket_entries` 表 (外键关联案号)。
    *   支持 `UPSERT` 操作：若案号已存在，则更新状态和历史记录。
*   **FR-09 文件备份 (JSON)**：
    *   每个案件生成一个独立的 JSON 文件。
    *   命名格式：`./data/{YEAR}/{CASE_ID}.json`。

---

## 4. 数据需求 (Data Specifications)

### 4.1 数据库 Schema 设计

**表 1: cases (案件主表)**
| 字段名 | 类型 | 说明 | 约束 |
| :--- | :--- | :--- | :--- |
| `case_id` | VARCHAR(20) | 案号 (e.g., IMM-1234-25) | PRIMARY KEY |
| `style_of_cause` | TEXT | 案件标题/当事人 | |
| `nature_of_proceeding`| TEXT | 案件性质 | |
| `filing_date` | DATE | 立案日期 | |
| `office` | VARCHAR(50) | 办事处 | |
| `case_type` | VARCHAR(100)| (新增) Type | |
| `action_type` | VARCHAR(100)| (新增) Type of Action | |
| `crawled_at` | TIMESTAMP | 抓取时间 | Default NOW() |

**表 2: docket_entries (历史记录表)**
| 字段名 | 类型 | 说明 | 约束 |
| :--- | :--- | :--- | :--- |
| `id` | SERIAL | 自增主键 | PRIMARY KEY |
| `case_id` | VARCHAR(20) | 关联案号 | FOREIGN KEY |
| `doc_id` | INTEGER | 网站显示的序号 | |
| `entry_date` | DATE | 提交日期 | |
| `entry_office` | VARCHAR(50) | 提交地 | |
| `summary` | TEXT | 摘要内容 | |


*联合唯一约束*：`UNIQUE(case_id, doc_id)`，防止重复插入相同记录。

---

## 5. 非功能性需求 (Non-Functional Requirements)

### 5.1 性能与效率
*   **NFR-01 采集频率**：鉴于无代理 IP 环境，单次查询间隔需设置为 **3 至 6 秒** 的随机值。
*   **NFR-02 长时运行**：每连续查询 **100** 次，强制休眠 **60 秒**，以模拟人类休息。

### 5.2 可靠性与健壮性
*   **NFR-03 异常恢复**：
    *   网络超时 (Timeout) 应重试 3 次。
    *   页面元素定位失败 (NoSuchElement) 应记录日志并跳过当前案件。
*   **NFR-04 浏览器环境**：
    *   模式：Headless Chrome (无头模式)。
    *   参数：`--no-sandbox`, `--disable-dev-shm-usage` (适配 WSL 环境)。

### 5.3 交付物
*   Python 源代码脚本。
*   `requirements.txt` 依赖列表。
*   数据库初始化 SQL 脚本。

---

## 6. 风险与约束 (Risks & Constraints)

1.  **网站改版风险**：如果法院网站修改了 ID 命名或 HTML 结构（特别是模态框的实现方式），脚本将需要维护更新。
2.  **IP 封禁风险**：虽然设置了延时，但连续数万次请求仍可能触发 WAF (Web Application Firewall)。
    *   *缓解措施*：脚本需捕获 HTTP 403 错误，一旦发现立即停止运行并报警，而不是继续尝试。
3.  **数据一致性**：由于网络原因，极少数详情页可能加载不完全。脚本应校验“表格行数”是否大于0（针对有记录的案件）。

---

## 7. 验收标准 (Acceptance Criteria)

1.  程序能在 WSL 环境下无报错启动。
2.  程序能正确自动点击 Tab 和 Dropdown 完成页面初始化。
3.  程序能准确区分“无结果”和“有结果”的案件。
4.  对于有结果的案件，数据库中 `cases` 表和 `docket_entries` 表均有正确数据写入。
5.  生成的 JSON 文件格式合法，且包含截图所示的所有字段。
6.  程序在遇到网络波动时不会崩溃，而是重试或跳过。

## 8. 附联邦法院网站查询功能，人工操作流程

1. 进入 页面： https://www.fct-cf.ca/en/court-files-and-decisions/court-files
2.  点击 'Search by court number' Tab,  切换到查询Form
3. 在Court 下拉框中，选择 'Federal Court',  其余两项是'Federal Court of Apeal', 'Both'
4. 在 'Search by court number:' 输入框中，输入编号，比如 IMM-23456-25'
5. 点击 'Submit'
6.  下面会显示一个表格，如果没有结果，表格中显示 'No data available in table'
7.  如果有记录，将显示查找结果，columns: 'Court Number', 'Style of Cause', 'Nature of Processing', 'Parties', 'More'
8. 点击 'Parties' cell，会弹出一个对话框，显示案件双方的信息
9. 点击 'More' cell, 会弹出详情对话框，我们需要采集的数据全部在这个页面中
10. 点击 'Close' 关闭对话框
11. 输入下一个编号，继续查询
