# NDJSON系统移除实施计划

## 概述

本文档提供了逐步实施NDJSON系统移除和数据库跟踪系统集成的详细计划。

## 实施阶段

### 阶段1：数据库架构准备 ✅

**目标**: 创建跟踪系统所需的数据库表

**任务**:
- [x] 创建 `scripts/migrate_tracking_schema.py`
- [x] 定义4个核心跟踪表：
  - `case_processing_history` - 案例处理历史
  - `processing_runs` - 运行会话记录  
  - `case_status_snapshots` - 案例状态快照
- [x] 添加必要的索引优化查询性能

**执行命令**:
```bash
python scripts/migrate_tracking_schema.py
```

### 阶段2：NDJSON系统清理工具 ✅

**目标**: 创建安全的NDJSON系统移除工具

**任务**:
- [x] 创建 `scripts/remove_ndjson_system.py`
- [x] 支持干运行模式 (`--dry-run`)
- [x] 支持备份选项 (`--backup`)
- [x] 自动移除导入和使用引用

**执行命令**:
```bash
# 预览将要删除的内容
python scripts/remove_ndjson_system.py --dry-run

# 执行移除（带备份）
python scripts/remove_ndjson_system.py --confirm --backup

# 执行移除（无备份）
python scripts/remove_ndjson_system.py --confirm --no-backup
```

### 阶段3：跟踪集成模块 ✅

**目标**: 创建跟踪系统与现有代码的集成层

**任务**:
- [x] 创建 `src/cli/tracking_integration.py`
- [x] 实现 `TrackingIntegration` 辅助类
- [x] 提供 `create_tracking_integrated_check_exists()` 函数
- [x] 提供 `create_tracking_integrated_scrape_case()` 函数

### 阶段4：更新main.py集成跟踪 ✅

**目标**: 将跟踪系统集成到主要的CLI操作中

**任务**:
- [x] 移除 `RunLogger` 导入，添加跟踪相关导入
- [x] 在 `FederalCourtScraperCLI.__init__()` 中初始化跟踪器
- [x] 更新 `scrape_single_case()` 方法：
  - 启动运行跟踪
  - 记录成功/失败结果
  - 记录案例未找到情况
- [x] 更新 `scrape_batch_cases()` 方法：
  - 启动批量运行跟踪
  - 集成跟踪到探测函数
  - 集成跟踪到采集函数
  - 结束运行跟踪
- [x] 验证purge命令已集成跟踪数据清理
 
**状态说明**: 已完成将 `TrackingIntegration` 集成到 `main.py`，批处理逻辑使用 `TrackingIntegration` 写入探测/采集事件以替代原来的 NDJSON `RunLogger`。

### 阶段5：测试和验证

**目标**: 全面测试新系统功能

#### 5.1 数据库验证
```bash
# 验证表创建
psql -d fct_autoquery -c "\dt"

# 验证索引
psql -d fct_autoquery -c "\di"
```

#### 5.2 单个案例处理测试
```bash
# 测试单个案例处理
python -m src.cli.main single IMM-1-23

# 检查跟踪记录
psql -d fct_autoquery -c "SELECT * FROM case_processing_history ORDER BY created_at DESC LIMIT 5;"
```

#### 5.3 批量处理测试
```bash
# 测试批量探测（小规模）
python -m src.cli.main probe 2025 --start 1 --max-cases 10

# 检查运行记录
psql -d fct_autoquery -c "SELECT * FROM processing_runs ORDER BY start_time DESC LIMIT 5;"
```

#### 5.4 Purge功能测试
```bash
# 测试年度清理（干运行）
python -m src.cli.main purge 2024 --dry-run

# 执行实际清理（测试年份）
python -m src.cli.main purge 2024 --yes

# 验证清理结果
psql -d fct_autoquery -c "SELECT COUNT(*) FROM case_processing_history WHERE case_number LIKE 'IMM-%-24';"
```

### 阶段6：执行NDJSON系统移除

**目标**: 完全移除NDJSON系统

**前提条件**:
- [ ] 所有测试通过
- [ ] 跟踪系统正常工作
- [ ] Purge功能验证正常

**执行步骤**:
```bash
# 1. 最终备份NDJSON文件
python scripts/remove_ndjson_system.py --confirm --backup

# 2. 验证移除完成
ls logs/run_*.ndjson  # 应该没有输出

# 3. 验证代码中无RunLogger引用
grep -r "RunLogger" src/  # 应该没有输出
grep -r "run_logger" src/  # 应该没有输出
```

