#!/usr/bin/env python3
"""
Optimized ChromaDB High Availability Load Balancer
Enhanced with connection pooling, request throttling, and circuit breaker patterns
"""

import os
import time
import logging
import requests
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
import random

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
    avg_response_time: float = 0.0
    total_requests: int = 0
    successful_requests: int = 0
    
    def update_stats(self, response_time: float, success: bool):
        """Update instance statistics"""
        self.total_requests += 1
        if success:
            self.successful_requests += 1
            self.consecutive_failures = 0
            # Update average response time
            self.avg_response_time = (self.avg_response_time * (self.successful_requests - 1) + response_time) / self.successful_requests
        else:
            self.consecutive_failures += 1
    
    def get_success_rate(self) -> float:
        """Get success rate as percentage"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100

class CircuitBreaker:
    """Circuit breaker pattern for service resilience"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def can_execute(self) -> bool:
        """Check if request can be executed"""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if self.last_failure_time and (datetime.now() - self.last_failure_time).seconds >= self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        elif self.state == "HALF_OPEN":
            return True
        return False
    
    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")

class RequestThrottler:
    """Request throttling and queuing for resource management"""
    
    def __init__(self, max_concurrent: int = 8, queue_size: int = 50):
        self.max_concurrent = max_concurrent
        self.semaphore = threading.Semaphore(max_concurrent)
        self.request_queue = Queue(maxsize=queue_size)
        self.active_requests = 0
        self.total_queued = 0
        self.total_rejected = 0
        
    def acquire(self, timeout: float = 5.0) -> bool:
        """Acquire a request slot"""
        try:
            if self.semaphore.acquire(timeout=timeout):
                self.active_requests += 1
                return True
            return False
        except:
            return False
    
    def release(self):
        """Release a request slot"""
        self.active_requests -= 1
        self.semaphore.release()
    
    def get_stats(self) -> Dict[str, int]:
        """Get throttling statistics"""
        return {
            "active_requests": self.active_requests,
            "max_concurrent": self.max_concurrent,
            "total_queued": self.total_queued,
            "total_rejected": self.total_rejected
        }

class ConnectionPool:
    """Connection pool for reusing HTTP sessions"""
    
    def __init__(self, pool_size: int = 10):
        self.pool_size = pool_size
        self.available_sessions = Queue(maxsize=pool_size)
        self.total_sessions = 0
        self.lock = threading.Lock()
        
        # Pre-populate pool
        for _ in range(pool_size):
            session = requests.Session()
            session.headers.update({
                'Accept-Encoding': '',  # No compression for compatibility
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            })
            self.available_sessions.put(session)
            self.total_sessions += 1
    
    def get_session(self, timeout: float = 1.0) -> Optional[requests.Session]:
        """Get a session from the pool"""
        try:
            return self.available_sessions.get(timeout=timeout)
        except Empty:
            # Pool exhausted, create temporary session
            with self.lock:
                if self.total_sessions < self.pool_size * 2:  # Allow temporary expansion
                    session = requests.Session()
                    session.headers.update({
                        'Accept-Encoding': '',
                        'Accept': 'application/json', 
                        'Content-Type': 'application/json'
                    })
                    self.total_sessions += 1
                    return session
            return None
    
    def return_session(self, session: requests.Session):
        """Return session to pool"""
        try:
            self.available_sessions.put_nowait(session)
        except:
            # Pool full, close excess session
            session.close()
            with self.lock:
                self.total_sessions -= 1

