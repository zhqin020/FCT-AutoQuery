# NDJSON系统移除实施指南

## 概述

本指南提供了完全移除NDJSON系统并实施简化的数据库跟踪系统的详细步骤。

## 实施步骤

### 第一步：创建数据库架构

```bash
# 创建跟踪系统数据库表
python scripts/migrate_tracking_schema.py

# 验证架构创建
psql -d fct_autoquery -c "\dt"
```

### 第二步：移除NDJSON系统

```bash
# 预览将要删除的内容
python scripts/remove_ndjson_system.py --dry-run

# 执行移除（备份为默认行为）
python scripts/remove_ndjson_system.py --confirm

# 或者不备份直接删除（显式跳过备份）
python scripts/remove_ndjson_system.py --confirm --no-backup
```

### 第三步：更新代码集成

#### 3.1 修改main.py导入

移除这些导入（删除 RunLogger 相关引用）：
```python
# 删除这些 RunLogger 相关导入
# from src.lib.run_logger import RunLogger
```

添加这些导入：
```python
# 确保这些导入存在
from src.services.case_tracking_service import CaseTrackingService
from src.cli.tracking_integration import TrackingIntegration, create_tracking_integrated_check_exists
```

#### 3.2 修改CLI初始化

在 `FederalCourtScraperCLI.__init__()` 中：
```python
# 删除
# self.run_logger = RunLogger()

# 添加
self.tracker = CaseTrackingService()
self.current_run_id = None
```

#### 3.3 修改单个案例处理

在 `scrape_single_case()` 方法中：
```python
def scrape_single_case(self, case_number: str) -> Optional[Case]:
    # 开始运行跟踪
    if not hasattr(self, 'current_run_id') or self.current_run_id is None:
        self.current_run_id = self.tracker.start_run("single_case")
    
    # ... 现有的处理逻辑 ...
    
    # 记录结果到数据库（替代NDJSON）
    if case:
        self.tracker.record_case_processing(
            court_file_no=case_number,
            run_id=self.current_run_id,
            processing_mode="single",
            outcome="success",
            case_id=case.case_id
        )
        logger.info(f"Successfully scraped and recorded case: {case.case_id}")
    else:
        self.tracker.record_case_processing(
            court_file_no=case_number,
            run_id=self.current_run_id,
            processing_mode="single",
            outcome="failed",
            error_message="Case not found or scraping failed"
        )
        logger.warning(f"Failed to scrape case: {case_number}")
    
    return case
```

#### 3.4 修改批量处理

在批量处理方法中：
```python
def run_batch_probe(self, year: int, start: int = 1, max_cases: int = 100000):
    # 开始批量运行跟踪
    run_id = self.tracker.start_run(
        processing_mode="batch_probe",
        start_case_number=start,
        max_cases=max_cases
    )
    
    # 创建集成跟踪的检查函数
    check_exists = create_tracking_integrated_check_exists(self, run_id)
    
    # 执行批量处理
    try:
        upper_bound, probes = BatchService.find_upper_bound(
            check_case_exists=check_exists,
            start=start,
            max_limit=999999,
            collect=False,
            max_cases=max_cases,
            rate_limiter=self.rate_limiter
        )
        
        # 结束运行跟踪
        self.tracker.end_run(run_id, {
            "total_cases_processed": probes,
            "upper_bound": upper_bound,
            "processing_mode": "batch_probe"
        })
        
        logger.info(f"Batch probe completed: upper_bound={upper_bound}, probes={probes}")
        
    except Exception as e:
        # 记录运行失败
        self.tracker.end_run(run_id, {
            "error": str(e),
            "processing_mode": "batch_probe"
        })
        raise
```

### 第四步：测试系统

#### 4.1 测试单个案例
```bash
# 测试单个案例处理
python -m src.cli.main single IMM-1-23

# 检查数据库记录
psql -d fct_autoquery -c "SELECT * FROM case_processing_history ORDER BY created_at DESC LIMIT 5;"
```

#### 4.2 测试批量处理
```bash
# 测试批量探测（小规模）
python -m src.cli.main probe 2025 --start 1 --max-cases 10

# 检查运行记录
psql -d fct_autoquery -c "SELECT * FROM processing_runs ORDER BY start_time DESC LIMIT 5;"
```

#### 4.3 测试Purge功能
```bash
# 测试年度清理（干运行）
python -m src.cli.main purge 2024 --dry-run

# 执行实际清理
python -m src.cli.main purge 2024 --yes

# 验证清理结果
psql -d fct_autoquery -c "SELECT COUNT(*) FROM case_processing_history WHERE case_number LIKE 'IMM-%-24';"
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

## 故障排除

### 常见问题

1. **数据库连接失败**
   ```bash
   # 检查数据库配置
   python -c "from src.lib.config import Config; print(Config.get_db_config())"
   
   # 测试连接
   python scripts/test_db_connection.py
   ```

2. **导入错误**
   ```bash
   # 检查Python路径
   python -c "import sys; print(sys.path)"
   
   # 测试导入
   python -c "from src.services.case_tracking_service import CaseTrackingService"
   ```

3. **跟踪数据未写入**
   ```bash
   # 检查日志
   tail -f logs/scraper.log | grep -i tracking
   
   # 检查数据库权限
   psql -d fct_autoquery -c "\dp"
   ```

### 回滚计划

如果需要回滚：

1. **恢复NDJSON文件**
   ```bash
   # 从备份恢复
   cp logs/backup/run_*.ndjson logs/
   
   # 恢复代码
   git checkout HEAD~1 -- src/lib/run_logger.py src/cli/main.py
   ```

2. **删除跟踪表**
   ```sql
   DROP TABLE IF EXISTS case_processing_history;
   DROP TABLE IF EXISTS processing_runs;
   DROP TABLE IF EXISTS case_status_snapshots;
   ```

## 性能监控

### 关键指标
```python
# 查询处理统计
SELECT 
    processing_mode,
    COUNT(*) as total_cases,
    COUNT(CASE WHEN outcome = 'success' THEN 1 END) as successes,
    COUNT(CASE WHEN outcome = 'failed' THEN 1 END) as failures,
    AVG(processing_duration_ms) as avg_duration_ms
FROM case_processing_history 
WHERE processed_at >= NOW() - INTERVAL '7 days'
GROUP BY processing_mode;

# 查询运行统计
SELECT 
    processing_mode,
    COUNT(*) as total_runs,
    AVG(total_cases_processed) as avg_cases_per_run,
    MAX(total_cases_processed) as max_cases_per_run
FROM processing_runs 
WHERE start_time >= NOW() - INTERVAL '30 days'
GROUP BY processing_mode;
```

## 维护任务

### 定期清理
```bash
# 清理90天前的历史记录
python -c "
from src.services.case_tracking_service import CaseTrackingService
tracker = CaseTrackingService()
tracker.cleanup_old_records(days_to_keep=90)
"
```

### 数据备份
```bash
# 备份跟踪数据
pg_dump -d fct_autoquery -t case_processing_history -t processing_runs -t case_status_snapshots > backup_tracking_$(date +%Y%m%d).sql
```

## 总结

完成这些步骤后，系统将：

- ✅ **完全移除NDJSON系统**
- ✅ **使用数据库统一管理跟踪数据**
- ✅ **支持智能跳过和历史查询**
- ✅ **提供扩展的Purge功能**
- ✅ **保持现有功能兼容性**

这个简化方案在最小化改动的同时，为系统提供了现代化的案例跟踪能力。