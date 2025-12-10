# FCT 数据分析程序使用示例

## 目录
1. [基础示例](#基础示例)
2. [实际案例分析](#实际案例分析)
3. [高级用法示例](#高级用法示例)
4. [批量处理示例](#批量处理示例)
5. [可视化示例](#可视化示例)

---

## 基础示例

### 示例 1：最简单的用法

**目标**：快速分析一小批案件数据

**步骤**：
```bash
# 1. 创建测试数据文件
cat > test_cases.json << 'EOF'
[
  {
    "case_number": "IMM-1-24",
    "filing_date": "2024-01-15",
    "title": "Mandamus action to compel processing",
    "office": "Toronto",
    "docket_entries": [
      {"entry_date": "2024-01-15", "summary": "Complaint filed"},
      {"entry_date": "2024-03-20", "summary": "Rule 9 notice issued"},
      {"entry_date": "2024-06-10", "summary": "Order: dismiss application"}
    ]
  },
  {
    "case_number": "IMM-2-24", 
    "filing_date": "2024-02-10",
    "title": "Application for judicial review",
    "office": "Vancouver",
    "docket_entries": [
      {"entry_date": "2024-02-10", "summary": "Application filed"},
      {"entry_date": "2024-05-15", "summary": "Notice of Discontinuance filed"}
    ]
  }
]
EOF

# 2. 运行分析
python -m fct_analysis.cli -i test_cases.json --mode rule -o test_output

# 3. 查看结果
cat test_output/federal_cases_0005_summary.json
```

**预期输出**：
```json
{
  "total_cases": 2,
  "rows": 2
}
```

### 示例 2：查看详细结果

```bash
# 查看详细 CSV
head -5 test_output/federal_cases_0005_details.csv

# 使用更友好的方式查看
python -c "
import pandas as pd
df = pd.read_csv('test_output/federal_cases_0005_details.csv')
print(df[['case_number', 'type', 'status', 'duration_days']].to_string())
"
```

---

## 实际案例分析

### 示例 3：分析真实的移民案件数据

**背景**：律师事务所需要分析过去一年的案件表现

**数据准备**：
```bash
# 假设我们有以下格式的真实数据
cat > real_cases_2024.json << 'EOF'
[
  {
    "case_id": "IMM-123-23",
    "case_number": "IMM-123-23",
    "title": "Mandamus action to compel processing of permanent residence application",
    "court": "Toronto",
    "date": "2023-03-12",
    "filing_date": "2023-03-12",
    "office": "Toronto", 
    "style_of_cause": "Mandamus action to compel processing of permanent residence application",
    "docket_entries": [
      {"entry_date": "2023-03-12", "summary": "Complaint filed"},
      {"entry_date": "2023-07-02", "summary": "Rule 9 notice issued: referred to IRCC Beijing office"},
      {"entry_date": "2023-09-15", "summary": "Order: application approved by IRCC"},
      {"entry_date": "2023-09-20", "summary": "Notice of Discontinuance filed"}
    ],
    "scraped_at": "2023-09-25T12:00:00"
  },
  {
    "case_id": "IMM-456-23",
    "case_number": "IMM-456-23", 
    "title": "Judicial review of visa refusal",
    "court": "Vancouver",
    "date": "2023-05-20",
    "filing_date": "2023-05-20",
    "office": "Vancouver",
    "style_of_cause": "Judicial review of visa refusal from Ankara office",
    "docket_entries": [
      {"entry_date": "2023-05-20", "summary": "Application for judicial review filed"},
      {"entry_date": "2023-08-10", "summary": "Hearing conducted"},
      {"entry_date": "2023-10-05", "summary": "Judgment: application dismissed"}
    ]
  },
  {
    "case_id": "IMM-789-23",
    "case_number": "IMM-789-23",
    "title": "Application to compel work permit processing",
    "court": "Montreal", 
    "date": "2023-07-08",
    "filing_date": "2023-07-08",
    "office": "Montreal",
    "style_of_cause": "Application to compel work permit processing - delay 18 months",
    "docket_entries": [
      {"entry_date": "2023-07-08", "summary": "Application for mandamus filed"},
      {"entry_date": "2023-09-15", "summary": "Rule 9 notice: referred to IRCC New Delhi"},
      {"entry_date": "2023-11-20", "summary": "Order: grant mandamus, IRCC to decide within 60 days"},
      {"entry_date": "2024-01-15", "summary": "IRCC decision: approve work permit"}
    ]
  }
]
EOF
```

**运行分析**：
```bash
# 规则模式分析
python -m fct_analysis.cli -i real_cases_2024.json --mode rule -o analysis_results

# 查看结果概览
python -c "
import pandas as pd
import json

# 读取详细结果
df = pd.read_csv('analysis_results/federal_cases_0005_details.csv')

print('=== 案件类型分布 ===')
print(df['type'].value_counts())
print()

print('=== 案件状态分布 ===') 
print(df['status'].value_counts())
print()

print('=== 处理时长统计 ===')
duration_stats = df['time_to_close'].describe()
print(duration_stats)
print()

print('=== Mandamus 案件隐性成功率 ===')
mandamus_df = df[df['type'] == 'Mandamus']
if len(mandamus_df) > 0:
    success_rate = (mandamus_df['status'] == 'Discontinued').mean()
    print(f'成功率: {success_rate:.1%} ({mandamus_df[mandamus_df[\"status\"] == \"Discontinued\"].shape[0]}/{mandamus_df.shape[0]})')
"
```

**生成可视化图表**：
```bash
python -c "from fct_analysis import plots; plots.make_charts('analysis_results/federal_cases_0005_details.csv', 'analysis_results/charts')"

# 查看生成的图表
ls -la analysis_results/charts/
```

### 示例 4：使用 LLM 模式获取更精准分析

```bash
# 确保 Ollama 运行
ollama serve &

# 运行 LLM 分析
python -m fct_analysis.cli -i real_cases_2024.json --mode llm -o llm_results --sample-audit 5

# 查看 LLM 提取的实体信息
python -c "
import pandas as pd
import json

df = pd.read_csv('llm_results/federal_cases_0005_details.csv')

# 查看 meta 列中的实体提取结果
for idx, row in df.iterrows():
    print(f'案件 {row[\"case_number\"]}:')
    print(f'  类型: {row[\"type\"]}')
    print(f'  状态: {row[\"status\"]}')
    
    # 解析 meta 字段
    try:
        meta = json.loads(row['meta']) if pd.notna(row['meta']) else {}
        if meta.get('visa_office'):
            print(f'  签证处: {meta[\"visa_office\"]}')
        if meta.get('judge'):
            print(f'  法官: {meta[\"judge\"]}')
    except:
        pass
    print()
"

# 查看审计样本
cat logs/0005_llm_audit_samples.ndjson | python -m json.tool | head -30
```

---

## 高级用法示例

### 示例 5：自定义分析脚本

**目标**：创建一个专门分析 Mandamus 案件胜诉率的脚本

```python
#!/usr/bin/env python3
# mandamus_analysis.py

import pandas as pd
import json
from pathlib import Path
from fct_analysis import parser, rules, metrics, plots

def analyze_mandamus_performance(input_file, output_dir):
    """专门分析 Mandamus 案件表现"""
    
    # 1. 解析和分类数据
    df = parser.parse_cases(input_file)
    
    # 2. 应用分类规则
    types = []
    statuses = []
    for _, row in df.iterrows():
        res = rules.classify_case_rule(row.get("raw") or row)
        types.append(res.get("type"))
        statuses.append(res.get("status"))
    
    df["type"] = types
    df["status"] = statuses
    
    # 3. 计算指标
    df = metrics.compute_durations(df)
    
    # 4. 筛选 Mandamus 案件
    mandamus_df = df[df["type"] == "Mandamus"].copy()
    
    # 5. 详细分析
    analysis_results = {
        "total_mandamus": len(mandamus_df),
        "discontinued_count": (mandamus_df["status"] == "Discontinued").sum(),
        "granted_count": (mandamus_df["status"] == "Granted").sum(),
        "dismissed_count": (mandamus_df["status"] == "Dismissed").sum(),
        "ongoing_count": (mandamus_df["status"] == "Ongoing").sum(),
    }
    
    # 计算隐性胜诉率（撤销视为成功）
    if len(mandamus_df) > 0:
        analysis_results["implicit_success_rate"] = analysis_results["discontinued_count"] / len(mandamus_df)
        analysis_results["explicit_success_rate"] = analysis_results["granted_count"] / len(mandamus_df)
        analysis_results["overall_success_rate"] = (analysis_results["discontinued_count"] + analysis_results["granted_count"]) / len(mandamus_df)
    
    # 处理时长统计（仅已结案）
    closed_cases = mandamus_df[mandamus_df["status"].isin(["Discontinued", "Granted", "Dismissed"])]
    if len(closed_cases) > 0:
        analysis_results["duration_stats"] = {
            "mean": closed_cases["time_to_close"].mean(),
            "median": closed_cases["time_to_close"].median(),
            "min": closed_cases["time_to_close"].min(),
            "max": closed_cases["time_to_close"].max(),
        }
    
    # Rule 9 统计
    rule9_cases = mandamus_df[mandamus_df["rule9_wait"].notna()]
    if len(rule9_cases) > 0:
        analysis_results["rule9_stats"] = {
            "count": len(rule9_cases),
            "mean_wait": rule9_cases["rule9_wait"].mean(),
            "median_wait": rule9_cases["rule9_wait"].median(),
        }
    
    # 6. 保存结果
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 保存详细数据
    mandamus_df.to_csv(output_path / "mandamus_details.csv", index=False)
    
    # 保存分析结果
    with open(output_path / "mandamus_analysis.json", "w") as f:
        json.dump(analysis_results, f, indent=2, default=str)
    
    # 7. 打印报告
    print("=== Mandamus 案件分析报告 ===")
    print(f"总案件数: {analysis_results['total_mandamus']}")
    print(f"隐性成功率（撤销）: {analysis_results.get('implicit_success_rate', 0):.1%}")
    print(f"显性成功率（胜诉）: {analysis_results.get('explicit_success_rate', 0):.1%}")
    print(f"总体成功率: {analysis_results.get('overall_success_rate', 0):.1%}")
    
    if "duration_stats" in analysis_results:
        stats = analysis_results["duration_stats"]
        print(f"平均处理时长: {stats['mean']:.1f} 天")
        print(f"中位数处理时长: {stats['median']:.1f} 天")
    
    if "rule9_stats" in analysis_results:
        stats = analysis_results["rule9_stats"]
        print(f"Rule 9 平均等待: {stats['mean_wait']:.1f} 天")
    
    print(f"\n详细结果已保存到: {output_path}")
    
    return analysis_results

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("用法: python mandamus_analysis.py <input_file> <output_dir>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_dir = sys.argv[2]
    
    analyze_mandamus_performance(input_file, output_dir)
```

**使用自定义脚本**：
```bash
# 使脚本可执行
chmod +x mandamus_analysis.py

# 运行分析
./mandamus_analysis.py real_cases_2024.json mandamus_analysis

# 查看结果
cat mandamus_analysis/mandamus_analysis.json
```

### 示例 6：趋势分析脚本

```python
#!/usr/bin/env python3
# trend_analysis.py

import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path

def analyze_trends(input_csv, output_dir):
    """分析案件趋势"""
    
    # 读取数据
    df = pd.read_csv(input_csv)
    
    # 确保日期格式正确
    df['filing_date_parsed'] = pd.to_datetime(df['filing_date'], errors='coerce')
    
    # 提取年月
    df['year_month'] = df['filing_date_parsed'].dt.to_period('M')
    
    # 按月统计
    monthly_stats = df.groupby(['year_month', 'type']).size().unstack(fill_value=0)
    monthly_total = df.groupby('year_month').size()
    
    # 创建图表
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # 图1: 月度案件量趋势
    monthly_total.plot(kind='bar', ax=ax1, color='steelblue', alpha=0.7)
    ax1.set_title('月度案件量趋势')
    ax1.set_ylabel('案件数量')
    ax1.set_xlabel('月份')
    ax1.tick_params(axis='x', rotation=45)
    
    # 图2: 案件类型分布
    monthly_stats.plot(kind='bar', ax=ax2, stacked=True)
    ax2.set_title('月度案件类型分布')
    ax2.set_ylabel('案件数量')
    ax2.set_xlabel('月份')
    ax2.legend(title='案件类型')
    ax2.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    
    # 保存图表
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_path / 'trend_analysis.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 生成趋势统计
    trend_stats = {
        "total_cases": len(df),
        "date_range": {
            "start": df['filing_date_parsed'].min().strftime('%Y-%m-%d'),
            "end": df['filing_date_parsed'].max().strftime('%Y-%m-%d')
        },
        "monthly_average": monthly_total.mean(),
        "peak_month": {
            "period": str(monthly_total.idxmax()),
            "count": monthly_total.max()
        },
        "case_type_distribution": df['type'].value_counts().to_dict()
    }
    
    # 保存统计结果
    import json
    with open(output_path / 'trend_stats.json', 'w') as f:
        json.dump(trend_stats, f, indent=2, default=str)
    
    print("趋势分析完成")
    print(f"总案件数: {trend_stats['total_cases']}")
    print(f"数据期间: {trend_stats['date_range']['start']} 至 {trend_stats['date_range']['end']}")
    print(f"月均案件: {trend_stats['monthly_average']:.1f}")
    print(f"峰值月份: {trend_stats['peak_month']['period']} ({trend_stats['peak_month']['count']} 件)")
    
    return trend_stats

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("用法: python trend_analysis.py <input_csv> <output_dir>")
        sys.exit(1)
    
    analyze_trends(sys.argv[1], sys.argv[2])
```

---

## 批量处理示例

### 示例 7：批量处理月度数据

**场景**：每月收到新数据，需要更新分析报告

```bash
#!/bin/bash
# monthly_batch_process.sh

# 设置数据目录
DATA_DIR="monthly_data"
OUTPUT_DIR="monthly_reports"
CURRENT_DATE=$(date +%Y-%m)

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 处理每个月的数据
for data_file in "$DATA_DIR"/*.json; do
    if [ -f "$data_file" ]; then
        filename=$(basename "$data_file" .json)
        report_dir="$OUTPUT_DIR/$filename"
        
        echo "处理文件: $filename"
        
        # 运行分析
        python -m fct_analysis.cli \
            -i "$data_file" \
            --mode rule \
            -o "$report_dir"
        
        # 生成图表
        python -c "from fct_analysis import plots; plots.make_charts('$report_dir/federal_cases_0005_details.csv', '$report_dir/charts')"
        
        echo "完成: $filename"
    fi
done

# 生成月度汇总报告
python -c "
import pandas as pd
import json
import os
from pathlib import Path

# 收集所有月度数据
all_data = []
summary_data = []

for report_dir in Path('$OUTPUT_DIR').iterdir():
    if report_dir.is_dir():
        summary_file = report_dir / 'federal_cases_0005_summary.json'
        details_file = report_dir / 'federal_cases_0005_details.csv'
        
        if summary_file.exists():
            with open(summary_file) as f:
                summary = json.load(f)
                summary['month'] = report_dir.name
                summary_data.append(summary)
        
        if details_file.exists():
            df = pd.read_csv(details_file)
            df['month'] = report_dir.name
            all_data.append(df)

# 合并数据
if all_data:
    combined_df = pd.concat(all_data, ignore_index=True)
    combined_df.to_csv('$OUTPUT_DIR/combined_all_months.csv', index=False)
    
    # 生成汇总图表
    from fct_analysis import plots
    plots.make_charts('$OUTPUT_DIR/combined_all_months.csv', '$OUTPUT_DIR/combined_charts')

if summary_data:
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv('$OUTPUT_DIR/monthly_summary.csv', index=False)

print('批量处理完成！')
print(f'总处理月份: {len(summary_data)}')
print(f'总案件数: {len(combined_df) if all_data else 0}')
"

echo "批量处理完成！查看结果: $OUTPUT_DIR"
```

### 示例 8：自动化监控脚本

```bash
#!/bin/bash
# daily_monitor.sh

# 监控新增数据并自动分析
WATCH_DIR="incoming_data"
PROCESSED_DIR="processed_data"
RESULTS_DIR="daily_results"
LOG_FILE="monitoring.log"

# 创建必要目录
mkdir -p "$WATCH_DIR" "$PROCESSED_DIR" "$RESULTS_DIR"

# 记录日志
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "开始监控..."

# 监控新文件
inotifywait -m -e create --format '%f' "$WATCH_DIR" | while read file; do
    if [[ "$file" == *.json ]]; then
        log "发现新文件: $file"
        
        input_file="$WATCH_DIR/$file"
        timestamp=$(date +%Y%m%d_%H%M%S)
        result_dir="$RESULTS_DIR/analysis_$timestamp"
        
        # 运行分析
        log "开始分析: $file"
        if python -m fct_analysis.cli -i "$input_file" --mode rule -o "$result_dir"; then
            log "分析完成: $file"
            
            # 移动已处理文件
            mv "$input_file" "$PROCESSED_DIR/"
            
            # 发送通知（可选）
            echo "案件数据分析完成 - $file" | mail -s "FCT Analysis Complete" your.email@example.com
            
        else
            log "分析失败: $file"
        fi
    fi
done
```

---

## 可视化示例

### 示例 9：自定义可视化

```python
#!/usr/bin/env python3
# custom_visualization.py

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

def create_custom_dashboard(input_csv, output_dir):
    """创建自定义仪表盘"""
    
    # 读取数据
    df = pd.read_csv(input_csv)
    
    # 设置样式
    plt.style.use('seaborn-v0_8')
    sns.set_palette("husl")
    
    # 创建 2x2 子图布局
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('FCT 案件分析仪表盘', fontsize=16, fontweight='bold')
    
    # 1. 案件状态饼图
    status_counts = df['status'].value_counts()
    ax1.pie(status_counts.values, labels=status_counts.index, autopct='%1.1f%%', startangle=90)
    ax1.set_title('案件状态分布')
    
    # 2. 处理时长分布直方图
    df['time_to_close'].hist(bins=20, ax=ax2, alpha=0.7)
    ax2.set_title('处理时长分布')
    ax2.set_xlabel('天数')
    ax2.set_ylabel('案件数量')
    
    # 3. 月度趋势线图
    df['filing_date_parsed'] = pd.to_datetime(df['filing_date'], errors='coerce')
    monthly_counts = df.groupby(df['filing_date_parsed'].dt.to_period('M')).size()
    monthly_counts.plot(kind='line', ax=ax3, marker='o')
    ax3.set_title('月度立案趋势')
    ax3.set_xlabel('月份')
    ax3.set_ylabel('案件数量')
    ax3.tick_params(axis='x', rotation=45)
    
    # 4. 案件类型 vs 状态热力图
    type_status_crosstab = pd.crosstab(df['type'], df['status'])
    sns.heatmap(type_status_crosstab, annot=True, fmt='d', cmap='YlOrRd', ax=ax4)
    ax4.set_title('案件类型 vs 状态分布')
    
    plt.tight_layout()
    
    # 保存仪表盘
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    plt.savefig(output_path / 'custom_dashboard.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"自定义仪表盘已保存到: {output_path / 'custom_dashboard.png'}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("用法: python custom_visualization.py <input_csv> <output_dir>")
        sys.exit(1)
    
    create_custom_dashboard(sys.argv[1], sys.argv[2])
```

### 示例 10：交互式报告生成

```python
#!/usr/bin/env python3
# interactive_report.py

import pandas as pd
import json
from pathlib import Path

def generate_interactive_report(input_csv, output_dir):
    """生成 HTML 交互式报告"""
    
    # 读取数据
    df = pd.read_csv(input_csv)
    
    # 基础统计
    stats = {
        'total_cases': len(df),
        'case_types': df['type'].value_counts().to_dict(),
        'case_statuses': df['status'].value_counts().to_dict(),
        'avg_duration': df['time_to_close'].mean() if 'time_to_close' in df.columns else 0,
    }
    
    # 生成 HTML 报告
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>FCT 案件分析报告</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
            .stat-card {{ background-color: #f9f9f9; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }}
            .table-container {{ margin: 20px 0; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>FCT 案件分析报告</h1>
            <p>生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <h2>总体概况</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <h3>总案件数</h3>
                <h2>{stats['total_cases']}</h2>
            </div>
            <div class="stat-card">
                <h3>平均处理时长</h3>
                <h2>{stats['avg_duration']:.1f} 天</h2>
            </div>
        </div>
        
        <h2>案件类型分布</h2>
        <div class="stats-grid">
    """
    
    for case_type, count in stats['case_types'].items():
        percentage = (count / stats['total_cases']) * 100
        html_content += f"""
            <div class="stat-card">
                <h3>{case_type}</h3>
                <h2>{count} ({percentage:.1f}%)</h2>
            </div>
        """
    
    html_content += """
        </div>
        
        <h2>案件状态分布</h2>
        <div class="stats-grid">
    """
    
    for status, count in stats['case_statuses'].items():
        percentage = (count / stats['total_cases']) * 100
        html_content += f"""
            <div class="stat-card">
                <h3>{status}</h3>
                <h2>{count} ({percentage:.1f}%)</h2>
            </div>
        """
    
    html_content += """
        </div>
        
        <h2>案件详情</h2>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>案件编号</th>
                        <th>立案日期</th>
                        <th>类型</th>
                        <th>状态</th>
                        <th>处理时长(天)</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    # 只显示前50条记录
    for _, row in df.head(50).iterrows():
        duration = f"{row.get('time_to_close', 0):.0f}" if pd.notna(row.get('time_to_close')) else "进行中"
        html_content += f"""
                    <tr>
                        <td>{row['case_number']}</td>
                        <td>{row['filing_date']}</td>
                        <td>{row['type']}</td>
                        <td>{row['status']}</td>
                        <td>{duration}</td>
                    </tr>
        """
    
    html_content += """
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    
    # 保存 HTML 报告
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    with open(output_path / 'interactive_report.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"交互式报告已保存到: {output_path / 'interactive_report.html'}")
    print(f"请在浏览器中打开: file://{output_path.absolute() / 'interactive_report.html'}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("用法: python interactive_report.py <input_csv> <output_dir>")
        sys.exit(1)
    
    generate_interactive_report(sys.argv[1], sys.argv[2])
```

---

## 运行示例

```bash
# 1. 运行基础示例
python -m fct_analysis.cli -i test_cases.json --mode rule -o example_output

# 2. 运行 Mandamus 专项分析
./mandamus_analysis.py real_cases_2024.json mandamus_results

# 3. 生成趋势分析
python trend_analysis.py example_output/federal_cases_0005_details.csv trend_results

# 4. 创建自定义可视化
python custom_visualization.py example_output/federal_cases_0005_details.csv custom_charts

# 5. 生成交互式报告
python interactive_report.py example_output/federal_cases_0005_details.csv html_report

# 6. 批量处理
chmod +x monthly_batch_process.sh
./monthly_batch_process.sh
```

这些示例展示了 FCT 数据分析程序的各种用法，从基础的案件分析到高级的自定义报告生成。根据您的具体需求选择合适的示例进行修改和使用。