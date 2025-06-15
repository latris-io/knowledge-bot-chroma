# Write-Ahead Log Operations Guide

## 🎯 Quick Reference

### Essential Commands

```bash
# Check WAL status
curl -s https://chroma-load-balancer.onrender.com/status | jq '.write_ahead_log'

# Monitor system health
curl -s https://chroma-load-balancer.onrender.com/health

# View pending writes count
curl -s https://chroma-load-balancer.onrender.com/status | jq '.write_ahead_log.pending_writes'

# Check instance health
curl -s https://chroma-primary.onrender.com/api/v2/version
curl -s https://chroma-replica.onrender.com/api/v2/version
```

### WAL Status Interpretation

| Metric | Normal | Warning | Critical |
|--------|--------|---------|----------|
| `pending_writes` | 0 | 1-10 | >10 |
| `is_replaying` | false | true (brief) | true (extended) |
| `failed_replays` | 0 | 1-2 | >2 |
| `oldest_pending` | null | <5 min | >5 min |

## 🚨 Incident Response Procedures

### Scenario 1: Primary Database Down

**Symptoms:**
- Primary health check fails
- Pending writes count increases
- WAL becomes active

**Response:**
1. **Verify Primary Status**
   ```bash
   curl -s https://chroma-primary.onrender.com/api/v2/version
   # Expected: 503 Service Unavailable or timeout
   ```

2. **Check WAL Activation**
   ```bash
   curl -s https://chroma-load-balancer.onrender.com/status | jq '.write_ahead_log'
   # Verify: pending_writes > 0 if writes are happening
   ```

3. **Monitor Write Operations**
   ```bash
   # Test write capability
   curl -X POST -H "Content-Type: application/json" \
     -d '{"name":"test_during_outage","metadata":{"test":true}}' \
     https://chroma-load-balancer.onrender.com/api/v2/collections
   ```

4. **Primary Recovery Actions**
   - Monitor primary service restart
   - Watch for replay initiation
   - Verify replay completion

**Expected WAL Behavior:**
- ✅ Writes accepted and queued
- ✅ Reads continue from replica
- ✅ Automatic replay when primary recovers

### Scenario 2: High Pending Writes Count

**Symptoms:**
- `pending_writes` > 10
- `oldest_pending` > 5 minutes
- Primary still down

**Response:**
1. **Assess Queue Size**
   ```bash
   PENDING=$(curl -s https://chroma-load-balancer.onrender.com/status | jq '.write_ahead_log.pending_writes')
   echo "Pending writes: $PENDING"
   ```

2. **Check Memory Usage**
   ```bash
   # Monitor load balancer resource usage
   curl -s https://chroma-load-balancer.onrender.com/status | jq '.stats'
   ```

3. **Escalation Criteria**
   - Pending writes > 50
   - Oldest pending > 15 minutes
   - Memory warnings

**Mitigation:**
- Throttle incoming writes if necessary
- Prioritize primary recovery
- Consider manual failover if available

### Scenario 3: Replay Failures

**Symptoms:**
- `failed_replays` > 0
- `is_replaying` stuck as true
- Primary recovered but writes not replaying

**Response:**
1. **Check Replay Status**
   ```bash
   curl -s https://chroma-load-balancer.onrender.com/status | jq '.write_ahead_log | {pending: .pending_writes, replaying: .is_replaying, failed: .failed_replays}'
   ```

2. **Verify Primary Accessibility**
   ```bash
   # Test primary direct access
   curl -X GET https://chroma-primary.onrender.com/api/v2/collections
   ```

3. **Manual Intervention**
   - Restart load balancer service if replay stuck
   - Check primary capacity and health
   - Review failed write patterns

## 📊 Monitoring & Alerting

### Key Metrics to Monitor

