-- Emergency Transaction Safety Schema
-- Prevents data loss during timing gaps by logging ALL operations before execution

CREATE TABLE IF NOT EXISTS emergency_transaction_log (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_session VARCHAR(100),
    client_ip VARCHAR(45),
    method VARCHAR(10) NOT NULL,
    path TEXT NOT NULL,
    data JSONB,
    headers JSONB,
    status VARCHAR(20) DEFAULT 'ATTEMPTING' NOT NULL,
    failure_reason TEXT,
    response_status INTEGER,
    response_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    attempted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TIMESTAMP WITH TIME ZONE,
    is_timing_gap_failure BOOLEAN DEFAULT FALSE,
    target_instance VARCHAR(20),
    operation_type VARCHAR(50), -- 'file_upload', 'file_delete', 'collection_create', etc.
    user_identifier VARCHAR(100)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_emergency_tx_status ON emergency_transaction_log(status);
CREATE INDEX IF NOT EXISTS idx_emergency_tx_created ON emergency_transaction_log(created_at);
CREATE INDEX IF NOT EXISTS idx_emergency_tx_retry ON emergency_transaction_log(next_retry_at) WHERE status = 'FAILED';
CREATE INDEX IF NOT EXISTS idx_emergency_tx_session ON emergency_transaction_log(client_session);
CREATE INDEX IF NOT EXISTS idx_emergency_tx_timing_gap ON emergency_transaction_log(is_timing_gap_failure) WHERE is_timing_gap_failure = TRUE;

-- Transaction status tracking
-- ATTEMPTING: Operation logged, about to be executed
-- COMPLETED: Operation executed successfully  
-- FAILED: Operation failed, may be retried
-- RECOVERED: Operation auto-recovered after infrastructure failure
-- ABANDONED: Operation failed after max retries

-- Function to automatically set retry timing
CREATE OR REPLACE FUNCTION set_retry_timing()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'FAILED' AND NEW.retry_count < NEW.max_retries THEN
        -- Exponential backoff: 60s, 120s, 240s
        NEW.next_retry_at = NOW() + INTERVAL '60 seconds' * POWER(2, NEW.retry_count);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for automatic retry scheduling
DROP TRIGGER IF EXISTS trigger_retry_timing ON emergency_transaction_log;
CREATE TRIGGER trigger_retry_timing
    BEFORE UPDATE ON emergency_transaction_log
    FOR EACH ROW
    EXECUTE FUNCTION set_retry_timing();

-- View for monitoring transaction safety
CREATE OR REPLACE VIEW transaction_safety_summary AS
SELECT 
    status,
    COUNT(*) as count,
    COUNT(*) FILTER (WHERE is_timing_gap_failure = TRUE) as timing_gap_failures,
    MIN(created_at) as oldest_transaction,
    MAX(created_at) as newest_transaction,
    AVG(retry_count) as avg_retries,
    AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) as avg_completion_time_seconds
FROM emergency_transaction_log 
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY status
ORDER BY 
    CASE status 
        WHEN 'FAILED' THEN 1 
        WHEN 'ATTEMPTING' THEN 2 
        WHEN 'RECOVERED' THEN 3 
        WHEN 'COMPLETED' THEN 4 
        WHEN 'ABANDONED' THEN 5 
    END;

-- View for recovery monitoring
CREATE OR REPLACE VIEW pending_recovery_transactions AS
SELECT 
    transaction_id,
    method,
    path,
    operation_type,
    client_session,
    retry_count,
    max_retries,
    next_retry_at,
    failure_reason,
    created_at,
    EXTRACT(EPOCH FROM (NOW() - created_at)) as age_seconds
FROM emergency_transaction_log 
WHERE status = 'FAILED' 
    AND retry_count < max_retries 
    AND (next_retry_at IS NULL OR next_retry_at <= NOW())
ORDER BY created_at ASC; 