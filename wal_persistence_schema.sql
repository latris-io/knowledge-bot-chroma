-- WAL (Write-Ahead Log) Persistence Schema
-- This table stores pending writes during primary ChromaDB failures
-- Ensures data durability across load balancer restarts

CREATE TABLE IF NOT EXISTS wal_pending_writes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    write_id VARCHAR(100) UNIQUE NOT NULL,  -- Unique identifier for each write
    method VARCHAR(10) NOT NULL,            -- HTTP method (POST, PUT, DELETE, etc.)
    path TEXT NOT NULL,                     -- API endpoint path
    data JSONB,                             -- Request body data
    headers JSONB,                          -- Request headers
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),  -- When write was queued
    retry_count INTEGER DEFAULT 0,          -- Number of replay attempts
    status VARCHAR(20) DEFAULT 'pending',   -- Status: pending, replaying, completed, failed
    error_message TEXT,                     -- Last error if any
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_wal_status ON wal_pending_writes(status);
CREATE INDEX IF NOT EXISTS idx_wal_timestamp ON wal_pending_writes(timestamp);
CREATE INDEX IF NOT EXISTS idx_wal_write_id ON wal_pending_writes(write_id);

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_wal_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
DROP TRIGGER IF EXISTS trigger_wal_updated_at ON wal_pending_writes;
CREATE TRIGGER trigger_wal_updated_at
    BEFORE UPDATE ON wal_pending_writes
    FOR EACH ROW
    EXECUTE FUNCTION update_wal_updated_at();

-- View for monitoring WAL status
CREATE OR REPLACE VIEW wal_status_summary AS
SELECT 
    status,
    COUNT(*) as count,
    MIN(timestamp) as oldest_write,
    MAX(timestamp) as newest_write,
    AVG(retry_count) as avg_retries
FROM wal_pending_writes 
GROUP BY status;

-- Cleanup function for old completed/failed writes (optional)
CREATE OR REPLACE FUNCTION cleanup_old_wal_entries(days_old INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM wal_pending_writes 
    WHERE status IN ('completed', 'failed') 
    AND updated_at < NOW() - INTERVAL '1 day' * days_old;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql; 