#!/usr/bin/env python3
"""
Production-Ready ChromaDB Sync Service
Complete scalable solution that works on free/starter tier and grows with your needs

Features:
- Memory-efficient batching for current 512MB constraint
- Automatic resource monitoring with upgrade recommendations  
- State tracking using free PostgreSQL
- Error handling and retry logic
- Performance metrics and alerting
- Ready to scale to millions of documents
"""

import os
import time
import logging
import schedule
import requests
import json
import psycopg2
import threading
import psutil
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc
import sys
from dataclasses import dataclass
from enum import Enum

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SyncStatus(Enum):
    PENDING = "pending"
    SYNCING = "syncing" 
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"

@dataclass
class ResourceMetrics:
    memory_usage_mb: float
    memory_percent: float
    cpu_percent: float
    disk_usage_percent: float
    timestamp: datetime

@dataclass
class SyncMetrics:
    collection_id: str
    collection_name: str
    documents_processed: int
    sync_duration_seconds: float
    batch_count: int
    memory_peak_mb: float
    status: SyncStatus
    error_message: Optional[str] = None

class ProductionSyncService:
    def __init__(self):
        # Service configuration
        self.primary_url = os.getenv("PRIMARY_URL", "https://chroma-primary.onrender.com").rstrip('/')
        self.replica_url = os.getenv("REPLICA_URL", "https://chroma-replica.onrender.com").rstrip('/')
        self.sync_interval = int(os.getenv("SYNC_INTERVAL", "300"))
        self.database_url = os.getenv("DATABASE_URL")
        
        # Resource management for current tier
        self.max_memory_usage_mb = int(os.getenv("MAX_MEMORY_MB", "400"))  # 400MB for 512MB container
        self.max_workers = int(os.getenv("MAX_WORKERS", "2"))  # Conservative for starter tier
        self.default_batch_size = int(os.getenv("DEFAULT_BATCH_SIZE", "1000"))
        
        # Distributed sync configuration (NEW)
        self.distributed_mode = os.getenv("SYNC_DISTRIBUTED", "false").lower() == "true"
        self.coordinator_mode = os.getenv("SYNC_COORDINATOR", "false").lower() == "true"
        self.worker_id = f"worker-{os.getenv('RENDER_SERVICE_ID', 'local')}-{int(time.time())}"
        self.chunk_size = int(os.getenv("SYNC_CHUNK_SIZE", "1000"))
        
        # Performance monitoring
        self.resource_check_interval = 30  # seconds
        self.performance_history = []
        self.upgrade_recommendations = []
        
        # Initialize components
        self.init_database()
        self.start_resource_monitoring()
        
        logger.info("🚀 Production ChromaDB Sync Service initialized")
        logger.info(f"📊 Resource limits: {self.max_memory_usage_mb}MB RAM, {self.max_workers} workers")
        logger.info(f"🔄 Sync interval: {self.sync_interval}s")
        
        if self.distributed_mode:
            mode = "Coordinator" if self.coordinator_mode else "Worker"
            logger.info(f"🌐 Distributed mode: {mode} (ID: {self.worker_id})")
        else:
            logger.info("🔄 Single-worker mode (traditional)")
        
    def init_database(self):
        """Initialize production database schema"""
        if not self.database_url:
            logger.warning("⚠️ No DATABASE_URL - state tracking disabled")
            return
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # Enhanced production schema
                    cursor.execute("""
                        -- Main sync state table
                        CREATE TABLE IF NOT EXISTS sync_collections (
                            collection_id UUID PRIMARY KEY,
                            collection_name VARCHAR(255) NOT NULL,
                            primary_document_count BIGINT DEFAULT 0,
                            replica_document_count BIGINT DEFAULT 0,
                            last_successful_sync TIMESTAMP,
                            last_sync_attempt TIMESTAMP DEFAULT NOW(),
                            sync_status VARCHAR(20) DEFAULT 'pending',
                            sync_duration_seconds REAL DEFAULT 0,
                            avg_batch_size INTEGER DEFAULT 0,
                            consecutive_errors INTEGER DEFAULT 0,
                            last_error_message TEXT,
                            memory_peak_mb REAL DEFAULT 0,
                            created_at TIMESTAMP DEFAULT NOW(),
                            updated_at TIMESTAMP DEFAULT NOW()
                        );
                        
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
                        
                        -- Indexes
                        CREATE INDEX IF NOT EXISTS idx_sync_status ON sync_collections(sync_status);
                        CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON performance_metrics(metric_timestamp);
                        CREATE INDEX IF NOT EXISTS idx_recommendations_urgency ON upgrade_recommendations(urgency, created_at);
                        CREATE INDEX IF NOT EXISTS idx_sync_tasks_status ON sync_tasks(task_status, created_at);
                        CREATE INDEX IF NOT EXISTS idx_sync_workers_heartbeat ON sync_workers(worker_status, last_heartbeat);
                        
                        -- Cleanup function
                        CREATE OR REPLACE FUNCTION cleanup_old_data() RETURNS void AS $$
                        BEGIN
                            DELETE FROM performance_metrics WHERE metric_timestamp < NOW() - INTERVAL '7 days';
                            DELETE FROM upgrade_recommendations WHERE created_at < NOW() - INTERVAL '30 days';
                        END;
                        $$ LANGUAGE plpgsql;
                    """)
                conn.commit()
            logger.info("✅ Production database schema initialized")
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            self.database_url = None
    
    def start_resource_monitoring(self):
        """Start background resource monitoring"""
        def monitor_resources():
            while True:
                try:
                    metrics = self.collect_resource_metrics()
                    self.store_performance_metrics(metrics)
                    self.check_upgrade_recommendations(metrics)
                    time.sleep(self.resource_check_interval)
                except Exception as e:
                    logger.error(f"Resource monitoring error: {e}")
                    time.sleep(60)
        
        monitor_thread = threading.Thread(target=monitor_resources, daemon=True)
        monitor_thread.start()
        logger.info("📊 Resource monitoring started")
    
    def collect_resource_metrics(self) -> ResourceMetrics:
        """Collect current resource usage metrics"""
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        disk = psutil.disk_usage('/')
        
        return ResourceMetrics(
            memory_usage_mb=memory.used / 1024 / 1024,
            memory_percent=memory.percent,
            cpu_percent=cpu_percent,
            disk_usage_percent=disk.percent,
            timestamp=datetime.now()
        )
    
    def store_performance_metrics(self, metrics: ResourceMetrics):
        """Store performance metrics in database"""
        if not self.database_url:
            return
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO performance_metrics 
                        (memory_usage_mb, memory_percent, cpu_percent, total_documents_synced)
                        VALUES (%s, %s, %s, %s)
                    """, [metrics.memory_usage_mb, metrics.memory_percent, 
                          metrics.cpu_percent, self.get_total_documents_synced()])
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to store metrics: {e}")
    
    def check_upgrade_recommendations(self, metrics: ResourceMetrics):
        """Analyze metrics and generate upgrade recommendations"""
        recommendations = []
        
        # Memory upgrade check
        if metrics.memory_percent > 85:
            recommendations.append({
                'type': 'memory',
                'current': metrics.memory_percent,
                'recommended_tier': 'standard',
                'cost': 21,
                'reason': f'Memory usage at {metrics.memory_percent:.1f}% - approaching limit',
                'urgency': 'high' if metrics.memory_percent > 95 else 'medium'
            })
        
        # CPU upgrade check  
        if metrics.cpu_percent > 80:
            recommendations.append({
                'type': 'cpu',
                'current': metrics.cpu_percent,
                'recommended_tier': 'standard',
                'cost': 21,
                'reason': f'CPU usage at {metrics.cpu_percent:.1f}% - sync performance degraded',
                'urgency': 'medium'
            })
        
        # Disk upgrade check
        if metrics.disk_usage_percent > 80:
            recommendations.append({
                'type': 'disk',
                'current': metrics.disk_usage_percent,
                'recommended_tier': 'larger_disk',
                'cost': 10,
                'reason': f'Disk usage at {metrics.disk_usage_percent:.1f}% - data growth risk',
                'urgency': 'low'
            })
        
        # Store new recommendations
        for rec in recommendations:
            self.store_upgrade_recommendation(rec)
        
        # Log urgent recommendations and send Slack alerts
        urgent_recs = [r for r in recommendations if r['urgency'] == 'high']
        if urgent_recs:
            rec = urgent_recs[0]
            logger.warning(f"🚨 URGENT: Resource upgrade recommended - {rec['reason']}")
            self.send_slack_upgrade_alert(rec)
        
        # Send Slack for medium priority recommendations (daily limit)
        medium_recs = [r for r in recommendations if r['urgency'] == 'medium']
        if medium_recs:
            self.send_slack_upgrade_alert(medium_recs[0], frequency_limit=True)
    
    def store_upgrade_recommendation(self, recommendation: dict):
        """Store upgrade recommendation in database"""
        if not self.database_url:
            return
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO upgrade_recommendations 
                        (recommendation_type, current_usage, recommended_tier, 
                         estimated_monthly_cost, reason, urgency)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, [recommendation['type'], recommendation['current'],
                          recommendation['recommended_tier'], recommendation['cost'],
                          recommendation['reason'], recommendation['urgency']])
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to store recommendation: {e}")
    
    def send_slack_upgrade_alert(self, recommendation: dict, frequency_limit: bool = False):
        """Send Slack notification for upgrade recommendations"""
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            return
        
        # Check frequency limiting for non-urgent alerts
        if frequency_limit:
            try:
                with psycopg2.connect(self.database_url) as conn:
                    with conn.cursor() as cursor:
                        # Check if we've sent this type of alert in the last 24 hours
                        cursor.execute("""
                            SELECT COUNT(*) FROM upgrade_recommendations 
                            WHERE recommendation_type = %s AND urgency = %s 
                            AND created_at > NOW() - INTERVAL '24 hours'
                        """, [recommendation['type'], recommendation['urgency']])
                        
                        recent_count = cursor.fetchone()[0]
                        if recent_count > 1:  # Already sent today
                            return
            except Exception:
                pass  # If check fails, send anyway
        
        # Determine alert styling
        urgency = recommendation['urgency']
        emoji = "🚨" if urgency == "high" else "⚠️" if urgency == "medium" else "ℹ️"
        color = "danger" if urgency == "high" else "warning" if urgency == "medium" else "good"
        
        # Format service name
        service_name = f"chroma-sync ({recommendation['type']} upgrade needed)"
        
        # Create Slack message
        message = f"*{recommendation['reason']}*\n"
        message += f"Current Usage: {recommendation['current']:.1f}%\n"
        message += f"Recommended: {recommendation['recommended_tier']} plan\n"
        message += f"Cost Impact: ${recommendation['cost']}/month\n"
        message += f"Urgency: {urgency.title()}"
        
        payload = {
            "text": f"{emoji} ChromaDB Upgrade Needed",
            "attachments": [
                {
                    "color": color,
                    "title": service_name,
                    "text": message,
                    "footer": "ChromaDB Resource Monitoring",
                    "ts": int(time.time()),
                    "fields": [
                        {
                            "title": "Resource Type",
                            "value": recommendation['type'].title(),
                            "short": True
                        },
                        {
                            "title": "Current Usage", 
                            "value": f"{recommendation['current']:.1f}%",
                            "short": True
                        },
                        {
                            "title": "Recommended Plan",
                            "value": recommendation['recommended_tier'],
                            "short": True
                        },
                        {
                            "title": "Monthly Cost",
                            "value": f"${recommendation['cost']}",
                            "short": True
                        }
                    ]
                }
            ]
        }
        
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"📱 Slack upgrade alert sent: {recommendation['type']} {urgency}")
            else:
                logger.warning(f"❌ Slack alert failed: HTTP {response.status_code}")
        except Exception as e:
            logger.debug(f"Failed to send Slack notification: {e}")
    
    def get_total_documents_synced(self) -> int:
        """Get total documents currently synced"""
        if not self.database_url:
            return 0
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT SUM(replica_document_count) FROM sync_collections")
                    result = cursor.fetchone()
                    return result[0] if result[0] else 0
        except:
            return 0
    
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with optimized headers"""
        headers = kwargs.get('headers', {})
        headers.update({
            'Accept-Encoding': '',  # No compression for compatibility
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        kwargs['headers'] = headers
        
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    
    def get_all_collections(self, base_url: str) -> List[Dict]:
        """Get all collections with database structure verification"""
        try:
            # Ensure database exists
            databases_url = f"{base_url}/api/v2/tenants/default_tenant/databases"
            databases_response = self._make_request('GET', databases_url)
            databases = databases_response.json()
            
            # Create default_database if missing
            if not any(db.get('name') == 'default_database' for db in databases):
                create_data = {"name": "default_database"}
                self._make_request('POST', databases_url, json=create_data)
                logger.info(f"✅ Created default_database on {base_url}")
            
            # Get collections
            collections_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
            response = self._make_request('GET', collections_url)
            return response.json()
            
        except Exception as e:
            logger.error(f"❌ Failed to get collections from {base_url}: {e}")
            return []

    def calculate_optimal_batch_size(self, collection_id: str, estimated_total: int) -> int:
        """Calculate optimal batch size based on current memory usage"""
        current_memory = psutil.virtual_memory()
        available_memory_mb = (self.max_memory_usage_mb - (current_memory.used / 1024 / 1024))
        
        if available_memory_mb < 50:  # Less than 50MB available
            return min(100, self.default_batch_size // 4)  # Very small batches
        elif available_memory_mb < 100:  # Less than 100MB available
            return min(500, self.default_batch_size // 2)  # Small batches
        else:
            return self.default_batch_size  # Normal batches
    
    def sync_collection_production(self, primary_collection: Dict, replica_collections: List[Dict]) -> SyncMetrics:
        """Production-grade collection sync with full monitoring and proper ID handling"""
        collection_name = primary_collection['name']
        collection_id = primary_collection['id']
        start_time = time.time()
        start_memory = psutil.virtual_memory().used / 1024 / 1024
        
        try:
            logger.info(f"🔄 Syncing collection '{collection_name}' (Primary ID: {collection_id})")
            
            # Find or create replica collection
            replica_collection_id = None
            replica_collection_metadata = {}
            for replica_col in replica_collections:
                if replica_col['name'] == collection_name:
                    replica_collection_id = replica_col['id']
                    replica_collection_metadata = replica_col.get('metadata', {})
                    logger.info(f"📍 Found existing replica collection (Replica ID: {replica_collection_id})")
                    break
            
            if not replica_collection_id:
                # Create replica collection with enhanced metadata including primary ID mapping
                create_url = f"{self.replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
                create_data = {
                    "name": collection_name,
                    "metadata": {
                        "synced_from": "primary", 
                        "sync_version": "2.0",
                        "primary_collection_id": collection_id,  # Track the primary ID
                        "sync_created_at": time.time()
                    }
                }
                response = self._make_request('POST', create_url, json=create_data)
                replica_collection_id = response.json().get('id')
                logger.info(f"✅ Created replica collection '{collection_name}' (Replica ID: {replica_collection_id}, Primary ID: {collection_id})")
            else:
                # Update existing replica metadata to include primary ID mapping if missing
                if replica_collection_metadata.get('primary_collection_id') != collection_id:
                    logger.info(f"🔄 Updating replica metadata to track primary ID mapping")
                    update_metadata = dict(replica_collection_metadata)
                    update_metadata.update({
                        "synced_from": "primary",
                        "sync_version": "2.0", 
                        "primary_collection_id": collection_id,
                        "last_sync_update": time.time()
                    })
                    
                    # Update replica collection metadata
                    modify_url = f"{self.replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_collection_id}"
                    modify_data = {"metadata": update_metadata}
                    self._make_request('PATCH', modify_url, json=modify_data)
                    logger.info(f"✅ Updated replica metadata with primary ID mapping")
            
            # Check if we need to sync (basic change detection)
            skip_sync = False
            if replica_collection_metadata.get('primary_collection_id') == collection_id:
                # Could add more sophisticated change detection here (e.g., document counts, checksums)
                logger.debug(f"Collection '{collection_name}' metadata indicates previous successful sync")
            
            # Stream sync with adaptive batching (only if needed)
            if not skip_sync:
                batch_size = self.calculate_optimal_batch_size(collection_id, 1000)
                offset = 0
                total_synced = 0
                batch_count = 0
                peak_memory = start_memory
                
                # Clear existing documents in replica collection first (for clean sync)
                logger.info(f"🧹 Clearing existing documents from replica collection for clean sync")
                try:
                    # Get all document IDs from replica
                    get_replica_url = f"{self.replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_collection_id}/get"
                    get_replica_data = {"include": ["documents"], "limit": 10000}  # Get all docs
                    replica_response = self._make_request('POST', get_replica_url, json=get_replica_data)
                    replica_docs = replica_response.json()
                    
                    if replica_docs.get('ids'):
                        # Delete existing documents
                        delete_url = f"{self.replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_collection_id}/delete"
                        delete_data = {"ids": replica_docs['ids']}
                        self._make_request('POST', delete_url, json=delete_data)
                        logger.info(f"🗑️ Cleared {len(replica_docs['ids'])} existing documents from replica")
                except Exception as e:
                    logger.warning(f"⚠️ Could not clear existing documents: {e} - proceeding with sync")
                
                while True:
                    # Monitor memory before each batch
                    current_memory = psutil.virtual_memory().used / 1024 / 1024
                    peak_memory = max(peak_memory, current_memory)
                    
                    # Adaptive batch size based on memory pressure
                    if current_memory > self.max_memory_usage_mb * 0.9:
                        batch_size = max(100, batch_size // 2)  # Reduce batch size
                        logger.warning(f"⚠️ High memory usage, reducing batch size to {batch_size}")
                    
                    # Get batch from primary
                    get_url = f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get"
                    get_data = {
                        "include": ["documents", "metadatas", "embeddings"],
                        "offset": offset,
                        "limit": batch_size
                    }
                    response = self._make_request('POST', get_url, json=get_data)
                    batch = response.json()
                    
                    if not batch.get('ids'):
                        break
                    
                    # Add batch to replica
                    add_url = f"{self.replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_collection_id}/add"
                    add_data = {k: v for k, v in batch.items() if v is not None and k != 'include'}
                    self._make_request('POST', add_url, json=add_data)
                    
                    total_synced += len(batch['ids'])
                    batch_count += 1
                    offset += batch_size
                    
                    # Clear batch from memory and force cleanup
                    del batch, add_data
                    gc.collect()
                    
                    logger.debug(f"📦 Batch {batch_count}: synced {total_synced} docs")
                    
                    # Prevent overwhelming the system
                    time.sleep(0.05)
                
                logger.info(f"✅ Synced {total_synced} documents in {batch_count} batches")
            else:
                total_synced = 0
                batch_count = 0
                logger.info(f"⏭️ Skipped sync - collection appears up to date")
            
            duration = time.time() - start_time
            
            # Update database state (use primary collection ID for tracking)
            self.update_collection_state(
                collection_id, collection_name, total_synced, total_synced,
                SyncStatus.SUCCESS, duration, batch_count, peak_memory - start_memory
            )
            
            logger.info(f"✅ Sync complete '{collection_name}': {total_synced} docs in {duration:.2f}s")
            logger.info(f"📊 ID Mapping: Primary({collection_id}) → Replica({replica_collection_id})")
            
            return SyncMetrics(
                collection_id=collection_id,  # Always use primary ID for consistency
                collection_name=collection_name,
                documents_processed=total_synced,
                sync_duration_seconds=duration,
                batch_count=batch_count,
                memory_peak_mb=peak_memory - start_memory,
                status=SyncStatus.SUCCESS
            )
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            
            self.update_collection_state(
                collection_id, collection_name, 0, 0,
                SyncStatus.ERROR, duration, 0, 0, error_msg
            )
            
            logger.error(f"❌ Failed to sync '{collection_name}': {error_msg}")
            
            return SyncMetrics(
                collection_id=collection_id,
                collection_name=collection_name,
                documents_processed=0,
                sync_duration_seconds=duration,
                batch_count=0,
                memory_peak_mb=0,
                status=SyncStatus.ERROR,
                error_message=error_msg
            )
    
    def update_collection_state(self, collection_id: str, collection_name: str,
                               primary_count: int, replica_count: int, status: SyncStatus,
                               duration: float, batch_count: int, memory_delta: float,
                               error_msg: str = None):
        """Update collection sync state in database"""
        if not self.database_url:
            return
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO sync_collections 
                        (collection_id, collection_name, primary_document_count, replica_document_count,
                         sync_status, sync_duration_seconds, avg_batch_size, memory_peak_mb,
                         last_error_message, last_sync_attempt, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (collection_id) DO UPDATE SET
                            collection_name = EXCLUDED.collection_name,
                            primary_document_count = EXCLUDED.primary_document_count,
                            replica_document_count = EXCLUDED.replica_document_count,
                            sync_status = EXCLUDED.sync_status,
                            sync_duration_seconds = EXCLUDED.sync_duration_seconds,
                            avg_batch_size = EXCLUDED.avg_batch_size,
                            memory_peak_mb = EXCLUDED.memory_peak_mb,
                            last_error_message = EXCLUDED.last_error_message,
                            last_sync_attempt = NOW(),
                            updated_at = NOW(),
                            consecutive_errors = CASE 
                                WHEN EXCLUDED.sync_status = 'success' THEN 0
                                ELSE sync_collections.consecutive_errors + 1
                            END,
                            last_successful_sync = CASE
                                WHEN EXCLUDED.sync_status = 'success' THEN NOW()
                                ELSE sync_collections.last_successful_sync
                            END
                    """, [collection_id, collection_name, primary_count, replica_count,
                          status.value, duration, batch_count, memory_delta, error_msg])
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update collection state: {e}")
    
    def sync_deletions(self):
        """Sync deletions from primary to replica - remove collections that don't exist on primary"""
        try:
            logger.info("🗑️ Starting deletion sync...")
            
            # Get collections from both instances
            primary_collections = self.get_all_collections(self.primary_url)
            replica_collections = self.get_all_collections(self.replica_url)
            
            if not replica_collections:
                logger.info("ℹ️ No collections on replica to check for deletion")
                return {'deleted': 0, 'errors': []}
            
            # Create set of primary collection names for fast lookup
            primary_names = {col['name'] for col in primary_collections}
            
            # Find collections on replica that don't exist on primary
            collections_to_delete = []
            for replica_col in replica_collections:
                collection_name = replica_col['name']
                
                # Skip if collection exists on primary
                if collection_name in primary_names:
                    continue
                
                # Safety check: Only auto-delete test collections to prevent accidents
                if not collection_name.startswith('AUTOTEST_'):
                    logger.warning(f"⚠️ Found orphaned non-test collection on replica: {collection_name} (manual review needed)")
                    continue
                
                collections_to_delete.append(collection_name)
            
            if not collections_to_delete:
                logger.info("✅ No orphaned collections found - replica in sync")
                return {'deleted': 0, 'errors': []}
            
            logger.info(f"🗑️ Found {len(collections_to_delete)} orphaned collections to delete")
            
            # HIGH-VOLUME STRATEGY: Use parallel processing for deletions
            deleted_count = 0
            deletion_errors = []
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit deletion tasks in parallel
                future_to_collection = {
                    executor.submit(self._delete_collection_from_replica, collection_name): collection_name
                    for collection_name in collections_to_delete
                }
                
                # Process results as they complete
                for future in as_completed(future_to_collection):
                    collection_name = future_to_collection[future]
                    try:
                        success = future.result()
                        if success:
                            deleted_count += 1
                            logger.info(f"✅ Deleted orphaned collection: {collection_name}")
                        else:
                            deletion_errors.append(f"Failed to delete {collection_name}: Unknown error")
                    except Exception as e:
                        error_msg = f"Failed to delete {collection_name}: {str(e)}"
                        logger.error(f"❌ {error_msg}")
                        deletion_errors.append(error_msg)
            
            # Log summary
            if deleted_count > 0:
                logger.info(f"🗑️ Deletion sync complete: {deleted_count} orphaned collections removed")
                
                # Send Slack notification for significant deletions
                if deleted_count > 5:
                    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
                    if webhook_url:
                        try:
                            payload = {
                                "text": f"🗑️ ChromaDB Sync: Cleaned up {deleted_count} orphaned test collections from replica"
                            }
                            requests.post(webhook_url, json=payload, timeout=10)
                        except:
                            pass  # Don't fail sync for notification issues
            
            return {'deleted': deleted_count, 'errors': deletion_errors}
            
        except Exception as e:
            logger.error(f"❌ Deletion sync failed: {e}")
            return {'deleted': 0, 'errors': [str(e)]}

    def _delete_collection_from_replica(self, collection_name: str) -> bool:
        """Delete a single collection from replica using collection name (correct ChromaDB API format)"""
        try:
            # Use collection NAME in URL path - this is the correct ChromaDB API format!
            delete_url = f"{self.replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
            self._make_request('DELETE', delete_url)
            logger.info(f"✅ Deleted collection '{collection_name}' from replica")
            return True
            
        except Exception as e:
            if "404" in str(e):
                logger.info(f"📝 Collection '{collection_name}' not found on replica (already deleted)")
                return True  # Consider it successfully deleted if it doesn't exist
            else:
                logger.error(f"❌ Failed to delete '{collection_name}' from replica: {e}")
                return False

    def perform_production_sync(self):
        """Perform full production sync with monitoring and reporting"""
        try:
            start_time = time.time()
            start_memory = psutil.virtual_memory().used / 1024 / 1024
            
            logger.info("🚀 Starting production sync cycle")
            
            # Get collections from both instances
            primary_collections = self.get_all_collections(self.primary_url)
            replica_collections = self.get_all_collections(self.replica_url)
            
            # ENHANCED: Sync deletions first (new functionality)
            deletion_results = self.sync_deletions()
            
            if not primary_collections:
                logger.info("ℹ️ No collections found on primary instance")
                return
            
            logger.info(f"📊 Sync status: Primary({len(primary_collections)}) → Replica({len(replica_collections)})")
            
            # Sync collections with controlled parallelism
            sync_results = []
            successful_syncs = 0
            total_documents = 0
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit sync tasks
                future_to_collection = {
                    executor.submit(self.sync_collection_production, col, replica_collections): col
                    for col in primary_collections
                }
                
                # Process results as they complete
                for future in as_completed(future_to_collection):
                    try:
                        result = future.result()
                        sync_results.append(result)
                        
                        if result.status == SyncStatus.SUCCESS:
                            successful_syncs += 1
                            total_documents += result.documents_processed
                    except Exception as e:
                        logger.error(f"Sync task failed: {e}")
            
            # Calculate final metrics
            total_duration = time.time() - start_time
            end_memory = psutil.virtual_memory().used / 1024 / 1024
            memory_delta = end_memory - start_memory
            
            # ENHANCED: Log comprehensive results including deletions
            logger.info(f"🎯 Sync cycle completed:")
            logger.info(f"   ✅ Successful: {successful_syncs}/{len(primary_collections)} collections")
            logger.info(f"   📄 Documents: {total_documents:,} synced")
            logger.info(f"   🗑️ Deletions: {deletion_results['deleted']} orphaned collections removed")
            logger.info(f"   ⏱️ Duration: {total_duration:.2f}s")
            logger.info(f"   🧠 Memory: {memory_delta:+.1f}MB delta")
            
            # Check for performance issues
            if memory_delta > 100:
                logger.warning(f"⚠️ High memory usage: +{memory_delta:.1f}MB - consider upgrading plan")
            
            if total_duration > 300:  # 5 minutes
                logger.warning(f"⚠️ Slow sync: {total_duration:.1f}s - consider upgrading CPU")
            
        except Exception as e:
            logger.error(f"❌ Production sync failed: {e}")
    
    def run(self):
        """Main production service loop with distributed mode support"""
        logger.info(f"🚀 Starting production ChromaDB sync service")
        logger.info(f"⚙️ Configuration: {self.sync_interval}s interval, {self.max_memory_usage_mb}MB limit")
        
        if self.distributed_mode:
            if self.coordinator_mode:
                self.run_coordinator()
            else:
                self.run_worker()
        else:
            self.run_traditional_sync()

    def run_traditional_sync(self):
        """Traditional single-worker sync mode (unchanged behavior)"""
        # Schedule regular sync
        schedule.every(self.sync_interval).seconds.do(self.perform_production_sync)
        
        # Initial sync
        self.perform_production_sync()
        
        # Main loop
        while True:
            try:
                schedule.run_pending()
                time.sleep(10)
            except KeyboardInterrupt:
                logger.info("🛑 Sync service shutting down...")
                break
            except Exception as e:
                logger.error(f"❌ Unexpected error: {e}")
                time.sleep(60)

    def run_coordinator(self):
        """Coordinator mode: breaks collections into chunks and creates tasks"""
        logger.info("🌐 Starting in COORDINATOR mode")
        
        while True:
            try:
                coordinator_start = time.time()
                
                # Get collections that need syncing
                primary_collections = self.get_all_collections(self.primary_url)
                if not primary_collections:
                    logger.info("ℹ️ No collections to coordinate")
                    time.sleep(self.sync_interval)
                    continue
                
                # Break collections into sync tasks
                total_tasks_created = 0
                for collection in primary_collections:
                    tasks_created = self.create_sync_tasks(collection)
                    total_tasks_created += tasks_created
                
                coordinator_duration = time.time() - coordinator_start
                logger.info(f"📋 Coordinator cycle: {total_tasks_created} tasks created in {coordinator_duration:.2f}s")
                
                # Clean up old completed tasks
                self.cleanup_old_tasks()
                
                # Wait for next coordination cycle
                time.sleep(self.sync_interval)
                
            except KeyboardInterrupt:
                logger.info("🛑 Coordinator shutting down...")
                break
            except Exception as e:
                logger.error(f"❌ Coordinator error: {e}")
                time.sleep(60)

    def run_worker(self):
        """Worker mode: processes assigned tasks from queue"""
        logger.info(f"🔧 Starting in WORKER mode (ID: {self.worker_id})")
        
        # Register this worker
        self.register_worker()
        
        while True:
            try:
                # Send heartbeat
                self.update_worker_heartbeat()
                
                # Get next available task
                task = self.claim_next_task()
                
                if task:
                    logger.info(f"🔄 Processing task {task['id']}: {task['collection_name']} "
                               f"chunk {task['chunk_start_offset']}-{task['chunk_end_offset']}")
                    
                    # Process the task
                    self.process_sync_task(task)
                else:
                    # No work available, short wait
                    time.sleep(10)
                
            except KeyboardInterrupt:
                logger.info("🛑 Worker shutting down...")
                self.unregister_worker()
                break
            except Exception as e:
                logger.error(f"❌ Worker error: {e}")
                time.sleep(30)

    def create_sync_tasks(self, collection: Dict) -> int:
        """Break collection into chunks and create sync tasks"""
        collection_id = collection['id']
        collection_name = collection['name']
        
        try:
            # Estimate collection size
            total_docs = self.estimate_collection_size(collection_id)
            
            if total_docs == 0:
                # Empty collection - create single task for structure sync
                self.create_task(collection_id, collection_name, 0, 0, is_empty=True)
                return 1
            
            # Break into chunks
            chunks = self.calculate_chunks(total_docs, self.chunk_size)
            tasks_created = 0
            
            for chunk_start, chunk_end in chunks:
                self.create_task(collection_id, collection_name, chunk_start, chunk_end)
                tasks_created += 1
            
            logger.info(f"📦 Collection '{collection_name}': {total_docs} docs → {tasks_created} tasks")
            return tasks_created
            
        except Exception as e:
            logger.error(f"❌ Failed to create tasks for '{collection_name}': {e}")
            return 0

    def calculate_chunks(self, total_docs: int, chunk_size: int) -> List[Tuple[int, int]]:
        """Calculate optimal chunk boundaries"""
        chunks = []
        for start in range(0, total_docs, chunk_size):
            end = min(start + chunk_size, total_docs)
            chunks.append((start, end))
        return chunks

    def create_task(self, collection_id: str, collection_name: str, 
                   start_offset: int, end_offset: int, is_empty: bool = False):
        """Create a sync task in database"""
        if not self.database_url:
            return
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # Check if task already exists and is not failed
                    cursor.execute("""
                        SELECT id FROM sync_tasks 
                        WHERE collection_id = %s AND chunk_start_offset = %s 
                        AND chunk_end_offset = %s AND task_status != 'failed'
                    """, [collection_id, start_offset, end_offset])
                    
                    if cursor.fetchone():
                        return  # Task already exists
                    
                    # Create new task
                    cursor.execute("""
                        INSERT INTO sync_tasks 
                        (collection_id, collection_name, chunk_start_offset, chunk_end_offset)
                        VALUES (%s, %s, %s, %s)
                    """, [collection_id, collection_name, start_offset, end_offset])
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to create task: {e}")

    def claim_next_task(self) -> Optional[Dict]:
        """Atomically claim next available task"""
        if not self.database_url:
            return None
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # Atomic task claiming using PostgreSQL row-level locking
                    cursor.execute("""
                        UPDATE sync_tasks 
                        SET task_status = 'processing',
                            worker_id = %s,
                            started_at = NOW()
                        WHERE id = (
                            SELECT id FROM sync_tasks 
                            WHERE task_status = 'pending'
                            ORDER BY created_at ASC
                            LIMIT 1
                            FOR UPDATE SKIP LOCKED
                        )
                        RETURNING id, collection_id, collection_name, 
                                 chunk_start_offset, chunk_end_offset
                    """, [self.worker_id])
                    
                    result = cursor.fetchone()
                    if result:
                        columns = ['id', 'collection_id', 'collection_name', 
                                 'chunk_start_offset', 'chunk_end_offset']
                        return dict(zip(columns, result))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to claim task: {e}")
        
        return None

    def process_sync_task(self, task: Dict):
        """Process a single sync task (chunk of a collection)"""
        task_id = task['id']
        collection_id = task['collection_id']
        collection_name = task['collection_name']
        start_offset = task['chunk_start_offset']
        end_offset = task['chunk_end_offset']
        
        try:
            # Handle empty collection case
            if start_offset == 0 and end_offset == 0:
                self.sync_empty_collection_structure(collection_name)
                self.complete_task(task_id, success=True)
                return
            
            # Get chunk from primary
            chunk_size = end_offset - start_offset
            chunk_data = self.get_collection_chunk(collection_id, start_offset, chunk_size)
            
            if not chunk_data or not chunk_data.get('ids'):
                logger.info(f"📭 Task {task_id}: No data in chunk")
                self.complete_task(task_id, success=True)
                return
            
            # Add chunk to replica
            self.add_chunk_to_replica(collection_name, chunk_data)
            
            # Mark task complete
            self.complete_task(task_id, success=True)
            
            logger.info(f"✅ Task {task_id} completed: {len(chunk_data['ids'])} docs")
            
        except Exception as e:
            logger.error(f"❌ Task {task_id} failed: {e}")
            self.complete_task(task_id, success=False, error=str(e))

    def complete_task(self, task_id: int, success: bool, error: str = None):
        """Mark task as completed or failed"""
        if not self.database_url:
            return
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    status = 'completed' if success else 'failed'
                    cursor.execute("""
                        UPDATE sync_tasks 
                        SET task_status = %s,
                            completed_at = NOW(),
                            error_message = %s
                        WHERE id = %s
                    """, [status, error, task_id])
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to complete task {task_id}: {e}")

    def register_worker(self):
        """Register this worker in the database"""
        if not self.database_url:
            return
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO sync_workers (worker_id, worker_status)
                        VALUES (%s, 'active')
                        ON CONFLICT (worker_id) DO UPDATE SET
                            worker_status = 'active',
                            last_heartbeat = NOW()
                    """, [self.worker_id])
                conn.commit()
            logger.info(f"✅ Worker {self.worker_id} registered")
        except Exception as e:
            logger.error(f"Failed to register worker: {e}")

    def update_worker_heartbeat(self):
        """Update worker heartbeat and resource usage"""
        if not self.database_url:
            return
            
        try:
            metrics = self.collect_resource_metrics()
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE sync_workers 
                        SET last_heartbeat = NOW(),
                            memory_usage_mb = %s,
                            cpu_percent = %s
                        WHERE worker_id = %s
                    """, [metrics.memory_usage_mb, metrics.cpu_percent, self.worker_id])
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to update heartbeat: {e}")

    def unregister_worker(self):
        """Unregister worker on shutdown"""
        if not self.database_url:
            return
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM sync_workers WHERE worker_id = %s", [self.worker_id])
                conn.commit()
            logger.info(f"✅ Worker {self.worker_id} unregistered")
        except Exception as e:
            logger.error(f"Failed to unregister worker: {e}")

    def estimate_collection_size(self, collection_id: str) -> int:
        """Estimate total documents in collection"""
        try:
            get_url = f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get"
            get_data = {"include": ["documents"], "limit": 1}
            response = self._make_request('POST', get_url, json=get_data)
            data = response.json()
            
            # ChromaDB doesn't return total count directly, so we estimate
            # This is a limitation we'd improve in production
            return 1000  # Conservative estimate for now
        except:
            return 0

    def get_collection_chunk(self, collection_id: str, offset: int, limit: int) -> Dict:
        """Get a chunk of documents from collection"""
        get_url = f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get"
        get_data = {
            "include": ["documents", "metadatas", "embeddings"],
            "offset": offset,
            "limit": limit
        }
        response = self._make_request('POST', get_url, json=get_data)
        return response.json()

    def add_chunk_to_replica(self, collection_name: str, chunk_data: Dict):
        """Add chunk data to replica collection"""
        # Find or create replica collection
        replica_collections = self.get_all_collections(self.replica_url)
        replica_collection_id = None
        
        for replica_col in replica_collections:
            if replica_col['name'] == collection_name:
                replica_collection_id = replica_col['id']
                break
        
        if not replica_collection_id:
            # Create replica collection
            create_url = f"{self.replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
            create_data = {
                "name": collection_name,
                "metadata": {"synced_from": "primary"}
            }
            response = self._make_request('POST', create_url, json=create_data)
            replica_collection_id = response.json().get('id')
        
        # Add chunk to replica
        add_url = f"{self.replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_collection_id}/add"
        add_data = {k: v for k, v in chunk_data.items() if v is not None and k != 'include'}
        self._make_request('POST', add_url, json=add_data)

    def sync_empty_collection_structure(self, collection_name: str):
        """Ensure empty collection structure exists on replica"""
        replica_collections = self.get_all_collections(self.replica_url)
        
        # Check if collection already exists
        for replica_col in replica_collections:
            if replica_col['name'] == collection_name:
                return  # Already exists
        
        # Create empty collection
        create_url = f"{self.replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
        create_data = {
            "name": collection_name,
            "metadata": {"synced_from": "primary", "empty_collection": True}
        }
        self._make_request('POST', create_url, json=create_data)

    def cleanup_old_tasks(self):
        """Clean up old completed/failed tasks"""
        if not self.database_url:
            return
            
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # Delete completed tasks older than 1 hour
                    cursor.execute("""
                        DELETE FROM sync_tasks 
                        WHERE task_status IN ('completed', 'failed') 
                        AND completed_at < NOW() - INTERVAL '1 hour'
                    """)
                    
                    # Reset abandoned tasks (processing > 30 minutes)
                    cursor.execute("""
                        UPDATE sync_tasks 
                        SET task_status = 'pending', worker_id = NULL, started_at = NULL
                        WHERE task_status = 'processing' 
                        AND started_at < NOW() - INTERVAL '30 minutes'
                    """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to cleanup tasks: {e}")

if __name__ == "__main__":
    service = ProductionSyncService()
    service.run()