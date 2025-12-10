# FCT 数据分析程序快速参考

## 快速开始

```bash
# 1. 基础分析
python -m fct_analysis.cli -i cases.json --mode rule -o results/

# 2. 精准分析（需要 Ollama）
python -m fct_analysis.cli -i cases.json --mode llm -o results/

# 3. 生成图表
python -c "from fct_analysis import plots; plots.make_charts('results/federal_cases_0005_details.csv', 'results/charts')"
```

## 数据格式

### 最低要求
```json
[
  {
    "case_number": "IMM-1-23",
    "filing_date": "2024-01-15", 
    "docket_entries": [
      {"entry_date": "2024-01-15", "summary": "Complaint filed"}
    ]
  }
]
```

### 完整格式
```json
[
  {
    "case_number": "IMM-1-23",
    "filing_date": "2024-01-15",
    "title": "Mandamus action",
    "office": "Toronto",
    "docket_entries": [
      {"entry_date": "2024-01-15", "summary": "Complaint filed"},
      {"entry_date": "2024-03-20", "summary": "Rule 9 notice"}
    ]
  }
]
```

## 输出文件

```
results/
├── federal_cases_0005_details.csv     # 详细分析结果
├── federal_cases_0005_summary.json    # 统计摘要
└── plots/                             # 图表（可选）
    ├── volume_trend.png               # 案件量趋势
    ├── duration_boxplot.png            # 处理周期分布
    ├── outcome_donut.png              # 结果分布
    └── visa_office_heatmap.png        # 签证处效率
```

## 案件分类逻辑

### 类型分类
- **Mandamus**: 含 "Mandamus", "compel", "delay"
- **Other**: 其他所有案件

### 状态判断（优先级）
1. **Discontinued**: "Notice of Discontinuance"
2. **Granted**: "Granted", "Allowed"  
3. **Dismissed**: "Dismissed", "Leave Dismissed"
4. **Ongoing**: 无终局状态

## 时间指标

| 指标 | 计算 | 用途 |
|------|------|------|
| 结案时长 | 结案日期 - 立案日期 | 评估处理效率 |
| 当前案龄 | 当前日期 - 立案日期 | 监控积压 |
| Rule 9 等待期 | Rule 9 日期 - 立案日期 | 移民局响应速度 |

## 常用命令

### 基础分析
```bash
# 规则模式（快速）
python -m fct_analysis.cli -i data.json --mode rule -o output/

# LLM 模式（精准）
python -m fct_analysis.cli -i data.json --mode llm -o output/
```

### 高级选项
```bash
# 断点续传
python -m fct_analysis.cli -i data.json --mode llm --resume -o output/

# 自定义 Ollama 地址
python -m fct_analysis.cli -i data.json --mode llm --ollama-url http://192.168.1.100:11434 -o output/

# 审计采样
python -m fct_analysis.cli -i data.json --mode llm --sample-audit 10 -o output/
```

### 可视化
```bash
# 生成所有图表
python -c "from fct_analysis import plots; plots.make_charts('output/federal_cases_0005_details.csv', 'output/charts')"

# 生成特定图表
python -c "from fct_analysis import plots; df = pd.read_csv('output/federal_cases_0005_details.csv'); plots.volume_trend(df, 'output/volume.png')"
```

## 故障排除

### 常见错误

**ModuleNotFoundError**
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"
python -m fct_analysis.cli -i data.json
```

**Ollama 连接失败**
```bash
# 启动 Ollama
ollama serve

# 检查服务
curl http://localhost:11434/api/version
```

**JSON 格式错误**
```bash
# 验证 JSON
python -m json.tool data.json > /dev/null
```

### 性能优化

```bash
# 大数据集用规则模式
python -m fct_analysis.cli -i large_data.json --mode rule -o output/

# 分批处理
split -l 1000 large_data.json batch_
for batch in batch_*; do
  python -m fct_analysis.cli -i $batch --mode rule -o "output_$(basename $batch)"
done
```

## 性能参考

| 数据量 | 规则模式 | LLM模式 | 内存需求 |
|--------|----------|---------|----------|
| 1,000  | 2秒      | 45秒    | 200MB    |
| 5,000  | 8秒      | 3分钟   | 800MB    |
| 10,000 | 15秒     | 6分钟   | 1.5GB    |

## 最佳实践

1. **先运行规则模式**了解数据概况
2. **重要数据使用 LLM 模式**获得精准结果  
3. **定期生成图表**监控趋势
4. **使用断点续传**处理大数据集
5. **抽样验证**确保分析准确性

---

*快速参考版本 - 详见完整用户指南*