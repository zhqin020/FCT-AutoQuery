# 专用分析表架构实施总结

## 概述

根据安全要求，我们实现了专门用于分析的数据表架构，避免直接修改原始cases表。新架构保护源数据完整性，同时提供灵活的分析环境。

## 数据库架构

### 原始表（只读）
- **cases**: 原始案件数据
- **docket_entries**: 案件记录子表

### 专用分析表
- **case_analysis**: 分析结果存储表

#### case_analysis表结构
```sql
CREATE TABLE case_analysis (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(50) NOT NULL,           -- 案件编号
    case_number VARCHAR(50),
    title TEXT,                             -- 案件标题
    court VARCHAR(100),                      -- 法院
    filing_date DATE,                        -- 立案日期
    
    -- 分析结果字段
    case_type VARCHAR(50),                   -- 案件类型 (Mandamus/Other)
    case_status VARCHAR(50),                 -- 案件状态 (Dismissed/Granted/Discontinued/Ongoing)
    visa_office VARCHAR(100),                -- 签证处 (LLM提取)
    judge VARCHAR(100),                      -- 法官 (LLM提取)
    
    -- 时间指标
    time_to_close INTEGER,                   -- 结案时长
    age_of_case INTEGER,                     -- 当前案龄
    rule9_wait INTEGER,                      -- Rule 9等待期
    outcome_date DATE,                       -- 结案日期
    
    -- 元数据
    analysis_mode VARCHAR(20) NOT NULL DEFAULT 'rule',  -- 分析模式
    analysis_version VARCHAR(20) DEFAULT '1.0',         -- 分析版本
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,        -- 分析时间
    analysis_data JSONB,                                       -- 附加数据(含docket_entries)
    original_case_id VARCHAR(50),                             -- 原始案件ID引用
    
    CONSTRAINT case_analysis_unique UNIQUE (case_id, analysis_mode),
    CONSTRAINT case_analysis_check CHECK (analysis_mode IN ('rule', 'llm', 'smart'))
);
```

## 核心特性

### 1. 数据安全隔离
- 原始数据表保持只读状态
- 所有分析和修改在专用表中进行
- 原始数据完整性得到保护

### 2. 复制机制
```sql
-- 从原始表复制到分析表
INSERT INTO case_analysis (
    case_id, case_number, title, court, filing_date, 
    original_case_id, analysis_data, analysis_mode
)
SELECT DISTINCT
    c.case_number, c.case_number, c.style_of_cause, c.office, c.filing_date,
    c.case_number, jsonb_build_object(
        'case_type', c.case_type,
        'type_of_action', c.type_of_action,
        'nature_of_proceeding', c.nature_of_proceeding,
        'docket_entries', (
            SELECT jsonb_agg(jsonb_build_object(
                'id', d.id_from_table,
                'case_id', d.case_number,
                'doc_id', d.id_from_table,
                'entry_date', d.date_filed,
                'entry_office', d.office,
                'summary', d.recorded_entry_summary
            ))
            FROM docket_entries d
            WHERE d.case_number = c.case_number
        )
    ), 'rule'
FROM cases c
INNER JOIN docket_entries d ON c.case_number = d.case_number
WHERE c.case_number NOT IN (SELECT DISTINCT case_id FROM case_analysis);
```

### 3. 智能更新策略
- **skip**: 跳过已分析案件
- **force**: 强制重新分析
- **smart**: 智能更新已有结果

### 4. 数据持久化
- 每次分析结果保存到分析表
- 支持断点续传
- 避免重复LLM调用

## 管理脚本

### 1. 数据库迁移 (`scripts/migrate_analysis_db.py`)
- 创建专用分析表
- 复制原始数据
- 建立索引

### 2. 数据复制 (`scripts/copy_cases_to_analysis.py`)
- 批量复制案件到分析表
- 支持dry-run模式
- 进度跟踪

### 3. 结果查看 (`scripts/view_analysis_results.py`)
- 查看分析统计
- 导出分析结果
- 多种格式支持

### 4. 测试脚本 (`scripts/test_analysis.py`)
- 小规模分析测试
- 功能验证

## 使用流程

### 初次设置
```bash
# 1. 迁移数据库架构
python scripts/migrate_analysis_db.py

# 2. 复制案件数据
python scripts/copy_cases_to_analysis.py

# 3. 验证复制结果
python scripts/view_analysis_results.py --summary-only
```

### 分析执行
```bash
# 规则模式分析
python -m fct_analysis.cli --mode rule --input-format database --skip-analyzed

# LLM模式分析
python -m fct_analysis.cli --mode llm --input-format database --skip-analyzed

# 从数据库读取已有分析结果
python -m fct_analysis.cli --from-db --input-format database
```

### 结果查看
```bash
# 查看统计摘要
python scripts/view_analysis_results.py --summary-only

# 查看最近案件
python scripts/view_analysis_results.py --limit 10

# 导出结果
python scripts/view_analysis_results.py --export results.csv --format csv
```

## 性能优化

### 索引策略
- case_id: 主键索引
- analysis_mode: 模式索引  
- case_type: 类型索引
- case_status: 状态索引
- visa_office: 签证处索引
- analyzed_at: 时间索引

### 批处理
- 支持1000条/批次的批量复制
- 进度跟踪和错误处理
- 内存友好的大数据处理

## 数据一致性

### 1. 唯一约束
- (case_id, analysis_mode) 组合唯一
- 防止重复分析记录

### 2. 引用完整性
- original_case_id 引用原始cases表
- 可选外键约束

### 3. 版本控制
- analysis_version 追踪分析算法版本
- 支持结果版本比较

## 扩展性

### 1. 多模式支持
- rule: 规则分析
- llm: LLM分析  
- smart: 混合分析

### 2. 灵活存储
- analysis_data JSONB字段存储任意结构
- 支持未来新字段添加

### 3. 并发安全
- UPSERT操作支持
- 事务完整性保证

## 总结

专用分析表架构成功实现了：
✅ 数据安全隔离
✅ 高效分析处理
✅ 结果持久化
✅ 灵活更新策略
✅ 完整管理工具集
✅ 良好扩展性

该架构为大规模FCT案件分析提供了安全、高效、可扩展的基础平台。