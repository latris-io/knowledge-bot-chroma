# Write-Ahead Log (WAL) Architecture Guide

## 🎯 Overview

The **Write-Ahead Log (WAL)** provides **both data safety AND high availability** for the ChromaDB distributed system. When the primary database is down, writes are queued and automatically replayed when the primary recovers, ensuring zero data loss while maintaining system availability.

## 🏗️ Architecture Components

### Core Components

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Client Apps   │────│  Load Balancer   │────│   Primary DB    │
└─────────────────┘    │   + WAL System   │    └─────────────────┘
                       └──────────────────┘             │
                                │                       │ Sync
                                └───────────────────────┼─────────────┐
                                                        │             │
                                                        ▼             ▼
                                              ┌─────────────────┐    ┌──────────────┐
                                              │   Replica DB    │    │  WAL Buffer  │
                                              └─────────────────┘    │  (In-Memory) │
                                                                     └──────────────┘
```

### Write-Ahead Log Flow

1. **Normal Operation** (Primary Healthy):
   ```
   Write Request → Primary DB ✅ → Sync Service → Replica DB ✅
   ```

2. **Primary Down** (WAL Active):
   ```
   Write Request → WAL Buffer → Replica DB ✅ → Queue for Replay
   ```

3. **Primary Recovery** (Replay Phase):
   ```
   WAL Replay Monitor → Primary DB Recovery → Replay Queued Writes → Resume Normal Sync
   ```

## 📊 WAL Data Structures

### PendingWrite Class

```python
@dataclass
class PendingWrite:
    id: str                    # Unique write identifier
    timestamp: datetime        # When write was received
    method: str               # HTTP method (POST, PUT, DELETE)
    path: str                 # API endpoint path
    data: bytes              # Request body
    headers: Dict[str, str]  # HTTP headers
    collection_id: str       # Collection being modified
    retries: int             # Retry attempt count
    max_retries: int = 3     # Maximum retry attempts
```

### WAL Status Structure

```json
{
  "write_ahead_log": {
    "pending_writes": 0,           // Number of writes waiting replay
    "is_replaying": false,         // Currently replaying flag
    "oldest_pending": null,        // Timestamp of oldest pending write
    "total_replayed": 15,          // Total successful replays
    "failed_replays": 2            // Total failed replays
  }
}
```

## 🔄 Operational Flows

### Write Operation Logic

```python
def select_instance(method, path):
    if is_write_operation(method, path):
        primary = get_primary_instance()
        if primary and primary.is_healthy:
            return primary  # Normal operation
        else:
            replica = get_replica_instance()
            if replica and replica.is_healthy:
                # WAL will be triggered
                return replica
            else:
                raise Exception("No instances available")
```

### WAL Activation

```python
def make_request(instance, method, path, **kwargs):
    is_replica_write = (is_write_operation(method, path) and 
                       instance.name == "replica")
    
    if is_replica_write:
        # Add to Write-Ahead Log before executing
        write_id = add_pending_write(method, path, 
                                   kwargs.get('data', b''),
                                   kwargs.get('headers', {}))
        logger.info(f"📋 Write {write_id[:8]} queued for replay")
    
    # Execute the write on replica
    return requests.request(method, f"{instance.url}{path}", **kwargs)
```

### Replay Process

```python
def replay_pending_writes():
    with pending_writes_lock:
        pending_list = list(pending_writes.values())
    
    # Sort by timestamp to maintain order
    pending_list.sort(key=lambda w: w.timestamp)
    
    primary = get_primary_instance()
    if not primary:
        return False
    
    for write in pending_list:
        try:
            # Replay write to primary
            response = make_direct_request(primary, write.method, 
                                         write.path, data=write.data, 
                                         headers=write.headers)
            
            # Remove from pending queue
            del pending_writes[write.id]
            stats["replayed_writes"] += 1
            
        except Exception as e:
            write.retries += 1
            if write.retries >= write.max_retries:
                del pending_writes[write.id]
                stats["failed_replays"] += 1
```

## ⚙️ Configuration

### Environment Variables

```bash
# WAL Configuration
CONSISTENCY_WINDOW=30          # Seconds to force primary reads after writes
READ_REPLICA_RATIO=0.8         # Percentage of reads to route to replica
REQUEST_TIMEOUT=15             # Request timeout in seconds
CHECK_INTERVAL=30              # Health check interval in seconds
```

### Default Settings

```python
class StableLoadBalancer:
    def __init__(self):
        self.consistency_window = 30        # 30 seconds
        self.request_timeout = 15           # 15 seconds
        self.read_replica_ratio = 0.8       # 80% replica reads
        self.check_interval = 30            # 30 second health checks
