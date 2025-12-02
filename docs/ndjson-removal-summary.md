# NDJSON完全移除总结

## 概述

本文档总结了完全移除NDJSON处理后的系统架构变化和操作指南。

## 架构变化

### 之前：双重数据源
```
┌─────────────────┐    ┌─────────────────┐
│   NDJSON Files  │    │    Database     │
│                 │    │                 │
│ run_*.ndjson    │    │ cases table     │
│ logs/           │    │                 │
└─────────────────┘    └─────────────────┘
        │                       │
        └──────────┬────────────┘
                   │
        ┌─────────────────┐
        │  Application    │
        │                 │
        │ RunLogger       │
        │ ExportService   │
        └─────────────────┘
```

### 现在：单一数据源
```
┌─────────────────────────────────────────────────┐
│                 Database                         │
│                                                 │
│  case_processing_history  │  processing_runs    │
│  case_status_snapshots   │  probe_state        │
│                                                 │
└─────────────────────────────────────────────────┘
                        │
        ┌─────────────────┐
        │  Application    │
│                 │
        │ CaseTracking    │
        │ Service         │
        └─────────────────┘
```

## 移除的组件

### 1. 文件删除
- ❌ `src/lib/run_logger.py`
- ❌ `logs/run_*.ndjson` （迁移后删除）
- ❌ NDJSON相关配置项

### 2. 代码移除
- ❌ `RunLogger` 类的所有引用
- ❌ `enable_run_logger` 配置参数
- ❌ NDJSON文件生成逻辑
- ❌ `run_logger.record_case()` 调用

### 3. 配置清理
```toml
# 移除这些配置项
[logging]
enable_run_logger = true  # 删除
run_logger_path = "logs"  # 删除
```

## 新增的组件

### 1. 核心服务
- ✅ `CaseTrackingService` - 统一的跟踪服务
- ✅ `TrackingIntegration` - 集成辅助类

### 2. 数据库表
- ✅ `case_processing_history` - 处理历史
- ✅ `processing_runs` - 运行会话
- ✅ `case_status_snapshots` - 状态快照
- ✅ `probe_state` - 探测状态

### 3. 迁移工具
- ✅ `migrate_tracking_schema.py` - 数据库架构
- ✅ `migrate_ndjson_simple.py` - 数据迁移
- ✅ `cleanup_legacy_ndjson.py` - 清理工具

## 操作步骤

### 第一阶段：准备
```bash
# 1. 创建数据库架构
python scripts/migrate_tracking_schema.py

# 2. 验证架构
psql -d fct_autoquery -c "\dt"
```

### 第二阶段：迁移（一次性）
```bash
# 1. 预览迁移
python scripts/migrate_ndjson_simple.py --dry-run

# 2. 执行迁移并清理NDJSON
python scripts/migrate_ndjson_simple.py --cleanup

# 3. 验证迁移结果
python scripts/verify_migration.py
```

### 第三阶段：代码更新
```bash
# 1. 清理遗留代码
python scripts/cleanup_legacy_ndjson.py --confirm

# 2. 更新导入语句
# 移除：from src.lib.run_logger import RunLogger
# 移除：run_logger = RunLogger()

# 3. 更新主逻辑
# 使用：tracker = CaseTrackingService()
# 使用：tracking = TrackingIntegration(tracker, exporter, run_id)
```

## 代码示例对比

### 之前的代码
```python
from src.lib.run_logger import RunLogger

# 初始化
run_logger = RunLogger()

# 记录处理
run_logger.record_case(
    case_number="IMM-123-25",
    outcome="success",
    case_id="case_123"
)

# 生成NDJSON文件
# 自动创建 logs/run_20251201_120000.ndjson
```

### 现在的代码
```python
from src.services.case_tracking_service import CaseTrackingService
from src.cli.tracking_integration import TrackingIntegration

# 初始化
tracker = CaseTrackingService()
run_id = tracker.start_run("single_case")

# 记录处理（直接写入数据库）
tracker.record_case_processing(
    court_file_no="IMM-123-25",
    run_id=run_id,
    processing_mode="single",
    outcome="success",
    case_id="case_123"
)

# 结束运行
tracker.end_run(run_id, {"total_cases": 1, "successes": 1})
```

## 查询对比

### 之前：查询NDJSON
```bash
# 查找特定案例的历史
grep "IMM-123-25" logs/run_*.ndjson

# 统计运行结果
cat logs/run_20251201_*.ndjson | jq -r '.outcome' | sort | uniq -c
```

### 现在：查询数据库
```python
from src.services.case_tracking_service import CaseTrackingService

tracker = CaseTrackingService()

# 查询案例历史
history = tracker.get_case_history("IMM-123-25")
for record in history:
    print(f"{record['processed_at']}: {record['outcome']}")

# 查询运行统计
summary = tracker.get_run_summary(run_id)
print(f"处理了 {summary['total_cases_processed']} 个案例")
```

## 性能优势

### 1. 存储效率
- **之前**：每个运行生成独立文件，存储分散
- **现在**：统一数据库存储，支持压缩和索引

### 2. 查询性能
- **之前**：需要遍历多个文件，O(n)复杂度
- **现在**：数据库索引查询，O(log n)复杂度

### 3. 并发安全
- **之前**：文件写入可能冲突
- **现在**：数据库事务保证一致性

### 4. 数据完整性
- **之前**：文件可能损坏或丢失
- **现在**：数据库备份和恢复机制

## 监控和维护

### 1. 数据质量检查
```sql
-- 检查数据完整性
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT case_number) as unique_cases,
    COUNT(DISTINCT run_id) as total_runs
FROM case_processing_history;
```

### 2. 性能监控
```python
# 监控关键指标
metrics = {
    'total_cases_processed': tracker.get_total_cases_processed(),
    'success_rate': tracker.get_success_rate(),
    'average_processing_time': tracker.get_average_processing_time(),
}
```

### 3. 定期维护
```bash
# 清理过期数据
python scripts/cleanup_old_data.py --days 365

# 重建索引
python scripts/rebuild_indexes.py

# 数据备份
python scripts/backup_tracking_data.py
```

## 故障排除

### 常见问题

1. **迁移失败**
   ```bash
   # 检查数据库连接
   python scripts/test_db_connection.py
   
   # 检查架构
   python scripts/verify_schema.py
   ```

2. **数据不一致**
   ```bash
   # 验证迁移结果
   python scripts/verify_migration.py --detailed
   
   # 修复不一致数据
   python scripts/fix_inconsistencies.py
   ```

3. **性能问题**
   ```bash
   # 分析查询性能
   python scripts/analyze_queries.py
   
   # 优化索引
   python scripts/optimize_indexes.py
   ```

## 回滚计划

如果需要回滚到NDJSON系统：

1. **备份数据库**
   ```bash
   pg_dump fct_autoquery > backup_rollback.sql
   ```

2. **恢复NDJSON文件**
   ```bash
   # 从备份恢复
   cp logs/backup/run_*.ndjson logs/
   ```

3. **恢复代码**
   ```bash
   git checkout HEAD~1 -- src/lib/run_logger.py
   git checkout HEAD~1 -- src/cli/main.py
   ```

## 总结

完全移除NDJSON后，系统获得了以下优势：

- ✅ **简化架构**：单一数据源，减少复杂性
- ✅ **提升性能**：数据库索引和查询优化
- ✅ **增强功能**：丰富的查询和统计分析
- ✅ **改善维护**：统一的数据管理和备份
- ✅ **提高可靠性**：事务保证和数据完整性

这个变化为案例处理跟踪提供了更加现代化、高效和可维护的解决方案。