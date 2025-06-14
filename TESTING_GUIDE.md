# ChromaDB High Availability Testing Guide

This guide provides comprehensive testing procedures for your redundant ChromaDB setup.

## 🚀 Quick Start

### Automated Testing

```bash
# Run basic automated tests
python test_suite.py

# Test against specific URL
python test_suite.py --url https://your-load-balancer.onrender.com

# Save detailed results
python test_suite.py --output test_results.json
```

### Prerequisites

```bash 
pip install chromadb requests
```

## 📋 Test Categories

### 1. Basic Connectivity Tests
- Load balancer accessibility
- Health endpoint responses
- ChromaDB API availability

### 2. Load Balancing Tests
- Request distribution based on strategy
- Round-robin behavior
- Write-primary routing

### 3. ChromaDB Operation Tests
- Collection creation
- Document insertion/querying
- Data retrieval

### 4. Failover Readiness Tests
- Multiple healthy instances
- Health monitoring active
- Failover configuration

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

## ✅ Test Checklist

Before production:
- [ ] All automated tests pass
- [ ] Load balancing works correctly
- [ ] Failover completes within 60 seconds
- [ ] Data sync functioning
- [ ] Performance meets requirements
- [ ] Monitoring configured

## 📈 Expected Performance

- **Write Operations:** 10-50 ops/second
- **Query Operations:** 20-100 ops/second
- **Health Check Response:** < 200ms
- **Failover Time:** 30-60 seconds
- **Data Sync Lag:** 5-10 minutes
