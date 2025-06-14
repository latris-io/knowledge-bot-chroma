# 📊 Service Monitoring Integration Guide

## 🎯 **Comprehensive Disk Space Monitoring for ALL Services**

This guide shows how to add **memory, CPU, and disk space monitoring** to every ChromaDB service with **automatic Slack alerts** and **upgrade recommendations**.

## 🔍 **Monitoring Coverage**

| Service | Memory | CPU | Disk Space | Alerts | Auto Upgrade Recs |
|---------|--------|-----|------------|--------|-------------------|
| **chroma-primary** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **chroma-replica** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **chroma-load-balancer** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **chroma-monitor** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **chroma-sync** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **chroma-metadata** | ✅ | ✅ | ✅ | ✅ | ✅ |

## 🚀 **Integration Steps**

### **1. Load Balancer Integration**

Add to `load_balancer.py`:

```python
# Add at the top
from comprehensive_resource_monitor import start_resource_monitoring

# Add in main() function or __init__
monitor = start_resource_monitoring("chroma-load-balancer")

# Monitor will automatically:
# - Track memory, CPU, disk usage every 30 seconds
# - Send Slack alerts when thresholds are exceeded
# - Provide upgrade recommendations with cost estimates
```

### **2. Monitor Service Integration**

Add to `render_monitor.py`:

```python
# Add at the top
from comprehensive_resource_monitor import start_resource_monitoring

# Add in RenderMonitor.__init__()
self.resource_monitor = start_resource_monitoring("chroma-monitor")

# Add method to get all service statuses
def get_comprehensive_status(self):
    status = self.generate_health_report()
    status["resource_metrics"] = self.resource_monitor.get_current_status()
    return status
```

### **3. ChromaDB Instance Monitoring**

For **chroma-primary** and **chroma-replica**, create a simple monitoring wrapper:

```python
# Create monitoring_wrapper.py
from comprehensive_resource_monitor import start_resource_monitoring
import os
import time

def start_chroma_with_monitoring():
    # Determine service name from environment
    service_role = os.getenv("INSTANCE_ROLE", "unknown")
    service_name = f"chroma-{service_role}"
    
    # Start resource monitoring
    monitor = start_resource_monitoring(service_name)
    
    # Keep monitoring alive
    try:
        while True:
            time.sleep(60)  # Keep process alive for monitoring
    except KeyboardInterrupt:
        monitor.stop_monitoring()

if __name__ == "__main__":
    start_chroma_with_monitoring()
```

Add to Dockerfile:
```dockerfile
# Copy monitoring files
COPY comprehensive_resource_monitor.py /app/
COPY monitoring_wrapper.py /app/

# Install psutil for resource monitoring
RUN pip install psutil

# Start both ChromaDB and monitoring
CMD ["sh", "-c", "python /app/monitoring_wrapper.py & chroma run --host 0.0.0.0 --port 8000 --path /chroma/chroma"]
```

### **4. PostgreSQL Database Monitoring**

PostgreSQL monitoring is handled by connecting to the database externally. Add this to `render_monitor.py`:

```python
def monitor_database_resources(self):
    """Monitor PostgreSQL database resources"""
    if not self.db_url:
        return
    
    try:
        with psycopg2.connect(self.db_url) as conn:
            with conn.cursor() as cursor:
                # Check database size
                cursor.execute("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as size,
                           pg_database_size(current_database()) as size_bytes
                """)
                size_data = cursor.fetchone()
                
                # Check connection count
                cursor.execute("SELECT count(*) FROM pg_stat_activity")
                connection_count = cursor.fetchone()[0]
                
                # Log metrics
                logger.info(f"📊 Database size: {size_data[0]}, Connections: {connection_count}")
                
                # Alert if database is getting large (approaching free tier limit)
                if size_data[1] > 800 * 1024 * 1024:  # 800MB (close to 1GB limit)
                    self.send_notification(
                        f"Database size approaching limit: {size_data[0]} (free tier is 1GB)",
                        "warning"
                    )
                    
    except Exception as e:
        logger.error(f"Database monitoring failed: {e}")
```

## ⚠️ **Alert Thresholds**

