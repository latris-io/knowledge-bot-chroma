#!/usr/bin/env python3
"""
ChromaDB True Load Balancer for Render
Now with data sync, we can do actual load balancing!
"""

import os
import time
import requests
import logging
import json
from flask import Flask, request, jsonify, Response
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
        self.request_count = 0  # For round-robin

class TrueLoadBalancer:
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
        # Options: "round_robin", "random", "priority", "write_primary"
        
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "30"))
        self.failure_threshold = int(os.getenv("FAILURE_THRESHOLD", "3"))
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "30"))
        
        self.current_instance_index = 0  # For round-robin
        
        # Start health monitoring thread
        self.health_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
        self.health_thread.start()
        
        logger.info(f"True load balancer initialized with strategy: {self.load_balance_strategy}")

    def get_healthy_instances(self) -> List[ChromaInstance]:
        """Get all healthy instances"""
        return [inst for inst in self.instances if inst.is_healthy]

    def get_instance_round_robin(self) -> Optional[ChromaInstance]:
        """Round-robin load balancing"""
        healthy_instances = self.get_healthy_instances()
        if not healthy_instances:
            return None
        
        # Rotate through healthy instances
        instance = healthy_instances[self.current_instance_index % len(healthy_instances)]
        self.current_instance_index += 1
        
        logger.debug(f"Round-robin selected: {instance.name}")
        return instance

    def get_instance_random(self) -> Optional[ChromaInstance]:
        """Random load balancing"""
        healthy_instances = self.get_healthy_instances()
        if not healthy_instances:
            return None
        
        instance = random.choice(healthy_instances)
        logger.debug(f"Random selected: {instance.name}")
        return instance

    def get_instance_priority(self) -> Optional[ChromaInstance]:
        """Priority-based (original failover behavior)"""
        healthy_instances = self.get_healthy_instances()
        if not healthy_instances:
            return None
        
        instance = max(healthy_instances, key=lambda x: x.priority)
        logger.debug(f"Priority selected: {instance.name}")
        return instance

    def get_instance_write_primary(self, method: str) -> Optional[ChromaInstance]:
        """Writes to primary, reads distributed"""
        healthy_instances = self.get_healthy_instances()
        if not healthy_instances:
            return None
        
        # Writes go to primary only
        if method in ['POST', 'PUT', 'DELETE', 'PATCH']:
            primary = next((inst for inst in healthy_instances if inst.name == "primary"), None)
            if primary:
                logger.debug(f"Write operation routed to primary")
                return primary
            else:
                # Primary down, use any healthy instance
                instance = healthy_instances[0]
                logger.warning(f"Primary down, write routed to {instance.name}")
                return instance
        
        # Reads can go anywhere (round-robin)
        instance = healthy_instances[self.current_instance_index % len(healthy_instances)]
        self.current_instance_index += 1
        logger.debug(f"Read operation routed to {instance.name}")
        return instance

    def get_target_instance(self, method: str = "GET") -> Optional[ChromaInstance]:
        """Get target instance based on load balancing strategy"""
        if self.load_balance_strategy == "round_robin":
            return self.get_instance_round_robin()
        elif self.load_balance_strategy == "random":
            return self.get_instance_random()
        elif self.load_balance_strategy == "priority":
            return self.get_instance_priority()
        elif self.load_balance_strategy == "write_primary":
            return self.get_instance_write_primary(method)
        else:
            # Default to round-robin
            return self.get_instance_round_robin()

    def check_instance_health(self, instance: ChromaInstance) -> bool:
        """Check if a ChromaDB instance is healthy"""
        try:
            response = requests.get(
                f"{instance.url}/api/v2/version",
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed for {instance.name}: {e}")
            return False

    def update_instance_health(self, instance: ChromaInstance, is_healthy: bool):
        """Update instance health status"""
        instance.last_check = datetime.now()
        
        if is_healthy:
            if not instance.is_healthy:
                logger.info(f"Instance {instance.name} recovered")
                self.send_notification(f"ChromaDB instance {instance.name} recovered")
            instance.is_healthy = True
            instance.failure_count = 0
        else:
            instance.failure_count += 1
            if instance.failure_count >= self.failure_threshold:
                if instance.is_healthy:
                    logger.error(f"Instance {instance.name} marked as unhealthy")
                    self.send_notification(f"ChromaDB instance {instance.name} failed")
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

    def send_notification(self, message: str):
        """Send notification about health changes"""
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not webhook_url:
            return
        
        try:
            payload = {
                "text": f"ChromaDB True Load Balancer Alert: {message}",
                "timestamp": datetime.now().isoformat()
            }
            requests.post(webhook_url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def proxy_request(self, target_url: str, path: str, method: str, **kwargs) -> Response:
        """Proxy request to target ChromaDB instance"""
        try:
            url = f"{target_url}{path}"
            
            if method == 'GET':
                # For GET requests, make them EXACTLY like working health checks
                # Health check: requests.get(f"{instance.url}/api/v2/version", timeout=10)
                # This works perfectly, so replicate it exactly
                
                # Add query parameters to URL if present
                if request.args:
                    query_string = urlencode(request.args)
                    url = f"{url}?{query_string}"
                
                # Make simple GET request exactly like health check - use same timeout too!
                response = requests.get(url, timeout=10)
                
                # Create proper Flask Response object but keep it simple
                return Response(
                    response.text,
                    status=response.status_code,
                    mimetype='application/json'
                )
                
            else:
                # For non-GET requests, use full parameter handling
                req_params = {
                    "timeout": self.request_timeout,
                    "allow_redirects": False
                }
                
                # Handle request body - improved JSON handling for ChromaDB client
                if request.content_type and 'application/json' in request.content_type:
                    # For JSON requests, try to get the JSON data safely
                    try:
                        if request.is_json and request.json is not None:
                            req_params["json"] = request.json
                        elif request.data:
                            # Try to parse as JSON first
                            try:
                                json_data = json.loads(request.data.decode('utf-8'))
                                req_params["json"] = json_data
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                # If not valid JSON, send as raw data
                                req_params["data"] = request.data
                        else:
                            # No body data
                            pass
                    except Exception as e:
                        logger.warning(f"JSON handling error: {e}, falling back to raw data")
                        if request.data:
                            req_params["data"] = request.data
                elif request.data:
                    # Non-JSON data
                    req_params["data"] = request.data
                
                # Prepare headers for non-GET requests
                headers = {}
                for key, value in request.headers.items():
                    lower_key = key.lower()
                    if lower_key not in ['host', 'content-length', 'connection', 'upgrade-insecure-requests']:
                        headers[key] = value
                
                # Set appropriate Content-Type
                if request.is_json:
                    headers['Content-Type'] = 'application/json'
                elif request.content_type and request.content_type not in headers:
                    headers['Content-Type'] = request.content_type
                
                req_params["headers"] = headers
                
                # Add query parameters
                if request.args:
                    req_params["params"] = request.args
                
                # Make the request
                response = requests.request(method, url, **req_params)
                
                # For all responses, return simple Flask response using response.text
                # The requests library automatically handles decompression
                return Response(
                    response.text,
                    status=response.status_code,
                    mimetype='application/json' if 'json' in response.headers.get('content-type', '') else None
                )
            
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout to {target_url}")
            raise ServiceUnavailable("Request timeout")
        except Exception as e:
            logger.error(f"Proxy error to {target_url}: {e}")
            raise ServiceUnavailable(f"Proxy error: {str(e)}")

# Initialize load balancer
lb = TrueLoadBalancer()

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
    """Proxy requests using true load balancing"""
    # Get target instance based on strategy
    target_instance = lb.get_target_instance(request.method)
    
    if not target_instance:
        logger.error("No healthy ChromaDB instances available")
        return jsonify({
            "error": "No healthy ChromaDB instances available",
            "timestamp": datetime.now().isoformat()
        }), 503
    
    # Track request
    target_instance.request_count += 1
    logger.debug(f"Request routed to {target_instance.name}, new count: {target_instance.request_count}")
    
    # Construct full path
    full_path = f"/{path}" if path else ""
    
    try:
        return lb.proxy_request(
            target_instance.url,
            full_path,
            request.method
        )
    except ServiceUnavailable as e:
        # Try another healthy instance if available
        remaining_instances = [inst for inst in lb.get_healthy_instances() 
                             if inst != target_instance]
        
        if remaining_instances:
            backup_instance = remaining_instances[0]  # Use first available
            backup_instance.request_count += 1
            logger.info(f"Retrying with backup instance: {backup_instance.name}")
            return lb.proxy_request(
                backup_instance.url,
                full_path,
                request.method
            )
        
        return jsonify({
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 503

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False) 