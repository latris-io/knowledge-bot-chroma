# ChromaDB Component Scaling Guide
## When to Upgrade Each Service Based on Real Metrics

### 🗄️ **Primary ChromaDB (chroma-primary)**
**Current**: Starter plan (512MB RAM, 10GB disk)

**Upgrade Triggers:**
- ❌ **Disk Full**: >80% disk usage (upgrade disk first)
- ❌ **Memory Pressure**: >85% RAM usage during writes
- ❌ **Write Latency**: >5 seconds for document insertion
- ❌ **Connection Errors**: HTTP 503/504 errors under load

**Upgrade Path:**
1. **Storage First**: 25GB disk (+$10/month) when >8GB used
2. **Performance Next**: Standard plan (+$21/month) when memory/CPU bottlenecked
3. **Scale Up**: Professional plan (+$85/month) when >1M active documents

**Capacity Estimates:**
- Starter: ~50K documents efficiently
- Standard: ~500K documents efficiently  
- Professional: ~5M documents efficiently

---

### 🔄 **Replica ChromaDB (chroma-replica)**
**Current**: Starter plan (512MB RAM, 10GB disk)

**Upgrade Triggers:**
- ❌ **Read Latency**: >3 seconds for document queries
- ❌ **Sync Lag**: >10 minutes behind primary
- ❌ **Query Failures**: Timeouts during read operations
- ❌ **Disk Usage**: >80% storage capacity

**Upgrade Path:**
1. **Storage**: Upgrade disk when approaching capacity
2. **Performance**: Standard plan when read performance degrades
3. **Redundancy**: Add second replica when high availability critical

**Load Balancing**: Replica handles ~40% of read traffic

---

### ⚖️ **Load Balancer (chroma-load-balancer)**
**Current**: Starter plan (512MB RAM)

**Upgrade Triggers:**
- ❌ **Request Queue**: >100 pending requests
- ❌ **Response Time**: >2 seconds for routing decisions
- ❌ **Memory Usage**: >400MB (80% of container)
- ❌ **Failed Health Checks**: >5% health check failures

**Upgrade Path:**
1. **Standard Plan** (+$21/month): When handling >1000 requests/hour
2. **Professional Plan** (+$85/month): When handling >10000 requests/hour

**Performance Impact**: Load balancer rarely bottlenecks before databases

---

### 📊 **Monitor Service (chroma-monitor)**
**Current**: Starter plan (512MB RAM)

**Upgrade Triggers:**
- ❌ **Monitoring Lag**: >60 second delay in health checks
- ❌ **Alert Failures**: Missing critical alerts
- ❌ **Memory Growth**: Continuous memory increase (leak)

**Upgrade Path:**
- Usually **LAST** to need upgrading
- Monitoring is lightweight - starter plan handles massive scales
- Only upgrade if storing extensive historical metrics

**Note**: Monitor typically stays on starter plan indefinitely

---

### 🔄 **Sync Service (chroma-sync)**
**Current**: Starter plan (512MB RAM)

**Upgrade Triggers:**
- ❌ **Sync Failures**: Memory errors during batch processing
- ❌ **Sync Lag**: >30 minutes behind primary
- ❌ **Batch Errors**: Unable to process document batches
- ❌ **OOM Kills**: Container restarts due to memory

**Upgrade Path:**
1. **First Priority**: Usually first service to need upgrading
2. **Standard Plan** (+$21/month): When syncing >50K documents
3. **Professional Plan** (+$85/month): When syncing >1M documents

**Why First**: Sync service does most memory-intensive work

---

### 🗃️ **PostgreSQL Database (chroma-metadata)**
**Current**: Free plan (1GB storage)

**Upgrade Triggers:**
- ❌ **Storage**: >800MB used (80% capacity)
- ❌ **Connection Limits**: "Too many connections" errors
- ❌ **Query Performance**: >5 seconds for state queries
- ❌ **Backup Needs**: Production-grade backup requirements

**Upgrade Path:**
1. **Standard Plan** (+$15/month): 10GB storage, better performance
2. **Professional Plan** (+65/month): 100GB storage, high availability

**Data Growth**: ~1MB per 10K documents synced (very efficient)

---

## 💰 **Cost-Optimized Upgrade Sequence**

### **Most Common Real-World Progression:**

#### **Month 1-3: Learning/Testing** ($0/month)
- All services on free/starter tier
- Handle up to ~10K documents comfortably

#### **Month 4-6: Growing Data** (~$25/month)
```yaml
Upgrades:
  - Primary disk: 25GB (+$10)
  - Replica disk: 25GB (+$10) 
  - PostgreSQL: Standard (+$15)
# Handles ~100K documents
```

#### **Month 7-12: Performance Needs** (~$65/month)
```yaml
Additional Upgrades:
  - Sync service: Standard (+$21)
  - Load balancer: Standard (+$21)
# Handles ~500K documents with good performance
```

#### **Year 2+: Scale Requirements** (~$150/month)
```yaml
Additional Upgrades:
  - Primary: Standard (+$21)
  - Replica: Standard (+$21)
# Handles 1M+ documents efficiently
```

---

## 📊 **Automated Monitoring Alerts**

### **Set Up Alerts for Each Component:**

```yaml
# Resource monitoring thresholds
alerts:
  primary_disk_usage:
    threshold: 80%
    message: "Primary storage upgrade needed (+$10/month)"
    
  sync_memory_usage:
    threshold: 85%
    message: "Sync service upgrade needed (+$21/month)"
    
  postgres_size:
    threshold: 800MB
    message: "PostgreSQL upgrade needed (+$15/month)"
    
  replica_lag:
    threshold: 600 seconds
    message: "Replica performance upgrade needed"
```

---

## 🎯 **Key Principles**

1. **Storage First**: Usually hits limits before CPU/RAM
2. **Sync Service**: Typically first performance bottleneck
3. **Monitor Last**: Rarely needs upgrading
4. **Independent Scaling**: Each service upgrades separately
5. **Cost Efficiency**: Only pay for what you actually need

---

## 📈 **Capacity Planning**

| Documents | Monthly Cost | Services Upgraded |
|-----------|--------------|-------------------|
| 0-50K     | $0           | None (free tier)  |
| 50K-100K  | $25          | Storage only      |
| 100K-500K | $65          | + Sync & LB       |
| 500K-1M   | $150         | + Primary & Replica|
| 1M-5M     | $300         | Professional plans |
| 5M+       | $500+        | Multi-replica     |

**Result**: You never pay for capacity you don't need, but the architecture is ready to scale to millions of documents without major rewrites. 