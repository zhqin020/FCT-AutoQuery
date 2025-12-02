-- Case Processing Tracking Schema
-- 用于跟踪case编号的处理历史和状态

-- 1. Case处理历史表
CREATE TABLE IF NOT EXISTS case_processing_history (
    id SERIAL PRIMARY KEY,
    court_file_no VARCHAR(50) NOT NULL,
    run_id VARCHAR(50) NOT NULL,
    outcome VARCHAR(20) NOT NULL CHECK (outcome IN ('success', 'failed', 'skipped', 'error', 'no-results')),
    reason TEXT,
    message TEXT,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_seconds FLOAT,
    attempt_count INTEGER DEFAULT 1,
    scrape_mode VARCHAR(20) DEFAULT 'single' CHECK (scrape_mode IN ('single', 'batch_probe', 'batch_linear')),
    -- 元数据
    user_agent TEXT,
    session_id VARCHAR(50),
    -- 索引
    UNIQUE(court_file_no, run_id),
    INDEX idx_court_file_no (court_file_no),
    INDEX idx_run_id (run_id),
    INDEX idx_outcome (outcome),
    INDEX idx_started_at (started_at)
);

-- 2. 运行会话表
CREATE TABLE IF NOT EXISTS processing_runs (
    run_id VARCHAR(50) PRIMARY KEY,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    mode VARCHAR(20) NOT NULL CHECK (mode IN ('single', 'batch', 'probe')),
    parameters JSONB,
    total_cases INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed', 'cancelled')),
    metadata JSONB
);

-- 3. Case状态快照表 (替代visited字典)
CREATE TABLE IF NOT EXISTS case_status_snapshot (
    court_file_no VARCHAR(50) PRIMARY KEY,
    last_outcome VARCHAR(20),
    last_run_id VARCHAR(50),
    last_processed_at TIMESTAMP WITH TIME ZONE,
    consecutive_failures INTEGER DEFAULT 0,
    first_seen_at TIMESTAMP WITH TIME ZONE,
    last_success_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB,
    FOREIGN KEY (last_run_id) REFERENCES processing_runs(run_id),
    INDEX idx_last_outcome (last_outcome),
    INDEX idx_last_processed_at (last_processed_at)
);

-- 4. 探测状态表 (替代probe_state文件)
CREATE TABLE IF NOT EXISTS probe_state (
    case_number INTEGER NOT NULL,
    year_part INTEGER NOT NULL,
    exists BOOLEAN NOT NULL,
    first_checked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    run_id VARCHAR(50),
    PRIMARY KEY (case_number, year_part),
    INDEX idx_exists (exists),
    INDEX idx_last_checked (last_checked_at),
    FOREIGN KEY (run_id) REFERENCES processing_runs(run_id)
);

-- 5. 视图：Case处理统计
CREATE OR REPLACE VIEW case_processing_stats AS
SELECT 
    c.court_file_no,
    h.outcome as last_outcome,
    h.started_at as last_processed_at,
    COUNT(h.id) as total_attempts,
    COUNT(CASE WHEN h.outcome = 'success' THEN 1 END) as success_count,
    COUNT(CASE WHEN h.outcome = 'failed' THEN 1 END) as failed_count,
    COUNT(CASE WHEN h.outcome = 'skipped' THEN 1 END) as skipped_count,
    MAX(h.started_at) as last_attempt_at,
    MIN(h.started_at) as first_attempt_at
FROM cases c
LEFT JOIN case_processing_history h ON c.court_file_no = h.court_file_no
GROUP BY c.court_file_no, h.outcome, h.started_at;