-- Optimized Sync State Schema for Free PostgreSQL Tier
-- Designed to be efficient and stay well under 1GB limit

-- Main collection sync state (one record per collection)
CREATE TABLE IF NOT EXISTS sync_collections (
    collection_id UUID PRIMARY KEY,
    collection_name VARCHAR(255) NOT NULL,
    primary_document_count BIGINT DEFAULT 0,
    replica_document_count BIGINT DEFAULT 0,
    last_successful_sync TIMESTAMP,
    last_sync_attempt TIMESTAMP DEFAULT NOW(),
    sync_status VARCHAR(20) DEFAULT 'pending', -- pending, syncing, success, error
    sync_lag_seconds INTEGER DEFAULT 0,
    consecutive_errors INTEGER DEFAULT 0,
    last_error_message TEXT,
    bytes_synced BIGINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Lightweight sync history (only keep recent records)
CREATE TABLE IF NOT EXISTS sync_history (
    id SERIAL PRIMARY KEY,
    collection_id UUID REFERENCES sync_collections(collection_id) ON DELETE CASCADE,
    sync_started_at TIMESTAMP DEFAULT NOW(),
    sync_completed_at TIMESTAMP,
    documents_processed INTEGER,
    sync_duration_seconds INTEGER,
    success BOOLEAN,
    error_message TEXT,
    
    -- Auto-cleanup: only keep last 30 days
    CONSTRAINT check_recent_sync CHECK (sync_started_at > NOW() - INTERVAL '30 days')
);

-- Performance metrics (aggregated, not per-document)
CREATE TABLE IF NOT EXISTS sync_metrics_daily (
    metric_date DATE PRIMARY KEY,
    total_collections_synced INTEGER DEFAULT 0,
    total_documents_synced BIGINT DEFAULT 0,
    total_sync_time_seconds INTEGER DEFAULT 0,
    average_lag_seconds INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient queries (minimal overhead)
CREATE INDEX IF NOT EXISTS idx_sync_collections_status ON sync_collections(sync_status);
CREATE INDEX IF NOT EXISTS idx_sync_collections_updated ON sync_collections(updated_at);
CREATE INDEX IF NOT EXISTS idx_sync_history_collection ON sync_history(collection_id);
CREATE INDEX IF NOT EXISTS idx_sync_history_date ON sync_history(sync_started_at);

-- Automatic cleanup function to maintain free tier limits
CREATE OR REPLACE FUNCTION cleanup_old_sync_data() RETURNS void AS $$
BEGIN
    -- Keep only last 30 days of sync history
    DELETE FROM sync_history 
    WHERE sync_started_at < NOW() - INTERVAL '30 days';
    
    -- Keep only last 90 days of daily metrics  
    DELETE FROM sync_metrics_daily 
    WHERE metric_date < CURRENT_DATE - INTERVAL '90 days';
    
    -- Reset consecutive error counts for old successful syncs
    UPDATE sync_collections 
    SET consecutive_errors = 0 
    WHERE sync_status = 'success' AND consecutive_errors > 0;
    
END;
$$ LANGUAGE plpgsql;

-- Auto-cleanup trigger (run daily)
CREATE OR REPLACE FUNCTION schedule_cleanup() RETURNS trigger AS $$
BEGIN
    -- Only run cleanup occasionally to avoid overhead
    IF random() < 0.01 THEN  -- 1% chance on each update
        PERFORM cleanup_old_sync_data();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auto_cleanup_trigger
    AFTER UPDATE ON sync_collections
    FOR EACH ROW
    EXECUTE FUNCTION schedule_cleanup();

-- Helper view for monitoring
CREATE OR REPLACE VIEW sync_status_summary AS
SELECT 
    sync_status,
    COUNT(*) as collection_count,
    SUM(primary_document_count) as total_documents,
    AVG(sync_lag_seconds) as avg_lag_seconds,
    MAX(last_successful_sync) as last_activity
FROM sync_collections 
GROUP BY sync_status;

-- Space usage monitoring query
CREATE OR REPLACE VIEW database_usage AS
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC; 