```json
{
  "wal_alerts": {
    "pending_writes_high": {
      "condition": "pending_writes > 20",
      "severity": "warning",
      "action": "investigate_primary_status"
    },
    "pending_writes_critical": {
      "condition": "pending_writes > 50",
      "severity": "critical", 
      "action": "immediate_intervention"
    },
    "old_pending_writes": {
      "condition": "oldest_pending > 300", // 5 minutes
      "severity": "warning",
      "action": "check_primary_recovery"
    },
    "replay_failures": {
      "condition": "failed_replays > 5",
      "severity": "critical",
      "action": "investigate_replay_issues"
    }
  }
}
```

### Monitoring Script

```bash
#!/bin/bash
# wal_monitor.sh - WAL monitoring script

LOAD_BALANCER_URL="https://chroma-load-balancer.onrender.com"

while true; do
    STATUS=$(curl -s "$LOAD_BALANCER_URL/status")
    PENDING=$(echo "$STATUS" | jq '.write_ahead_log.pending_writes')
    REPLAYING=$(echo "$STATUS" | jq '.write_ahead_log.is_replaying')
    FAILED=$(echo "$STATUS" | jq '.write_ahead_log.failed_replays')
    
    echo "$(date): WAL Status - Pending: $PENDING, Replaying: $REPLAYING, Failed: $FAILED"
    
    # Alert conditions
    if [ "$PENDING" -gt 20 ]; then
        echo "⚠️  WARNING: High pending writes count: $PENDING"
    fi
    
    if [ "$FAILED" -gt 2 ]; then
        echo "🚨 CRITICAL: Replay failures detected: $FAILED"
    fi
    
    sleep 30
done
```

## 🔧 Maintenance Procedures

### WAL Health Check

```bash
#!/bin/bash
# wal_health_check.sh

LOAD_BALANCER_URL="https://chroma-load-balancer.onrender.com"

echo "🔍 WAL Health Check - $(date)"
echo "=================================="

# 1. Get overall status
STATUS=$(curl -s "$LOAD_BALANCER_URL/status")
if [ $? -ne 0 ]; then
    echo "❌ FAIL: Cannot reach load balancer"
    exit 1
fi

# 2. Check WAL structure
WAL_PRESENT=$(echo "$STATUS" | jq 'has("write_ahead_log")')
if [ "$WAL_PRESENT" != "true" ]; then
    echo "❌ FAIL: WAL not present in status"
    exit 1
fi

# 3. Extract WAL metrics
PENDING=$(echo "$STATUS" | jq '.write_ahead_log.pending_writes')
REPLAYING=$(echo "$STATUS" | jq '.write_ahead_log.is_replaying') 
TOTAL_REPLAYED=$(echo "$STATUS" | jq '.write_ahead_log.total_replayed')
FAILED_REPLAYS=$(echo "$STATUS" | jq '.write_ahead_log.failed_replays')

# 4. Instance health
PRIMARY_HEALTHY=$(echo "$STATUS" | jq '.instances[] | select(.name=="primary") | .healthy')
REPLICA_HEALTHY=$(echo "$STATUS" | jq '.instances[] | select(.name=="replica") | .healthy')

# 5. Report results
echo "WAL Metrics:"
echo "  Pending writes: $PENDING"
echo "  Currently replaying: $REPLAYING" 
echo "  Total replayed: $TOTAL_REPLAYED"
echo "  Failed replays: $FAILED_REPLAYS"
echo ""
echo "Instance Health:"
echo "  Primary: $PRIMARY_HEALTHY"
echo "  Replica: $REPLICA_HEALTHY"

# 6. Health assessment
if [ "$PENDING" -eq 0 ] && [ "$REPLAYING" == "false" ]; then
    echo "✅ WAL Status: HEALTHY"
elif [ "$PENDING" -lt 10 ]; then
    echo "⚠️  WAL Status: WARNING - Some pending writes"
else
    echo "🚨 WAL Status: CRITICAL - High pending writes"
fi
```

### Performance Testing