| Resource | Warning | Critical | Action |
|----------|---------|----------|---------|
| **Memory** | 80% | 95% | Upgrade plan recommendation |
| **CPU** | 80% | 95% | Performance optimization alert |
| **Disk Space** | 80% | 90% | Storage expansion recommendation |

### **Disk Space Specifics:**

- **Persistent Disks** (primary/replica): Monitor 10GB storage, alert when >8GB used
- **Local Storage** (all services): Monitor for log files, temp data, cache buildup
- **Database**: Monitor PostgreSQL size approaching free tier 1GB limit

## 📱 **Slack Alert Examples**

### **Disk Space Alert:**
```
🚨 ChromaDB Resource Alert
chroma-primary - Disk Critical

Disk usage CRITICAL: 92.3% (Free: 0.8GB)
Service: chroma-primary
Current Usage: 92.3%

Upgrade Recommendation:
• Increase disk size from 10GB to 20GB (+$5/month)
• Current free space: 0.8GB

Memory Usage: 67.2%    CPU Usage: 45.1%
Disk Usage: 92.3%      Disk Free: 0.8GB
```

### **Memory Alert:**
```
⚠️ ChromaDB Resource Alert
chroma-load-balancer - Memory Warning

Memory usage HIGH: 85.4%
Service: chroma-load-balancer
Current Usage: 85.4%

Upgrade Recommendation:
• Monitor closely - upgrade may be needed soon
• Consider Standard plan ($7/month) for 1GB RAM
```

## 🔧 **Environment Variables**

Add to all services in `render.yaml`:

```yaml
envVars:
  # Existing variables...
  - key: SLACK_WEBHOOK_URL
    sync: false
  - key: RESOURCE_CHECK_INTERVAL
    value: "30"  # Check every 30 seconds
```

## 📊 **Database Storage**

All metrics are automatically stored in PostgreSQL:

```sql
-- View recent resource metrics
SELECT service_name, memory_percent, cpu_percent, disk_usage_percent, 
       disk_free_gb, recorded_at 
FROM service_resource_metrics 
WHERE recorded_at > NOW() - INTERVAL '1 hour'
ORDER BY recorded_at DESC;

-- Check which services need attention
SELECT service_name, 
       MAX(memory_percent) as max_memory,
       MAX(cpu_percent) as max_cpu,
       MIN(disk_free_gb) as min_disk_free
FROM service_resource_metrics 
WHERE recorded_at > NOW() - INTERVAL '24 hours'
GROUP BY service_name
HAVING MAX(memory_percent) > 80 OR MAX(cpu_percent) > 80 OR MIN(disk_free_gb) < 2;
```

## 🎯 **Deployment Checklist**

- [ ] Add `comprehensive_resource_monitor.py` to all service containers
- [ ] Install `psutil` dependency in all Dockerfiles  
- [ ] Integrate monitoring startup in all service entry points
- [ ] Configure `SLACK_WEBHOOK_URL` in Render environment variables
- [ ] Test alerts by artificially triggering thresholds
- [ ] Verify database metrics storage is working

## 🚨 **Alert Frequency**

- **Critical alerts**: Immediate (no cooldown)
- **Warning alerts**: Maximum 1 per 6 hours per service per metric type
- **Upgrade recommendations**: Included with every alert
- **Database alerts**: Once per day maximum

## ✅ **Verification Commands**

```bash
# Check if monitoring is active (look for resource monitoring logs)
curl https://chroma-load-balancer.onrender.com/status

# Check database for recent metrics
psql $DATABASE_URL -c "SELECT COUNT(*) FROM service_resource_metrics WHERE recorded_at > NOW() - INTERVAL '1 hour';"

# Test alert (if you have SSH access to a service)
python -c "from comprehensive_resource_monitor import start_resource_monitoring; m=start_resource_monitoring('test'); import time; time.sleep(60)"
```

## 🎉 **Result**

After integration, you'll have:

- **🔍 Complete visibility** into resource usage across all 6 services
- **📱 Proactive alerts** before services hit limits  
- **💰 Smart upgrade recommendations** with cost estimates
- **📊 Historical data** for capacity planning
- **🚨 Early warning system** for disk space issues

**No more surprise service failures due to resource exhaustion!** 🚀 