```

## 📈 Monitoring & Observability

### WAL Metrics

| Metric | Description | Type |
|--------|-------------|------|
| `pending_writes` | Writes waiting for replay | Counter |
| `total_replayed` | Successfully replayed writes | Counter |
| `failed_replays` | Failed replay attempts | Counter |
| `is_replaying` | Currently replaying flag | Boolean |
| `oldest_pending` | Timestamp of oldest queued write | Timestamp |

### Health Monitoring

```python
# Instance health structure
{
  "name": "primary|replica",
  "healthy": true|false,
  "success_rate": "95.2%",
  "total_requests": 1543,
  "last_health_check": "2024-06-15T01:33:45.543827"
}
```

### Status Endpoints

- **`/status`** - Complete WAL and system status
- **`/health`** - Simple health check
- **Instance URLs** - Direct instance health checks

## 🚀 Deployment

### Docker Configuration

```dockerfile
# Dockerfile.loadbalancer
FROM python:3.11-slim
COPY stable_load_balancer.py ./
COPY requirements.loadbalancer.txt ./
RUN pip install -r requirements.loadbalancer.txt
EXPOSE 8000
CMD ["python", "stable_load_balancer.py"]
```

### Render Deployment

```yaml
# render.yaml - Load Balancer Service
- type: web
  name: chroma-load-balancer
  runtime: python3
  buildCommand: pip install -r requirements.loadbalancer.txt
  startCommand: python stable_load_balancer.py
  envVars:
    - key: PRIMARY_URL
      value: https://chroma-primary.onrender.com
    - key: REPLICA_URL
      value: https://chroma-replica.onrender.com
```

## 🔧 Operations

### Normal Operation

1. **Both instances healthy**: Writes go to primary, reads distributed
2. **WAL inactive**: No pending writes, normal sync operation
3. **Monitoring**: Track success rates and response times

### Primary Failure Scenario

1. **Detection**: Health monitor marks primary as unhealthy
2. **WAL Activation**: Writes begin queuing in memory
3. **Replica Serving**: Reads continue from replica
4. **Monitoring**: Track pending write count and queue age

### Primary Recovery

1. **Health Recovery**: Primary passes health checks
2. **Replay Trigger**: WAL monitor detects recovery
3. **Ordered Replay**: Writes replayed in chronological order
4. **Resume Normal**: Return to standard operation mode

### Troubleshooting Commands

```bash
# Check WAL status
curl https://chroma-load-balancer.onrender.com/status

# Monitor pending writes
watch -n 5 'curl -s https://chroma-load-balancer.onrender.com/status | jq .write_ahead_log'

# Check instance health
curl https://chroma-primary.onrender.com/api/v2/version
curl https://chroma-replica.onrender.com/api/v2/version
```

## 🎯 Benefits & Trade-offs

### ✅ Benefits

| Benefit | Description |
|---------|-------------|
| **High Availability** | Accepts writes during primary outages |
| **Data Safety** | Zero data loss with ordered replay |
| **Automatic Recovery** | Self-healing when primary returns |
| **Real-time Monitoring** | Full visibility into WAL operations |
| **Graceful Degradation** | System continues operating during failures |

### ⚠️ Trade-offs

| Trade-off | Impact | Mitigation |
|-----------|---------|------------|
| **Memory Usage** | WAL stored in memory | Configurable limits, monitoring |
| **Replay Latency** | Delay when primary recovers | Parallel replay, retry logic |
| **Complexity** | More moving parts | Comprehensive monitoring |
| **Temporary Inconsistency** | Replica ahead during outage | Consistency window handling |

## 🧪 Testing

### Test Categories

1. **Unit Tests**: Individual WAL components
2. **Integration Tests**: WAL with load balancer
3. **Failure Tests**: Primary/replica failure scenarios
4. **Performance Tests**: WAL under load
5. **Recovery Tests**: Replay functionality

### Test Commands

```bash
# Run comprehensive WAL tests
python test_wal_comprehensive.py

# Run specific test categories
python -m unittest TestWriteAheadLog.test_wal_status_endpoint
python -m unittest TestWriteAheadLog.test_write_queuing_during_primary_failure

# Integration with existing test suite
python run_all_tests.py --include-wal
```

## 📚 References

- [ENHANCED_SYNC_SERVICE.md](./ENHANCED_SYNC_SERVICE.md) - Sync service architecture
- [PRODUCTION_TESTING_GUIDE.md](./PRODUCTION_TESTING_GUIDE.md) - Testing procedures
- [SERVICE_MONITORING_INTEGRATION.md](./SERVICE_MONITORING_INTEGRATION.md) - Monitoring setup

## 🔮 Future Enhancements

### Planned Features

1. **Persistent WAL** - Disk-based write buffer for restart resilience
2. **WAL Compression** - Reduce memory usage for large write queues
3. **Multi-Region WAL** - Cross-region write buffering
4. **WAL Analytics** - Advanced metrics and alerting
5. **Auto-scaling WAL** - Dynamic resource allocation

### Performance Optimizations

1. **Batch Replay** - Replaying multiple writes in single requests
2. **Async Replay** - Non-blocking replay operations
3. **WAL Sharding** - Distribute WAL across multiple processes
4. **Smart Retry** - Exponential backoff with jitter

---

**Write-Ahead Log Architecture v2.0**  
*Ensuring both data safety and high availability for distributed ChromaDB* 