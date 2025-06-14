# ChromaDB High Availability on Render

## 🎯 **Render-Specific Deployment Guide**

This guide explains how to deploy a redundant ChromaDB setup on Render with automated failover capabilities.

## 📋 **Prerequisites**

- Render account with billing enabled
- GitHub repository with this code
- Optional: Slack webhook for notifications
- Optional: PostgreSQL database for metrics storage

## 🏗️ **Architecture on Render**

```
┌─────────────────────────────────────────────────────────────────┐
│                        Render Platform                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐ │
│  │  Load Balancer  │    │  Primary DB     │    │  Replica DB     │ │
│  │  (Web Service)  │───▶│  (Web Service)  │    │  (Web Service)  │ │
│  │  Port: 8000     │    │  Port: 8000     │    │  Port: 8000     │ │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘ │
│           │                                                       │
│  ┌─────────────────┐    ┌─────────────────┐                      │
│  │  Health Monitor │    │  PostgreSQL     │                      │
│  │  (Worker)       │    │  (Database)     │                      │
│  └─────────────────┘    └─────────────────┘                      │
└─────────────────────────────────────────────────────────────────┘
```

## 🚀 **Deployment Steps**

### **Step 1: Repository Setup**

1. **Fork/Clone** this repository to your GitHub account
2. **Ensure all files** are in the repository:
   - `render.yaml` (main deployment configuration)
   - `Dockerfile` (ChromaDB instances)
   - `Dockerfile.loadbalancer` (load balancer service)
   - `Dockerfile.monitor` (monitoring service)
   - `load_balancer.py` (load balancer application)
   - `render_monitor.py` (monitoring application)
   - `requirements.txt`, `requirements.loadbalancer.txt`, `requirements.monitor.txt`

### **Step 2: Deploy to Render**

#### **Option A: Using render.yaml (Recommended)**

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New"** → **"Blueprint"**
3. Connect your GitHub repository
4. Select your repository and branch
5. Render will automatically detect `render.yaml` and deploy all services

#### **Option B: Manual Service Creation**

If you prefer manual setup:

1. **Create Primary ChromaDB Service:**
   ```
   Service Type: Web Service
   Name: chroma-primary
   Environment: Docker
   Dockerfile Path: ./Dockerfile
   Plan: Starter ($7/month)
   ```

2. **Create Replica ChromaDB Service:**
   ```
   Service Type: Web Service
   Name: chroma-replica
   Environment: Docker
   Dockerfile Path: ./Dockerfile
   Plan: Starter ($7/month)
   ```

3. **Create Load Balancer Service:**
   ```
   Service Type: Web Service
   Name: chroma-load-balancer
   Environment: Docker
   Dockerfile Path: ./Dockerfile.loadbalancer
   Plan: Starter ($7/month)
   ```

4. **Create Monitor Service:**
   ```
   Service Type: Background Worker
   Name: chroma-monitor
   Environment: Docker
   Dockerfile Path: ./Dockerfile.monitor
   Plan: Starter ($7/month)
   ```

### **Step 3: Configure Environment Variables**

For each service, set the following environment variables:

#### **Primary ChromaDB (`chroma-primary`)**
```bash
CHROMA_SERVER_HOST=0.0.0.0
CHROMA_SERVER_HTTP_PORT=8000
CHROMA_PERSIST_DIRECTORY=/chroma/chroma
INSTANCE_ROLE=primary
INSTANCE_PRIORITY=100
```

#### **Replica ChromaDB (`chroma-replica`)**
```bash
CHROMA_SERVER_HOST=0.0.0.0
CHROMA_SERVER_HTTP_PORT=8000
CHROMA_PERSIST_DIRECTORY=/chroma/chroma
INSTANCE_ROLE=replica
INSTANCE_PRIORITY=80
```

#### **Load Balancer (`chroma-load-balancer`)**
```bash
PRIMARY_URL=https://chroma-primary.onrender.com
REPLICA_URL=https://chroma-replica.onrender.com
CHECK_INTERVAL=30
FAILURE_THRESHOLD=3
NOTIFICATION_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK
```

#### **Monitor (`chroma-monitor`)**
```bash
PRIMARY_URL=https://chroma-primary.onrender.com
REPLICA_URL=https://chroma-replica.onrender.com
LOAD_BALANCER_URL=https://chroma-load-balancer.onrender.com
CHECK_INTERVAL=30
FAILURE_THRESHOLD=3
NOTIFICATION_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK
DATABASE_URL=postgres://user:pass@hostname:port/database
```

### **Step 4: Add Persistent Storage**

For each ChromaDB service, add a persistent disk:

1. Go to your service settings
2. Click **"Add Disk"**
3. Configure:
   ```
   Name: chroma-data
   Mount Path: /chroma/chroma
   Size: 10GB (or as needed)
   ```

### **Step 5: Configure Health Checks**

Render will automatically use the health check paths defined in `render.yaml`:

- **ChromaDB instances**: `/api/v1/heartbeat`
- **Load balancer**: `/health`

## 🔧 **Configuration**

### **Service URLs**

After deployment, your services will be available at:

- **Load Balancer**: `https://chroma-load-balancer.onrender.com` (main endpoint)
- **Primary**: `https://chroma-primary.onrender.com`
- **Replica**: `https://chroma-replica.onrender.com`
- **Monitor Status**: `https://chroma-load-balancer.onrender.com/status`

