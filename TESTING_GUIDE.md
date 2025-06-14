# ChromaDB High Availability Testing Guide

This guide provides comprehensive testing procedures for your redundant ChromaDB setup with distributed sync, monitoring, and Slack notifications.

## 🚀 Quick Start

### **NEW: Comprehensive Test Runner**

```bash
# Run ALL test suites (recommended)
python run_all_tests.py

# Quick test (required tests only)
python run_all_tests.py --quick

# Save detailed report
python run_all_tests.py --save-report test_report.json
```

### **Individual Test Suites**

```bash
# Basic functionality (connectivity, operations, load balancing)
python test_suite.py --url https://your-load-balancer.onrender.com

# Advanced performance testing
python advanced_tests.py --concurrent-users 5 --duration 30

# Distributed sync coordination
python test_distributed_sync.py

# Resource monitoring and Slack notifications
python test_monitoring_and_slack.py

# Production features (memory optimization, backward compatibility)
python test_production_features.py

# Load balancer logic
python test_load_balancer_logic.py
```

### Prerequisites

```bash 
pip install chromadb requests psycopg2-binary
export DATABASE_URL="your_postgresql_connection_string"
export SLACK_WEBHOOK_URL="your_slack_webhook_url"  # Optional
```

## 📋 Comprehensive Test Coverage

### **1. Basic Functionality (test_suite.py)**
- ✅ Load balancer accessibility and health endpoints
- ✅ ChromaDB API availability and basic operations
- ✅ Request distribution based on strategy
- ✅ Failover readiness and multiple instance health

### **2. Advanced Performance (advanced_tests.py)**  
- ✅ Write performance with batch operations
- ✅ Concurrent user simulation (multiple simultaneous users)
- ✅ Load testing with realistic workloads
- ✅ Performance metrics collection and analysis

### **3. Distributed Sync Coordination (test_distributed_sync.py)**
- ✅ Coordinator task creation and chunk distribution
- ✅ Worker task claiming and processing
- ✅ PostgreSQL-based task coordination
- ✅ Data consistency verification across primary/replica
- ✅ Worker heartbeat and health monitoring

### **4. Resource Monitoring & Slack (test_monitoring_and_slack.py)**
- ✅ Database schema validation (performance_metrics, upgrade_recommendations, sync_tasks, sync_workers)
- ✅ Slack notification message formatting and delivery
- ✅ Upgrade recommendation logic for memory/CPU/disk
- ✅ Frequency limiting for alert spam prevention
- ✅ Performance metrics storage and retrieval

### **5. Production Features (test_production_features.py)**
- ✅ Backward compatibility (traditional vs distributed modes)
- ✅ Memory pressure detection and adaptive batching
- ✅ Configuration validation and environment variable handling
- ✅ Worker vs coordinator role detection
- ✅ Error handling resilience and recovery mechanisms

### **6. Load Balancer Logic (test_load_balancer_logic.py)**
- ✅ Load balancing strategies (round-robin, write-primary, etc.)
- ✅ Health check mechanisms and failover logic
- ✅ Request routing and distribution accuracy

## 🔧 Manual Testing Scenarios

### Normal Operation Testing

1. Check Service Status:
```bash
curl https://chroma-load-balancer.onrender.com/status
```

2. Test Basic Operations:
```python
import chromadb

client = chromadb.HttpClient(
    host="chroma-load-balancer.onrender.com",
    port=443,
    ssl=True
)

# Create collection
collection = client.get_or_create_collection("test_manual")

# Add documents
collection.add(
    documents=["Test document 1", "Test document 2"],
    ids=["manual_1", "manual_2"]
)

# Query
results = collection.query(query_texts=["test"], n_results=5)
print(f"Found {len(results['ids'][0])} results")

# Cleanup
client.delete_collection("test_manual")
```

### Failover Testing

⚠️ **WARNING:** This will temporarily affect service availability.

1. Document current state:
```bash
curl https://chroma-load-balancer.onrender.com/status > before_failover.json
```

2. Simulate primary failure:
   - Go to Render Dashboard
   - Suspend `chroma-primary` service
   - Wait 30-60 seconds

3. Verify failover:
```bash
# Should still work via replica
curl https://chroma-load-balancer.onrender.com/api/v1/heartbeat
```

4. Restore primary:
   - Resume service in Render
   - Verify both instances healthy

## 📊 Monitoring During Tests

```bash
# Check strategy and instance health
curl https://chroma-load-balancer.onrender.com/status | jq '{
  strategy: .load_balancer.strategy,
  healthy_instances: .summary.healthy_instances
}'

# Monitor request distribution  
curl https://chroma-load-balancer.onrender.com/status | jq '.instances[] | {
  name: .name,
  request_count: .request_count,
  healthy: .healthy
}'
```

## 🚨 Troubleshooting

### Common Issues

**Tests Failing to Connect:**
- Check service status in Render Dashboard
- Verify all services are "Live"
- Wait for services to fully start (2-3 minutes)

**Load Balancing Not Working:**
- Check strategy: `curl .../status`
- Verify instance health
- Check load balancer logs

**Failover Not Triggering:**
- Check health check configuration
- Review monitor service logs
- Verify failure thresholds

## 🧪 Testing New Scalability Features

### **Distributed Sync Testing**

```bash
# Test coordinator/worker coordination
python test_distributed_sync.py

# Check sync tasks in database
psql $DATABASE_URL -c "SELECT * FROM sync_tasks ORDER BY created_at DESC LIMIT 5;"

# Check active workers
psql $DATABASE_URL -c "SELECT worker_id, worker_status, last_heartbeat FROM sync_workers;"
```

### **Resource Monitoring Testing**

```bash
# Test monitoring and alerts
python test_monitoring_and_slack.py

# Check upgrade recommendations
psql $DATABASE_URL -c "SELECT * FROM upgrade_recommendations ORDER BY created_at DESC LIMIT 5;"

# Check performance metrics
psql $DATABASE_URL -c "SELECT metric_timestamp, memory_percent, cpu_percent FROM performance_metrics ORDER BY metric_timestamp DESC LIMIT 5;"
```

### **Slack Notification Testing**

```bash
# Test Slack webhook (requires SLACK_WEBHOOK_URL)
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/your/webhook/url"
python test_monitoring_and_slack.py

# Manual Slack test
curl -X POST $SLACK_WEBHOOK_URL \
  -H 'Content-type: application/json' \
  --data '{"text":"🧪 Test notification from ChromaDB"}'
```

## ✅ Comprehensive Test Checklist

### **Core Infrastructure:**
- [ ] All automated tests pass (run_all_tests.py)
- [ ] Load balancing works correctly
- [ ] Failover completes within 60 seconds
- [ ] Basic data operations functional

### **Scalability Features:**
- [ ] Distributed sync coordination working
- [ ] Resource monitoring active
- [ ] Upgrade recommendations generating
- [ ] Slack notifications configured and working
- [ ] PostgreSQL database schema created
- [ ] Worker heartbeat system functional

### **Production Readiness:**
- [ ] Memory optimization working (adaptive batching)
- [ ] Backward compatibility maintained (traditional mode)
- [ ] Configuration validation passing
- [ ] Error handling resilient
- [ ] Performance meets requirements
- [ ] Cost optimization verified (free tier usage)

## 📈 Expected Performance

- **Write Operations:** 10-50 ops/second
- **Query Operations:** 20-100 ops/second
- **Health Check Response:** < 200ms
- **Failover Time:** 30-60 seconds
- **Data Sync Lag:** 5-10 minutes
