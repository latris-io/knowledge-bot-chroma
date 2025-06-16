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
        
        # Initialize database schema and health check instances
        try:
            self._initialize_unified_wal_schema()
            logger.info("✅ Unified WAL schema initialized")
            
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
            
            # Check if this looks like a UUID (collection ID vs collection name)
            if len(collection_id) < 30:  # Collection name, not ID
                logger.error(f"   ℹ️ Collection identifier appears to be name (length < 30) - no mapping needed")
                return original_path  # No mapping needed for name-based paths
            
            logger.error(f"   🔍 Collection ID detected (length >= 30) - attempting mapping")
            
            # First, try to find existing mapping in database
            try:
                logger.error(f"   🔍 Querying database for existing mapping...")
                
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        # Check if we have a mapping for this collection ID
                        cur.execute("""
                            SELECT collection_name, primary_collection_id, replica_collection_id 
                            FROM collection_id_mapping 
                            WHERE primary_collection_id = %s OR replica_collection_id = %s
                        """, (collection_id, collection_id))
                        
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
                    # Include both PENDING (DELETEs) and EXECUTED (other operations) statuses
                    cur.execute("""
                        SELECT write_id, method, path, data, headers, collection_id, 
                               timestamp, retry_count, data_size_bytes, priority, executed_on
                        FROM unified_wal_writes 
                        WHERE (status = 'pending' OR status = 'executed')
                        AND (
                            -- For PENDING operations (DELETEs), sync to target_instance if it's BOTH or matches
                            (status = 'pending' AND (target_instance = 'both' OR target_instance = %s))
                            OR
                            -- For EXECUTED operations, use original logic
                            (status = 'executed' AND (
                                target_instance = 'both' OR 
                                (target_instance = %s AND executed_on != %s) OR
                                (target_instance != %s AND executed_on != %s)
                            ))
                        )
                        AND retry_count < 3
                        ORDER BY priority DESC, timestamp ASC
                        LIMIT %s
                    """, (target_instance, target_instance, target_instance, target_instance, target_instance, batch_size * 3))
                    
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
                    logger.error(f"      Data size: {len(data)}")
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
                            # 404 on DELETE is often expected (collection doesn't exist)
                            logger.error(f"   ℹ️ DELETE 404 - Collection likely doesn't exist, marking as successful")
                            self.mark_write_synced(write_id)
                            success_count += 1
                            self.stats["successful_syncs"] += 1
                            continue
                        elif '/collections/' in original_path:
                            logger.error(f"   🔧 404 detected - attempting auto-collection creation")
                            
                            try:
                                # Extract collection info from the path
                                collection_id_from_path = self.extract_collection_identifier(original_path)
                                logger.error(f"      Extracted collection ID: {collection_id_from_path}")
                                
                                if collection_id_from_path:
                                    # Try to get collection name from source instance
                                    source_instance_name = "primary" if batch.target_instance == "replica" else "replica"
                                    source_instance = next((inst for inst in self.instances if inst.name == source_instance_name and inst.is_healthy), None)
                                    
                                    logger.error(f"      Source instance: {source_instance_name}")
                                    logger.error(f"      Source instance available: {source_instance is not None}")
                                    
                                    if source_instance:
                                        # Get collection details from source
                                        source_url = f"{source_instance.url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id_from_path}"
                                        logger.error(f"      Fetching collection from source: {source_url}")
                                        
                                        source_collection_response = requests.get(source_url, timeout=20)
                                        logger.error(f"      Source collection response: {source_collection_response.status_code}")
                                        
                                        if source_collection_response.status_code == 200:
                                            source_collection = source_collection_response.json()
                                            collection_name = source_collection.get('name')
                                            collection_config = source_collection.get('configuration_json', {})
                                            
                                            logger.error(f"      Collection name: {collection_name}")
                                            logger.error(f"      Collection config: {collection_config}")
                                            
                                            if collection_name:
                                                logger.error(f"      🔧 Creating collection mapping for '{collection_name}'")
                                                
                                                # Create collection mapping (this will auto-create the collection)
                                                mapping = self.get_or_create_collection_mapping(
                                                    collection_name, collection_id_from_path, source_instance_name, collection_config
                                                )
                                                
                                                logger.error(f"      Mapping result: {mapping}")
                                                
                                                if mapping:
                                                    # Retry the sync with proper collection ID mapping
                                                    logger.error(f"      🔄 Retrying sync with new mapping...")
                                                    retry_mapped_path = self.map_collection_id_for_sync(original_path, batch.target_instance)
                                                    logger.error(f"      Retry path: {retry_mapped_path}")
                                                    
                                                    retry_response = self.make_direct_request(instance, method, retry_mapped_path, data=data, headers=headers)
                                                    
                                                    logger.error(f"      ✅ RETRY SUCCESS: {retry_response.status_code}")
                                                    
                                                    self.mark_write_synced(write_id)
                                                    success_count += 1
                                                    self.stats["successful_syncs"] += 1
                                                    self.stats["auto_created_collections"] = self.stats.get("auto_created_collections", 0) + 1
                                                    continue
                                                else:
                                                    logger.error(f"      ❌ Mapping creation failed")
                                            else:
                                                logger.error(f"      ❌ No collection name found in source response")
                                        else:
                                            logger.error(f"      ❌ Failed to fetch collection from source: {source_collection_response.status_code}")
                                    else:
                                        logger.error(f"      ❌ Source instance not available")
                                else:
                                    logger.error(f"      ❌ Could not extract collection ID from path")
                                    
                            except Exception as auto_create_error:
                                logger.error(f"      ❌ Auto-creation exception: {auto_create_error}")
                        
                        # For other 404 errors or failed auto-creation
                        error_msg = f"404: Resource not found: {str(e)}"
                        self.mark_write_failed(write_record['write_id'], error_msg)
                        self.stats["failed_syncs"] += 1
                        logger.error(f"      ❌ Marked as failed: {error_msg}")
                        
                    else:
                        # Other HTTP errors - mark as failed
                        error_msg = f"HTTP {e.response.status_code if e.response else 'unknown'}: {str(e)}"
                        self.mark_write_failed(write_record['write_id'], error_msg)
                        self.stats["failed_syncs"] += 1
                        logger.error(f"      ❌ Marked as failed: {error_msg}")
                        
                except Exception as e:
                    # General sync errors - mark as failed
                    error_msg = f"Sync error: {type(e).__name__}: {str(e)}"
                    self.mark_write_failed(write_record['write_id'], error_msg)
                    self.stats["failed_syncs"] += 1
                    logger.error(f"   ❌ GENERAL ERROR for write {write_id}:")
                    logger.error(f"      Error type: {type(e).__name__}")
                    logger.error(f"      Error message: {str(e)}")
                    logger.error(f"      Error details: {repr(e)}")
            
            # 🔍 DEBUGGING: Batch completion analysis
            end_memory = psutil.virtual_memory().used / 1024 / 1024
            memory_delta = end_memory - start_memory
            processing_time = time.time() - start_time
            throughput = batch.batch_size / processing_time if processing_time > 0 else 0
            
            logger.error(f"🔍 BATCH COMPLETION DEBUG:")
            logger.error(f"   Successful writes: {success_count}/{batch.batch_size}")
            logger.error(f"   Failed writes: {len(batch.writes) - success_count}")
            logger.error(f"   Processing time: {processing_time:.2f}s")
            logger.error(f"   Throughput: {throughput:.1f} writes/sec")
            logger.error(f"   Memory delta: {memory_delta:+.1f}MB")
            logger.error(f"   End memory: {end_memory:.1f}MB")
            
            # Update throughput stats
            if throughput > 0:
                if self.stats["avg_sync_throughput"] == 0:
                    self.stats["avg_sync_throughput"] = throughput
                else:
                    self.stats["avg_sync_throughput"] = (self.stats["avg_sync_throughput"] + throughput) / 2
            
            return success_count, len(batch.writes) - success_count
            
        except Exception as e:
            logger.error(f"🔍 BATCH ERROR DEBUG:")
            logger.error(f"   Exception type: {type(e).__name__}")
            logger.error(f"   Exception message: {str(e)}")
            logger.error(f"   Exception details: {repr(e)}")
            logger.error(f"   Successful writes before error: {success_count}")
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
        """Enhanced high-volume WAL sync loop with adaptive timing and automatic cleanup"""
        base_interval = self.sync_interval
        cleanup_counter = 0
        
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
                
                # AUTOMATIC CLEANUP: Clean up old failed entries every 10 sync cycles
                cleanup_counter += 1
                if cleanup_counter >= 10:
                    try:
                        logger.info("🧹 Performing automatic WAL cleanup...")
                        deleted_count, reset_count = self.clear_failed_wal_entries(max_age_hours=1)
                        if deleted_count > 0 or reset_count > 0:
                            logger.info(f"✅ Auto-cleanup: {deleted_count} deleted, {reset_count} reset")
                        cleanup_counter = 0
                    except Exception as e:
                        logger.error(f"❌ Auto-cleanup failed: {e}")
                
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
        """Make direct request without WAL logging (used for sync operations) - WITH COMPREHENSIVE DEBUGGING"""
        kwargs['timeout'] = self.request_timeout
        
        # 🔍 DEBUGGING: Log all request details
        logger.error(f"🔍 SYNC REQUEST DEBUG - Starting request")
        logger.error(f"   Target instance: {instance.name} ({instance.url})")
        logger.error(f"   Method: {method}")
        logger.error(f"   Path: {path}")
        logger.error(f"   Raw kwargs keys: {list(kwargs.keys())}")
        
        # CRITICAL FIX: Set proper headers for ChromaDB API compatibility
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        
        logger.error(f"   Original headers: {kwargs.get('headers', {})}")
        
        # 🔍 DEBUGGING: Data handling analysis
        original_data = kwargs.get('data')
        logger.error(f"   Original data type: {type(original_data)}")
        logger.error(f"   Original data size: {len(original_data) if original_data else 0} chars")
        if original_data:
            logger.error(f"   Original data preview: {str(original_data)[:200]}...")
        
        # CRITICAL FIX: Handle raw bytes data by converting to JSON for ChromaDB API
        if 'data' in kwargs and kwargs['data'] and method in ['POST', 'PUT', 'PATCH']:
            try:
                # Convert various data types to proper format for ChromaDB API
                if isinstance(kwargs['data'], bytes):
                    logger.error(f"   🔄 Converting bytes data to JSON...")
                    json_data = json.loads(kwargs['data'].decode('utf-8'))
                    del kwargs['data']  # Remove raw data
                    kwargs['json'] = json_data  # Use json parameter instead
                    logger.error(f"   ✅ Converted to JSON: {str(json_data)[:200]}...")
                elif isinstance(kwargs['data'], memoryview):
                    logger.error(f"   🔄 Converting memoryview data to JSON...")
                    # Convert memoryview to bytes first, then to JSON
                    bytes_data = bytes(kwargs['data'])
                    json_data = json.loads(bytes_data.decode('utf-8'))
                    del kwargs['data']  # Remove raw data
                    kwargs['json'] = json_data  # Use json parameter instead
                    logger.error(f"   ✅ Converted memoryview to JSON: {str(json_data)[:200]}...")
                elif isinstance(kwargs['data'], memoryview):
                    logger.error(f"   🔄 Converting memoryview data to JSON...")
                    # Convert memoryview to bytes first, then to JSON
                    bytes_data = bytes(kwargs['data'])
                    json_data = json.loads(bytes_data.decode('utf-8'))
                    del kwargs['data']  # Remove raw data
                    kwargs['json'] = json_data  # Use json parameter instead
                    logger.error(f"   ✅ Converted memoryview to JSON: {str(json_data)[:200]}...")
                elif isinstance(kwargs['data'], (str, dict)):
                    logger.error(f"   🔄 Converting string/dict data to JSON...")
                    if isinstance(kwargs['data'], str):
                        json_data = json.loads(kwargs['data'])
                    else:
                        json_data = kwargs['data']
                    del kwargs['data']
                    kwargs['json'] = json_data
                    logger.error(f"   ✅ Converted to JSON: {str(json_data)[:200]}...")
            except Exception as e:
                logger.error(f"   ❌ CRITICAL: Data conversion failed: {type(e).__name__}: {e}")
                logger.error(f"   📄 Raw data that failed: {repr(kwargs.get('data', 'None'))[:300]}...")
                # Continue with original data but log the issue
        
        # 🔍 DEBUGGING: Final request parameters
        final_headers = kwargs.get('headers', {})
        final_json = kwargs.get('json')
        final_data = kwargs.get('data')
        
        logger.error(f"   Final headers: {final_headers}")
        logger.error(f"   Final json: {str(final_json)[:200] if final_json else 'None'}...")
        logger.error(f"   Final data: {str(final_data)[:200] if final_data else 'None'}...")
        
        # Construct final URL
        url = f"{instance.url.rstrip('/')}/{path.lstrip('/')}"
        logger.error(f"   🎯 Final URL: {url}")
        
        try:
            # 🔍 DEBUGGING: Making the request
            logger.error(f"   🚀 Executing request...")
            
            response = requests.request(method, url, **kwargs)
            
            # 🔍 DEBUGGING: Response analysis
            logger.error(f"   📥 Response received:")
            logger.error(f"      Status: {response.status_code}")
            logger.error(f"      Headers: {dict(response.headers)}")
            logger.error(f"      Content-Type: {response.headers.get('Content-Type', 'unknown')}")
            logger.error(f"      Content-Length: {response.headers.get('Content-Length', 'unknown')}")
            
            if response.text:
                response_preview = response.text[:500] + "..." if len(response.text) > 500 else response.text
                logger.error(f"      Response body: {response_preview}")
            else:
                logger.error(f"      Response body: (empty)")
            
            # Check for success
            if response.status_code < 400:
                logger.error(f"   ✅ SUCCESS: Request completed successfully")
            else:
                logger.error(f"   ⚠️ HTTP ERROR: Status {response.status_code}")
                
            response.raise_for_status()
            return response
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"   ❌ HTTP ERROR DETAILS:")
            logger.error(f"      Exception type: {type(e).__name__}")
            logger.error(f"      Exception message: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"      Response status: {e.response.status_code}")
                logger.error(f"      Response headers: {dict(e.response.headers)}")
                logger.error(f"      Response body: {e.response.text[:500]}...")
            raise e
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"   ❌ CONNECTION ERROR:")
            logger.error(f"      Exception type: {type(e).__name__}")
            logger.error(f"      Exception message: {str(e)}")
            logger.error(f"      URL attempted: {url}")
            raise e
            
        except requests.exceptions.Timeout as e:
            logger.error(f"   ❌ TIMEOUT ERROR:")
            logger.error(f"      Exception type: {type(e).__name__}")
            logger.error(f"      Exception message: {str(e)}")
            logger.error(f"      Timeout value: {kwargs.get('timeout', 'unknown')}")
            raise e
            
        except Exception as e:
            logger.error(f"   ❌ UNEXPECTED ERROR:")
            logger.error(f"      Exception type: {type(e).__name__}")
            logger.error(f"      Exception message: {str(e)}")
            logger.error(f"      Exception details: {repr(e)}")
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

    def forward_request(self, method: str, path: str, headers: Dict[str, str], 
                       data: bytes = b'', target_instance: Optional[ChromaInstance] = None, 
                       retry_count: int = 0, max_retries: int = 1, **kwargs) -> requests.Response:
        """Forward request to appropriate instance with WAL logging for deletions"""
        
        # 🔧 CRITICAL: Apply V1→V2 path normalization for ALL requests
        original_path = path
        normalized_path = self.normalize_api_path_to_v2(path)
        if normalized_path != original_path:
            logger.error(f"🔧 LIVE REQUEST V1→V2 CONVERSION: {original_path} → {normalized_path}")
            path = normalized_path
        
        # Prevent infinite retry loops
        if retry_count >= max_retries:
            raise Exception(f"All instances failed after {max_retries} retries")
        
        # Choose target instance if not specified
        if not target_instance:
            target_instance = self.choose_read_instance(path, method, headers)
        
        if not target_instance:
            raise Exception("No healthy instances available")
        
        # CRITICAL FIX: Special handling for DELETE operations to prevent double-deletion corruption
        if method == "DELETE":
            logger.info(f"🗑️ DELETE request received: {path}")
            
            # ONLY log to WAL - do NOT execute immediately to prevent corruption
            self.add_wal_write(
                method=method,
                path=path,
                data=data,
                headers=headers,
                target_instance=TargetInstance.BOTH,  # Delete from both instances via WAL
                executed_on=None  # Mark as not yet executed
            )
            
            # Return immediate success response without executing deletion
            # The WAL system will handle the actual deletion safely
            logger.info(f"✅ DELETE logged to WAL for both instances: {path}")
            
            # Create a mock successful response
            from requests import Response as RequestsResponse
            mock_response = RequestsResponse()
            mock_response.status_code = 200
            mock_response._content = b'{"success": true, "message": "Deletion queued for WAL processing"}'
            mock_response.headers['Content-Type'] = 'application/json'
            
            self.stats["successful_requests"] += 1
            return mock_response
        
        # For non-DELETE write operations, log to WAL and execute normally
        if method in ['POST', 'PUT', 'PATCH']:
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
        
        # Execute the request normally for all non-DELETE operations
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
            response.raise_for_status()
            logger.info(f"Debug: Response status {response.status_code}, content length {len(response.content)}")
            
            # Debug logging to see response content
            logger.info(f"Response status: {response.status_code}, Content length: {len(response.content)}, Content preview: {response.content[:100]}")
            
            target_instance.update_stats(True)
            self.stats["successful_requests"] += 1
            
            logger.info(f"Successfully forwarded {method} /{path} -> {response.status_code}")
            
            # Debug the response content before returning
            content_length = len(response.content)
            logger.info(f"Response content length: {content_length}")
            if content_length > 0:
                logger.info(f"Response preview: {response.content[:100]}")
            
            return response
            
        except Exception as e:
            target_instance.update_stats(False)
            self.stats["failed_requests"] += 1
            
            # For critical failures, try other instances (with retry limit)
            if target_instance.consecutive_failures > 2 and retry_count < max_retries:
                other_instances = [inst for inst in self.get_healthy_instances() if inst != target_instance]
                if other_instances:
                    logger.warning(f"Retrying request on {other_instances[0].name} due to {target_instance.name} failures (attempt {retry_count + 1}/{max_retries})")
                    return self.forward_request(method, path, headers, data, other_instances[0], retry_count + 1, max_retries)
            
            raise e

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
    
    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def proxy_request(path):
        """Proxy all other requests through the load balancer"""
        try:
            if enhanced_wal is None:
                logger.error("Proxy request failed: WAL system not ready")
                return jsonify({"error": "WAL system not ready"}), 503
                
            logger.info(f"Forwarding {request.method} request to /{path}")
            
            # CRITICAL FIX: Properly handle JSON data and headers
            data = b''
            kwargs = {}
            
            # Check if request has JSON data
            if request.is_json and request.method in ['POST', 'PUT', 'PATCH']:
                # Use json parameter for JSON requests
                kwargs['json'] = request.get_json()
                logger.debug(f"🔄 Using JSON data: {str(kwargs['json'])[:100]}...")
            elif request.method in ['POST', 'PUT', 'PATCH'] and request.content_length:
                # Use data parameter for non-JSON requests
                data = request.get_data()
                logger.debug(f"🔄 Using raw data: {len(data)} bytes")
            
            # Extract relevant headers from Flask request
            headers = {}
            if request.content_type:
                headers['Content-Type'] = request.content_type
            
            response = enhanced_wal.forward_request(
                method=request.method,
                path=f"/{path}",
                headers=headers,
                data=data,
                **kwargs  # Pass json parameter if present
            )
            
            logger.info(f"Successfully forwarded {request.method} /{path} -> {response.status_code}")
            
            # Debug the response content before returning
            content_length = len(response.content)
            logger.info(f"Response content length: {content_length}")
            if content_length > 0:
                logger.info(f"Response preview: {response.content[:100]}")
            
            # Return the raw requests.Response for proxy_request to handle
            flask_response = Response(
                response.content,
                status=response.status_code,
                headers=dict(response.headers) if hasattr(response, 'headers') else {}
            )
            
            # Ensure content-type is set
            if 'application/json' not in (response.headers.get('Content-Type', '') if hasattr(response, 'headers') else ''):
                flask_response.headers['Content-Type'] = 'application/json'
                
            return response.content, response.status_code, {"Content-Type": "application/json"}
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