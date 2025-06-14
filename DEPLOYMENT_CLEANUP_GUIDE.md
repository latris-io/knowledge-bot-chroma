#!/usr/bin/env python3
"""
Enhanced Cleanup Service
Includes both PostgreSQL data cleanup and application log file cleanup
"""

import os
import glob
import time
from datetime import datetime, timedelta
from cleanup_service import DatabaseCleanupService

class EnhancedCleanupService(DatabaseCleanupService):
    """Extended cleanup service with log file management"""
    
    def __init__(self):
        super().__init__()
        
        # Log cleanup configuration
        self.log_retention_days = int(os.getenv("LOG_RETENTION_DAYS", "14"))
        self.max_log_size_mb = int(os.getenv("MAX_LOG_SIZE_MB", "100"))
        
    def cleanup_application_logs(self):
        """Clean up application log files"""
        log.info("📝 Starting application log cleanup")
        
        # Common log file patterns
        log_patterns = [
            "/var/log/*.log",
            "/tmp/*.log", 
            "/app/logs/*.log",
            "./logs/*.log"
        ]
        
        cutoff_date = datetime.now() - timedelta(days=self.log_retention_days)
        cutoff_timestamp = cutoff_date.timestamp()
        
        deleted_files = 0
        freed_space_mb = 0
        
        for pattern in log_patterns:
            try:
                for log_file in glob.glob(pattern):
                    try:
                        stat = os.stat(log_file)
                        
                        # Delete old files
                        if stat.st_mtime < cutoff_timestamp:
                            size_mb = stat.st_size / (1024 * 1024)
                            os.remove(log_file)
                            deleted_files += 1
                            freed_space_mb += size_mb
                            logger.info(f"🗑️ Deleted old log: {log_file} ({size_mb:.1f}MB)")
                        
                        # Truncate large files
                        elif stat.st_size > (self.max_log_size_mb * 1024 * 1024):
                            size_mb = stat.st_size / (1024 * 1024)
                            with open(log_file, 'w') as f:
                                f.write(f"# Log truncated by cleanup service at {datetime.now()}\n")
                            freed_space_mb += size_mb
                            logger.info(f"✂️ Truncated large log: {log_file} ({size_mb:.1f}MB)")
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to process {log_file}: {e}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Error with pattern {pattern}: {e}")
        
        logger.info(f"📝 Log cleanup complete: {deleted_files} files deleted, {freed_space_mb:.1f}MB freed")
        return {'deleted_files': deleted_files, 'freed_space_mb': freed_space_mb}
    
    def run_enhanced_cleanup(self):
        """Run complete cleanup cycle including logs"""
        logger.info("🚀 Starting enhanced cleanup cycle")
        
        # 1. Database cleanup
        db_results = self.run_cleanup()
        
        # 2. Application log cleanup
        log_results = self.cleanup_application_logs()
        
        # 3. Summary
        logger.info("📊 ENHANCED CLEANUP SUMMARY")
        logger.info(f"  Database records deleted: {db_results['total_deleted']:,}")
        logger.info(f"  Log files deleted: {log_results['deleted_files']}")
        logger.info(f"  Disk space freed: {log_results['freed_space_mb']:.1f}MB")
        
        return {
            'database': db_results,
            'logs': log_results
        }

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Cleanup Service")
    parser.add_argument("--run", action="store_true", help="Run complete cleanup")
    parser.add_argument("--db-only", action="store_true", help="Database cleanup only")
    parser.add_argument("--logs-only", action="store_true", help="Log cleanup only")
    parser.add_argument("--report", action="store_true", help="Show size report")
    
    args = parser.parse_args()
    
    service = EnhancedCleanupService()
    
    if args.report:
        service.get_size_report()
    elif args.db_only:
        service.run_cleanup()
    elif args.logs_only:
        service.cleanup_application_logs()
    elif args.run:
        service.run_enhanced_cleanup()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

# Cleanup Service Deployment Guide

## 🎯 Overview

This guide explains **where to run the cleanup service** and **what logs are cleaned** across your distributed ChromaDB infrastructure.

## 📊 Cleanup Scope

### ✅ What IS Cleaned
| Component | Cleanup Type | Location | Method |
|-----------|--------------|----------|--------|
| **PostgreSQL Database** | Data retention | chroma-metadata database | `cleanup_service.py` |
| **Health Metrics** | 7-day retention | PostgreSQL tables | Automated deletion |
| **Performance Data** | 30-day retention | PostgreSQL tables | Automated deletion |
| **Sync History** | 90-day retention | PostgreSQL tables | Automated deletion |

### ❌ What is NOT Cleaned (by our script)
| Component | Why Not Cleaned | Render's Handling |
|-----------|-----------------|-------------------|
| **Render Service Logs** | Render manages automatically | 30-day retention by default |
| **Application stdout/stderr** | Captured by Render | Available in Render dashboard |
| **Container logs** | Managed by Render infrastructure | Auto-rotated and cleaned |

## 🚀 Deployment Options

### Option 1: Local Testing (Current)
```bash
# What we've been doing - for testing only
python cleanup_service.py --report
python cleanup_service.py --run
```

**Pros:**
- ✅ Easy testing and development
- ✅ Immediate feedback

**Cons:**
- ❌ Manual execution only
- ❌ Not automated for production
- ❌ Requires local environment setup

### Option 2: Deploy as Render Worker (Recommended)

Add to your `render.yaml`:

```yaml
services:
  # ... existing services ...
  
  # Cleanup worker service
  - type: worker
    name: chroma-cleanup
    env: docker
    dockerfilePath: ./Dockerfile.cleanup
    region: oregon
    plan: starter  # $7/month
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: chroma-metadata
          property: connectionString
      - key: HEALTH_METRICS_RETENTION_DAYS
        value: "7"
      - key: PERFORMANCE_METRICS_RETENTION_DAYS
        value: "30"
      - key: SYNC_HISTORY_RETENTION_DAYS
        value: "90"
      - key: FAILOVER_EVENTS_RETENTION_DAYS
        value: "180"
      - key: UPGRADE_RECOMMENDATIONS_RETENTION_DAYS
        value: "365"
```

**Pros:**
- ✅ Automated daily execution
- ✅ Integrated with your infrastructure
- ✅ Logs visible in Render dashboard
- ✅ Uses same database connection

**Cons:**
- ❌ Additional $7/month cost
- ❌ Worker services don't have free tier

### Option 3: Add to Existing Service

Add cleanup to an existing worker (like `chroma-sync`):

```python
# In your existing worker's startup script
import schedule
from cleanup_service import DatabaseCleanupService

def run_cleanup():
    service = DatabaseCleanupService()
    service.run_cleanup()

# Schedule daily cleanup at 2 AM
schedule.every().day.at("02:00").do(run_cleanup)

# In your main loop
while True:
    schedule.run_pending()
    # ... your existing worker logic ...
    time.sleep(60)
```

**Pros:**
- ✅ No additional service cost
- ✅ Automated execution
- ✅ Leverages existing infrastructure

**Cons:**
- ❌ Mixed responsibilities in one service
- ❌ Cleanup depends on worker service health

## 📝 Render Service Logs - What You Need to Know

### Render's Automatic Log Management

Render **automatically handles** service logs:

```
chroma-primary logs:     [Managed by Render]
├── stdout/stderr:       30-day retention
├── Application logs:    Auto-rotated
└── Container logs:      Platform managed

chroma-replica logs:     [Managed by Render]
├── stdout/stderr:       30-day retention  
├── Application logs:    Auto-rotated
└── Container logs:      Platform managed

chroma-load-balancer:    [Managed by Render]
├── Flask logs:          30-day retention
├── Request logs:        Auto-rotated
└── Health check logs:   Platform managed
```

### What Our Cleanup Service Does

Our cleanup service **only handles**:
```
PostgreSQL Database:     [Our cleanup_service.py]
├── health_metrics:      7-day retention
├── performance_metrics: 30-day retention
├── sync_history:        90-day retention
├── failover_events:     180-day retention
└── other tables:        Configurable retention
```

### Why This Division?

1. **Render Platform Logs**: Render optimizes these automatically
2. **Database Data**: Our application's responsibility
3. **Separation of Concerns**: Platform vs. application data

## 🔧 Recommended Production Setup

### 1. Deploy Cleanup Worker

```bash
# Add the cleanup service to render.yaml
git add render.yaml Dockerfile.cleanup cleanup_service.py
git commit -m "Add automated cleanup service"
git push origin main
```

### 2. Monitor Cleanup Execution

```bash
# Check cleanup logs in Render dashboard
# Service: chroma-cleanup
# Logs will show:
# "🧹 Cleanup Service initialized"
# "🗑️ health_metrics: Deleted X records"
# "✅ Cleanup complete: X total records deleted"
```

### 3. Verify Database Size

```bash
# Test locally to verify retention is working
python cleanup_service.py --report

# Expected output after a few days:
# health_metrics: ~50,000 records (7 days worth)
# Rather than growing indefinitely
```

## 📊 Expected Cleanup Results

### Before Cleanup (without retention)
```
📊 Database Growth Over Time
Week 1:  health_metrics: 100,000 records (50 MB)
Week 2:  health_metrics: 200,000 records (100 MB)  
Week 4:  health_metrics: 400,000 records (200 MB)
Week 12: health_metrics: 1,200,000 records (600 MB)
```

### After Cleanup (with retention)
```
📊 Steady State with Cleanup
Week 1:  health_metrics: 100,000 records (50 MB)
Week 2:  health_metrics: 100,000 records (50 MB) ← Cleanup removes old data
Week 4:  health_metrics: 100,000 records (50 MB) ← Stable
Week 12: health_metrics: 100,000 records (50 MB) ← Stable
```

## ❓ Frequently Asked Questions

### Q: Do I need to clean Render service logs manually?
**A:** No. Render automatically manages service logs with 30-day retention and auto-rotation.

### Q: Where should I run the cleanup service?
**A:** Deploy it as a Render worker service for automated production cleanup.

### Q: Will cleanup affect my application performance?
**A:** No. Cleanup runs during low-traffic hours and uses efficient database operations.

### Q: Can I customize retention periods?
**A:** Yes. Set environment variables like `HEALTH_METRICS_RETENTION_DAYS=14` for custom retention.

### Q: How do I know cleanup is working?
**A:** Check the cleanup service logs in Render dashboard and monitor database size with `--report`.

### Q: What if cleanup fails?
**A:** The service has error handling and will log failures. Each table is cleaned independently.

## 🎯 Next Steps

1. **Deploy cleanup worker** using the provided `render.yaml` configuration
2. **Monitor execution** through Render dashboard logs
3. **Verify effectiveness** with periodic size reports
4. **Adjust retention periods** based on your needs

This setup ensures your database stays optimized while letting Render handle platform-level log management automatically. 