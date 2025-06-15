#!/usr/bin/env python3
"""
Stable ChromaDB High Availability Load Balancer
Enhanced with Write-Ahead Log for both safety and availability
"""

import os
import time
import logging
import requests
import threading
import random
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class PendingWrite:
    """Represents a write operation pending sync to primary"""
    id: str
    timestamp: datetime
    method: str
    path: str
    data: bytes
    headers: Dict[str, str]
    collection_id: Optional[str] = None
    retries: int = 0
    max_retries: int = 3

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

class StableLoadBalancer:
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
        
        # Simple configuration
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "30"))
        self.failure_threshold = int(os.getenv("FAILURE_THRESHOLD", "3"))
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "15"))
        self.read_replica_ratio = float(os.getenv("READ_REPLICA_RATIO", "0.8"))
        
        # Simple consistency tracking - just recent collection names/UUIDs
        self.recent_writes = {}  # collection_id -> timestamp
        self.consistency_window = 30  # 30 seconds
        
        # Write-Ahead Log for high availability
        self.pending_writes = {}  # write_id -> PendingWrite
        self.pending_writes_lock = threading.Lock()
        self.is_replaying = False
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "consistency_overrides": 0,
            "pending_writes": 0,
            "replayed_writes": 0,
            "failed_replays": 0
        }
        
        # Start simple health monitoring
        self.health_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
        self.health_thread.start()
        
        # Start write replay monitoring
        self.replay_thread = threading.Thread(target=self.replay_monitor_loop, daemon=True)
        self.replay_thread.start()
        
        logger.info(f"🚀 Stable load balancer initialized with Write-Ahead Log")
        logger.info(f"🎯 Read replica ratio: {self.read_replica_ratio * 100}%")

    def extract_collection_identifier(self, path: str) -> Optional[str]:
        """Extract collection identifier (name or UUID) from path"""
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

    def track_write(self, collection_id: str):
        """Track a write operation for consistency"""
        if collection_id:
            self.recent_writes[collection_id] = time.time()
            # Clean old entries
            current_time = time.time()
            self.recent_writes = {
                cid: ts for cid, ts in self.recent_writes.items()
                if current_time - ts < self.consistency_window
            }

    def should_force_primary(self, collection_id: str) -> bool:
        """Check if we should force primary for consistency"""
        if not collection_id:
            return False
        
        if collection_id in self.recent_writes:
            write_time = self.recent_writes[collection_id]
            if time.time() - write_time < self.consistency_window:
                self.stats["consistency_overrides"] += 1
                return True
        
        return False

    def add_pending_write(self, method: str, path: str, data: bytes, headers: Dict[str, str]) -> str:
        """Add a write to the pending writes queue"""
        write_id = str(uuid.uuid4())
        collection_id = self.extract_collection_identifier(path)
        
        pending_write = PendingWrite(
            id=write_id,
            timestamp=datetime.now(),
            method=method,
            path=path,
            data=data,
            headers=headers,
            collection_id=collection_id
        )
        
        with self.pending_writes_lock:
            self.pending_writes[write_id] = pending_write
            self.stats["pending_writes"] = len(self.pending_writes)
        
        logger.info(f"📝 Added pending write {write_id[:8]} for collection {collection_id}")
        return write_id

    def replay_pending_writes(self) -> bool:
        """Replay all pending writes to primary"""
        if self.is_replaying:
            return False
        
        with self.pending_writes_lock:
            if not self.pending_writes:
                return True
            
            pending_list = list(self.pending_writes.values())
        
        self.is_replaying = True
        success_count = 0
        failure_count = 0
        
        try:
            logger.info(f"🔄 Starting replay of {len(pending_list)} pending writes")
            
            # Sort by timestamp to maintain order
            pending_list.sort(key=lambda w: w.timestamp)
            
            primary = self.get_primary_instance()
            if not primary:
                logger.error("❌ Cannot replay: Primary still unavailable")
                return False
            
            for write in pending_list:
                try:
                    # Replay the write to primary
                    response = self.make_direct_request(primary, write.method, write.path, 
                                                     data=write.data, headers=write.headers)
                    
                    # Mark as completed
                    with self.pending_writes_lock:
                        if write.id in self.pending_writes:
                            del self.pending_writes[write.id]
                    
                    success_count += 1
                    self.stats["replayed_writes"] += 1
                    logger.info(f"✅ Replayed write {write.id[:8]} successfully")
                    
                except Exception as e:
                    write.retries += 1
                    if write.retries >= write.max_retries:
                        logger.error(f"❌ Failed to replay write {write.id[:8]} after {write.max_retries} attempts: {e}")
                        with self.pending_writes_lock:
                            if write.id in self.pending_writes:
                                del self.pending_writes[write.id]
                        failure_count += 1
                        self.stats["failed_replays"] += 1
                    else:
                        logger.warning(f"⚠️ Retry {write.retries}/{write.max_retries} failed for write {write.id[:8]}: {e}")
            
            with self.pending_writes_lock:
                self.stats["pending_writes"] = len(self.pending_writes)
            
            logger.info(f"🎯 Replay completed: {success_count} success, {failure_count} failed")
            return failure_count == 0
            
        finally:
            self.is_replaying = False

    def get_primary_instance(self) -> Optional[ChromaInstance]:
        """Get primary instance if healthy"""
        return next((inst for inst in self.instances if inst.name == "primary" and inst.is_healthy), None)

    def get_replica_instance(self) -> Optional[ChromaInstance]:
        """Get replica instance if healthy"""
        return next((inst for inst in self.instances if inst.name == "replica" and inst.is_healthy), None)

    def get_healthy_instances(self) -> List[ChromaInstance]:
        """Get all healthy instances"""
        return [inst for inst in self.instances if inst.is_healthy]

    def select_instance(self, method: str, path: str) -> Optional[ChromaInstance]:
        """Select instance with enhanced Write-Ahead Log support"""
        healthy_instances = self.get_healthy_instances()
        
        if not healthy_instances:
            logger.error("❌ No healthy instances available")
            return None
        
        collection_id = self.extract_collection_identifier(path)
        
        # Write operations with Write-Ahead Log support
        if method in ['POST', 'PUT', 'DELETE'] or any(op in path for op in ['add', 'update', 'delete', 'upsert']):
            primary = self.get_primary_instance()
            if primary:
                # Primary is healthy - normal operation
                if collection_id:
                    self.track_write(collection_id)
                return primary
            else:
                # Primary is down - use replica with Write-Ahead Log
                replica = self.get_replica_instance()
                if replica:
                    logger.warning(f"🚨 Primary down - using replica with Write-Ahead Log for write")
                    if collection_id:
                        self.track_write(collection_id)
                    return replica  # This will trigger pending write logging
                else:
                    # Both instances down
                    raise Exception("No instances available for write operation")
        
        # Read operations with improved consistency and failover logic
        if method == 'GET' or any(op in path for op in ['query', 'get']):
            # Try to force primary for recent writes, but fallback gracefully
            if collection_id and self.should_force_primary(collection_id):
                primary = self.get_primary_instance()
                if primary:
                    logger.debug(f"🎯 Forcing PRIMARY for consistency: {collection_id}")
                    return primary
                else:
                    # PRIMARY IS DOWN - log warning and fallback to replica for availability
                    logger.warning(f"⚠️ Primary down during consistency window for {collection_id}, falling back to replica")
                    replica = self.get_replica_instance()
                    if replica:
                        return replica
                    # If replica also down, use any healthy instance
                    return healthy_instances[0] if healthy_instances else None
            
            # Normal load distribution for reads
            if random.random() < self.read_replica_ratio:
                replica = self.get_replica_instance()
                if replica:
                    return replica
            
            # Fallback to primary, then any healthy instance
            primary = self.get_primary_instance()
            return primary or healthy_instances[0]
        
        # Default case - prefer primary, fallback to any healthy
        primary = self.get_primary_instance()
        return primary or healthy_instances[0]

    def make_direct_request(self, instance: ChromaInstance, method: str, path: str, **kwargs) -> requests.Response:
        """Make direct request without Write-Ahead Log logic"""
        kwargs['timeout'] = self.request_timeout
        
        try:
            url = f"{instance.url}{path}"
            response = requests.request(method, url, **kwargs)
            instance.update_stats(True)
            response.raise_for_status()
            return response
            
        except Exception as e:
            instance.update_stats(False)
            logger.warning(f"Request to {instance.name} failed: {e}")
            raise e

    def make_request(self, instance: ChromaInstance, method: str, path: str, **kwargs) -> requests.Response:
        """Make request with Write-Ahead Log support"""
        # Check if this is a write operation to replica (indicating primary is down)
        is_write = method in ['POST', 'PUT', 'DELETE'] or any(op in path for op in ['add', 'update', 'delete', 'upsert'])
        is_replica_write = is_write and instance.name == "replica"
        
        if is_replica_write:
            # This is a write to replica because primary is down
            # Add to Write-Ahead Log before executing
            write_data = kwargs.get('data', b'')
            write_headers = kwargs.get('headers', {})
            write_id = self.add_pending_write(method, path, write_data, write_headers)
            logger.info(f"📋 Write {write_id[:8]} queued for later replay to primary")
        
        kwargs['timeout'] = self.request_timeout
        
        try:
            url = f"{instance.url}{path}"
            
            # Directly make the request without any header manipulation
            response = requests.request(method, url, **kwargs)
            
            # Handle 404 on replica with simple fallback
            if response.status_code == 404 and method == 'GET' and instance.name == "replica":
                logger.debug(f"🔄 404 on replica, trying primary")
                primary = self.get_primary_instance()
                if primary:
                    try:
                        primary_url = f"{primary.url}{path}"
                        primary_response = requests.request(method, primary_url, **kwargs)
                        primary_response.raise_for_status()
                        instance.update_stats(False)  # Replica failed
                        primary.update_stats(True)    # Primary succeeded
                        return primary_response
                    except:
                        pass
            
            instance.update_stats(True)
            response.raise_for_status()
            return response
            
        except Exception as e:
            instance.update_stats(False)
            logger.warning(f"Request to {instance.name} failed: {e}")
            raise e

    def replay_monitor_loop(self):
        """Monitor for primary recovery and replay pending writes"""
        while True:
            try:
                time.sleep(10)  # Check every 10 seconds
                
                # Only attempt replay if we have pending writes and primary is healthy
                with self.pending_writes_lock:
                    has_pending = len(self.pending_writes) > 0
                
                if has_pending and not self.is_replaying:
                    primary = self.get_primary_instance()
                    if primary:
                        logger.info(f"🔄 Primary recovered, attempting to replay {len(self.pending_writes)} pending writes")
                        success = self.replay_pending_writes()
                        if success:
                            logger.info("✅ All pending writes successfully replayed to primary")
                        else:
                            logger.warning("⚠️ Some pending writes failed to replay")
                
            except Exception as e:
                logger.error(f"Error in replay monitor: {e}")
                time.sleep(60)

    def health_monitor_loop(self):
        """Simple health monitoring"""
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

    def handle_request(self, method: str, path: str, **kwargs):
        """Handle request with simple routing"""
        self.stats["total_requests"] += 1
        
        instance = self.select_instance(method, path)
        if not instance:
            raise Exception("No healthy instances available")
        
        try:
            response = self.make_request(instance, method, path, **kwargs)
            self.stats["successful_requests"] += 1
            return response
        except Exception as e:
            self.stats["failed_requests"] += 1
            raise e

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status including Write-Ahead Log info"""
        healthy_instances = self.get_healthy_instances()
        
        with self.pending_writes_lock:
            pending_count = len(self.pending_writes)
            oldest_pending = None
            if self.pending_writes:
                oldest_write = min(self.pending_writes.values(), key=lambda w: w.timestamp)
                oldest_pending = oldest_write.timestamp.isoformat()
        
        return {
            "service": "ChromaDB Load Balancer with Write-Ahead Log",
            "healthy_instances": len(healthy_instances),
            "total_instances": len(self.instances),
            "read_replica_ratio": self.read_replica_ratio,
            "consistency_window": self.consistency_window,
            "write_ahead_log": {
                "pending_writes": pending_count,
                "is_replaying": self.is_replaying,
                "oldest_pending": oldest_pending,
                "total_replayed": self.stats["replayed_writes"],
                "failed_replays": self.stats["failed_replays"]
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

# Global load balancer instance
load_balancer = StableLoadBalancer()

def get_load_balancer():
    """Get the global load balancer instance"""
    return load_balancer

# Add Flask web server
from flask import Flask, request, Response, jsonify
import json

app = Flask(__name__)

@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        status = load_balancer.get_status()
        return jsonify({
            "status": "healthy",
            "service": "ChromaDB Load Balancer",
            "healthy_instances": status["healthy_instances"],
            "total_instances": status["total_instances"]
        })
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503

@app.route('/status')
def status():
    """Detailed status endpoint"""
    try:
        status = load_balancer.get_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
def proxy(path):
    """Proxy all requests to ChromaDB instances with completely agnostic handling"""
    try:
        # Get request details
        method = request.method
        url_path = f"/{path}" if path else "/"
        
        # Add query parameters
        if request.query_string:
            url_path += f"?{request.query_string.decode()}"
        
        # Prepare request kwargs
        request_kwargs = {}
        
        # Pass through ALL headers exactly as received (except host)
        headers = {}
        for header_name, header_value in request.headers:
            if header_name.lower() != 'host':  # Skip host header
                headers[header_name] = header_value
        
        if headers:
            request_kwargs['headers'] = headers
        
        # Get raw request body without any parsing or interpretation
        raw_body = request.get_data()
        if raw_body:
            request_kwargs['data'] = raw_body
        
        # Route through load balancer
        load_balancer.stats["total_requests"] += 1
        
        instance = load_balancer.select_instance(method, url_path)
        if not instance:
            raise Exception("No healthy instances available")
        
        response = load_balancer.make_request(instance, method, url_path, **request_kwargs)
        load_balancer.stats["successful_requests"] += 1
        
        # Return response with all headers preserved
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
        
    except Exception as e:
        load_balancer.stats["failed_requests"] += 1
        logger.error(f"Error in proxy: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    try:
        logger.info("🚀 Starting Flask web server")
        port = int(os.environ.get('PORT', 8000))
        logger.info(f"📡 Starting on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"❌ Failed to start Flask app: {e}")
        raise 