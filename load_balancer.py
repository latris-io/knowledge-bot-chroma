#!/usr/bin/env python3
"""
ChromaDB High Availability Load Balancer - Clean Uncompressed Version
Forces uncompressed JSON responses to eliminate corruption issues
"""

import os
import time
import requests
import logging
import json
from flask import Flask, request, jsonify, Response, make_response
from werkzeug.exceptions import ServiceUnavailable
import threading
import random
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class ChromaInstance:
    def __init__(self, name: str, url: str, priority: int):
        self.name = name
        self.url = url
        self.priority = priority
        self.is_healthy = True
        self.last_check = datetime.now()
        self.failure_count = 0
        self.last_failure = None
        self.request_count = 0

class CleanLoadBalancer:
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
        
        self.load_balance_strategy = os.getenv("LOAD_BALANCE_STRATEGY", "write_primary")
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "30"))
        self.failure_threshold = int(os.getenv("FAILURE_THRESHOLD", "3"))
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "30"))
        
        self.current_instance_index = 0
        
        # Start health monitoring thread
        self.health_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
        self.health_thread.start()
        
        logger.info(f"Clean load balancer initialized with strategy: {self.load_balance_strategy}")

    def get_healthy_instances(self) -> List[ChromaInstance]:
        """Get all healthy instances"""
        return [inst for inst in self.instances if inst.is_healthy]

    def get_target_instance(self, method: str = "GET") -> Optional[ChromaInstance]:
        """Get target instance based on load balancing strategy"""
        healthy_instances = self.get_healthy_instances()
        if not healthy_instances:
            return None
        
        # Write-primary strategy: writes to primary, reads round-robin
        if self.load_balance_strategy == "write_primary":
            if method in ['POST', 'PUT', 'DELETE', 'PATCH']:
                # Writes go to primary if available
                primary = next((inst for inst in healthy_instances if inst.name == "primary"), None)
                return primary if primary else healthy_instances[0]
            else:
                # Reads use round-robin
                instance = healthy_instances[self.current_instance_index % len(healthy_instances)]
                self.current_instance_index += 1
                return instance
        
        # Default round-robin for all other strategies
        instance = healthy_instances[self.current_instance_index % len(healthy_instances)]
        self.current_instance_index += 1
        return instance

    def check_instance_health(self, instance: ChromaInstance) -> bool:
        """Check if a ChromaDB instance is healthy"""
        try:
            # Use uncompressed health check request
            headers = {'Accept-Encoding': ''}
            response = requests.get(f"{instance.url}/api/v2/version", headers=headers, timeout=10)
            return response.status_code == 200
        except:
            return False

    def update_instance_health(self, instance: ChromaInstance, is_healthy: bool):
        """Update instance health status"""
        instance.last_check = datetime.now()
        
        if is_healthy:
            if not instance.is_healthy:
                logger.info(f"Instance {instance.name} recovered")
            instance.is_healthy = True
            instance.failure_count = 0
        else:
            instance.failure_count += 1
            if instance.failure_count >= self.failure_threshold:
                if instance.is_healthy:
                    logger.error(f"Instance {instance.name} marked as unhealthy")
                instance.is_healthy = False
                instance.last_failure = datetime.now()

    def health_monitor_loop(self):
        """Background health monitoring loop"""
        while True:
            try:
                for instance in self.instances:
                    is_healthy = self.check_instance_health(instance)
                    self.update_instance_health(instance, is_healthy)
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in health monitor: {e}")
                time.sleep(self.check_interval)

    def proxy_request(self, target_url: str, path: str, method: str) -> Response:
        """Proxy request with forced uncompressed responses"""
        try:
            url = f"{target_url}{path}"
            
            # Log for collection endpoints (the problematic ones)
            is_collection_endpoint = "/collections/" in path
            if is_collection_endpoint:
                logger.info(f"🔧 Proxying {method} {path} to {target_url}")
            
            if method == 'GET':
                # Add query parameters
                if request.args:
                    query_string = urlencode(request.args)
                    url = f"{url}?{query_string}"
                
                # Force uncompressed GET request
                headers = {
                    'Accept-Encoding': '',  # Empty = no compression
                    'Accept': 'application/json'
                }
                response = requests.get(url, headers=headers, timeout=self.request_timeout)
                
                # Return clean response
                return self.create_clean_response(response, is_collection_endpoint)
                
            else:
                # Handle POST/PUT/DELETE/PATCH requests
                req_params = {"timeout": self.request_timeout}
                
                # Handle JSON body
                if request.is_json and request.json is not None:
                    req_params["json"] = request.json
                elif request.data:
                    req_params["data"] = request.data
                
                # Create clean headers with no compression
                headers = {}
                for key, value in request.headers.items():
                    if key.lower() not in ['host', 'content-length', 'connection', 'accept-encoding']:
                        headers[key] = value
                
                # Force no compression with empty Accept-Encoding
                headers['Accept-Encoding'] = ''  # Empty = no compression
                headers['Accept'] = 'application/json'
                req_params["headers"] = headers
                
                # Add query parameters
                if request.args:
                    req_params["params"] = request.args
                
                # Make the request
                response = requests.request(method, url, **req_params)
                
                # Debug logging for collection endpoints
                if is_collection_endpoint:
                    logger.info(f"🔧 SENT HEADERS: {headers}")
                    content_encoding = response.headers.get('content-encoding', 'none')
                    logger.info(f"🔧 Response: status={response.status_code}, encoding={content_encoding}, content-type={response.headers.get('content-type')}")
                    logger.info(f"🔧 Response.text length: {len(response.text)}")
                    logger.info(f"🔧 Response.content length: {len(response.content)}")
                    logger.info(f"🔧 First 50 chars of response.text: {repr(response.text[:50])}")
                
                return self.create_clean_response(response, is_collection_endpoint)
            
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout to {target_url}")
            raise ServiceUnavailable("Request timeout")
        except Exception as e:
            logger.error(f"Proxy error to {target_url}: {e}")
            raise ServiceUnavailable(f"Proxy error: {str(e)}")

    def create_clean_response(self, response, is_collection_endpoint: bool) -> Response:
        """Create a clean Flask response without compression"""
        response_text = response.text
        
        # Debug logging for collection endpoints
        if is_collection_endpoint:
            logger.info(f"🔧 Creating clean response, length: {len(response_text)}")
            # Verify it's valid JSON for debugging
            try:
                if response.headers.get('content-type', '').startswith('application/json'):
                    json.loads(response_text)
                    logger.info("🔧 ✅ Response is valid JSON")
            except json.JSONDecodeError:
                logger.warning("🔧 ⚠️ Response is not valid JSON")
                logger.warning(f"🔧 First 100 chars: {repr(response_text[:100])}")
        
        # Create response with clean headers that prevent compression
        clean_headers = {
            'Content-Type': response.headers.get('content-type', 'application/json'),
            'Cache-Control': 'no-transform',  # Prevent Cloudflare compression
        }
        
        flask_response = make_response(response_text, response.status_code, clean_headers)
        flask_response.headers['Content-Encoding'] = 'identity'  # Explicitly no compression
        flask_response.headers['Vary'] = 'Accept-Encoding'
        
        return flask_response

