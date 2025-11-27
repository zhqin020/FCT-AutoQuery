

# 需求：联邦法院移民案件数据统计分析
**日期**：2025-11-26
**状态**：待开发

## 1. 背景与目标
### 1.1 背景
目前拥有一批加拿大联邦法院（Federal Court）的移民案件记录（JSON格式）。这些数据包含案件基本信息及详细的案卷记录（Docket Entries）。目前依靠人工阅读分析效率低下且难以发现宏观趋势。

### 1.2 目标
开发自动化分析模块，独立于目前的采集功能，结合 **规则匹配** 与 **本地 LLM (大语言模型)** 技术，对案件进行清洗、分类和统计，最终生成可视化的报表。

### 1.3 核心价值
*   **趋势洞察**：了解每月案件量及积压情况。
*   **效率评估**：计算案件处理的平均周期、中位数周期。
*   **策略辅助**：通过分析不同签证处（Visa Office）和法官的判决倾向，辅助移民律师制定策略。

---

## 2. 数据源说明
*   **输入格式**：采集输出的JSON 文件（数组结构）。
*   **核心字段**：
    *   `case_number`: 案件编号
    *   `filing_date`: 立案日期
    *   `title`: 案件标题
    *   `office`: 法院办事处（如 Toronto, Vancouver）
    *   `docket_entries`: 案卷记录列表（包含 `summary` 摘要和 `entry_date` 日期）

---

## 3. 功能需求 (Functional Requirements)

### 3.1 数据清洗与预处理 (Data Preprocessing)
*   **P0 (最高优先级)**: 解析 JSON 文件，处理日期格式（YYYY-MM-DD）。
*   **P0**: 处理缺失数据（如无立案日期的记录需剔除或标记）。

### 3.2 案件分类逻辑 (Classification Logic)
系统需支持两种分类模式：**快速模式（规则匹配）** 和 **精准模式（LLM分析）**。

#### A. 案件类型 (Case Type)
*   **Mandamus (强制令)**:
    *   *规则*: Title 或 Docket Summary 中包含 "Mandamus", "compel", "delay"。
    *   *LLM*: 根据案情描述判断是否为强制令申请。
*   **Judicial Review (司法审查/其他)**: 不符合上述条件的归为 Other。

#### B. 案件状态 (Case Status) & 结束日期
优先级逻辑如下（一旦匹配即终止）：
1.  **Discontinued (撤销)**: 检测到 "Notice of Discontinuance"。
    *   *业务含义*: 申请人主动撤诉（通常意味着 IRCC 已妥协或发签）。
2.  **Granted (胜诉/批准)**: 检测到判决结果为 "Granted" 或 "Allowed"。
3.  **Dismissed (驳回)**: 检测到 "Dismissed"（含 Leave Dismissed 许可被拒）。
4.  **Ongoing (进行中)**: 无上述终局状态。

### 3.3 实体提取 (Entity Extraction) - **需使用 LLM**
*   **P1**: **Visa Office (签证处)**: 从 Docket 文本中提取具体的签证中心地点（如 Beijing, Ankara, New Delhi），而非仅仅使用法院的 Office。
*   **P2**: **Judge (法官)**: 提取做出最终裁决的法官姓名。

---

## 4. 统计分析需求 (Statistical Analysis)

### 4.1 周期统计 (Duration Metrics)
需计算以下时间指标（单位：天）：
*   **结案时长 (Time to Close)**: `结案日期` - `立案日期`（仅针对已结案）。
*   **当前案龄 (Age of Case)**: `当前日期` - `立案日期`（仅针对进行中）。
*   **Rule 9 等待期**: `立案日期` 到 `Rule 9 记录收到日期` 的时长（衡量移民局移交档案的速度）。

**统计维度**：
*   平均值 (Mean)
*   中位数 (Median)
*   最大值 (Max) / 最小值 (Min)

### 4.2 趋势与分布 (Trends & Distribution)
*   **月度趋势**: 按 `YYYY-MM` 统计各类案件的提交数量。
*   **地域分布**:
    *   按法院 (Court Office): Toronto vs Vancouver 等。
    *   按签证处 (Visa Office): 统计哪些海外签证处的被诉案件最多。

### 4.3 成功率分析 (Success Metrics)
*   **Mandamus 隐性胜诉率**: 统计 Mandamus 案件中 `Discontinued` 的比例（视为达到了催办目的）。
*   **许可通过率 (Leave Grant Rate)**: 统计进入实质审理阶段的比例。

---

## 5. 技术架构与非功能需求

### 5.1 技术栈建议
*   **编程语言**: Python 3.9+
*   **数据处理**: Pandas, NumPy
*   **AI 模型**:
    *   工具: Ollama (本地部署)
    *   模型: `qwen2.5-7b-instruct` 或 `llama3-8b` (平衡速度与准确性)
    *   交互: Python `requests` 库调用 Ollama API
*   **输出**: CSV / Excel (.xlsx)

### 5.2 性能要求
*   **规则模式**: 5000 条案件记录处理时间 < 10秒。
*   **LLM 模式**: 支持断点续传（处理大量数据时，如果中断，下次能接着跑）。

