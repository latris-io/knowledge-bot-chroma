-- Complete Monitoring Schema for ChromaDB HA System
-- Performance metrics
CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL PRIMARY KEY,
    metric_timestamp TIMESTAMP DEFAULT NOW(),
    memory_usage_mb REAL,
    memory_percent REAL,
    cpu_percent REAL,
    active_collections INTEGER,
    total_documents_synced BIGINT,
    avg_sync_time_seconds REAL
);

-- Upgrade recommendations
CREATE TABLE IF NOT EXISTS upgrade_recommendations (
    id SERIAL PRIMARY KEY,
    recommendation_type VARCHAR(50),
    current_usage REAL,
    recommended_tier VARCHAR(50),
    estimated_monthly_cost REAL,
    reason TEXT,
    urgency VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Distributed sync coordination tables
CREATE TABLE IF NOT EXISTS sync_tasks (
    id SERIAL PRIMARY KEY,
    collection_id UUID NOT NULL,
    collection_name VARCHAR(255) NOT NULL,
    chunk_start_offset INTEGER NOT NULL,
    chunk_end_offset INTEGER NOT NULL,
    task_status VARCHAR(20) DEFAULT 'pending',
    worker_id VARCHAR(50),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sync_workers (
    worker_id VARCHAR(50) PRIMARY KEY,
    last_heartbeat TIMESTAMP DEFAULT NOW(),
    worker_status VARCHAR(20) DEFAULT 'active',
    current_task_id INTEGER REFERENCES sync_tasks(id),
    memory_usage_mb REAL,
    cpu_percent REAL
);

-- Additional monitoring table from comprehensive monitor
CREATE TABLE IF NOT EXISTS service_resource_metrics (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(50) NOT NULL,
    memory_usage_mb REAL NOT NULL,
    memory_percent REAL NOT NULL,
    cpu_percent REAL NOT NULL,
    disk_usage_percent REAL NOT NULL,
    disk_free_gb REAL NOT NULL,
    disk_total_gb REAL NOT NULL,
    recorded_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON performance_metrics(metric_timestamp);
CREATE INDEX IF NOT EXISTS idx_recommendations_urgency ON upgrade_recommendations(urgency, created_at);
CREATE INDEX IF NOT EXISTS idx_sync_tasks_status ON sync_tasks(task_status, created_at);
CREATE INDEX IF NOT EXISTS idx_sync_workers_heartbeat ON sync_workers(worker_status, last_heartbeat); 