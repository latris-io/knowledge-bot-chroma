#!/usr/bin/env python3
"""
Enhanced Unified WAL-First Load Balancer with High-Volume Processing
Combines load balancing and bidirectional sync in a single service with PostgreSQL persistence.

DEPLOYMENT TIMESTAMP: 2025-06-17 13:31:00 UTC - CRITICAL FIXES DEPLOYED
- Fixed None return bug in forward_request
- Enhanced production validation test coverage
- Fixed write failover when primary instance down

EMERGENCY DEPLOYMENT: 2025-06-17 22:25:00 UTC - EMERGENCY FALLBACK ACTIVE
- Added emergency direct routing when response content is empty
- Fixed empty response bug with guaranteed content return
- Added comprehensive debugging for response content issues
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

# Configure logging FIRST before any imports that use logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import transaction safety service
try:
    from transaction_safety_service import TransactionSafetyService, TransactionStatus
    TRANSACTION_SAFETY_AVAILABLE = True
    logger.info("✅ Transaction safety service imported successfully")
except ImportError as e:
    logger.warning(f"⚠️ Transaction safety service not available - running without transaction protection: {e}")
    TRANSACTION_SAFETY_AVAILABLE = False
    TransactionSafetyService = None
    TransactionStatus = None

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
        """Initialize the Enhanced Unified WAL Load Balancer"""
        self.instances = [
            ChromaInstance("primary", "https://chroma-primary.onrender.com", priority=1),
            ChromaInstance("replica", "https://chroma-replica.onrender.com", priority=2)
        ]
        
        # High-volume processing configuration
        self.max_memory_usage_mb = int(os.getenv('WAL_MAX_MEMORY_MB', '400'))
        self.max_workers = int(os.getenv('WAL_MAX_WORKERS', '3'))
        self.default_batch_size = int(os.getenv('WAL_DEFAULT_BATCH_SIZE', '50'))
        self.max_batch_size = int(os.getenv('WAL_MAX_BATCH_SIZE', '200'))
        self.request_timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))
        self.sync_interval = int(os.getenv('WAL_SYNC_INTERVAL', '10'))
        self.check_interval = int(os.getenv('HEALTH_CHECK_INTERVAL', '30'))
        self.resource_check_interval = int(os.getenv('RESOURCE_CHECK_INTERVAL', '60'))
        self.read_replica_ratio = float(os.getenv('READ_REPLICA_RATIO', '0.3'))
        
        # Thread-safe database operations
        self.db_lock = threading.RLock()
        
        # Performance statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_wal_writes": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "memory_pressure_events": 0,
            "adaptive_batch_reductions": 0,
            "batches_processed": 0,
            "avg_sync_throughput": 0.0,
            "peak_memory_usage": 0.0,
            "sync_cycles": 0,
            "consistency_overrides": 0
        }
        
        # High-volume processing state
        self.is_syncing = False
        self.current_memory_usage = 0.0
        
        # Database configuration
        self.database_url = os.getenv('DATABASE_URL')
        if not self.database_url:
            raise Exception("DATABASE_URL environment variable not set")
        
        # Initialize transaction safety service
        self.transaction_safety_service = None
        if TRANSACTION_SAFETY_AVAILABLE:
            try:
                self.transaction_safety_service = TransactionSafetyService(self.database_url)
                # FIXED: Remove recursive lambda - transaction safety service handles its own recovery
                logger.info("✅ Transaction safety service initialized")
            except Exception as e:
                logger.error(f"❌ Failed to initialize transaction safety service: {e}")
                self.transaction_safety_service = None
        else:
            logger.warning("⚠️ Transaction safety service not available")
        
        # Initialize database schema and health check instances
        try:
            self._initialize_unified_wal_schema()
            logger.info("✅ Unified WAL schema initialized")
            
            # Initialize transaction safety schema if service is available
            if self.transaction_safety_service:
                self.transaction_safety_service._initialize_schema()
                logger.info("✅ Transaction safety schema initialized")
            
            # Initialize existing collection mappings
            self.initialize_existing_collection_mappings()
            logger.info("✅ Collection mappings initialized")
            
            # Initial health check
            for instance in self.instances:
                try:
                    response = requests.get(f"{instance.url}/api/v2/version", timeout=5)
                    instance.is_healthy = response.status_code == 200
                    if instance.is_healthy:
                        logger.info(f"✅ {instance.name} instance healthy")
                    else:
                        logger.warning(f"❌ {instance.name} instance unhealthy: HTTP {response.status_code}")
                except Exception as e:
                    instance.is_healthy = False
                    logger.warning(f"❌ {instance.name} instance unreachable: {e}")
            
        except Exception as e:
            logger.error(f"❌ Initialization error: {e}")
            # Continue anyway to allow Flask to start

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
        """Initialize WAL database schema with collection mapping support"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Create main WAL table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS unified_wal_writes (
                            write_id VARCHAR(36) PRIMARY KEY,
                            method VARCHAR(10) NOT NULL,
                            path TEXT NOT NULL,
                            data BYTEA,
                            headers JSONB,
                            target_instance VARCHAR(20) NOT NULL,
                            executed_on VARCHAR(20),
                            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
                            error_message TEXT,
                            retry_count INTEGER DEFAULT 0,
                            collection_id VARCHAR(100),
                            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            synced_at TIMESTAMP WITH TIME ZONE,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            data_size_bytes BIGINT,
                            priority INTEGER DEFAULT 0
                        )
                    """)
                    
                    # Create collection ID mapping table for cross-instance sync
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS collection_id_mapping (
                            mapping_id SERIAL PRIMARY KEY,
                            collection_name VARCHAR(255) NOT NULL,
                            primary_collection_id VARCHAR(100),
                            replica_collection_id VARCHAR(100),
                            collection_config JSONB,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            UNIQUE(collection_name)
                        )
                    """)
                    
                    # Create performance metrics table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS wal_performance_metrics (
                            id SERIAL PRIMARY KEY,
                            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            memory_usage_mb FLOAT,
                            memory_percent FLOAT,
                            cpu_percent FLOAT,
                            pending_writes INTEGER,
                            batches_processed INTEGER,
                            sync_throughput_per_sec FLOAT,
                            avg_batch_size INTEGER,
                            memory_pressure_events INTEGER
                        )
                    """)
                    
                    # Create upgrade recommendations table
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS upgrade_recommendations (
                            id SERIAL PRIMARY KEY,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            recommendation_type VARCHAR(50),
                            current_usage FLOAT,
                            recommended_tier VARCHAR(100),
                            reason TEXT,
                            urgency VARCHAR(20),
                            service_component VARCHAR(50)
                        )
                    """)
                    
                    # Create indexes for better performance
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_wal_status_retry ON unified_wal_writes(status, retry_count)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_wal_timestamp ON unified_wal_writes(timestamp)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_wal_target_instance ON unified_wal_writes(target_instance)")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_collection_mapping_name ON collection_id_mapping(collection_name)")
                    
                    conn.commit()
                    logger.info("✅ Unified WAL schema with collection mapping initialized")
                    
        except Exception as e:
            logger.error(f"Error initializing WAL schema: {e}")

    def get_or_create_collection_mapping(self, collection_name: str, source_collection_id: str, 
                                       source_instance: str, collection_config: Optional[Dict] = None) -> Dict[str, str]:
        """Get or create collection ID mapping between primary and replica instances"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Check if mapping already exists
                    cur.execute("""
                        SELECT primary_collection_id, replica_collection_id, collection_config
                        FROM collection_id_mapping 
                        WHERE collection_name = %s
                    """, (collection_name,))
                    
                    result = cur.fetchone()
                    if result:
                        primary_id, replica_id, stored_config = result
                        logger.info(f"📋 Found existing collection mapping for '{collection_name}': primary={primary_id[:8]}..., replica={replica_id[:8]}...")
                        return {
                            'primary_collection_id': primary_id,
                            'replica_collection_id': replica_id,
                            'collection_config': stored_config or {}
                        }
                    
                    # Create new mapping - we know the source, need to create/find the target
                    if source_instance == "primary":
                        primary_id = source_collection_id
                        replica_id = self.ensure_collection_exists_on_instance("replica", collection_name, collection_config)
                    else:
                        replica_id = source_collection_id  
                        primary_id = self.ensure_collection_exists_on_instance("primary", collection_name, collection_config)
                    
                    if primary_id and replica_id:
                        # Store the mapping
                        cur.execute("""
                            INSERT INTO collection_id_mapping 
                            (collection_name, primary_collection_id, replica_collection_id, collection_config)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (collection_name) 
                            DO UPDATE SET 
                                primary_collection_id = EXCLUDED.primary_collection_id,
                                replica_collection_id = EXCLUDED.replica_collection_id,
                                collection_config = EXCLUDED.collection_config,
                                updated_at = NOW()
                        """, (collection_name, primary_id, replica_id, json.dumps(collection_config or {})))
                        conn.commit()
                        
                        logger.info(f"✅ Created collection mapping for '{collection_name}': primary={primary_id[:8]}..., replica={replica_id[:8]}...")
                        return {
                            'primary_collection_id': primary_id,
                            'replica_collection_id': replica_id,
                            'collection_config': collection_config or {}
                        }
                    else:
                        logger.error(f"❌ Failed to create collection mapping for '{collection_name}'")
                        return {}
                        
        except Exception as e:
            logger.error(f"Error managing collection mapping for '{collection_name}': {e}")
            return {}

    def ensure_collection_exists_on_instance(self, instance_name: str, collection_name: str, 
                                           collection_config: Optional[Dict] = None) -> Optional[str]:
        """Ensure collection exists on target instance, create if missing"""
        try:
            instance = next((inst for inst in self.instances if inst.name == instance_name and inst.is_healthy), None)
            if not instance:
                logger.warning(f"⚠️ Instance '{instance_name}' not available for collection creation")
                return None
            
            # First, try to find existing collection by name
            collections_response = requests.get(
                f"{instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=30
            )
            
            if collections_response.status_code == 200:
                collections = collections_response.json()
                for collection in collections:
                    if collection.get('name') == collection_name:
                        collection_id = collection.get('id')
                        logger.info(f"📋 Found existing collection '{collection_name}' on {instance_name}: {collection_id[:8]}...")
                        return collection_id
            
            # Collection doesn't exist, create it
            logger.info(f"🔧 Creating collection '{collection_name}' on {instance_name}...")
            
            # Use provided config or default config
            create_payload = {
                "name": collection_name,
                "configuration": collection_config or {
                    "hnsw": {
                        "space": "l2",
                        "ef_construction": 100,
                        "ef_search": 100,
                        "max_neighbors": 16,
                        "resize_factor": 1.2,
                        "sync_threshold": 1000
                    }
                }
            }
            
            create_response = requests.post(
                f"{instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json=create_payload,
                timeout=30
            )
            
            if create_response.status_code in [200, 201]:
                created_collection = create_response.json()
                collection_id = created_collection.get('id')
                logger.info(f"✅ Created collection '{collection_name}' on {instance_name}: {collection_id[:8]}...")
                return collection_id
            else:
                logger.error(f"❌ Failed to create collection '{collection_name}' on {instance_name}: {create_response.status_code}")
                logger.error(f"Response: {create_response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"Error ensuring collection '{collection_name}' exists on {instance_name}: {e}")
            return None

    def map_collection_id_for_sync(self, original_path: str, target_instance: str) -> str:
        """Map collection ID in path from source instance to target instance - WITH COMPREHENSIVE DEBUGGING"""
        logger.error(f"🔍 COLLECTION MAPPING DEBUG - Starting mapping")
        logger.error(f"   Original path: {original_path}")
        logger.error(f"   Target instance: {target_instance}")
        
        try:
            # Extract collection ID from path
            if '/collections/' not in original_path:
                logger.error(f"   ℹ️ No /collections/ in path - no mapping needed")
                return original_path
            
            path_parts = original_path.split('/collections/')
            if len(path_parts) < 2:
                logger.error(f"   ⚠️ Invalid path structure after split - no mapping possible")
                return original_path
            
            collection_id_and_rest = path_parts[1]
            collection_id = collection_id_and_rest.split('/')[0]
            
            logger.error(f"   📋 Path analysis:")
            logger.error(f"      Path parts: {path_parts}")
            logger.error(f"      Collection ID extracted: {collection_id}")
            logger.error(f"      Collection ID length: {len(collection_id)}")
            
            # 🔧 CRITICAL FIX: Use proper UUID validation instead of flawed length-based heuristic
            import re
            uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
            is_uuid = bool(uuid_pattern.match(collection_id))
            
            logger.error(f"   🔍 UUID validation:")
            logger.error(f"      Collection ID: {collection_id}")
            logger.error(f"      Is valid UUID: {is_uuid}")
            logger.error(f"      Length: {len(collection_id)}")
            
            if is_uuid:
                logger.error(f"   🔍 Collection UUID detected - checking for UUID mapping between instances")
            else:
                logger.error(f"   🔍 Collection NAME detected (not a UUID pattern) - attempting name→UUID mapping")
            
            # First, try to find existing mapping in database
            try:
                logger.error(f"   🔍 Querying database for existing mapping...")
                
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        # Check if we have a mapping for this collection name OR UUID
                        cur.execute("""
                            SELECT collection_name, primary_collection_id, replica_collection_id 
                            FROM collection_id_mapping 
                            WHERE collection_name = %s 
                               OR primary_collection_id = %s 
                               OR replica_collection_id = %s
                        """, (collection_id, collection_id, collection_id))
                        
                        result = cur.fetchone()
                        logger.error(f"   📊 Database query result: {result}")
                        
                        if result:
                            collection_name, primary_id, replica_id = result
                            logger.error(f"   ✅ Found existing mapping:")
                            logger.error(f"      Collection name: {collection_name}")
                            logger.error(f"      Primary ID: {primary_id}")
                            logger.error(f"      Replica ID: {replica_id}")
                            
                            target_collection_id = replica_id if target_instance == "replica" else primary_id
                            logger.error(f"      Target collection ID for {target_instance}: {target_collection_id}")
                            
                            if target_collection_id and target_collection_id != collection_id:
                                mapped_path = original_path.replace(collection_id, target_collection_id)
                                logger.error(f"   🎯 MAPPING SUCCESS:")
                                logger.error(f"      Original: {original_path}")
                                logger.error(f"      Mapped: {mapped_path}")
                                logger.error(f"      ID change: {collection_id} → {target_collection_id}")
                                return mapped_path
                            else:
                                logger.error(f"   ℹ️ No mapping needed:")
                                logger.error(f"      Target ID same as source: {target_collection_id == collection_id}")
                                logger.error(f"      Target ID exists: {target_collection_id is not None}")
                                return original_path
                        else:
                            logger.error(f"   ⚠️ No existing mapping found in database")
                            
            except Exception as e:
                logger.error(f"   ❌ Database mapping lookup failed:")
                logger.error(f"      Error type: {type(e).__name__}")
                logger.error(f"      Error message: {str(e)}")
            
            # 🔧 DYNAMIC MAPPING ENHANCEMENT: Check if collection ID exists anywhere
            logger.error(f"   🔧 No existing mapping - attempting DYNAMIC DISCOVERY")
            
            # FIRST: Try to find collection by the given ID on both instances
            collection_found_on = None
            collection_name = None
            collection_config = None
            
            # PROACTIVE COLLECTION MAPPING REFRESH - Fix for orphaned collection IDs
            logger.error(f"   🚀 PROACTIVE MAPPING REFRESH - Refreshing all mappings due to 404")
            
            # When a collection ID fails (404), proactively refresh ALL collection mappings
            try:
                primary_instance = self.get_primary_instance()
                replica_instance = self.get_replica_instance()
                
                if primary_instance and replica_instance:
                    logger.error(f"   🔍 Querying current collections on both instances")
                    
                    primary_response = requests.get(
                        f"{primary_instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                        timeout=15
                    )
                    
                    replica_response = requests.get(
                        f"{replica_instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                        timeout=15
                    )
                    
                    if primary_response.status_code == 200 and replica_response.status_code == 200:
                        primary_collections = primary_response.json()
                        replica_collections = replica_response.json()
                        
                        primary_by_name = {c['name']: c['id'] for c in primary_collections}
                        replica_by_name = {c['name']: c['id'] for c in replica_collections}
                        
                        logger.error(f"   📊 Found collections - Primary: {len(primary_collections)}, Replica: {len(replica_collections)}")
                        
                        # Update ALL collection mappings with current IDs
                        with self.get_db_connection() as conn:
                            with conn.cursor() as cur:
                                mappings_updated = 0
                                
                                for collection_name in set(primary_by_name.keys()) & set(replica_by_name.keys()):
                                    current_primary_id = primary_by_name[collection_name]
                                    current_replica_id = replica_by_name[collection_name]
                                    
                                    cur.execute("""
                                        INSERT INTO collection_id_mapping 
                                        (collection_name, primary_collection_id, replica_collection_id, collection_config)
                                        VALUES (%s, %s, %s, %s)
                                        ON CONFLICT (collection_name) 
                                        DO UPDATE SET 
                                            primary_collection_id = EXCLUDED.primary_collection_id,
                                            replica_collection_id = EXCLUDED.replica_collection_id,
                                            updated_at = NOW()
                                    """, (collection_name, current_primary_id, current_replica_id, '{}'))
                                    
                                    mappings_updated += 1
                                    logger.error(f"   ✅ Updated mapping for '{collection_name}': {current_primary_id[:8]}... ↔ {current_replica_id[:8]}...")
                                
                                conn.commit()
                                logger.error(f"   🎯 PROACTIVE REFRESH: Updated {mappings_updated} collection mappings")
                                
                                # Now use the first available collection mapping for this request
                                if mappings_updated > 0:
                                    cur.execute("""
                                        SELECT collection_name, primary_collection_id, replica_collection_id 
                                        FROM collection_id_mapping 
                                        LIMIT 1
                                    """)
                                    
                                    mapping_result = cur.fetchone()
                                    if mapping_result:
                                        coll_name, prim_id, repl_id = mapping_result
                                        target_collection_id = repl_id if target_instance == "replica" else prim_id
                                        
                                        mapped_path = original_path.replace(collection_id, target_collection_id)
                                        logger.error(f"   🎯 PROACTIVE MAPPING SUCCESS:")
                                        logger.error(f"      Using collection: {coll_name}")
                                        logger.error(f"      Original: {original_path}")
                                        logger.error(f"      Mapped: {mapped_path}")
                                        logger.error(f"      ID change: {collection_id} → {target_collection_id}")
                                        return mapped_path
                        
            except Exception as e:
                logger.error(f"   ❌ Proactive mapping refresh failed: {e}")
            
            # THIRD: Standard discovery if dynamic mapping didn't work
            logger.error(f"   🔧 Falling back to standard collection discovery")
            
            # Check primary instance
            logger.error(f"   🔍 Checking primary instance for collection...")
            try:
                primary_instance = self.get_primary_instance()
                logger.error(f"   Primary instance available: {primary_instance is not None}")
                
                if primary_instance:
                    primary_url = f"{primary_instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}"
                    logger.error(f"   🌐 Querying primary: {primary_url}")
                    
                    primary_response = requests.get(primary_url, timeout=15)
                    logger.error(f"   📥 Primary response: {primary_response.status_code}")
                    
                    if primary_response.status_code == 200:
                        collection_data = primary_response.json()
                        collection_name = collection_data.get('name')
                        collection_config = collection_data.get('configuration_json', {})
                        collection_found_on = "primary"
                        logger.error(f"   ✅ Found collection on primary:")
                        logger.error(f"      Name: {collection_name}")
                        logger.error(f"      Config: {collection_config}")
                    else:
                        logger.error(f"   ❌ Collection not found on primary: {primary_response.status_code}")
                        if primary_response.text:
                            logger.error(f"      Response body: {primary_response.text[:200]}...")
                else:
                    logger.error(f"   ❌ Primary instance not available")
                    
            except Exception as e:
                logger.error(f"   ❌ Primary collection lookup failed:")
                logger.error(f"      Error type: {type(e).__name__}")
                logger.error(f"      Error message: {str(e)}")
            
            # Check replica instance if not found on primary
            if not collection_found_on:
                logger.error(f"   🔍 Checking replica instance for collection...")
                try:
                    replica_instance = self.get_replica_instance()
                    logger.error(f"   Replica instance available: {replica_instance is not None}")
                    
                    if replica_instance:
                        replica_url = f"{replica_instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}"
                        logger.error(f"   🌐 Querying replica: {replica_url}")
                        
                        replica_response = requests.get(replica_url, timeout=15)
                        logger.error(f"   📥 Replica response: {replica_response.status_code}")
                        
                        if replica_response.status_code == 200:
                            collection_data = replica_response.json()
                            collection_name = collection_data.get('name')
                            collection_config = collection_data.get('configuration_json', {})
                            collection_found_on = "replica"
                            logger.error(f"   ✅ Found collection on replica:")
                            logger.error(f"      Name: {collection_name}")
                            logger.error(f"      Config: {collection_config}")
                        else:
                            logger.error(f"   ❌ Collection not found on replica: {replica_response.status_code}")
                            if replica_response.text:
                                logger.error(f"      Response body: {replica_response.text[:200]}...")
                    else:
                        logger.error(f"   ❌ Replica instance not available")
                        
                except Exception as e:
                    logger.error(f"   ❌ Replica collection lookup failed:")
                    logger.error(f"      Error type: {type(e).__name__}")
                    logger.error(f"      Error message: {str(e)}")
            
            # If we found the collection, create mapping
            if collection_found_on and collection_name:
                logger.error(f"   🔧 Creating collection mapping:")
                logger.error(f"      Collection name: {collection_name}")
                logger.error(f"      Found on: {collection_found_on}")
                logger.error(f"      Source collection ID: {collection_id}")
                
                mapping = self.get_or_create_collection_mapping(
                    collection_name, collection_id, collection_found_on, collection_config
                )
                
                logger.error(f"   📊 Mapping creation result: {mapping}")
                
                if mapping:
                    target_collection_id = mapping.get(f'{target_instance}_collection_id')
                    logger.error(f"   🎯 Target collection ID from mapping: {target_collection_id}")
                    
                    if target_collection_id and target_collection_id != collection_id:
                        mapped_path = original_path.replace(collection_id, target_collection_id)
                        logger.error(f"   ✅ NEW MAPPING SUCCESS:")
                        logger.error(f"      Original: {original_path}")
                        logger.error(f"      Mapped: {mapped_path}")
                        logger.error(f"      ID change: {collection_id} → {target_collection_id}")
                        return mapped_path
                    else:
                        logger.error(f"   ℹ️ No mapping needed after creation:")
                        logger.error(f"      Target ID same as source: {target_collection_id == collection_id}")
                        logger.error(f"      Target ID exists: {target_collection_id is not None}")
                        return original_path
                else:
                    logger.error(f"   ❌ Failed to create mapping - mapping result was None/empty")
            else:
                logger.error(f"   ❌ Collection not found anywhere:")
                logger.error(f"      Found on instance: {collection_found_on}")
                logger.error(f"      Collection name: {collection_name}")
                logger.error(f"      Unable to create mapping")
            
            logger.error(f"   🔄 Returning original path unchanged: {original_path}")
            return original_path
            
        except Exception as e:
            logger.error(f"   ❌ MAPPING ERROR:")
            logger.error(f"      Exception type: {type(e).__name__}")
            logger.error(f"      Exception message: {str(e)}")
            logger.error(f"      Exception details: {repr(e)}")
            logger.error(f"      Returning original path: {original_path}")
            return original_path

    def initialize_existing_collection_mappings(self):
        """Initialize mappings for existing collections that have different IDs"""
        try:
            logger.info("🔧 Initializing existing collection mappings...")
            
            primary_instance = self.get_primary_instance()
            replica_instance = self.get_replica_instance()
            
            if not primary_instance or not replica_instance:
                logger.warning("⚠️ Cannot initialize mappings - instances not available")
                return
            
            # Get collections from both instances
            primary_response = requests.get(
                f"{primary_instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=30
            )
            
            replica_response = requests.get(
                f"{replica_instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=30
            )
            
            if primary_response.status_code != 200 or replica_response.status_code != 200:
                logger.warning("⚠️ Failed to fetch collections for mapping initialization")
                return
            
            primary_collections = primary_response.json()
            replica_collections = replica_response.json()
            
            # Create name-to-ID mappings
            primary_by_name = {c['name']: c for c in primary_collections}
            replica_by_name = {c['name']: c for c in replica_collections}
            
            mappings_created = 0
            
            # Find collections with same name but different IDs
            for collection_name in primary_by_name.keys():
                if collection_name in replica_by_name:
                    primary_collection = primary_by_name[collection_name]
                    replica_collection = replica_by_name[collection_name]
                    
                    primary_id = primary_collection['id']
                    replica_id = replica_collection['id']
                    
                    if primary_id != replica_id:
                        logger.info(f"🔧 Creating mapping for '{collection_name}': {primary_id[:8]}... ↔ {replica_id[:8]}...")
                        
                        # Store mapping in database
                        try:
                            with self.get_db_connection() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("""
                                        INSERT INTO collection_id_mapping 
                                        (collection_name, primary_collection_id, replica_collection_id, collection_config)
                                        VALUES (%s, %s, %s, %s)
                                        ON CONFLICT (collection_name) 
                                        DO UPDATE SET 
                                            primary_collection_id = EXCLUDED.primary_collection_id,
                                            replica_collection_id = EXCLUDED.replica_collection_id,
                                            collection_config = EXCLUDED.collection_config,
                                            updated_at = NOW()
                                    """, (
                                        collection_name, 
                                        primary_id, 
                                        replica_id, 
                                        json.dumps(primary_collection.get('configuration_json', {}))
                                    ))
                                    conn.commit()
                                    mappings_created += 1
                                    logger.info(f"✅ Mapping created for '{collection_name}'")
                        except Exception as e:
                            logger.error(f"❌ Failed to store mapping for '{collection_name}': {e}")
                    else:
                        logger.info(f"🔄 Collection '{collection_name}' has same ID on both instances")
                else:
                    logger.info(f"⚠️ Collection '{collection_name}' only exists on primary")
            
            # Check for collections only on replica
            for collection_name in replica_by_name.keys():
                if collection_name not in primary_by_name:
                    logger.info(f"⚠️ Collection '{collection_name}' only exists on replica")
            
            logger.info(f"✅ Collection mapping initialization completed: {mappings_created} mappings created")
            
        except Exception as e:
            logger.error(f"❌ Error initializing collection mappings: {e}")

    def collect_resource_metrics(self) -> ResourceMetrics:
        """Collect current resource usage metrics - PROCESS-SPECIFIC to prevent false alerts"""
        # CRITICAL FIX: Use process-specific metrics instead of system-wide
        process = psutil.Process()
        
        # Process-specific memory usage
        memory_info = process.memory_info()
        memory_usage_mb = memory_info.rss / 1024 / 1024
        
        # Process-specific CPU usage
        cpu_percent = process.cpu_percent(interval=0.1)
        
        # Calculate memory percentage based on container/service limits
        memory_limit_mb = 1024  # Render.com limit for primary/replica services
        memory_percent = (memory_usage_mb / memory_limit_mb) * 100
        
        return ResourceMetrics(
            memory_usage_mb=memory_usage_mb,
            memory_percent=memory_percent,
            cpu_percent=cpu_percent,
            timestamp=datetime.now()
        )

    def calculate_optimal_batch_size(self, estimated_total_writes: int = 100) -> int:
        """Calculate optimal WAL sync batch size based on current memory usage and volume"""
        current_memory = psutil.virtual_memory()
        available_memory_mb = (self.max_memory_usage_mb - (current_memory.used / 1024 / 1024))
        
        # CRITICAL FIX: Much more aggressive memory pressure handling
        if available_memory_mb < 50:  # Less than 50MB available
            self.stats["memory_pressure_events"] += 1
            batch_size = 1  # Ultra-small batches for critical memory pressure
            logger.error(f"🚨 CRITICAL memory pressure, reducing WAL batch size to {batch_size}")
            return batch_size
        elif available_memory_mb < 100:  # Less than 100MB available
            self.stats["adaptive_batch_reductions"] += 1
            batch_size = 2  # Very small batches
            logger.warning(f"⚠️ High memory pressure, reducing batch size to {batch_size}")
            return batch_size
        elif available_memory_mb < 200:  # Less than 200MB available
            batch_size = min(5, self.default_batch_size // 4)  # Small batches
            logger.info(f"📊 Memory pressure detected, reducing batch size to {batch_size}")
            return batch_size
        elif current_memory.percent > 85:  # High memory percentage
            batch_size = min(10, self.default_batch_size // 2)  # Moderate reduction
            logger.info(f"📊 High memory percentage ({current_memory.percent:.1f}%), batch size: {batch_size}")
            return batch_size
        else:
            # Normal memory conditions
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
                             data_size_bytes, priority)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
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
                            1 if (method == "DELETE" or path.endswith('/delete')) else 0  # DELETE operations and POST /delete get higher priority
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
                        WHERE (status = 'executed' OR status = 'pending') AND retry_count < 3
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
                    # FIXED: Proper logic for document sync from replica to primary and vice versa
                    cur.execute("""
                        SELECT write_id, method, path, data, headers, collection_id, 
                               timestamp, retry_count, data_size_bytes, priority, executed_on
                        FROM unified_wal_writes 
                        WHERE (status = 'pending' OR status = 'executed')
                        AND (
                            -- For PENDING operations (DELETEs), sync to target_instance if it's BOTH or matches
                            (status = 'pending' AND (target_instance = 'both' OR target_instance = %s))
                            OR
                            -- CRITICAL FIX: For EXECUTED operations, sync from source to target
                            (status = 'executed' AND (
                                target_instance = 'both' OR 
                                -- Sync replica→primary: executed on replica, targeting primary
                                (executed_on = 'replica' AND %s = 'primary') OR
                                -- Sync primary→replica: executed on primary, targeting replica  
                                (executed_on = 'primary' AND %s = 'replica')
                            ))
                        )
                        AND retry_count < 3
                        ORDER BY priority DESC, timestamp ASC
                        LIMIT %s
                    """, (target_instance, target_instance, target_instance, batch_size * 3))
                    
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
        """Process a batch of WAL syncs with intelligent collection mapping and auto-creation - WITH COMPREHENSIVE DEBUGGING"""
        logger.error(f"🔍 BATCH DEBUG - Starting batch processing")
        logger.error(f"   Target instance: {batch.target_instance}")
        logger.error(f"   Batch size: {batch.batch_size}")
        logger.error(f"   Estimated memory: {batch.estimated_memory_mb:.1f}MB")
        
        instance = next((inst for inst in self.instances if inst.name == batch.target_instance), None)
        if not instance or not instance.is_healthy:
            logger.error(f"   ❌ Target instance not available or unhealthy: {batch.target_instance}")
            return 0, len(batch.writes)
        
        logger.error(f"   ✅ Target instance available: {instance.name} ({instance.url})")
        
        success_count = 0
        start_memory = psutil.virtual_memory().used / 1024 / 1024
        start_time = time.time()
        
        logger.error(f"   📊 Starting memory usage: {start_memory:.1f}MB")
        logger.error(f"   🕐 Starting time: {datetime.now().isoformat()}")
        
        try:
            for write_index, write_record in enumerate(batch.writes):
                logger.error(f"🔍 WRITE {write_index+1}/{len(batch.writes)} DEBUG - Processing individual write")
                
                try:
                    # Check memory pressure during processing
                    current_memory = psutil.virtual_memory().used / 1024 / 1024
                    if current_memory > self.max_memory_usage_mb * 0.9:  # 90% threshold
                        logger.error(f"   ⚠️ Memory pressure during processing: {current_memory:.1f}MB (limit: {self.max_memory_usage_mb}MB)")
                        gc.collect()  # Force garbage collection
                    
                    # 🔍 DEBUGGING: Extract write record details
                    write_id = write_record['write_id']
                    method = write_record['method']
                    original_path = write_record['path']
                    data = write_record['data'] or b''
                    
                    logger.error(f"   Write ID: {write_id}")
                    logger.error(f"   Method: {method}")
                    logger.error(f"   Original path: {original_path}")
                    logger.error(f"   Data type: {type(data)}")
                    logger.error(f"   Data size: {len(data) if data else 0} chars")
                    if data:
                        # Convert memoryview to bytes for proper logging and processing
                        if isinstance(data, memoryview):
                            data = bytes(data)
                        logger.error(f"   Data preview: {str(data)[:100]}...")
                    
                    # 🔍 DEBUGGING: Headers processing
                    headers = {}
                    if write_record['headers']:
                        logger.error(f"   Raw headers from DB: {write_record['headers']}")
                        logger.error(f"   Headers type: {type(write_record['headers'])}")
                        
                        if isinstance(write_record['headers'], str):
                            try:
                                headers = json.loads(write_record['headers'])
                                logger.error(f"   ✅ Parsed headers from JSON string: {headers}")
                            except Exception as e:
                                logger.error(f"   ❌ Failed to parse headers JSON: {e}")
                                headers = {}
                        else:
                            headers = write_record['headers']
                            logger.error(f"   ✅ Using headers directly: {headers}")
                    else:
                        logger.error(f"   No headers in write record")
                    
                    # INTELLIGENT COLLECTION ID MAPPING
                    logger.error(f"   🔄 Starting collection mapping for path: {original_path}")
                    
                    # CRITICAL FIX: Normalize V1 paths to V2 format first
                    normalized_path = self.normalize_api_path_to_v2(original_path)
                    if normalized_path != original_path:
                        logger.error(f"   🔧 Path normalized: {original_path} → {normalized_path}")
                    
                    mapped_path = self.map_collection_id_for_sync(normalized_path, batch.target_instance)
                    
                    if mapped_path != normalized_path:
                        logger.error(f"   ✅ Path mapped: {normalized_path} → {mapped_path}")
                    else:
                        logger.error(f"   ℹ️ No mapping needed: {normalized_path}")
                    
                    # Use the final normalized and mapped path
                    final_sync_path = mapped_path
                    
                    # Prepare headers for sync request
                    sync_headers = {}
                    if headers:
                        sync_headers = headers.copy()
                    
                    # Always set Content-Type for POST/PUT/PATCH with data
                    if method in ['POST', 'PUT', 'PATCH'] and data:
                        sync_headers['Content-Type'] = 'application/json'
                        logger.error(f"   📝 Added Content-Type header for {method} request")
                    
                    logger.error(f"   Final sync headers: {sync_headers}")
                    
                    # 🔍 DEBUGGING: Make the sync request
                    logger.error(f"   🚀 Initiating sync request...")
                    logger.error(f"      Target: {batch.target_instance}")
                    logger.error(f"      Method: {method}")
                    logger.error(f"      Mapped path: {final_sync_path}")
                    logger.error(f"      Data size: {len(str(data))}")
                    logger.error(f"      Headers: {sync_headers}")
                    
                    response = self.make_direct_request(instance, method, final_sync_path, data=data, headers=sync_headers)
                    
                    # 🔍 DEBUGGING: Success handling
                    logger.error(f"   ✅ SYNC SUCCESS for write {write_id}")
                    logger.error(f"      Response status: {response.status_code}")
                    logger.error(f"      Response size: {len(response.text) if response.text else 0} chars")
                    
                    # Mark as synced
                    self.mark_write_synced(write_id)
                    success_count += 1
                    self.stats["successful_syncs"] += 1
                    
                    logger.error(f"   📊 Updated stats: {self.stats['successful_syncs']} successful syncs total")
                    
                except requests.exceptions.HTTPError as e:
                    logger.error(f"   ❌ HTTP ERROR for write {write_id}:")
                    logger.error(f"      Error type: {type(e).__name__}")
                    logger.error(f"      Status code: {e.response.status_code if e.response else 'unknown'}")
                    logger.error(f"      Error message: {str(e)}")
                    
                    # INTELLIGENT ERROR HANDLING WITH AUTO-COLLECTION CREATION
                    if e.response and e.response.status_code == 404:
                        # Handle 404 errors intelligently based on operation type
                        if method == "DELETE":
            logger.info(f"🗑️ SIMPLIFIED DELETE - trying all healthy instances")
            
            # Get all healthy instances
            healthy_instances = self.get_healthy_instances()
            if not healthy_instances:
                from requests import Response
                error_response = Response()
                error_response.status_code = 503
                error_response._content = json.dumps({
                    "error": "No healthy instances available"
                }).encode()
                logger.error(f"❌ DELETE failed: No healthy instances")
                return error_response
            
            # Try DELETE on all healthy instances using original path
            results = []
            for instance in healthy_instances:
                try:
                    url = f"{instance.url}{path}"
                    logger.info(f"   🔄 DELETE {instance.name}: {url}")
                    
                    response = requests.request(method, url, 
                                              headers=headers or {}, 
                                              data=data, 
                                              timeout=30, 
                                              **kwargs)
                    
                    success = response.status_code in [200, 204, 404]
                    results.append({
                        "instance": instance.name,
                        "status": response.status_code,
                        "success": success
                    })
                    
                    logger.info(f"   {'✅' if success else '❌'} {instance.name}: {response.status_code}")
                    
                except Exception as e:
                    results.append({
                        "instance": instance.name,
                        "error": str(e),
                        "success": False
                    })
                    logger.error(f"   ❌ {instance.name} exception: {e}")
            
            # Success if any instance succeeded
            successful = [r for r in results if r.get("success", False)]
            
            if successful:
                from requests import Response
                success_response = Response()
                success_response.status_code = 200 if len(successful) == len(healthy_instances) else 207
                success_response._content = json.dumps({
                    "success": True,
                    "instances_succeeded": len(successful),
                    "instances_total": len(healthy_instances),
                    "results": results
                }).encode()
                logger.info(f"✅ DELETE success: {len(successful)}/{len(healthy_instances)} instances")
                return success_response
            else:
                from requests import Response
                error_response = Response()
                error_response.status_code = 503
                error_response._content = json.dumps({
                    "error": "DELETE failed on all instances",
                    "results": results
                }).encode()
                logger.error(f"❌ DELETE failed on all {len(healthy_instances)} instances")
                return error_response
        
        # For non-DELETE write operations, log to WAL and execute normally
        elif method in ['POST', 'PUT', 'PATCH']:
            # Determine sync target
            if target_instance.name == "primary":
                sync_target = TargetInstance.REPLICA
            else:
                sync_target = TargetInstance.PRIMARY
            
            # CRITICAL FIX: Properly capture request data for WAL logging
            wal_data = data
            if not wal_data and 'json' in kwargs and kwargs['json']:
                # If we have JSON data but no raw data, serialize JSON for WAL storage
                wal_data = json.dumps(kwargs['json']).encode('utf-8')
                logger.debug(f"🔄 Converted JSON to bytes for WAL: {len(wal_data)} bytes")
            
            # Regular write operations - execute on target and sync to other
            self.add_wal_write(
                method=method,
                path=path,
                data=wal_data,  # Use properly captured data
                headers=headers,
                target_instance=sync_target,
                executed_on=target_instance.name
            )
        
        # Execute the request normally for non-DELETE operations (DELETE handled separately above)
        if method != "DELETE":
            try:
                url = f"{target_instance.url}{path}"
            
                # CRITICAL FIX: Improved request handling with proper headers like make_direct_request
                request_params = {'timeout': self.request_timeout}
                
                # Set proper headers for ChromaDB API compatibility
                if 'headers' not in request_params:
                    request_params['headers'] = {}
                
                # Merge passed headers
                if headers:
                    request_params['headers'].update(headers)
                
                # Set Content-Type and Accept headers for API compatibility
                if method in ['POST', 'PUT', 'PATCH'] and (data or kwargs.get('json')):
                    request_params['headers']['Content-Type'] = 'application/json'
                
                request_params['headers']['Accept'] = 'application/json'
                
                # Add data or json to request parameters
                if data:
                    request_params['data'] = data
                
                # Add other kwargs (including json parameter)
                request_params.update(kwargs)
                
                logger.debug(f"🔄 Forward request: {method} {url} with headers: {request_params['headers']}")
                
                # Make direct request without session (simpler and more reliable)
                response = requests.request(method, url, **request_params)
                
                # Don't raise for status - let the caller handle HTTP errors
                logger.info(f"Response: {response.status_code}, Content: {len(response.content)} bytes")
                
                # CRITICAL FIX: Auto-failover on 5xx server errors
                if response.status_code >= 500:
                    logger.error(f"❌ Server error {response.status_code} from {target_instance.name}, attempting failover...")
                    target_instance.update_stats(False)
                    self.stats["failed_requests"] += 1
                    
                    # Try failover to other healthy instances
                    if retry_count < max_retries:
                        other_instances = [inst for inst in self.get_healthy_instances() if inst != target_instance]
                        if other_instances:
                            logger.warning(f"🔄 FAILOVER: Retrying on {other_instances[0].name} due to 5xx error from {target_instance.name}")
                            return self.forward_request(method, path, headers, data, other_instances[0], retry_count + 1, max_retries, **kwargs)
                    
                    # If no failover possible, return the error response
                    logger.error(f"❌ No failover available for 5xx error from {target_instance.name}")
                    return response
                else:
                    target_instance.update_stats(True)
                    self.stats["successful_requests"] += 1
                
                # 🔧 Auto-create collection mappings when collections are created (simplified)
                if (method == "POST" and "/collections" in path and 
                    response.status_code in [200, 201] and response.content):
                    
                    try:
                        response_data = response.json()
                        collection_name = response_data.get('name')
                        collection_id = response_data.get('id')
                        
                        if collection_name and collection_id:
                            logger.error(f"🔧 AUTO-MAPPING: Collection '{collection_name}' created on {target_instance.name} with ID {collection_id[:8]}...")
                            
                            # Extract collection config from request
                            collection_config = None
                            if 'json' in kwargs and kwargs['json']:
                                collection_config = kwargs['json'].get('configuration', {})
                            
                            # CRITICAL FIX: Create mapping SYNCHRONOUSLY during failover to prevent document operation failures
                            mapping_result = self.get_or_create_collection_mapping(
                                collection_name=collection_name,
                                source_collection_id=collection_id,
                                source_instance=target_instance.name,
                                collection_config=collection_config
                            )
                            
                            if mapping_result:
                                logger.error(f"✅ AUTO-MAPPING SUCCESS: Collection '{collection_name}' mapping created")
                                # CRITICAL FIX: Verify mapping was created correctly for immediate use
                                try:
                                    with self.get_db_connection() as conn:
                                        with conn.cursor() as cur:
                                            cur.execute("""
                                                SELECT primary_collection_id, replica_collection_id 
                                                FROM collection_id_mapping 
                                                WHERE collection_name = %s
                                            """, (collection_name,))
                                            
                                            verify_result = cur.fetchone()
                                            if verify_result:
                                                primary_id, replica_id = verify_result
                                                logger.error(f"✅ MAPPING VERIFIED: {collection_name} → P:{primary_id[:8] if primary_id else 'None'}... R:{replica_id[:8] if replica_id else 'None'}...")
                                            else:
                                                logger.error(f"❌ MAPPING VERIFICATION FAILED: No mapping found for {collection_name}")
                                except Exception as e:
                                    logger.error(f"❌ MAPPING VERIFICATION ERROR: {e}")
                            else:
                                logger.error(f"❌ AUTO-MAPPING FAILED: Could not create mapping for '{collection_name}'")
                                
                    except Exception as e:
                        logger.error(f"❌ AUTO-MAPPING ERROR: Failed to create mapping for collection: {e}")
                
                # CRITICAL FIX: Always return response - no complex emergency fallback logic
                return response
                    
            except Exception as e:
                target_instance.update_stats(False)
                self.stats["failed_requests"] += 1
                
                logger.error(f"❌ Request failed on {target_instance.name}: {e}")
                
                # For critical failures, try other instances (with retry limit)
                if target_instance.consecutive_failures > 2 and retry_count < max_retries:
                    other_instances = [inst for inst in self.get_healthy_instances() if inst != target_instance]
                    if other_instances:
                        logger.warning(f"Retrying request on {other_instances[0].name} due to {target_instance.name} failures (attempt {retry_count + 1}/{max_retries})")
                        return self.forward_request(method, path, headers, data, other_instances[0], retry_count + 1, max_retries)
                
                # CRITICAL FIX: Return proper error response instead of raising exception
                from requests import Response
                error_response = Response()
                error_response.status_code = 503
                error_response._content = json.dumps({
                    "error": f"Service temporarily unavailable: {str(e)}",
                    "instance": target_instance.name
                }).encode()
                logger.error(f"❌ Returning 503 error response for failed request to {target_instance.name}")
                return error_response
        
        # CRITICAL FAILSAFE: If we reach here, something went wrong - return error response
        logger.error(f"❌ CRITICAL: forward_request reached end without returning for {method} /{path}")
        from requests import Response
        error_response = Response()
        error_response.status_code = 503
        error_response._content = json.dumps({"error": "Internal load balancer error: no response generated"}).encode()
        return error_response

    def clear_failed_wal_entries(self, max_age_hours: int = 24):
        """Clear old failed WAL entries to reset sync state"""
        try:
            logger.info(f"🧹 Clearing failed WAL entries older than {max_age_hours} hours...")
            
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Clear old failed entries
                    cur.execute("""
                        DELETE FROM unified_wal_writes 
                        WHERE status = 'failed' 
                        AND retry_count >= 3
                        AND created_at < NOW() - INTERVAL '%s hours'
                    """, (max_age_hours,))
                    
                    deleted_count = cur.rowcount
                    
                    # Reset retry count for recent failed entries to give them another chance
                    cur.execute("""
                        UPDATE unified_wal_writes 
                        SET retry_count = 0, error_message = NULL, updated_at = NOW()
                        WHERE status = 'failed' 
                        AND retry_count < 3
                        AND created_at >= NOW() - INTERVAL '1 hour'
                    """)
                    
                    reset_count = cur.rowcount
                    conn.commit()
                    
                    logger.info(f"✅ WAL cleanup completed: {deleted_count} old entries deleted, {reset_count} recent entries reset")
                    return deleted_count, reset_count
                    
        except Exception as e:
            logger.error(f"❌ Error clearing failed WAL entries: {e}")
            return 0, 0

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
            logger.error(f"🔧 V1→V2 PATH CONVERSION: {path} → {v1_to_v2_mappings[path]}")
            return v1_to_v2_mappings[path]
        
        # Pattern-based conversion for paths with collection IDs/names
        for v1_pattern, v2_pattern in v1_to_v2_mappings.items():
            if path.startswith(v1_pattern) and v1_pattern.endswith("/"):
                # Replace the V1 prefix with V2 prefix, keeping the rest of the path
                converted_path = path.replace(v1_pattern, v2_pattern, 1)
                logger.error(f"🔧 V1→V2 PATH CONVERSION: {path} → {converted_path}")
                return converted_path
        
        # If already V2 format or unknown format, return as-is
        return path

    def find_collection_by_name(self, instance_name: str, collection_name: str) -> Optional[str]:
        """Find collection ID by name on a specific instance - for dynamic mapping"""
        try:
            instance = next((inst for inst in self.instances if inst.name == instance_name and inst.is_healthy), None)
            if not instance:
                return None
            
            # Query collections endpoint
            response = requests.get(
                f"{instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=15
            )
            
            if response.status_code == 200:
                collections = response.json()
                for collection in collections:
                    if collection.get('name') == collection_name:
                        return collection.get('id')
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to find collection '{collection_name}' on {instance_name}: {e}")
            return None
    
    def refresh_stale_collection_mapping(self, collection_id: str, target_instance: str, original_path: str) -> str:
        """Dynamically refresh stale collection mappings by discovering current collection IDs"""
        logger.error(f"🔄 DYNAMIC MAPPING REFRESH for collection ID: {collection_id}")
        
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Check if this collection ID exists in any mapping (might be stale)
                    cur.execute("""
                        SELECT collection_name 
                        FROM collection_id_mapping 
                        WHERE primary_collection_id = %s OR replica_collection_id = %s
                    """, (collection_id, collection_id))
                    
                    stale_mapping = cur.fetchone()
                    if stale_mapping:
                        collection_name = stale_mapping[0]
                        logger.error(f"   📋 Found stale mapping for collection: {collection_name}")
                        
                        # Discover current collection IDs by name
                        current_primary_id = self.find_collection_by_name("primary", collection_name)
                        current_replica_id = self.find_collection_by_name("replica", collection_name)
                        
                        logger.error(f"   🔍 Discovery results:")
                        logger.error(f"      Primary ID: {current_primary_id}")
                        logger.error(f"      Replica ID: {current_replica_id}")
                        
                        if current_primary_id and current_replica_id:
                            # Update mapping with current IDs
                            logger.error(f"   ✅ Updating mapping with current IDs")
                            cur.execute("""
                                UPDATE collection_id_mapping 
                                SET primary_collection_id = %s, replica_collection_id = %s, updated_at = NOW()
                                WHERE collection_name = %s
                            """, (current_primary_id, current_replica_id, collection_name))
                            conn.commit()
                            
                            # Return mapped path with correct ID
                            target_collection_id = current_replica_id if target_instance == "replica" else current_primary_id
                            if target_collection_id != collection_id:
                                mapped_path = original_path.replace(collection_id, target_collection_id)
                                logger.error(f"   🎯 DYNAMIC MAPPING SUCCESS:")
                                logger.error(f"      Collection: {collection_name}")
                                logger.error(f"      Original: {original_path}")
                                logger.error(f"      Mapped: {mapped_path}")
                                logger.error(f"      ID change: {collection_id} → {target_collection_id}")
                                return mapped_path
                            else:
                                logger.error(f"   ℹ️ Collection ID unchanged after refresh")
                                return original_path
                                
                        elif current_primary_id or current_replica_id:
                            logger.error(f"   ⚠️ Collection '{collection_name}' only exists on one instance")
                            # Could attempt to create on missing instance, but for now just log
                            return original_path
                            
                        else:
                            logger.error(f"   ❌ Collection '{collection_name}' no longer exists - removing stale mapping")
                            cur.execute("DELETE FROM collection_id_mapping WHERE collection_name = %s", (collection_name,))
                            conn.commit()
                            logger.error(f"   🗑️ Removed stale mapping for '{collection_name}'")
                            return original_path
                    else:
                        logger.error(f"   ❌ No existing mapping found for collection ID: {collection_id}")
                        return original_path
                        
        except Exception as e:
            logger.error(f"   ❌ Dynamic mapping refresh failed: {e}")
            return original_path

    def forward_request_with_transaction_safety(self, method: str, path: str, headers: Dict[str, str], 
                                              data: bytes = b'', target_instance: Optional[ChromaInstance] = None, 
                                              retry_count: int = 0, max_retries: int = 1, 
                                              original_transaction_id: Optional[str] = None, **kwargs) -> requests.Response:
        """
        Transaction-safe wrapper for forward_request that implements pre-execution logging
        to prevent data loss during timing gaps
        """
        transaction_id = original_transaction_id
        
        # Only log if transaction safety is available and this is a write operation
        if (self.transaction_safety_service and 
            method in ['POST', 'PUT', 'PATCH', 'DELETE'] and 
            not original_transaction_id):  # Don't double-log retry operations
            
            try:
                # Extract client info from Flask request if available
                client_ip = getattr(request, 'remote_addr', 'unknown') if 'request' in globals() else 'unknown'
                
                # Log transaction attempt BEFORE execution
                transaction_id = self.transaction_safety_service.log_transaction_attempt(
                    method=method,
                    path=path,
                    data=data,
                    headers=headers,
                    remote_addr=client_ip,
                    target_instance=target_instance.name if target_instance else None
                )
                
                logger.info(f"🛡️ Transaction {transaction_id[:8]} logged for {method} {path}")
                
            except Exception as e:
                logger.error(f"❌ Failed to log transaction attempt: {e}")
                # Continue without transaction logging rather than failing the request
                transaction_id = None
        
        try:
            # Execute the actual request
            response = self.forward_request(
                method=method,
                path=path,
                headers=headers,
                data=data,
                target_instance=target_instance,
                retry_count=retry_count,
                max_retries=max_retries,
                **kwargs
            )
            
            # Mark transaction as completed if we logged it
            if transaction_id and self.transaction_safety_service:
                try:
                    response_data = None
                    if hasattr(response, 'json'):
                        try:
                            response_data = response.json()
                        except:
                            pass
                    
                    self.transaction_safety_service.mark_transaction_completed(
                        transaction_id=transaction_id,
                        response_status=response.status_code,
                        response_data=response_data
                    )
                    
                    logger.debug(f"✅ Transaction {transaction_id[:8]} completed successfully")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to mark transaction completed: {e}")
            
            return response
            
        except Exception as e:
            # Mark transaction as failed if we logged it
            if transaction_id and self.transaction_safety_service:
                try:
                    # Detect if this is a timing gap failure
                    is_timing_gap = self._is_timing_gap_failure(e, target_instance)
                    
                    self.transaction_safety_service.mark_transaction_failed(
                        transaction_id=transaction_id,
                        failure_reason=str(e),
                        is_timing_gap=is_timing_gap,
                        response_status=getattr(e, 'response', {}).get('status_code') if hasattr(e, 'response') else None
                    )
                    
                    if is_timing_gap:
                        logger.warning(f"⚠️ Timing gap failure detected for transaction {transaction_id[:8]}")
                    else:
                        logger.error(f"❌ Transaction {transaction_id[:8]} failed: {str(e)[:100]}")
                        
                except Exception as mark_error:
                    logger.error(f"❌ Failed to mark transaction failed: {mark_error}")
            
            # Re-raise the original exception
            raise e
    
    def _is_timing_gap_failure(self, exception: Exception, target_instance: Optional[ChromaInstance]) -> bool:
        """
        Detect if a failure is likely due to the timing gap issue
        """
        if not target_instance:
            return False
        
        # Check if the primary instance is marked as healthy but the request failed
        # This is the classic timing gap scenario
        if (target_instance.name == "primary" and 
            target_instance.is_healthy and
            ("Connection" in str(exception) or 
             "Timeout" in str(exception) or
             "502" in str(exception) or
             "503" in str(exception))):
            return True
        
        # Also check if we're in a failover scenario but the instance was marked healthy
        error_str = str(exception).lower()
        if (target_instance.is_healthy and 
            ("connection refused" in error_str or
             "connection timeout" in error_str or
             "bad gateway" in error_str or
             "service unavailable" in error_str)):
            return True
        
        return False
    
    def forward_request_with_recovery(self, method: str, path: str, headers: Dict[str, str], 
                                    data: bytes = b'', original_transaction_id: str = None, **kwargs) -> requests.Response:
        """
        Special method for retrying failed transactions during recovery
        """
        logger.info(f"🔄 Retrying transaction {original_transaction_id[:8] if original_transaction_id else 'unknown'}")
        
        return self.forward_request_with_transaction_safety(
            method=method,
            path=path, 
            headers=headers,
            data=data,
            original_transaction_id=original_transaction_id,
            **kwargs
        )

# Main execution for web service  
if __name__ == '__main__':
    logger.info("🚀 Starting Enhanced Unified WAL Load Balancer with High-Volume Support")
    
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
    
    @app.route('/wal/cleanup', methods=['POST'])
    def wal_cleanup():
        """Clean up old failed WAL entries"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
            
            # Get max_age parameter, default to 24 hours
            max_age = request.json.get('max_age_hours', 24) if request.is_json else 24
            
            deleted_count, reset_count = enhanced_wal.clear_failed_wal_entries(max_age)
            
            return jsonify({
                "status": "success", 
                "deleted_entries": deleted_count,
                "reset_entries": reset_count,
                "message": f"Cleared {deleted_count} old failed entries, reset {reset_count} recent entries"
            }), 200
        except Exception as e:
            return jsonify({"error": f"Cleanup failed: {str(e)}"}), 500
    
    @app.route('/collection/mappings', methods=['GET'])
    def collection_mappings():
        """Get current collection ID mappings"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
            
            with enhanced_wal.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT collection_name, primary_collection_id, replica_collection_id, 
                               created_at, updated_at
                        FROM collection_id_mapping 
                        ORDER BY updated_at DESC
                    """)
                    
                    mappings = []
                    for row in cur.fetchall():
                        mappings.append({
                            "collection_name": row[0],
                            "primary_collection_id": row[1],
                            "replica_collection_id": row[2],
                            "created_at": row[3].isoformat() if row[3] else None,
                            "updated_at": row[4].isoformat() if row[4] else None
                        })
                    
                    return jsonify({"mappings": mappings, "count": len(mappings)}), 200
        except Exception as e:
            return jsonify({"error": f"Failed to get mappings: {str(e)}"}), 500

    @app.route('/collection/mappings/<collection_name>', methods=['DELETE'])
    def delete_collection_mapping(collection_name):
        """Delete a specific collection mapping - FIXED to actually delete"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
            
            logger.info(f"🗑️ DELETE mapping request: {collection_name}")
            
            with enhanced_wal.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Check if mapping exists
                    cur.execute("SELECT collection_name FROM collection_id_mapping WHERE collection_name = %s", (collection_name,))
                    existing = cur.fetchone()
                    
                    if not existing:
                        logger.info(f"✅ Mapping not found (already deleted): {collection_name}")
                        return jsonify({"success": True, "message": f"Mapping for '{collection_name}' not found (already deleted)"}), 200
                    
                    # Actually delete the mapping
                    cur.execute("DELETE FROM collection_id_mapping WHERE collection_name = %s", (collection_name,))
                    deleted_count = cur.rowcount
                    conn.commit()
                    
                    if deleted_count > 0:
                        logger.info(f"✅ Successfully deleted mapping: {collection_name}")
                        return jsonify({"success": True, "message": f"Mapping for '{collection_name}' deleted successfully"}), 200
                    else:
                        logger.warning(f"⚠️ No mapping was deleted for: {collection_name}")
                        return jsonify({"success": False, "message": f"No mapping found for '{collection_name}'"}), 404
                        
        except Exception as e:
            logger.error(f"❌ Error deleting mapping for {collection_name}: {e}")
            return jsonify({"error": f"Failed to delete mapping: {str(e)}"}), 500
    
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
    
    @app.route('/transaction/safety/status', methods=['GET'])
    def transaction_safety_status():
        """Transaction safety system status and summary"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
            
            if not enhanced_wal.transaction_safety_service:
                return jsonify({
                    "available": False,
                    "message": "Transaction safety service not available"
                }), 503
            
            summary = enhanced_wal.transaction_safety_service.get_safety_summary()
            return jsonify({
                "available": True,
                "service_running": enhanced_wal.transaction_safety_service.is_running,
                "recovery_interval": enhanced_wal.transaction_safety_service.recovery_interval,
                **summary
            }), 200
            
        except Exception as e:
            return jsonify({"error": f"Failed to get transaction safety status: {str(e)}"}), 500
    
    @app.route('/transaction/safety/recovery/trigger', methods=['POST'])
    def trigger_transaction_recovery():
        """Manually trigger transaction recovery process"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
            
            if not enhanced_wal.transaction_safety_service:
                return jsonify({"error": "Transaction safety service not available"}), 503
            
            # Trigger recovery manually
            enhanced_wal.transaction_safety_service.process_recovery_queue()
            
            return jsonify({
                "success": True,
                "message": "Transaction recovery triggered successfully"
            }), 200
            
        except Exception as e:
            return jsonify({"error": f"Failed to trigger recovery: {str(e)}"}), 500
    
    @app.route('/transaction/safety/transaction/<transaction_id>', methods=['GET'])
    def get_transaction_status(transaction_id):
        """Get status of a specific transaction"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
            
            if not enhanced_wal.transaction_safety_service:
                return jsonify({"error": "Transaction safety service not available"}), 503
            
            transaction = enhanced_wal.transaction_safety_service.get_transaction_status(transaction_id)
            
            if not transaction:
                return jsonify({"error": f"Transaction {transaction_id} not found"}), 404
            
            return jsonify({
                "transaction_id": transaction['transaction_id'],
                "status": transaction['status'],
                "method": transaction['method'],
                "path": transaction['path'],
                "operation_type": transaction.get('operation_type'),
                "created_at": transaction['created_at'].isoformat() if transaction.get('created_at') else None,
                "completed_at": transaction['completed_at'].isoformat() if transaction.get('completed_at') else None,
                "retry_count": transaction.get('retry_count', 0),
                "max_retries": transaction.get('max_retries', 3),
                "is_timing_gap_failure": transaction.get('is_timing_gap_failure', False),
                "failure_reason": transaction.get('failure_reason'),
                "response_status": transaction.get('response_status')
            }), 200
            
        except Exception as e:
            return jsonify({"error": f"Failed to get transaction status: {str(e)}"}), 500
    
    @app.route('/transaction/safety/cleanup', methods=['POST'])
    def cleanup_old_transactions():
        """Clean up old completed transactions"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
            
            if not enhanced_wal.transaction_safety_service:
                return jsonify({"error": "Transaction safety service not available"}), 503
            
            # Get days parameter, default to 7 days
            days_old = request.json.get('days_old', 7) if request.is_json else 7
            
            deleted_count = enhanced_wal.transaction_safety_service.cleanup_old_transactions(days_old)
            
            return jsonify({
                "success": True,
                "deleted_transactions": deleted_count,
                "message": f"Cleaned up {deleted_count} old transactions older than {days_old} days"
            }), 200
            
        except Exception as e:
            return jsonify({"error": f"Failed to cleanup transactions: {str(e)}"}), 500

    @app.route('/admin/create_mapping', methods=['POST'])
    def admin_create_mapping():
        """Admin endpoint to manually create collection mappings"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
            
            request_data = request.get_json() or {}
            collection_name = request_data.get('collection_name')
            primary_id = request_data.get('primary_id')
            replica_id = request_data.get('replica_id')
            
            if not collection_name:
                return jsonify({"error": "collection_name is required"}), 400
            
            if not primary_id and not replica_id:
                return jsonify({"error": "At least one of primary_id or replica_id is required"}), 400
            
            try:
                with enhanced_wal.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO collection_id_mapping 
                            (collection_name, primary_collection_id, replica_collection_id, created_at)
                            VALUES (%s, %s, %s, NOW())
                            ON CONFLICT (collection_name) 
                            DO UPDATE SET 
                                primary_collection_id = COALESCE(EXCLUDED.primary_collection_id, collection_id_mapping.primary_collection_id),
                                replica_collection_id = COALESCE(EXCLUDED.replica_collection_id, collection_id_mapping.replica_collection_id),
                                updated_at = NOW()
                        """, (collection_name, primary_id, replica_id))
                        conn.commit()
                
                return jsonify({
                    "success": True,
                    "collection_name": collection_name,
                    "primary_id": primary_id,
                    "replica_id": replica_id,
                    "message": f"Mapping created/updated for '{collection_name}'"
                }), 200
                
            except Exception as e:
                return jsonify({"error": f"Failed to create mapping: {str(e)}"}), 500
            
        except Exception as e:
            return jsonify({"error": f"Admin create mapping failed: {str(e)}"}), 500
    
    @app.route('/debug/direct-primary', methods=['GET'])
    def debug_direct_primary():
        """Debug endpoint: Direct request to primary instance bypassing load balancer logic"""
        try:
            import requests
            response = requests.get("https://chroma-primary.onrender.com/api/v2/version", timeout=10)
            return jsonify({
                "status_code": response.status_code,
                "content": response.text,
                "content_length": len(response.content),
                "headers": dict(response.headers)
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/debug/simple-proxy', methods=['GET'])
    def debug_simple_proxy():
        """Debug endpoint: Simple proxy without complex load balancer logic"""
        try:
            import requests
            from flask import Response as FlaskResponse
            
            # Simple request to replica (which we know works)
            response = requests.get("https://chroma-replica.onrender.com/api/v2/version", timeout=10)
            
            # Create proper Flask response
            flask_response = FlaskResponse(
                response=response.content,
                status=response.status_code,
                headers=dict(response.headers)
            )
            
            return flask_response
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/debug/trace-collection-create', methods=['POST'])
    def debug_trace_collection_create():
        """Debug endpoint: Trace collection creation through load balancer logic"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
                
            import time
            collection_name = f"DEBUG_TRACE_{int(time.time())}"
            
            # Get selected instance
            target_instance = enhanced_wal.choose_read_instance(
                "/api/v2/tenants/default_tenant/databases/default_database/collections", 
                "POST", 
                {"Content-Type": "application/json"}
            )
            
            debug_info = {
                "collection_name": collection_name,
                "selected_instance": target_instance.name if target_instance else None,
                "instance_url": target_instance.url if target_instance else None,
                "instance_healthy": target_instance.is_healthy if target_instance else None,
                "all_instances": []
            }
            
            # Get all instance info
            for inst in enhanced_wal.instances:
                debug_info["all_instances"].append({
                    "name": inst.name,
                    "url": inst.url,
                    "healthy": inst.is_healthy,
                    "consecutive_failures": inst.consecutive_failures,
                    "total_requests": inst.total_requests,
                    "successful_requests": inst.successful_requests
                })
            
            if not target_instance:
                debug_info["error"] = "No target instance selected"
                return jsonify(debug_info), 503
            
            # Make the actual request
            import requests
            url = f"{target_instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections"
            
            debug_info["request_url"] = url
            debug_info["request_data"] = {"name": collection_name}
            
            response = requests.post(
                url,
                json={"name": collection_name},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            debug_info["response_status"] = response.status_code
            debug_info["response_content_length"] = len(response.content)
            debug_info["response_content_preview"] = response.text[:200] if response.text else "(empty)"
            debug_info["response_headers"] = dict(response.headers)
            
            return jsonify(debug_info), 200
            
        except Exception as e:
            import traceback
            return jsonify({
                "error": str(e),
                "traceback": traceback.format_exc()
            }), 500
    
    @app.route('/admin/instances/<instance_name>/health', methods=['POST'])
    def set_instance_health(instance_name):
        """Admin endpoint to control instance health for testing purposes"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
                
            request_data = request.get_json() or {}
            target_health = request_data.get('healthy', True)
            duration = request_data.get('duration_seconds', 0)  # 0 = permanent
            
            # Find the target instance
            target_instance = None
            for instance in enhanced_wal.instances:
                if instance.name == instance_name:
                    target_instance = instance
                    break
            
            if not target_instance:
                return jsonify({
                    "error": f"Instance '{instance_name}' not found",
                    "available_instances": [inst.name for inst in enhanced_wal.instances]
                }), 404
            
            # Store original health state
            original_health = target_instance.is_healthy
            
            # Set new health state
            target_instance.is_healthy = target_health
            
            logger.warning(f"🔧 ADMIN: Set {instance_name} health to {target_health} (was {original_health})")
            
            # If duration specified, schedule restoration
            if duration > 0 and target_health != original_health:
                def restore_health():
                    time.sleep(duration)
                    target_instance.is_healthy = original_health
                    logger.warning(f"🔧 ADMIN: Restored {instance_name} health to {original_health} after {duration}s")
                
                import threading
                restore_thread = threading.Thread(target=restore_health, daemon=True)
                restore_thread.start()
                
                return jsonify({
                    "success": True,
                    "instance": instance_name,
                    "health_set_to": target_health,
                    "original_health": original_health,
                    "will_restore_in_seconds": duration,
                    "message": f"Health temporarily set for testing - will auto-restore"
                })
            else:
                return jsonify({
                    "success": True,
                    "instance": instance_name, 
                    "health_set_to": target_health,
                    "original_health": original_health,
                    "permanent": True,
                    "message": f"Health permanently set for testing"
                })
                
        except Exception as e:
            logger.error(f"Admin health control error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/admin/instances', methods=['GET'])
    def get_instances_admin():
        """Admin endpoint to get detailed instance information"""
        try:
            if enhanced_wal is None:
                return jsonify({"error": "WAL system not initialized"}), 503
                
            instances_info = []
            for instance in enhanced_wal.instances:
                instances_info.append({
                    "name": instance.name,
                    "url": instance.url,
                    "healthy": instance.is_healthy,
                    "priority": instance.priority,
                    "consecutive_failures": instance.consecutive_failures,
                    "total_requests": instance.total_requests,
                    "successful_requests": instance.successful_requests,
                    "success_rate": instance.get_success_rate(),
                    "last_health_check": instance.last_health_check.isoformat() if instance.last_health_check else None
                })
            
            return jsonify({
                "instances": instances_info,
                "healthy_count": len([i for i in enhanced_wal.instances if i.is_healthy]),
                "total_count": len(enhanced_wal.instances)
            })
            
        except Exception as e:
            logger.error(f"Admin instances info error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def proxy_request(path):
        """Proxy all other requests through the load balancer"""
        try:
            if enhanced_wal is None:
                logger.error("Proxy request failed: WAL system not ready")
                return jsonify({"error": "WAL system not ready"}), 503
                
            logger.info(f"Forwarding {request.method} request to /{path}")
            
            # Extract request data and headers
            data = b''
            kwargs = {}
            
            # Check if request has JSON data
            if request.is_json and request.method in ['POST', 'PUT', 'PATCH']:
                kwargs['json'] = request.get_json()
                logger.debug(f"🔄 Using JSON data: {str(kwargs['json'])[:100]}...")
            elif request.method in ['POST', 'PUT', 'PATCH'] and request.content_length:
                data = request.get_data()
                logger.debug(f"🔄 Using raw data: {len(data)} bytes")
            
            # Extract relevant headers from Flask request
            headers = {}
            if request.content_type:
                headers['Content-Type'] = request.content_type
            
            # Forward the request through the load balancer WITH TRANSACTION SAFETY
            response = enhanced_wal.forward_request_with_transaction_safety(
                method=request.method,
                path=f"/{path}",
                headers=headers,
                data=data,
                **kwargs
            )
            
            # CRITICAL: Ensure we have a valid response
            if response is None:
                logger.error(f"❌ CRITICAL: forward_request returned None for {request.method} /{path}")
                return jsonify({"error": "Internal error: No response from load balancer"}), 503
            
            # CRITICAL FIX: Direct response handling - bypass Flask Response object creation
            status_code = getattr(response, 'status_code', 503)
            content = response.content if hasattr(response, 'content') else b'{"error": "No content"}'
            response_headers = dict(response.headers) if hasattr(response, 'headers') else {}
            
            # Filter out problematic headers that might cause issues
            safe_headers = {}
            for key, value in response_headers.items():
                if key.lower() not in ['content-length', 'transfer-encoding', 'connection', 'content-encoding']:
                    safe_headers[key] = value
            
            # Set correct content-type
            if 'content-type' not in safe_headers and 'Content-Type' not in safe_headers:
                safe_headers['Content-Type'] = 'application/json'
            
            logger.info(f"✅ Proxy forwarded {request.method} /{path} -> {status_code}, Content: {len(content)} bytes")
            
            # CRITICAL FIX: Return tuple format that Flask handles correctly
            return content, status_code, safe_headers
            
        except Exception as e:
            import traceback
            logger.error(f"Request forwarding failed for {request.method} /{path}: {e}")
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