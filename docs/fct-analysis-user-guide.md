# FCT 数据分析程序使用指南

## 目录
1. [概述](#概述)
2. [安装与配置](#安装与配置)
3. [快速开始](#快速开始)
4. [功能详解](#功能详解)
5. [输入数据格式](#输入数据格式)
6. [输出结果说明](#输出结果说明)
7. [高级用法](#高级用法)
8. [故障排除](#故障排除)
9. [最佳实践](#最佳实践)
10. [常见问题](#常见问题)

---

## 概述

### 什么是 FCT 数据分析程序？

FCT (Federal Court of Canada) 数据分析程序是一个专门用于分析加拿大联邦法院移民案件的自动化工具。该程序能够：

- **自动分类案件**：将案件分为强制令(Mandamus)和司法审查(Other)类型
- **智能状态判断**：识别案件的当前状态（撤销/胜诉/驳回/进行中）
- **实体提取**：从案件文本中提取签证处和法官信息
- **统计分析**：计算处理时长、案龄、Rule 9等待期等关键指标
- **可视化报表**：生成专业的分析图表

### 核心价值

1. **趋势洞察**：了解每月案件量及积压情况
2. **效率评估**：计算案件处理的平均周期、中位数周期
3. **策略辅助**：通过分析不同签证处和法官的判决倾向，辅助制定策略

---

## 安装与配置

### 系统要求

- **Python版本**：3.9+
- **内存要求**：基础功能 4GB，LLM模式 8GB+
- **存储空间**：至少 1GB 可用空间

### 依赖安装

1. **克隆项目**
```bash
git clone <repository-url>
cd FCT-AutoQuery
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **可选：安装 Ollama（LLM模式）**
```bash
# Ubuntu/Debian
curl -fsSL https://ollama.ai/install.sh | sh

# 或访问 https://ollama.ai/download 下载对应版本
```

4. **下载 LLM 模型**
```bash
# 推荐模型
ollama pull qwen2.5-7b-instruct
# 或
ollama pull llama3-8b
```

### 配置验证

```bash
# 验证基础安装
python -c "import fct_analysis; print('基础模块安装成功')"

# 验证 Ollama 连接（可选）
ollama list
```

---

## 快速开始

### 1. 准备数据

确保您有一个包含案件数据的 JSON 文件，格式如下：

```json
[
  {
    "case_number": "IMM-1-23",
    "filing_date": "2024-01-15",
    "title": "Mandamus action to compel processing",
    "office": "Toronto",
    "docket_entries": [
      {"entry_date": "2024-01-15", "summary": "Complaint filed"},
      {"entry_date": "2024-03-20", "summary": "Rule 9 notice issued"}
    ]
  }
]
```

### 2. 运行分析

**规则模式（推荐新手使用）**
```bash
python -m fct_analysis.cli -i cases.json --mode rule -o results/
```

**LLM模式（更精准的分析）**
```bash
python -m fct_analysis.cli -i cases.json --mode llm -o results/
```

### 3. 查看结果

```bash
# 查看分析结果
ls results/
cat results/federal_cases_0005_summary.json

# 生成图表
python -c "from fct_analysis import plots; plots.make_charts('results/federal_cases_0005_details.csv', 'results/charts')"
```

---

## 功能详解

### 双模式分析系统

#### 规则模式
- **速度**：快速处理（5000条 < 10秒）
- **方法**：基于关键词和正则表达式匹配
- **适用**：日常分析、快速概览、大批量数据

```bash
python -m fct_analysis.cli -i data.json --mode rule -o output/
```

#### LLM模式
- **精度**：更准确的实体提取和状态判断
- **依赖**：需要本地 Ollama 服务
- **适用**：精准分析、重要案件、深度研究

```bash
# 确保 Ollama 运行中
ollama serve

# 运行 LLM 分析
python -m fct_analysis.cli -i data.json --mode llm -o output/
```

### 案件分类逻辑

#### 案件类型分类

**Mandamus（强制令）**
- 规则关键词：`Mandamus`, `compel`, `delay`
- 应用场景：催促移民局处理申请的案件

**Other（司法审查）**
- 其他所有不匹配强制令条件的案件

#### 案件状态判断

按优先级检测，一旦匹配即终止：

1. **Discontinued（撤销）**
   - 关键词：`Notice of Discontinuance`
   - 含义：申请人主动撤诉，通常意味着已达成目的

2. **Granted（胜诉）**
   - 关键词：`Granted`, `Allowed`
   - 含义：法院支持申请人请求

3. **Dismissed（驳回）**
   - 关键词：`Dismissed`, `Leave Dismissed`
   - 含义：法院拒绝申请

4. **Ongoing（进行中）**
   - 默认状态，无上述终局状态标记

### 时间指标计算

#### 结案时长（Time to Close）
```python
结案日期 - 立案日期
```
- 适用：已结案案件
- 用途：评估案件处理效率

#### 当前案龄（Age of Case）
```python
当前日期 - 立案日期
```
- 适用：进行中案件
- 用途：监控积压情况

#### Rule 9 等待期
```python
Rule 9记录日期 - 立案日期
```
- 适用：包含 Rule 9 标记的案件
- 用途：评估移民局档案移交速度

---

## 输入数据格式

### 必需字段

| 字段名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `case_number` | string | 案件编号 | "IMM-1-23" |
| `filing_date` | string | 立案日期 | "2024-01-15" |
| `docket_entries` | array | 案卷记录 | 见下方格式 |

### 可选字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `title` | string | 案件标题 |
| `style_of_cause` | string | 案件样式 |
| `office` | string | 法院办事处 |
| `court` | string | 法院名称 |
| `html_content` | string | HTML 内容（LLM 上下文） |

### Docket Entries 格式

```json
{
  "docket_entries": [
    {
      "entry_date": "2024-01-15",
      "summary": "Complaint filed",
      "doc_id": 1,
      "entry_office": null
    },
    {
      "entry_date": "2024-03-20", 
      "summary": "Rule 9 notice issued: referred to IRCC",
      "doc_id": 2,
      "entry_office": null
    }
  ]
}
```

### 数据质量要求

1. **日期格式**：推荐 ISO 格式 YYYY-MM-DD
2. **编码**：UTF-8 编码
3. **完整性**：缺失字段不影响处理，但会影响分析准确性

---

## 输出结果说明

### 文件结构

```
output/
├── federal_cases_0005_details.csv     # 详细数据表
├── federal_cases_0005_summary.json    # 统计摘要
└── plots/                             # 图表目录（可选）
    ├── volume_trend.png               # 案件量趋势图
    ├── duration_boxplot.png            # 处理周期箱线图
    ├── outcome_donut.png              # 结案结果分布图
    └── visa_office_heatmap.png        # 签证处效率图
```

### CSV 详细数据表

包含以下列：

| 列名 | 说明 | 示例 |
|------|------|------|
| `case_number` | 案件编号 | IMM-1-23 |
| `filing_date` | 立案日期 | 2024-01-15 |
| `type` | 案件类型 | Mandamus/Other |
| `status` | 案件状态 | Discontinued/Granted/Dismissed/Ongoing |
| `duration_days` | 处理时长 | 45 |
| `age_of_case` | 案龄 | 150 |
| `rule9_wait` | Rule 9 等待期 | 20 |

### JSON 统计摘要

```json
{
  "total_cases": 150,
  "rows": 150,
  "mandamus_cases": 80,
  "other_cases": 70,
  "discontinued_rate": 0.35,
  "avg_duration": 120.5
}
```

### 可视化图表

#### 1. 案件量趋势图（volume_trend.png）
- **类型**：堆叠柱状图
- **X轴**：月份（YYYY-MM）
- **Y轴**：案件数量
- **用途**：观察案件增长趋势

#### 2. 处理周期箱线图（duration_boxplot.png）
- **类型**：箱线图
- **X轴**：案件类型
- **Y轴**：处理天数
- **用途**：了解正常处理时间范围

#### 3. 结案结果分布图（outcome_donut.png）
- **类型**：环形图
- **内容**：各状态占比
- **用途**：查看成功率分布

#### 4. 签证处效率图（visa_office_heatmap.png）
- **类型**：水平条形图
- **维度**：签证处 vs 平均处理时间
- **用途**：识别高效和低效签证处

---

## 高级用法

### 断点续传

LLM模式处理大量数据时，如果中断可以继续：

```bash
# 第一次运行
python -m fct_analysis.cli -i large_data.json --mode llm -o output/

# 中断后继续
python -m fct_analysis.cli -i large_data.json --mode llm --resume -o output/
```

### 自定义 Ollama 地址

```bash
# 使用远程 Ollama 服务
python -m fct_analysis.cli -i data.json --mode llm --ollama-url http://192.168.1.100:11434 -o output/
```

### 审计采样

记录 LLM 分析的样本用于质量检查：

```bash
# 记录前 10 个 LLM 分析结果
python -m fct_analysis.cli -i data.json --mode llm --sample-audit 10 -o output/

# 查看审计样本
cat logs/0005_llm_audit_samples.ndjson
```

### 批量处理

处理多个数据文件：

```bash
#!/bin/bash
# batch_process.sh

for file in data/*.json; do
  output_dir="results/$(basename "$file" .json)"
  python -m fct_analysis.cli -i "$file" --mode rule -o "$output_dir"
done
```

### 自定义分析脚本

```python
#!/usr/bin/env python3
# custom_analysis.py

from fct_analysis import parser, rules, metrics, plots
import pandas as pd

def custom_analysis(input_file, output_dir):
    # 1. 解析数据
    df = parser.parse_cases(input_file)
    
    # 2. 自定义分类
    df['custom_type'] = df['raw'].apply(lambda x: 
        'priority' if 'urgent' in str(x).lower() else 'normal')
    
    # 3. 计算指标
    df = metrics.compute_durations(df)
    
    # 4. 保存结果
    df.to_csv(f"{output_dir}/custom_analysis.csv", index=False)
    
    # 5. 生成图表
    plots.make_charts(f"{output_dir}/custom_analysis.csv", 
                     f"{output_dir}/charts")

if __name__ == "__main__":
    custom_analysis("data.json", "custom_results")
```

---

## 故障排除

### 常见错误及解决方案

#### 1. ImportError: No module named 'fct_analysis'

**原因**：Python 路径问题或安装不完整

**解决方案**：
```bash
# 方法1：使用 PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
python -m fct_analysis.cli -i data.json

# 方法2：直接运行
python src/fct_analysis/cli.py -i data.json
```

#### 2. ModuleNotFoundError: No module named 'matplotlib'

**原因**：缺少可视化依赖

**解决方案**：
```bash
pip install matplotlib seaborn pandas numpy
```

#### 3. ConnectionError: Failed to connect to Ollama

**原因**：Ollama 服务未运行或配置错误

**解决方案**：
```bash
# 启动 Ollama 服务
ollama serve

# 检查服务状态
curl http://localhost:11434/api/version

# 重新运行分析
python -m fct_analysis.cli -i data.json --mode llm
```

#### 4. JSONDecodeError: Expecting value

**原因**：输入 JSON 文件格式错误

**解决方案**：
```bash
# 验证 JSON 格式
python -m json.tool data.json > /dev/null

# 修复常见问题
# 1. 检查是否包含 BOM
# 2. 检查是否为有效数组格式
# 3. 检查特殊字符转义
```

#### 5. KeyError: 'type'

**原因**：数据分类步骤失败

**解决方案**：
```bash
# 使用规则模式作为备选
python -m fct_analysis.cli -i data.json --mode rule -o output/

# 检查数据完整性
python -c "
import json
data = json.load(open('data.json'))
print(f'Total cases: {len(data)}')
print(f'Cases with title: {len([c for c in data if c.get(\"title\")])}')
"
```

### 性能优化

#### 大数据集处理

```bash
# 1. 使用规则模式
python -m fct_analysis.cli -i large_data.json --mode rule -o output/

# 2. 分批处理
python -c "
import json
data = json.load(open('large_data.json'))
batch_size = 1000
for i in range(0, len(data), batch_size):
    batch = data[i:i+batch_size]
    with open(f'batch_{i}.json', 'w') as f:
        json.dump(batch, f)
"

# 3. 并行处理批处理文件
```

#### 内存优化

```python
# 处理大文件的内存优化版本
import json
from fct_analysis import parser

def stream_process_large_file(input_file, output_file):
    """流式处理大文件以节省内存"""
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    # 分批处理
    batch_size = 500
    results = []
    
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        batch_df = parser.parse_cases_data(batch)
        results.append(batch_df)
    
    # 合并结果
    final_df = pd.concat(results, ignore_index=True)
    final_df.to_csv(output_file, index=False)
```

---

## 最佳实践

### 数据准备

1. **数据清洗**
   - 移除重复记录
   - 标准化日期格式
   - 填充缺失值（如可能）

2. **质量检查**
   ```bash
   # 检查数据完整性
   python -c "
   import json
   data = json.load(open('your_data.json'))
   required_fields = ['case_number', 'filing_date', 'docket_entries']
   
   for i, case in enumerate(data):
       for field in required_fields:
           if field not in case:
               print(f'Case {i}: Missing field {field}')
   "
   ```

### 分析策略

1. **分层分析**
   - 第一层：规则模式快速概览
   - 第二层：LLM模式深度分析
   - 第三层：定制化专项分析

2. **定期监控**
   ```bash
   # 设置定期分析任务
   #!/bin/bash
   # weekly_analysis.sh
   
   DATE=$(date +%Y%m%d)
   python -m fct_analysis.cli \
       -i "data/cases_${DATE}.json" \
       --mode rule \
       -o "weekly_reports/${DATE}"
   
   # 生成趋势报告
   python generate_trend_report.py "weekly_reports"
   ```

### 结果验证

1. **抽样检查**
   ```python
   # 随机抽样验证分析结果
   import pandas as pd
   import random
   
   df = pd.read_csv('federal_cases_0005_details.csv')
   sample = df.sample(n=10, random_state=42)
   
   for _, row in sample.iterrows():
       print(f"Case {row['case_number']}: {row['type']} - {row['status']}")
   ```

2. **交叉验证**
   - 与人工分类结果对比
   - 使用不同模式的交叉验证
   - 时间趋势合理性检查

### 安全考虑

1. **数据隐私**
   - 不要在公共云上运行 LLM 分析
   - 本地 Ollama 确保数据不出网
   - 定期清理日志和临时文件

2. **访问控制**
   ```bash
   # 设置适当的文件权限
   chmod 700 results/
   chmod 600 results/*.csv
   ```

---

## 常见问题

### Q1: 规则模式和 LLM模式有什么区别？

**A**: 
- **规则模式**：速度快（<10秒/5000条），基于关键词匹配，适合日常快速分析
- **LLM模式**：精度高，能理解上下文，提取更准确的签证处和法官信息，但速度较慢

### Q2: 为什么有些案件被分类为 "Other"？

**A**: "Other" 是司法审查案件的统称。只有包含 "Mandamus"、"compel"、"delay" 等关键词的案件才会被分类为强制令。

### Q3: Rule 9 是什么意思？

**A**: Rule 9 是加拿大联邦法院的程序规则，涉及案件记录的移交。Rule 9 等待期衡量从立案到移民局移交档案的时间，是评估移民局响应速度的重要指标。

### Q4: 如何处理缺失的立案日期？

**A**: 程序会：
1. 标记缺失日期为 null
2. 在统计时排除相关案件
3. 在报告中说明缺失情况

### Q5: 可以分析其他类型的法律案件吗？

**A**: 目前程序专门针对移民案件设计。分析其他类型案件需要：
1. 修改分类规则
2. 调整时间计算逻辑
3. 更新可视化组件

### Q6: 如何自定义分析规则？

**A**: 可以修改 `src/fct_analysis/rules.py` 文件：
```python
# 添加新的案件类型
def classify_case_custom(case_data):
    if "appeal" in str(case_data.get("title", "")).lower():
        return {"type": "Appeal", "status": determine_status(case_data)}
    # ... 其他逻辑
```

### Q7: 程序支持多少数据量？

**A**: 
- **规则模式**：推荐 < 50,000 条记录
- **LLM模式**：推荐 < 10,000 条记录（考虑处理时间）
- **更大数据量**：建议分批处理

### Q8: 如何获取技术支持？

**A**: 
1. 查看项目文档和代码注释
2. 运行测试套件验证安装：`python -m pytest tests/`
3. 检查日志文件：`logs/` 目录
4. 提交 Issue 到项目仓库

---

## 附录

### A. 命令行参数参考

```
usage: fct_analysis [-h] --input INPUT [--mode {rule,llm}] [--output-dir OUTPUT_DIR] [--resume] [--sample-audit SAMPLE_AUDIT] [--ollama-url OLLAMA_URL]

参数说明:
  -h, --help              显示帮助信息
  --input, -i INPUT       输入数据文件路径（必需）
  --mode {rule,llm}       分析模式，默认 rule
  --output-dir, -o OUTPUT_DIR 输出目录，默认 output/
  --resume                断点续传模式（仅LLM模式）
  --sample-audit N        记录前N个LLM分析样本
  --ollama-url URL        自定义Ollama服务地址
```

### B. 配置文件示例

创建 `config.toml` 文件：

```toml
[analysis]
default_mode = "rule"
output_format = ["csv", "json"]
enable_plots = true

[ollama]
url = "http://localhost:11434"
model = "qwen2.5-7b-instruct"
timeout = 60
max_retries = 3

[logging]
level = "INFO"
file = "logs/fct_analysis.log"
```

### C. 性能基准

| 数据量 | 规则模式 | LLM模式 | 内存使用 | 输出文件大小 |
|--------|----------|---------|----------|--------------|
| 1,000 | 2秒 | 45秒 | 200MB | 500KB |
| 5,000 | 8秒 | 3分钟 | 800MB | 2.5MB |
| 10,000 | 15秒 | 6分钟 | 1.5GB | 5MB |

---

*本文档最后更新：2024年12月*