# Initialize load balancer
lb = CleanLoadBalancer()

@app.route('/health')
def health_check():
    """Load balancer health check endpoint"""
    healthy_instances = lb.get_healthy_instances()
    
    return jsonify({
        "status": "healthy" if healthy_instances else "unhealthy", 
        "strategy": lb.load_balance_strategy,
        "instances": [
            {
                "name": inst.name,
                "url": inst.url,
                "healthy": inst.is_healthy,
                "priority": inst.priority,
                "failure_count": inst.failure_count,
                "request_count": inst.request_count,
                "last_check": inst.last_check.isoformat()
            }
            for inst in lb.instances
        ],
        "timestamp": datetime.now().isoformat()
    })

@app.route('/status')
def status():
    """Detailed status endpoint"""
    healthy_count = len(lb.get_healthy_instances())
    total_requests = sum(inst.request_count for inst in lb.instances)
    
    return jsonify({
        "load_balancer": {
            "strategy": lb.load_balance_strategy,
            "check_interval": lb.check_interval,
            "failure_threshold": lb.failure_threshold,
            "request_timeout": lb.request_timeout,
            "total_requests": total_requests
        },
        "instances": [
            {
                "name": inst.name,
                "url": inst.url,
                "healthy": inst.is_healthy,
                "priority": inst.priority,
                "failure_count": inst.failure_count,
                "request_count": inst.request_count,
                "request_percentage": (inst.request_count / total_requests * 100) if total_requests > 0 else 0,
                "last_check": inst.last_check.isoformat(),
                "last_failure": inst.last_failure.isoformat() if inst.last_failure else None
            }
            for inst in lb.instances
        ],
        "summary": {
            "healthy_instances": healthy_count,
            "total_instances": len(lb.instances),
            "current_strategy": lb.load_balance_strategy
        },
        "timestamp": datetime.now().isoformat()
    })

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(path):
    """Proxy requests with forced uncompressed responses"""
    target_instance = lb.get_target_instance(request.method)
    
    if not target_instance:
        logger.error("No healthy ChromaDB instances available")
        return jsonify({
            "error": "No healthy ChromaDB instances available",
            "timestamp": datetime.now().isoformat()
        }), 503
    
    # Track request
    target_instance.request_count += 1
    
    # Construct full path
    full_path = f"/{path}" if path else ""
    
    try:
        return lb.proxy_request(target_instance.url, full_path, request.method)
    except ServiceUnavailable as e:
        # Try another healthy instance if available
        remaining_instances = [inst for inst in lb.get_healthy_instances() 
                             if inst != target_instance]
        
        if remaining_instances:
            backup_instance = remaining_instances[0]
            backup_instance.request_count += 1
            logger.info(f"Retrying with backup instance: {backup_instance.name}")
            return lb.proxy_request(backup_instance.url, full_path, request.method)
        
        return jsonify({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 503

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