### 阶段7：性能监控和优化

**目标**: 监控新系统性能并进行优化

#### 7.1 关键性能指标
```sql
-- 查询处理统计
SELECT 
    processing_mode,
    COUNT(*) as total_cases,
    COUNT(CASE WHEN outcome = 'success' THEN 1 END) as successes,
    COUNT(CASE WHEN outcome = 'failed' THEN 1 END) as failures,
    AVG(processing_duration_ms) as avg_duration_ms
FROM case_processing_history 
WHERE processed_at >= NOW() - INTERVAL '7 days'
GROUP BY processing_mode;

-- 查询运行统计
SELECT 
    processing_mode,
    COUNT(*) as total_runs,
    AVG(total_cases_processed) as avg_cases_per_run,
    MAX(total_cases_processed) as max_cases_per_run
FROM processing_runs 
WHERE start_time >= NOW() - INTERVAL '30 days'
GROUP BY processing_mode;
```

#### 7.2 定期维护任务
```bash
# 清理90天前的历史记录
python -c "
from src.services.case_tracking_service import CaseTrackingService
tracker = CaseTrackingService()
tracker.cleanup_old_records(days_to_keep=90)
"

# 备份跟踪数据
pg_dump -d fct_autoquery -t case_processing_history -t processing_runs -t case_status_snapshots > backup_tracking_$(date +%Y%m%d).sql
```

## 验证清单

### 数据库验证
- [ ] 4个跟踪表已创建
- [ ] 索引已创建
- [ ] 新的处理记录正确写入
- [ ] Purge功能正常工作

### 功能验证
- [ ] 单个案例处理正常
- [ ] 批量处理正常
- [ ] 智能跳过功能正常
- [ ] 统计查询正常

### 代码验证
- [ ] 所有RunLogger引用已移除
- [ ] NDJSON文件已删除
- [ ] 配置文件已更新
- [ ] 导入语句正确

### 新增测试 & 自动化
- [x] 新增 `tests/test_tracking_integration.py` 覆盖 `TrackingIntegration` 的行为
- [x] 更新 `tests/test_run_logger.py` 为跟踪集成测试（不再依赖 RunLogger）
- [x] 添加 `scripts/remove_ndjson_system.py` 与 `scripts/cleanup_legacy_ndjson.py` 实现的 `--dry-run` 检查

运行本地测试命令：
```bash
pytest -q tests/test_tracking_integration.py tests/test_run_logger.py
```


### 性能验证
- [ ] 处理速度无显著下降
- [ ] 数据库查询性能良好
- [ ] 内存使用正常

## 回滚计划

如果需要回滚到NDJSON系统：

### 1. 恢复NDJSON文件
```bash
# 从备份恢复
cp logs/backup/run_*.ndjson logs/
```

### 2. 恢复代码
```bash
# 恢复到移除前的提交
git checkout HEAD~1 -- src/lib/run_logger.py src/cli/main.py

# 或者手动恢复RunLogger相关代码
```

### 3. 清理跟踪表（可选）
```sql
DROP TABLE IF EXISTS case_processing_history;
DROP TABLE IF EXISTS processing_runs;
DROP TABLE IF EXISTS case_status_snapshots;
```

## 风险评估

### 高风险
- **数据库架构变更**: 可能影响现有功能
  - 缓解: 充分测试，保留回滚方案

### 中风险
- **性能影响**: 新的数据库写入可能影响处理速度
  - 缓解: 性能监控，异步写入优化

### 低风险
- **数据丢失**: NDJSON文件删除可能导致历史数据丢失
  - 缓解: 强制备份，可选数据迁移

## 完成标准

实施完成的标准：
1. ✅ 所有测试通过
2. ✅ NDJSON系统完全移除
3. ✅ 跟踪系统正常工作
4. ✅ 性能无显著下降
5. ✅ 文档更新完成
6. ✅ 回滚方案准备就绪

## 后续优化建议

1. **异步写入**: 考虑异步写入跟踪数据以提高性能
2. **缓存优化**: 为频繁查询的状态快照添加缓存
3. **监控仪表板**: 创建跟踪数据的可视化监控
4. **自动清理**: 实现基于时间的自动数据清理
5. **分区表**: 对大表进行分区以提高查询性能