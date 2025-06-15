#!/bin/bash
# wal_health_check.sh - WAL Health Check Script
# Comprehensive health check for Write-Ahead Log system

LOAD_BALANCER_URL="${LOAD_BALANCER_URL:-https://chroma-load-balancer.onrender.com}"

echo "🔍 WAL Health Check - $(date)"
echo "=================================="

# 1. Get overall status
echo "📡 Checking load balancer connectivity..."
STATUS=$(curl -s "$LOAD_BALANCER_URL/status" --max-time 10)
if [ $? -ne 0 ]; then
    echo "❌ FAIL: Cannot reach load balancer at $LOAD_BALANCER_URL"
    exit 1
fi

# 2. Check if response is valid JSON
echo "$STATUS" | jq . > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "❌ FAIL: Invalid JSON response from load balancer"
    exit 1
fi

# 3. Check WAL structure
WAL_PRESENT=$(echo "$STATUS" | jq 'has("write_ahead_log")')
if [ "$WAL_PRESENT" != "true" ]; then
    echo "❌ FAIL: WAL not present in status response"
    exit 1
fi

# 4. Extract WAL metrics
PENDING=$(echo "$STATUS" | jq '.write_ahead_log.pending_writes')
REPLAYING=$(echo "$STATUS" | jq '.write_ahead_log.is_replaying') 
TOTAL_REPLAYED=$(echo "$STATUS" | jq '.write_ahead_log.total_replayed')
FAILED_REPLAYS=$(echo "$STATUS" | jq '.write_ahead_log.failed_replays')

# 5. Instance health
PRIMARY_HEALTHY=$(echo "$STATUS" | jq '.instances[] | select(.name=="primary") | .healthy')
REPLICA_HEALTHY=$(echo "$STATUS" | jq '.instances[] | select(.name=="replica") | .healthy')

# 6. Service identification
SERVICE_NAME=$(echo "$STATUS" | jq -r '.service // "Unknown"')

# 7. Report results
echo ""
echo "📊 WAL Metrics:"
echo "  Service: $SERVICE_NAME"
echo "  Pending writes: $PENDING"
echo "  Currently replaying: $REPLAYING" 
echo "  Total replayed: $TOTAL_REPLAYED"
echo "  Failed replays: $FAILED_REPLAYS"
echo ""
echo "🏥 Instance Health:"
echo "  Primary: $PRIMARY_HEALTHY"
echo "  Replica: $REPLICA_HEALTHY"

# 8. Health assessment
echo ""
if [[ "$SERVICE_NAME" != *"Write-Ahead Log"* ]]; then
    echo "⚠️  WARNING: Service doesn't identify as WAL-enabled"
elif [ "$PENDING" -eq 0 ] && [ "$REPLAYING" == "false" ]; then
    echo "✅ WAL Status: HEALTHY"
elif [ "$PENDING" -lt 10 ]; then
    echo "⚠️  WAL Status: WARNING - Some pending writes ($PENDING)"
else
    echo "🚨 WAL Status: CRITICAL - High pending writes ($PENDING)"
fi

# 9. Recommendations
echo ""
echo "💡 Recommendations:"
if [ "$PENDING" -gt 20 ]; then
    echo "  🚨 HIGH: Investigate primary database status immediately"
elif [ "$FAILED_REPLAYS" -gt 5 ]; then
    echo "  ⚠️  MEDIUM: Review replay failures and primary connectivity"
elif [ "$PRIMARY_HEALTHY" == "false" ]; then
    echo "  ℹ️  INFO: Primary down - WAL should be protecting writes"
else
    echo "  ✅ GOOD: System operating normally"
fi

echo ""
echo "🏁 Health check completed at $(date)" 