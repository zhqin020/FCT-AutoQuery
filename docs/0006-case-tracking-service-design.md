# 设计说明书 0006: Case Tracking Service 数据库化重构

## 概述

本文档描述了将案例编号处理跟踪从分散的NDJSON文件迁移到结构化数据库管理系统的完整设计方案。该重构解决了当前系统中处理历史分散、查询困难、重复处理判断不完整等问题。

## 问题背景

### 当前系统问题

1. **NDJSON文件分散**
   - 每次运行产生独立的 `run_YYYYMMDD_HHMMSS.ndjson` 文件
   - 查询某个case number的历史处理情况需要遍历多个文件
   - 缺少统一的历史记录视图

2. **缺少历史查询功能**
   - 系统主要依赖 `case_exists()` 检查数据库中的案例存在性
   - 无法查询几天前的处理状态、失败原因、重试次数等信息
   - 缺少智能的跳过/重试决策机制

3. **处理状态管理不完整**
   - 只有简单的存在性检查，没有记录处理历史
   - 无法区分"已存在但处理失败"和"已存在且处理成功"
   - 缺少连续失败次数、最近处理时间等关键信息

### 业务需求

- **统一数据管理**：将所有处理历史集中在数据库中
- **智能决策**：基于历史数据做出跳过/重试决策
- **丰富查询**：支持复杂的历史查询和统计分析
- **性能优化**：避免重复探测和处理
- **向后兼容**：保持与现有NDJSON系统的兼容性

## 系统设计

### 1. 数据库架构设计

#### 1.1 核心表结构

```sql
-- 案例处理历史记录表
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

-- 案例状态快照表
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

-- 探测状态表
CREATE TABLE probe_state (
    case_number VARCHAR(50) PRIMARY KEY,
    exists BOOLEAN NOT NULL,
    last_probed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    run_id VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### 1.2 索引设计

```sql
-- 性能优化索引
CREATE INDEX idx_case_processing_history_case_number ON case_processing_history(case_number);
CREATE INDEX idx_case_processing_history_run_id ON case_processing_history(run_id);
CREATE INDEX idx_case_processing_history_processed_at ON case_processing_history(processed_at);
CREATE INDEX idx_case_processing_history_outcome ON case_processing_history(outcome);

CREATE INDEX idx_case_status_snapshots_last_processed_at ON case_status_snapshots(last_processed_at);
CREATE INDEX idx_case_status_snapshots_last_outcome ON case_status_snapshots(last_outcome);
CREATE INDEX idx_case_status_snapshots_consecutive_failures ON case_status_snapshots(consecutive_failures);

CREATE INDEX idx_probe_state_last_probed_at ON probe_state(last_probed_at);
CREATE INDEX idx_probe_state_exists ON probe_state(exists);
```

### 2. 服务层设计

#### 2.1 CaseTrackingService 核心类

```python
class CaseTrackingService:
    """案例处理跟踪服务"""
    
    def __init__(self, db_config: Optional[Dict[str, Any]] = None):
        """初始化跟踪服务"""
        
    def start_run(self, processing_mode: str, **kwargs) -> str:
        """开始新的处理运行"""
        
    def end_run(self, run_id: str, summary: Dict[str, Any]) -> None:
        """结束处理运行"""
        
    def record_case_processing(self, case_number: str, outcome: str, **kwargs) -> None:
        """记录案例处理结果"""
        
    def should_skip_case(self, case_number: str, force: bool = False) -> Tuple[bool, str]:
        """判断是否应该跳过案例处理"""
        
    def get_case_history(self, case_number: str, limit: int = 10) -> List[Dict]:
        """获取案例处理历史"""
        
    def get_run_summary(self, run_id: str) -> Optional[Dict]:
        """获取运行摘要"""
```

#### 2.2 TrackingIntegration 集成辅助类

```python
class TrackingIntegration:
    """跟踪系统集成辅助类"""
    
    def __init__(self, tracker: CaseTrackingService, exporter: ExportService, run_id: str):
        """初始化集成辅助类"""
        
    def check_case_exists(self, case_num: int, year: int) -> bool:
        """集成跟踪功能的案例存在性检查"""
        
    def record_outcome(self, case_number: str, outcome: str, **kwargs) -> None:
        """记录处理结果"""
        
    @staticmethod
    def create_integrated_check_exists(cli_instance, run_id: str) -> Callable:
        """创建集成跟踪功能的检查函数"""
