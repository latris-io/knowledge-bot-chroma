# ChromaDB Load Balancer - Environment Variables Reference

This document provides a comprehensive reference for all environment variables used across the ChromaDB Load Balancer system. Variables are organized by service and include descriptions, valid values, defaults, and system impact.

## 📋 **Table of Contents**

- [chroma-primary Service](#chroma-primary-service)
- [chroma-replica Service](#chroma-replica-service)  
- [chroma-load-balancer Service](#chroma-load-balancer-service)
- [chroma-monitor Service](#chroma-monitor-service)
- [Cleanup & Maintenance Services](#cleanup--maintenance-services)
- [Development & Testing Variables](#development--testing-variables)
- [External Integration Variables](#external-integration-variables)

---

## 🔸 **chroma-primary Service**

ChromaDB primary instance configuration variables.

### **Core ChromaDB Configuration**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `CHROMA_SERVER_HOST` | `0.0.0.0` | IP address or hostname | Binds ChromaDB server to specific network interface | Controls which network interfaces can access the service |
| `CHROMA_SERVER_HTTP_PORT` | `8000` | `1024-65535` | Port number for ChromaDB HTTP API | Must match Dockerfile EXPOSE and Render port configuration |
| `CHROMA_PERSIST_DIRECTORY` | `/chroma/chroma` | Absolute path | Directory for persistent storage of ChromaDB data | **CRITICAL**: Data loss if path changes without migration |

### **High Availability Configuration**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `INSTANCE_ROLE` | `primary` | `primary`, `replica` | Identifies instance role in HA setup | Used by load balancer for routing decisions and health checks |
| `INSTANCE_PRIORITY` | `100` | `1-255` | Priority for load balancing (higher = preferred) | Determines preferred instance for write operations |

### **Resource Monitoring**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `MEMORY_LIMIT_MB` | `1024` | `512-8192` | Memory limit for container resource monitoring | Triggers Slack alerts when usage exceeds thresholds |
| `RESOURCE_CHECK_INTERVAL` | `60` | `10-300` | Interval in seconds for resource monitoring checks | Lower values = more responsive alerts, higher CPU usage |

### **Database & Integration**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `DATABASE_URL` | PostgreSQL connection string | Valid PostgreSQL URL | Connection to shared PostgreSQL database for metadata | **CRITICAL**: All services must use same database for consistency |
| `SLACK_WEBHOOK_URL` | None (optional) | Valid webhook URL | Slack webhook for resource monitoring alerts | Disabled if not set - no resource alerts sent |

---

## 🔸 **chroma-replica Service**

ChromaDB replica instance configuration variables. **Identical to primary except for role/priority.**

### **Core Configuration Differences**

| Variable | Value | Description | System Impact |
|----------|-------|-------------|---------------|
| `INSTANCE_ROLE` | `replica` | Identifies as replica instance | Load balancer routes reads preferentially to replica |
| `INSTANCE_PRIORITY` | `80` | Lower priority than primary | Ensures primary is preferred for writes |

> **Note**: All other variables identical to chroma-primary service. See [chroma-primary section](#chroma-primary-service) for complete reference.

---

## 🔸 **chroma-load-balancer Service**

The central load balancing and WAL system with the most extensive configuration.

### **Instance Discovery & Health**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `PRIMARY_URL` | `https://chroma-primary.onrender.com` | Valid HTTP URL | URL of primary ChromaDB instance | **CRITICAL**: Must match actual primary service URL |
| `REPLICA_URL` | `https://chroma-replica.onrender.com` | Valid HTTP URL | URL of replica ChromaDB instance | **CRITICAL**: Must match actual replica service URL |
| `CHECK_INTERVAL` | `30` | `1-300` | Health check interval in seconds | Lower = faster failure detection, higher CPU usage |
| `FAILURE_THRESHOLD` | `3` | `1-10` | Failed checks before marking instance unhealthy | Higher = more tolerant of transient failures |

### **Load Balancing Strategy**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `LOAD_BALANCE_STRATEGY` | `optimized_read_replica` | `round_robin`, `optimized_read_replica`, `primary_only` | Algorithm for distributing requests | Affects performance and instance utilization |
| `READ_REPLICA_RATIO` | `0.8` | `0.0-1.0` | Fraction of reads routed to replica | `0.8` = 80% reads to replica, 20% to primary |

### **Performance & Concurrency**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `MAX_CONCURRENT_REQUESTS` | `8` | `1-50` | Maximum simultaneous requests | Higher = better throughput, more memory usage |
| `CONNECTION_POOL_SIZE` | `10` | `5-100` | HTTP connection pool size | Higher = better performance, more memory |
| `REQUEST_QUEUE_SIZE` | `50` | `10-500` | Queue size for pending requests | Prevents memory overflow during traffic spikes |
| `REQUEST_TIMEOUT` | `15` | `5-120` | Request timeout in seconds | Balance between patience and responsiveness |
| `CIRCUIT_BREAKER_TIMEOUT` | `30` | `10-300` | Circuit breaker timeout in seconds | Time to wait before retrying failed instance |

### **Write-Ahead Log (WAL) System**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `WAL_ENABLED` | `"true"` | `"true"`, `"false"` | Enable/disable WAL system | **CRITICAL**: `false` disables data consistency guarantees |
| `WAL_SYNC_INTERVAL` | `10` | `5-300` | WAL sync interval in seconds | Lower = faster consistency, higher CPU usage |
| `WAL_BATCH_SIZE` | `100` | `10-1000` | Number of operations per sync batch | Higher = better efficiency, potential memory pressure |
| `WAL_HIGH_VOLUME_BATCH_SIZE` | `200` | `50-2000` | Batch size during high load | Used when system detects high operation volume |
| `WAL_RETRY_ATTEMPTS` | `3` | `1-10` | Max retries for failed sync operations | Higher = more resilient, potential for delays |
| `WAL_RETRY_DELAY` | `5` | `1-60` | Delay between retries in seconds | Exponential backoff: 5s, 10s, 20s, etc. |
| `WAL_DELETION_CONVERSION` | `"true"` | `"true"`, `"false"` | Convert DELETE operations for sync | Improves sync reliability across instances |
| `WAL_PERSISTENCE_SCHEMA` | `"true"` | `"true"`, `"false"` | Enable persistent WAL schema | **CRITICAL**: Required for data consistency |

### **Resource Management**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `MAX_MEMORY_MB` | `400` | `256-4096` | Memory limit for load balancer in MB | **USE CASE 5**: Affects batch sizes and worker counts |
| `MAX_WORKERS` | `3` | `1-24` | Maximum worker threads for parallel processing | **USE CASE 5**: Scales with CPU cores for performance |
| `DEFAULT_BATCH_SIZE` | `50` | `10-500` | Default WAL batch size | Starting batch size before adaptive scaling |
| `MAX_BATCH_SIZE` | `200` | `50-2000` | Maximum WAL batch size | Upper limit for adaptive batch sizing |
| `WAL_MEMORY_THRESHOLD` | `80` | `50-95` | Memory usage % threshold for high-volume mode | Triggers adaptive batch sizing at this memory usage |
| `WAL_CPU_THRESHOLD` | `80` | `50-95` | CPU usage % threshold for high-volume mode | Triggers performance optimizations |

### **USE CASE 5: Scalability Features** 🚀

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `ENABLE_CONNECTION_POOLING` | `"false"` | `"true"`, `"false"` | Enable database connection pooling | **50-80% reduction** in connection overhead |
| `ENABLE_GRANULAR_LOCKING` | `"false"` | `"true"`, `"false"` | Enable operation-specific locking | **60-80% reduction** in lock contention |

> **⚠️ PRODUCTION SAFETY**: Both features default to `"false"` for zero deployment risk. Enable after testing.

**Connection Pooling Impact**:
- Pool size automatically scales: `min(2, MAX_WORKERS)` to `max(10, MAX_WORKERS * 3)`
- Eliminates database connection overhead for high-throughput scenarios
- Graceful fallback to direct connections if pooling fails

**Granular Locking Impact**:
- Replaces single global lock with 4 operation-specific locks: `wal_write`, `collection_mapping`, `metrics`, `status`
- Enables higher concurrency during parallel operations
- Reduces waiting time for non-conflicting operations

### **Monitoring & Alerting**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `SLACK_WEBHOOK_URL` | None (optional) | Valid webhook URL | Slack webhook for system alerts | All alerts disabled if not set |
| `SLACK_ALERTS_ENABLED` | `"true"` | `"true"`, `"false"` | Enable general Slack notifications | Controls all non-critical alerts |
| `SLACK_UPGRADE_ALERTS` | `"true"` | `"true"`, `"false"` | Enable performance upgrade recommendations | Sends scaling suggestions based on metrics |

### **Database & Core**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `DATABASE_URL` | PostgreSQL connection string | Valid PostgreSQL URL | Shared database for WAL, mappings, metrics | **CRITICAL**: Must be same database across all services |
| `PORT` | `8000` | `1024-65535` | Port for load balancer HTTP API | Must match Render port configuration |

---

## 🔸 **chroma-monitor Service**

Background monitoring service for health checks and alerting.

### **Service URLs**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `PRIMARY_URL` | `https://chroma-primary.onrender.com` | Valid HTTP URL | Primary instance URL for monitoring | Must match actual service URL |
| `REPLICA_URL` | `https://chroma-replica.onrender.com` | Valid HTTP URL | Replica instance URL for monitoring | Must match actual service URL |
| `LOAD_BALANCER_URL` | `https://chroma-load-balancer.onrender.com` | Valid HTTP URL | Load balancer URL for monitoring | Must match actual service URL |

### **Monitoring Configuration**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `CHECK_INTERVAL` | `30` | `10-300` | Health check interval in seconds | Lower = more responsive monitoring, higher resource usage |
| `FAILURE_THRESHOLD` | `3` | `1-10` | Failed checks before alerting | Higher = fewer false alarms, slower detection |

### **Resource Alerting Thresholds**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `MEMORY_WARNING_THRESHOLD` | `80` | `50-95` | Memory usage % for warning alerts | First level alert threshold |
| `MEMORY_CRITICAL_THRESHOLD` | `95` | `70-99` | Memory usage % for critical alerts | Urgent intervention required |
| `CPU_WARNING_THRESHOLD` | `80` | `50-95` | CPU usage % for warning alerts | Performance degradation warning |
| `CPU_CRITICAL_THRESHOLD` | `95` | `70-99` | CPU usage % for critical alerts | System overload alert |

### **Integration**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `SLACK_WEBHOOK_URL` | None (optional) | Valid webhook URL | Slack webhook for monitoring alerts | No alerts sent if not configured |
| `DATABASE_URL` | PostgreSQL connection string | Valid PostgreSQL URL | Database for storing monitoring metrics | Required for metric persistence |

---

## 🔸 **Cleanup & Maintenance Services**

Environment variables for automated cleanup and maintenance tasks.

### **Data Retention Policies**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `HEALTH_METRICS_RETENTION_DAYS` | `7` | `1-365` | Days to retain health check metrics | Affects database size and historical analysis capability |
| `PERFORMANCE_METRICS_RETENTION_DAYS` | `30` | `7-365` | Days to retain performance metrics | Longer retention = better trend analysis |
| `SYNC_HISTORY_RETENTION_DAYS` | `90` | `30-365` | Days to retain WAL sync history | Critical for troubleshooting sync issues |
| `FAILOVER_EVENTS_RETENTION_DAYS` | `180` | `30-730` | Days to retain failover event logs | Important for reliability analysis |
| `SYNC_TASKS_RETENTION_DAYS` | `30` | `7-90` | Days to retain sync task details | Operational troubleshooting data |
| `UPGRADE_RECOMMENDATIONS_RETENTION_DAYS` | `365` | `90-730` | Days to retain upgrade recommendations | Capacity planning historical data |
| `SYNC_WORKERS_RETENTION_DAYS` | `7` | `1-30` | Days to retain worker process metrics | Short-term operational data |

### **Log Management**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `LOG_RETENTION_DAYS` | `14` | `1-90` | Days to retain application logs | Affects disk usage and debugging capability |
| `MAX_LOG_SIZE_MB` | `100` | `10-1000` | Maximum log file size in MB | Prevents excessive disk usage |

### **Database**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `DATABASE_URL` | PostgreSQL connection string | Valid PostgreSQL URL | Database connection for cleanup operations | **CRITICAL**: Must match production database |

---

## 🔸 **Development & Testing Variables**

Variables used during development, testing, and debugging.

### **Health Proxy (Development)**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `PROXY_PORT` | `3000` | `1024-65535` | Port for development health proxy | Development tool only - not used in production |

### **Render Integration (Infrastructure Management)**

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `RENDER_API_KEY` | None (required for auto-failover) | Valid Render API key | API key for automated Render service management | Enables automatic infrastructure failover |

### **Testing Database Override**

For testing environments, you can override database connections:

| Variable | Default | Valid Values | Description | System Impact |
|----------|---------|--------------|-------------|---------------|
| `DATABASE_URL` | Production connection | Test database URL | Override for testing environments | **⚠️ NEVER use production database for testing** |

---

## 🔸 **External Integration Variables**

Variables for integrating with external services and platforms.

### **Slack Integration**

| Variable | Used By | Required | Description | System Impact |
|----------|---------|----------|-------------|---------------|
| `SLACK_WEBHOOK_URL` | All services | Optional | Webhook URL for Slack notifications | **Global**: Affects all monitoring and alerting across services |

**Impact by Service**:
- **chroma-primary/replica**: Resource usage alerts (memory, CPU thresholds)
- **chroma-load-balancer**: System health, performance, and upgrade recommendations  
- **chroma-monitor**: Service health and failure notifications
- **cleanup services**: Cleanup operation results and warnings

### **PostgreSQL Database**

| Variable | Used By | Required | Description | System Impact |
|----------|---------|----------|-------------|---------------|
| `DATABASE_URL` | All services | **Critical** | PostgreSQL connection for shared state | **⚠️ CRITICAL**: Single point of configuration - all services must use identical URL |

**Database Tables Used**:
- **WAL operations**: `wal_operations`, `sync_state`
- **Collection mappings**: `collection_id_mapping`
- **Health metrics**: `health_metrics`, `performance_metrics`
- **Monitoring data**: `failover_events`, `upgrade_recommendations`
- **Transaction safety**: `emergency_transaction_log`

---

## 🚀 **Scaling & Performance Variables**

### **Resource-Only Scaling Method**

**USE CASE 5 Scalability Features** enable scaling through Render plan upgrades without code changes:

```yaml
Current Production → 10x Growth:
  Render Plan: Upgrade to 1GB RAM + 2 CPU cores
  Environment Variables: 
    - MAX_MEMORY_MB: "800"
    - MAX_WORKERS: "6"
    - ENABLE_CONNECTION_POOLING: "true"
    - ENABLE_GRANULAR_LOCKING: "true"
  
10x Growth → 100x Growth:  
  Render Plan: Upgrade to 2GB RAM + 4 CPU cores
  Environment Variables:
    - MAX_MEMORY_MB: "1600" 
    - MAX_WORKERS: "12"
    
100x Growth → 1000x Growth:
  Render Plan: Upgrade to 4GB RAM + 8 CPU cores  
  Environment Variables:
    - MAX_MEMORY_MB: "3200"
    - MAX_WORKERS: "24"
```

### **Performance Monitoring Endpoints**

Check current scalability status:
```bash
# View current configuration and feature status
curl https://chroma-load-balancer.onrender.com/admin/scalability_status

# Monitor performance impact of enabled features  
curl https://chroma-load-balancer.onrender.com/status | jq '.performance_impact'
```

---

## ⚠️ **Critical Configuration Guidelines**

### **🔴 NEVER Change Without Planning**

| Variable | Risk | Impact |
|----------|------|--------|
| `DATABASE_URL` | **CRITICAL** | Wrong database = data loss, sync failures, system breakdown |
| `CHROMA_PERSIST_DIRECTORY` | **HIGH** | Path change without migration = complete data loss |
| `PRIMARY_URL` / `REPLICA_URL` | **HIGH** | Wrong URLs = complete service failure |
| `WAL_ENABLED` | **HIGH** | Disabling WAL = no data consistency guarantees |

### **🟡 Change with Caution**

| Variable | Risk | Recommendation |
|----------|------|----------------|
| `INSTANCE_ROLE` | **MEDIUM** | Only change during maintenance windows |
| `WAL_BATCH_SIZE` | **MEDIUM** | Monitor performance after changes |
| `MAX_MEMORY_MB` / `MAX_WORKERS` | **MEDIUM** | Align with actual Render plan resources |
| `ENABLE_CONNECTION_POOLING` / `ENABLE_GRANULAR_LOCKING` | **LOW** | Test with `"false"` rollback plan |

### **🟢 Safe to Adjust**

| Variable | Impact | Notes |
|----------|--------|-------|
| `CHECK_INTERVAL` | Low | Affects monitoring frequency only |
| `SLACK_WEBHOOK_URL` | None | Only affects notifications |
| `REQUEST_TIMEOUT` | Low | Adjust based on network conditions |

---

## 📊 **Environment Variable Summary by Service**

| Service | Total Variables | Critical Variables | Performance Variables | Optional Variables |
|---------|-----------------|--------------------|-----------------------|-------------------|
| **chroma-primary** | 9 | 3 | 2 | 4 |
| **chroma-replica** | 9 | 3 | 2 | 4 |  
| **chroma-load-balancer** | 32 | 5 | 15 | 12 |
| **chroma-monitor** | 11 | 1 | 4 | 6 |
| **cleanup services** | 9 | 1 | 0 | 8 |

**Total Environment Variables**: **61 variables** across the entire system

---

## 🎯 **Quick Reference: Most Important Variables**

### **Must Configure for Production**
1. `DATABASE_URL` - All services
2. `PRIMARY_URL` - Load balancer & monitor  
3. `REPLICA_URL` - Load balancer & monitor
4. `SLACK_WEBHOOK_URL` - All services (if alerts desired)

### **Performance Tuning**
1. `MAX_WORKERS` - Load balancer scaling
2. `MAX_MEMORY_MB` - Load balancer memory management
3. `WAL_BATCH_SIZE` - Sync performance
4. `READ_REPLICA_RATIO` - Load distribution

### **High Availability**
1. `CHECK_INTERVAL` - Failure detection speed
2. `FAILURE_THRESHOLD` - Failure tolerance  
3. `WAL_RETRY_ATTEMPTS` - Sync resilience
4. `CIRCUIT_BREAKER_TIMEOUT` - Recovery time

### **USE CASE 5 Features**
1. `ENABLE_CONNECTION_POOLING` - Database performance
2. `ENABLE_GRANULAR_LOCKING` - Concurrency optimization

---

**📝 Document Version**: 1.0  
**📅 Last Updated**: Created for comprehensive environment variable reference  
**🔄 Next Review**: After USE CASE 5 production deployment 