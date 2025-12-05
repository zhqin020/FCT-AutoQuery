# 设计说明书 0006: Case Tracking Service 简化方案

## 概述

本文档描述了简化的案例处理跟踪系统设计方案。核心思想是：

1. **完全移除NDJSON系统** - 不进行数据迁移，直接删除
2. **仅记录新的处理结果** - 将新的案例处理记录到数据库跟踪表
3. **扩展Purge功能** - 支持按年份清除所有相关数据

## 核心变化

### 1. 移除NDJSON系统

#### 1.1 直接删除，不迁移
```bash
# 直接删除NDJSON文件和代码
python scripts/cleanup_legacy_ndjson.py --confirm --no-backup
```

#### 1.2 移除的组件
- ❌ `src/lib/run_logger.py` - 完全删除
- ❌ `logs/run_*.ndjson` - 直接删除
- ❌ 所有 `RunLogger` 相关代码引用
- ❌ NDJSON相关配置项

### 2. 简化的数据库架构

#### 2.1 保留核心跟踪表
```sql
-- 案例处理历史记录表（仅记录新数据）
CREATE TABLE case_processing_history (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL,
    case_number VARCHAR(50) NOT NULL,
    processing_mode VARCHAR(20) NOT NULL,
    outcome VARCHAR(20) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    case_id VARCHAR(50),
    details JSONB,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    processing_duration_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 运行会话表
CREATE TABLE processing_runs (
    run_id VARCHAR(50) PRIMARY KEY,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    processing_mode VARCHAR(20) NOT NULL,
    start_case_number INTEGER,
    max_cases INTEGER,
    force_mode BOOLEAN DEFAULT FALSE,
    config JSONB,
    total_cases_processed INTEGER DEFAULT 0,
    total_successes INTEGER DEFAULT 0,
    total_failures INTEGER DEFAULT 0,
    total_skipped INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 案例状态快照表（用于智能跳过）
CREATE TABLE case_status_snapshots (
    case_number VARCHAR(50) PRIMARY KEY,
    last_processed_at TIMESTAMP WITH TIME ZONE,
    last_outcome VARCHAR(20),
    last_run_id VARCHAR(50),
    consecutive_failures INTEGER DEFAULT 0,
    last_success_at TIMESTAMP WITH TIME ZONE,
    total_attempts INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 2.2 移除的表
- ❌ `probe_state` - 不再需要，使用现有探测机制

### 3. 扩展的Purge功能

#### 3.1 支持按年份清理所有数据

```python
def purge_year_with_tracking(year: int) -> Dict[str, int]:
    """
    清除指定年份的所有案例和跟踪数据
    
    Args:
        year: 要清除的年份 (e.g., 2023)
        
    Returns:
        Dict: 清理统计信息
    """
    stats = {
        'cases_deleted': 0,
        'history_deleted': 0,
        'snapshots_deleted': 0,
        'files_deleted': 0
    }
    
    # 1. 删除cases表中指定年份的记录
    delete_cases_sql = "DELETE FROM cases WHERE EXTRACT(YEAR FROM scraped_at) = %s"
    
    # 2. 删除case_processing_history表中相关记录
    delete_history_sql = """
        DELETE FROM case_processing_history 
        WHERE case_number LIKE %s
    """
    
    # 3. 删除case_status_snapshots表中相关记录
    delete_snapshots_sql = """
        DELETE FROM case_status_snapshots 
        WHERE case_number LIKE %s
    """
    
    # 4. 清理相关文件
    # 删除output目录下的相关文件
    # 删除attachment目录下的相关文件
    
    return stats
```

#### 3.2 CLI集成

```python
# 在main.py中扩展purge命令
def purge_year_extended(year: int):
    """扩展的年度清理功能"""
    logger.info(f"开始清理 {year} 年的所有数据...")
    
    # 原有的清理逻辑
    purge_year(year)
    
    # 新增的跟踪数据清理
    from src.services.case_tracking_service import CaseTrackingService
    tracker = CaseTrackingService()
    stats = tracker.purge_year(year)
    
    logger.info(f"清理完成: {stats}")
```

## 实施步骤

### 第一阶段：清理NDJSON

```bash
# 1. 创建数据库架构
python scripts/migrate_tracking_schema.py

# 2. 清理NDJSON系统
python scripts/cleanup_legacy_ndjson.py --confirm --no-backup
```

### 第二阶段：更新代码

#### 2.1 修改main.py
```python
# 移除这些导入
# from src.lib.run_logger import RunLogger

# 修改初始化
class FederalCourtScraperCLI:
    def __init__(self):
        # ... 现有代码 ...
        self.tracker = CaseTrackingService()  # 新增
        # 移除: self.run_logger = RunLogger()

# 修改处理方法
def scrape_single_case(self, case_number: str) -> Optional[Case]:
    # ... 现有处理逻辑 ...
    
    # 记录结果到数据库（替代NDJSON）
    if case:
        self.tracker.record_case_processing(
            court_file_no=case_number,
            run_id=self.current_run_id,
            processing_mode="single",
            outcome="success",
            case_id=case.case_id
        )
    else:
        self.tracker.record_case_processing(
            court_file_no=case_number,
            run_id=self.current_run_id,
            processing_mode="single",
            outcome="failed",
            error_message="Case not found or scraping failed"
        )
```

#### 2.2 修改批量处理
```python
# 在批量处理开始时
run_id = self.tracker.start_run(
    processing_mode="batch_probe",
    start_case_number=start,
    max_cases=max_cases
)

# 在处理每个案例时
self.tracker.record_case_processing(
    court_file_no=case_number,
    run_id=run_id,
    processing_mode="batch_probe",
    outcome=success ? "success" : "failed",
    case_id=case.case_id if case else None
)