```

### 3. 智能跳过策略

#### 3.1 跳过决策逻辑

```python
def should_skip_case(self, case_number: str, force: bool = False) -> Tuple[bool, str]:
    """
    智能跳过决策逻辑
    
    跳过条件：
    1. 强制模式：不跳过任何案例
    2. 数据库存在：跳过已存在的案例
    3. 连续失败：超过阈值的连续失败跳过
    4. 最近成功：短时间内已成功处理跳过
    5. 探测状态：已知不存在的案例跳过
    """
```

#### 3.2 跳过规则配置

```python
# 可配置的跳过规则
SKIP_RULES = {
    'max_consecutive_failures': 5,      # 最大连续失败次数
    'success_skip_hours': 24,           # 成功后跳过时间（小时）
    'failure_skip_hours': 1,             # 失败后跳过时间（小时）
    'probe_expire_days': 7,              # 探测状态过期天数
}
```

### 4. 一次性数据迁移设计

#### 4.1 NDJSON到数据库迁移（一次性）

```python
def migrate_ndjson_to_db(
    ndjson_dir: str = "logs/",
    dry_run: bool = False,
    cleanup_after_migration: bool = True
) -> None:
    """
    一次性将现有NDJSON文件迁移到数据库
    
    迁移步骤：
    1. 扫描logs目录下的所有run_*.ndjson文件
    2. 解析每行JSON记录（run_start, run_end, case）
    3. 根据记录类型插入对应数据库表
    4. 处理数据冲突和重复
    5. 生成迁移报告
    6. 可选：备份并删除原始NDJSON文件
    """
```

#### 4.4 简化迁移工具

```python
# 使用简化的迁移工具
python scripts/migrate_ndjson_simple.py --dry-run  # 预览
python scripts/migrate_ndjson_simple.py --cleanup    # 迁移并清理
```

#### 4.2 数据库架构迁移

```python
def migrate_tracking_schema() -> None:
    """
    创建跟踪系统数据库架构
    
    步骤：
    1. 检查现有数据库连接
    2. 创建4个核心表
    3. 创建性能优化索引
    4. 设置表约束和触发器
    5. 验证架构完整性
    """
```

#### 4.3 清理遗留NDJSON

```python
def cleanup_legacy_ndjson(
    backup_dir: str = "logs/backup/",
    confirm: bool = False
) -> None:
    """
    清理遗留的NDJSON文件
    
    步骤：
    1. 备份现有NDJSON文件到指定目录
    2. 删除logs目录下的run_*.ndjson文件
    3. 移除RunLogger相关代码引用
    4. 更新配置文件
    """
```

## 实现方案

### 1. 文件结构

```
src/
├── services/
│   └── case_tracking_service.py      # 核心跟踪服务
├── cli/
│   └── tracking_integration.py       # 集成辅助类
scripts/
├── migrate_tracking_schema.py         # 数据库架构迁移
├── migrate_ndjson_simple.py          # 简化的NDJSON数据迁移
├── migrate_ndjson_to_db.py           # 原有NDJSON数据迁移（可选）
└── cleanup_legacy_ndjson.py          # 清理遗留NDJSON文件
docs/
├── case_tracking_schema.sql           # 数据库架构定义
├── case_tracking_guide.md            # 使用指南
└── batch_tracking_integration.py     # 集成示例
# 移除：src/lib/run_logger.py
```

### 2. 集成步骤

#### 2.1 第一阶段：基础架构

1. **创建数据库架构**
   ```bash
   python scripts/migrate_tracking_schema.py
   ```

2. **实现核心服务**
   - `CaseTrackingService` 类
   - 基础CRUD操作
   - 数据库连接管理

3. **集成到现有CLI**
   - 修改 `main.py` 添加跟踪服务初始化
   - 创建 `TrackingIntegration` 辅助类
   - 更新批量处理逻辑

#### 2.2 第二阶段：一次性数据迁移和NDJSON移除

1. **迁移现有NDJSON数据（一次性）**
   ```bash
   # 先进行干运行测试
   python scripts/migrate_ndjson_simple.py --dry-run
   
   # 执行实际迁移并清理NDJSON
   python scripts/migrate_ndjson_simple.py --cleanup
   
   # 或者分步执行
   python scripts/migrate_ndjson_simple.py
   python scripts/cleanup_legacy_ndjson.py --backup
   ```

2. **验证数据完整性**
   - 对比NDJSON和数据库记录数
   - 验证关键字段一致性
   - 检查数据完整性约束

3. **完全移除NDJSON依赖**
   - 删除 `src/lib/run_logger.py` 文件
   - 移除所有 `RunLogger` 相关代码引用
   - 清理相关配置项
   - 更新导入语句

#### 2.3 第三阶段：功能完善

1. **增强查询功能**
   - 添加复杂查询接口
   - 实现统计分析功能
   - 提供数据导出功能

2. **优化性能**
   - 添加数据库索引
   - 实现查询缓存
   - 优化批量操作

### 3. 使用示例

#### 3.1 基本使用（无NDJSON）

```python
from src.services.case_tracking_service import CaseTrackingService
from src.cli.tracking_integration import TrackingIntegration

