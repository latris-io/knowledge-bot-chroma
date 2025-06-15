#!/usr/bin/env python3
"""
High-Volume Unified WAL-First ChromaDB Load Balancer
Combines the unified WAL architecture with high-volume processing capabilities

Features:
- WAL-first approach for all writes
- Memory-efficient batching (100-1000 adaptive batch sizes)
- Parallel WAL sync processing with ThreadPoolExecutor
- Resource monitoring and adaptive behavior
- Production-ready for high-volume scenarios
"""

import os
import time
import logging
import requests
import threading
import random
import json
import uuid
import psycopg2
import psycopg2.extras
import psutil
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WALWriteStatus(Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    SYNCED = "synced"
    FAILED = "failed"

class TargetInstance(Enum):
    PRIMARY = "primary"
    REPLICA = "replica"
    BOTH = "both"

@dataclass
class ResourceMetrics:
    memory_usage_mb: float
    memory_percent: float
    cpu_percent: float
    timestamp: datetime

@dataclass
class WALSyncBatch:
    """Batch of WAL writes for efficient processing"""
    writes: List[Dict]
    target_instance: str
    batch_size: int
    estimated_memory_mb: float

@dataclass
class ChromaInstance:
    name: str
    url: str
    priority: int
    is_healthy: bool = True
    consecutive_failures: int = 0
    last_health_check: datetime = field(default_factory=datetime.now)
    total_requests: int = 0
    successful_requests: int = 0
    last_sync_timestamp: Optional[datetime] = None
    
    def update_stats(self, success: bool):
        """Update instance statistics"""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1
    
    def get_success_rate(self) -> float:
        """Get success rate as percentage"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100

class HighVolumeUnifiedWAL:
    def __init__(self):
        self.instances = [
            ChromaInstance(
                name="primary",
                url=os.getenv("PRIMARY_URL", "https://chroma-primary.onrender.com"),
                priority=100
            ),
            ChromaInstance(
                name="replica", 
                url=os.getenv("REPLICA_URL", "https://chroma-replica.onrender.com"),
                priority=80
            )
        ]
        
        # Configuration
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "30"))
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "15"))
        self.read_replica_ratio = float(os.getenv("READ_REPLICA_RATIO", "0.8"))
        self.sync_interval = int(os.getenv("WAL_SYNC_INTERVAL", "10"))
        
        # High-volume configuration
        self.max_memory_usage_mb = int(os.getenv("MAX_MEMORY_MB", "400"))  # 400MB for 512MB container
        self.max_workers = int(os.getenv("MAX_WORKERS", "3"))  # Parallel WAL sync workers
        self.default_batch_size = int(os.getenv("DEFAULT_BATCH_SIZE", "100"))  # WAL sync batch size
        self.max_batch_size = int(os.getenv("MAX_BATCH_SIZE", "500"))
        self.resource_check_interval = 30  # seconds
        
        # PostgreSQL connection for unified WAL
        self.database_url = os.getenv("DATABASE_URL", "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha")
        self.db_lock = threading.Lock()
        
        # Consistency tracking
        self.recent_writes = {}  # collection_id -> timestamp
        self.consistency_window = 30  # 30 seconds
        
        # WAL sync state
        self.is_syncing = False
        self.current_memory_usage = 0.0
        
        # Initialize unified WAL schema
        self._initialize_unified_wal_schema()
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "consistency_overrides": 0,
            "total_wal_writes": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "sync_cycles": 0,
            "batches_processed": 0,
            "memory_pressure_events": 0,
            "adaptive_batch_reductions": 0
        }
        
        # Start monitoring and sync threads
        self.health_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
        self.health_thread.start()
        
        self.resource_thread = threading.Thread(target=self.resource_monitor_loop, daemon=True)
        self.resource_thread.start()
        
        self.wal_sync_thread = threading.Thread(target=self.wal_sync_loop, daemon=True)
        self.wal_sync_thread.start()
        
        logger.info(f"🚀 High-Volume Unified WAL Load Balancer initialized")
        logger.info(f"📊 Resource limits: {self.max_memory_usage_mb}MB RAM, {self.max_workers} workers")
        logger.info(f"🎯 Read replica ratio: {self.read_replica_ratio * 100}%")
        logger.info(f"🔄 WAL sync interval: {self.sync_interval}s, batch size: {self.default_batch_size}")

    def get_db_connection(self):
        """Get PostgreSQL database connection"""
        return psycopg2.connect(self.database_url)

    def _initialize_unified_wal_schema(self):
        """Initialize unified WAL schema with high-volume optimizations"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Unified WAL table for all writes
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS unified_wal_writes (
                            id SERIAL PRIMARY KEY,
                            write_id VARCHAR(100) UNIQUE NOT NULL,
                            method VARCHAR(10) NOT NULL,
                            path TEXT NOT NULL,
                            data BYTEA,
                            headers JSONB,
                            target_instance VARCHAR(20) NOT NULL,
                            status VARCHAR(20) DEFAULT 'pending',
                            collection_id VARCHAR(255),
                            executed_on VARCHAR(20),
                            retry_count INTEGER DEFAULT 0,
                            error_message TEXT,
                            data_size_bytes INTEGER DEFAULT 0,      -- For memory estimation
                            priority INTEGER DEFAULT 0,             -- For batching priority
                            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            executed_at TIMESTAMP WITH TIME ZONE,
                            synced_at TIMESTAMP WITH TIME ZONE,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        );
                    """)
                    
                    # High-volume performance indexes
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_unified_wal_status_priority ON unified_wal_writes(status, priority DESC, timestamp ASC);
                        CREATE INDEX IF NOT EXISTS idx_unified_wal_target_status ON unified_wal_writes(target_instance, status);
                        CREATE INDEX IF NOT EXISTS idx_unified_wal_collection ON unified_wal_writes(collection_id, status);
                        CREATE INDEX IF NOT EXISTS idx_unified_wal_size ON unified_wal_writes(data_size_bytes);
                    """)
                    
                    # Resource monitoring table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS wal_resource_metrics (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            memory_usage_mb REAL,
                            memory_percent REAL,
                            cpu_percent REAL,
                            pending_writes INTEGER,
                            active_batches INTEGER,
                            sync_throughput_per_sec REAL
                        );
                        
                        CREATE INDEX IF NOT EXISTS idx_wal_resource_timestamp ON wal_resource_metrics(timestamp);
                    """)
                    
                    conn.commit()
                    logger.info("✅ High-Volume Unified WAL PostgreSQL schema initialized")
                    
        except Exception as e:
            logger.error(f"❌ Failed to initialize high-volume WAL schema: {e}")
            raise

    def collect_resource_metrics(self) -> ResourceMetrics:
        """Collect current resource usage metrics"""
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        
        return ResourceMetrics(
            memory_usage_mb=memory.used / 1024 / 1024,
            memory_percent=memory.percent,
            cpu_percent=cpu_percent,
            timestamp=datetime.now()
        )

    def calculate_optimal_batch_size(self, estimated_total_writes: int = 100) -> int:
        """Calculate optimal WAL sync batch size based on current memory usage"""
        current_memory = psutil.virtual_memory()
        available_memory_mb = (self.max_memory_usage_mb - (current_memory.used / 1024 / 1024))
        
        if available_memory_mb < 50:  # Less than 50MB available
            self.stats["memory_pressure_events"] += 1
            batch_size = min(50, self.default_batch_size // 4)
            logger.warning(f"⚠️ High memory pressure, reducing WAL batch size to {batch_size}")
            return batch_size
        elif available_memory_mb < 100:  # Less than 100MB available
            self.stats["adaptive_batch_reductions"] += 1
            return min(100, self.default_batch_size // 2)
        else:
            return min(self.max_batch_size, max(self.default_batch_size, estimated_total_writes // 10))

    def add_wal_write(self, method: str, path: str, data: bytes, headers: Dict[str, str], 
                     target_instance: TargetInstance, executed_on: Optional[str] = None) -> str:
        """Add write to unified WAL system with size tracking"""
        write_id = str(uuid.uuid4())
        collection_id = self.extract_collection_identifier(path)
        data_size = len(data) if data else 0
        
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO unified_wal_writes 
                            (write_id, method, path, data, headers, target_instance, 
                             collection_id, executed_on, status, data_size_bytes)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            write_id,
                            method,
                            path,
                            data,
                            json.dumps(headers),
                            target_instance.value,
                            collection_id,
                            executed_on,
                            WALWriteStatus.EXECUTED.value if executed_on else WALWriteStatus.PENDING.value,
                            data_size
                        ))
                        conn.commit()
            
            self.stats["total_wal_writes"] += 1
            return write_id
            
        except Exception as e:
            logger.error(f"❌ Failed to add WAL write: {e}")
            raise

    def get_pending_syncs_batched(self, target_instance: str, batch_size: int) -> List[WALSyncBatch]:
        """Get pending writes in optimized batches for high-volume processing"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Get writes that need to be synced to this instance, ordered by priority and age
                    cur.execute("""
                        SELECT write_id, method, path, data, headers, collection_id, 
                               timestamp, retry_count, data_size_bytes
                        FROM unified_wal_writes 
                        WHERE status = 'executed' 
                        AND (target_instance = 'both' OR 
                             (target_instance = %s AND executed_on != %s) OR
                             (target_instance != %s AND executed_on != %s))
                        AND retry_count < 3
                        ORDER BY priority DESC, timestamp ASC
                        LIMIT %s
                    """, (target_instance, target_instance, target_instance, target_instance, batch_size * 2))
                    
                    all_writes = cur.fetchall()
                    
                    if not all_writes:
                        return []
                    
                    # Create optimized batches
                    batches = []
                    current_batch = []
                    current_batch_size_mb = 0
                    max_batch_size_mb = 50  # 50MB per batch
                    
                    for write in all_writes:
                        write_size_mb = (write.get('data_size_bytes', 0) / 1024 / 1024)
                        
                        # Start new batch if current would exceed size limit
                        if (len(current_batch) >= batch_size or 
                            current_batch_size_mb + write_size_mb > max_batch_size_mb):
                            
                            if current_batch:
                                batches.append(WALSyncBatch(
                                    writes=current_batch,
                                    target_instance=target_instance,
                                    batch_size=len(current_batch),
                                    estimated_memory_mb=current_batch_size_mb
                                ))
                                current_batch = []
                                current_batch_size_mb = 0
                        
                        current_batch.append(write)
                        current_batch_size_mb += write_size_mb
                    
                    # Add final batch
                    if current_batch:
                        batches.append(WALSyncBatch(
                            writes=current_batch,
                            target_instance=target_instance,
                            batch_size=len(current_batch),
                            estimated_memory_mb=current_batch_size_mb
                        ))
                    
                    return batches
                    
        except Exception as e:
            logger.error(f"Error getting batched pending syncs for {target_instance}: {e}")
            return []

    def process_wal_sync_batch(self, batch: WALSyncBatch) -> Tuple[int, int]:
        """Process a batch of WAL syncs with memory-efficient handling"""
        instance = next((inst for inst in self.instances if inst.name == batch.target_instance), None)
        if not instance or not instance.is_healthy:
            return 0, len(batch.writes)
        
        success_count = 0
        start_memory = psutil.virtual_memory().used / 1024 / 1024
        
        logger.info(f"🔄 Processing WAL batch: {batch.batch_size} writes to {batch.target_instance} ({batch.estimated_memory_mb:.1f}MB)")
        
        try:
            for write_record in batch.writes:
                try:
                    # Check memory pressure during processing
                    current_memory = psutil.virtual_memory().used / 1024 / 1024
                    if current_memory > self.max_memory_usage_mb * 0.9:  # 90% threshold
                        logger.warning(f"⚠️ Memory pressure during batch processing: {current_memory:.1f}MB")
                        gc.collect()  # Force garbage collection
                    
                    # Execute the write on target instance
                    write_id = write_record['write_id']
                    method = write_record['method']
                    path = write_record['path']
                    data = write_record['data'] or b''
                    headers = json.loads(write_record['headers']) if write_record['headers'] else {}
                    
                    # Make the sync request
                    response = self.make_direct_request(instance, method, path, data=data, headers=headers)
                    
                    # Mark as synced
                    self.mark_write_synced(write_id)
                    success_count += 1
                    self.stats["successful_syncs"] += 1
                    
                except Exception as e:
                    # Mark as failed
                    self.mark_write_failed(write_record['write_id'], str(e))
                    self.stats["failed_syncs"] += 1
                    logger.debug(f"❌ Failed to sync write {write_record['write_id'][:8]}: {e}")
            
            end_memory = psutil.virtual_memory().used / 1024 / 1024
            memory_delta = end_memory - start_memory
            
            logger.info(f"✅ Batch processed: {success_count}/{batch.batch_size} successful, memory delta: {memory_delta:+.1f}MB")
            
            return success_count, len(batch.writes) - success_count
            
        except Exception as e:
            logger.error(f"Error processing WAL sync batch: {e}")
            return success_count, len(batch.writes) - success_count

    def perform_high_volume_wal_sync(self):
        """Perform high-volume WAL synchronization with parallel processing"""
        try:
            # Calculate optimal batch size based on current conditions
            batch_size = self.calculate_optimal_batch_size()
            
            # Get batches for each instance
            all_batches = []
            for instance in self.instances:
                if instance.is_healthy:
                    batches = self.get_pending_syncs_batched(instance.name, batch_size)
                    all_batches.extend(batches)
            
            if not all_batches:
                return
            
            logger.info(f"🚀 Starting high-volume WAL sync: {len(all_batches)} batches")
            
            total_success = 0
            total_failed = 0
            
            # Process batches in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all batch processing tasks
                future_to_batch = {
                    executor.submit(self.process_wal_sync_batch, batch): batch 
                    for batch in all_batches
                }
                
                # Process completed batches
                for future in as_completed(future_to_batch):
                    batch = future_to_batch[future]
                    try:
                        success, failed = future.result()
                        total_success += success
                        total_failed += failed
                        self.stats["batches_processed"] += 1
                        
                    except Exception as e:
                        logger.error(f"Batch processing failed: {e}")
                        total_failed += len(batch.writes)
            
            logger.info(f"📊 High-volume WAL sync completed: {total_success} success, {total_failed} failed")
            
            # Store resource metrics
            self.store_resource_metrics()
            
        except Exception as e:
            logger.error(f"Error in high-volume WAL sync: {e}")

    def store_resource_metrics(self):
        """Store resource metrics for monitoring"""
        try:
            metrics = self.collect_resource_metrics()
            pending_count = self.get_pending_writes_count()
            
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO wal_resource_metrics 
                        (memory_usage_mb, memory_percent, cpu_percent, pending_writes, active_batches)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        metrics.memory_usage_mb,
                        metrics.memory_percent,
                        metrics.cpu_percent,
                        pending_count,
                        0  # active_batches - could be tracked if needed
                    ))
                    conn.commit()
        except Exception as e:
            logger.debug(f"Failed to store resource metrics: {e}")

    def get_pending_writes_count(self) -> int:
        """Get count of pending writes"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM unified_wal_writes WHERE status = 'executed'")
                    return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting pending writes count: {e}")
            return 0

    def mark_write_synced(self, write_id: str):
        """Mark a write as fully synced"""
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE unified_wal_writes 
                            SET status = %s, synced_at = NOW(), updated_at = NOW()
                            WHERE write_id = %s
                        """, (WALWriteStatus.SYNCED.value, write_id))
                        conn.commit()
        except Exception as e:
            logger.error(f"Error marking write {write_id} as synced: {e}")

    def mark_write_failed(self, write_id: str, error_message: str):
        """Mark a write as failed"""
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE unified_wal_writes 
                            SET status = %s, error_message = %s, retry_count = retry_count + 1, updated_at = NOW()
                            WHERE write_id = %s
                        """, (WALWriteStatus.FAILED.value, error_message, write_id))
                        conn.commit()
        except Exception as e:
            logger.error(f"Error marking write {write_id} as failed: {e}")

    def resource_monitor_loop(self):
        """Monitor resource usage and adjust behavior"""
        while True:
            try:
                metrics = self.collect_resource_metrics()
                self.current_memory_usage = metrics.memory_percent
                
                # Log resource warnings
                if metrics.memory_percent > 85:
                    logger.warning(f"🚨 High memory usage: {metrics.memory_percent:.1f}%")
                
                if metrics.cpu_percent > 80:
                    logger.warning(f"🚨 High CPU usage: {metrics.cpu_percent:.1f}%")
                
                time.sleep(self.resource_check_interval)
                
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                time.sleep(60)

    def wal_sync_loop(self):
        """Main high-volume WAL sync loop"""
        while True:
            try:
                time.sleep(self.sync_interval)
                
                if self.is_syncing:
                    continue
                
                self.is_syncing = True
                self.perform_high_volume_wal_sync()
                self.stats["sync_cycles"] += 1
                
            except Exception as e:
                logger.error(f"Error in high-volume WAL sync loop: {e}")
                time.sleep(60)
            finally:
                self.is_syncing = False

    # Include essential methods from the base implementation
    def extract_collection_identifier(self, path: str) -> Optional[str]:
        """Extract collection identifier from path"""
        if '/collections/' not in path:
            return None
        
        try:
            parts = path.split('/collections/')
            if len(parts) < 2:
                return None
            identifier = parts[1].split('/')[0]
            return identifier if len(identifier) > 5 else None
        except:
            return None

    def make_direct_request(self, instance: ChromaInstance, method: str, path: str, **kwargs) -> requests.Response:
        """Make direct request without WAL logging (used for sync operations)"""
        kwargs['timeout'] = self.request_timeout
        
        try:
            url = f"{instance.url}{path}"
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
            
        except Exception as e:
            logger.warning(f"Direct request to {instance.name} failed: {e}")
            raise e

    def get_primary_instance(self) -> Optional[ChromaInstance]:
        """Get primary instance if healthy"""
        return next((inst for inst in self.instances if inst.name == "primary" and inst.is_healthy), None)

    def get_replica_instance(self) -> Optional[ChromaInstance]:
        """Get replica instance if healthy"""
        return next((inst for inst in self.instances if inst.name == "replica" and inst.is_healthy), None)

    def get_healthy_instances(self) -> List[ChromaInstance]:
        """Get all healthy instances"""
        return [inst for inst in self.instances if inst.is_healthy]

    def health_monitor_loop(self):
        """Health monitoring for instances"""
        while True:
            try:
                for instance in self.instances:
                    try:
                        response = requests.get(f"{instance.url}/api/v2/version", timeout=5)
                        was_healthy = instance.is_healthy
                        instance.is_healthy = response.status_code == 200
                        instance.last_health_check = datetime.now()
                        
                        if instance.is_healthy and not was_healthy:
                            logger.info(f"✅ {instance.name} recovered")
                        elif not instance.is_healthy and was_healthy:
                            logger.warning(f"❌ {instance.name} went down")
                        
                    except Exception as e:
                        was_healthy = instance.is_healthy
                        instance.is_healthy = False
                        if was_healthy:
                            logger.warning(f"❌ {instance.name} health check failed: {e}")
                
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                time.sleep(60)

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status including high-volume metrics"""
        healthy_instances = self.get_healthy_instances()
        pending_count = self.get_pending_writes_count()
        
        return {
            "service": "High-Volume Unified WAL-First ChromaDB Load Balancer",
            "architecture": "WAL-First with High-Volume Processing",
            "healthy_instances": len(healthy_instances),
            "total_instances": len(self.instances),
            "high_volume_config": {
                "max_memory_mb": self.max_memory_usage_mb,
                "max_workers": self.max_workers,
                "default_batch_size": self.default_batch_size,
                "max_batch_size": self.max_batch_size,
                "current_memory_percent": self.current_memory_usage
            },
            "unified_wal": {
                "pending_writes": pending_count,
                "is_syncing": self.is_syncing,
                "sync_interval_seconds": self.sync_interval,
                "database": "PostgreSQL",
                "approach": "High-Volume WAL-First"
            },
            "performance_stats": {
                "batches_processed": self.stats["batches_processed"],
                "memory_pressure_events": self.stats["memory_pressure_events"],
                "adaptive_batch_reductions": self.stats["adaptive_batch_reductions"],
                "successful_syncs": self.stats["successful_syncs"],
                "failed_syncs": self.stats["failed_syncs"]
            },
            "instances": [
                {
                    "name": inst.name,
                    "healthy": inst.is_healthy,
                    "success_rate": f"{inst.get_success_rate():.1f}%",
                    "total_requests": inst.total_requests,
                    "last_health_check": inst.last_health_check.isoformat()
                } for inst in self.instances
            ],
            "stats": self.stats
        }

if __name__ == '__main__':
    # Test high-volume WAL system
    logger.info("🚀 Starting High-Volume Unified WAL Load Balancer")
    
    try:
        hv_wal = HighVolumeUnifiedWAL()
        status = hv_wal.get_status()
        
        logger.info("✅ High-Volume WAL system initialized successfully")
        logger.info(f"📊 Max memory: {status['high_volume_config']['max_memory_mb']}MB")
        logger.info(f"👥 Max workers: {status['high_volume_config']['max_workers']}")
        logger.info(f"📦 Batch size: {status['high_volume_config']['default_batch_size']}-{status['high_volume_config']['max_batch_size']}")
        
    except Exception as e:
        logger.error(f"❌ Failed to start high-volume WAL system: {e}")
        raise 