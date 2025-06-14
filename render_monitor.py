#!/usr/bin/env python3
"""
ChromaDB Background Monitor for Render
Advanced monitoring and failover management
"""

import os
import time
import requests
import logging
import json
import schedule
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import DictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RenderMonitor:
    def __init__(self):
        self.primary_url = os.getenv("PRIMARY_URL", "https://chroma-primary.onrender.com")
        self.replica_url = os.getenv("REPLICA_URL", "https://chroma-replica.onrender.com")
        self.load_balancer_url = os.getenv("LOAD_BALANCER_URL", "https://chroma-load-balancer.onrender.com")
        
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "30"))
        self.failure_threshold = int(os.getenv("FAILURE_THRESHOLD", "3"))
        self.notification_webhook = os.getenv("SLACK_WEBHOOK_URL")
        
        # Database connection for storing metrics (optional)
        self.db_url = os.getenv("DATABASE_URL")
        self.db_conn = None
        
        if self.db_url:
            self.init_database()
        
        logger.info("Render monitor initialized")

    def init_database(self):
        """Initialize database connection and tables"""
        try:
            self.db_conn = psycopg2.connect(self.db_url)
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS health_metrics (
                        id SERIAL PRIMARY KEY,
                        instance_name VARCHAR(50) NOT NULL,
                        instance_url VARCHAR(255) NOT NULL,
                        is_healthy BOOLEAN NOT NULL,
                        response_time_ms INTEGER,
                        error_message TEXT,
                        checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS failover_events (
                        id SERIAL PRIMARY KEY,
                        event_type VARCHAR(50) NOT NULL,
                        from_instance VARCHAR(50),
                        to_instance VARCHAR(50),
                        reason TEXT,
                        success BOOLEAN,
                        occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                self.db_conn.commit()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            self.db_conn = None

    def check_instance_health(self, name: str, url: str) -> Dict:
        """Check health of a ChromaDB instance"""
        start_time = time.time()
        
        try:
            response = requests.get(f"{url}/api/v2/version", timeout=10)
            response_time = int((time.time() - start_time) * 1000)
            
            is_healthy = response.status_code == 200
            
            result = {
                "name": name,
                "url": url,
                "healthy": is_healthy,
                "response_time_ms": response_time,
                "status_code": response.status_code,
                "error": None
            }
            
            if is_healthy:
                logger.debug(f"{name} is healthy (response time: {response_time}ms)")
            else:
                logger.warning(f"{name} returned status {response.status_code}")
                result["error"] = f"HTTP {response.status_code}"
            
            return result
            
        except requests.exceptions.Timeout:
            response_time = int((time.time() - start_time) * 1000)
            logger.warning(f"{name} health check timed out")
            return {
                "name": name,
                "url": url,
                "healthy": False,
                "response_time_ms": response_time,
                "status_code": None,
                "error": "Timeout"
            }
        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            logger.error(f"{name} health check failed: {e}")
            return {
                "name": name,
                "url": url,
                "healthy": False,
                "response_time_ms": response_time,
                "status_code": None,
                "error": str(e)
            }

    def store_health_metrics(self, health_result: Dict):
        """Store health check results in database"""
        if not self.db_conn:
            return
        
        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO health_metrics 
                    (instance_name, instance_url, is_healthy, response_time_ms, error_message)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    health_result["name"],
                    health_result["url"],
                    health_result["healthy"],
                    health_result["response_time_ms"],
                    health_result["error"]
                ))
            self.db_conn.commit()
        except Exception as e:
            logger.error(f"Failed to store health metrics: {e}")

    def get_load_balancer_status(self) -> Dict:
        """Get status from load balancer"""
        try:
            response = requests.get(f"{self.load_balancer_url}/status", timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Load balancer status check failed: {response.status_code}")
                return {}
        except Exception as e:
            logger.error(f"Failed to get load balancer status: {e}")
            return {}

    def send_notification(self, message: str, severity: str = "info"):
        """Send notification via webhook"""
        if not self.notification_webhook:
            return
        
        try:
            color_map = {
                "info": "#36a64f",     # Green
                "warning": "#ff9500",  # Orange  
                "error": "#ff0000",    # Red
                "critical": "#800080"  # Purple
            }
            
            payload = {
                "text": f"ChromaDB Monitor Alert",
                "attachments": [
                    {
                        "color": color_map.get(severity, "#36a64f"),
                        "fields": [
                            {
                                "title": "Alert",
                                "value": message,
                                "short": False
                            },
                            {
                                "title": "Severity",
                                "value": severity.upper(),
                                "short": True
                            },
                            {
                                "title": "Timestamp",
                                "value": datetime.now().isoformat(),
                                "short": True
                            }
                        ]
                    }
                ]
            }
            
            response = requests.post(self.notification_webhook, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"Notification sent: {message}")
            else:
                logger.warning(f"Notification failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def cleanup_old_metrics(self):
        """Clean up old health metrics (keep last 7 days)"""
        if not self.db_conn:
            return
        
        try:
            with self.db_conn.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM health_metrics 
                    WHERE checked_at < %s
                """, (datetime.now() - timedelta(days=7),))
                
                deleted_count = cursor.rowcount
                self.db_conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old health metrics")
                    
        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")

    def generate_health_report(self) -> Dict:
        """Generate comprehensive health report"""
        # Check individual instances
        primary_health = self.check_instance_health("primary", self.primary_url)
        replica_health = self.check_instance_health("replica", self.replica_url)
        
        # Store metrics
        self.store_health_metrics(primary_health)
        self.store_health_metrics(replica_health)
        
        # Get load balancer status
        lb_status = self.get_load_balancer_status()
        
        # Generate report
        report = {
            "timestamp": datetime.now().isoformat(),
            "instances": {
                "primary": primary_health,
                "replica": replica_health
            },
            "load_balancer": lb_status,
            "summary": {
                "healthy_instances": sum(1 for h in [primary_health, replica_health] if h["healthy"]),
                "total_instances": 2,
                "load_balancer_healthy": bool(lb_status.get("instances"))
            }
        }
        
        return report

    def monitor_check(self):
        """Perform monitoring check"""
        try:
            report = self.generate_health_report()
            
            # Check for critical issues
            healthy_count = report["summary"]["healthy_instances"]
            
            if healthy_count == 0:
                self.send_notification(
                    "CRITICAL: All ChromaDB instances are unhealthy!",
                    "critical"
                )
            elif healthy_count == 1:
                unhealthy_instance = None
                for name, health in report["instances"].items():
                    if not health["healthy"]:
                        unhealthy_instance = name
                        break
                
                if unhealthy_instance:
                    self.send_notification(
                        f"WARNING: ChromaDB {unhealthy_instance} instance is unhealthy. Running on backup.",
                        "warning"
                    )
            
            # Log summary
            logger.info(f"Health check complete: {healthy_count}/2 instances healthy")
            
        except Exception as e:
            logger.error(f"Monitor check failed: {e}")
            self.send_notification(f"Monitor check failed: {str(e)}", "error")

    def run(self):
        """Main monitoring loop"""
        logger.info("Starting ChromaDB monitor...")
        
        # Schedule regular tasks
        schedule.every(self.check_interval).seconds.do(self.monitor_check)
        schedule.every().hour.do(self.cleanup_old_metrics)
        
        # Initial check
        self.monitor_check()
        
        # Main loop
        while True:
            try:
                schedule.run_pending()
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Monitor shutting down...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}")
                time.sleep(self.check_interval)

if __name__ == "__main__":
    monitor = RenderMonitor()
    monitor.run() 