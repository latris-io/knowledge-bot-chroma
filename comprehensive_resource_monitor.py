#!/usr/bin/env python3
"""
Comprehensive Resource Monitoring for All ChromaDB Services
Monitors memory, CPU, disk space, and sends upgrade alerts
"""

import os
import time
import psutil
import requests
import logging
import threading
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class ServiceResourceMetrics:
    service_name: str
    memory_usage_mb: float
    memory_percent: float
    cpu_percent: float
    disk_usage_percent: float
    disk_free_gb: float
    disk_total_gb: float
    timestamp: datetime
    
class UniversalResourceMonitor:
    """Universal resource monitor that can be embedded in any service"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        self.database_url = os.getenv("DATABASE_URL")
        self.monitoring_interval = int(os.getenv("RESOURCE_CHECK_INTERVAL", "30"))
        
        # Thresholds for alerts
        self.memory_warning_threshold = 80  # 80%
        self.memory_critical_threshold = 95  # 95%
        self.cpu_warning_threshold = 80     # 80%
        self.cpu_critical_threshold = 95    # 95%
        self.disk_warning_threshold = 80    # 80%
        self.disk_critical_threshold = 90   # 90%
        
        # Alert frequency limiting (don't spam)
        self.last_alert_time = {}
        self.alert_cooldown_hours = 6
        
        self.monitoring_active = False
        self.monitor_thread = None
        
        logger.info(f"🔍 Resource monitor initialized for {service_name}")
    
    def start_monitoring(self):
        """Start background resource monitoring"""
        if self.monitoring_active:
            return
            
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"📊 Resource monitoring started for {self.service_name}")
    
    def stop_monitoring(self):
        """Stop resource monitoring"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info(f"⏹️ Resource monitoring stopped for {self.service_name}")
    
    def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                metrics = self.collect_metrics()
                self.analyze_and_alert(metrics)
                self.store_metrics(metrics)
                time.sleep(self.monitoring_interval)
            except Exception as e:
                logger.error(f"Resource monitoring error for {self.service_name}: {e}")
                time.sleep(60)  # Wait longer on error
    
    def collect_metrics(self) -> ServiceResourceMetrics:
        """Collect current resource usage metrics"""
        try:
            # FIXED: Use process-specific memory instead of system-wide memory
            process = psutil.Process()
            process_memory_info = process.memory_info()
            
            # Get container memory limit (default 512MB if not specified)
            container_memory_limit_mb = int(os.getenv("MEMORY_LIMIT_MB", "512"))
            
            # Calculate process-specific memory percentage
            process_memory_mb = process_memory_info.rss / (1024 * 1024)
            process_memory_percent = (process_memory_mb / container_memory_limit_mb) * 100
            
            # Validate memory percentage is reasonable (0-200% allowing for some burst)
            if process_memory_percent < 0 or process_memory_percent > 200:
                logger.warning(f"⚠️ Invalid process memory reading: {process_memory_percent}%, using system fallback")
                # Fallback to system memory if process monitoring fails
                system_memory = psutil.virtual_memory()
                process_memory_mb = system_memory.used / (1024 * 1024)
                process_memory_percent = system_memory.percent
            
            # FIXED: Use process-specific CPU instead of system-wide CPU
            try:
                process_cpu_percent = process.cpu_percent(interval=1.0)
                
                # Validate CPU percentage is reasonable (0-100%)
                if process_cpu_percent < 0 or process_cpu_percent > 100:
                    logger.warning(f"⚠️ Invalid process CPU reading: {process_cpu_percent}%, using system fallback")
                    process_cpu_percent = psutil.cpu_percent(interval=1.0)
            except Exception as e:
                logger.error(f"❌ Process CPU monitoring error: {e}, using system fallback")
                process_cpu_percent = psutil.cpu_percent(interval=1.0)
            
            # Disk metrics for root filesystem (container disk usage)
            disk = psutil.disk_usage('/')
            disk_total_gb = disk.total / (1024**3)
            disk_free_gb = disk.free / (1024**3)
            disk_usage_percent = (disk.used / disk.total) * 100
            
            # DEBUGGING: Log both system vs process metrics for comparison
            try:
                system_memory = psutil.virtual_memory()
                logger.info(f"🔍 MONITORING COMPARISON ({self.service_name}):")
                logger.info(f"   System Memory: {system_memory.percent:.1f}% (what we used to measure)")
                logger.info(f"   Process Memory: {process_memory_percent:.1f}% (what Render measures)")
                logger.info(f"   Process CPU: {process_cpu_percent:.1f}%")
                logger.info(f"   Container Limit: {container_memory_limit_mb}MB")
            except:
                pass  # Don't fail if logging fails
            
            return ServiceResourceMetrics(
                service_name=self.service_name,
                memory_usage_mb=process_memory_mb,
                memory_percent=process_memory_percent,
                cpu_percent=process_cpu_percent,
                disk_usage_percent=disk_usage_percent,
                disk_free_gb=disk_free_gb,
                disk_total_gb=disk_total_gb,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to collect metrics for {self.service_name}: {e}")
            # Return empty metrics on error
            return ServiceResourceMetrics(
                service_name=self.service_name,
                memory_usage_mb=0, memory_percent=0, cpu_percent=0,
                disk_usage_percent=0, disk_free_gb=0, disk_total_gb=0,
                timestamp=datetime.now()
            )
    
    def analyze_and_alert(self, metrics: ServiceResourceMetrics):
        """Analyze metrics and send alerts if needed"""
        alerts = []
        
        # Memory alerts
        if metrics.memory_percent >= self.memory_critical_threshold:
            alerts.append({
                'type': 'memory',
                'level': 'critical',
                'current': metrics.memory_percent,
                'threshold': self.memory_critical_threshold,
                'message': f'Memory usage CRITICAL: {metrics.memory_percent:.1f}%'
            })
        elif metrics.memory_percent >= self.memory_warning_threshold:
            alerts.append({
                'type': 'memory',
                'level': 'warning',
                'current': metrics.memory_percent,
                'threshold': self.memory_warning_threshold,
                'message': f'Memory usage HIGH: {metrics.memory_percent:.1f}%'
            })
        
        # CPU alerts
        if metrics.cpu_percent >= self.cpu_critical_threshold:
            alerts.append({
                'type': 'cpu',
                'level': 'critical',
                'current': metrics.cpu_percent,
                'threshold': self.cpu_critical_threshold,
                'message': f'CPU usage CRITICAL: {metrics.cpu_percent:.1f}%'
            })
        elif metrics.cpu_percent >= self.cpu_warning_threshold:
            alerts.append({
                'type': 'cpu',
                'level': 'warning',
                'current': metrics.cpu_percent,
                'threshold': self.cpu_warning_threshold,
                'message': f'CPU usage HIGH: {metrics.cpu_percent:.1f}%'
            })
        
        # Disk alerts
        if metrics.disk_usage_percent >= self.disk_critical_threshold:
            alerts.append({
                'type': 'disk',
                'level': 'critical',
                'current': metrics.disk_usage_percent,
                'threshold': self.disk_critical_threshold,
                'message': f'Disk usage CRITICAL: {metrics.disk_usage_percent:.1f}% (Free: {metrics.disk_free_gb:.1f}GB)'
            })
        elif metrics.disk_usage_percent >= self.disk_warning_threshold:
            alerts.append({
                'type': 'disk',
                'level': 'warning',
                'current': metrics.disk_usage_percent,
                'threshold': self.disk_warning_threshold,
                'message': f'Disk usage HIGH: {metrics.disk_usage_percent:.1f}% (Free: {metrics.disk_free_gb:.1f}GB)'
            })
        
        # Send alerts with frequency limiting
        for alert in alerts:
            self.send_alert_if_needed(alert, metrics)
    
    def send_alert_if_needed(self, alert: Dict[str, Any], metrics: ServiceResourceMetrics):
        """Send alert with frequency limiting"""
        alert_key = f"{alert['type']}_{alert['level']}"
        current_time = time.time()
        
        # Check if we've sent this alert recently
        if alert_key in self.last_alert_time:
            time_since_last = current_time - self.last_alert_time[alert_key]
            if time_since_last < (self.alert_cooldown_hours * 3600):
                return  # Skip - too soon since last alert
        
        # Send the alert
        self.send_slack_alert(alert, metrics)
        self.last_alert_time[alert_key] = current_time
    
    def send_slack_alert(self, alert: Dict[str, Any], metrics: ServiceResourceMetrics):
        """Send Slack alert for resource issue"""
        if not self.slack_webhook:
            logger.warning(f"No Slack webhook configured - would send alert: {alert['message']}")
            return
        
        # Determine alert styling
        if alert['level'] == 'critical':
            color = "danger"
            emoji = "🚨"
        else:
            color = "warning"
            emoji = "⚠️"
        
        # Generate upgrade recommendation
        upgrade_rec = self.generate_upgrade_recommendation(alert['type'], metrics)
        
        # Create Slack message
        message = f"*{alert['message']}*\n"
        message += f"Service: {self.service_name}\n"
        message += f"Current Usage: {alert['current']:.1f}%\n"
        if upgrade_rec:
            message += f"\n**Upgrade Recommendation:**\n{upgrade_rec}"
        
        payload = {
            "text": f"{emoji} ChromaDB Resource Alert",
            "attachments": [
                {
                    "color": color,
                    "title": f"{self.service_name} - {alert['type'].title()} {alert['level'].title()}",
                    "text": message,
                    "footer": "ChromaDB Resource Monitoring",
                    "ts": int(time.time()),
                    "fields": [
                        {
                            "title": "Memory Usage",
                            "value": f"{metrics.memory_percent:.1f}%",
                            "short": True
                        },
                        {
                            "title": "CPU Usage",
                            "value": f"{metrics.cpu_percent:.1f}%",
                            "short": True
                        },
                        {
                            "title": "Disk Usage",
                            "value": f"{metrics.disk_usage_percent:.1f}%",
                            "short": True
                        },
                        {
                            "title": "Disk Free",
                            "value": f"{metrics.disk_free_gb:.1f}GB",
                            "short": True
                        }
                    ]
                }
            ]
        }
        
        try:
            response = requests.post(self.slack_webhook, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info(f"📱 Slack alert sent for {self.service_name}: {alert['message']}")
            else:
                logger.warning(f"❌ Slack alert failed for {self.service_name}: HTTP {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send Slack alert for {self.service_name}: {e}")
    
    def generate_upgrade_recommendation(self, resource_type: str, metrics: ServiceResourceMetrics) -> Optional[str]:
        """Generate upgrade recommendation based on resource usage"""
        if resource_type == 'memory':
            if metrics.memory_percent > 95:
                return "• Upgrade to Standard+ plan ($21/month) for 2GB RAM\n• Consider adding more workers if applicable"
            elif metrics.memory_percent > 85:
                return "• Monitor closely - upgrade may be needed soon\n• Consider Standard plan ($7/month) for 1GB RAM"
        
        elif resource_type == 'cpu':
            if metrics.cpu_percent > 95:
                return "• Upgrade to Standard+ plan ($21/month) for 1 CPU\n• Consider distributing load across multiple services"
            elif metrics.cpu_percent > 85:
                return "• Monitor performance - upgrade may improve response times\n• Standard plan ($7/month) provides more CPU"
        
        elif resource_type == 'disk':
            if metrics.disk_usage_percent > 90:
                if 'primary' in self.service_name or 'replica' in self.service_name:
                    return f"• Increase disk size from 10GB to 20GB (+$5/month)\n• Current free space: {metrics.disk_free_gb:.1f}GB"
                else:
                    return "• Clear logs and temporary files\n• Consider upgrading plan for more storage"
            elif metrics.disk_usage_percent > 80:
                return "• Monitor disk growth patterns\n• Plan for storage expansion"
        
        return None
    
    def store_metrics(self, metrics: ServiceResourceMetrics):
        """Store metrics in database if available"""
        if not self.database_url:
            return
        
        try:
            import psycopg2
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # Create table if not exists
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS service_resource_metrics (
                            id SERIAL PRIMARY KEY,
                            service_name VARCHAR(50) NOT NULL,
                            memory_usage_mb REAL NOT NULL,
                            memory_percent REAL NOT NULL,
                            cpu_percent REAL NOT NULL,
                            disk_usage_percent REAL NOT NULL,
                            disk_free_gb REAL NOT NULL,
                            disk_total_gb REAL NOT NULL,
                            recorded_at TIMESTAMP DEFAULT NOW()
                        )
                    """)
                    
                    # Insert metrics
                    cursor.execute("""
                        INSERT INTO service_resource_metrics 
                        (service_name, memory_usage_mb, memory_percent, cpu_percent, 
                         disk_usage_percent, disk_free_gb, disk_total_gb)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        metrics.service_name,
                        metrics.memory_usage_mb,
                        metrics.memory_percent,
                        metrics.cpu_percent,
                        metrics.disk_usage_percent,
                        metrics.disk_free_gb,
                        metrics.disk_total_gb
                    ))
                conn.commit()
        except Exception as e:
            logger.debug(f"Failed to store metrics for {self.service_name}: {e}")
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current resource status summary"""
        metrics = self.collect_metrics()
        
        return {
            "service": self.service_name,
            "status": "healthy" if (
                metrics.memory_percent < self.memory_warning_threshold and
                metrics.cpu_percent < self.cpu_warning_threshold and
                metrics.disk_usage_percent < self.disk_warning_threshold
            ) else "warning",
            "memory_percent": round(metrics.memory_percent, 1),
            "cpu_percent": round(metrics.cpu_percent, 1),
            "disk_usage_percent": round(metrics.disk_usage_percent, 1),
            "disk_free_gb": round(metrics.disk_free_gb, 1),
            "timestamp": metrics.timestamp.isoformat()
        }

# Convenience function for easy integration
def start_resource_monitoring(service_name: str):
    """Start resource monitoring for a service"""
    monitor = UniversalResourceMonitor(service_name)
    monitor.start_monitoring()
    return monitor

# Example usage
if __name__ == "__main__":
    # Test the monitor
    import sys
    service_name = sys.argv[1] if len(sys.argv) > 1 else "test-service"
    
    monitor = start_resource_monitoring(service_name)
    
    try:
        while True:
            status = monitor.get_current_status()
            print(f"Status: {status}")
            time.sleep(30)
    except KeyboardInterrupt:
        monitor.stop_monitoring()
        print("Monitoring stopped") 