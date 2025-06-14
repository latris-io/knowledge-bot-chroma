# Database and Log Cleanup Guide

## Overview

This guide covers the automated data retention and cleanup systems designed to prevent unnecessary disk space usage while maintaining system performance and data integrity.

## 🗄️ Database Retention Policies

### Configurable Retention Periods

All retention policies can be customized via environment variables:

| Table | Default Retention | Environment Variable | Purpose |
|-------|------------------|---------------------|---------|
| `health_metrics` | 7 days | `HEALTH_METRICS_RETENTION_DAYS` | High-frequency monitoring data |
| `performance_metrics` | 30 days | `PERFORMANCE_METRICS_RETENTION_DAYS` | Resource usage tracking |
| `sync_history` | 90 days | `SYNC_HISTORY_RETENTION_DAYS` | Sync operation audit trail |
| `failover_events` | 180 days | `FAILOVER_EVENTS_RETENTION_DAYS` | Critical system events |
| `sync_tasks` | 30 days | `SYNC_TASKS_RETENTION_DAYS` | Distributed sync coordination |
| `upgrade_recommendations` | 365 days | `UPGRADE_RECOMMENDATIONS_RETENTION_DAYS` | Strategic planning data |
| `sync_workers` | 7 days | `SYNC_WORKERS_RETENTION_DAYS` | Worker heartbeat tracking |

### Retention Policy Rationale

**Short Retention (7 days)**
- `health_metrics`: Generated every ~12 seconds, high volume
- `sync_workers`: Only recent heartbeats are relevant

**Medium Retention (30-90 days)**
- `performance_metrics`: Monthly trending analysis
- `sync_tasks`: Operational debugging window
- `sync_history`: Recent sync troubleshooting

**Long Retention (180-365 days)**
- `failover_events`: Critical for incident analysis
- `upgrade_recommendations`: Annual planning cycles

## 🧹 Cleanup Service Usage

### Manual Cleanup

```bash
# Show current database size and record counts
python cleanup_service.py --report

# Run cleanup once (delete old records)
python cleanup_service.py --run
```

### Environment Configuration

```bash
# Customize retention periods
export HEALTH_METRICS_RETENTION_DAYS=14
export PERFORMANCE_METRICS_RETENTION_DAYS=60
export SYNC_HISTORY_RETENTION_DAYS=30

# Run with custom settings
python cleanup_service.py --run
```

### Example Output

```
📊 Database Size Report
  health_metrics: 3,328 records, 448 kB, 7 day retention
  performance_metrics: 0 records, 8192 bytes, 30 day retention
  sync_history: 0 records, 32 kB, 90 day retention
  ...
```

## 💾 Disk Space Optimization

### Database Optimization

The cleanup service automatically runs `VACUUM ANALYZE` after deletions to:
- Reclaim disk space from deleted records
- Update query planner statistics
- Optimize database performance

### Expected Data Growth

With default retention policies:

**Health Metrics** (highest volume)
- Frequency: Every ~12 seconds for 2 instances
- Daily records: ~14,400 
- 7-day total: ~100,000 records
- Estimated size: ~50-100 MB

**Total Database Size**
- Expected steady state: 100-200 MB
- With cleanup: Space usage remains constant
- Without cleanup: Linear growth (~15 MB/day)

## 🔧 Integration with Production

### Adding to Deployment

Add cleanup service to your deployment configuration:

**Render (render.yaml)**
```yaml
services:
  - type: worker
    name: chroma-cleanup
    env: docker
    dockerfilePath: ./Dockerfile.cleanup
    region: oregon
    plan: starter
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: chroma-metadata
          property: connectionString
      - key: HEALTH_METRICS_RETENTION_DAYS
        value: "7"
      - key: PERFORMANCE_METRICS_RETENTION_DAYS
        value: "30"
```

**Dockerfile.cleanup**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt cleanup_service.py ./
RUN pip install -r requirements.txt
CMD ["python", "cleanup_service.py", "--run"]
```

### Scheduled Cleanup

For production environments, run cleanup on a schedule:

```bash
# Daily cleanup at 2 AM
0 2 * * * cd /app && python cleanup_service.py --run >> /var/log/cleanup.log 2>&1

# Weekly cleanup with reporting
0 3 * * 0 cd /app && python cleanup_service.py --report >> /var/log/cleanup-report.log
```

## 📊 Monitoring and Alerting

### Key Metrics to Monitor

1. **Database Size Growth**
   ```bash
   python cleanup_service.py --report | grep "records"
   ```

2. **Cleanup Effectiveness**
   ```bash
   # Monitor deleted record counts
   python cleanup_service.py --run | grep "deleted"
   ```

3. **Retention Policy Violations**
   ```sql
   -- Check for excessive health metrics
   SELECT COUNT(*) FROM health_metrics WHERE checked_at < NOW() - INTERVAL '7 days';
   ```

### Slack Notifications

The monitoring system can alert on:
- Database size exceeding thresholds
- Cleanup service failures
- Unexpected data retention issues

## 🛡️ Data Protection

### Safety Measures

1. **Retention Windows**: Only data older than retention period is deleted
2. **Error Handling**: Failed deletions don't affect other tables
3. **Transaction Safety**: All deletions are committed atomically
4. **Validation**: Tests ensure recent data is never deleted

### Recovery Considerations

- **Recent Data**: Always preserved within retention windows
- **Backup Strategy**: Consider external backups for critical events
- **Gradual Cleanup**: Large deletions are handled efficiently

## 🔍 Troubleshooting

### Common Issues

**Large Database Size**
```bash
# Check what's consuming space
python cleanup_service.py --report

# Run cleanup if needed
python cleanup_service.py --run
```

**Cleanup Not Running**
```bash
# Check environment variables
env | grep RETENTION_DAYS

# Test database connection
python cleanup_service.py --report
```

**Performance Issues**
```sql
-- Check for tables needing vacuum
SELECT schemaname, tablename, n_dead_tup, n_live_tup 
FROM pg_stat_user_tables 
WHERE n_dead_tup > 1000;
```

### Logs and Debugging

Cleanup service provides detailed logging:
```
2025-06-14 17:52:55,056 - INFO - 🧹 Cleanup Service initialized
2025-06-14 17:52:55,056 - INFO - 🚀 Starting database cleanup cycle
2025-06-14 17:52:55,957 - INFO - ✅ health_metrics: No old records to clean
2025-06-14 17:52:02,445 - INFO - ✅ Cleanup complete: 0 total records deleted
```

## 📈 Cost Optimization

### Database Size Impact

With proper cleanup:
- **Render PostgreSQL**: Stays within free tier limits
- **Performance**: Consistent query response times
- **Maintenance**: Reduced vacuum/maintenance overhead

### Scaling Considerations

As your system grows:
1. **Adjust retention periods** based on actual needs
2. **Monitor query performance** with larger datasets
3. **Consider partitioning** for very high-volume tables
4. **Implement archival** for historical data analysis

## ✅ Best Practices

1. **Test retention policies** in staging before production
2. **Monitor database size** regularly
3. **Adjust retention periods** based on actual usage
4. **Run cleanup regularly** (daily recommended)
5. **Keep monitoring logs** for trend analysis
6. **Document any custom retention requirements**

## 🧪 Testing

The cleanup system includes comprehensive tests:

```bash
# Test all cleanup functionality
python test_cleanup_systems.py

# Include in full test suite
python run_all_tests.py --url https://chroma-load-balancer.onrender.com
```

This ensures:
- Retention policies are correctly configured
- Data protection measures work
- Cleanup operations function properly
- Database optimization is effective 