# Skip Record Optimization

## 问题描述

在大批量案例采集过程中，跳过的案例记录会占用大量内存：
- 每个跳过的案例都会保存为一个字典对象
- 长时间运行后，内存占用会显著增长
- 最终输出中包含大量跳过记录，难以查阅

## 优化方案

### 1. **内存限制**
- 只在内存中保留最近 N 条跳过记录（默认100条）
- 超出限制的记录自动清理
- 通过配置选项 `max_skipped_log` 控制

### 2. **定期统计报告**
- 每跳过 M 个案例报告一次统计信息（默认100个）
- 显示跳过总数，帮助了解进度
- 通过配置选项 `skip_report_interval` 控制

### 3. **优化的输出格式**
- 最终输出中包含跳过统计摘要而非完整列表
- 保留最近的跳过记录用于调试
- 显示跳过总数和内存占用情况

## 配置选项

### config.toml
```toml
[app]
# 内存中保留的最大跳过记录数
max_skipped_log = 100

# 跳过统计报告间隔（每N个跳过案例报告一次）
skip_report_interval = 100
```

### 环境变量
```bash
export FCT_MAX_SKIPPED_LOG=100
export FCT_SKIP_REPORT_INTERVAL=100
```

## 实际效果

### 优化前
```
跳过案例数: 2500
跳过案例详情: [
    {'case_number': 'IMM-1-21', 'status': 'skipped', 'reason': 'exists_in_db'},
    {'case_number': 'IMM-2-21', 'status': 'skipped', 'reason': 'exists_in_db'},
    # ... 2498 more records
]
```

### 优化后
```
Skip statistics: 100 total cases skipped so far
Skip statistics: 200 total cases skipped so far
Skip statistics: 300 total cases skipped so far
...
跳过案例总数: 2500
内存中保留的跳过记录数: 100 (显示最近 100 条)
最近跳过的案例: [显示最后10条]
```

## 内存优化

### 优化效果
- **内存占用减少**: 从 O(n) 降低到 O(1)
- **长期运行稳定**: 不会因跳过记录积累导致内存溢出
- **性能提升**: 减少内存分配和垃圾回收压力

### 配置建议
- **大批量任务** (1000+ 案例): 使用默认值或减小 `max_skipped_log`
- **小批量任务** (<100 案例): 可以增加 `max_skipped_log` 保留更多记录
- **调试场景**: 设置 `skip_report_interval` 为较小值以获得更频繁的进度更新

## 实现细节

### 核心逻辑
1. **记录截断**: `skipped = skipped[-max_skipped_log:]`
2. **计数器分离**: 使用 `skipped_counter` 追踪总数
3. **定期报告**: 每 `skip_report_interval` 次跳过输出统计
4. **优化输出**: 返回包含摘要而非完整列表的字典

### 数据结构
```python
skipped_info = {
    "total_skipped": 2500,          # 总跳过数
    "recent_skipped": [...],          # 最近100条记录
    "max_stored": 100                # 最大存储限制
}
```

这些优化确保程序在大批量采集时保持稳定的内存使用，同时提供有意义的进度报告。