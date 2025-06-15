#!/usr/bin/env python3
"""
ChromaDB 1.0.0 Compatible Unified WAL Load Balancer
Updated to work with the new tenant/database/collection API structure in ChromaDB 1.0.0

Key Changes for ChromaDB 1.0.0:
- Updated API endpoints from /api/v1/* to /api/v2/tenants/default_tenant/databases/default_database/*
- Fixed heartbeat endpoint to /api/v2/heartbeat
- Updated collection management for new API structure
- Maintained WAL-first approach with PostgreSQL persistence
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
    api_version: str = "1.0.0"  # ChromaDB 1.0.0
    
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

class ChromaDB_v1_LoadBalancer:
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
        self.max_memory_usage_mb = int(os.getenv("MAX_MEMORY_MB", "400"))
        self.max_workers = int(os.getenv("MAX_WORKERS", "3"))
        self.default_batch_size = int(os.getenv("DEFAULT_BATCH_SIZE", "50"))
        self.max_batch_size = int(os.getenv("MAX_BATCH_SIZE", "200"))
        
        # PostgreSQL connection for WAL
        self.database_url = os.getenv("DATABASE_URL", "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha")
        self.db_lock = threading.Lock()
        
        # ChromaDB 1.0.0 API structure
        self.api_base = "/api/v2"
        self.tenant = "default_tenant"
        self.database = "default_database"
        self.collections_endpoint = f"{self.api_base}/tenants/{self.tenant}/databases/{self.database}/collections"
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_wal_writes": 0,
            "successful_syncs": 0,
            "failed_syncs": 0,
            "sync_cycles": 0,
            "deletion_conversions": 0,
            "api_version": "ChromaDB 1.0.0"
        }
        
        # Initialize WAL schema
        self._initialize_wal_schema()
        
        # Start monitoring threads
        self.health_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
        self.health_thread.start()
        
        self.wal_sync_thread = threading.Thread(target=self.wal_sync_loop, daemon=True)
        self.wal_sync_thread.start()
        
        logger.info(f"🚀 ChromaDB 1.0.0 Compatible Load Balancer initialized")
        logger.info(f"📊 API Structure: {self.collections_endpoint}")
        logger.info(f"🔄 WAL sync interval: {self.sync_interval}s")

    def get_db_connection(self):
        """Get database connection with improved error handling"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return psycopg2.connect(
                    self.database_url,
                    connect_timeout=10,
                    application_name='chromadb-v1-lb'
                )
            except psycopg2.OperationalError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Database connection attempt {attempt + 1} failed, retrying: {e}")
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                    raise e

    def _initialize_wal_schema(self):
        """Initialize unified WAL schema for ChromaDB 1.0.0"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Enhanced WAL table for ChromaDB 1.0.0
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS chromadb_v1_wal_writes (
                            id SERIAL PRIMARY KEY,
                            write_id VARCHAR(100) UNIQUE NOT NULL,
                            method VARCHAR(10) NOT NULL,
                            path TEXT NOT NULL,
                            data BYTEA,
                            headers JSONB,
                            target_instance VARCHAR(20) NOT NULL,
                            status VARCHAR(20) DEFAULT 'pending',
                            collection_id VARCHAR(255),
                            collection_name VARCHAR(255),
                            executed_on VARCHAR(20),
                            retry_count INTEGER DEFAULT 0,
                            error_message TEXT,
                            timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            executed_at TIMESTAMP WITH TIME ZONE,
                            synced_at TIMESTAMP WITH TIME ZONE,
                            priority INTEGER DEFAULT 0,
                            original_data BYTEA,
                            conversion_type VARCHAR(50),
                            api_version VARCHAR(20) DEFAULT '1.0.0'
                        );
                    """)
                    
                    # Indexes for performance
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_chromadb_v1_wal_status ON chromadb_v1_wal_writes(status, timestamp ASC);
                        CREATE INDEX IF NOT EXISTS idx_chromadb_v1_wal_target_status ON chromadb_v1_wal_writes(target_instance, status);
                        CREATE INDEX IF NOT EXISTS idx_chromadb_v1_wal_priority ON chromadb_v1_wal_writes(priority DESC, timestamp ASC);
                    """)
                    
                    conn.commit()
                    logger.info("✅ ChromaDB 1.0.0 WAL PostgreSQL schema initialized")
                    
        except Exception as e:
            logger.error(f"❌ Failed to initialize WAL schema: {e}")
            raise

    def check_instance_health(self, instance: ChromaInstance) -> bool:
        """Check health using ChromaDB 1.0.0 heartbeat endpoint"""
        try:
            # Use the correct heartbeat endpoint for ChromaDB 1.0.0
            response = requests.get(
                f"{instance.url}{self.api_base}/heartbeat",
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                instance.is_healthy = True
                instance.consecutive_failures = 0
                logger.debug(f"✅ {instance.name} health check passed")
                return True
            else:
                logger.warning(f"⚠️ {instance.name} health check failed: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"⚠️ {instance.name} health check error: {e}")
        
        instance.is_healthy = False
        instance.consecutive_failures += 1
        return False

    def get_collections(self, instance: ChromaInstance) -> Optional[List[Dict]]:
        """Get collections using ChromaDB 1.0.0 API structure"""
        try:
            response = requests.get(
                f"{instance.url}{self.collections_endpoint}",
                timeout=self.request_timeout
            )
            
            if response.status_code == 200:
                collections = response.json()
                logger.debug(f"📋 {instance.name} has {len(collections)} collections")
                return collections
            else:
                logger.warning(f"⚠️ Failed to get collections from {instance.name}: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting collections from {instance.name}: {e}")
            return None

    def convert_api_path_for_v1(self, original_path: str) -> str:
        """Convert old API paths to ChromaDB 1.0.0 format"""
        # Handle old API paths and convert them to new structure
        if original_path.startswith('/api/v1/'):
            # Remove the old prefix
            path_without_prefix = original_path[8:]  # Remove '/api/v1/'
            
            # Convert to new structure
            if path_without_prefix.startswith('collections/'):
                # Extract collection identifier and operation
                parts = path_without_prefix.split('/')
                if len(parts) >= 2:
                    collection_id = parts[1]
                    operation = '/'.join(parts[2:]) if len(parts) > 2 else ''
                    
                    # Build new path
                    new_path = f"{self.collections_endpoint}/{collection_id}"
                    if operation:
                        new_path += f"/{operation}"
                    
                    logger.debug(f"🔄 Converted path: {original_path} -> {new_path}")
                    return new_path
            
            # For other endpoints, prepend the new API base
            return f"{self.api_base}/{path_without_prefix}"
        
        # If it's already a new format path, return as-is
        if original_path.startswith(self.api_base):
            return original_path
            
        # For root paths, prepend the collections endpoint
        if not original_path.startswith('/'):
            return f"{self.collections_endpoint}/{original_path}"
            
        return original_path

    def add_wal_write(self, method: str, path: str, data: bytes, headers: Dict[str, str], 
                     target_instance: TargetInstance, executed_on: Optional[str] = None) -> str:
        """Add write to WAL with ChromaDB 1.0.0 path conversion"""
        write_id = str(uuid.uuid4())
        
        # Convert path to ChromaDB 1.0.0 format
        converted_path = self.convert_api_path_for_v1(path)
        
        # Extract collection info
        collection_id = self.extract_collection_identifier(converted_path)
        collection_name = self.extract_collection_name(converted_path)
        
        # Handle deletion conversion for ID-based operations
        converted_data = data
        original_data = None
        conversion_type = None
        priority = 0
        
        # High priority for deletions
        if method == "DELETE" or path.endswith('/delete'):
            priority = 1
        
        # ID-based deletion conversion logic
        if method == "POST" and path.endswith('/delete') and data:
            try:
                delete_payload = json.loads(data.decode())
                
                if 'ids' in delete_payload and delete_payload['ids']:
                    logger.info(f"🔄 Converting ID-based deletion for ChromaDB 1.0.0")
                    
                    original_data = data
                    conversion_type = "id_to_metadata_v1"
                    
                    # Convert to metadata-based deletion
                    converted_deletion = self.convert_deletion_for_v1(
                        collection_id, delete_payload, executed_on
                    )
                    
                    if converted_deletion:
                        converted_data = json.dumps(converted_deletion).encode()
                        logger.info(f"✅ Converted deletion for ChromaDB 1.0.0")
                    else:
                        converted_data = data
                        conversion_type = None
                        
            except Exception as e:
                logger.warning(f"⚠️ Failed to convert deletion: {e}")
                converted_data = data
                conversion_type = None
        
        # Store in WAL
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO chromadb_v1_wal_writes 
                            (write_id, method, path, data, headers, target_instance, 
                             collection_id, collection_name, executed_on, status, 
                             priority, original_data, conversion_type, api_version)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            write_id,
                            method,
                            converted_path,  # Use converted path
                            converted_data,
                            json.dumps(headers) if headers else None,
                            target_instance.value,
                            collection_id,
                            collection_name,
                            executed_on,
                            WALWriteStatus.EXECUTED.value if executed_on else WALWriteStatus.PENDING.value,
                            priority,
                            original_data,
                            conversion_type,
                            "1.0.0"
                        ))
                        conn.commit()
            
            self.stats["total_wal_writes"] += 1
            if conversion_type:
                self.stats["deletion_conversions"] += 1
                
            logger.info(f"📝 WAL write {write_id[:8]} added for ChromaDB 1.0.0 ({converted_path})")
            return write_id
            
        except Exception as e:
            logger.error(f"❌ Failed to add WAL write: {e}")
            raise

    def convert_deletion_for_v1(self, collection_id: str, delete_payload: Dict, 
                               executed_instance: Optional[str]) -> Optional[Dict]:
        """Convert ID-based deletion to metadata-based for ChromaDB 1.0.0"""
        try:
            if 'ids' not in delete_payload or not delete_payload['ids']:
                return None
            
            chunk_ids = delete_payload['ids']
            logger.info(f"🔍 Converting {len(chunk_ids)} chunk IDs for ChromaDB 1.0.0")
            
            # Get source instance for metadata extraction
            query_instance = None
            if executed_instance == "primary":
                query_instance = self.get_primary_instance()
            elif executed_instance == "replica":
                query_instance = self.get_replica_instance()
            else:
                query_instance = self.get_primary_instance() or self.get_replica_instance()
            
            if not query_instance:
                logger.warning("⚠️ No healthy instance available for metadata extraction")
                return None
            
            # Query using ChromaDB 1.0.0 API structure
            query_url = f"{query_instance.url}{self.collections_endpoint}/{collection_id}/get"
            query_data = {
                "ids": chunk_ids,
                "include": ["metadatas"]
            }
            
            try:
                response = requests.post(
                    query_url,
                    json=query_data,
                    headers={"Content-Type": "application/json"},
                    timeout=self.request_timeout
                )
                
                if response.status_code == 200:
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
                    
                    if document_ids:
                        # Create metadata-based deletion
                        if len(document_ids) == 1:
                            document_id = list(document_ids)[0]
                            converted_deletion = {
                                "where": {"document_id": {"$eq": document_id}}
                            }
                        else:
                            converted_deletion = {
                                "where": {"document_id": {"$in": list(document_ids)}}
                            }
                        
                        logger.info(f"✅ Converted to metadata deletion for ChromaDB 1.0.0: {len(document_ids)} documents")
                        return converted_deletion
                    else:
                        logger.warning(f"⚠️ No document_ids found in metadata")
                        return None
                else:
                    logger.warning(f"⚠️ Failed to query metadata: {response.status_code}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Error querying metadata: {e}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error in deletion conversion: {e}")
            return None

    def extract_collection_identifier(self, path: str) -> Optional[str]:
        """Extract collection identifier from ChromaDB 1.0.0 path"""
        try:
            if self.collections_endpoint in path:
                # Extract collection ID from the path
                parts = path.split(self.collections_endpoint + "/")
                if len(parts) > 1:
                    collection_part = parts[1].split("/")[0]
                    return collection_part
        except Exception as e:
            logger.debug(f"Could not extract collection ID from path {path}: {e}")
        
        return None

    def extract_collection_name(self, path: str) -> Optional[str]:
        """Extract collection name from path or database"""
        collection_id = self.extract_collection_identifier(path)
        if collection_id:
            # Try to get collection name from database or instances
            try:
                # For now, return the ID as the name
                # In a full implementation, you might want to cache collection ID->name mappings
                return collection_id
            except:
                pass
        
        return None

    def get_primary_instance(self) -> Optional[ChromaInstance]:
        return next((i for i in self.instances if i.name == "primary" and i.is_healthy), None)

    def get_replica_instance(self) -> Optional[ChromaInstance]:
        return next((i for i in self.instances if i.name == "replica" and i.is_healthy), None)

    def get_healthy_instances(self) -> List[ChromaInstance]:
        return [i for i in self.instances if i.is_healthy]

    def health_monitor_loop(self):
        """Monitor health of all instances"""
        while True:
            try:
                for instance in self.instances:
                    self.check_instance_health(instance)
                    
                healthy_count = len(self.get_healthy_instances())
                logger.debug(f"💓 Health check: {healthy_count}/{len(self.instances)} instances healthy")
                
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"❌ Health monitor error: {e}")
                time.sleep(self.check_interval)

    def wal_sync_loop(self):
        """Sync WAL entries between instances"""
        while True:
            try:
                self.perform_wal_sync()
                time.sleep(self.sync_interval)
                
            except Exception as e:
                logger.error(f"❌ WAL sync error: {e}")
                time.sleep(self.sync_interval)

    def perform_wal_sync(self):
        """Perform WAL synchronization for ChromaDB 1.0.0"""
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        # Get pending WAL entries, prioritize deletions
                        cur.execute("""
                            SELECT write_id, method, path, data, target_instance, collection_id
                            FROM chromadb_v1_wal_writes 
                            WHERE status = 'pending' 
                            ORDER BY priority DESC, timestamp ASC 
                            LIMIT %s
                        """, (self.default_batch_size,))
                        
                        pending_writes = cur.fetchall()
                        
                        if not pending_writes:
                            return
                        
                        logger.info(f"🔄 Processing {len(pending_writes)} WAL entries for ChromaDB 1.0.0")
                        
                        successful_syncs = 0
                        failed_syncs = 0
                        
                        for write_data in pending_writes:
                            write_id, method, path, data, target_instance, collection_id = write_data
                            
                            # Determine target instance
                            if target_instance == "primary":
                                target = self.get_primary_instance()
                            elif target_instance == "replica":
                                target = self.get_replica_instance()
                            else:
                                continue
                            
                            if not target:
                                logger.warning(f"⚠️ Target instance {target_instance} not healthy")
                                continue
                            
                            # Execute the write
                            try:
                                response = requests.request(
                                    method,
                                    f"{target.url}{path}",
                                    data=data,
                                    headers={"Content-Type": "application/json"},
                                    timeout=self.request_timeout
                                )
                                
                                if response.status_code in [200, 201, 204]:
                                    # Mark as synced
                                    cur.execute("""
                                        UPDATE chromadb_v1_wal_writes 
                                        SET status = 'synced', synced_at = NOW() 
                                        WHERE write_id = %s
                                    """, (write_id,))
                                    successful_syncs += 1
                                    logger.debug(f"✅ Synced WAL entry {write_id[:8]} to {target.name}")
                                else:
                                    # Mark as failed
                                    cur.execute("""
                                        UPDATE chromadb_v1_wal_writes 
                                        SET status = 'failed', error_message = %s 
                                        WHERE write_id = %s
                                    """, (f"HTTP {response.status_code}: {response.text[:200]}", write_id))
                                    failed_syncs += 1
                                    logger.warning(f"⚠️ Failed to sync WAL entry {write_id[:8]}: {response.status_code}")
                                
                            except Exception as e:
                                # Mark as failed
                                cur.execute("""
                                    UPDATE chromadb_v1_wal_writes 
                                    SET status = 'failed', error_message = %s 
                                    WHERE write_id = %s
                                """, (str(e)[:200], write_id))
                                failed_syncs += 1
                                logger.error(f"❌ Error syncing WAL entry {write_id[:8]}: {e}")
                        
                        conn.commit()
                        
                        self.stats["successful_syncs"] += successful_syncs
                        self.stats["failed_syncs"] += failed_syncs
                        self.stats["sync_cycles"] += 1
                        
                        if successful_syncs > 0 or failed_syncs > 0:
                            logger.info(f"📊 WAL sync completed: {successful_syncs} successful, {failed_syncs} failed")
                            
        except Exception as e:
            logger.error(f"❌ WAL sync error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get load balancer status"""
        healthy_instances = self.get_healthy_instances()
        
        return {
            "service": "ChromaDB 1.0.0 Compatible WAL Load Balancer",
            "status": "healthy" if len(healthy_instances) > 0 else "unhealthy",
            "healthy_instances": f"{len(healthy_instances)}/{len(self.instances)}",
            "api_version": "ChromaDB 1.0.0",
            "architecture": "WAL-First with ChromaDB 1.0.0 API",
            "pending_writes": self.get_pending_writes_count(),
            "stats": self.stats,
            "instances": [
                {
                    "name": i.name,
                    "url": i.url,
                    "healthy": i.is_healthy,
                    "success_rate": f"{i.get_success_rate():.1f}%",
                    "consecutive_failures": i.consecutive_failures,
                    "api_version": i.api_version
                }
                for i in self.instances
            ]
        }

    def get_pending_writes_count(self) -> int:
        """Get count of pending WAL writes"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM chromadb_v1_wal_writes WHERE status = 'pending'")
                    return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting pending writes count: {e}")
            return 0

    def forward_request(self, method: str, path: str, headers: Dict[str, str], 
                       data: bytes = b'', target_instance: Optional[ChromaInstance] = None, 
                       retry_count: int = 0, max_retries: int = 1, **kwargs) -> requests.Response:
        """Forward request with ChromaDB 1.0.0 path conversion"""
        
        # Convert path for ChromaDB 1.0.0
        converted_path = self.convert_api_path_for_v1(path)
        
        # Choose target instance if not specified
        if not target_instance:
            if method.upper() in ['GET', 'HEAD']:
                # Read operations can use replica
                healthy_instances = self.get_healthy_instances()
                if healthy_instances:
                    target_instance = random.choice(healthy_instances)
            else:
                # Write operations go to primary
                target_instance = self.get_primary_instance()
        
        if not target_instance:
            raise requests.exceptions.ConnectionError("No healthy instances available")
        
        # Add to WAL for write operations
        if method.upper() in ['POST', 'PUT', 'DELETE', 'PATCH']:
            target_enum = TargetInstance.PRIMARY if target_instance.name == "primary" else TargetInstance.REPLICA
            
            try:
                self.add_wal_write(
                    method=method.upper(),
                    path=path,  # Store original path
                    data=data,
                    headers=headers,
                    target_instance=target_enum,
                    executed_on=target_instance.name
                )
            except Exception as e:
                logger.error(f"❌ Failed to add WAL entry: {e}")
        
        # Execute request
        try:
            url = f"{target_instance.url}{converted_path}"
            response = requests.request(
                method,
                url,
                data=data,
                headers=headers,
                timeout=self.request_timeout,
                **kwargs
            )
            
            target_instance.update_stats(True)
            self.stats["successful_requests"] += 1
            
            logger.debug(f"✅ Request forwarded to {target_instance.name}: {method} {converted_path} -> {response.status_code}")
            return response
            
        except Exception as e:
            target_instance.update_stats(False)
            self.stats["failed_requests"] += 1
            
            logger.error(f"❌ Request failed to {target_instance.name}: {method} {converted_path} -> {e}")
            
            # Retry logic
            if retry_count < max_retries:
                logger.info(f"🔄 Retrying request ({retry_count + 1}/{max_retries})")
                return self.forward_request(method, path, headers, data, None, retry_count + 1, max_retries, **kwargs)
            
            raise

# Flask application
def create_app():
    app = Flask(__name__)
    lb = ChromaDB_v1_LoadBalancer()
    
    @app.route('/health', methods=['GET'])
    def health_check():
        """Health check endpoint"""
        status = lb.get_status()
        return jsonify(status), 200 if status["status"] == "healthy" else 503
    
    @app.route('/status', methods=['GET'])
    def get_status():
        """Detailed status endpoint"""
        return jsonify(lb.get_status())
    
    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def proxy_request(path):
        """Proxy all requests with ChromaDB 1.0.0 compatibility"""
        try:
            # Prepare request data
            headers = dict(request.headers)
            # Remove hop-by-hop headers
            headers.pop('Host', None)
            headers.pop('Content-Length', None)
            
            data = request.get_data()
            
            # Forward request
            response = lb.forward_request(
                method=request.method,
                path=f"/{path}",
                headers=headers,
                data=data,
                params=request.args
            )
            
            # Prepare response
            response_headers = dict(response.headers)
            # Remove hop-by-hop headers
            response_headers.pop('Content-Encoding', None)
            response_headers.pop('Transfer-Encoding', None)
            response_headers.pop('Connection', None)
            
            return Response(
                response.content,
                status=response.status_code,
                headers=response_headers
            )
            
        except Exception as e:
            logger.error(f"❌ Proxy error: {e}")
            return jsonify({"error": "Service temporarily unavailable", "details": str(e)}), 503
    
    return app

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PORT", 8080))
    
    logger.info(f"🚀 Starting ChromaDB 1.0.0 Compatible Load Balancer on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False) 