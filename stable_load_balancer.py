#!/usr/bin/env python3
"""
Stable ChromaDB High Availability Load Balancer
Simplified version focused on core consistency without complex caching
"""

import os
import time
import logging
import requests
import threading
import random
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "consistency_overrides": 0
        }
        
        # Start simple health monitoring
        self.health_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
        self.health_thread.start()
        
        logger.info(f"🚀 Stable load balancer initialized")
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

    def get_healthy_instances(self) -> List[ChromaInstance]:
        """Get all healthy instances"""
        return [inst for inst in self.instances if inst.is_healthy]

    def select_instance(self, method: str, path: str) -> Optional[ChromaInstance]:
        """Select instance with simple consistency logic"""
        healthy_instances = self.get_healthy_instances()
        
        if not healthy_instances:
            logger.error("❌ No healthy instances available")
            return None
        
        collection_id = self.extract_collection_identifier(path)
        
        # Write operations always go to primary
        if method in ['POST', 'PUT', 'DELETE'] or any(op in path for op in ['add', 'update', 'delete', 'upsert']):
            primary = next((inst for inst in healthy_instances if inst.name == "primary"), None)
            if primary and collection_id:
                self.track_write(collection_id)
            return primary or healthy_instances[0]
        
        # Read operations with simple consistency check
        if method == 'GET' or any(op in path for op in ['query', 'get']):
            # Force primary for recent writes
            if collection_id and self.should_force_primary(collection_id):
                primary = next((inst for inst in healthy_instances if inst.name == "primary"), None)
                if primary:
                    logger.debug(f"🎯 Forcing PRIMARY for consistency: {collection_id}")
                    return primary
            
            # Normal distribution
            if random.random() < self.read_replica_ratio:
                replica = next((inst for inst in healthy_instances if inst.name == "replica"), None)
                if replica:
                    return replica
            
            # Fallback to primary
            primary = next((inst for inst in healthy_instances if inst.name == "primary"), None)
            return primary or healthy_instances[0]
        
        # Default to primary
        primary = next((inst for inst in healthy_instances if inst.name == "primary"), None)
        return primary or healthy_instances[0]

    def make_request(self, instance: ChromaInstance, method: str, path: str, **kwargs) -> requests.Response:
        """Make request with simple error handling"""
        kwargs['timeout'] = self.request_timeout
        
        try:
            url = f"{instance.url}{path}"
            
            # Simple session for this request
            session = requests.Session()
            
            # Start with default headers
            headers = {
                'Accept-Encoding': '',  # No compression
                'Accept': 'application/json'
            }
            
            # Only set Content-Type for requests that have data
            if 'json' in kwargs or 'data' in kwargs or method in ['POST', 'PUT', 'PATCH']:
                headers['Content-Type'] = 'application/json'
            
            # Merge with any headers passed in kwargs, giving priority to incoming headers
            if 'headers' in kwargs:
                headers.update(kwargs['headers'])
                # Remove headers from kwargs since we'll set them on session
                del kwargs['headers']
            
            session.headers.update(headers)
            
            response = session.request(method, url, **kwargs)
            
            # Handle 404 on replica with simple fallback
            if response.status_code == 404 and method == 'GET' and instance.name == "replica":
                logger.debug(f"🔄 404 on replica, trying primary")
                primary = next((inst for inst in self.instances if inst.name == "primary" and inst.is_healthy), None)
                if primary:
                    try:
                        primary_url = f"{primary.url}{path}"
                        primary_response = session.request(method, primary_url, **kwargs)
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

    def health_monitor_loop(self):
        """Simple health monitoring"""
        while True:
            try:
                for instance in self.instances:
                    try:
                        response = requests.get(f"{instance.url}/api/v2/version", timeout=5)
                        instance.is_healthy = response.status_code == 200
                        instance.last_health_check = datetime.now()
                        if instance.is_healthy:
                            logger.debug(f"✅ {instance.name} healthy")
                        else:
                            logger.warning(f"❌ {instance.name} unhealthy: HTTP {response.status_code}")
                    except Exception as e:
                        instance.is_healthy = False
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
        """Get simple status"""
        healthy_instances = self.get_healthy_instances()
        
        return {
            "healthy_instances": len(healthy_instances),
            "total_instances": len(self.instances),
            "read_replica_ratio": self.read_replica_ratio,
            "consistency_window": self.consistency_window,
            "instances": [
                {
                    "name": inst.name,
                    "healthy": inst.is_healthy,
                    "success_rate": f"{inst.get_success_rate():.1f}%",
                    "total_requests": inst.total_requests
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
    """Proxy all requests to ChromaDB instances"""
    try:
        # Get request details
        method = request.method
        url_path = f"/{path}" if path else "/"
        
        # Add query parameters
        if request.query_string:
            url_path += f"?{request.query_string.decode()}"
        
        # Prepare request kwargs
        request_kwargs = {}
        
        # Handle request body
        if request.data:
            request_kwargs['data'] = request.data
        elif request.json:
            request_kwargs['json'] = request.json
        elif request.form:
            request_kwargs['data'] = request.form
        
        # Handle headers - only pass essential headers, let load balancer set the rest
        essential_headers = {}
        if 'authorization' in request.headers:
            essential_headers['Authorization'] = request.headers['authorization']
        if 'user-agent' in request.headers:
            essential_headers['User-Agent'] = request.headers['user-agent']
        if 'accept' in request.headers:
            essential_headers['Accept'] = request.headers['accept']
        
        # Override any existing headers in request_kwargs
        if 'headers' not in request_kwargs:
            request_kwargs['headers'] = {}
        request_kwargs['headers'].update(essential_headers)
        
        # Route through load balancer
        load_balancer.stats["total_requests"] += 1
        
        instance = load_balancer.select_instance(method, url_path)
        if not instance:
            raise Exception("No healthy instances available")
        
        response = load_balancer.make_request(instance, method, url_path, **request_kwargs)
        load_balancer.stats["successful_requests"] += 1
        
        # Return response
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