# 初始化跟踪服务（唯一数据源）
tracker = CaseTrackingService()
run_id = tracker.start_run("batch_probe", start_case_number=12000, max_cases=1000)

# 创建集成辅助类
tracking = TrackingIntegration(tracker, exporter, run_id)

# 使用集成的检查函数
check_exists = TrackingIntegration.create_integrated_check_exists(cli, run_id)
exists = check_exists(12345, 2025)

# 记录处理结果（直接写入数据库）
tracking.record_outcome("IMM-12345-25", "success", case_id="case_123")

# 无需NDJSON文件操作
```

#### 3.2 查询历史记录

```python
# 查询案例处理历史
history = tracker.get_case_history("IMM-12345-25", limit=5)
for record in history:
    print(f"{record['processed_at']}: {record['outcome']} - {record.get('error_message', '')}")

# 查询运行摘要
summary = tracker.get_run_summary(run_id)
print(f"处理了 {summary['total_cases_processed']} 个案例")
```

#### 3.3 智能跳过决策

```python
# 判断是否应该跳过
should_skip, reason = tracker.should_skip_case("IMM-12345-25", force=False)
if should_skip:
    print(f"跳过案例: {reason}")
else:
    # 执行处理
    pass
```

## 配置说明

### 1. 数据库配置

```toml
[database]
host = "localhost"
port = 5432
name = "fct_autoquery"
user = "postgres"
password = "password"

[tracking]
enabled = true
max_consecutive_failures = 5
success_skip_hours = 24
failure_skip_hours = 1
probe_expire_days = 7
```

### 2. 日志配置

```toml
[logging]
level = "INFO"
file = "logs/tracking.log"
```

## 性能考虑

### 1. 数据库优化

- **索引策略**：为常用查询字段创建索引
- **分区表**：按时间分区存储历史记录
- **连接池**：使用数据库连接池管理连接
- **批量操作**：批量插入和更新减少数据库调用

### 2. 内存优化

- **缓存策略**：缓存频繁查询的案例状态
- **批量处理**：批量处理减少内存占用
- **懒加载**：按需加载历史数据

### 3. 查询优化

- **分页查询**：大数据集分页处理
- **条件索引**：为特定查询条件创建索引
- **查询缓存**：缓存常用查询结果

## 监控和维护

### 1. 数据质量监控

```sql
-- 检查数据完整性
SELECT 
    COUNT(*) as total_records,
    COUNT(DISTINCT case_number) as unique_cases,
    COUNT(DISTINCT run_id) as total_runs
FROM case_processing_history;

-- 检查异常记录
SELECT case_number, COUNT(*) as attempts
FROM case_processing_history 
WHERE outcome = 'failed'
GROUP BY case_number 
HAVING COUNT(*) > 10
ORDER BY attempts DESC;
```

### 2. 性能监控

```python
# 监控关键指标
metrics = {
    'total_cases_processed': tracker.get_total_cases_processed(),
    'success_rate': tracker.get_success_rate(),
    'average_processing_time': tracker.get_average_processing_time(),
    'skip_rate': tracker.get_skip_rate(),
}
```

### 3. 维护任务

```bash
# 定期清理过期数据
python scripts/cleanup_old_data.py --days 365

