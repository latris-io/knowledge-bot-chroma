#!/usr/bin/env python3
"""
ChromaDB Load Balancer for Render
Proxies requests to healthy ChromaDB instances with automatic failover
"""

import os
import time
import requests
import logging
from flask import Flask, request, jsonify, Response
from werkzeug.exceptions import ServiceUnavailable
import threading
from typing import Dict, List, Optional
from datetime import datetime, timedelta

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

class LoadBalancer:
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
        
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "30"))
        self.failure_threshold = int(os.getenv("FAILURE_THRESHOLD", "3"))
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "30"))
        
        # Start health monitoring thread
        self.health_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
        self.health_thread.start()
        
        logger.info(f"Load balancer initialized with {len(self.instances)} instances")

    def check_instance_health(self, instance: ChromaInstance) -> bool:
        """Check if a ChromaDB instance is healthy"""
        try:
            response = requests.get(
                f"{instance.url}/api/v1/heartbeat",
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

    def get_healthy_instance(self) -> Optional[ChromaInstance]:
        """Get the best healthy instance"""
        healthy_instances = [inst for inst in self.instances if inst.is_healthy]
        
        if not healthy_instances:
            return None
        
        # Return instance with highest priority
        return max(healthy_instances, key=lambda x: x.priority)

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
        webhook_url = os.getenv("NOTIFICATION_WEBHOOK")
        if not webhook_url:
            return
        
        try:
            payload = {
                "text": f"ChromaDB Load Balancer Alert: {message}",
                "timestamp": datetime.now().isoformat()
            }
            requests.post(webhook_url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def proxy_request(self, target_url: str, path: str, method: str, **kwargs) -> Response:
        """Proxy request to target ChromaDB instance"""
        try:
            url = f"{target_url}{path}"
            
            # Prepare request parameters
            req_params = {
                "timeout": self.request_timeout,
                "allow_redirects": False
            }
            
            # Add request body for POST/PUT requests
            if request.data:
                req_params["data"] = request.data
            elif request.json:
                req_params["json"] = request.json
            
            # Add headers (exclude host header)
            headers = {k: v for k, v in request.headers.items() 
                      if k.lower() not in ['host', 'content-length']}
            req_params["headers"] = headers
            
            # Add query parameters
            if request.args:
                req_params["params"] = request.args
            
            # Make the request
            response = requests.request(method, url, **req_params)
            
            # Create Flask response
            flask_response = Response(
                response.content,
                status=response.status_code,
                headers=dict(response.headers)
            )
            
            return flask_response
            
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout to {target_url}")
            raise ServiceUnavailable("Request timeout")
        except Exception as e:
            logger.error(f"Proxy error to {target_url}: {e}")
            raise ServiceUnavailable(f"Proxy error: {str(e)}")

# Initialize load balancer
lb = LoadBalancer()

@app.route('/health')
def health_check():
    """Load balancer health check endpoint"""
    healthy_instances = [inst for inst in lb.instances if inst.is_healthy]
    
    return jsonify({
        "status": "healthy" if healthy_instances else "unhealthy",
        "instances": [
            {
                "name": inst.name,
                "url": inst.url,
                "healthy": inst.is_healthy,
                "priority": inst.priority,
                "failure_count": inst.failure_count,
                "last_check": inst.last_check.isoformat()
            }
            for inst in lb.instances
        ],
        "timestamp": datetime.now().isoformat()
    })

@app.route('/status')
def status():
    """Detailed status endpoint"""
    return jsonify({
        "load_balancer": {
            "check_interval": lb.check_interval,
            "failure_threshold": lb.failure_threshold,
            "request_timeout": lb.request_timeout
        },
        "instances": [
            {
                "name": inst.name,
                "url": inst.url,
                "healthy": inst.is_healthy,
                "priority": inst.priority,
                "failure_count": inst.failure_count,
                "last_check": inst.last_check.isoformat(),
                "last_failure": inst.last_failure.isoformat() if inst.last_failure else None
            }
            for inst in lb.instances
        ],
        "timestamp": datetime.now().isoformat()
    })

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
def proxy(path):
    """Proxy all requests to healthy ChromaDB instance"""
    # Get healthy instance
    target_instance = lb.get_healthy_instance()
    
    if not target_instance:
        logger.error("No healthy ChromaDB instances available")
        return jsonify({
            "error": "No healthy ChromaDB instances available",
            "timestamp": datetime.now().isoformat()
        }), 503
    
    # Construct full path
    full_path = f"/{path}" if path else ""
    
    try:
        return lb.proxy_request(
            target_instance.url,
            full_path,
            request.method
        )
    except ServiceUnavailable as e:
        # Try next healthy instance if available
        remaining_instances = [inst for inst in lb.instances 
                             if inst.is_healthy and inst != target_instance]
        
        if remaining_instances:
            backup_instance = max(remaining_instances, key=lambda x: x.priority)
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