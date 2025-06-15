# Unified WAL Deployment Plan

## Current Status
- ❌ **chroma-sync**: Running `data_sync_service.py` (old service)
- ❌ **chroma-load-balancer**: Running `stable_load_balancer.py` (old service)  
- ✅ **unified WAL**: Developed but not deployed

## Deployment Steps

### 1. Update Load Balancer Dockerfile
```dockerfile
# Update Dockerfile.loadbalancer
COPY unified_wal_load_balancer.py ./
CMD ["python", "unified_wal_load_balancer.py"]
```

### 2. Remove Separate Sync Service
```yaml
# Remove from render.yaml (unified WAL handles sync)
# - type: worker
#   name: chroma-sync
```

### 3. Update Dependencies
```txt
# Add to requirements.loadbalancer.txt
psycopg2-binary>=2.9.0
psutil>=5.8.0
```

### 4. Environment Variables
```yaml
# Add to chroma-load-balancer in render.yaml
- key: DATABASE_URL
  fromDatabase:
    name: chroma-metadata
    property: connectionString
- key: WAL_SYNC_INTERVAL
  value: "10"
- key: MAX_MEMORY_MB
  value: "400"
- key: MAX_WORKERS
  value: "3"
```

## Benefits After Deployment
- ⚡ 10-second sync instead of 5-minute delays
- 🔄 Real-time WAL logging
- 🗑️ Smart deletion conversion (ChromaDB ID compatibility)
- 📊 High-volume processing
- 💾 PostgreSQL durability (zero data loss)
- 📈 Advanced monitoring and alerting

## Rollback Plan
- Keep old files as backup
- Quick revert to `stable_load_balancer.py` if needed
- Database schema is backward compatible 