class OptimizedLoadBalancer:
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
        self.load_balance_strategy = os.getenv("LOAD_BALANCE_STRATEGY", "optimized_read_replica")
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "30"))
        self.failure_threshold = int(os.getenv("FAILURE_THRESHOLD", "3"))
        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "15"))  # Reduced from 30
        
        # Performance optimizations
        self.throttler = RequestThrottler(
            max_concurrent=int(os.getenv("MAX_CONCURRENT_REQUESTS", "8")),
            queue_size=int(os.getenv("REQUEST_QUEUE_SIZE", "50"))
        )
        self.connection_pool = ConnectionPool(
            pool_size=int(os.getenv("CONNECTION_POOL_SIZE", "10"))
        )
        self.circuit_breakers = {
            instance.name: CircuitBreaker(
                failure_threshold=self.failure_threshold,
                recovery_timeout=int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "30"))
            ) for instance in self.instances
        }
        
        # Load balancing state
        self.current_instance_index = 0
        self.read_replica_ratio = float(os.getenv("READ_REPLICA_RATIO", "0.8"))  # 80% reads to replica
        
        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "throttled_requests": 0,
            "circuit_breaker_trips": 0
        }
        
        # Start health monitoring
        self.health_thread = threading.Thread(target=self.health_monitor_loop, daemon=True)
        self.health_thread.start()
        
        logger.info(f"🚀 Optimized load balancer initialized")
        logger.info(f"📊 Max concurrent requests: {self.throttler.max_concurrent}")
        logger.info(f"🔗 Connection pool size: {self.connection_pool.pool_size}")
        logger.info(f"🎯 Read replica ratio: {self.read_replica_ratio * 100}%")

    def get_healthy_instances(self) -> List[ChromaInstance]:
        """Get all healthy instances"""
        healthy = []
        for instance in self.instances:
            circuit_breaker = self.circuit_breakers[instance.name]
            if instance.is_healthy and circuit_breaker.can_execute():
                healthy.append(instance)
        return healthy

    def select_instance_for_request(self, method: str, path: str) -> Optional[ChromaInstance]:
        """Intelligently select instance based on request type and health"""
        healthy_instances = self.get_healthy_instances()
        
        if not healthy_instances:
            logger.error("❌ No healthy instances available")
            return None
        
        # Write operations always go to primary
        if method in ['POST', 'PUT', 'DELETE'] or 'add' in path or 'update' in path or 'delete' in path:
            primary = next((inst for inst in healthy_instances if inst.name == "primary"), None)
            if primary:
                return primary
            # Fallback to any healthy instance if primary unavailable
            return healthy_instances[0]
        
        # Read operations - use optimized distribution
        if method == 'GET' or 'query' in path or 'get' in path:
            # 80% to replica, 20% to primary (configurable)
            if random.random() < self.read_replica_ratio:
                replica = next((inst for inst in healthy_instances if inst.name == "replica"), None)
                if replica:
                    return replica
            
            # Fallback to primary or any healthy instance
            primary = next((inst for inst in healthy_instances if inst.name == "primary"), None)
            if primary:
                return primary
            
            return healthy_instances[0]
        
        # Default: round-robin with performance weighting
        return self.select_best_performing_instance(healthy_instances)
    
    def select_best_performing_instance(self, instances: List[ChromaInstance]) -> ChromaInstance:
        """Select instance based on performance metrics"""
        if len(instances) == 1:
            return instances[0]
        
        # Weight by success rate and response time
        best_instance = instances[0]
        best_score = 0
        
        for instance in instances:
            # Score = success_rate * priority / avg_response_time
            success_rate = instance.get_success_rate()
            response_time = max(instance.avg_response_time, 0.1)  # Avoid division by zero
            score = (success_rate * instance.priority) / response_time
            
            if score > best_score:
                best_score = score
                best_instance = instance
        
        return best_instance

    def make_request_with_resilience(self, instance: ChromaInstance, method: str, path: str, **kwargs) -> requests.Response:
        """Make request with full resilience pattern"""
        circuit_breaker = self.circuit_breakers[instance.name]
        
        if not circuit_breaker.can_execute():
            raise Exception(f"Circuit breaker OPEN for {instance.name}")
        
        session = self.connection_pool.get_session(timeout=2.0)
        if not session:
            raise Exception("Connection pool exhausted")
        
        start_time = time.time()
        
        try:
            # Set adaptive timeout based on operation type
            timeout = self.get_adaptive_timeout(method, path)
            kwargs['timeout'] = timeout
            
            url = f"{instance.url}{path}"
            response = session.request(method, url, **kwargs)
            
            # Record success
            response_time = time.time() - start_time
            instance.update_stats(response_time, True)
            circuit_breaker.record_success()
            
            response.raise_for_status()
            return response
            
        except Exception as e:
            # Record failure
            response_time = time.time() - start_time
            instance.update_stats(response_time, False)
            circuit_breaker.record_failure()
            
            logger.warning(f"Request to {instance.name} failed: {e}")
            raise e
            
        finally:
            self.connection_pool.return_session(session)
    
    def get_adaptive_timeout(self, method: str, path: str) -> int:
        """Get adaptive timeout based on operation complexity"""
        # Quick operations
        if path in ['/health', '/status', '/api/v2/version', '/api/v2/heartbeat']:
            return 5
        
        # Read operations
        if method == 'GET' or 'get' in path:
            return 10
        
        # Query operations (more complex)
        if 'query' in path or 'search' in path:
            return 20
        
        # Write operations
        if method in ['POST', 'PUT'] or 'add' in path or 'update' in path:
            return 15
        
        # Delete operations
        if method == 'DELETE' or 'delete' in path:
            return 10
        
        # Default
        return self.request_timeout

    def health_monitor_loop(self):
        """Background health monitoring with improved logic"""
        while True:
            try:
                for instance in self.instances:
                    self.check_instance_health(instance)
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                time.sleep(60)

    def check_instance_health(self, instance: ChromaInstance):
        """Enhanced health check with circuit breaker awareness"""
        try:
            # Skip health check if circuit breaker is open
            circuit_breaker = self.circuit_breakers[instance.name]
            if circuit_breaker.state == "OPEN":
                logger.debug(f"Skipping health check for {instance.name} - circuit breaker OPEN")
                return
            
            start_time = time.time()
            response = requests.get(f"{instance.url}/api/v2/version", timeout=5)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                instance.is_healthy = True
                instance.update_stats(response_time, True)
                circuit_breaker.record_success()
                instance.last_health_check = datetime.now()
                logger.debug(f"✅ {instance.name} healthy (response time: {response_time:.2f}s)")
            else:
                instance.is_healthy = False
                instance.update_stats(response_time, False)
                circuit_breaker.record_failure()
                logger.warning(f"❌ {instance.name} unhealthy: HTTP {response.status_code}")
                
        except Exception as e:
            instance.is_healthy = False
            circuit_breaker.record_failure()
            logger.warning(f"❌ {instance.name} health check failed: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive load balancer status"""
        healthy_instances = self.get_healthy_instances()
        
        return {
            "strategy": self.load_balance_strategy,
            "healthy_instances": len(healthy_instances),
            "total_instances": len(self.instances),
            "max_concurrent_requests": self.throttler.max_concurrent,
            "active_requests": self.throttler.active_requests,
            "read_replica_ratio": self.read_replica_ratio,
            "instances": [
                {
                    "name": inst.name,
                    "url": inst.url,
                    "healthy": inst.is_healthy,
                    "priority": inst.priority,
                    "success_rate": f"{inst.get_success_rate():.1f}%",
                    "avg_response_time": f"{inst.avg_response_time:.3f}s",
                    "total_requests": inst.total_requests,
                    "circuit_breaker_state": self.circuit_breakers[inst.name].state,
                    "consecutive_failures": inst.consecutive_failures
                } for inst in self.instances
            ],
            "throttling_stats": self.throttler.get_stats(),
            "performance_stats": self.stats
        }

    def handle_request(self, method: str, path: str, **kwargs):
        """Handle request with full optimization pipeline"""
        self.stats["total_requests"] += 1
        
        # Step 1: Request throttling
        if not self.throttler.acquire(timeout=5.0):
            self.stats["throttled_requests"] += 1
            logger.warning("⚠️ Request throttled - too many concurrent requests")
            raise Exception("Service temporarily overloaded")
        
        try:
            # Step 2: Instance selection
            instance = self.select_instance_for_request(method, path)
            if not instance:
                raise Exception("No healthy instances available")
            
            # Step 3: Execute request with resilience
            response = self.make_request_with_resilience(instance, method, path, **kwargs)
            
            self.stats["successful_requests"] += 1
            return response
            
        except Exception as e:
            self.stats["failed_requests"] += 1
            
            # Check for circuit breaker trips
            if "Circuit breaker OPEN" in str(e):
                self.stats["circuit_breaker_trips"] += 1
            
            raise e
            
        finally:
            # Step 4: Release throttling
            self.throttler.release()

# Global load balancer instance
load_balancer = OptimizedLoadBalancer()

def get_load_balancer():
    """Get the global load balancer instance"""
    return load_balancer 