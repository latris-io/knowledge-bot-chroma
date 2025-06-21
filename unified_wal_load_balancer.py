#!/usr/bin/env python3
"""
Enhanced Unified WAL-First Load Balancer with High-Volume Processing
Combines load balancing and bidirectional sync in a single service with PostgreSQL persistence.

Features:
- WAL-first approach with PostgreSQL persistence
- Batched sync processing with adaptive sizing
- Parallel sync workers with ThreadPoolExecutor
- Memory monitoring and resource optimization
- Bidirectional synchronization
"""

import os
import sys
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

# Flask imports for web service
from flask import Flask, request, Response, jsonify

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
class SyncBatch:
    """Optimized batch for high-volume WAL sync"""
    writes: List[Dict]
    target_instance: str
    batch_size: int
    estimated_memory_mb: float
    priority: int = 0

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

class UnifiedWALLoadBalancer:
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
        self.max_workers = int(os.getenv("MAX_WORKERS", "3"))  # Parallel sync workers
        self.default_batch_size = int(os.getenv("DEFAULT_BATCH_SIZE", "50"))  # WAL sync batch size
        self.max_batch_size = int(os.getenv("MAX_BATCH_SIZE", "200"))
        self.resource_check_interval = 30  # seconds
        
        # PostgreSQL connection for unified WAL
        self.database_url = os.getenv("DATABASE_URL", "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha")
        self.db_lock = threading.Lock()
        
        # Consistency tracking
        self.recent_writes = {}  # collection_id -> timestamp
        self.consistency_window = 30  # 30 seconds
        
        # High-volume sync state
        self.is_syncing = False
        self.current_memory_usage = 0.0
        self.sync_executor = None
        
        # Initialize unified WAL schema
        self._initialize_unified_wal_schema()
        
        # Enhanced statistics
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
            "adaptive_batch_reductions": 0,
            "avg_sync_throughput": 0.0,
            "peak_memory_usage": 0.0,
            "deletion_conversions": 0
        }
        
        # Start monitoring and sync threads
        self.health_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
        self.health_thread.start()
        
        self.resource_thread = threading.Thread(target=self.resource_monitor_loop, daemon=True)
        self.resource_thread.start()
        
        self.wal_sync_thread = threading.Thread(target=self.enhanced_wal_sync_loop, daemon=True)
        self.wal_sync_thread.start()
        
        logger.info(f"🚀 Enhanced Unified WAL Load Balancer initialized")
        logger.info(f"📊 High-volume config: {self.max_memory_usage_mb}MB RAM, {self.max_workers} workers, batch {self.default_batch_size}-{self.max_batch_size}")
        logger.info(f"🎯 Read replica ratio: {self.read_replica_ratio * 100}%")
        logger.info(f"🔄 WAL sync interval: {self.sync_interval}s")

    def get_db_connection(self):
        """Get database connection with improved error handling and retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return psycopg2.connect(
                    self.database_url,
                    connect_timeout=10,
                    application_name='unified-wal-lb'
                )
            except psycopg2.OperationalError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Database connection attempt {attempt + 1} failed, retrying: {e}")
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                    raise e
            except Exception as e:
                logger.error(f"Unexpected database error: {e}")
                raise e

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
                            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            executed_at TIMESTAMP WITH TIME ZONE,
                            synced_at TIMESTAMP WITH TIME ZONE,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            original_data BYTEA,
                            conversion_type VARCHAR(50)
                        );
                    """)
                    
                    # Add high-volume columns if they don't exist (compatible approach)
                    try:
                        # Check and add data_size_bytes column
                        cur.execute("""
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_name = 'unified_wal_writes' AND column_name = 'data_size_bytes';
                        """)
                        if not cur.fetchone():
                            cur.execute("ALTER TABLE unified_wal_writes ADD COLUMN data_size_bytes INTEGER DEFAULT 0;")
                            logger.info("Added data_size_bytes column")
                        
                        # Check and add priority column
                        cur.execute("""
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_name = 'unified_wal_writes' AND column_name = 'priority';
                        """)
                        if not cur.fetchone():
                            cur.execute("ALTER TABLE unified_wal_writes ADD COLUMN priority INTEGER DEFAULT 0;")
                            logger.info("Added priority column")
                            
                    except Exception as e:
                        logger.info(f"Column handling: {e}")
                    
                    # Safe index creation
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_unified_wal_status ON unified_wal_writes(status, timestamp ASC);
                        CREATE INDEX IF NOT EXISTS idx_unified_wal_target_status ON unified_wal_writes(target_instance, status);
                        CREATE INDEX IF NOT EXISTS idx_unified_wal_collection ON unified_wal_writes(collection_id, status);
                    """)
                    
                    # Add priority index only if column exists
                    try:
                        cur.execute("""
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_name = 'unified_wal_writes' AND column_name = 'priority';
                        """)
                        if cur.fetchone():
                            cur.execute("CREATE INDEX IF NOT EXISTS idx_unified_wal_priority ON unified_wal_writes(priority DESC, timestamp ASC);")
                    except Exception as e:
                        logger.info(f"Priority index creation: {e}")
                    
                    # Upgrade recommendations table (for complete scalability)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS upgrade_recommendations (
                            id SERIAL PRIMARY KEY,
                            recommendation_type VARCHAR(50),
                            current_usage REAL,
                            recommended_tier VARCHAR(100),
                            reason TEXT,
                            urgency VARCHAR(20),
                            service_component VARCHAR(50) DEFAULT 'unified-wal',
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        );
                        
                        CREATE INDEX IF NOT EXISTS idx_recommendations_urgency ON upgrade_recommendations(urgency, created_at);
                        CREATE INDEX IF NOT EXISTS idx_recommendations_type ON upgrade_recommendations(recommendation_type, created_at);
                    """)
                    
                    # Performance metrics table for high-volume monitoring
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS wal_performance_metrics (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            memory_usage_mb REAL,
                            memory_percent REAL,
                            cpu_percent REAL,
                            pending_writes INTEGER,
                            batches_processed INTEGER,
                            sync_throughput_per_sec REAL,
                            avg_batch_size INTEGER,
                            memory_pressure_events INTEGER
                        );
                        
                        CREATE INDEX IF NOT EXISTS idx_wal_perf_timestamp ON wal_performance_metrics(timestamp);
                    """)
                    
                    # Cleanup old recommendations (keep for 30 days)
                    cur.execute("""
                        DELETE FROM upgrade_recommendations WHERE created_at < NOW() - INTERVAL '30 days';
                    """)
                    
                    # Collection ID mapping table for distributed system
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS collection_id_mapping (
                            id SERIAL PRIMARY KEY,
                            collection_name VARCHAR(255) UNIQUE NOT NULL,
                            primary_collection_id VARCHAR(255),
                            replica_collection_id VARCHAR(255),
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        );
                        
                        CREATE INDEX IF NOT EXISTS idx_collection_mapping_name ON collection_id_mapping(collection_name);
                        CREATE INDEX IF NOT EXISTS idx_collection_mapping_primary ON collection_id_mapping(primary_collection_id);
                        CREATE INDEX IF NOT EXISTS idx_collection_mapping_replica ON collection_id_mapping(replica_collection_id);
                    """)
                    
                    conn.commit()
                    logger.info("✅ Enhanced Unified WAL PostgreSQL schema initialized (with upgrade notifications)")
                    
        except Exception as e:
            logger.error(f"❌ Failed to initialize enhanced WAL schema: {e}")
            raise

    def collect_resource_metrics(self) -> ResourceMetrics:
        """Collect current resource usage metrics"""
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.1)  # Non-blocking
        
        return ResourceMetrics(
            memory_usage_mb=memory.used / 1024 / 1024,
            memory_percent=memory.percent,
            cpu_percent=cpu_percent,
            timestamp=datetime.now()
        )

    def calculate_optimal_batch_size(self, estimated_total_writes: int = 100) -> int:
        """Calculate optimal WAL sync batch size based on current memory usage and volume"""
        current_memory = psutil.virtual_memory()
        available_memory_mb = (self.max_memory_usage_mb - (current_memory.used / 1024 / 1024))
        
        # Adaptive batch sizing based on memory pressure
        if available_memory_mb < 50:  # Less than 50MB available
            self.stats["memory_pressure_events"] += 1
            batch_size = min(10, self.default_batch_size // 8)  # Very small batches
            logger.warning(f"⚠️ Critical memory pressure, reducing WAL batch size to {batch_size}")
            return batch_size
        elif available_memory_mb < 100:  # Less than 100MB available
            self.stats["adaptive_batch_reductions"] += 1
            batch_size = min(25, self.default_batch_size // 2)  # Small batches
            logger.info(f"📊 Memory pressure detected, reducing batch size to {batch_size}")
            return batch_size
        elif available_memory_mb < 200:  # Less than 200MB available
            return min(self.default_batch_size, estimated_total_writes // 5)
        else:
            # Plenty of memory, use larger batches for efficiency
            return min(self.max_batch_size, max(self.default_batch_size, estimated_total_writes // 3))

    def add_wal_write(self, method: str, path: str, data: bytes, headers: Dict[str, str], 
                     target_instance: TargetInstance, executed_on: Optional[str] = None) -> str:
        """Add write to unified WAL with intelligent deletion handling for ChromaDB ID issues"""
        write_id = str(uuid.uuid4())
        collection_id = self.extract_collection_identifier(path)
        data_size = len(data) if data else 0
        
        # INTELLIGENT DELETION HANDLING FOR CHROMADB ID SYNCHRONIZATION
        converted_data = data
        original_data = None
        conversion_type = None
        
        # Check if this is a POST /delete operation (your ingestion service pattern)
        if method == "POST" and path.endswith('/delete') and data:
            try:
                delete_payload = json.loads(data.decode())
                
                # If deletion uses specific IDs, convert to metadata-based deletion
                if 'ids' in delete_payload and delete_payload['ids']:
                    logger.info(f"🔄 ID-based deletion detected - converting to metadata-based deletion")
                    
                    # Store original for logging
                    original_data = data
                    conversion_type = "id_to_metadata"
                    
                    # Extract collection ID from path to query for metadata
                    collection_uuid = path.split('/collections/')[-1].split('/')[0]
                    
                    # Convert ID-based deletion to metadata-based deletion
                    converted_deletion = self.convert_id_deletion_to_metadata(
                        collection_uuid, delete_payload, executed_on
                    )
                    
                    if converted_deletion:
                        converted_data = json.dumps(converted_deletion).encode()
                        logger.info(f"✅ Converted ID deletion to metadata deletion: {converted_deletion.get('where', {})}")
                    else:
                        logger.warning(f"⚠️ Could not convert ID deletion - using original")
                        converted_data = data
                        conversion_type = None
                        
            except Exception as e:
                logger.warning(f"⚠️ Failed to process deletion conversion: {e}")
                converted_data = data
                conversion_type = None
        
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO unified_wal_writes 
                            (write_id, method, path, data, headers, target_instance, 
                             collection_id, timestamp, executed_on, status, 
                             data_size_bytes, priority, original_data, conversion_type)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s)
                        """, (
                            write_id,
                            method,
                            path,
                            converted_data,  # Use converted data
                            json.dumps(headers) if headers else None,
                            target_instance.value,
                            collection_id,
                            executed_on,
                            WALWriteStatus.EXECUTED.value if executed_on else WALWriteStatus.PENDING.value,
                            data_size,
                            1 if (method == "DELETE" or path.endswith('/delete')) else 0,  # DELETE operations and POST /delete get higher priority
                            original_data,  # Store original for reference
                            conversion_type  # Track conversion type
                        ))
                        conn.commit()
            
            self.stats["total_wal_writes"] += 1
            if conversion_type:
                self.stats["deletion_conversions"] = self.stats.get("deletion_conversions", 0) + 1
                
            logger.info(f"📝 WAL write {write_id[:8]} added ({WALWriteStatus.EXECUTED.value if executed_on else WALWriteStatus.PENDING.value}) for {target_instance.value}")
            
            if conversion_type:
                logger.info(f"🔄 Deletion conversion applied: {conversion_type}")
                
            return write_id
            
        except Exception as e:
            logger.error(f"❌ Failed to add WAL write: {e}")
            raise

    def convert_id_deletion_to_metadata(self, collection_uuid: str, delete_payload: Dict, 
                                       executed_instance: Optional[str]) -> Optional[Dict]:
        """Convert ID-based deletion to metadata-based deletion for ChromaDB compatibility"""
        try:
            if 'ids' not in delete_payload or not delete_payload['ids']:
                return None
            
            chunk_ids = delete_payload['ids']
            logger.info(f"🔍 Converting {len(chunk_ids)} chunk IDs to metadata query")
            
            # Get the instance to query from
            query_instance = None
            if executed_instance == "primary":
                query_instance = self.get_primary_instance()
            elif executed_instance == "replica":
                query_instance = self.get_replica_instance()
            else:
                # Default to primary for metadata extraction
                query_instance = self.get_primary_instance() or self.get_replica_instance()
            
            if not query_instance:
                logger.warning("⚠️ No healthy instance available for metadata extraction")
                return None
            
            # Query the chunks to extract their metadata
            query_url = f"{query_instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}/get"
            query_data = {
                "ids": chunk_ids,
                "include": ["metadatas"]
            }
            
            try:
                response = self.make_direct_request(query_instance, "POST", f"/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}/get", 
                                                   data=json.dumps(query_data).encode(), 
                                                   headers={"Content-Type": "application/json"})
                
                result = response.json()
                metadatas = result.get('metadatas', [])
                
                if not metadatas:
                    logger.warning(f"⚠️ No metadata found for chunk IDs")
                    return None
                
                # Extract document_ids from metadata
                document_ids = set()
                for metadata in metadatas:
                    if metadata and 'document_id' in metadata:
                        document_ids.add(metadata['document_id'])
                
                if not document_ids:
                    logger.warning(f"⚠️ No document_id found in chunk metadata")
                    return None
                
                # Create metadata-based deletion query
                if len(document_ids) == 1:
                    # Single document deletion
                    document_id = list(document_ids)[0]
                    metadata_deletion = {
                        "where": {"document_id": {"$eq": document_id}}
                    }
                    logger.info(f"🎯 Converted to single document deletion: document_id = {document_id}")
                else:
                    # Multiple documents deletion
                    metadata_deletion = {
                        "where": {"document_id": {"$in": list(document_ids)}}
                    }
                    logger.info(f"🎯 Converted to multi-document deletion: {len(document_ids)} documents")
                
                return metadata_deletion
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to query chunk metadata: {e}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Deletion conversion failed: {e}")
            return None

    def get_pending_writes_count(self) -> int:
        """Get count of pending writes for monitoring (high-volume optimized)"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*) FROM unified_wal_writes 
                        WHERE status = 'executed' AND retry_count < 3
                    """)
                    return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting pending writes count: {e}")
            return 0

    def get_pending_syncs_in_batches(self, target_instance: str, batch_size: int) -> List[SyncBatch]:
        """Get pending writes organized into optimized batches for high-volume processing"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Get writes that need to be synced to this instance
                    cur.execute("""
                        SELECT write_id, method, path, data, headers, collection_id, 
                               timestamp, retry_count, data_size_bytes, priority
                        FROM unified_wal_writes 
                        WHERE status = 'executed' 
                        AND (target_instance = 'both' OR 
                             (target_instance = %s AND executed_on != %s) OR
                             (target_instance != %s AND executed_on != %s))
                        AND retry_count < 3
                        ORDER BY priority DESC, timestamp ASC
                        LIMIT %s
                    """, (target_instance, target_instance, target_instance, target_instance, batch_size * 3))
                    
                    all_writes = cur.fetchall()
                    
                    if not all_writes:
                        return []
                    
                    # Create memory-optimized batches
                    batches = []
                    current_batch = []
                    current_batch_size_mb = 0
                    max_batch_size_mb = 30  # 30MB per batch to prevent memory issues
                    
                    for write in all_writes:
                        write_dict = dict(write)  # Convert RealDictRow to dict
                        write_size_mb = (write_dict.get('data_size_bytes', 0) / 1024 / 1024)
                        
                        # Start new batch if current would exceed limits
                        if (len(current_batch) >= batch_size or 
                            current_batch_size_mb + write_size_mb > max_batch_size_mb):
                            
                            if current_batch:
                                batches.append(SyncBatch(
                                    writes=current_batch,
                                    target_instance=target_instance,
                                    batch_size=len(current_batch),
                                    estimated_memory_mb=current_batch_size_mb,
                                    priority=max(w.get('priority', 0) for w in current_batch)
                                ))
                                current_batch = []
                                current_batch_size_mb = 0
                        
                        current_batch.append(write_dict)
                        current_batch_size_mb += write_size_mb
                    
                    # Add final batch
                    if current_batch:
                        batches.append(SyncBatch(
                            writes=current_batch,
                            target_instance=target_instance,
                            batch_size=len(current_batch),
                            estimated_memory_mb=current_batch_size_mb,
                            priority=max(w.get('priority', 0) for w in current_batch)
                        ))
                    
                    # Sort batches by priority (high priority first)
                    batches.sort(key=lambda b: b.priority, reverse=True)
                    
                    return batches
                    
        except Exception as e:
            logger.error(f"Error getting batched pending syncs for {target_instance}: {e}")
            return []

    def process_sync_batch(self, batch: SyncBatch) -> Tuple[int, int]:
        """Process a batch of WAL syncs with optimized error handling"""
        instance = next((inst for inst in self.instances if inst.name == batch.target_instance), None)
        if not instance or not instance.is_healthy:
            return 0, len(batch.writes)
        
        success_count = 0
        start_memory = psutil.virtual_memory().used / 1024 / 1024
        start_time = time.time()
        
        logger.info(f"🔄 Processing sync batch: {batch.batch_size} writes to {batch.target_instance} ({batch.estimated_memory_mb:.1f}MB)")
        
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
                    
                    # Fix headers parsing
                    headers = {}
                    if write_record['headers']:
                        if isinstance(write_record['headers'], str):
                            headers = json.loads(write_record['headers'])
                        else:
                            headers = write_record['headers']
                    
                    # Make the sync request
                    response = self.make_direct_request(instance, method, path, data=data, headers=headers)
                    
                    # CRITICAL: Update collection mapping for successful collection creation on replica
                    if (method == 'POST' and 
                        '/collections' in path and 
                        response.status_code == 200 and 
                        instance.name == 'replica'):
                        try:
                            # Parse response to get replica collection info
                            collection_info = response.json()
                            replica_uuid = collection_info.get('id')
                            collection_name = collection_info.get('name')
                            
                            if replica_uuid and collection_name:
                                # Update mapping with replica UUID
                                with self.db_lock:
                                    with self.get_db_connection() as conn:
                                        with conn.cursor() as cur:
                                            cur.execute("""
                                                UPDATE collection_id_mapping 
                                                SET replica_collection_id = %s, updated_at = NOW()
                                                WHERE collection_name = %s AND replica_collection_id IS NULL
                                            """, (replica_uuid, collection_name))
                                            
                                            if cur.rowcount > 0:
                                                conn.commit()
                                                logger.info(f"✅ Updated collection mapping: {collection_name} -> replica UUID: {replica_uuid[:8]}")
                                            else:
                                                logger.info(f"ℹ️ Collection mapping already exists for {collection_name}")
                                
                        except Exception as mapping_error:
                            logger.error(f"❌ Failed to update collection mapping: {mapping_error}")
                            # Don't fail sync for mapping issues
                    
                    # Mark as synced
                    self.mark_write_synced(write_id)
                    success_count += 1
                    self.stats["successful_syncs"] += 1
                    
                except Exception as e:
                    # Mark as failed with retry increment
                    self.mark_write_failed(write_record['write_id'], str(e))
                    self.stats["failed_syncs"] += 1
                    logger.debug(f"❌ Failed to sync write {write_record['write_id'][:8]}: {e}")
            
            end_memory = psutil.virtual_memory().used / 1024 / 1024
            memory_delta = end_memory - start_memory
            processing_time = time.time() - start_time
            throughput = batch.batch_size / processing_time if processing_time > 0 else 0
            
            # Update throughput stats
            if throughput > 0:
                if self.stats["avg_sync_throughput"] == 0:
                    self.stats["avg_sync_throughput"] = throughput
                else:
                    self.stats["avg_sync_throughput"] = (self.stats["avg_sync_throughput"] + throughput) / 2
            
            logger.info(f"✅ Batch completed: {success_count}/{batch.batch_size} successful, {throughput:.1f} writes/sec, memory delta: {memory_delta:+.1f}MB")
            
            return success_count, len(batch.writes) - success_count
            
        except Exception as e:
            logger.error(f"Error processing sync batch: {e}")
            return success_count, len(batch.writes) - success_count

    def perform_high_volume_sync(self):
        """Perform high-volume WAL synchronization with parallel batch processing"""
        if self.is_syncing:
            return
        
        self.is_syncing = True
        start_time = time.time()
        
        try:
            # Calculate optimal batch size based on current conditions
            pending_count = self.get_pending_writes_count()
            if pending_count == 0:
                return
            
            batch_size = self.calculate_optimal_batch_size(pending_count)
            
            # Get batches for each healthy instance
            all_batches = []
            for instance in self.instances:
                if instance.is_healthy:
                    batches = self.get_pending_syncs_in_batches(instance.name, batch_size)
                    all_batches.extend(batches)
            
            if not all_batches:
                return
            
            logger.info(f"🚀 High-volume sync: {len(all_batches)} batches, {sum(b.batch_size for b in all_batches)} total writes")
            
            total_success = 0
            total_failed = 0
            
            # Process batches in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="WAL-Sync") as executor:
                # Submit all batch processing tasks
                future_to_batch = {
                    executor.submit(self.process_sync_batch, batch): batch 
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
            
            processing_time = time.time() - start_time
            overall_throughput = (total_success + total_failed) / processing_time if processing_time > 0 else 0
            
            logger.info(f"📊 High-volume sync completed: {total_success} success, {total_failed} failed, {overall_throughput:.1f} writes/sec")
            
            # Store performance metrics
            self.store_performance_metrics(total_success, total_failed, len(all_batches))
            
        except Exception as e:
            logger.error(f"Error in high-volume sync: {e}")
        finally:
            self.is_syncing = False

    def store_performance_metrics(self, successful_syncs: int, failed_syncs: int, batches_processed: int):
        """Store detailed performance metrics"""
        try:
            metrics = self.collect_resource_metrics()
            pending_count = self.get_pending_writes_count()
            
            # Track peak memory usage
            if metrics.memory_usage_mb > self.stats["peak_memory_usage"]:
                self.stats["peak_memory_usage"] = metrics.memory_usage_mb
            
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO wal_performance_metrics 
                        (memory_usage_mb, memory_percent, cpu_percent, pending_writes, 
                         batches_processed, sync_throughput_per_sec, avg_batch_size, memory_pressure_events)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        metrics.memory_usage_mb,
                        metrics.memory_percent,
                        metrics.cpu_percent,
                        pending_count,
                        batches_processed,
                        self.stats["avg_sync_throughput"],
                        self.default_batch_size,
                        self.stats["memory_pressure_events"]
                    ))
                    conn.commit()
        except Exception as e:
            logger.debug(f"Failed to store performance metrics: {e}")

    def mark_write_synced(self, write_id: str):
        """Mark a write as fully synced with graceful error handling"""
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
        except psycopg2.OperationalError as e:
            logger.warning(f"Database unavailable, skipping sync status update for {write_id[:8]}: {e}")
            # Continue operation - sync succeeded even if we can't update status
        except Exception as e:
            logger.error(f"Error marking write {write_id[:8]} as synced: {e}")

    def mark_write_failed(self, write_id: str, error_message: str):
        """Mark a write as failed with graceful error handling"""
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE unified_wal_writes 
                            SET status = %s, error_message = %s, retry_count = retry_count + 1, updated_at = NOW()
                            WHERE write_id = %s
                        """, (WALWriteStatus.FAILED.value, error_message[:500], write_id))  # Limit error message length
                        conn.commit()
        except psycopg2.OperationalError as e:
            logger.warning(f"Database unavailable, skipping failure status update for {write_id[:8]}: {e}")
            # Continue operation - failure is already logged
        except Exception as e:
            logger.error(f"Error marking write {write_id[:8]} as failed: {e}")

    def resource_monitor_loop(self):
        """Enhanced resource monitoring with adaptive behavior and upgrade recommendations"""
        while True:
            try:
                metrics = self.collect_resource_metrics()
                self.current_memory_usage = metrics.memory_percent
                
                # Track peak memory usage
                if metrics.memory_usage_mb > self.stats["peak_memory_usage"]:
                    self.stats["peak_memory_usage"] = metrics.memory_usage_mb
                
                # Check for upgrade recommendations
                self.check_upgrade_recommendations(metrics)
                
                # Log resource warnings with thresholds
                if metrics.memory_percent > 90:
                    logger.error(f"🚨 CRITICAL memory usage: {metrics.memory_percent:.1f}%")
                elif metrics.memory_percent > 85:
                    logger.warning(f"⚠️ High memory usage: {metrics.memory_percent:.1f}%")
                
                if metrics.cpu_percent > 90:
                    logger.warning(f"🚨 High CPU usage: {metrics.cpu_percent:.1f}%")
                
                time.sleep(self.resource_check_interval)
                
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                time.sleep(60)

    def check_upgrade_recommendations(self, metrics: ResourceMetrics):
        """Analyze metrics and generate upgrade recommendations (same as data_sync_service)"""
        recommendations = []
        
        # Memory upgrade check
        if metrics.memory_percent > 85:
            recommendations.append({
                'type': 'memory',
                'current': metrics.memory_percent,
                'recommended_tier': 'Standard or Pro Plan',
                'reason': f'Memory usage at {metrics.memory_percent:.1f}% - approaching limit',
                'urgency': 'high' if metrics.memory_percent > 95 else 'medium'
            })
        
        # CPU upgrade check
        if metrics.cpu_percent > 80:
            recommendations.append({
                'type': 'cpu',
                'current': metrics.cpu_percent,
                'recommended_tier': 'Standard or Pro Plan',
                'reason': f'CPU usage at {metrics.cpu_percent:.1f}% - WAL sync performance degraded',
                'urgency': 'high' if metrics.cpu_percent > 95 else 'medium'
            })
        
        # WAL backlog check (unique to WAL system)
        pending_count = self.get_pending_writes_count()
        if pending_count > 1000:
            recommendations.append({
                'type': 'performance',
                'current': pending_count,
                'recommended_tier': 'Standard or Pro Plan',
                'reason': f'WAL backlog at {pending_count} writes - sync falling behind',
                'urgency': 'high' if pending_count > 5000 else 'medium'
            })
        
        # Process recommendations
        for rec in recommendations:
            self.store_upgrade_recommendation(rec)
        
        # Send alerts for urgent recommendations
        urgent_recs = [r for r in recommendations if r['urgency'] == 'high']
        for rec in urgent_recs:
            logger.warning(f"🚨 URGENT: Resource upgrade recommended - {rec['reason']}")
            self.send_slack_upgrade_alert(rec)
        
        # Send Slack for medium priority recommendations (daily limit)
        medium_recs = [r for r in recommendations if r['urgency'] == 'medium']
        if medium_recs:
            self.send_slack_upgrade_alert(medium_recs[0], frequency_limit=True)

    def store_upgrade_recommendation(self, recommendation: dict):
        """Store upgrade recommendation in database"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO upgrade_recommendations
                        (recommendation_type, current_usage, recommended_tier,
                         reason, urgency, service_component)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, [recommendation['type'], recommendation['current'],
                          recommendation['recommended_tier'], recommendation['reason'],
                          recommendation['urgency'], 'unified-wal'])
                    conn.commit()
        except Exception as e:
            logger.debug(f"Failed to store upgrade recommendation: {e}")

    def send_slack_upgrade_alert(self, recommendation: dict, frequency_limit: bool = False):
        """Send Slack notification for upgrade recommendations"""
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            return
        
        try:
            # Check frequency limiting for non-urgent alerts
            if frequency_limit:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        # Check if we've sent this type of alert in the last 24 hours
                        cur.execute("""
                            SELECT COUNT(*) FROM upgrade_recommendations
                            WHERE recommendation_type = %s AND urgency = %s
                            AND created_at > NOW() - INTERVAL '24 hours'
                        """, [recommendation['type'], recommendation['urgency']])
                        
                        recent_count = cur.fetchone()[0]
                        if recent_count > 0:
                            return  # Skip to avoid spam
            
            # Determine alert styling
            urgency = recommendation['urgency']
            emoji = "🚨" if urgency == 'high' else "⚠️"
            color = "#ff0000" if urgency == 'high' else "#ffaa00"
            service_name = f"unified-wal ({recommendation['type']} upgrade needed)"
            
            # Create Slack message
            payload = {
                "text": f"{emoji} ChromaDB Upgrade Needed",
                "attachments": [{
                    "color": color,
                    "title": service_name,
                    "fields": [
                        {"title": "Resource Type", "value": recommendation['type'].title(), "short": True},
                        {"title": "Current Usage", "value": f"{recommendation['current']:.1f}%", "short": True},
                        {"title": "Recommended", "value": recommendation['recommended_tier'], "short": False},
                        {"title": "Reason", "value": recommendation['reason'], "short": False}
                    ],
                    "footer": "ChromaDB Resource Monitoring",
                    "ts": int(datetime.now().timestamp())
                }]
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"📱 Slack upgrade alert sent: {recommendation['type']} {urgency}")
            else:
                logger.warning(f"❌ Slack alert failed: HTTP {response.status_code}")
                
        except Exception as e:
            logger.debug(f"Failed to send Slack notification: {e}")

    def enhanced_wal_sync_loop(self):
        """Enhanced high-volume WAL sync loop with adaptive timing"""
        base_interval = self.sync_interval
        
        while True:
            try:
                # Adaptive sync interval based on pending writes
                pending_count = self.get_pending_writes_count()
                
                if pending_count > 200:
                    sync_interval = max(5, base_interval // 2)  # Faster sync for high volume
                elif pending_count > 50:
                    sync_interval = base_interval
                else:
                    sync_interval = min(30, base_interval * 2)  # Slower sync for low volume
                
                time.sleep(sync_interval)
                
                if pending_count > 0:
                    self.perform_high_volume_sync()
                    self.stats["sync_cycles"] += 1
                
            except Exception as e:
                logger.error(f"Error in high-volume WAL sync loop: {e}")
                time.sleep(60)

    # Essential load balancer methods (keeping original implementation)
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

    def get_healthy_instances(self):
        """Get list of currently healthy instances"""
        return [instance for instance in self.instances if instance.is_healthy]

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
                        instance.update_stats(instance.is_healthy)
                        
                        if instance.is_healthy and not was_healthy:
                            logger.info(f"✅ {instance.name} recovered")
                        elif not instance.is_healthy and was_healthy:
                            logger.warning(f"❌ {instance.name} went down")
                        
                    except Exception as e:
                        was_healthy = instance.is_healthy
                        instance.is_healthy = False
                        instance.update_stats(False)
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
            "service": "Enhanced Unified WAL-First ChromaDB Load Balancer",
            "architecture": "WAL-First with High-Volume Processing",
            "healthy_instances": len(healthy_instances),
            "total_instances": len(self.instances),
            "high_volume_config": {
                "max_memory_mb": self.max_memory_usage_mb,
                "max_workers": self.max_workers,
                "default_batch_size": self.default_batch_size,
                "max_batch_size": self.max_batch_size,
                "current_memory_percent": self.current_memory_usage,
                "peak_memory_usage": self.stats["peak_memory_usage"]
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
                "failed_syncs": self.stats["failed_syncs"],
                "avg_sync_throughput": f"{self.stats['avg_sync_throughput']:.1f} writes/sec",
                "sync_cycles": self.stats["sync_cycles"]
            },
            "instances": [
                {
                    "name": inst.name,
                    "healthy": inst.is_healthy,
                    "success_rate": f"{inst.get_success_rate():.1f}%",
                    "total_requests": inst.total_requests,
                    "consecutive_failures": inst.consecutive_failures,
                    "last_health_check": inst.last_health_check.isoformat()
                } for inst in self.instances
            ],
            "stats": self.stats
        }

    # Keep other essential methods for load balancing functionality
    def choose_read_instance(self, path: str, method: str, headers: Dict[str, str]) -> Optional[ChromaInstance]:
        """Choose instance for read operations"""
        healthy_instances = self.get_healthy_instances()
        if not healthy_instances:
            return None
        
        # For read operations, prefer replica if available
        if method == "GET":
            replica = self.get_replica_instance()
            primary = self.get_primary_instance()
            
            # Use read replica ratio to determine routing
            if replica and primary and random.random() < self.read_replica_ratio:
                return replica
            elif primary:
                return primary
            else:
                return replica
        
        # For write operations, always use primary
        return self.get_primary_instance()

    def normalize_api_path_to_v2(self, path: str) -> str:
        """Convert V1-style API paths to proper V2 format for ChromaDB compatibility"""
        
        # V1 to V2 path conversions
        v1_to_v2_mappings = {
            # Collections endpoints
            "/api/v2/collections": "/api/v2/tenants/default_tenant/databases/default_database/collections",
            "/api/v1/collections": "/api/v2/tenants/default_tenant/databases/default_database/collections",
            
            # Collection-specific endpoints (with dynamic collection ID/name)
            "/api/v2/collections/": "/api/v2/tenants/default_tenant/databases/default_database/collections/",
            "/api/v1/collections/": "/api/v2/tenants/default_tenant/databases/default_database/collections/",
        }
        
        # Direct mapping for exact matches
        if path in v1_to_v2_mappings:
            logger.info(f"🔧 V1→V2 PATH CONVERSION: {path} → {v1_to_v2_mappings[path]}")
            return v1_to_v2_mappings[path]
        
        # Pattern-based conversion for paths with collection IDs/names
        for v1_pattern, v2_pattern in v1_to_v2_mappings.items():
            if path.startswith(v1_pattern) and v1_pattern.endswith("/"):
                # Replace the V1 prefix with V2 prefix, keeping the rest of the path
                converted_path = path.replace(v1_pattern, v2_pattern, 1)
                logger.info(f"🔧 V1→V2 PATH CONVERSION: {path} → {converted_path}")
                return converted_path
        
        # If already V2 format or unknown format, return as-is
        return path

    def resolve_collection_name_to_uuid(self, collection_name: str, target_instance_name: str) -> Optional[str]:
        """Resolve collection name to UUID for the specified instance"""
        try:
            # First try to get UUID from collection mapping database
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    if target_instance_name == "primary":
                        cur.execute("""
                            SELECT primary_collection_id FROM collection_id_mapping 
                            WHERE collection_name = %s AND primary_collection_id IS NOT NULL
                        """, (collection_name,))
                    else:  # replica
                        cur.execute("""
                            SELECT replica_collection_id FROM collection_id_mapping 
                            WHERE collection_name = %s AND replica_collection_id IS NOT NULL
                        """, (collection_name,))
                    
                    result = cur.fetchone()
                    if result and result[0]:
                        logger.info(f"✅ Resolved {collection_name} -> {result[0][:8]}... via mapping for {target_instance_name}")
                        return result[0]
            
            # Fallback: Query the instance directly to get UUID by name
            instance = next((inst for inst in self.instances if inst.name == target_instance_name and inst.is_healthy), None)
            if not instance:
                logger.warning(f"❌ No healthy {target_instance_name} instance for UUID resolution")
                return None
            
            logger.info(f"🔍 Fallback: Querying {target_instance_name} instance directly for {collection_name}")
            response = self.make_direct_request(
                instance, 
                "GET", 
                "/api/v2/tenants/default_tenant/databases/default_database/collections"
            )
            
            if response.status_code == 200:
                collections = response.json()
                for collection in collections:
                    if collection.get('name') == collection_name:
                        uuid = collection.get('id')
                        logger.info(f"✅ Resolved {collection_name} -> {uuid[:8]}... via direct query on {target_instance_name}")
                        
                        # Update mapping database for future use
                        try:
                            with self.get_db_connection() as conn:
                                with conn.cursor() as cur:
                                    if target_instance_name == "primary":
                                        cur.execute("""
                                            UPDATE collection_id_mapping 
                                            SET primary_collection_id = %s, updated_at = NOW()
                                            WHERE collection_name = %s
                                        """, (uuid, collection_name))
                                    else:  # replica
                                        cur.execute("""
                                            UPDATE collection_id_mapping 
                                            SET replica_collection_id = %s, updated_at = NOW()
                                            WHERE collection_name = %s
                                        """, (uuid, collection_name))
                                    conn.commit()
                                    logger.info(f"✅ Updated mapping database with {target_instance_name} UUID")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to update mapping: {e}")
                        
                        return uuid
            
            logger.warning(f"❌ Collection {collection_name} not found on {target_instance_name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ UUID resolution failed for {collection_name} on {target_instance_name}: {e}")
            return None

# Main execution for web service  
if __name__ == '__main__':
    logger.info("🚀 Starting Enhanced Unified WAL Load Balancer with High-Volume Support")
    logger.info("🔧 DEPLOYMENT TRIGGER: Debug logging enabled - v2.1")  # Force redeploy
    
    # Initialize Flask app first
    app = Flask(__name__)
    enhanced_wal = None
    
    try:
        enhanced_wal = UnifiedWALLoadBalancer()
        logger.info("✅ Enhanced WAL system initialized successfully")
        
        # Start background threads
        threading.Thread(target=enhanced_wal.enhanced_wal_sync_loop, daemon=True).start()
        threading.Thread(target=enhanced_wal.health_monitor_loop, daemon=True).start()
        threading.Thread(target=enhanced_wal.resource_monitor_loop, daemon=True).start()
        
    except Exception as e:
        logger.error(f"❌ WAL system initialization failed: {e}")
        # Continue with Flask app even if WAL fails initially
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint"""
        try:
            if enhanced_wal is None:
                return jsonify({"status": "initializing", "message": "WAL system starting up"}), 503
                
            status = enhanced_wal.get_status()
            healthy_instances = status['healthy_instances']
            total_instances = status['total_instances']
            
            return jsonify({
                "status": "healthy" if healthy_instances > 0 else "degraded",
                "healthy_instances": f"{healthy_instances}/{total_instances}",
                "service": "Enhanced Unified WAL Load Balancer",
                "architecture": status.get('architecture', 'WAL-First'),
                "pending_writes": status.get('unified_wal', {}).get('pending_writes', 0)
            }), 200 if healthy_instances > 0 else 503
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500
    
    @app.route('/status', methods=['GET'])
    def get_status():
        """Detailed status endpoint"""
        try:
            if enhanced_wal is None:
                return jsonify({"status": "initializing"}), 503
            return jsonify(enhanced_wal.get_status()), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/wal/status', methods=['GET'])
    def wal_status():
        """WAL-specific status endpoint"""
        try:
            if enhanced_wal is None:
                return jsonify({"status": "initializing"}), 503
            status = enhanced_wal.get_status()
            return jsonify({
                "wal_system": status.get('unified_wal', {}),
                "performance_stats": status.get('performance_stats', {}),
                "high_volume_config": status.get('high_volume_config', {})
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/metrics', methods=['GET'])
    def metrics():
        """Resource metrics endpoint"""
        try:
            if enhanced_wal is None:
                return jsonify({"status": "initializing"}), 503
            metrics = enhanced_wal.collect_resource_metrics()
            return jsonify({
                "memory_usage_mb": metrics.memory_usage_mb,
                "memory_percent": metrics.memory_percent,
                "cpu_percent": metrics.cpu_percent,
                "timestamp": metrics.timestamp.isoformat(),
                "peak_memory_usage": enhanced_wal.stats.get("peak_memory_usage", 0)
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/admin/test_wal', methods=['POST'])
    def test_wal():
        """Admin endpoint to test WAL logging directly"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not ready"}), 503
            
            # Test WAL logging
            test_data = request.get_json() or {"test": "data"}
            
            # Use string-to-enum pattern like proxy_request
            sync_target_enum = TargetInstance.REPLICA
            
            write_id = enhanced_wal.add_wal_write(
                method="POST",
                path="/test/path",
                data=json.dumps(test_data).encode(),
                headers={'Content-Type': 'application/json'},
                target_instance=sync_target_enum,
                executed_on="primary"
            )
            
            return jsonify({
                "success": True,
                "write_id": write_id,
                "message": "WAL write created successfully"
            }), 200
            
        except Exception as e:
            import traceback
            return jsonify({
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500
    
    @app.route('/admin/wal_count', methods=['GET'])
    def wal_count():
        """Admin endpoint to check WAL count directly"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not ready"}), 503
            
            count = enhanced_wal.get_pending_writes_count()
            
            return jsonify({
                "pending_writes": count,
                "wal_system_ready": True
            }), 200
            
        except Exception as e:
            import traceback
            return jsonify({
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500
    
    @app.route('/admin/collection_mappings', methods=['GET'])
    def collection_mappings():
        """Admin endpoint to check collection mappings for distributed system"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not ready"}), 503
            
            with enhanced_wal.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT collection_name, primary_collection_id, replica_collection_id, 
                               created_at, updated_at
                        FROM collection_id_mapping 
                        ORDER BY created_at DESC
                        LIMIT 20
                    """)
                    
                    mappings = []
                    for row in cur.fetchall():
                        mappings.append({
                            "collection_name": row[0],
                            "primary_uuid": row[1][:8] + "..." if row[1] else None,
                            "replica_uuid": row[2][:8] + "..." if row[2] else None,
                            "created_at": row[3].isoformat() if row[3] else None,
                            "updated_at": row[4].isoformat() if row[4] else None,
                            "status": "complete" if row[1] and row[2] else "partial"
                        })
            
            return jsonify({
                "collection_mappings": mappings,
                "total_mappings": len(mappings)
            }), 200
            
        except Exception as e:
            import traceback
            return jsonify({
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500
    
    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def proxy_request(path):
        """Streamlined proxy with essential WAL logging for distributed system"""
        try:
            logger.info(f"🚀 PROXY_REQUEST START: {request.method} /{path}")
            
            if enhanced_wal is None:
                logger.error("❌ PROXY_REQUEST FAILED: WAL system not ready")
                return jsonify({"error": "WAL system not ready"}), 503
                
            logger.info(f"✅ PROXY_REQUEST: enhanced_wal object exists")
            logger.info(f"Forwarding {request.method} request to /{path}")
            
            # Get target instance using existing health-based routing
            logger.info(f"🔍 PROXY_REQUEST: Getting target instance...")
            target_instance = enhanced_wal.choose_read_instance(f"/{path}", request.method, {})
            if not target_instance:
                logger.error(f"❌ PROXY_REQUEST: No healthy instances available")
                return jsonify({"error": "No healthy instances available"}), 503
            
            logger.info(f"✅ PROXY_REQUEST: Target instance selected: {target_instance.name}")
            
            # Convert API path for ChromaDB compatibility
            normalized_path = enhanced_wal.normalize_api_path_to_v2(f"/{path}")
            
            # CRITICAL: Collection name-to-UUID resolution for document operations
            original_path = normalized_path
            if '/collections/' in normalized_path and any(doc_op in normalized_path for doc_op in ['/add', '/upsert', '/get', '/query', '/update', '/delete']):
                # Extract collection name from path
                path_parts = normalized_path.split('/collections/')
                if len(path_parts) > 1:
                    collection_part = path_parts[1].split('/')[0]
                    # Check if it's a name (not UUID) - UUIDs have specific format
                    import re
                    if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', collection_part):
                        logger.info(f"🔍 PROXY_REQUEST: Detected collection name '{collection_part}' in document operation")
                        
                        # Resolve collection name to UUID for target instance
                        resolved_uuid = enhanced_wal.resolve_collection_name_to_uuid(collection_part, target_instance.name)
                        if resolved_uuid:
                            # Replace collection name with UUID in path
                            normalized_path = normalized_path.replace(f'/collections/{collection_part}/', f'/collections/{resolved_uuid}/')
                            logger.info(f"✅ PROXY_REQUEST: Resolved path: {original_path} -> {normalized_path}")
                        else:
                            logger.warning(f"⚠️ PROXY_REQUEST: Could not resolve collection name '{collection_part}' to UUID")
                            return jsonify({"error": f"Collection '{collection_part}' not found"}), 404
            
            url = f"{target_instance.url}{normalized_path}"
            logger.info(f"✅ PROXY_REQUEST: URL constructed: {url}")
            
            # Get request data
            data = request.get_data() if request.method in ['POST', 'PUT', 'PATCH'] else None
            logger.info(f"✅ PROXY_REQUEST: Request data size: {len(data) if data else 0} bytes")
            
            # CRITICAL: WAL logging for write operations (restores auto-mapping)
            logger.info(f"🔍 PROXY_REQUEST: Checking if write operation: {request.method}")
            if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
                logger.info(f"🎯 PROXY_REQUEST: WRITE OPERATION DETECTED - Starting WAL logging")
                try:
                    logger.info(f"🔍 WAL logging check: method={request.method}, target={target_instance.name}")
                    
                    # Determine sync target for distributed system (using string values)
                    logger.info(f"🔍 PROXY_REQUEST: Determining sync target...")
                    if target_instance.name == "primary":
                        sync_target_value = "replica"  # Sync to replica
                        logger.info(f"✅ PROXY_REQUEST: Primary target -> sync to replica")
                    else:
                        sync_target_value = "primary"  # Sync to primary
                        logger.info(f"✅ PROXY_REQUEST: Replica target -> sync to primary")
                    
                    # Special handling for DELETE operations (bidirectional sync)
                    if request.method == "DELETE":
                        sync_target_value = "both"  # Sync to both instances
                        logger.info(f"✅ PROXY_REQUEST: DELETE operation -> sync to both")
                    
                    logger.info(f"🎯 Sync target determined: {sync_target_value}")
                    
                    # SIMPLIFIED WAL LOGGING - bypassing complex add_wal_write method
                    logger.info(f"🔍 PROXY_REQUEST: Starting SIMPLIFIED WAL logging...")
                    try:
                        import uuid
                        write_id = str(uuid.uuid4())
                        logger.info(f"✅ PROXY_REQUEST: Generated write_id: {write_id[:8]}")
                        
                        logger.info(f"🔍 PROXY_REQUEST: Extracting collection identifier...")
                        collection_id = enhanced_wal.extract_collection_identifier(normalized_path)
                        logger.info(f"✅ PROXY_REQUEST: Collection ID: {collection_id}")
                        
                        # Direct database insert without complex logic
                        logger.info(f"🔍 PROXY_REQUEST: Acquiring database lock...")
                        with enhanced_wal.db_lock:
                            logger.info(f"✅ PROXY_REQUEST: Database lock acquired")
                            
                            logger.info(f"🔍 PROXY_REQUEST: Getting database connection...")
                            with enhanced_wal.get_db_connection() as conn:
                                logger.info(f"✅ PROXY_REQUEST: Database connection established")
                                
                                logger.info(f"🔍 PROXY_REQUEST: Creating cursor...")
                                with conn.cursor() as cur:
                                    logger.info(f"✅ PROXY_REQUEST: Cursor created")
                                    
                                    logger.info(f"🔍 PROXY_REQUEST: Executing WAL insert SQL...")
                                    cur.execute("""
                                        INSERT INTO unified_wal_writes 
                                        (write_id, method, path, data, headers, target_instance, 
                                         collection_id, timestamp, executed_on, status, data_size_bytes, priority)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
                                    """, (
                                        write_id,
                                        request.method,
                                        normalized_path,
                                        data or b'',
                                        '{"Content-Type": "application/json"}',
                                        sync_target_value,
                                        collection_id,
                                        target_instance.name,
                                        'executed',
                                        len(data) if data else 0,
                                        1 if request.method == 'DELETE' else 0
                                    ))
                                    logger.info(f"✅ PROXY_REQUEST: SQL executed successfully")
                                    
                                    logger.info(f"🔍 PROXY_REQUEST: Committing transaction...")
                                    conn.commit()
                                    logger.info(f"✅ PROXY_REQUEST: Transaction committed")
                        
                        logger.info(f"✅ SIMPLIFIED WAL logged: write_id={write_id[:8]}, method={request.method}, target={sync_target_value}")
                        
                    except Exception as simple_wal_error:
                        logger.error(f"❌ SIMPLIFIED WAL logging failed: {simple_wal_error}")
                        import traceback
                        logger.error(f"Simplified WAL traceback: {traceback.format_exc()}")
                    
                except Exception as wal_error:
                    import traceback
                    logger.error(f"❌ WAL logging failed: {wal_error}")
                    logger.error(f"WAL error traceback: {traceback.format_exc()}")
                    # Continue anyway - don't fail request for WAL issues
            else:
                logger.info(f"ℹ️ PROXY_REQUEST: READ OPERATION - No WAL logging needed")
            
            # Make request with proven working approach
            logger.info(f"🔍 PROXY_REQUEST: Making HTTP request to target...")
            import requests
            response = requests.request(
                method=request.method,
                url=url,
                headers={'Content-Type': 'application/json'} if data else {},
                data=data,
                timeout=10
            )
            
            logger.info(f"✅ PROXY_REQUEST: HTTP response received: {response.status_code}")
            logger.info(f"Response: {response.status_code}, Content: {response.text[:100]}")
            
            # CRITICAL: Create collection mapping for distributed UUID tracking
            if (request.method == 'POST' and 
                '/collections' in normalized_path and 
                response.status_code == 200 and 
                data):
                try:
                    logger.info(f"🔍 PROXY_REQUEST: Creating collection mapping for distributed system...")
                    
                    # Parse response to get collection info
                    collection_info = response.json()
                    collection_name = collection_info.get('name')
                    primary_uuid = collection_info.get('id')
                    
                    if collection_name and primary_uuid:
                        logger.info(f"✅ PROXY_REQUEST: Collection created - name: {collection_name}, UUID: {primary_uuid[:8]}")
                        
                        # Store collection mapping in database for distributed system
                        with enhanced_wal.db_lock:
                            with enhanced_wal.get_db_connection() as conn:
                                with conn.cursor() as cur:
                                    # Check if mapping already exists
                                    cur.execute("""
                                        SELECT collection_name FROM collection_id_mapping 
                                        WHERE collection_name = %s
                                    """, (collection_name,))
                                    
                                    if not cur.fetchone():
                                        # Create new mapping entry (replica UUID will be filled by WAL sync)
                                        cur.execute("""
                                            INSERT INTO collection_id_mapping 
                                            (collection_name, primary_collection_id, replica_collection_id, created_at)
                                            VALUES (%s, %s, NULL, NOW())
                                            ON CONFLICT (collection_name) DO UPDATE SET
                                            primary_collection_id = EXCLUDED.primary_collection_id,
                                            updated_at = NOW()
                                        """, (collection_name, primary_uuid))
                                        conn.commit()
                                        
                                        logger.info(f"✅ PROXY_REQUEST: Collection mapping created for {collection_name}")
                                    else:
                                        logger.info(f"ℹ️ PROXY_REQUEST: Collection mapping already exists for {collection_name}")
                        
                except Exception as mapping_error:
                    logger.error(f"❌ PROXY_REQUEST: Collection mapping failed: {mapping_error}")
                    # Don't fail the request for mapping issues
            
            # Return response with working JSON handling
            logger.info(f"✅ PROXY_REQUEST: Returning response to client")
            return Response(
                response.text,
                status=response.status_code,
                mimetype='application/json'
            )
            
        except Exception as e:
            import traceback
            logger.error(f"❌ PROXY_REQUEST FAILED for {request.method} /{path}: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return jsonify({"error": f"Service temporarily unavailable: {str(e)}"}), 503
    
    # Start Flask web server immediately
    port = int(os.getenv('PORT', 8000))
    logger.info(f"🌐 Starting Flask web server on port {port}")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"❌ Flask server failed to start: {e}")
        sys.exit(1) 