### **Usage in Your Application**

Update your knowledge bot to use the load balancer endpoint:

```python
import chromadb

# Use the load balancer URL
client = chromadb.HttpClient(
    host="chroma-load-balancer.onrender.com",
    port=443,  # HTTPS
    ssl=True
)

# Use normally - failover is automatic
collection = client.get_or_create_collection("knowledge-base")
```

## 🔍 **Monitoring & Alerts**

### **Health Check Endpoints**

- **Load Balancer Health**: `https://chroma-load-balancer.onrender.com/health`
- **Detailed Status**: `https://chroma-load-balancer.onrender.com/status`
- **Primary Health**: `https://chroma-primary.onrender.com/api/v1/heartbeat`
- **Replica Health**: `https://chroma-replica.onrender.com/api/v1/heartbeat`

### **Notification Setup**

1. **Create Slack Webhook:**
   ```
   https://api.slack.com/messaging/webhooks
   ```

2. **Add to Environment Variables:**
   ```bash
   NOTIFICATION_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK
   ```

3. **Test Notifications:**
   The system will automatically send alerts for:
   - Instance failures
   - Recovery events
   - Critical system issues

## 📊 **Cost Breakdown**

### **Monthly Costs (Starter Plan)**
- Primary ChromaDB: $7/month
- Replica ChromaDB: $7/month  
- Load Balancer: $7/month
- Monitor Worker: $7/month
- PostgreSQL Database: $0 (free tier)
- **Total: ~$28/month**

### **Cost Optimization**
- Use **Hobby Plan** ($7/month) for non-production
- **Free tier** available for development/testing
- Scale down replicas if not needed

## ⚠️ **Render Limitations**

### **What Works**
✅ Multiple independent services
✅ Service-to-service communication
✅ Health checks and auto-restart
✅ Persistent storage
✅ Environment variables
✅ Custom Docker images

### **What Doesn't Work**
❌ Docker Compose orchestration
❌ Kubernetes deployments
❌ Custom networking
❌ HAProxy deployment
❌ Direct service manipulation

### **Workarounds**
- **Load Balancing**: Custom Flask app instead of HAProxy
- **Service Discovery**: Hard-coded URLs with environment variables
- **Failover**: Application-level failover instead of infrastructure-level

## 🧪 **Testing Failover**

### **Manual Failover Test**

1. **Check Current Status:**
   ```bash
   curl https://chroma-load-balancer.onrender.com/status
   ```

2. **Simulate Primary Failure:**
   Go to Render dashboard and suspend the primary service

3. **Verify Failover:**
   ```bash
   # Should still work via replica
   curl https://chroma-load-balancer.onrender.com/api/v1/heartbeat
   ```

4. **Check Notifications:**
   You should receive Slack notifications about the failure and failover

### **Automated Testing**

```bash
# Test script (run locally)
#!/bin/bash
echo "Testing ChromaDB failover..."

# Check load balancer status
curl -s https://chroma-load-balancer.onrender.com/status | jq .

# Test API functionality
curl -s https://chroma-load-balancer.onrender.com/api/v1/heartbeat

echo "Test completed"
```

## 🛠️ **Troubleshooting**

### **Common Issues**

**Service won't start:**
```bash
# Check logs in Render dashboard
# Verify environment variables
# Check Dockerfile syntax
```

**Health checks failing:**
```bash
# Verify health check endpoints
curl https://chroma-primary.onrender.com/api/v1/heartbeat
curl https://chroma-replica.onrender.com/api/v1/heartbeat
```

**Load balancer not routing:**
```bash
# Check load balancer logs
# Verify service URLs in environment variables
# Test individual service health
```

### **Performance Issues**

- **Cold starts**: Render services sleep after 15 minutes of inactivity
- **Persistent connections**: Keep services warm with periodic health checks
- **Response times**: Expect 100-500ms additional latency vs local deployment

## 🔄 **Updates & Maintenance**

### **Updating Services**

1. **Push changes** to your GitHub repository
2. **Render auto-deploys** from connected branch
3. **Rolling updates** maintain availability during deployment
4. **Rollback** available if issues occur

### **Scaling**

- **Vertical scaling**: Upgrade to higher tier plans
- **Horizontal scaling**: Add more replica services
- **Regional deployment**: Deploy in multiple regions

## 📝 **Best Practices**

1. **Always use HTTPS** for service-to-service communication
2. **Set appropriate timeouts** for health checks
3. **Monitor service logs** regularly
4. **Test failover scenarios** periodically
5. **Keep backups** of persistent data
6. **Use environment variables** for all configuration
7. **Set up monitoring alerts** for critical issues

## 🎉 **Deployment Complete!**

Your redundant ChromaDB setup is now running on Render with:

- ✅ **Automatic failover** between primary and replica
- ✅ **Health monitoring** with Slack notifications
- ✅ **Load balancing** with intelligent routing
- ✅ **Persistent storage** for data durability
- ✅ **Zero-downtime** deployments

Your knowledge bot can now connect to:
```
https://chroma-load-balancer.onrender.com
```

And enjoy high availability with automated failover! 🚀 