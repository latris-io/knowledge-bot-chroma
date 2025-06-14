#!/bin/bash

# ChromaDB Deployment Monitor
# Monitors deployment progress after health check timeout fixes

echo "🩺 ChromaDB Deployment Monitor"
echo "=============================="
echo "⏰ Started: $(date)"
echo ""

# Service URLs
PRIMARY_URL="https://chroma-primary.onrender.com/api/v2/version"
REPLICA_URL="https://chroma-replica.onrender.com/api/v2/version"  
LOADBALANCER_URL="https://chroma-load-balancer.onrender.com/health"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

check_service() {
    local name="$1"
    local url="$2"
    
    printf "🔍 Checking %-20s " "$name..."
    
    response=$(curl -s -o /dev/null -w "%{http_code},%{time_total}" "$url" 2>/dev/null)
    
    if [ $? -ne 0 ]; then
        printf "${RED}❌ CONNECTION ERROR${NC}\n"
        return 1
    fi
    
    status_code=$(echo "$response" | cut -d',' -f1)
    time_total=$(echo "$response" | cut -d',' -f2)
    
    if [ "$status_code" = "200" ]; then
        printf "${GREEN}✅ HEALTHY${NC} (${time_total}s)\n"
        return 0
    elif [ "$status_code" = "502" ]; then
        printf "${YELLOW}⏳ STARTING${NC} (${time_total}s)\n"
        return 1
    else
        printf "${RED}❌ ERROR $status_code${NC} (${time_total}s)\n"
        return 1
    fi
}

# Monitor deployment progress
attempt=1
max_attempts=20  # ~10 minutes with 30s intervals

while [ $attempt -le $max_attempts ]; do
    echo "📊 Health Check #$attempt ($(date '+%H:%M:%S'))"
    echo "─────────────────────────────────────────"
    
    primary_healthy=0
    replica_healthy=0
    lb_healthy=0
    
    check_service "Primary" "$PRIMARY_URL" && primary_healthy=1
    check_service "Replica" "$REPLICA_URL" && replica_healthy=1  
    check_service "Load Balancer" "$LOADBALANCER_URL" && lb_healthy=1
    
    echo ""
    
    total_healthy=$((primary_healthy + replica_healthy + lb_healthy))
    
    if [ $total_healthy -eq 3 ]; then
        echo "🎉 SUCCESS: All services are healthy!"
        echo "📊 Final Status: 3/3 services healthy"
        echo "⏰ Completed: $(date)"
        echo ""
        echo "🚀 Your ChromaDB HA setup is ready!"
        echo "   Load Balancer: https://chroma-load-balancer.onrender.com"
        echo "   Test with: curl https://chroma-load-balancer.onrender.com/health"
        exit 0
    elif [ $total_healthy -eq 2 ] && [ $lb_healthy -eq 1 ]; then
        echo "⚠️  PARTIAL: Load balancer healthy, ChromaDB instances still starting..."
        echo "📊 Status: $total_healthy/3 services healthy"
    elif [ $total_healthy -eq 1 ] && [ $lb_healthy -eq 1 ]; then
        echo "⏳ PROGRESS: Load balancer healthy, ChromaDB instances deploying..."
        echo "📊 Status: $total_healthy/3 services healthy"
    else
        echo "⚠️  WAITING: $total_healthy/3 services healthy"
    fi
    
    if [ $attempt -lt $max_attempts ]; then
        echo "⏰ Waiting 30 seconds before next check..."
        echo ""
        sleep 30
    fi
    
    attempt=$((attempt + 1))
done

# Timeout reached
echo "⏰ TIMEOUT: Deployment monitoring timed out after $((max_attempts * 30 / 60)) minutes"
echo "📊 Final Status: Check Render dashboard for detailed logs"
echo ""
echo "🔧 Troubleshooting:"
echo "   1. Go to Render Dashboard"
echo "   2. Check individual service logs"
echo "   3. Look for deployment errors"
echo "   4. Verify services are rebuilding with new health checks"
echo ""
echo "💡 Services may still be deploying - check dashboard for progress"

exit 1 