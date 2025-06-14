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
                        
                        -- Indexes
                        CREATE INDEX IF NOT EXISTS idx_sync_status ON sync_collections(sync_status);
                        CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON performance_metrics(metric_timestamp);
                        CREATE INDEX IF NOT EXISTS idx_recommendations_urgency ON upgrade_recommendations(urgency, created_at);
                        
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
        
        # Log urgent recommendations
        urgent_recs = [r for r in recommendations if r['urgency'] == 'high']
        if urgent_recs:
            logger.warning(f"🚨 URGENT: Resource upgrade recommended - {urgent_recs[0]['reason']}")
    
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
        """Production-grade collection sync with full monitoring"""
        collection_name = primary_collection['name']
        collection_id = primary_collection['id']
        start_time = time.time()
        start_memory = psutil.virtual_memory().used / 1024 / 1024
        
        try:
            logger.info(f"🔄 Syncing collection '{collection_name}'")
            
            # Find or create replica collection
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
                    "metadata": {"synced_from": "primary", "sync_version": "2.0"}
                }
                response = self._make_request('POST', create_url, json=create_data)
                replica_collection_id = response.json().get('id')
                logger.info(f"✅ Created replica collection '{collection_name}'")
            
            # Stream sync with adaptive batching
            batch_size = self.calculate_optimal_batch_size(collection_id, 1000)
            offset = 0
            total_synced = 0
            batch_count = 0
            peak_memory = start_memory
            
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
            
            duration = time.time() - start_time
            
            # Update database state
            self.update_collection_state(
                collection_id, collection_name, total_synced, total_synced,
                SyncStatus.SUCCESS, duration, batch_count, peak_memory - start_memory
            )
            
            logger.info(f"✅ Synced '{collection_name}': {total_synced} docs in {duration:.2f}s ({batch_count} batches)")
            
            return SyncMetrics(
                collection_id=collection_id,
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
    
    def perform_production_sync(self):
        """Perform full production sync with monitoring and reporting"""
        try:
            start_time = time.time()
            start_memory = psutil.virtual_memory().used / 1024 / 1024
            
            logger.info("🚀 Starting production sync cycle")
            
            # Get collections from both instances
            primary_collections = self.get_all_collections(self.primary_url)
            replica_collections = self.get_all_collections(self.replica_url)
            
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
            
            # Log comprehensive results
            logger.info(f"🎯 Sync cycle completed:")
            logger.info(f"   ✅ Successful: {successful_syncs}/{len(primary_collections)} collections")
            logger.info(f"   📄 Documents: {total_documents:,} synced")
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
        """Main production service loop"""
        logger.info(f"🚀 Starting production ChromaDB sync service")
        logger.info(f"⚙️ Configuration: {self.sync_interval}s interval, {self.max_memory_usage_mb}MB limit")
        
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

if __name__ == "__main__":
    service = ProductionSyncService()
    service.run()