# 重建索引
python scripts/rebuild_indexes.py

# 数据备份
python scripts/backup_tracking_data.py
```

## 完全替换NDJSON方案

### 1. 移除NDJSON依赖

- **完全移除** `RunLogger` 类和相关NDJSON文件生成
- **移除** `logs/run_*.ndjson` 文件创建逻辑
- **移除** NDJSON相关的配置和参数

### 2. 数据库为中心

- **唯一数据源**：所有case跟踪数据仅存储在数据库中
- **实时记录**：每个case处理结果立即写入数据库
- **查询接口**：所有历史查询通过数据库接口实现

### 3. 系统简化

```python
# 旧方案：NDJSON + 数据库
run_logger = RunLogger()  # 生成NDJSON
tracker = CaseTrackingService()  # 数据库跟踪

# 新方案：仅数据库
tracker = CaseTrackingService()  # 统一的跟踪服务
```

### 4. 配置清理

```toml
# 移除NDJSON相关配置
# [logging]
# enable_run_logger = true  # 移除此配置

# 新增纯数据库配置
[tracking]
enabled = true
database_url = "postgresql://user:pass@localhost/fct_autoquery"
max_consecutive_failures = 5
success_skip_hours = 24
failure_skip_hours = 1
```

## 测试策略

### 1. 单元测试

```python
def test_case_tracking_service():
    tracker = CaseTrackingService()
    run_id = tracker.start_run("test")
    
    # 测试记录处理结果
    tracker.record_case_processing("IMM-1-23", "success", run_id=run_id)
    
    # 测试查询历史
    history = tracker.get_case_history("IMM-1-23")
    assert len(history) == 1
    assert history[0]['outcome'] == 'success'
```

### 2. 集成测试

```python
def test_tracking_integration():
    # 测试与现有系统的集成
    cli = FederalCourtScraperCLI()
    tracking = TrackingIntegration(cli.tracker, cli.exporter, "test_run")
    
    # 测试集成检查函数
    check_exists = TrackingIntegration.create_integrated_check_exists(cli, "test_run")
    result = check_exists(12345, 2025)
    assert isinstance(result, bool)
```

### 3. 性能测试

```python
def test_performance():
    # 测试大量数据处理的性能
    tracker = CaseTrackingService()
    start_time = time.time()
    
    for i in range(10000):
        tracker.record_case_processing(f"IMM-{i}-25", "success")
    
    duration = time.time() - start_time
    assert duration < 10.0  # 应在10秒内完成
```

## 部署指南

### 1. 环境准备

```bash
# 安装依赖
pip install psycopg2-binary

# 配置数据库
createdb fct_autoquery
```

### 2. 数据库初始化

```bash
# 创建架构
python scripts/migrate_tracking_schema.py

# 迁移现有数据
python scripts/migrate_ndjson_to_db.py
```

### 3. 配置更新

```toml
# 更新配置文件
[tracking]
enabled = true
database_url = "postgresql://user:pass@localhost/fct_autoquery"
```

### 4. 验证部署

```bash
# 运行测试
python -m pytest tests/test_case_tracking_service.py

# 验证数据
python scripts/verify_deployment.py
```

## 总结

本设计说明书详细描述了将案例处理跟踪从NDJSON文件完全迁移到数据库的方案。主要改进包括：

1. **完全替换NDJSON**：移除所有NDJSON相关代码和文件，以数据库为唯一数据源
2. **统一数据管理**：所有处理历史集中在结构化数据库中
3. **智能决策机制**：基于历史数据的智能跳过/重试策略
4. **丰富的查询功能**：支持复杂的历史查询和统计分析
5. **性能优化**：通过索引、缓存和批量操作提升性能
6. **系统简化**：移除双重数据源，简化架构和维护

### 关键变化

- ❌ **移除** `src/lib/run_logger.py`
- ❌ **移除** `logs/run_*.ndjson` 文件生成
- ✅ **新增** `CaseTrackingService` 作为唯一跟踪服务
- ✅ **新增** 4个核心数据库表管理所有跟踪数据
- ✅ **新增** 一次性数据迁移工具

该设计完全解决了当前系统的痛点，通过完全移除NDJSON依赖，为案例处理提供了更加可靠、高效和可维护的跟踪机制。