---

## 6. 输出交付物 (Deliverables)

### 报表 1: 案件明细表 (Case Details)
| Case ID | Title | Filing Date | Court Office | **Visa Office (LLM)** | Type | Status | Outcome Date | Duration (Days) | Judge (Optional) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| IMM-1 | ... | 2024-12-01 | Toronto | Beijing | Mandamus | Discontinued | 2025-01-15 | 45 | - |

### 报表 2: 统计概览 (Summary Report)
1.  **总体概况**: 总案件数、进行中、已结案。
2.  **时长分析**: 
    *   Mandamus 平均结案时间 vs. Other 平均结案时间。
    *   各签证处 (Visa Office) 平均案龄热力数据。
3.  **月度流量表**: 每月立案数、每月结案数。

---
 
#### 7. 可视化报表需求 (Visualization Requirements)

我们不仅仅需要表格，还需要生成一个**图表仪表盘 (Dashboard)**，核心关注以下四个维度：

**7.1 案件量趋势图 (Volume Trend)**
*   **图表类型**: 堆叠柱状图 (Stacked Bar Chart)
*   **X轴**: 月份 (YYYY-MM)
*   **Y轴**: 案件数量
*   **颜色分组**: 案件类型 (Mandamus / Other) 或 状态 (进行中 / 已结案)
*   **业务价值**: 直观展示案件量的增长趋势，以及每个月新案的构成。

**7.2 处理周期箱线图 (Duration Box Plot) —— *核心图表***
*   **图表类型**: 箱线图 (Box & Whisker Plot)
*   **X轴**: 案件类型 (Mandamus vs. Other) 或 签证处 (Visa Office)
*   **Y轴**: 天数 (Days)
*   **展示内容**: 显示中位数(Median)、上/下四分位数(25%-75%的大多数案件范围)以及异常值(Outliers)。
*   **业务价值**: 客户最关心“大概要等多久”。平均值容易被极端长案子拉高，**箱线图能告诉客户“正常情况下”的等待范围**。

**7.3 结案结果分布图 (Outcome Distribution)**
*   **图表类型**: 环形图 (Donut Chart)
*   **切片**: 撤销 (Discontinued)、胜诉 (Granted)、驳回 (Dismissed)、进行中 (Ongoing)。
*   **业务价值**: 展示案件的“隐性成功率”（如 Mandamus 的高撤诉率通常代表成功）。

**7.4 签证处/法院热力图 (Geo/Office Heatmap)**
*   **图表类型**: 水平条形图 (Horizontal Bar Chart) 或 热力图矩阵。
*   **维度**: 
    *   Y轴: 签证处名称 (如 Beijing, Ankara, Delhi) - *需通过 LLM 提取*
    *   X轴: 平均结案天数
    *   颜色深浅: 案件数量
*   **业务价值**: **高价值图表**。一眼识别出哪个签证处是“黑洞”（处理慢且量大），哪个签证处效率高。

---

### 二、 技术实现方案 (Python Code)

在之前的 Python 脚本基础上，我们将引入 `matplotlib` 和 `seaborn` (用于静态图片) 或 `plotly` (用于交互式网页图表)。

**推荐方案**：使用 **Seaborn** 生成静态图片报告（适合插入 Word/PDF），简单、美观且无需前端知识。
 
### 三、 为什么选择这几种图表？（给开发人员的解释）

1.  **箱线图 (Box Plot)** 是法律数据分析的神器。
    *   客户问：“强制令要多久？”
    *   平均值说：“90天。”（但这可能被一个拖了3年的案子拉高了）
    *   箱线图说：“**50% 的案子在 45天 到 75天 之间**（箱体），中位数是 60天。” —— **这对预期管理非常重要**。

2.  **双轴图 (Bar + Line)** 用于地区分析。
    *   可以同时展示 **“哪里案子多”** (柱状) 和 **“哪里处理慢”** (折线)。如果某个办事处柱子很高（案子多）但红线很低（速度快），说明效率高。

3.  **堆叠柱状图 (Stacked Bar)** 用于趋势。
    *   可以看到某个月份是不是突然爆发了很多 Mandamus 申请（可能是因为某个签证政策变动）。

### 四、 总结建议

在你的 **PRD** 中，加入上述“可视化需求”章节。在开发阶段，先让 LLM 把 `Visa Office`（签证处）提取出来，因为“法院办事处（Toronto）”的数据通常没有“签证处（Beijing/Ankara）”的数据对申请人更有参考价值。基于 Visa Office 做上面的图表分析，价值会翻倍。

## 8. 开发路线图 (Roadmap)

*   **阶段一 (MVP)**: 完成基于规则（关键字）的分类，输出基础的 CSV 统计（数量、状态、法院地区）。
*   **阶段二 (AI Integration)**: 接入 Ollama，实现"签证处提取"和更精准的"状态判断"，修正规则判断的误判。
*   **阶段三 (Advanced Analytics)**: 增加 Rule 9 延迟分析、法官倾向性分析、可视化图表生成。

---