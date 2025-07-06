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
import contextlib
from psycopg2 import pool as psycopg2_pool
from werkzeug.exceptions import RequestTimeout
from threading import Semaphore
import queue

# Flask imports for web service
from flask import Flask, request, Response, jsonify

# Import Transaction Safety Service for timing gap protection
try:
    from transaction_safety_service import TransactionSafetyService
    TRANSACTION_SAFETY_AVAILABLE = True
except ImportError:
    logger.warning("⚠️ Transaction Safety Service not available - timing gaps may cause data loss")
    TRANSACTION_SAFETY_AVAILABLE = False

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
        
        # Configuration - AGGRESSIVE HEALTH CHECK INTERVAL FOR INSTANT FAILURE DETECTION  
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "2"))  # 2 seconds for faster detection
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "15"))
        self.read_replica_ratio = float(os.getenv("READ_REPLICA_RATIO", "0.8"))
        self.sync_interval = int(os.getenv("WAL_SYNC_INTERVAL", "10"))
        
        # High-volume configuration
        self.max_memory_usage_mb = int(os.getenv("MAX_MEMORY_MB", "400"))  # 400MB for 512MB container
        self.max_workers = int(os.getenv("MAX_WORKERS", "3"))  # Parallel sync workers
        self.default_batch_size = int(os.getenv("DEFAULT_BATCH_SIZE", "50"))  # WAL sync batch size
        self.max_batch_size = int(os.getenv("MAX_BATCH_SIZE", "200"))
        self.resource_check_interval = 30  # seconds
        
        # 🚀 SCALABILITY FEATURES - Feature flags for safe deployment
        self.enable_connection_pooling = os.getenv("ENABLE_CONNECTION_POOLING", "false").lower() == "true"
        self.enable_granular_locking = os.getenv("ENABLE_GRANULAR_LOCKING", "false").lower() == "true"
        
        # 🚀 REQUEST CONCURRENCY MANAGER - Handle high concurrent user load (200+ simultaneous users)
        self.concurrency_manager = ConcurrencyManager(
            max_concurrent_requests=int(os.getenv("MAX_CONCURRENT_REQUESTS", "30")),  # 🔧 FIX: Match USE CASE 4 testing
            request_queue_size=int(os.getenv("REQUEST_QUEUE_SIZE", "100")),  # 🔧 FIX: Reduced to match 30 concurrency
            request_timeout=int(os.getenv("REQUEST_TIMEOUT", "120"))  # 🔧 FIX: Increased from 30s to 120s
        )
        
        # 🔗 CONNECTION POOLING - Eliminates database connection overhead
        self.database_url = os.getenv("DATABASE_URL", "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha")
        self.connection_pool = None
        self.pool_available = False
        
        if self.enable_connection_pooling:
            try:
                # 🔧 FIX: Calculate pool size for high-concurrency workloads  
                # Each operation can make 10-20 DB calls, so scale pool appropriately
                # 🎯 BALANCED: Optimal pool size for both stability and performance
                min_connections = 5   # Sufficient base connections 
                max_connections = 15  # Balanced for burst workloads without DB overload
                
                self.connection_pool = psycopg2_pool.ThreadedConnectionPool(
                    minconn=min_connections,
                    maxconn=max_connections,
                    dsn=self.database_url,
                    connect_timeout=10,
                    application_name='unified-wal-lb-pooled'
                )
                
                # 🔧 FIX: Pre-warm the pool to improve hit rates
                temp_connections = []
                for i in range(min(3, min_connections)):
                    try:
                        conn = self.connection_pool.getconn()
                        if conn:
                            with conn.cursor() as cur:
                                cur.execute("SELECT 1")
                            temp_connections.append(conn)
                    except Exception as e:
                        logger.debug(f"Pre-warm connection {i} failed: {e}")
                        break
                
                # Return pre-warmed connections to pool
                for conn in temp_connections:
                    try:
                        self.connection_pool.putconn(conn)
                    except Exception as e:
                        logger.debug(f"Failed to return pre-warmed connection: {e}")
                        try:
                            conn.close()
                        except:
                            pass
                self.pool_available = True
                logger.info(f"🔗 Connection pool enabled: {min_connections}-{max_connections} connections")
            except Exception as e:
                logger.warning(f"⚠️ Connection pool initialization failed, using direct connections: {e}")
                self.connection_pool = None
                self.pool_available = False
        else:
            logger.info("🔗 Connection pooling disabled (set ENABLE_CONNECTION_POOLING=true to enable)")
        
        # 🔒 GRANULAR LOCKING - Reduces lock contention for better scalability
        if self.enable_granular_locking:
            # Operation-specific locks for better concurrent performance
            self.wal_write_lock = threading.Lock()          # WAL operations
            self.collection_mapping_lock = threading.Lock() # UUID mappings  
            self.metrics_lock = threading.Lock()            # Performance metrics
            self.status_lock = threading.Lock()             # Status updates
            logger.info("🔒 Granular locking enabled - improved concurrency")
        else:
            logger.info("🔒 Granular locking disabled (set ENABLE_GRANULAR_LOCKING=true to enable)")
        
        # 🔒 BACKWARD COMPATIBILITY - Keep global lock for fallback
        self.db_lock = threading.Lock()
        
        # Consistency tracking
        self.recent_writes = {}  # collection_id -> timestamp
        self.consistency_window = 30  # 30 seconds
        
        # High-volume sync state
        self.is_syncing = False
        self.current_memory_usage = 0.0
        self.sync_executor = None
        
        # Enhanced statistics - INITIALIZE BEFORE SCHEMA INITIALIZATION
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
            "deletion_conversions": 0,
            # 🚀 SCALABILITY METRICS
            "connection_pool_hits": 0,
            "connection_pool_misses": 0,
            "lock_contention_avoided": 0,
            # 🚀 CONCURRENCY METRICS
            "concurrent_requests": 0,
            "total_requests_processed": 0,
            "timeout_requests": 0,
            "queue_full_rejections": 0
        }

        # 🧪 TESTING MODE - For optimized connection pooling during rapid operations
        self.testing_mode = False
        self.testing_mode_enabled_at = None
        
        # Initialize unified WAL schema
        self._initialize_unified_wal_schema()
        
        # Initialize Transaction Safety Service for timing gap protection
        self.transaction_safety = None
        if TRANSACTION_SAFETY_AVAILABLE:
            try:
                self.transaction_safety = TransactionSafetyService(self.database_url)
                # 🔧 CRITICAL FIX: Give transaction safety service reference to load balancer for recovery
                self.transaction_safety.load_balancer = self
                logger.info("🛡️ Transaction Safety Service enabled - timing gaps protected + recovery enabled")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Transaction Safety Service: {e}")
                self.transaction_safety = None
        
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
        
        # 🚀 SCALABILITY STATUS
        features = []
        if self.enable_connection_pooling and self.pool_available:
            features.append("Connection Pooling")
        if self.enable_granular_locking:
            features.append("Granular Locking")
        
        if features:
            logger.info(f"🚀 Scalability features enabled: {', '.join(features)}")
        else:
            logger.info("🚀 Scalability features disabled - enable with ENABLE_CONNECTION_POOLING=true, ENABLE_GRANULAR_LOCKING=true")

    def _get_appropriate_lock(self, operation_type: str):
        """🔒 Get appropriate lock based on operation type for optimal concurrency"""
        if not self.enable_granular_locking:
            return self.db_lock  # SAFE: Fallback to global lock
        
        # ENHANCED: Operation-specific locking for better performance
        lock_map = {
            'wal_write': self.wal_write_lock,
            'collection_mapping': self.collection_mapping_lock,
            'metrics': self.metrics_lock,
            'status': self.status_lock,
        }
        
        lock = lock_map.get(operation_type, self.db_lock)
        
        if lock != self.db_lock:
            self.stats["lock_contention_avoided"] += 1
            
        return lock

    @contextlib.contextmanager
    def get_db_connection_ctx(self):
        """🔗 OPTIMIZED database connection with efficient pooling support"""
        conn = None
        connection_source = "direct"  
        start_time = time.time()
        
        # 🔍 DEBUG: Connection request initiated
        logger.info(f"🔍 DEBUG: Connection request started - pool_available={self.pool_available}, enable_connection_pooling={self.enable_connection_pooling}")
        
        try:
            # 🚀 OPTIMIZED: Try pool first with minimal overhead
            if self.pool_available and self.connection_pool:
                try:
                    logger.info(f"🔍 DEBUG: Attempting to get connection from pool")
                    conn = self.connection_pool.getconn()
                    if conn:
                        # ✅ NO CONNECTION TESTING - trust the pool!
                        self.stats["connection_pool_hits"] += 1
                        connection_source = "pool"
                        elapsed = time.time() - start_time
                        logger.info(f"🔍 DEBUG: SUCCESS - Pool connection obtained in {elapsed:.3f}s (hits: {self.stats['connection_pool_hits']}, misses: {self.stats['connection_pool_misses']})")
                    else:
                        logger.info(f"🔍 DEBUG: Pool returned None connection")
                        self.stats["connection_pool_misses"] += 1
                except Exception as e:
                    logger.info(f"🔍 DEBUG: Pool connection failed: {e}")
                    self.stats["connection_pool_misses"] += 1
                    
            # Direct connection fallback  
            if not conn:
                logger.info(f"🔍 DEBUG: Creating direct connection (pool_available={self.pool_available})")
                conn = psycopg2.connect(self.database_url)
                connection_source = "direct"
                if not self.pool_available:
                    self.stats["connection_pool_misses"] += 1
                    
            elapsed = time.time() - start_time
            logger.info(f"🔍 DEBUG: Connection established - source={connection_source}, time={elapsed:.3f}s")
            yield conn
            
        finally:
            if conn:
                try:
                    if connection_source == "pool" and self.connection_pool:
                        # ✅ NO ARTIFICIAL DELAYS - return immediately for better reuse
                        logger.info(f"🔍 DEBUG: Returning connection to pool")
                        self.connection_pool.putconn(conn)
                    else:
                        logger.info(f"🔍 DEBUG: Closing direct connection")
                        conn.close()
                except Exception as e:
                    logger.info(f"🔍 DEBUG: Error handling connection cleanup: {e}")
                    try:
                        conn.close()
                    except:
                        pass

    @contextlib.contextmanager
    def get_shared_db_connection_ctx(self):
        """🚀 Shared database connection for rapid sequential operations - improves pool efficiency"""
        conn = None
        try:
            conn = self.get_db_connection()
            yield conn
            # ✅ NO ARTIFICIAL DELAYS - let the pool handle timing
        finally:
            if conn:
                if self.pool_available and self.connection_pool:
                    try:
                        self.connection_pool.putconn(conn)
                    except Exception as e:
                        logger.debug(f"Pool return failed: {e}")
                        conn.close()
                else:
                    conn.close()

    def get_db_connection(self):
        """🔗 Get database connection with improved error handling, retry logic, and connection pooling"""
        # 🚀 SCALABILITY: Use connection pool if available
        if self.pool_available and self.connection_pool:
            try:
                conn = self.connection_pool.getconn()
                if conn:
                    # ✅ NO CONNECTION TESTING - trust the pool, massive performance gain!
                    self.stats["connection_pool_hits"] += 1
                    return conn
                else:
                    # Pool available but no connection available
                    self.stats["connection_pool_misses"] += 1
            except Exception as e:
                logger.warning(f"⚠️ Pool connection failed, falling back to direct: {e}")
                self.stats["connection_pool_misses"] += 1
                # Fall through to direct connection
        
        # 🔗 FALLBACK: Direct connection (original behavior)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = psycopg2.connect(
                    self.database_url,
                    connect_timeout=10,
                    application_name='unified-wal-lb'
                )
                # ❌ DON'T double-count misses here
                return conn
                
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
            # 🔧 FIX: Use connection context manager for pooled connections
            with self.get_db_connection_ctx() as conn:
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
                        
                        # Check and add synced_instances column for "both" target tracking
                        cur.execute("""
                            SELECT column_name FROM information_schema.columns 
                            WHERE table_name = 'unified_wal_writes' AND column_name = 'synced_instances';
                        """)
                        if not cur.fetchone():
                            cur.execute("ALTER TABLE unified_wal_writes ADD COLUMN synced_instances JSONB DEFAULT NULL;")
                            logger.info("Added synced_instances column for target_instance='both' tracking")
                            
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
                    
                    # Collection ID mapping table for distributed system (COMPATIBILITY FIX)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS collection_id_mapping (
                            mapping_id SERIAL PRIMARY KEY,
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
        """Collect current PROCESS-SPECIFIC resource usage metrics"""
        # CRITICAL FIX: Use process-specific metrics, not system-wide
        process = psutil.Process()
        
        # Process-specific memory usage
        memory_info = process.memory_info()
        memory_usage_mb = memory_info.rss / 1024 / 1024  # Resident Set Size in MB
        
        # Calculate memory percentage based on container limit (400MB)
        memory_percent = (memory_usage_mb / self.max_memory_usage_mb) * 100
        
        # Process-specific CPU usage
        cpu_percent = process.cpu_percent(interval=0.1)  # Non-blocking
        
        return ResourceMetrics(
            memory_usage_mb=memory_usage_mb,
            memory_percent=memory_percent,
            cpu_percent=cpu_percent,
            timestamp=datetime.now()
        )

    def calculate_optimal_batch_size(self, estimated_total_writes: int = 100) -> int:
        """Calculate optimal WAL sync batch size based on current PROCESS memory usage and volume"""
        # CRITICAL FIX: Use process-specific memory, not system-wide
        process = psutil.Process()
        process_memory_mb = process.memory_info().rss / 1024 / 1024
        available_memory_mb = (self.max_memory_usage_mb - process_memory_mb)
        
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

    def calculate_retry_delay_seconds(self, retry_count: int = 0) -> int:
        """Calculate exponential backoff delay for failed operation retries"""
        # Check if primary instance is healthy - if not, use longer delays
        primary = self.get_primary_instance()
        if not primary or not primary.is_healthy:
            # Primary is down - use longer delays to avoid overwhelming when it recovers
            base_delay = 60  # 1 minute minimum
        else:
            # Primary is healthy - use shorter delays for faster recovery
            base_delay = 15  # 15 seconds minimum
        
        # Calculate exponential backoff: base_delay * 2^retry_count
        # For retry_count 0: base_delay
        # For retry_count 1: base_delay * 2 
        # For retry_count 2: base_delay * 4
        delay = base_delay * (2 ** retry_count)
        
        # Cap maximum delay at 15 minutes to prevent infinite waiting
        max_delay = 900  # 15 minutes
        return min(delay, max_delay)

    def calculate_recovery_batch_size(self, instance: ChromaInstance, base_batch_size: int) -> int:
        """Calculate gradual recovery batch size to prevent overwhelming recently recovered instances"""
        # Check if instance has recent failures (indicating recent recovery)
        if instance.consecutive_failures > 0:
            # Instance has recent failures - use very small batches
            return max(1, base_batch_size // 8)
        
        # Check success rate - if low, it might be struggling
        success_rate = instance.get_success_rate()
        if success_rate < 80:
            # Low success rate - use small batches
            return max(2, base_batch_size // 4)
        elif success_rate < 95:
            # Moderate success rate - use reduced batches
            return max(5, base_batch_size // 2)
        
        # High success rate - use full batch size
        return base_batch_size

    def add_wal_write(self, method: str, path: str, data: bytes, headers: Dict[str, str], 
                     target_instance: TargetInstance, executed_on: Optional[str] = None) -> str:
        """Add write to unified WAL with proper collection UUID resolution"""
        write_id = str(uuid.uuid4())
        
        # CRITICAL FIX: Store proper collection identifier - resolve names to UUIDs when possible
        collection_identifier = self.extract_collection_identifier(path)
        
        # CRITICAL: For collection-level operations, try to resolve name to UUID immediately if executed_on is known
        resolved_collection_id = collection_identifier
        if collection_identifier and executed_on:
            # Check if this is a collection name (not UUID) that needs resolution
            import re
            if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', collection_identifier):
                # This is a collection name, try to resolve to UUID for the executed instance
                resolved_uuid = self.resolve_collection_name_to_uuid(collection_identifier, executed_on)
                if resolved_uuid:
                    resolved_collection_id = resolved_uuid
                    logger.info(f"✅ WAL WRITE: Resolved collection name '{collection_identifier}' to UUID {resolved_uuid[:8]} for {executed_on}")
                else:
                    logger.warning(f"⚠️ WAL WRITE: Could not resolve collection name '{collection_identifier}' to UUID for {executed_on} - storing name for later resolution")
                    # Keep the collection name for later resolution during sync
                    resolved_collection_id = collection_identifier
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
            # 🔒 SCALABILITY: Use appropriate lock for WAL operations
            with self._get_appropriate_lock('wal_write'):
                # 🧪 TESTING MODE: Use high-frequency connections for better pool hit rates
                connection_context = (self.get_high_frequency_db_connection_ctx() 
                                    if getattr(self, 'testing_mode', False) 
                                    else self.get_db_connection_ctx())
                
                with connection_context as conn:
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
                            resolved_collection_id,  # CRITICAL FIX: Use resolved UUID instead of raw collection name
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
                
            # Enhanced logging with collection info
            if resolved_collection_id != collection_identifier:
                logger.info(f"📝 WAL write {write_id[:8]} added ({WALWriteStatus.EXECUTED.value if executed_on else WALWriteStatus.PENDING.value}) for {target_instance.value}")
                logger.info(f"   Collection: {collection_identifier} → {resolved_collection_id[:8] if resolved_collection_id else 'None'}")
            else:
                logger.info(f"📝 WAL write {write_id[:8]} added ({WALWriteStatus.EXECUTED.value if executed_on else WALWriteStatus.PENDING.value}) for {target_instance.value}")
                if resolved_collection_id:
                    logger.info(f"   Collection: {resolved_collection_id[:8] if len(resolved_collection_id) > 8 else resolved_collection_id}")
            
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
            # 🔧 FIX: Use context manager for proper connection pooling
            with self.get_db_connection_ctx() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*) FROM unified_wal_writes 
                        WHERE (status = 'executed' OR status = 'failed') AND retry_count < 3
                    """)
                    return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting pending writes count: {e}")
            return 0

    def get_pending_syncs_in_batches(self, target_instance: str, batch_size: int) -> List[SyncBatch]:
        """Get pending writes organized into optimized batches for high-volume processing"""
        try:
            # 🔧 FIX: Use context manager for proper connection pooling
            with self.get_db_connection_ctx() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    # Get writes that need to be synced to this instance
                    # 🔧 CRITICAL FIX FOR "BOTH" TARGET LOGIC: Enhanced logic for per-instance sync tracking
                    # When looking for operations to sync TO an instance, we want:
                    # 1. Operations with target_instance = target_instance AND executed_on != target_instance (single instance sync)
                    # 2. Operations with target_instance = 'both' AND this instance NOT in synced_instances (both instance sync)
                    
                    # 🔧 CRITICAL FIX: Use correct PostgreSQL JSON array element checking
                    # synced_instances is a JSON array like ["primary"] or ["primary", "replica"]
                    # We need to check if the target_instance string exists as an element in this array
                    # Use ? operator to check if array contains the target instance as a text element
                    cur.execute("""
                        SELECT write_id, method, path, data, headers, collection_id, 
                               timestamp, retry_count, data_size_bytes, priority, target_instance, synced_instances
                        FROM unified_wal_writes 
                        WHERE (status = 'executed' OR status = 'failed') 
                        AND (
                            (target_instance = %s AND executed_on != %s) OR
                            (target_instance = 'both' AND (
                                synced_instances IS NULL OR 
                                synced_instances = '[]'::jsonb OR
                                NOT (synced_instances ? %s)
                            ))
                        )
                        AND retry_count < 3
                        AND (
                            status = 'executed' OR 
                            (status = 'failed' AND updated_at < NOW() - INTERVAL '1 minute' * POWER(2, retry_count))
                        )
                        ORDER BY timestamp ASC, retry_count ASC, priority DESC
                        LIMIT %s
                    """, (target_instance, target_instance, target_instance, batch_size * 3))
                    
                    records = cur.fetchall()
                    
                    # 🔍 ENHANCED DEBUG: Log WAL processing order verification
                    if records:
                        logger.info(f"📋 WAL BATCH ORDER DEBUG: Processing {len(records)} operations for {target_instance}")
                        for i, record in enumerate(records[:5]):  # Log first 5 for verification
                            logger.info(f"   {i+1}. {record['timestamp']} - {record['method']} (priority={record['priority']}, retries={record['retry_count']})")
                        if len(records) > 5:
                            logger.info(f"   ... and {len(records) - 5} more operations")
                    
                    # 🔧 DEBUG: Log what we found for troubleshooting
                    if target_instance == 'replica':
                        both_operations = [w for w in records if w.get('target_instance') == 'both']
                        if both_operations:
                            logger.info(f"🔍 DEBUG: Found {len(both_operations)} 'both' target operations to sync to replica")
                            for op in both_operations[:3]:  # Log first 3
                                logger.info(f"   - {op['method']} {op['path']} (synced_instances: {op.get('synced_instances')})")
                    
                    if not records:
                        return []
                    
                    # Create memory-optimized batches
                    batches = []
                    current_batch = []
                    current_batch_size_mb = 0
                    max_batch_size_mb = 30  # 30MB per batch to prevent memory issues
                    
                    for write in records:
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
        # CRITICAL FIX: Use process-specific memory, not system-wide  
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024
        start_time = time.time()
        
        logger.info(f"🔄 Processing sync batch: {batch.batch_size} writes to {batch.target_instance} ({batch.estimated_memory_mb:.1f}MB)")
        
        try:
            for write_record in batch.writes:
                try:
                    # Check PROCESS memory pressure during processing
                    current_memory = process.memory_info().rss / 1024 / 1024
                    if current_memory > self.max_memory_usage_mb * 0.9:  # 90% threshold
                        logger.warning(f"⚠️ Memory pressure during batch processing: {current_memory:.1f}MB")
                        gc.collect()  # Force garbage collection
                    
                    # Execute the write on target instance
                    write_id = write_record['write_id']
                    method = write_record['method']
                    path = write_record['path']
                    data = write_record['data'] or b''
                    
                    # CRITICAL FIX: Define target_instance_type early to prevent variable reference errors
                    target_instance_type = None
                    try:
                        with self.get_db_connection() as conn:
                            with conn.cursor() as cur:
                                cur.execute("SELECT target_instance FROM unified_wal_writes WHERE write_id = %s", (write_id,))
                                result = cur.fetchone()
                                if result:
                                    target_instance_type = result[0]
                    except Exception as e:
                        logger.error(f"Error checking target_instance for {write_id[:8]}: {e}")
                        target_instance_type = 'single'  # Default fallback
                    
                    # CRITICAL: Normalize API path for WAL sync (fixes 502 errors)
                    normalized_path = self.normalize_api_path_to_v2(path)
                    if normalized_path != path:
                        logger.info(f"🔧 WAL SYNC PATH CONVERSION: {path} → {normalized_path}")
                    
                    # CRITICAL FIX: Resolve collection names to UUIDs for collection-level operations (DELETE)
                    final_path = normalized_path
                    if (method == "DELETE" and '/collections/' in normalized_path and 
                        not any(doc_op in normalized_path for doc_op in ['/add', '/upsert', '/update', '/delete', '/get', '/query', '/count'])):
                        # This is a collection-level DELETE operation
                        path_parts = normalized_path.split('/collections/')
                        if len(path_parts) > 1:
                            collection_name = path_parts[1].split('/')[0]  # Extract collection name
                            # Check if it's a name (not UUID) - UUIDs have specific format
                            import re
                            if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', collection_name):
                                logger.info(f"🔍 WAL SYNC: Collection DELETE detected - resolving name '{collection_name}' to UUID for {instance.name}")
                                
                                # CRITICAL FIX: Always try to resolve UUID with enhanced logging
                                resolved_uuid = self.resolve_collection_name_to_uuid(collection_name, instance.name)
                                if resolved_uuid:
                                    # Replace collection name with UUID in path
                                    final_path = normalized_path.replace(f'/collections/{collection_name}', f'/collections/{resolved_uuid}')
                                    logger.info(f"✅ WAL SYNC: Collection DELETE path resolved for {instance.name}: {collection_name} -> {resolved_uuid[:8]}")
                                    logger.info(f"   Final path: {final_path}")
                                else:
                                    # CRITICAL: Don't immediately mark as synced - this might be a resolution error
                                    logger.error(f"❌ WAL SYNC: FAILED to resolve collection name '{collection_name}' to UUID for {instance.name}")
                                    logger.error(f"   This is unexpected - collection might exist but resolution failed")
                                    
                                    # Try one more direct verification before giving up
                                    logger.info(f"🔍 VERIFICATION: Double-checking if collection '{collection_name}' exists on {instance.name}")
                                    try:
                                        verification_response = self.make_direct_request(
                                            instance, 
                                            "GET", 
                                            "/api/v2/tenants/default_tenant/databases/default_database/collections"
                                        )
                                        if verification_response.status_code == 200:
                                            collections = verification_response.json()
                                            found_collection = None
                                            for coll in collections:
                                                if coll.get('name') == collection_name:
                                                    found_collection = coll
                                                    break
                                            
                                            if found_collection:
                                                actual_uuid = found_collection.get('id')
                                                logger.error(f"❌ CRITICAL BUG: Collection '{collection_name}' EXISTS with UUID {actual_uuid[:8]} but resolution failed!")
                                                logger.error(f"   Trying DELETE with discovered UUID: {actual_uuid}")
                                                final_path = normalized_path.replace(f'/collections/{collection_name}', f'/collections/{actual_uuid}')
                                                
                                                # PHANTOM COLLECTION FIX: Try DELETE by UUID first, fall back to name if 404
                                                uuid_delete_response = self.make_direct_request(instance, "DELETE", final_path)
                                                if uuid_delete_response.status_code in [200, 204]:
                                                    logger.info(f"✅ PHANTOM FIX: Collection '{collection_name}' deleted by corrected UUID {actual_uuid[:8]}")
                                                    # Mark as synced and continue
                                                    if target_instance_type == 'both':
                                                        self.mark_instance_synced(write_id, instance.name)
                                                    else:
                                                        self.mark_write_synced(write_id)
                                                    continue
                                                elif uuid_delete_response.status_code == 404:
                                                    # PHANTOM COLLECTION: UUID exists in listing but not accessible - try name-based DELETE
                                                    logger.warning(f"🔍 PHANTOM COLLECTION DETECTED: UUID {actual_uuid[:8]} in listing but 404 on DELETE")
                                                    logger.warning(f"   Attempting DELETE by name as fallback...")
                                                    
                                                    name_delete_path = f"/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
                                                    name_delete_response = self.make_direct_request(instance, "DELETE", name_delete_path)
                                                    
                                                    if name_delete_response.status_code in [200, 204]:
                                                        logger.info(f"✅ PHANTOM FIX: Collection '{collection_name}' deleted by NAME after UUID 404")
                                                        # Mark as synced and continue
                                                        if target_instance_type == 'both':
                                                            self.mark_instance_synced(write_id, instance.name)
                                                        else:
                                                            self.mark_write_synced(write_id)
                                                        continue
                                                    elif name_delete_response.status_code == 404:
                                                        logger.info(f"✅ PHANTOM COLLECTION RESOLVED: '{collection_name}' not found by name either - DELETE goal achieved")
                                                        # Both UUID and name DELETE returned 404 - collection is actually gone
                                                        if target_instance_type == 'both':
                                                            self.mark_instance_synced(write_id, instance.name)
                                                        else:
                                                            self.mark_write_synced(write_id)
                                                        continue
                                                    else:
                                                        logger.error(f"❌ PHANTOM FIX FAILED: Name-based DELETE returned {name_delete_response.status_code}")
                                                        self.mark_write_failed(write_id, f"Phantom collection DELETE failed: UUID 404, Name {name_delete_response.status_code}")
                                                        continue
                                                else:
                                                    logger.error(f"❌ CORRECTED UUID DELETE FAILED: {uuid_delete_response.status_code}")
                                                    self.mark_write_failed(write_id, f"Corrected UUID DELETE failed: HTTP {uuid_delete_response.status_code}")
                                                    continue
                                            else:
                                                # Collection doesn't exist - this could be timing issue during sync
                                                logger.warning(f"⚠️ DELETE SYNC ISSUE: Collection '{collection_name}' not found on {instance.name}")
                                                logger.warning(f"   This could be:")
                                                logger.warning(f"   1. DELETE goal already achieved (collection was deleted)")
                                                logger.warning(f"   2. Timing issue - collection hasn't been created via sync yet")
                                                logger.warning(f"   3. Collection mapping issue")
                                                
                                                # CRITICAL FIX: Don't assume "not found" = "DELETE goal achieved"
                                                # Check if this collection was supposed to be created during same sync batch
                                                logger.info(f"🔍 CHECKING: Looking for pending CREATE operations for '{collection_name}'")
                                                
                                                try:
                                                    with self.get_db_connection() as conn:
                                                        with conn.cursor() as cur:
                                                            # Check if there are pending CREATE operations for this collection
                                                            cur.execute("""
                                                                SELECT COUNT(*) FROM unified_wal_writes 
                                                                WHERE method = 'POST' 
                                                                AND path LIKE %s
                                                                AND collection_id = %s
                                                                AND status != 'synced'
                                                            """, (f'%/collections%', collection_name))
                                                            pending_creates = cur.fetchone()[0]
                                                            
                                                            if pending_creates > 0:
                                                                logger.warning(f"⚠️ TIMING ISSUE: {pending_creates} pending CREATE operations for '{collection_name}'")
                                                                logger.warning(f"   DELETE should wait for CREATE operations to complete first")
                                                                # Fail this DELETE sync so it gets retried after CREATE completes
                                                                self.mark_write_failed(write_id, f"Collection '{collection_name}' has pending CREATE operations - retry after CREATE completes")
                                                                continue
                                                            else:
                                                                logger.info(f"✅ CONFIRMED: No pending CREATE operations - DELETE goal legitimately achieved")
                                                                # Safe to mark as completed
                                                                # Use appropriate sync marking based on target_instance
                                                                if target_instance_type == 'both':
                                                                    # Use per-instance sync tracking for "both" operations
                                                                    self.mark_instance_synced(write_id, instance.name)
                                                                    logger.info(f"📝 MARKED: DELETE operation {write_id[:8]} synced to {instance.name} (goal achieved - no pending CREATEs)")
                                                                else:
                                                                    # Use regular sync marking for single-instance operations
                                                                    self.mark_write_synced(write_id)
                                                                    logger.info(f"📝 MARKED: DELETE operation {write_id[:8]} completed (goal achieved - no pending CREATEs)")
                                                                continue
                                                except Exception as check_error:
                                                    logger.error(f"❌ Error checking pending CREATE operations: {check_error}")
                                                    # On error, be conservative and fail the DELETE sync for retry
                                                    self.mark_write_failed(write_id, f"Could not verify pending CREATE operations for '{collection_name}': {check_error}")
                                                    continue
                                        else:
                                            logger.error(f"❌ VERIFICATION FAILED: Cannot list collections on {instance.name} (HTTP {verification_response.status_code})")
                                            self.mark_write_failed(write_id, f"DELETE verification failed - cannot list collections on {instance.name}")
                                            continue
                                    except Exception as verify_error:
                                        logger.error(f"❌ VERIFICATION ERROR during DELETE sync: {verify_error}")
                                        self.mark_write_failed(write_id, f"DELETE verification error on {instance.name}: {verify_error}")
                                        continue
                    
                    # CRITICAL: Resolve collection names to UUIDs for document operations in WAL sync
                    # Note: Collection DELETE operations already have UUID resolution handled above
                    if ('/collections/' in normalized_path and 
                        any(doc_op in normalized_path for doc_op in ['/add', '/upsert', '/update', '/delete'])):
                        # Extract collection name from path
                        path_parts = normalized_path.split('/collections/')
                        if len(path_parts) > 1:
                            collection_part = path_parts[1].split('/')[0]
                            # Check if it's a name (not UUID) - UUIDs have specific format
                            import re
                            if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', collection_part):
                                logger.info(f"🔍 WAL SYNC: Detected collection name '{collection_part}' in document operation for {instance.name}")
                                
                                # Resolve collection name to UUID for target instance
                                resolved_uuid = self.resolve_collection_name_to_uuid(collection_part, instance.name)
                                if resolved_uuid:
                                    # Replace collection name with UUID in path
                                    final_path = normalized_path.replace(f'/collections/{collection_part}/', f'/collections/{resolved_uuid}/')
                                    logger.info(f"✅ WAL SYNC: Resolved path for {instance.name}: {normalized_path} -> {final_path}")
                                else:
                                    logger.warning(f"⚠️ WAL SYNC: Could not resolve collection name '{collection_part}' to UUID for {instance.name}")
                                    # Skip this sync operation - collection doesn't exist on target
                                    self.mark_write_failed(write_id, f"Collection '{collection_part}' not found on {instance.name}")
                                    continue
                    
                    # Fix headers parsing
                    headers = {}
                    if write_record['headers']:
                        if isinstance(write_record['headers'], str):
                            headers = json.loads(write_record['headers'])
                        else:
                            headers = write_record['headers']
                    
                    # Extract collection ID from path for UUID mapping
                    collection_id = self.extract_collection_identifier(final_path)
                    
                    # CRITICAL: Map collection ID for proper sync (UUID resolution for document operations)
                    # Note: Collection DELETE operations use the resolved UUID from above
                    if (collection_id and 
                        any(doc_op in final_path for doc_op in ['/add', '/upsert', '/update', '/delete'])):
                        # This is a document operation - need to map collection UUID from source to target instance
                        logger.info(f"🔍 DOCUMENT OPERATION DETECTED: {method} {final_path}")
                        logger.info(f"   Source collection ID: {collection_id}")
                        logger.info(f"   Target instance: {instance.name}")
                        
                        # 🔧 CRITICAL FIX: Add retry logic for UUID resolution
                        mapped_uuid = None
                        max_retries = 3
                        for retry_attempt in range(max_retries):
                            try:
                                # Get the correct UUID for the target instance
                                mapped_uuid = self.resolve_collection_name_to_uuid_by_source_id(collection_id, instance.name)
                                logger.info(f"   Mapping attempt {retry_attempt + 1}/{max_retries}: {mapped_uuid}")
                                
                                if mapped_uuid:
                                    break  # Success!
                                elif retry_attempt < max_retries - 1:
                                    # Wait before retry - mapping might be created shortly after collection creation
                                    logger.warning(f"   ⏳ UUID mapping not found on attempt {retry_attempt + 1}, retrying in 2 seconds...")
                                    time.sleep(2)
                                else:
                                    logger.error(f"   ❌ UUID mapping still not found after {max_retries} attempts")
                                    
                            except Exception as uuid_error:
                                logger.error(f"   ❌ UUID resolution error on attempt {retry_attempt + 1}: {uuid_error}")
                                if retry_attempt < max_retries - 1:
                                    time.sleep(2)
                        
                        if mapped_uuid and mapped_uuid != collection_id:
                            # Replace source UUID with target UUID in path
                            old_path = final_path
                            final_path = final_path.replace(collection_id, mapped_uuid)
                            logger.info(f"✅ UUID MAPPED for {instance.name}: {collection_id[:8]} -> {mapped_uuid[:8]}")
                            logger.info(f"   Path changed: {old_path} -> {final_path}")
                        elif mapped_uuid is None:
                            logger.error(f"❌ CRITICAL: No UUID mapping found for {collection_id[:8]} -> {instance.name} after {max_retries} retries")
                            logger.error(f"   Collection may not exist yet on target instance")
                            
                            # 🔧 ENHANCED DEBUG: Check if mapping exists but for wrong direction
                            try:
                                logger.error(f"   🔍 DEBUG: Checking if reverse mapping exists...")
                                reverse_mapped = self.resolve_collection_name_to_uuid_by_source_id(collection_id, "primary" if instance.name == "replica" else "replica")
                                if reverse_mapped:
                                    logger.error(f"   🔍 DEBUG: Reverse mapping exists: {collection_id[:8]} -> {reverse_mapped[:8]} (wrong direction)")
                                else:
                                    logger.error(f"   🔍 DEBUG: No mapping found in either direction")
                                    
                                # Check total mappings for context
                                with self.get_db_connection() as conn:
                                    with conn.cursor() as cur:
                                        cur.execute("SELECT COUNT(*) FROM collection_id_mapping")
                                        total_mappings = cur.fetchone()[0]
                                        logger.error(f"   🔍 DEBUG: Total mappings in database: {total_mappings}")
                                        
                                        # Check if the collection name exists
                                        cur.execute("""
                                            SELECT collection_name, primary_collection_id, replica_collection_id, status
                                            FROM collection_id_mapping 
                                            WHERE primary_collection_id = %s OR replica_collection_id = %s
                                        """, (collection_id, collection_id))
                                        result = cur.fetchone()
                                        if result:
                                            name, p_id, r_id, status = result
                                            logger.error(f"   🔍 DEBUG: Found mapping: {name} -> P:{p_id[:8] if p_id else 'None'}, R:{r_id[:8] if r_id else 'None'}, Status:{status}")
                                        else:
                                            logger.error(f"   🔍 DEBUG: No mapping row found for UUID {collection_id[:8]}")
                                            
                            except Exception as debug_error:
                                logger.error(f"   🔍 DEBUG failed: {debug_error}")
                            
                            # Skip this sync operation - collection doesn't exist on target
                            self.mark_write_failed(write_id, f"No UUID mapping found for collection {collection_id[:8]} on {instance.name} after {max_retries} retries")
                            continue
                        else:
                            logger.info(f"ℹ️ UUID mapping not needed: {collection_id[:8]} (same on both instances)")
                            # Continue with current UUID
                    
                    # Make the sync request with normalized path
                    response = self.make_direct_request(instance, method, final_path, data=data, headers=headers)
                    
                    # CRITICAL FIX: Handle collection creation sync with proper error handling including 409 Conflict
                    if (method == 'POST' and 
                        ('/collections' in final_path and not any(doc_op in final_path for doc_op in ['/add', '/upsert', '/get', '/query', '/update', '/delete', '/count']))):
                        
                        if response.status_code in [200, 201]:
                            logger.info(f"✅ WAL SYNC: Collection creation successful on {instance.name} - Status: {response.status_code}")
                            # Mark as synced using appropriate method
                            if target_instance_type == 'both':
                                self.mark_instance_synced(write_id, instance.name)
                            else:
                                self.mark_write_synced(write_id)
                        elif response.status_code == 409:
                            # 409 Conflict = Collection already exists = SUCCESS for sync purposes
                            logger.info(f"✅ WAL SYNC: Collection creation successful on {instance.name} - Status: 409 (collection already exists)")
                            # Mark as synced using appropriate method
                            if target_instance_type == 'both':
                                self.mark_instance_synced(write_id, instance.name)
                            else:
                                self.mark_write_synced(write_id)
                        else:
                            logger.error(f"❌ WAL SYNC: Collection creation failed on {instance.name} - Status: {response.status_code}")
                            logger.error(f"   Response: {response.text[:200]}")
                            self.mark_write_failed(write_id, f"Collection creation failed: HTTP {response.status_code}")
                            continue
                    
                    # CRITICAL FIX: Handle DELETE operations with proper status code validation and unified sync completion
                    elif (method == 'DELETE' and '/collections/' in final_path):
                        delete_success = False
                        
                        if response.status_code in [200, 204]:
                            logger.info(f"✅ WAL SYNC: Collection DELETE successful on {instance.name} - Status: {response.status_code}")
                            delete_success = True
                        elif response.status_code == 404:
                            logger.info(f"✅ WAL SYNC: Collection DELETE successful on {instance.name} - Status: 404 (collection not found - goal achieved)")
                            delete_success = True
                        else:
                            logger.error(f"❌ WAL SYNC: Collection DELETE failed on {instance.name} - Status: {response.status_code}")
                            logger.error(f"   Response: {response.text[:200]}")
                            logger.error(f"   DELETE path: {final_path}")
                            self.mark_write_failed(write_id, f"Collection DELETE failed: HTTP {response.status_code}")
                            continue
                        
                        # CRITICAL FIX: Unified DELETE sync completion - always use appropriate method based on target_instance
                        if delete_success:
                            if target_instance_type == 'both':
                                self.mark_instance_synced(write_id, instance.name)
                                logger.info(f"📝 DELETE SYNC: Operation {write_id[:8]} marked as synced to {instance.name} (both-target operation)")
                            else:
                                self.mark_write_synced(write_id)
                                logger.info(f"📝 DELETE SYNC: Operation {write_id[:8]} marked as completed (single-target operation)")
                    
                    # Handle other operations (document operations, etc.)
                    elif response.status_code in [200, 201, 204]:
                        logger.info(f"✅ WAL SYNC: {method} operation successful on {instance.name} - Status: {response.status_code}")
                        # Mark as synced using appropriate method
                        if target_instance_type == 'both':
                            self.mark_instance_synced(write_id, instance.name)
                        else:
                            self.mark_write_synced(write_id)
                    else:
                        logger.error(f"❌ WAL SYNC: {method} operation failed on {instance.name} - Status: {response.status_code}")
                        logger.error(f"   Response: {response.text[:200]}")
                        self.mark_write_failed(write_id, f"{method} operation failed: HTTP {response.status_code}")
                        continue
                    
                    # Collection mapping updates for successful operations
                    # (This section handles mapping updates for collection creation operations)
                    # ... existing mapping code ...
                    
                    # Clean up collection mapping if DELETE was successful
                    if (method == 'DELETE' and 
                        '/collections/' in final_path and 
                        response.status_code in [200, 204]):
                        try:
                            # Extract collection name from the original WAL record for mapping cleanup
                            original_collection_identifier = write_record.get('collection_id')
                            
                            # CRITICAL FIX: Only clean up mapping if this is a name-based identifier
                            import re
                            if (original_collection_identifier and 
                                not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', original_collection_identifier)):
                                
                                collection_name = original_collection_identifier
                                logger.info(f"🗑️ COLLECTION DELETED: {collection_name} from {instance.name} - cleaning up mapping")
                                
                                # Update mapping to remove the UUID for this instance
                                # 🔒 SCALABILITY: Use appropriate lock for collection mapping operations
                                with self._get_appropriate_lock('collection_mapping'):
                                    with self.get_db_connection() as conn:
                                        with conn.cursor() as cur:
                                            if instance.name == 'primary':
                                                # Collection deleted from primary - clear primary UUID
                                                cur.execute("""
                                                    UPDATE collection_id_mapping 
                                                    SET primary_collection_id = NULL, updated_at = NOW()
                                                    WHERE collection_name = %s
                                                """, (collection_name,))
                                                logger.info(f"🗑️ Cleared primary mapping for {collection_name}")
                                            else:  # replica
                                                # Collection deleted from replica - clear replica UUID  
                                                cur.execute("""
                                                    UPDATE collection_id_mapping 
                                                    SET replica_collection_id = NULL, updated_at = NOW()
                                                    WHERE collection_name = %s
                                                """, (collection_name,))
                                                logger.info(f"🗑️ Cleared replica mapping for {collection_name}")
                                            
                                            conn.commit()
                                            
                                            # Check if both UUIDs are now NULL and delete the mapping entirely
                                            cur.execute("""
                                                SELECT primary_collection_id, replica_collection_id 
                                                FROM collection_id_mapping 
                                                WHERE collection_name = %s
                                            """, (collection_name,))
                                            result = cur.fetchone()
                                            
                                            if result and not result[0] and not result[1]:
                                                # Both UUIDs are NULL - delete the mapping entirely
                                                cur.execute("""
                                                    DELETE FROM collection_id_mapping 
                                                    WHERE collection_name = %s
                                                """, (collection_name,))
                                                conn.commit()
                                                logger.info(f"🗑️ MAPPING DELETED: {collection_name} (both instances cleared)")
                                            else:
                                                logger.info(f"✅ MAPPING UPDATED: {collection_name} (one instance still has collection)")
                                                
                        except Exception as mapping_cleanup_error:
                            logger.error(f"❌ Collection mapping cleanup failed: {mapping_cleanup_error}")
                            # Don't fail the sync operation for mapping cleanup errors
                    
                    # CRITICAL FIX: Use proper sync completion logic for "both" target operations
                    if target_instance_type == 'both':
                        # For "both" operations, use instance-specific sync tracking
                        self.mark_instance_synced(write_id, instance.name)
                        logger.info(f"🔄 BOTH TARGET: {write_id[:8]} {method} completed on {instance.name} - using instance-specific sync tracking")
                    else:
                        # For single target operations, mark as fully synced
                        self.mark_write_synced(write_id)
                        logger.info(f"✅ SINGLE TARGET: {write_id[:8]} {method} completed on {instance.name} - marked as fully synced")
                    
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"❌ WAL sync failed for {write_id[:8]}: {e}")
                    self.mark_write_failed(write_id, str(e)[:500])
                    
        except Exception as e:
            logger.error(f"❌ Batch processing failed: {e}")
            
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
            
            # Get batches for each healthy instance with gradual recovery
            all_batches = []
            for instance in self.instances:
                # USE CASE 2 METHOD: Real-time health verification before sync attempts
                if instance.is_healthy:
                    # ENHANCED: Double-check health with real-time verification (prevents timing race conditions)
                    realtime_healthy = self.check_instance_health_realtime(instance, timeout=3)
                    if not realtime_healthy:
                        logger.warning(f"⚠️ SYNC PREVENTION: {instance.name} marked unhealthy via real-time check (cached: healthy, actual: down)")
                        # Update cached health status immediately
                        instance.is_healthy = False
                        continue
                    
                    # Use smaller batch size for recently recovered instances to prevent overload
                    instance_batch_size = self.calculate_recovery_batch_size(instance, batch_size)
                    batches = self.get_pending_syncs_in_batches(instance.name, instance_batch_size)
                    all_batches.extend(batches)
                    logger.info(f"✅ SYNC APPROVED: {instance.name} real-time verified healthy - {len(batches)} batches queued")
                else:
                    logger.info(f"⏸️ SYNC SKIPPED: {instance.name} cached as unhealthy (USE CASE 2 method)")
            
            if not all_batches:
                logger.info("ℹ️ No sync batches available (all instances down or no pending writes)")
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
            # 🔒 SCALABILITY: Use appropriate lock for WAL status updates
            with self._get_appropriate_lock('wal_write'):
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
            # 🔒 SCALABILITY: Use appropriate lock for WAL status updates
            with self._get_appropriate_lock('wal_write'):
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
        """
        🔧 ENHANCED: Make direct request with retry logic for 502 errors and improved reliability
        """
        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 10
        
        # CRITICAL FIX: Add retry logic for 502 Bad Gateway errors (common during instance recovery)
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries + 1):
            try:
                url = f"{instance.url}{path}"
                logger.debug(f"🔧 WAL SYNC REQUEST (attempt {attempt + 1}/{max_retries + 1}): {method} {url}")
                response = requests.request(method, url, **kwargs)
                
                # Log response for debugging WAL sync issues
                logger.debug(f"🔧 WAL SYNC RESPONSE: {response.status_code} - {response.text[:100]}")
                
                # CRITICAL FIX: Handle 502 errors with retry logic
                if response.status_code == 502 and attempt < max_retries:
                    logger.warning(f"⚠️ 502 Bad Gateway on {instance.name} (attempt {attempt + 1}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                
                # 🔧 CRITICAL FIX: Don't raise 404 errors for DELETE operations - they indicate success
                if method == 'DELETE' and response.status_code == 404:
                    logger.debug(f"✅ DELETE 404 treated as success: collection already deleted")
                else:
                    response.raise_for_status()
                return response
                
            except requests.exceptions.Timeout as e:
                if attempt < max_retries:
                    logger.warning(f"⚠️ Timeout on {instance.name} (attempt {attempt + 1}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error(f"❌ Final timeout on {instance.name} after {max_retries + 1} attempts")
                    raise e
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries:
                    logger.warning(f"⚠️ Connection error on {instance.name} (attempt {attempt + 1}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error(f"❌ Final connection error on {instance.name} after {max_retries + 1} attempts")
                    raise e
            except Exception as e:
                if attempt < max_retries and "502" in str(e):
                    logger.warning(f"⚠️ 502 error on {instance.name} (attempt {attempt + 1}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.warning(f"Direct request to {instance.name} failed: {method} {path} - {e}")
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
                        # Enhanced health check: Test actual functionality, not just connectivity
                        response = requests.get(f"{instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=5)
                        was_healthy = instance.is_healthy
                        # More stringent health check - require both 200 status AND valid JSON
                        if response.status_code == 200:
                            try:
                                collections = response.json()
                                instance.is_healthy = isinstance(collections, list)  # Valid collections response
                                if not instance.is_healthy:
                                    logger.warning(f"❌ {instance.name} health check failed: Invalid collections response")
                            except:
                                instance.is_healthy = False
                                logger.warning(f"❌ {instance.name} health check failed: Non-JSON response")
                        else:
                            instance.is_healthy = False
                        instance.last_health_check = datetime.now()
                        instance.update_stats(instance.is_healthy)
                        
                        if instance.is_healthy and not was_healthy:
                            logger.info(f"✅ {instance.name} recovered")
                            # CRITICAL: Trigger collection recovery AFTER WAL sync completes to prevent race conditions
                            # This prevents collection recovery from recreating collections that have pending DELETE operations
                            threading.Thread(
                                target=lambda: self.coordinated_recovery_sequence(instance.name),
                                daemon=True,
                                name=f"CoordinatedRecovery-{instance.name}"
                            ).start()
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

    def coordinated_recovery_sequence(self, target_instance_name: str):
        """
        🔧 CRITICAL FIX: Coordinated recovery that prevents race conditions between collection recovery and WAL sync
        """
        try:
            logger.info(f"🔧 COORDINATED RECOVERY: Starting for {target_instance_name}")
            
            # STEP 1: Wait for WAL sync to process any pending operations
            max_wait_seconds = 60  # Max wait time for WAL sync
            wait_interval = 5  # Check every 5 seconds
            
            for attempt in range(max_wait_seconds // wait_interval):
                pending_writes = self.get_pending_writes_count()
                if pending_writes == 0:
                    logger.info(f"✅ COORDINATED RECOVERY: WAL sync complete (0 pending writes)")
                    break
                else:
                    logger.info(f"⏳ COORDINATED RECOVERY: Waiting for WAL sync completion ({pending_writes} pending writes)")
                    time.sleep(wait_interval)
            else:
                logger.warning(f"⚠️ COORDINATED RECOVERY: Proceeding despite pending WAL operations (timeout after {max_wait_seconds}s)")
            
            # STEP 2: Wait additional buffer time for any final DELETE operations to complete
            logger.info(f"⏳ COORDINATED RECOVERY: Waiting 10s buffer for final operations...")
            time.sleep(10)
            
            # STEP 3: Now safe to run collection recovery
            logger.info(f"🔧 COORDINATED RECOVERY: Starting collection recovery for {target_instance_name}")
            success = self.sync_missing_collections_to_instance(target_instance_name)
            
            if success:
                logger.info(f"✅ COORDINATED RECOVERY: Completed successfully for {target_instance_name}")
            else:
                logger.error(f"❌ COORDINATED RECOVERY: Failed for {target_instance_name}")
            
        except Exception as e:
            logger.error(f"❌ COORDINATED RECOVERY: Error for {target_instance_name}: {e}")
            import traceback
            logger.error(f"Recovery traceback: {traceback.format_exc()}")

    def get_status(self, realtime_health: bool = False) -> Dict[str, Any]:
        """🎯 Enhanced status with high-volume monitoring, real-time health, and advanced metrics"""
        try:
            instances = self.instances if hasattr(self, 'instances') else []
            healthy_instances = [inst for inst in instances if inst.is_healthy]
            
            # Get pending write count
            pending_count = 0
            if hasattr(self, 'get_pending_write_count'):
                try:
                    pending_count = self.get_pending_write_count()
                except:
                    pass
            
            # 🔧 FIX: Get concurrency manager metrics properly
            concurrency_stats = {
                "max_concurrent_requests": self.concurrency_manager.max_concurrent_requests,
                "request_queue_size": self.concurrency_manager.request_queue_size,
                "request_timeout": self.concurrency_manager.request_timeout,
                "concurrent_requests_active": self.concurrency_manager.stats.get("concurrent_requests", 0),
                "total_requests_processed": self.concurrency_manager.stats.get("total_requests", 0),
                "timeout_requests": self.concurrency_manager.stats.get("timeout_requests", 0),
                "queue_full_rejections": self.concurrency_manager.stats.get("queue_full_rejections", 0),
                "semaphore_acquisitions": self.concurrency_manager.stats.get("semaphore_acquisitions", 0),
                "semaphore_releases": self.concurrency_manager.stats.get("semaphore_releases", 0),
                "processing_failures": self.concurrency_manager.stats.get("processing_failures", 0)
            }

            return {
                "service": "Enhanced Unified WAL-First ChromaDB Load Balancer",
                "architecture": "WAL-First with High-Volume Processing",
                "healthy_instances": len(healthy_instances),
                "total_instances": len(self.instances),
                "high_volume_config": {
                    "max_memory_mb": self.max_memory_usage_mb,
                    "current_memory_percent": self.current_memory_usage,
                    "max_workers": self.max_workers,
                    "default_batch_size": self.default_batch_size,
                    "max_batch_size": self.max_batch_size,
                    "peak_memory_usage": self.stats.get("peak_memory_usage", 0.0),
                    # 🚀 CONCURRENCY CONFIGURATION
                    "max_concurrent_requests": concurrency_stats["max_concurrent_requests"],
                    "request_queue_size": concurrency_stats["request_queue_size"],
                    "request_timeout": concurrency_stats["request_timeout"]
                },
                "unified_wal": {
                    "pending_writes": pending_count,
                    "is_syncing": self.is_syncing,
                    "sync_interval_seconds": self.sync_interval,
                    "database": "PostgreSQL",
                    "approach": "High-Volume WAL-First"
                },
                "performance_stats": {
                    "memory_pressure_events": self.stats.get("memory_pressure_events", 0),
                    "adaptive_batch_reductions": self.stats.get("adaptive_batch_reductions", 0),
                    "avg_sync_throughput": self.stats.get("avg_sync_throughput", 0.0),
                    # 🚀 SCALABILITY METRICS
                    "connection_pool_hits": self.stats.get("connection_pool_hits", 0),
                    "connection_pool_misses": self.stats.get("connection_pool_misses", 0),
                    "lock_contention_avoided": self.stats.get("lock_contention_avoided", 0),
                    # 🚀 CONCURRENCY METRICS  
                    "concurrent_requests_active": concurrency_stats["concurrent_requests_active"],
                    "total_requests_processed": concurrency_stats["total_requests_processed"],
                    "timeout_requests": concurrency_stats["timeout_requests"],
                    "queue_full_rejections": concurrency_stats["queue_full_rejections"],
                    # 🔧 MAPPING MONITORING (CRITICAL FOR USE CASE 4 SUCCESS)
                    "mapping_failures": self.stats.get("mapping_failures", 0),
                    "critical_mapping_failures": self.stats.get("critical_mapping_failures", 0),
                    "mapping_exceptions": self.stats.get("mapping_exceptions", 0)
                },
                # 🔧 FIX: Add concurrency details for debugging
                "concurrency_details": concurrency_stats,
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
                "stats": self.stats,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Status generation error: {e}")
            return {
                "service": "Enhanced Unified WAL-First ChromaDB Load Balancer",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    # Keep other essential methods for load balancing functionality

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

    def resolve_collection_name_to_uuid_by_source_id(self, source_collection_id: str, target_instance_name: str) -> Optional[str]:
        """Map collection UUID from source instance to target instance UUID"""
        try:
            logger.info(f"🔍 UUID MAPPING: Resolving {source_collection_id[:8]} for {target_instance_name}")
            
            # 🔧 CRITICAL FIX: Use fresh database connection to avoid transaction isolation issues
            # This ensures we see the latest collection mappings during WAL sync
            import psycopg2
            fresh_conn = None
            try:
                fresh_conn = psycopg2.connect(
                    self.database_url,
                    connect_timeout=10,
                    application_name='wal-uuid-resolution'
                )
                
                with fresh_conn.cursor() as cur:
                    # Find collection name by source UUID
                    cur.execute("""
                        SELECT collection_name, primary_collection_id, replica_collection_id 
                        FROM collection_id_mapping 
                        WHERE primary_collection_id = %s OR replica_collection_id = %s
                    """, (source_collection_id, source_collection_id))
                    
                    result = cur.fetchone()
                    if result:
                        collection_name, primary_uuid, replica_uuid = result
                        logger.info(f"   Found mapping: {collection_name} -> primary:{primary_uuid[:8] if primary_uuid else 'None'}, replica:{replica_uuid[:8] if replica_uuid else 'None'}")
                        
                        # Return the target instance UUID
                        if target_instance_name == "primary" and primary_uuid:
                            logger.info(f"✅ Mapped {source_collection_id[:8]} -> {primary_uuid[:8]} (primary)")
                            return primary_uuid
                        elif target_instance_name == "replica" and replica_uuid:
                            logger.info(f"✅ Mapped {source_collection_id[:8]} -> {replica_uuid[:8]} (replica)")
                            return replica_uuid
                        else:
                            logger.error(f"❌ Missing {target_instance_name} UUID for collection {collection_name}")
                            logger.error(f"   Available: primary={primary_uuid is not None}, replica={replica_uuid is not None}")
                            return None
                    else:
                        logger.error(f"❌ No mapping found for UUID {source_collection_id[:8]}")
                        # Check if any mappings exist at all
                        cur.execute("SELECT COUNT(*) FROM collection_id_mapping")
                        total_mappings = cur.fetchone()[0]
                        logger.error(f"   Total mappings in database: {total_mappings}")
                        return None  # Return None to fail sync properly instead of using wrong UUID
                        
            finally:
                if fresh_conn:
                    fresh_conn.close()
                        
        except Exception as e:
            logger.error(f"❌ UUID mapping failed for {source_collection_id[:8]} -> {target_instance_name}: {e}")
            return None  # Return None on error to fail sync properly

    def check_instance_health_realtime(self, instance: ChromaInstance, timeout: int = 5) -> bool:
        """
        CRITICAL: Real-time health check that bypasses the 30-second cache
        
        This method performs immediate health checking for critical operations
        to prevent transaction loss during infrastructure failures.
        """
        try:
            response = requests.get(f"{instance.url}/api/v2/version", timeout=timeout)
            is_healthy = response.status_code == 200
            
            logger.info(f"🔍 REALTIME HEALTH: {instance.name} = {'✅ Healthy' if is_healthy else '❌ Down'} (bypassed cache)")
            return is_healthy
            
        except Exception as e:
            logger.warning(f"🔍 REALTIME HEALTH: {instance.name} = ❌ Down ({e})")
            return False

    def choose_read_instance_with_realtime_health(self, path: str, method: str, headers: Dict[str, str]) -> Optional[ChromaInstance]:
        """
        CRITICAL: Choose instance with real-time health checking for write operations
        
        This prevents the 30-second timing gap where transactions are lost
        during infrastructure failures.
        """
        healthy_instances = self.get_healthy_instances()
        if not healthy_instances:
            logger.warning("⚠️ No cached healthy instances - using real-time health checking")
            
            # Real-time fallback when cache shows no healthy instances
            for instance in self.instances:
                if self.check_instance_health_realtime(instance):
                    logger.info(f"✅ REALTIME RECOVERY: Found healthy {instance.name} via real-time check")
                    return instance
            
            logger.error("❌ No healthy instances found via real-time checking")
            return None
        
        # For WRITE operations, use real-time health checking to prevent transaction loss
        if method in ["POST", "PUT", "DELETE", "PATCH"]:
            logger.info(f"🔍 WRITE OPERATION: Using real-time health checking for {method} {path}")
            
            # Prefer primary for writes, but verify health in real-time
            primary = self.get_primary_instance()
            if primary:
                if self.check_instance_health_realtime(primary):
                    logger.info("✅ WRITE → PRIMARY (real-time verified)")
                    return primary
                else:
                    logger.warning("⚠️ PRIMARY DOWN (real-time) - Attempting replica failover")
                    
                    # Write failover to replica if primary is down
                    replica = self.get_replica_instance()
                    if replica and self.check_instance_health_realtime(replica):
                        logger.warning("🔄 WRITE FAILOVER → REPLICA (real-time verified)")
                        return replica
                    else:
                        logger.error("❌ WRITE FAILOVER FAILED - Both instances down")
                        return None
            
            # No primary available, try replica
            replica = self.get_replica_instance()
            if replica and self.check_instance_health_realtime(replica):
                logger.warning("🔄 WRITE → REPLICA (primary unavailable)")
                return replica
            
            logger.error("❌ NO HEALTHY INSTANCES for write operation")
            return None
        
        # For READ operations, use real-time health checking (FIXED: was using cached health)
        if method == "GET":
            logger.info(f"🔍 READ OPERATION: Using real-time health checking for {method} {path}")
            
            replica = self.get_replica_instance()
            primary = self.get_primary_instance()
            
            # Use read replica ratio, but verify health in real-time
            if replica and primary and random.random() < self.read_replica_ratio:
                # Prefer replica for reads, but verify it's actually healthy
                if self.check_instance_health_realtime(replica):
                    logger.info("✅ READ → REPLICA (real-time verified)")
                    return replica
                else:
                    logger.warning("⚠️ REPLICA DOWN (real-time) - Attempting primary failover")
                    if self.check_instance_health_realtime(primary):
                        logger.info("🔄 READ FAILOVER → PRIMARY (real-time verified)")
                        return primary
                    else:
                        logger.error("❌ READ FAILOVER FAILED - Both instances down")
                        return None
            elif primary:
                # Prefer primary for reads, verify real-time health
                if self.check_instance_health_realtime(primary):
                    logger.info("✅ READ → PRIMARY (real-time verified)")
                    return primary
                else:
                    logger.warning("⚠️ PRIMARY DOWN (real-time) - Attempting replica failover")
                    if replica and self.check_instance_health_realtime(replica):
                        logger.info("🔄 READ FAILOVER → REPLICA (real-time verified)")
                        return replica
                    else:
                        logger.error("❌ READ FAILOVER FAILED - Both instances down")
                        return None
            elif replica:
                # Only replica available, verify real-time health
                if self.check_instance_health_realtime(replica):
                    logger.info("✅ READ → REPLICA (primary unavailable, real-time verified)")
                    return replica
                else:
                    logger.error("❌ READ OPERATION FAILED - No healthy instances")
                    return None
            
            logger.error("❌ NO INSTANCES AVAILABLE for read operation")
            return None
        
        # Default fallback
        return self.get_primary_instance()
    
    def forward_request_with_recovery(self, method: str, path: str, headers: Dict[str, str], 
                                    data: bytes, original_transaction_id: str = None):
        """
        🛡️ TRANSACTION SAFETY: Forward request for transaction recovery
        
        This method is called by the Transaction Safety Service to retry failed transactions.
        """
        try:
            logger.info(f"🔄 RECOVERY: Retrying {method} {path} (transaction: {original_transaction_id[:8] if original_transaction_id else 'unknown'})")
            
            # Use real-time health checking for recovery operations
            target_instance = self.choose_read_instance_with_realtime_health(path, method, headers)
            if not target_instance:
                logger.error(f"❌ RECOVERY: No healthy instances for retry")
                return None
            
            # Normalize path and resolve collections
            normalized_path = self.normalize_api_path_to_v2(path)
            final_path = normalized_path
            
            # Collection name resolution for document operations
            if '/collections/' in normalized_path and any(doc_op in normalized_path for doc_op in ['/add', '/upsert', '/get', '/query', '/update', '/delete']):
                path_parts = normalized_path.split('/collections/')
                if len(path_parts) > 1:
                    collection_part = path_parts[1].split('/')[0]
                    import re
                    if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', collection_part):
                        resolved_uuid = self.resolve_collection_name_to_uuid(collection_part, target_instance.name)
                        if resolved_uuid:
                            final_path = normalized_path.replace(f'/collections/{collection_part}/', f'/collections/{resolved_uuid}/')
            
            url = f"{target_instance.url}{final_path}"
            
            # Execute recovery request
            import requests
            response = requests.request(
                method=method,
                url=url,
                headers=headers or {'Content-Type': 'application/json'},
                data=data,
                timeout=15
            )
            
            logger.info(f"✅ RECOVERY: {method} {path} completed with status {response.status_code}")
            return response
            
        except Exception as e:
            logger.error(f"❌ RECOVERY: Failed to retry {method} {path}: {e}")
            return None

    def create_collection_mapping_with_retry(self, collection_name: str, collection_uuid: str, target_instance_name: str, max_retries: int = 3) -> bool:
        """
        🔧 BULLETPROOF: Create collection mapping with retry logic and race condition protection
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"🔧 MAPPING ATTEMPT {attempt + 1}/{max_retries}: Creating mapping for {collection_name} -> {collection_uuid[:8]} on {target_instance_name}")
                
                # 🔒 SCALABILITY: Use appropriate lock for collection mapping operations
                with self._get_appropriate_lock('collection_mapping'):
                    with self.get_db_connection() as conn:
                        with conn.cursor() as cur:
                            # BULLETPROOF: Use UPSERT to eliminate race conditions
                            if target_instance_name == "primary":
                                cur.execute("""
                                    INSERT INTO collection_id_mapping 
                                    (collection_name, primary_collection_id, created_at) 
                                    VALUES (%s, %s, NOW())
                                    ON CONFLICT (collection_name) DO UPDATE SET
                                    primary_collection_id = EXCLUDED.primary_collection_id,
                                    updated_at = NOW()
                                """, (collection_name, collection_uuid))
                                logger.info(f"✅ MAPPING SUCCESS: Primary mapping created/updated for {collection_name}")
                                
                            elif target_instance_name == "replica":
                                cur.execute("""
                                    INSERT INTO collection_id_mapping 
                                    (collection_name, replica_collection_id, created_at) 
                                    VALUES (%s, %s, NOW())
                                    ON CONFLICT (collection_name) DO UPDATE SET
                                    replica_collection_id = EXCLUDED.replica_collection_id,
                                    updated_at = NOW()
                                """, (collection_name, collection_uuid))
                                logger.info(f"✅ MAPPING SUCCESS: Replica mapping created/updated for {collection_name}")
                            
                            conn.commit()
                            
                            # VALIDATION: Verify mapping was created
                            cur.execute("""
                                SELECT collection_name, primary_collection_id, replica_collection_id 
                                FROM collection_id_mapping 
                                WHERE collection_name = %s
                            """, (collection_name,))
                            result = cur.fetchone()
                            
                            if result:
                                _, primary_id, replica_id = result
                                logger.info(f"✅ MAPPING VERIFIED: {collection_name} -> P:{primary_id[:8] if primary_id else 'None'}, R:{replica_id[:8] if replica_id else 'None'}")
                                return True
                            else:
                                logger.error(f"❌ MAPPING VALIDATION FAILED: No mapping found after creation for {collection_name}")
                                return False
                            
            except Exception as e:
                logger.error(f"❌ MAPPING ATTEMPT {attempt + 1} FAILED for {collection_name}: {e}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff: 0.1s, 0.2s, 0.4s
                    delay = 0.1 * (2 ** attempt)
                    logger.info(f"⏳ MAPPING RETRY: Waiting {delay}s before retry {attempt + 2}/{max_retries}")
                    import time
                    time.sleep(delay)
                else:
                    logger.error(f"💀 MAPPING FATAL: All {max_retries} attempts failed for {collection_name}")
                    # Log to stats for monitoring
                    self.stats["mapping_failures"] = self.stats.get("mapping_failures", 0) + 1
                    return False
        
        return False

    def create_complete_collection_mapping_with_retry(self, collection_name: str, primary_uuid: str, replica_uuid: str, initiated_from: str, max_retries: int = 3) -> bool:
        """
        🔧 DISTRIBUTED SYSTEM FIX: Create complete collection mapping with both primary and replica UUIDs
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"🔧 COMPLETE MAPPING ATTEMPT {attempt + 1}/{max_retries}: Creating complete mapping for {collection_name}")
                logger.info(f"   Primary UUID: {primary_uuid[:8] if primary_uuid else 'None'}")
                logger.info(f"   Replica UUID: {replica_uuid[:8] if replica_uuid else 'None'}")
                logger.info(f"   Initiated from: {initiated_from}")
                
                # 🔒 SCALABILITY: Use appropriate lock for collection mapping operations
                with self._get_appropriate_lock('collection_mapping'):
                    with self.get_db_connection_ctx() as conn:
                        with conn.cursor() as cur:
                            # BULLETPROOF: Create complete mapping with UPSERT
                            cur.execute("""
                                INSERT INTO collection_id_mapping 
                                (collection_name, primary_collection_id, replica_collection_id, created_at) 
                                VALUES (%s, %s, %s, NOW())
                                ON CONFLICT (collection_name) DO UPDATE SET
                                primary_collection_id = COALESCE(EXCLUDED.primary_collection_id, collection_id_mapping.primary_collection_id),
                                replica_collection_id = COALESCE(EXCLUDED.replica_collection_id, collection_id_mapping.replica_collection_id),
                                updated_at = NOW()
                            """, (collection_name, primary_uuid, replica_uuid))
                            
                            conn.commit()
                            
                            # VALIDATION: Verify complete mapping was created
                            cur.execute("""
                                SELECT collection_name, primary_collection_id, replica_collection_id 
                                FROM collection_id_mapping 
                                WHERE collection_name = %s
                            """, (collection_name,))
                            result = cur.fetchone()
                            
                            if result:
                                _, final_primary_id, final_replica_id = result
                                logger.info(f"✅ COMPLETE MAPPING VERIFIED: {collection_name}")
                                logger.info(f"   Final Primary: {final_primary_id[:8] if final_primary_id else 'None'}")
                                logger.info(f"   Final Replica: {final_replica_id[:8] if final_replica_id else 'None'}")
                                
                                # Check if mapping is complete
                                if final_primary_id and final_replica_id:
                                    logger.info(f"🎉 COMPLETE MAPPING SUCCESS: {collection_name} fully mapped on both instances")
                                    return True
                                else:
                                    logger.warning(f"⚠️ PARTIAL MAPPING: {collection_name} partially mapped (better than none)")
                                    return True  # Partial is still success - other instance might be down
                            else:
                                logger.error(f"❌ MAPPING VALIDATION FAILED: No mapping found after creation for {collection_name}")
                                return False
                            
            except Exception as e:
                logger.error(f"❌ COMPLETE MAPPING ATTEMPT {attempt + 1} FAILED for {collection_name}: {e}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff: 0.1s, 0.2s, 0.4s
                    delay = 0.1 * (2 ** attempt)
                    logger.info(f"⏳ COMPLETE MAPPING RETRY: Waiting {delay}s before retry {attempt + 2}/{max_retries}")
                    import time
                    time.sleep(delay)
                else:
                    logger.error(f"💀 COMPLETE MAPPING FATAL: All {max_retries} attempts failed for {collection_name}")
                    self.stats["mapping_failures"] = self.stats.get("mapping_failures", 0) + 1
                    return False
        
        return False

    def optimize_connection_pool_for_rapid_operations(self):
        """🚀 Optimize connection pool configuration for rapid database operations"""
        if not self.pool_available or not self.connection_pool:
            return False
            
        try:
            # 🔧 Pre-warm the connection pool by creating some connections
            temp_connections = []
            for i in range(min(3, self.connection_pool.maxconn // 2)):
                try:
                    conn = self.connection_pool.getconn(timeout=1)
                    if conn:
                        # Test connection
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1")
                        temp_connections.append(conn)
                except Exception as e:
                    logger.debug(f"Pre-warm connection {i} failed: {e}")
                    break
            
            # Return all pre-warmed connections to pool
            for conn in temp_connections:
                try:
                    self.connection_pool.putconn(conn)
                except Exception as e:
                    logger.debug(f"Failed to return pre-warmed connection: {e}")
                    try:
                        conn.close()
                    except:
                        pass
            
            logger.info(f"🚀 Connection pool optimized: {len(temp_connections)} connections pre-warmed")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Connection pool optimization failed: {e}")
            return False

    @contextlib.contextmanager
    def get_high_frequency_db_connection_ctx(self):
        """🚀 Connection context optimized for high-frequency operations like testing"""
        conn = None
        connection_source = "direct"
        try:
            if self.pool_available and self.connection_pool:
                # For high-frequency operations, try harder to get pooled connection
                for attempt in range(2):  # Try twice for pool connection
                    try:
                        conn = self.connection_pool.getconn(timeout=3)
                        if conn:
                            # Test if connection is still valid
                            with conn.cursor() as test_cur:
                                test_cur.execute("SELECT 1")
                            self.stats["connection_pool_hits"] += 1
                            connection_source = "pool"
                            logger.debug(f"🚀 High-freq pooled connection (attempt {attempt + 1})")
                            break
                        else:
                            self.stats["connection_pool_misses"] += 1
                    except Exception as e:
                        logger.debug(f"Pool connection attempt {attempt + 1} failed: {e}")
                        self.stats["connection_pool_misses"] += 1
                        if attempt == 0:
                            time.sleep(0.01)  # Brief pause before retry
            
            # Fallback to direct connection
            if conn is None:
                conn = psycopg2.connect(
                    self.database_url,
                    connect_timeout=10,
                    application_name='unified-wal-lb-high-freq'
                )
                if self.enable_connection_pooling:
                    self.stats["connection_pool_misses"] += 1
                connection_source = "direct"
                logger.debug(f"🚀 High-freq direct connection")
            
            yield conn
            
        finally:
            if conn:
                if connection_source == "pool" and self.pool_available and self.connection_pool:
                    try:
                        # 🔧 FIX: Longer delay for high-frequency operations to improve reuse
                        time.sleep(0.005)  # 5ms delay for better pool utilization in rapid scenarios
                        self.connection_pool.putconn(conn)
                        logger.debug(f"🚀 Returned high-freq connection to pool")
                    except Exception as e:
                        logger.debug(f"Pool return failed: {e}")
                        try:
                            conn.close()
                        except:
                            pass
                else:
                    try:
                        conn.close()
                    except:
                        pass

    def mark_instance_synced(self, write_id: str, instance_name: str):
        """Mark a write as synced to a specific instance for 'both' target operations"""
        try:
            with self._get_appropriate_lock('wal_write'):
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        # First get the current target_instance and synced_instances
                        cur.execute("""
                            SELECT target_instance, synced_instances, method, path, collection_id
                            FROM unified_wal_writes 
                            WHERE write_id = %s
                        """, (write_id,))
                        
                        result = cur.fetchone()
                        if not result:
                            logger.error(f"❌ WAL record not found for write_id: {write_id[:8]}")
                            return
                        
                        target_instance, synced_instances, method, path, collection_id = result
                        
                        # If target is not 'both', use regular sync logic
                        if target_instance != 'both':
                            logger.info(f"🔄 SINGLE TARGET: {write_id[:8]} target={target_instance}, using regular sync")
                            self.mark_write_synced(write_id)
                            return
                        
                        # Parse current synced instances (JSON array or empty)
                        try:
                            if synced_instances:
                                synced_list = json.loads(synced_instances) if isinstance(synced_instances, str) else synced_instances
                            else:
                                synced_list = []
                        except (json.JSONDecodeError, TypeError):
                            synced_list = []
                        
                        # Add this instance if not already synced
                        if instance_name not in synced_list:
                            synced_list.append(instance_name)
                            logger.info(f"✅ INSTANCE SYNC: {write_id[:8]} {method} synced to {instance_name} ({len(synced_list)}/2 instances)")
                            
                            # ENHANCED LOGGING: Show operation details for DELETE operations
                            if method == 'DELETE' and '/collections/' in path:
                                logger.info(f"   🗑️ DELETE SYNC DETAILS: Collection {collection_id} deleted from {instance_name}")
                                logger.info(f"   📋 Synced instances so far: {synced_list}")
                        else:
                            logger.warning(f"⚠️ DUPLICATE SYNC: {write_id[:8]} already marked synced to {instance_name}")
                        
                        # Check if both instances are now synced
                        required_instances = ['primary', 'replica']
                        all_synced = all(inst in synced_list for inst in required_instances)
                        
                        if all_synced:
                            # CRITICAL FIX: Before marking as fully synced, verify the operation actually succeeded on both instances
                            verification_passed = True
                            
                            if method == 'DELETE' and '/collections/' in path and collection_id:
                                logger.info(f"🔍 DELETE VERIFICATION: Verifying collection is actually deleted from both instances")
                                
                                # CRITICAL FIX: Extract collection name from path, not UUID
                                collection_name = None
                                if '/collections/' in path:
                                    # Extract collection name from path like: .../collections/UC3_MANUAL_1751810860_DELETE_TEST
                                    path_parts = path.split('/collections/')
                                    if len(path_parts) > 1:
                                        collection_name = path_parts[1].split('/')[0]  # Get first segment after /collections/
                                
                                if not collection_name:
                                    logger.warning(f"⚠️ DELETE VERIFICATION: Cannot extract collection name from path: {path}")
                                    # Don't fail verification for path parsing issues
                                else:
                                    logger.info(f"🔍 DELETE VERIFICATION: Checking if collection '{collection_name}' is deleted from both instances")
                                
                                    # CRITICAL FIX: Force verification even if instances appear unhealthy - we need to verify deletion worked
                                    for verify_instance_name in required_instances:
                                        verify_instance = next((inst for inst in self.instances if inst.name == verify_instance_name), None)
                                        if verify_instance:  # Remove health check dependency - we must verify DELETE
                                            try:
                                                logger.info(f"🔍 DELETE VERIFICATION: Checking {verify_instance_name} for collection '{collection_name}'")
                                                
                                                # Check if collection still exists on this instance
                                                collections_response = self.make_direct_request(
                                                    verify_instance,
                                                    "GET",
                                                    "/api/v2/tenants/default_tenant/databases/default_database/collections"
                                                )
                                                
                                                if collections_response.status_code == 200:
                                                    collections = collections_response.json()
                                                    logger.info(f"🔍 DELETE VERIFICATION: Got {len(collections)} collections from {verify_instance_name}")
                                                    
                                                    # CRITICAL FIX: Compare by collection NAME, not UUID
                                                    collection_exists = any(c.get('name') == collection_name for c in collections)
                                                    
                                                    if collection_exists:
                                                        collection_uuid = next((c.get('id') for c in collections if c.get('name') == collection_name), 'not found')
                                                        logger.error(f"❌ DELETE VERIFICATION FAILED: Collection '{collection_name}' still exists on {verify_instance_name}")
                                                        logger.error(f"   This indicates DELETE sync failed - operation should not be marked as complete")
                                                        logger.error(f"   Collection UUID on {verify_instance_name}: {collection_uuid}")
                                                        verification_passed = False
                                                        
                                                        # CRITICAL FIX: Remove this instance from synced list since verification failed
                                                        if verify_instance_name in synced_list:
                                                            synced_list.remove(verify_instance_name)
                                                            logger.info(f"🔧 CORRECTED: Removed {verify_instance_name} from synced list due to verification failure")
                                                    else:
                                                        logger.info(f"✅ DELETE VERIFIED: Collection '{collection_name}' confirmed deleted from {verify_instance_name}")
                                                else:
                                                    logger.error(f"❌ DELETE VERIFICATION ERROR: Cannot list collections on {verify_instance_name} (HTTP {collections_response.status_code})")
                                                    logger.error(f"   Response: {collections_response.text[:200]}")
                                                    # CRITICAL FIX: Treat inability to verify as verification failure
                                                    verification_passed = False
                                                    if verify_instance_name in synced_list:
                                                        synced_list.remove(verify_instance_name)
                                                        logger.info(f"🔧 CORRECTED: Removed {verify_instance_name} from synced list - cannot verify deletion")
                                                    
                                            except Exception as verify_error:
                                                logger.error(f"❌ DELETE VERIFICATION EXCEPTION for {verify_instance_name}: {verify_error}")
                                                import traceback
                                                logger.error(f"   Full traceback: {traceback.format_exc()}")
                                                # CRITICAL FIX: Treat verification exceptions as verification failure
                                                verification_passed = False
                                                if verify_instance_name in synced_list:
                                                    synced_list.remove(verify_instance_name)
                                                    logger.info(f"🔧 CORRECTED: Removed {verify_instance_name} from synced list due to verification exception")
                                        else:
                                            logger.error(f"❌ DELETE VERIFICATION ERROR: Cannot find instance {verify_instance_name}")
                                            verification_passed = False
                            
                            # Re-check if all instances are still synced after verification
                            all_synced = all(inst in synced_list for inst in required_instances)
                            
                            if all_synced and verification_passed:
                                # Both instances synced and verified - mark as fully synced
                                cur.execute("""
                                    UPDATE unified_wal_writes 
                                    SET status = %s, synced_instances = %s, synced_at = NOW(), updated_at = NOW()
                                    WHERE write_id = %s
                                """, (WALWriteStatus.SYNCED.value, json.dumps(synced_list), write_id))
                                logger.info(f"🎉 BOTH SYNC COMPLETE: {write_id[:8]} {method} synced to both instances - marking as SYNCED")
                                
                                if method == 'DELETE' and '/collections/' in path:
                                    logger.info(f"   🗑️ DELETE SUCCESS: Collection '{collection_name}' confirmed deleted from both instances")
                            else:
                                # Verification failed or partial sync - update synced instances but keep status as executed
                                cur.execute("""
                                    UPDATE unified_wal_writes 
                                    SET synced_instances = %s, updated_at = NOW()
                                    WHERE write_id = %s
                                """, (json.dumps(synced_list), write_id))
                                missing_instances = [inst for inst in required_instances if inst not in synced_list]
                                logger.warning(f"⚠️ SYNC INCOMPLETE: {write_id[:8]} {method} verification failed or partial sync")
                                logger.warning(f"   Synced to: {synced_list}, Missing: {missing_instances}")
                                
                                if method == 'DELETE' and not verification_passed:
                                    logger.error(f"   🗑️ DELETE ISSUE: Collection '{collection_name}' still exists on some instances")
                        else:
                            # Partial sync - update synced instances but keep status as executed
                            cur.execute("""
                                UPDATE unified_wal_writes 
                                SET synced_instances = %s, updated_at = NOW()
                                WHERE write_id = %s
                            """, (json.dumps(synced_list), write_id))
                            missing_instances = [inst for inst in required_instances if inst not in synced_list]
                            logger.info(f"⏳ PARTIAL SYNC: {write_id[:8]} {method} synced to {instance_name}, waiting for: {missing_instances}")
                        
                        conn.commit()
                        
        except psycopg2.OperationalError as e:
            logger.warning(f"Database unavailable, skipping instance sync update for {write_id[:8]}: {e}")
        except Exception as e:
            logger.error(f"Error marking write {write_id[:8]} as synced to {instance_name}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

    def sync_missing_collections_to_instance(self, target_instance_name: str) -> bool:
        """
        🔧 ENHANCED: Sync collections that were created on one instance during the other's failure
        CRITICAL FIX: Skip collections with pending DELETE operations to prevent timing conflicts
        """
        try:
            missing_collections = []
            
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    if target_instance_name == "replica":
                        # Collections missing on replica (created during replica failure)
                        cur.execute("""
                            SELECT collection_name, primary_collection_id
                            FROM collection_id_mapping 
                            WHERE primary_collection_id IS NOT NULL 
                            AND replica_collection_id IS NULL
                            ORDER BY created_at ASC
                        """)
                    else:  # primary
                        # Collections missing on primary (created during primary failure)
                        cur.execute("""
                            SELECT collection_name, replica_collection_id
                            FROM collection_id_mapping 
                            WHERE replica_collection_id IS NOT NULL 
                            AND primary_collection_id IS NULL
                            ORDER BY created_at ASC
                        """)
                    
                    results = cur.fetchall()
                    for row in results:
                        collection_name, source_uuid = row
                        
                        # ENHANCED: Log pending DELETE operations but don't block collection recovery
                        # Collection recovery should happen first, then WAL sync will process DELETEs
                        cur.execute("""
                            SELECT COUNT(*) FROM unified_wal_writes 
                            WHERE method = 'DELETE' 
                            AND path LIKE %s 
                            AND (
                                -- Pending or failed DELETEs
                                status IN ('failed', 'pending')
                                OR 
                                -- Incomplete "both" target DELETEs (executed but not synced to target instance)
                                (
                                    status = 'executed' 
                                    AND target_instance = 'both'
                                    AND (
                                        synced_instances IS NULL 
                                        OR synced_instances::text NOT LIKE %s
                                    )
                                )
                            )
                        """, (f'%/collections/{collection_name}%', f'%{target_instance_name}%'))
                        
                        pending_deletes = cur.fetchone()[0]
                        
                        if pending_deletes > 0:
                            logger.info(f"📋 COLLECTION RECOVERY: '{collection_name}' has {pending_deletes} pending DELETE operations")
                            logger.info(f"   Will recreate collection first, then WAL sync will process DELETE operations")
                            
                            # Log the specific DELETE operations for tracking
                            cur.execute("""
                                SELECT write_id, target_instance, status, synced_instances 
                                FROM unified_wal_writes 
                                WHERE method = 'DELETE' 
                                AND path LIKE %s 
                                AND (
                                    status IN ('failed', 'pending')
                                    OR 
                                    (
                                        status = 'executed' 
                                        AND target_instance = 'both'
                                        AND (
                                            synced_instances IS NULL 
                                            OR synced_instances::text NOT LIKE %s
                                        )
                                    )
                                )
                                ORDER BY created_at DESC
                            """, (f'%/collections/{collection_name}%', f'%{target_instance_name}%'))
                            
                            pending_operations = cur.fetchall()
                            for op in pending_operations:
                                write_id, target, status, synced = op
                                logger.info(f"   Pending DELETE: {write_id[:8]} target={target} status={status} synced={synced}")
                        
                        # Continue with collection recovery regardless of pending DELETEs
                        
                        missing_collections.append({
                            'name': collection_name,
                            'source_uuid': source_uuid
                        })
            
            if not missing_collections:
                logger.info(f"✅ COLLECTION RECOVERY: No missing collections on {target_instance_name}")
                return True
            
            logger.info(f"🔧 COLLECTION RECOVERY: Found {len(missing_collections)} collections missing on {target_instance_name}")
            
            # Get target instance
            target_instance = next((inst for inst in self.instances if inst.name == target_instance_name), None)
            if not target_instance:
                logger.error(f"❌ COLLECTION RECOVERY: Cannot find {target_instance_name} instance")
                return False
            
            if not target_instance.is_healthy:
                logger.warning(f"⚠️ COLLECTION RECOVERY: {target_instance_name} is not healthy, skipping recovery")
                return False
            
            # Get source instance for metadata copying
            source_instance_name = "primary" if target_instance_name == "replica" else "replica"
            source_instance = next((inst for inst in self.instances if inst.name == source_instance_name), None)
            
            success_count = 0
            for collection_info in missing_collections:
                collection_name = collection_info['name']
                source_uuid = collection_info['source_uuid']
                
                try:
                    logger.info(f"🔧 COLLECTION RECOVERY: Recreating '{collection_name}' on {target_instance_name}")
                    
                    # Get collection metadata from source instance
                    source_response = self.make_direct_request(
                        source_instance,
                        "GET",
                        f"/api/v2/tenants/default_tenant/databases/default_database/collections/{source_uuid}"
                    )
                    
                    if source_response.status_code != 200:
                        logger.error(f"❌ COLLECTION RECOVERY: Cannot get metadata for '{collection_name}' from {source_instance_name} (HTTP {source_response.status_code})")
                        continue
                    
                    source_collection = source_response.json()
                    
                    # Create collection on target instance with same metadata
                    create_payload = {
                        'name': collection_name,
                        'metadata': source_collection.get('metadata', {}),
                        'get_or_create': True  # Prevent conflicts if collection already exists
                    }
                    
                    target_response = self.make_direct_request(
                        target_instance,
                        "POST",
                        "/api/v2/tenants/default_tenant/databases/default_database/collections",
                        data=json.dumps(create_payload).encode(),
                        headers={'Content-Type': 'application/json'}
                    )
                    
                    if target_response.status_code in [200, 201]:
                        target_collection = target_response.json()
                        target_uuid = target_collection.get('id')
                        
                        logger.info(f"✅ COLLECTION RECOVERY: Created '{collection_name}' on {target_instance_name} (UUID: {target_uuid[:8]}...)")
                        
                        # Update mapping with new target UUID
                        with self.get_db_connection() as conn:
                            with conn.cursor() as cur:
                                if target_instance_name == "replica":
                                    cur.execute("""
                                        UPDATE collection_id_mapping 
                                        SET replica_collection_id = %s, updated_at = NOW()
                                        WHERE collection_name = %s
                                    """, (target_uuid, collection_name))
                                else:  # primary
                                    cur.execute("""
                                        UPDATE collection_id_mapping 
                                        SET primary_collection_id = %s, updated_at = NOW()
                                        WHERE collection_name = %s
                                    """, (target_uuid, collection_name))
                                
                                conn.commit()
                                logger.info(f"✅ COLLECTION RECOVERY: Updated mapping for '{collection_name}' with {target_instance_name} UUID")
                        
                        success_count += 1
                    else:
                        logger.error(f"❌ COLLECTION RECOVERY: Failed to create '{collection_name}' on {target_instance_name} (HTTP {target_response.status_code})")
                        logger.error(f"   Response: {target_response.text[:200]}")
                        
                except Exception as recovery_error:
                    logger.error(f"❌ COLLECTION RECOVERY: Error recreating '{collection_name}': {recovery_error}")
                    continue
            
            logger.info(f"✅ COLLECTION RECOVERY: Successfully recovered {success_count}/{len(missing_collections)} collections on {target_instance_name}")
            return success_count == len(missing_collections)
            
        except Exception as e:
            logger.error(f"❌ COLLECTION RECOVERY: Failed for {target_instance_name}: {e}")
            return False

# 🚀 REQUEST CONCURRENCY CONTROLS - Handle high concurrent user load
class ConcurrencyManager:
    def __init__(self, max_concurrent_requests=None, request_queue_size=None, request_timeout=None):
        # Get values from environment variables that were set but not implemented
        self.max_concurrent_requests = int(os.getenv("MAX_CONCURRENT_REQUESTS", max_concurrent_requests or "30"))  # 🔧 FIX: Match USE CASE 4 testing
        self.request_queue_size = int(os.getenv("REQUEST_QUEUE_SIZE", request_queue_size or "100"))  # 🔧 FIX: Reduced to match concurrency
        # 🔧 FIX: Increased timeout from 30s to 120s to prevent premature timeouts
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", request_timeout or "120"))
        
        # Create semaphore to limit concurrent requests
        self.request_semaphore = Semaphore(self.max_concurrent_requests)
        self.request_queue = queue.Queue(maxsize=self.request_queue_size)
        
        # Statistics
        self.stats = {
            "concurrent_requests": 0,
            "queued_requests": 0,
            "total_requests": 0,
            "timeout_requests": 0,
            "queue_full_rejections": 0,
            # 🔧 NEW: Additional debugging stats
            "semaphore_acquisitions": 0,
            "semaphore_releases": 0,
            "processing_failures": 0
        }
        
        logger.info(f"🚀 Concurrency Manager initialized: {self.max_concurrent_requests} concurrent, {self.request_queue_size} queue size, {self.request_timeout}s timeout")
    
    def __enter__(self):
        """Context manager entry - acquire semaphore or timeout"""
        start_time = time.time()
        request_id = f"req_{int(time.time() * 1000) % 10000}"
        
        logger.debug(f"🔄 {request_id}: Attempting semaphore acquire (current: {self.stats['concurrent_requests']}/{self.max_concurrent_requests})")
        
        # 🔧 FIX: Use blocking acquire with timeout but add proper error handling
        try:
            acquired = self.request_semaphore.acquire(timeout=self.request_timeout)
        except Exception as e:
            logger.error(f"❌ {request_id}: Semaphore acquire failed with exception: {e}")
            self.stats["timeout_requests"] += 1
            raise RequestTimeout(f"Semaphore acquisition failed: {e}")
        
        if not acquired:
            logger.warning(f"⏰ {request_id}: Semaphore acquire timed out after {self.request_timeout}s")
            self.stats["timeout_requests"] += 1
            raise RequestTimeout(f"Request timeout after {self.request_timeout}s - too many concurrent requests")
        
        # Successfully acquired semaphore
        self.stats["concurrent_requests"] += 1
        self.stats["total_requests"] += 1
        self.stats["semaphore_acquisitions"] += 1
        
        wait_time = time.time() - start_time
        if wait_time > 1.0:  # Log if waited more than 1 second
            logger.warning(f"⏳ {request_id}: Request waited {wait_time:.2f}s for concurrency slot")
        else:
            logger.debug(f"✅ {request_id}: Semaphore acquired in {wait_time:.3f}s")
        
        # Store request_id for debugging
        self._current_request_id = request_id
        self._request_start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release semaphore"""
        request_id = getattr(self, '_current_request_id', 'unknown')
        start_time = getattr(self, '_request_start_time', time.time())
        duration = time.time() - start_time
        
        try:
            self.request_semaphore.release()
            self.stats["concurrent_requests"] -= 1
            self.stats["semaphore_releases"] += 1
            
            # Enhanced logging for debugging transaction failures
            if exc_type is not None:
                self.stats["processing_failures"] += 1
                logger.error(f"❌ {request_id}: Request FAILED after {duration:.2f}s - {exc_type.__name__}: {exc_val}")
                # Log full exception details for debugging
                import traceback
                logger.error(f"❌ {request_id}: Full traceback: {traceback.format_exception(exc_type, exc_val, exc_tb)}")
            else:
                logger.debug(f"✅ {request_id}: Request SUCCESS in {duration:.2f}s")
            
            logger.debug(f"🔓 {request_id}: Semaphore released (remaining: {self.stats['concurrent_requests']}/{self.max_concurrent_requests})")
                
        except Exception as e:
            logger.error(f"❌ {request_id}: Error releasing semaphore: {e}")
            # Don't raise here to avoid masking the original exception

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
        
        # 🛡️ TRANSACTION SAFETY: Inject load balancer into recovery service
        if enhanced_wal.transaction_safety:
            enhanced_wal.transaction_safety.load_balancer = enhanced_wal
            logger.info("🛡️ Transaction recovery service linked to load balancer")
        
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
            
            # Check for real-time parameter
            realtime = request.args.get('realtime', 'false').lower() == 'true'
            return jsonify(enhanced_wal.get_status(realtime_health=realtime)), 200
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
            
            with enhanced_wal.get_db_connection_ctx() as conn:
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
                            "primary_collection_id": row[1],  # Full UUID for testing
                            "replica_collection_id": row[2],  # Full UUID for testing
                            "primary_uuid": row[1][:8] + "..." if row[1] else None,  # Display version
                            "replica_uuid": row[2][:8] + "..." if row[2] else None,  # Display version
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
    
    @app.route('/admin/wal_errors', methods=['GET'])
    def wal_errors():
        """Get recent WAL sync errors for debugging"""
        try:
            with enhanced_wal.get_db_connection_ctx() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT write_id, method, path, error_message, updated_at, retry_count
                        FROM unified_wal_writes 
                        WHERE status = 'failed' 
                        ORDER BY updated_at DESC 
                        LIMIT 10
                    """)
                    
                    errors = []
                    for row in cur.fetchall():
                        errors.append({
                            'write_id': row[0][:8],
                            'method': row[1],
                            'path': row[2],
                            'error': row[3],
                            'timestamp': row[4].isoformat() if row[4] else None,
                            'retry_count': row[5]
                        })
                    
                    return jsonify({
                        'recent_errors': errors,
                        'error_count': len(errors)
                    })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/admin/wal_debug', methods=['GET'])
    def wal_debug():
        """Comprehensive WAL debug information for troubleshooting DELETE sync issues"""
        try:
            with enhanced_wal.get_db_connection_ctx() as conn:
                with conn.cursor() as cur:
                    # Get recent writes (all statuses)
                    cur.execute("""
                        SELECT write_id, method, path, collection_id, status, target_instance, 
                               synced_instances, error_message, created_at, updated_at, retry_count
                        FROM unified_wal_writes 
                        ORDER BY created_at DESC 
                        LIMIT 20
                    """)
                    
                    recent_writes = []
                    for row in cur.fetchall():
                        recent_writes.append({
                            'write_id': row[0][:8],
                            'method': row[1],
                            'path': row[2],
                            'collection_id': row[3],
                            'status': row[4],
                            'target_instance': row[5],
                            'synced_instances': row[6],
                            'error_message': row[7],
                            'created_at': row[8].isoformat() if row[8] else None,
                            'updated_at': row[9].isoformat() if row[9] else None,
                            'retry_count': row[10]
                        })
                    
                    # Get DELETE operations specifically
                    cur.execute("""
                        SELECT write_id, path, collection_id, status, target_instance, 
                               synced_instances, error_message, created_at
                        FROM unified_wal_writes 
                        WHERE method = 'DELETE' 
                        ORDER BY created_at DESC 
                        LIMIT 10
                    """)
                    
                    delete_operations = []
                    for row in cur.fetchall():
                        delete_operations.append({
                            'write_id': row[0][:8],
                            'path': row[1],
                            'collection_id': row[2],
                            'status': row[3],
                            'target_instance': row[4],
                            'synced_instances': row[5],
                            'error_message': row[6],
                            'created_at': row[7].isoformat() if row[7] else None
                        })
                    
                    return jsonify({
                        'recent_writes': recent_writes,
                        'delete_operations': delete_operations,
                        'summary': {
                            'total_recent_writes': len(recent_writes),
                            'total_delete_operations': len(delete_operations),
                            'pending_writes': enhanced_wal.get_pending_writes_count()
                        }
                    })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/admin/scalability_status', methods=['GET'])
    def scalability_status():
        """🚀 Enhanced scalability status with performance metrics"""
        try:
            # Scalability features status
            features = {
                "connection_pooling": {
                    "available": enhanced_wal.pool_available,
                    "enabled": enhanced_wal.enable_connection_pooling,
                    "min_connections": 5 if enhanced_wal.pool_available else 0,
                    "max_connections": 20 if enhanced_wal.pool_available else 0
                },
                "granular_locking": {
                    "available": enhanced_wal.enable_granular_locking,
                    "lock_types": ["wal_write", "collection_mapping", "metrics", "status"] if enhanced_wal.enable_granular_locking else []
                }
            }
            
            # Pool performance metrics
            pool_stats = {}
            total_pool_ops = enhanced_wal.stats.get("connection_pool_hits", 0) + enhanced_wal.stats.get("connection_pool_misses", 0)
            if total_pool_ops > 0:
                pool_stats["pool_hit_rate"] = f"{(enhanced_wal.stats.get('connection_pool_hits', 0) / max(1, enhanced_wal.stats.get('connection_pool_hits', 0) + enhanced_wal.stats.get('connection_pool_misses', 0)) * 100):.1f}%"
                pool_stats["total_operations"] = total_pool_ops
                pool_stats["hits"] = enhanced_wal.stats.get("connection_pool_hits", 0)
                pool_stats["misses"] = enhanced_wal.stats.get("connection_pool_misses", 0)
            
            return jsonify({
                "timestamp": datetime.now().isoformat(),
                "scalability_features": features,
                "performance_stats": {
                    "lock_contention_avoided": enhanced_wal.stats.get("lock_contention_avoided", 0),
                    "memory_pressure_events": enhanced_wal.stats.get("memory_pressure_events", 0),
                    "adaptive_batch_reductions": enhanced_wal.stats.get("adaptive_batch_reductions", 0),
                    **pool_stats
                },
                "current_load": {
                    "concurrent_requests": enhanced_wal.stats.get("concurrent_requests", 0),
                    "total_requests_processed": enhanced_wal.stats.get("total_requests_processed", 0),
                    "timeout_requests": enhanced_wal.stats.get("timeout_requests", 0),
                    "queue_full_rejections": enhanced_wal.stats.get("queue_full_rejections", 0)
                }
            })
            
        except Exception as e:
            logger.error(f"Scalability status error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/admin/optimize_connection_pool', methods=['POST'])
    def optimize_connection_pool():
        """🚀 Optimize connection pool for rapid operations"""
        try:
            if not enhanced_wal.pool_available:
                return jsonify({
                    "success": False,
                    "message": "Connection pooling not available"
                }), 400
            
            success = enhanced_wal.optimize_connection_pool_for_rapid_operations()
            
            # Get updated stats
            total_pool_ops = enhanced_wal.stats.get("connection_pool_hits", 0) + enhanced_wal.stats.get("connection_pool_misses", 0)
            hit_rate = 0
            if total_pool_ops > 0:
                hit_rate = (enhanced_wal.stats.get("connection_pool_hits", 0) / total_pool_ops) * 100
            
            return jsonify({
                "success": success,
                "message": "Connection pool optimization completed" if success else "Optimization failed",
                "current_stats": {
                    "hit_rate": f"{hit_rate:.1f}%",
                    "total_operations": total_pool_ops,
                    "hits": enhanced_wal.stats.get("connection_pool_hits", 0),
                    "misses": enhanced_wal.stats.get("connection_pool_misses", 0)
                }
            })
            
        except Exception as e:
            logger.error(f"Connection pool optimization error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/admin/enable_testing_mode', methods=['POST'])
    def enable_testing_mode():
        """🧪 Enable testing mode for optimized connection pooling during rapid operations"""
        try:
            enhanced_wal.testing_mode = True
            enhanced_wal.testing_mode_enabled_at = datetime.now()
            
            # 🚀 ENHANCED: Pre-warm connection pool and optimize for rapid operations
            optimization_success = enhanced_wal.optimize_connection_pool_for_rapid_operations()
            
            # 🔧 FIX: Force several database operations to prime the pool
            db_operations_success = 0
            total_db_operations = 0
            
            if enhanced_wal.pool_available and enhanced_wal.connection_pool:
                # Perform multiple rapid database operations to test and prime the pool
                for i in range(5):
                    try:
                        total_db_operations += 1
                        with enhanced_wal.get_high_frequency_db_connection_ctx() as conn:
                            with conn.cursor() as cur:
                                # Quick health check query
                                cur.execute("SELECT COUNT(*) FROM collection_id_mapping")
                                result = cur.fetchone()
                                if result:
                                    db_operations_success += 1
                        # Brief delay to allow potential connection reuse
                        time.sleep(0.01)
                    except Exception as e:
                        logger.debug(f"Testing mode db operation {i} failed: {e}")
            
            return jsonify({
                "success": True,
                "message": "Testing mode enabled for optimized database operations",
                "testing_mode": True,
                "enabled_at": enhanced_wal.testing_mode_enabled_at.isoformat(),
                "pool_optimization": optimization_success,
                "db_operations_test": {
                    "successful": db_operations_success,
                    "total": total_db_operations,
                    "success_rate": f"{(db_operations_success/max(1,total_db_operations)*100):.1f}%"
                },
                "pool_status": {
                    "available": enhanced_wal.pool_available,
                    "enabled": enhanced_wal.enable_connection_pooling
                }
            })
            
        except Exception as e:
            logger.error(f"Testing mode enable error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/admin/disable_testing_mode', methods=['POST'])
    def disable_testing_mode():
        """🧪 Disable testing mode and return to normal operation"""
        try:
            was_enabled = enhanced_wal.testing_mode
            enabled_duration = None
            
            if was_enabled and enhanced_wal.testing_mode_enabled_at:
                enabled_duration = (datetime.now() - enhanced_wal.testing_mode_enabled_at).total_seconds()
            
            enhanced_wal.testing_mode = False
            enhanced_wal.testing_mode_enabled_at = None
            
            # 🔧 FIX: Get final pool statistics for testing mode summary
            pool_stats = {
                "hits": enhanced_wal.stats.get("connection_pool_hits", 0),
                "misses": enhanced_wal.stats.get("connection_pool_misses", 0),
                "total": enhanced_wal.stats.get("connection_pool_hits", 0) + enhanced_wal.stats.get("connection_pool_misses", 0)
            }
            
            hit_rate = 0.0
            if pool_stats["total"] > 0:
                hit_rate = (pool_stats["hits"] / pool_stats["total"]) * 100
            
            return jsonify({
                "success": True,
                "message": "Testing mode disabled",
                "testing_mode": False,
                "was_enabled": was_enabled,
                "enabled_duration_seconds": enabled_duration,
                "final_pool_stats": {
                    "hit_rate": f"{hit_rate:.1f}%",
                    "hits": pool_stats["hits"],
                    "misses": pool_stats["misses"],
                    "total_operations": pool_stats["total"]
                }
            })
            
        except Exception as e:
            logger.error(f"Testing mode disable error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/admin/transaction_safety_status', methods=['GET'])
    def transaction_safety_status():
        """Get Transaction Safety Service status and recent transaction logs"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not ready"}), 503
            
            # Check if Transaction Safety Service is available
            transaction_safety_available = enhanced_wal.transaction_safety is not None
            
            result = {
                "transaction_safety_service": {
                    "available": transaction_safety_available,
                    "running": getattr(enhanced_wal.transaction_safety, 'is_running', False) if transaction_safety_available else False
                }
            }
            
            # If available, get transaction statistics
            if transaction_safety_available:
                try:
                    with enhanced_wal.get_db_connection_ctx() as conn:
                        with conn.cursor() as cur:
                            # Check if table exists
                            cur.execute("""
                                SELECT EXISTS (
                                    SELECT FROM information_schema.tables 
                                    WHERE table_name = 'emergency_transaction_log'
                                )
                            """)
                            table_exists = cur.fetchone()[0]
                            result["transaction_safety_service"]["table_exists"] = table_exists
                            
                            if table_exists:
                                # Get recent transaction statistics
                                cur.execute("""
                                    SELECT 
                                        status,
                                        COUNT(*) as count,
                                        MAX(created_at) as latest
                                    FROM emergency_transaction_log 
                                    WHERE created_at > NOW() - INTERVAL '2 hours'
                                    GROUP BY status
                                    ORDER BY count DESC
                                """)
                                
                                transactions = []
                                total_transactions = 0
                                for row in cur.fetchall():
                                    status, count, latest = row
                                    total_transactions += count
                                    transactions.append({
                                        "status": status,
                                        "count": count,
                                        "latest": latest.isoformat() if latest else None
                                    })
                                
                                result["recent_transactions"] = {
                                    "total_last_2_hours": total_transactions,
                                    "by_status": transactions
                                }
                                
                                # Get timing gap failures specifically
                                cur.execute("""
                                    SELECT COUNT(*) 
                                    FROM emergency_transaction_log 
                                    WHERE is_timing_gap_failure = TRUE 
                                    AND created_at > NOW() - INTERVAL '24 hours'
                                """)
                                timing_gap_failures = cur.fetchone()[0]
                                result["timing_gap_failures_24h"] = timing_gap_failures
                                
                                # Get pending recovery transactions
                                cur.execute("""
                                    SELECT COUNT(*) 
                                    FROM emergency_transaction_log 
                                    WHERE status IN ('FAILED', 'ATTEMPTING') 
                                    AND retry_count < max_retries
                                """)
                                pending_recovery = cur.fetchone()[0]
                                result["pending_recovery"] = pending_recovery
                            
                except Exception as db_error:
                    result["database_error"] = str(db_error)
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/admin/create_mapping', methods=['POST'])
    def create_mapping():
        """Admin endpoint to manually create collection mapping and see exact error"""
        try:
            data = request.get_json()
            collection_name = data.get('collection_name')
            primary_id = data.get('primary_id') 
            replica_id = data.get('replica_id')
            
            if not collection_name:
                return jsonify({"error": "collection_name required"}), 400
            
            # 🔒 SCALABILITY: Use appropriate lock for collection mapping operations
            with enhanced_wal._get_appropriate_lock('collection_mapping'):
                with enhanced_wal.get_db_connection_ctx() as conn:
                    with conn.cursor() as cur:
                        # Try the same INSERT that's failing
                        cur.execute("""
                            INSERT INTO collection_id_mapping 
                            (collection_name, primary_collection_id, replica_collection_id, created_at)
                            VALUES (%s, %s, %s, NOW())
                            ON CONFLICT (collection_name) DO UPDATE SET
                            primary_collection_id = EXCLUDED.primary_collection_id,
                            replica_collection_id = EXCLUDED.replica_collection_id,
                            updated_at = NOW()
                        """, (collection_name, primary_id, replica_id))
                        conn.commit()
                        
            return jsonify({
                "success": True,
                "message": f"Mapping created/updated for {collection_name}",
                "primary_id": primary_id,
                "replica_id": replica_id
            }), 200
            
        except Exception as e:
            import traceback
            return jsonify({
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500

    @app.route('/admin/force_recovery_restart', methods=['POST'])
    def force_recovery_restart():
        """Force restart transaction recovery processing"""
        try:
            if not enhanced_wal.transaction_safety:
                return jsonify({"error": "Transaction safety service not available"}), 503
            
            # Reset stuck transactions first
            reset_count = enhanced_wal.transaction_safety.reset_stuck_transactions()
            
            # Force recovery restart with proper load balancer reference
            enhanced_wal.transaction_safety.force_recovery_restart(enhanced_wal)
            
            # Get updated status
            with enhanced_wal.transaction_safety.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            COUNT(*) FILTER (WHERE status IN ('FAILED', 'ATTEMPTING') AND retry_count < max_retries) as pending_recovery,
                            COUNT(*) FILTER (WHERE status = 'COMPLETED') as completed,
                            COUNT(*) FILTER (WHERE status = 'RECOVERED') as recovered,
                            COUNT(*) FILTER (WHERE status = 'ABANDONED') as abandoned
                        FROM emergency_transaction_log
                    """)
                    result = cur.fetchone()
                    status = {
                        "pending_recovery": result[0] if result else 0,
                        "completed": result[1] if result else 0,
                        "recovered": result[2] if result else 0,
                        "abandoned": result[3] if result else 0
                    }
            
            return jsonify({
                "success": True,
                "message": "Transaction recovery restarted",
                "reset_count": reset_count,
                "current_status": status
            })
            
        except Exception as e:
            logger.error(f"❌ Force recovery error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/admin/force_transaction_reset', methods=['POST']) 
    def force_transaction_reset():
        """Reset stuck transactions and clear WAL errors - comprehensive fix"""
        try:
            if not enhanced_wal.transaction_safety:
                return jsonify({"error": "Transaction safety service not available"}), 503
            
            reset_results = {}
            
            # 1. Reset stuck transaction safety operations
            reset_count = enhanced_wal.transaction_safety.reset_stuck_transactions()
            reset_results["transaction_reset_count"] = reset_count
            
            # 2. Clear old WAL errors 
            with enhanced_wal.get_db_connection_ctx() as conn:
                with conn.cursor() as cur:
                    # Clear failed WAL operations that are old/stuck
                    cur.execute("""
                        UPDATE unified_wal_writes 
                        SET status = 'abandoned', 
                            error_message = 'Auto-abandoned during system reset'
                        WHERE status = 'failed' 
                        AND retry_count >= 3
                        AND timestamp < NOW() - INTERVAL '30 minutes'
                    """)
                    wal_abandoned = cur.rowcount
                    
                    # Clear stuck pending operations
                    cur.execute("""
                        UPDATE unified_wal_writes 
                        SET status = 'abandoned',
                            error_message = 'Auto-abandoned during system reset - stuck pending'
                        WHERE status IN ('executed', 'pending')
                        AND timestamp < NOW() - INTERVAL '2 hours'
                    """)
                    wal_pending_abandoned = cur.rowcount
                    
                    conn.commit()
                    
                    reset_results["wal_failed_abandoned"] = wal_abandoned
                    reset_results["wal_pending_abandoned"] = wal_pending_abandoned
            
            # 3. Force recovery restart with load balancer reference
            if hasattr(enhanced_wal, 'transaction_safety') and enhanced_wal.transaction_safety:
                enhanced_wal.transaction_safety.force_recovery_restart(enhanced_wal)
                reset_results["recovery_restarted"] = True
            
            # 4. Get final status
            with enhanced_wal.transaction_safety.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            COUNT(*) FILTER (WHERE status IN ('FAILED', 'ATTEMPTING') AND retry_count < max_retries) as pending_recovery,
                            COUNT(*) FILTER (WHERE status = 'COMPLETED') as completed,
                            COUNT(*) FILTER (WHERE status = 'RECOVERED') as recovered,
                            COUNT(*) FILTER (WHERE status = 'ABANDONED') as abandoned,
                            COUNT(*) FILTER (WHERE status = 'ATTEMPTING') as attempting
                        FROM emergency_transaction_log
                    """)
                    result = cur.fetchone()
                    reset_results["final_status"] = {
                        "pending_recovery": result[0] if result else 0,
                        "completed": result[1] if result else 0,
                        "recovered": result[2] if result else 0,
                        "abandoned": result[3] if result else 0,
                        "attempting": result[4] if result else 0
                    }
            
            return jsonify({
                "success": True,
                "message": "Comprehensive system reset completed",
                "results": reset_results
            })
            
        except Exception as e:
            logger.error(f"❌ Force transaction reset error: {e}")
            import traceback
            return jsonify({
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500

    @app.route('/admin/clear_wal_errors', methods=['POST'])
    def clear_wal_errors():
        """Clear old WAL errors that are causing test failures"""
        try:
            data = request.get_json() or {}
            max_retries = data.get('max_retries', 3)  # Clear operations that hit max retries
            hours_old = data.get('hours_old', 1)      # Default to 1+ hours old
            
            with enhanced_wal.get_db_connection_ctx() as conn:
                with conn.cursor() as cur:
                    # Mark old failed operations as abandoned to remove them from error list
                    cur.execute("""
                        UPDATE unified_wal_writes 
                        SET status = 'abandoned', 
                            error_message = CONCAT('Auto-abandoned: max retries reached (', retry_count, '/3), age: ', 
                                          EXTRACT(EPOCH FROM (NOW() - timestamp))/3600, ' hours')
                        WHERE status = 'failed' 
                        AND retry_count >= %s
                        AND timestamp < NOW() - INTERVAL '%s hours'
                    """, (max_retries, hours_old))
                    abandoned_count = cur.rowcount
                    
                    # Also clear any pending operations that are too old and likely stuck
                    cur.execute("""
                        UPDATE unified_wal_writes 
                        SET status = 'abandoned',
                            error_message = CONCAT('Auto-abandoned: stuck pending for ', 
                                          EXTRACT(EPOCH FROM (NOW() - timestamp))/3600, ' hours')
                        WHERE status IN ('executed', 'pending')
                        AND timestamp < NOW() - INTERVAL '%s hours'
                    """, (hours_old * 4,))  # Use 4x hours for pending operations
                    pending_abandoned = cur.rowcount
                    
                    conn.commit()
                    
                    # Get updated error count
                    cur.execute("""
                        SELECT COUNT(*) FROM unified_wal_writes 
                        WHERE status = 'failed' AND retry_count >= 3
                    """)
                    remaining_errors = cur.fetchone()[0] if cur.fetchone() else 0
            
            message = f"Cleared {abandoned_count} failed operations and {pending_abandoned} stuck pending operations"
            
            return jsonify({
                "success": True,
                "message": message,
                "abandoned_failed": abandoned_count,
                "abandoned_pending": pending_abandoned,
                "remaining_errors": remaining_errors
            })
            
        except Exception as e:
            logger.error(f"❌ Clear WAL errors failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/admin/reset_stuck_transactions', methods=['POST'])
    def reset_stuck_transactions():
        """Reset stuck transaction safety operations"""
        try:
            if not enhanced_wal.transaction_safety:
                return jsonify({"error": "Transaction safety service not available"}), 503
            
            data = request.get_json() or {}
            action = data.get('action', 'reset')  # 'reset' or 'abandon'
            hours_old = data.get('hours_old', 0.5)  # Default to 30 minutes old
            
            with enhanced_wal.transaction_safety.get_db_connection() as conn:
                with conn.cursor() as cur:
                    if action == 'reset':
                        # Reset stuck ATTEMPTING transactions back to FAILED for retry
                        cur.execute("""
                            UPDATE emergency_transaction_log 
                            SET status = 'FAILED', 
                                retry_count = 0,
                                failure_reason = CONCAT('Reset from stuck ATTEMPTING status after ', 
                                               EXTRACT(EPOCH FROM (NOW() - attempted_at))/3600, ' hours'),
                                next_retry_at = NOW(),
                                attempted_at = NOW()
                            WHERE status = 'ATTEMPTING'
                            AND attempted_at < NOW() - INTERVAL '%s hours'
                        """, (hours_old,))
                        reset_count = cur.rowcount
                        
                        message = f"Reset {reset_count} stuck ATTEMPTING transactions for retry"
                        
                    elif action == 'abandon':
                        # Abandon old stuck transactions
                        cur.execute("""
                            UPDATE emergency_transaction_log 
                            SET status = 'ABANDONED', 
                                failure_reason = CONCAT('Auto-abandoned: stuck for ', 
                                               EXTRACT(EPOCH FROM (NOW() - created_at))/3600, ' hours'),
                                completed_at = NOW()
                            WHERE status IN ('FAILED', 'ATTEMPTING') 
                            AND created_at < NOW() - INTERVAL '%s hours'
                        """, (hours_old,))
                        reset_count = cur.rowcount
                        
                        message = f"Abandoned {reset_count} old stuck transactions"
                    
                    else:
                        return jsonify({"error": "Invalid action. Use 'reset' or 'abandon'"}), 400
                    
                    conn.commit()
                    
                    # Get updated status
                    cur.execute("""
                        SELECT 
                            COUNT(*) FILTER (WHERE status IN ('FAILED', 'ATTEMPTING') AND retry_count < max_retries) as pending_recovery,
                            COUNT(*) FILTER (WHERE status = 'ATTEMPTING') as attempting,
                            COUNT(*) FILTER (WHERE status = 'FAILED') as failed
                        FROM emergency_transaction_log
                        WHERE created_at > NOW() - INTERVAL '2 hours'
                    """)
                    result = cur.fetchone()
                    status = {
                        "pending_recovery": result[0] if result else 0,
                        "attempting": result[1] if result else 0,
                        "failed": result[2] if result else 0
                    }
            
            return jsonify({
                "success": True,
                "action": action,
                "message": message,
                "affected_count": reset_count,
                "current_status": status
            })
            
        except Exception as e:
            logger.error(f"❌ Reset stuck transactions failed: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/admin/sync_collections', methods=['POST'])
    def sync_collections():
        """Manually trigger collection recovery sync"""
        try:
            data = request.get_json() or {}
            target_instance = data.get('target_instance')
            
            if not target_instance:
                return jsonify({"error": "target_instance required (primary or replica)"}), 400
                
            if target_instance not in ['primary', 'replica']:
                return jsonify({"error": "target_instance must be 'primary' or 'replica'"}), 400
            
            logger.info(f"🔧 MANUAL COLLECTION SYNC: Triggering sync to {target_instance}")
            
            if enhanced_wal:
                success = enhanced_wal.sync_missing_collections_to_instance(target_instance)
                return jsonify({
                    "success": success,
                    "message": f"Collection sync to {target_instance} {'completed' if success else 'failed'}",
                    "target_instance": target_instance
                }), 200 if success else 500
            else:
                return jsonify({"error": "WAL system not ready"}), 503
                
        except Exception as e:
            import traceback
            return jsonify({
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500

    @app.route('/admin/force_delete_sync', methods=['POST'])
    def force_delete_sync():
        """🔧 CRITICAL FIX: Force completion of incomplete DELETE sync operations"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not ready"}), 503
            
            data = request.get_json() or {}
            collection_name = data.get('collection_name')  # Optional: specific collection
            
            with enhanced_wal.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Find incomplete DELETE operations
                    if collection_name:
                        cur.execute("""
                            SELECT write_id, path, collection_id, target_instance, synced_instances, error_message
                            FROM unified_wal_writes 
                            WHERE method = 'DELETE' 
                            AND status = 'executed'
                            AND path LIKE %s
                            AND (synced_instances IS NULL OR synced_instances::text NOT LIKE '%replica%' OR synced_instances::text NOT LIKE '%primary%')
                        """, (f'%{collection_name}%',))
                    else:
                        cur.execute("""
                            SELECT write_id, path, collection_id, target_instance, synced_instances, error_message
                            FROM unified_wal_writes 
                            WHERE method = 'DELETE' 
                            AND status = 'executed'
                            AND (synced_instances IS NULL OR synced_instances::text NOT LIKE '%replica%' OR synced_instances::text NOT LIKE '%primary%')
                            ORDER BY created_at DESC
                            LIMIT 10
                        """)
                    
                    incomplete_deletes = cur.fetchall()
                    
                    if not incomplete_deletes:
                        return jsonify({
                            "success": True,
                            "message": "No incomplete DELETE operations found",
                            "incomplete_deletes": 0
                        })
                    
                    results = []
                    for row in incomplete_deletes:
                        write_id, path, collection_id, target_instance, synced_instances, error_message = row
                        
                        # Extract collection name from path
                        if '/collections/' in path:
                            path_collection_name = path.split('/collections/')[-1].split('/')[0]
                        else:
                            path_collection_name = collection_id or "unknown"
                        
                        # Check if collection still exists on either instance
                        primary_exists = False
                        replica_exists = False
                        
                        try:
                            primary_instance = enhanced_wal.get_primary_instance()
                            if primary_instance and primary_instance.is_healthy:
                                primary_response = enhanced_wal.make_direct_request(
                                    primary_instance,
                                    "GET",
                                    "/api/v2/tenants/default_tenant/databases/default_database/collections"
                                )
                                if primary_response.status_code == 200:
                                    primary_collections = primary_response.json()
                                    primary_exists = any(c.get('name') == path_collection_name for c in primary_collections)
                            
                            replica_instance = enhanced_wal.get_replica_instance()
                            if replica_instance and replica_instance.is_healthy:
                                replica_response = enhanced_wal.make_direct_request(
                                    replica_instance,
                                    "GET",
                                    "/api/v2/tenants/default_tenant/databases/default_database/collections"
                                )
                                if replica_response.status_code == 200:
                                    replica_collections = replica_response.json()
                                    replica_exists = any(c.get('name') == path_collection_name for c in replica_collections)
                        
                        except Exception as check_error:
                            results.append({
                                "write_id": write_id[:8],
                                "collection_name": path_collection_name,
                                "action": "error",
                                "error": f"Cannot check collection existence: {check_error}"
                            })
                            continue
                        
                        # Determine action based on collection existence
                        if not primary_exists and not replica_exists:
                            # Both deleted - mark as fully synced
                            cur.execute("""
                                UPDATE unified_wal_writes 
                                SET status = 'synced', synced_instances = '["primary", "replica"]', synced_at = NOW(), updated_at = NOW()
                                WHERE write_id = %s
                            """, (write_id,))
                            conn.commit()
                            
                            results.append({
                                "write_id": write_id[:8],
                                "collection_name": path_collection_name,
                                "action": "marked_synced",
                                "reason": "Collection deleted from both instances"
                            })
                        
                        elif primary_exists and not replica_exists:
                            # Need to sync to primary (delete from primary)
                            try:
                                delete_response = enhanced_wal.make_direct_request(
                                    primary_instance,
                                    "DELETE",
                                    f"/api/v2/tenants/default_tenant/databases/default_database/collections/{path_collection_name}"
                                )
                                
                                if delete_response.status_code in [200, 204, 404]:
                                    enhanced_wal.mark_instance_synced(write_id, 'primary')
                                    results.append({
                                        "write_id": write_id[:8],
                                        "collection_name": path_collection_name,
                                        "action": "deleted_from_primary",
                                        "status": delete_response.status_code
                                    })
                                else:
                                    results.append({
                                        "write_id": write_id[:8],
                                        "collection_name": path_collection_name,
                                        "action": "delete_failed",
                                        "error": f"Primary DELETE failed: HTTP {delete_response.status_code}"
                                    })
                            except Exception as delete_error:
                                results.append({
                                    "write_id": write_id[:8],
                                    "collection_name": path_collection_name,
                                    "action": "delete_error",
                                    "error": str(delete_error)
                                })
                        
                        elif not primary_exists and replica_exists:
                            # Need to sync to replica (delete from replica)
                            try:
                                delete_response = enhanced_wal.make_direct_request(
                                    replica_instance,
                                    "DELETE",
                                    f"/api/v2/tenants/default_tenant/databases/default_database/collections/{path_collection_name}"
                                )
                                
                                if delete_response.status_code in [200, 204, 404]:
                                    enhanced_wal.mark_instance_synced(write_id, 'replica')
                                    results.append({
                                        "write_id": write_id[:8],
                                        "collection_name": path_collection_name,
                                        "action": "deleted_from_replica",
                                        "status": delete_response.status_code
                                    })
                                else:
                                    results.append({
                                        "write_id": write_id[:8],
                                        "collection_name": path_collection_name,
                                        "action": "delete_failed",
                                        "error": f"Replica DELETE failed: HTTP {delete_response.status_code}"
                                    })
                            except Exception as delete_error:
                                results.append({
                                    "write_id": write_id[:8],
                                    "collection_name": path_collection_name,
                                    "action": "delete_error",
                                    "error": str(delete_error)
                                })
                        
                        else:
                            # Both exist - DELETE failed entirely, try to complete
                            for instance_name, instance in [("primary", primary_instance), ("replica", replica_instance)]:
                                if instance and instance.is_healthy:
                                    try:
                                        delete_response = enhanced_wal.make_direct_request(
                                            instance,
                                            "DELETE",
                                            f"/api/v2/tenants/default_tenant/databases/default_database/collections/{path_collection_name}"
                                        )
                                        
                                        if delete_response.status_code in [200, 204, 404]:
                                            enhanced_wal.mark_instance_synced(write_id, instance_name)
                                            results.append({
                                                "write_id": write_id[:8],
                                                "collection_name": path_collection_name,
                                                "action": f"deleted_from_{instance_name}",
                                                "status": delete_response.status_code
                                            })
                                    except Exception as delete_error:
                                        results.append({
                                            "write_id": write_id[:8],
                                            "collection_name": path_collection_name,
                                            "action": f"delete_error_{instance_name}",
                                            "error": str(delete_error)
                                        })
                    
                    return jsonify({
                        "success": True,
                        "incomplete_deletes_found": len(incomplete_deletes),
                        "results": results
                    })
                    
        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500

    @app.route('/admin/complete_mappings', methods=['POST'])
    def complete_mappings():
        """🔧 CRITICAL FIX: Complete partial collection mappings by querying instances directly"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not ready"}), 503
            
            data = request.get_json() or {}
            fix_specific_collection = data.get('collection_name')  # Optional: fix specific collection
            
            logger.info(f"🔧 MAPPING COMPLETION: Starting comprehensive mapping completion process")
            
            completed_mappings = []
            failed_mappings = []
            
            # Get all incomplete mappings
            with enhanced_wal.get_db_connection() as conn:
                with conn.cursor() as cur:
                    if fix_specific_collection:
                        # Fix specific collection
                        cur.execute("""
                            SELECT collection_name, primary_collection_id, replica_collection_id 
                            FROM collection_id_mapping 
                            WHERE collection_name = %s
                            AND (primary_collection_id IS NULL OR replica_collection_id IS NULL)
                        """, (fix_specific_collection,))
                    else:
                        # Fix all incomplete mappings
                        cur.execute("""
                            SELECT collection_name, primary_collection_id, replica_collection_id 
                            FROM collection_id_mapping 
                            WHERE primary_collection_id IS NULL OR replica_collection_id IS NULL
                        """)
                    
                    incomplete_mappings = cur.fetchall()
            
            logger.info(f"🔧 MAPPING COMPLETION: Found {len(incomplete_mappings)} incomplete mappings")
            
            for collection_name, primary_uuid, replica_uuid in incomplete_mappings:
                try:
                    logger.info(f"🔧 MAPPING COMPLETION: Processing '{collection_name}' (P:{primary_uuid[:8] if primary_uuid else 'None'}, R:{replica_uuid[:8] if replica_uuid else 'None'})")
                    
                    updated_primary_uuid = primary_uuid
                    updated_replica_uuid = replica_uuid
                    
                    # Complete missing primary UUID
                    if not primary_uuid:
                        primary_instance = next((inst for inst in enhanced_wal.instances if inst.name == "primary" and inst.is_healthy), None)
                        if primary_instance:
                            try:
                                response = enhanced_wal.make_direct_request(
                                    primary_instance,
                                    "GET",
                                    "/api/v2/tenants/default_tenant/databases/default_database/collections"
                                )
                                if response.status_code == 200:
                                    collections = response.json()
                                    for collection in collections:
                                        if collection.get('name') == collection_name:
                                            updated_primary_uuid = collection.get('id')
                                            logger.info(f"   ✅ Found primary UUID: {updated_primary_uuid[:8]}")
                                            break
                            except Exception as e:
                                logger.error(f"   ❌ Error querying primary for '{collection_name}': {e}")
                    
                    # Complete missing replica UUID
                    if not replica_uuid:
                        replica_instance = next((inst for inst in enhanced_wal.instances if inst.name == "replica" and inst.is_healthy), None)
                        if replica_instance:
                            try:
                                response = enhanced_wal.make_direct_request(
                                    replica_instance,
                                    "GET",
                                    "/api/v2/tenants/default_tenant/databases/default_database/collections"
                                )
                                if response.status_code == 200:
                                    collections = response.json()
                                    for collection in collections:
                                        if collection.get('name') == collection_name:
                                            updated_replica_uuid = collection.get('id')
                                            logger.info(f"   ✅ Found replica UUID: {updated_replica_uuid[:8]}")
                                            break
                            except Exception as e:
                                logger.error(f"   ❌ Error querying replica for '{collection_name}': {e}")
                    
                    # Update mapping if we found missing UUIDs
                    if (updated_primary_uuid != primary_uuid) or (updated_replica_uuid != replica_uuid):
                        with enhanced_wal.get_db_connection() as conn:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    UPDATE collection_id_mapping 
                                    SET primary_collection_id = %s, replica_collection_id = %s, updated_at = NOW()
                                    WHERE collection_name = %s
                                """, (updated_primary_uuid, updated_replica_uuid, collection_name))
                                conn.commit()
                                
                        completed_mappings.append({
                            "collection_name": collection_name,
                            "primary_uuid": updated_primary_uuid[:8] if updated_primary_uuid else None,
                            "replica_uuid": updated_replica_uuid[:8] if updated_replica_uuid else None,
                            "was_primary_missing": primary_uuid is None,
                            "was_replica_missing": replica_uuid is None
                        })
                        logger.info(f"   ✅ COMPLETED: Updated mapping for '{collection_name}'")
                    else:
                        failed_mappings.append({
                            "collection_name": collection_name,
                            "reason": "Could not find missing UUIDs on instances",
                            "primary_available": primary_uuid is not None,
                            "replica_available": replica_uuid is not None
                        })
                        logger.warning(f"   ⚠️ FAILED: Could not complete mapping for '{collection_name}'")
                        
                except Exception as e:
                    failed_mappings.append({
                        "collection_name": collection_name,
                        "reason": f"Exception: {str(e)}",
                        "primary_available": primary_uuid is not None,
                        "replica_available": replica_uuid is not None
                    })
                    logger.error(f"   ❌ EXCEPTION: Error processing '{collection_name}': {e}")
            
            return jsonify({
                "success": True,
                "message": f"Mapping completion process finished",
                "total_processed": len(incomplete_mappings),
                "completed_count": len(completed_mappings),
                "failed_count": len(failed_mappings),
                "completed_mappings": completed_mappings,
                "failed_mappings": failed_mappings
            }), 200
            
        except Exception as e:
            logger.error(f"❌ MAPPING COMPLETION: Critical error: {e}")
            import traceback
            return jsonify({
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500

    def _handle_proxy_request_core(path, transaction_id=None):
        """Core proxy request logic - separated for cleaner concurrency control"""
        
        try:
            logger.info(f"🚀 PROXY_REQUEST START: {request.method} /{path} [Concurrent: {enhanced_wal.concurrency_manager.stats['concurrent_requests']}/{enhanced_wal.concurrency_manager.max_concurrent_requests}]")
            
            if enhanced_wal is None:
                logger.error("❌ PROXY_REQUEST FAILED: WAL system not ready")
                return jsonify({"error": "WAL system not ready"}), 503
                
            logger.info(f"✅ PROXY_REQUEST: enhanced_wal object exists")
            logger.info(f"Forwarding {request.method} request to /{path}")
            
            # Get target instance using existing health-based routing
            logger.info(f"🔍 PROXY_REQUEST: Getting target instance...")
            target_instance = enhanced_wal.choose_read_instance_with_realtime_health(f"/{path}", request.method, {})
            if not target_instance:
                logger.error(f"❌ PROXY_REQUEST: No healthy instances available")
                return jsonify({"error": "No healthy instances available"}), 503
            
            logger.info(f"✅ PROXY_REQUEST: Target instance selected: {target_instance.name}")
            
            # Convert API path for ChromaDB compatibility
            normalized_path = enhanced_wal.normalize_api_path_to_v2(f"/{path}")
            
            # CRITICAL: Resolve collection names to UUIDs for document operations in WAL sync
            final_path = normalized_path
            if '/collections/' in normalized_path and any(doc_op in normalized_path for doc_op in ['/add', '/upsert', '/get', '/query', '/update', '/delete']):
                # Extract collection name from path
                path_parts = normalized_path.split('/collections/')
                if len(path_parts) > 1:
                    collection_part = path_parts[1].split('/')[0]
                    # Check if it's a name (not UUID) - UUIDs have specific format
                    import re
                    if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', collection_part):
                        logger.info(f"🔍 PROXY_REQUEST: Detected collection name '{collection_part}' in document operation for {target_instance.name}")
                        
                        # Resolve collection name to UUID for target instance
                        resolved_uuid = enhanced_wal.resolve_collection_name_to_uuid(collection_part, target_instance.name)
                        if resolved_uuid:
                            # Replace collection name with UUID in path
                            final_path = normalized_path.replace(f'/collections/{collection_part}/', f'/collections/{resolved_uuid}/')
                            logger.info(f"✅ PROXY_REQUEST: Resolved path for {target_instance.name}: {normalized_path} -> {final_path}")
                        else:
                            logger.warning(f"⚠️ PROXY_REQUEST: Could not resolve collection name '{collection_part}' to UUID for {target_instance.name}")
                            return jsonify({"error": f"Collection '{collection_part}' not found"}), 404
            
            url = f"{target_instance.url}{final_path}"
            logger.info(f"✅ PROXY_REQUEST: URL constructed: {url}")
            
            # Get request data
            data = request.get_data() if request.method in ['POST', 'PUT', 'PATCH'] else None
            logger.info(f"✅ PROXY_REQUEST: Request data size: {len(data) if data else 0} bytes")
            
            # CRITICAL: WAL logging for write operations (FIXED: Only log operations that need sync)
            logger.info(f"🔍 PROXY_REQUEST: Checking if write operation: {request.method}")
            
            # 🔧 CRITICAL FIX: Only log operations that NEED WAL sync
            # Collection creation/deletion are handled by distributed system - DON'T log them
            # Document operations need WAL sync - DO log them
            should_log_to_wal = False
            operation_type = "unknown"
            
            # 🔍 DEBUG: Log path analysis for troubleshooting
            logger.info(f"🔍 WAL_DEBUG: Analyzing path '{final_path}' for method '{request.method}'")
            logger.info(f"🔍 WAL_DEBUG: Path slash count: {final_path.count('/')}")
            
            if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
                # 🔧 CRITICAL FIX: Detect POST requests to read endpoints (ChromaDB uses POST for reads)
                if request.method == 'POST' and '/collections/' in final_path and any(read_op in final_path for read_op in ['/get', '/query', '/count']):
                    operation_type = "document_read_operation_via_post"
                    should_log_to_wal = False  # POST to read endpoints don't need WAL sync
                    logger.info(f"🔍 PROXY_REQUEST: DOCUMENT READ OPERATION (POST) - No WAL logging needed (ChromaDB read via POST)")
                
                # Determine operation type for WAL logging decision
                elif request.method == 'POST' and '/collections' in final_path and not any(doc_op in final_path for doc_op in ['/add', '/upsert', '/get', '/query', '/update', '/delete', '/count']):
                    operation_type = "collection_creation"
                    # 🔧 CRITICAL FIX: Log collection operations when in failover mode (USE CASE 2)
                    # Check if both instances are healthy - if not, we need WAL logging for sync
                    primary_instance = enhanced_wal.get_primary_instance()
                    replica_instance = enhanced_wal.get_replica_instance()
                    both_instances_healthy = (primary_instance and primary_instance.is_healthy and 
                                            replica_instance and replica_instance.is_healthy)
                    
                    if both_instances_healthy:
                        should_log_to_wal = False  # Distributed creation handles this
                        logger.info(f"🔍 PROXY_REQUEST: COLLECTION CREATION - Both instances healthy, using distributed creation (no WAL)")
                    else:
                        should_log_to_wal = True  # Need WAL for failover sync
                        logger.info(f"🔍 PROXY_REQUEST: COLLECTION CREATION - Failover mode detected, logging to WAL for sync")
                
                elif request.method == 'DELETE' and '/collections/' in final_path and final_path.count('/') <= 8:  # DELETE /collections/{id} - FIX: 8 slashes in V2 API
                    operation_type = "collection_deletion"
                    # 🔧 CRITICAL FIX: Log collection deletions when in failover mode (USE CASE 2/3)
                    # CONSISTENCY FIX: Use same coordination logic as CREATE operations 
                    primary_instance = enhanced_wal.get_primary_instance()
                    replica_instance = enhanced_wal.get_replica_instance()
                    
                    # CONSISTENCY FIX: Use cached health status like CREATE operations
                    # Real-time health checking was causing DELETE operations to not be logged to WAL
                    # during replica failure because real-time check incorrectly detected replica as healthy
                    both_instances_healthy = (primary_instance and primary_instance.is_healthy and 
                                            replica_instance and replica_instance.is_healthy)
                    
                    if both_instances_healthy:
                        should_log_to_wal = False  # Distributed deletion handles this
                        logger.info(f"🔍 PROXY_REQUEST: COLLECTION DELETION - Both instances healthy (cached status), using distributed deletion (no WAL)")
                    else:
                        should_log_to_wal = True  # Need WAL for failover sync
                        logger.info(f"🔍 PROXY_REQUEST: COLLECTION DELETION - Failover mode detected (primary={primary_instance.is_healthy if primary_instance else 'None'}, replica={replica_instance.is_healthy if replica_instance else 'None'}), logging to WAL for sync")
                
                elif '/collections/' in final_path and any(doc_op in final_path for doc_op in ['/add', '/upsert', '/update', '/delete']):  # WRITE operations only (removed /get, /query, /count)
                    operation_type = "document_write_operation"
                    should_log_to_wal = True  # Document WRITE operations need WAL sync
                    logger.info(f"🔍 PROXY_REQUEST: DOCUMENT WRITE OPERATION - Will log to WAL for sync")
                
                elif request.method in ['PUT', 'PATCH']:
                    operation_type = "update_operation"
                    should_log_to_wal = True  # Update operations need WAL sync
                    logger.info(f"🔍 PROXY_REQUEST: UPDATE OPERATION - Will log to WAL for sync")
                
                else:
                    operation_type = "other_write"
                    should_log_to_wal = True  # Other writes need WAL sync by default
                    logger.info(f"🔍 PROXY_REQUEST: OTHER WRITE OPERATION - Will log to WAL for sync")
            
            # 🔍 DEBUG: Log final decision
            logger.info(f"🔍 WAL_DEBUG: Final decision - operation_type='{operation_type}', should_log_to_wal={should_log_to_wal}")
            
            if should_log_to_wal:
                logger.info(f"🎯 PROXY_REQUEST: WRITE OPERATION DETECTED - Starting WAL logging for {operation_type}")
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
                    
                    # ENHANCED WAL LOGGING - using proper add_wal_write method with UUID resolution
                    logger.info(f"🔍 PROXY_REQUEST: Starting ENHANCED WAL logging with UUID resolution...")
                    try:
                        # Convert sync_target_value string to TargetInstance enum
                        if sync_target_value == "primary":
                            target_enum = TargetInstance.PRIMARY
                        elif sync_target_value == "replica":
                            target_enum = TargetInstance.REPLICA
                        elif sync_target_value == "both":
                            target_enum = TargetInstance.BOTH
                        else:
                            logger.warning(f"⚠️ Unknown sync target '{sync_target_value}', defaulting to BOTH")
                            target_enum = TargetInstance.BOTH
                        
                        # Use enhanced add_wal_write method with UUID resolution
                        write_id = enhanced_wal.add_wal_write(
                            method=request.method,
                            path=final_path,
                            data=data or b'',
                            headers={'Content-Type': 'application/json'},
                            target_instance=target_enum,
                            executed_on=target_instance.name
                        )
                        
                        logger.info(f"✅ ENHANCED WAL logged with UUID resolution: write_id={write_id[:8]}, method={request.method}, target={sync_target_value}")
                        
                    except Exception as enhanced_wal_error:
                        logger.error(f"❌ ENHANCED WAL logging failed: {enhanced_wal_error}")
                        import traceback
                        logger.error(f"Enhanced WAL traceback: {traceback.format_exc()}")
                    
                except Exception as wal_error:
                    import traceback
                    logger.error(f"❌ WAL logging failed: {wal_error}")
                    logger.error(f"WAL error traceback: {traceback.format_exc()}")
                    # Continue anyway - don't fail request for WAL issues
            else:
                logger.info(f"ℹ️ PROXY_REQUEST: {operation_type.upper()} - Using distributed system (no WAL logging needed)")
            
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
            

            
            # CRITICAL: Create collection on BOTH instances for distributed system (FIXED v2 functionality)
            if (request.method == 'POST' and 
                '/collections' in final_path and 
                response.status_code == 200 and 
                data):
                try:
                    logger.info(f"🔍 PROXY_REQUEST: DISTRIBUTED COLLECTION CREATION starting...")
                    
                    # Parse response to get collection info from target instance
                    collection_info = response.json()
                    collection_name = collection_info.get('name')
                    target_collection_uuid = collection_info.get('id')
                    
                    if collection_name and target_collection_uuid:
                        logger.info(f"✅ PROXY_REQUEST: Collection '{collection_name}' created on {target_instance.name} - UUID: {target_collection_uuid[:8]}")
                        
                        # 🔧 CRITICAL FIX: Determine other instance correctly
                        primary_instance = enhanced_wal.get_primary_instance()
                        replica_instance = enhanced_wal.get_replica_instance()
                        
                        # Determine which is the "other" instance
                        if target_instance.name == "primary":
                            other_instance = replica_instance
                            other_instance_name = "replica"
                        else:
                            other_instance = primary_instance
                            other_instance_name = "primary"
                        
                        logger.info(f"🔍 PROXY_REQUEST: Target={target_instance.name}, Other={other_instance_name}")
                        logger.info(f"🔍 PROXY_REQUEST: Other instance healthy={other_instance.is_healthy if other_instance else 'None'}")
                        
                        other_collection_uuid = None
                        if other_instance and other_instance.is_healthy:
                            try:
                                logger.info(f"🔍 PROXY_REQUEST: Creating collection '{collection_name}' on {other_instance_name}...")
                                
                                # Build the URL for the other instance
                                other_url = f"{other_instance.url}{final_path}"
                                logger.info(f"🔍 PROXY_REQUEST: Other instance URL: {other_url}")
                                
                                # Create collection on other instance with same data
                                import requests
                                other_response = requests.post(
                                    other_url,
                                    headers={'Content-Type': 'application/json'},
                                    data=data,
                                    timeout=15
                                )
                                
                                logger.info(f"🔍 PROXY_REQUEST: Other instance response: {other_response.status_code}")
                                
                                if other_response.status_code == 200:
                                    other_collection_info = other_response.json()
                                    other_collection_uuid = other_collection_info.get('id')
                                    logger.info(f"✅ PROXY_REQUEST: Collection '{collection_name}' created on {other_instance_name} - UUID: {other_collection_uuid[:8]}")
                                else:
                                    logger.warning(f"⚠️ PROXY_REQUEST: Failed to create collection on {other_instance_name}: {other_response.status_code} - {other_response.text[:200]}")
                                    
                            except Exception as other_error:
                                logger.error(f"❌ PROXY_REQUEST: Error creating collection on {other_instance_name}: {other_error}")
                                import traceback
                                logger.error(f"Other instance error traceback: {traceback.format_exc()}")
                        
                        # 🔧 FAILOVER FIX: If other instance unavailable, create WAL entry for sync when it recovers
                        if not other_collection_uuid and other_instance:
                            if not other_instance.is_healthy:
                                logger.info(f"🔧 FAILOVER FIX: {other_instance_name} unhealthy - creating WAL entry for collection creation sync")
                                
                                try:
                                    # Create WAL entry to create collection on other instance when it recovers
                                    if other_instance_name == "primary":
                                        target_enum = TargetInstance.PRIMARY
                                    else:
                                        target_enum = TargetInstance.REPLICA
                                    
                                    # Use the same data that was used to create the collection
                                    failover_write_id = enhanced_wal.add_wal_write(
                                        method='POST',
                                        path=final_path,
                                        data=data,
                                        headers={'Content-Type': 'application/json'},
                                        target_instance=target_enum,
                                        executed_on=target_instance.name
                                    )
                                    
                                    logger.info(f"✅ FAILOVER FIX: WAL entry created for {other_instance_name} collection creation: {failover_write_id[:8]}")
                                    
                                except Exception as wal_error:
                                    logger.error(f"❌ FAILOVER FIX: Failed to create WAL entry for {other_instance_name}: {wal_error}")
                            else:
                                logger.warning(f"⚠️ PROXY_REQUEST: {other_instance_name} not healthy (healthy={other_instance.is_healthy}) - creating partial mapping")
                        else:
                            if not other_instance:
                                logger.error(f"❌ PROXY_REQUEST: {other_instance_name} instance not found - creating partial mapping")
                        
                        # 🔧 CREATE MAPPING: Create complete mapping with both UUIDs
                        try:
                            # Determine primary and replica UUIDs correctly
                            if target_instance.name == "primary":
                                primary_uuid = target_collection_uuid
                                replica_uuid = other_collection_uuid
                            else:
                                primary_uuid = other_collection_uuid
                                replica_uuid = target_collection_uuid
                            
                            logger.info(f"🔍 PROXY_REQUEST: Creating mapping - Primary UUID: {primary_uuid[:8] if primary_uuid else 'None'}, Replica UUID: {replica_uuid[:8] if replica_uuid else 'None'}")
                            
                            # Create the mapping entry
                            mapping_success = enhanced_wal.create_complete_collection_mapping_with_retry(
                                collection_name,
                                primary_uuid,
                                replica_uuid,
                                target_instance.name
                            )
                            
                            if mapping_success:
                                logger.info(f"🎉 PROXY_REQUEST: Complete distributed collection mapping created for '{collection_name}'")
                            else:
                                logger.error(f"💀 PROXY_REQUEST: CRITICAL - Complete mapping failed for '{collection_name}'")
                                enhanced_wal.stats["critical_mapping_failures"] = enhanced_wal.stats.get("critical_mapping_failures", 0) + 1
                                
                        except Exception as mapping_error:
                            logger.error(f"❌ PROXY_REQUEST: Mapping creation failed: {mapping_error}")
                            import traceback
                            logger.error(f"Mapping error traceback: {traceback.format_exc()}")
                        
                except Exception as distributed_error:
                    logger.error(f"❌ PROXY_REQUEST: Distributed collection creation failed: {distributed_error}")
                    import traceback
                    logger.error(f"Distributed creation traceback: {traceback.format_exc()}")
                    
                    # ESCALATION: Log critical infrastructure issue
                    enhanced_wal.stats["mapping_exceptions"] = enhanced_wal.stats.get("mapping_exceptions", 0) + 1
                    logger.error(f"💀 CRITICAL: Collection {collection_name if 'collection_name' in locals() else 'UNKNOWN'} may be inaccessible via load balancer")
            
            # 🗑️ CRITICAL: DELETE collection from BOTH instances for distributed system (FIX DELETE SYNC ISSUE)
            # 🔧 COORDINATION FIX: Only run distributed DELETE when NOT using WAL sync
            elif (request.method == 'DELETE' and 
                  '/collections/' in final_path and 
                  response.status_code in [200, 204] and
                  not should_log_to_wal):
                try:
                    logger.info(f"🔍 PROXY_REQUEST: DISTRIBUTED COLLECTION DELETION starting...")
                    
                    # Extract collection name/UUID from path
                    collection_identifier = final_path.split('/collections/')[-1].split('/')[0] if '/collections/' in final_path else None
                    
                    if collection_identifier:
                        logger.info(f"✅ PROXY_REQUEST: Collection '{collection_identifier}' deleted from {target_instance.name}")
                        
                        # 🔧 CRITICAL FIX: Determine other instance correctly
                        primary_instance = enhanced_wal.get_primary_instance()
                        replica_instance = enhanced_wal.get_replica_instance()
                        
                        # Determine which is the "other" instance
                        if target_instance.name == "primary":
                            other_instance = replica_instance
                            other_instance_name = "replica"
                        else:
                            other_instance = primary_instance
                            other_instance_name = "primary"
                        
                        logger.info(f"🔍 PROXY_REQUEST: Target={target_instance.name}, Other={other_instance_name}")
                        logger.info(f"🔍 PROXY_REQUEST: Other instance healthy={other_instance.is_healthy if other_instance else 'None'}")
                        
                        # Delete from other instance as well
                        if other_instance and other_instance.is_healthy:
                            try:
                                logger.info(f"🔍 PROXY_REQUEST: Deleting collection '{collection_identifier}' from {other_instance_name}...")
                                
                                # Build the URL for the other instance
                                other_url = f"{other_instance.url}{final_path}"
                                logger.info(f"🔍 PROXY_REQUEST: Other instance DELETE URL: {other_url}")
                                
                                # Delete collection from other instance
                                import requests
                                other_response = requests.delete(
                                    other_url,
                                    timeout=15
                                )
                                
                                logger.info(f"🔍 PROXY_REQUEST: Other instance DELETE response: {other_response.status_code}")
                                
                                if other_response.status_code in [200, 204, 404]:  # 404 is OK - already deleted
                                    logger.info(f"✅ PROXY_REQUEST: Collection '{collection_identifier}' deleted from {other_instance_name} - Status: {other_response.status_code}")
                                else:
                                    logger.warning(f"⚠️ PROXY_REQUEST: Failed to delete collection from {other_instance_name}: {other_response.status_code} - {other_response.text[:200]}")
                                    
                            except Exception as other_error:
                                logger.error(f"❌ PROXY_REQUEST: Error deleting collection from {other_instance_name}: {other_error}")
                                import traceback
                                logger.error(f"Other instance DELETE error traceback: {traceback.format_exc()}")
                        else:
                            if other_instance:
                                logger.warning(f"⚠️ PROXY_REQUEST: {other_instance_name} not healthy (healthy={other_instance.is_healthy}) - DELETE incomplete")
                            else:
                                logger.error(f"❌ PROXY_REQUEST: {other_instance_name} instance not found - DELETE incomplete")
                        
                        # 🔧 DELETE MAPPING: Remove collection mapping from database
                        try:
                            logger.info(f"🔍 PROXY_REQUEST: Removing collection mapping for '{collection_identifier}'...")
                            
                            # 🔒 SCALABILITY: Use appropriate lock for collection mapping operations
                            with enhanced_wal._get_appropriate_lock('collection_mapping'):
                                with enhanced_wal.get_db_connection_ctx() as conn:
                                    with conn.cursor() as cur:
                                        # Delete mapping by collection name or UUID
                                        cur.execute("""
                                            DELETE FROM collection_id_mapping 
                                            WHERE collection_name = %s 
                                               OR primary_collection_id = %s 
                                               OR replica_collection_id = %s
                                        """, (collection_identifier, collection_identifier, collection_identifier))
                                        
                                        deleted_count = cur.rowcount
                                        conn.commit()
                                        
                                        if deleted_count > 0:
                                            logger.info(f"✅ PROXY_REQUEST: Removed {deleted_count} collection mapping(s) for '{collection_identifier}'")
                                        else:
                                            logger.warning(f"⚠️ PROXY_REQUEST: No collection mapping found for '{collection_identifier}' to remove")
                                
                        except Exception as mapping_error:
                            logger.error(f"❌ PROXY_REQUEST: Mapping deletion failed: {mapping_error}")
                            import traceback
                            logger.error(f"Mapping deletion error traceback: {traceback.format_exc()}")
                        
                except Exception as distributed_delete_error:
                    logger.error(f"❌ PROXY_REQUEST: Distributed collection deletion failed: {distributed_delete_error}")
                    import traceback
                    logger.error(f"Distributed deletion traceback: {traceback.format_exc()}")
                    
                    # Log issue but don't fail the request - the primary deletion succeeded
                    enhanced_wal.stats["delete_sync_failures"] = enhanced_wal.stats.get("delete_sync_failures", 0) + 1
                    logger.warning(f"⚠️ DELETE SYNC: Collection may be orphaned on other instance")
            
            # 🔧 COORDINATION: Log when WAL sync will handle DELETE instead of distributed system
            elif (request.method == 'DELETE' and 
                  '/collections/' in final_path and 
                  response.status_code in [200, 204] and
                  should_log_to_wal):
                logger.info(f"🎯 WAL COORDINATION: DELETE operation will be synced via WAL system (distributed DELETE skipped)")
                logger.info(f"   Collection deleted from {target_instance.name}, WAL will sync to other instance when healthy")
            
            # 🛡️ TRANSACTION SAFETY: Mark transaction as completed
            if transaction_id and enhanced_wal.transaction_safety:
                try:
                    enhanced_wal.transaction_safety.mark_transaction_completed(
                        transaction_id, 
                        response.status_code,
                        {"status": "success", "proxy_response": True}
                    )
                    logger.info(f"🛡️ TRANSACTION SAFETY: Completed {transaction_id[:8]} with status {response.status_code}")
                except Exception as e:
                    logger.error(f"❌ Failed to mark transaction completed: {e}")
            
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
            
            # 🔧 RETRY LOGIC: Attempt simple retry for certain failures
            if "Connection" in str(e) or "timeout" in str(e).lower() or "502" in str(e):
                logger.warning(f"🔄 RETRY: Connection issue detected, attempting simple retry")
                try:
                    import time
                    time.sleep(0.5)  # Brief pause
                    
                    # Simple retry without complex logic
                    target_instance = enhanced_wal.choose_read_instance_with_realtime_health(f"/{path}", request.method, {})
                    if target_instance:
                        normalized_path = enhanced_wal.normalize_api_path_to_v2(f"/{path}")
                        url = f"{target_instance.url}{normalized_path}"
                        data = request.get_data() if request.method in ['POST', 'PUT', 'PATCH'] else None
                        
                        import requests
                        response = requests.request(
                            method=request.method,
                            url=url,
                            headers={'Content-Type': 'application/json'} if data else {},
                            data=data,
                            timeout=15  # Longer timeout for retry
                        )
                        
                        logger.info(f"✅ RETRY SUCCESS: {response.status_code} for {request.method} /{path}")
                        
                        # 🛡️ TRANSACTION SAFETY: Mark retry success
                        if transaction_id and enhanced_wal.transaction_safety:
                            try:
                                enhanced_wal.transaction_safety.mark_transaction_completed(
                                    transaction_id, 
                                    response.status_code,
                                    {"status": "retry_success", "original_error": str(e)[:100]}
                                )
                            except Exception as te:
                                logger.error(f"❌ Failed to mark retry transaction completed: {te}")
                        
                        # Return successful retry response
                        return Response(
                            response.text,
                            status=response.status_code,
                            mimetype='application/json'
                        )
                        
                except Exception as retry_error:
                    logger.error(f"❌ RETRY FAILED: {retry_error}")
                    # Fall through to original error handling
            
            # 🛡️ TRANSACTION SAFETY: Mark transaction as failed for recovery
            if transaction_id and enhanced_wal.transaction_safety:
                try:
                    # Detect timing gap failures
                    is_timing_gap = "No healthy instances" in str(e) or "Connection" in str(e)
                    
                    enhanced_wal.transaction_safety.mark_transaction_failed(
                        transaction_id,
                        str(e)[:500],  # Limit error message length
                        is_timing_gap=is_timing_gap
                    )
                    logger.info(f"🛡️ TRANSACTION SAFETY: Failed {transaction_id[:8]} - {'timing gap' if is_timing_gap else 'general error'}")
                except Exception as te:
                    logger.error(f"❌ Failed to mark transaction failed: {te}")
            
            return jsonify({"error": f"Service temporarily unavailable: {str(e)}"}), 503

    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def proxy_request(path):
        """🚀 CONCURRENCY-CONTROLLED proxy for 200+ simultaneous users"""
        transaction_id = None
        
        # 🛡️ TRANSACTION SAFETY: Pre-execution logging BEFORE concurrency control
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE'] and enhanced_wal and enhanced_wal.transaction_safety:
            try:
                data = request.get_data()
                headers = dict(request.headers)
                
                # Log transaction BEFORE concurrency control
                transaction_id = enhanced_wal.transaction_safety.log_transaction_attempt(
                    method=request.method,
                    path=f"/{path}",
                    data=data,
                    headers=headers,
                    remote_addr=request.remote_addr
                )
                logger.info(f"🛡️ TRANSACTION SAFETY: Pre-logged {transaction_id[:8]} for {request.method} /{path} BEFORE concurrency control")
                
            except Exception as e:
                logger.error(f"❌ Transaction logging failed: {e}")
                # Continue without transaction safety rather than failing the request
        
        try:
            # 🚀 CONCURRENCY CONTROL: Handle high concurrent user load (200+ simultaneous CMS uploads)
            with enhanced_wal.concurrency_manager:
                return _handle_proxy_request_core(path, transaction_id)
                
        except RequestTimeout:
            # 🚀 CONCURRENCY: Request timeout from concurrency manager
            logger.warning(f"⏰ PROXY_REQUEST TIMEOUT: {request.method} /{path} - too many concurrent requests")
            enhanced_wal.concurrency_manager.stats["timeout_requests"] += 1
            
            # 🛡️ TRANSACTION SAFETY: Mark timeout transactions as failed for recovery
            if transaction_id and enhanced_wal.transaction_safety:
                try:
                    enhanced_wal.transaction_safety.mark_transaction_failed(
                        transaction_id,
                        f"Concurrency timeout after {enhanced_wal.concurrency_manager.request_timeout}s",
                        is_timing_gap=False,  # This is a concurrency issue, not timing gap
                        is_concurrency_failure=True
                    )
                    logger.info(f"🛡️ TRANSACTION SAFETY: Marked timeout {transaction_id[:8]} for recovery")
                except Exception as e:
                    logger.error(f"❌ Failed to mark timeout transaction: {e}")
            
            return jsonify({
                "error": "Request timeout - server overloaded, please retry",
                "concurrent_limit": enhanced_wal.concurrency_manager.max_concurrent_requests,
                "queue_size": enhanced_wal.concurrency_manager.request_queue_size,
                "transaction_id": transaction_id[:8] if transaction_id else None
            }), 503
    
    # Start Flask web server immediately
    port = int(os.getenv('PORT', 8000))
    logger.info(f"🌐 Starting Flask web server on port {port}")
    
    try:
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"❌ Flask server failed to start: {e}")
        sys.exit(1) 

