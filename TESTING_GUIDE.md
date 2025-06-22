# ChromaDB High Availability Testing Guide

This guide provides comprehensive testing procedures for your redundant ChromaDB setup with **accurate validation** and **enhanced cleanup**.

## 🛡️ **CRITICAL: Test Validation Bug Fixed (Commit de446a9)**

**MAJOR DISCOVERY**: Previous test validation was showing **false negatives** due to using collection names instead of UUIDs when querying ChromaDB instances directly.

**Impact**: 
- ✅ **System was working perfectly** with zero transaction loss
- ❌ **Tests were lying** and reporting "sync issues" when system was bulletproof
- ✅ **Now fixed**: Tests show accurate system performance

## 🚀 **Quick Start (Current System 2025)**

### **Primary: Production Validation Suite**

```bash
# Run comprehensive production validation (RECOMMENDED)
python run_all_tests.py --url https://chroma-load-balancer.onrender.com

# Expected: 6/6 tests passed (🏆 PERFECT 100% success) with bulletproof validation
# Features: Enhanced cleanup (ChromaDB + PostgreSQL), selective lifecycle
```

### **Secondary: Enhanced Comprehensive Testing**

```bash
# Run all scenarios including failover testing
python run_enhanced_tests.py --url https://chroma-load-balancer.onrender.com

# Expected: 8/8+ tests passed with comprehensive scenario coverage
# Features: USE CASE testing, failover validation, performance testing
```

### **Specialized: Transaction Safety Validation**

```bash
# Test bulletproof transaction safety under stress
python test_use_case_4_transaction_safety.py --url https://chroma-load-balancer.onrender.com

# Expected: 15/15 transactions logged (100% capture rate)
# Features: Stress testing, transaction logging verification
```

### Prerequisites

```bash 
pip install chromadb requests psycopg2-binary
export DATABASE_URL="your_postgresql_connection_string"
export SLACK_WEBHOOK_URL="your_slack_webhook_url"  # Optional
```

## 📋 **Comprehensive Test Coverage (Current System 2025)**

### **🎯 Primary Production Validation (`run_all_tests.py`)**
- ✅ **System Health**: Load balancer and instance health with accurate validation
- ✅ **Collection Creation & Mapping**: Distributed UUID mapping with bulletproof validation
- ✅ **Load Balancer Failover**: CMS resilience testing with write failover
- ✅ **WAL Sync System**: Write-ahead log functionality with proper timing
- ✅ **Document Operations**: CMS-like workflow with accurate document validation

**Test Validation Fixed**: Now shows correct document counts instead of false "sync issues"

### **🚀 Enhanced Comprehensive Testing (`run_enhanced_tests.py`)**
- ✅ **Health Endpoints**: System health validation with proper monitoring
- ✅ **Collection Operations**: Distributed operations with UUID mapping validation
- ✅ **Document Operations**: CMS simulation with fixed sync validation
- ✅ **WAL Functionality**: Write-ahead log processing with accurate status
- ✅ **Load Balancer Features**: Read distribution with proper health checking
- ✅ **Document Delete Sync**: Collection deletion with cross-instance validation
- ✅ **Write Failover - Primary Down**: USE CASE 2 validation with infrastructure testing
- ✅ **DELETE Sync Functionality**: Cross-instance deletion sync validation
- ✅ **Replica Down Scenario**: USE CASE 3 validation with read failover

### **🛡️ Transaction Safety Validation (`test_use_case_4_transaction_safety.py`)**
- ✅ **Stress Load Generation**: High-concurrency collection creation testing
- ✅ **Transaction Logging Verification**: 100% transaction capture rate validation
- ✅ **503 Error Handling**: Operations logged even during timeout/connection issues
- ✅ **Baseline Comparison**: Before/after transaction count measurement
- ✅ **Production Safety**: Zero data loss confirmation under stress conditions

### **⚖️ Manual Infrastructure Testing (`use_case_2_manual_testing.py`)**
- ✅ **Real Infrastructure Failure**: Actual primary instance suspension testing
- ✅ **CMS Operation Continuity**: File upload/delete/query during failures  
- ✅ **Automatic Recovery Validation**: Primary restoration and sync verification
- ✅ **End-to-End Workflow**: Complete failure → recovery → validation cycle

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