```bash
#!/bin/bash
# wal_performance_test.sh

LOAD_BALANCER_URL="https://chroma-load-balancer.onrender.com"
TEST_COLLECTION="wal_perf_test_$(date +%s)"

echo "🚀 WAL Performance Test"
echo "======================="

# 1. Test normal operation speed
echo "Testing normal operation..."
START_TIME=$(date +%s.%N)
curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"name\":\"$TEST_COLLECTION\",\"metadata\":{\"test\":\"performance\"}}" \
  "$LOAD_BALANCER_URL/api/v2/collections" > /dev/null
END_TIME=$(date +%s.%N)
NORMAL_TIME=$(echo "$END_TIME - $START_TIME" | bc)

echo "Normal operation time: ${NORMAL_TIME}s"

# 2. Test status endpoint speed
echo "Testing status endpoint..."
START_TIME=$(date +%s.%N)
curl -s "$LOAD_BALANCER_URL/status" > /dev/null
END_TIME=$(date +%s.%N)
STATUS_TIME=$(echo "$END_TIME - $START_TIME" | bc)

echo "Status endpoint time: ${STATUS_TIME}s"

# 3. Cleanup
curl -s -X DELETE "$LOAD_BALANCER_URL/api/v2/collections/$TEST_COLLECTION" > /dev/null

# 4. Performance assessment
if (( $(echo "$STATUS_TIME < 2.0" | bc -l) )); then
    echo "✅ Performance: GOOD"
else
    echo "⚠️  Performance: SLOW - Status endpoint > 2s"
fi
```

## 🎛️ Configuration Management

### Environment Variables

```bash
# WAL Configuration
export CONSISTENCY_WINDOW=30
export READ_REPLICA_RATIO=0.8
export REQUEST_TIMEOUT=15
export CHECK_INTERVAL=30

# Instance URLs
export PRIMARY_URL="https://chroma-primary.onrender.com"
export REPLICA_URL="https://chroma-replica.onrender.com"
```

### Tuning Guidelines

| Parameter | Low Load | Medium Load | High Load |
|-----------|----------|-------------|-----------|
| `CONSISTENCY_WINDOW` | 30s | 20s | 10s |
| `READ_REPLICA_RATIO` | 0.5 | 0.7 | 0.8 |
| `REQUEST_TIMEOUT` | 30s | 15s | 10s |
| `CHECK_INTERVAL` | 60s | 30s | 15s |

## 📈 Capacity Planning

### WAL Memory Usage

```python
# Estimate WAL memory usage
def estimate_wal_memory(avg_write_size_kb, writes_per_minute, outage_duration_minutes):
    total_writes = writes_per_minute * outage_duration_minutes
    total_memory_kb = total_writes * avg_write_size_kb
    return total_memory_kb / 1024  # MB

# Example scenarios
print(f"Light load: {estimate_wal_memory(5, 10, 60):.1f} MB")    # 5KB writes, 10/min, 1hr outage
print(f"Medium load: {estimate_wal_memory(20, 50, 30):.1f} MB")  # 20KB writes, 50/min, 30min outage  
print(f"Heavy load: {estimate_wal_memory(100, 200, 15):.1f} MB") # 100KB writes, 200/min, 15min outage
```

### Scaling Considerations

- **Memory**: 1GB can handle ~10,000 typical writes
- **Network**: Replay speed limited by primary bandwidth
- **CPU**: WAL operations are lightweight
- **Storage**: Consider persistent WAL for long outages

## 🔒 Security Considerations

### WAL Data Handling

- **In-Memory Only**: WAL data not persisted to disk
- **No Encryption**: WAL inherits encryption from underlying requests
- **Access Control**: WAL status accessible via load balancer endpoints
- **Audit Trail**: WAL operations logged but not retained

### Best Practices

1. **Monitor WAL Size**: Prevent memory exhaustion
2. **Secure Endpoints**: Protect status/health endpoints
3. **Log Management**: Ensure WAL logs are properly rotated
4. **Network Security**: Use HTTPS for all WAL communications

---

**WAL Operations Guide v1.0**  
*Ensuring reliable operations of Write-Ahead Log system* 