# 在批量处理结束时
self.tracker.end_run(run_id, {
    "total_cases_processed": total_processed,
    "total_successes": successes,
    "total_failures": failures
})
```

### 第三阶段：扩展Purge功能

#### 3.1 更新purge命令
```python
# 在main.py中
def parse_args():
    parser.add_argument("command", choices=["single", "probe", "batch", "purge"])
    # ... 现有参数 ...
    
    if args.command == "purge":
        # 使用扩展的purge功能
        purge_year_extended(args.year)
        return

def purge_year_extended(year: int):
    """扩展的年度清理功能"""
    logger.info(f"开始清理 {year} 年的所有数据...")
    
    # 原有的清理逻辑
    purge_year(year)
    
    # 新增的跟踪数据清理
    stats = self.tracker.purge_year(year)
    
    logger.info(f"清理完成: 删除了 {stats['cases_deleted']} 个案例记录, "
               f"{stats['history_deleted']} 个历史记录, "
               f"{stats['snapshots_deleted']} 个状态快照")
```

## 智能跳过策略

### 1. 基于数据库的跳过逻辑

```python
def should_skip_case(self, case_number: str, force: bool = False) -> Tuple[bool, str]:
    """
    智能跳过决策
    
    Args:
        case_number: 案例编号
        force: 是否强制处理
        
    Returns:
        (should_skip, reason)
    """
    if force:
        return False, "force mode"
    
    # 1. 检查案例是否已存在
    if self.exporter.case_exists(case_number):
        return True, "case exists in database"
    
    # 2. 检查跟踪状态
    snapshot = self.get_case_snapshot(case_number)
    if snapshot:
        # 连续失败过多
        if snapshot['consecutive_failures'] >= 5:
            return True, f"too many consecutive failures ({snapshot['consecutive_failures']})"
        
        # 最近成功过，跳过一段时间
        if snapshot['last_success_at']:
            days_since_success = (datetime.now(timezone.utc) - snapshot['last_success_at']).days
            if days_since_success < 7:
                return True, f"recently succeeded ({days_since_success} days ago)"
        
        # 最近失败过，等待一段时间
        if snapshot['last_processed_at']:
            hours_since_processed = (datetime.now(timezone.utc) - snapshot['last_processed_at']).total_seconds() / 3600
            if hours_since_processed < 1:
                return True, f"recently processed ({hours_since_processed:.1f} hours ago)"
    
    return False, "proceed with processing"
```

### 2. 集成到现有逻辑

```python
# 在BatchService中集成
def find_upper_bound_with_tracking(
    check_case_exists: Callable[[int], bool],
    tracker: CaseTrackingService,
    # ... 其他参数
):
    """集成跟踪功能的边界查找"""
    
    def tracked_check_exists(number: int) -> bool:
        case_number = f"IMM-{number}-{year % 100:02d}"
        
        # 检查是否应该跳过
        should_skip, reason = tracker.should_skip_case(case_number, force)
        if should_skip:
            logger.info(f"Skipping {case_number}: {reason}")
            return False
        
        # 执行实际检查
        exists = check_case_exists(number)
        
        # 记录结果
        outcome = "success" if exists else "no_data"
        tracker.record_case_processing(
            court_file_no=case_number,
            run_id=run_id,
            processing_mode="batch_probe",
            outcome=outcome
        )
        
        return exists
    
    return BatchService.find_upper_bound(
        check_case_exists=tracked_check_exists,
        # ... 其他参数
    )
```

## 文件结构

```
src/
├── services/
│   ├── case_tracking_service.py      # 核心跟踪服务
│   └── export_service.py           # 现有服务，无需修改
├── cli/
│   ├── main.py                     # 更新：移除RunLogger，集成跟踪
│   └── tracking_integration.py       # 集成辅助类
├── lib/
│   └── run_logger.py              # 删除
scripts/
├── migrate_tracking_schema.py       # 数据库架构
├── cleanup_legacy_ndjson.py        # 清理NDJSON
└── verify_tracking.py              # 验证跟踪功能
```

## 使用示例

### 1. 单个案例处理
```python
# 开始处理
run_id = tracker.start_run("single_case")

# 处理案例
case = scraper.scrape_case_data("IMM-12345-25")

# 记录结果
tracker.record_case_processing(
    court_file_no="IMM-12345-25",
    run_id=run_id,
    processing_mode="single",
    outcome="success" if case else "failed",
    case_id=case.case_id if case else None
)

# 结束运行
tracker.end_run(run_id, {"total_cases": 1, "successes": 1 if case else 0})
```

### 2. 批量处理
```python
# 开始批量处理
run_id = tracker.start_run("batch_probe", start_case_number=12000, max_cases=1000)

# 集成跟踪的批量处理
upper_bound, probes = find_upper_bound_with_tracking(
    check_case_exists=original_check_func,
    tracker=tracker,
    run_id=run_id,
    start=12000
)

# 结束运行
tracker.end_run(run_id, {
    "total_cases_processed": probes,
    "upper_bound": upper_bound
})
```

### 3. 清理数据
```bash
# 清理2023年的所有数据
python main.py purge 2023

# 输出示例:
# 清理完成: 删除了 1500 个案例记录, 3000 个历史记录, 1500 个状态快照
```

## 总结

这个简化方案的优势：

1. **彻底简化** - 完全移除NDJSON，无需复杂迁移
2. **功能完整** - 保留智能跳过和历史查询功能
3. **易于实施** - 修改量最小，风险可控
4. **向后兼容** - 现有功能保持不变
5. **清理便利** - 扩展的purge功能支持按年份清理

该方案在最小化改动的同时，为系统提供了现代化的案例跟踪能力。