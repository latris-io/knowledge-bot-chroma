#!/bin/bash

# ChromaDB Startup Script
# Handles proper initialization and health check timing for Render deployment

echo "🚀 Starting ChromaDB initialization..."
echo "📁 Data directory: /chroma/chroma"
echo "🌐 Host: 0.0.0.0:8000"

# Ensure data directory exists and has proper permissions
mkdir -p /chroma/chroma
chmod 755 /chroma/chroma

echo "⏰ Allowing time for system initialization..."
sleep 10

echo "🔄 Starting ChromaDB server..."

# Start ChromaDB in background
chroma run --host 0.0.0.0 --port 8000 --path /chroma/chroma &
CHROMA_PID=$!

echo "📋 ChromaDB started with PID: $CHROMA_PID"

# Start resource monitoring if enabled
if [ -f "comprehensive_resource_monitor.py" ] && [ -n "$SLACK_WEBHOOK_URL" ]; then
    echo "📊 Starting resource monitoring..."
    SERVICE_NAME=${INSTANCE_ROLE:-"chroma-service"}
    python3 comprehensive_resource_monitor.py $SERVICE_NAME &
    MONITOR_PID=$!
    echo "📋 Resource monitor started with PID: $MONITOR_PID for service: $SERVICE_NAME"
fi

# Wait for ChromaDB to be ready
echo "⏳ Waiting for ChromaDB to initialize..."
RETRY_COUNT=0
MAX_RETRIES=60  # 60 seconds - more time for initialization

# First wait for the process to be listening
echo "🔌 Waiting for ChromaDB to start listening..."
sleep 15  # Give more initial time

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Try v2 API endpoints (v1 API is deprecated in 1.0.12)
    HEALTH_CHECK_PASSED=false
    
    # Try v2 version endpoint first (most reliable for v2 API)
    if curl -f -s http://localhost:8000/api/v2/version > /dev/null 2>&1; then
        HEALTH_CHECK_PASSED=true
    # Try v2 heartbeat endpoint  
    elif curl -f -s http://localhost:8000/api/v2/heartbeat > /dev/null 2>&1; then
        HEALTH_CHECK_PASSED=true
    # Try v2 collections endpoint (simple GET to check API is working)
    elif curl -f -s http://localhost:8000/api/v2/collections > /dev/null 2>&1; then
        HEALTH_CHECK_PASSED=true
    # Fallback: accept v1 deprecation response as "working" (410 Gone means API is responding)
    elif curl -s http://localhost:8000/api/v1/version 2>&1 | grep -q "410"; then
        HEALTH_CHECK_PASSED=true
    fi
    
    if [ "$HEALTH_CHECK_PASSED" = true ]; then
        echo "✅ ChromaDB is ready and responding to health checks!"
        break
    else
        # Check if ChromaDB process is still running
        if ! kill -0 $CHROMA_PID 2>/dev/null; then
            echo "❌ ChromaDB process has died!"
            exit 1
        fi
        
        echo "⏳ ChromaDB not ready yet... (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
        sleep 1
        RETRY_COUNT=$((RETRY_COUNT + 1))
    fi
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ ChromaDB failed to become ready within $MAX_RETRIES seconds"
    echo "🔍 Checking ChromaDB status..."
    echo "Testing v2 version endpoint:"
    curl -v http://localhost:8000/api/v2/version || echo "V2 version endpoint failed"
    echo "Testing v2 heartbeat endpoint:"
    curl -v http://localhost:8000/api/v2/heartbeat || echo "V2 heartbeat endpoint failed"
    echo "Testing v2 collections endpoint:"
    curl -v http://localhost:8000/api/v2/collections || echo "V2 collections endpoint failed"
    echo "Testing v1 version (for comparison):"
    curl -v http://localhost:8000/api/v1/version || echo "V1 version endpoint failed"
    echo "📋 ChromaDB process status:"
    if kill -0 $CHROMA_PID 2>/dev/null; then
        echo "ChromaDB process (PID: $CHROMA_PID) is still running"
    else
        echo "ChromaDB process (PID: $CHROMA_PID) is not running"
    fi
    echo "Process list (if available):"
    ps aux | grep chroma 2>/dev/null || echo "ps command not available"
    exit 1
fi

echo "🎉 ChromaDB is fully initialized and ready!"
echo "🌐 Available v2 endpoints: /api/v2/version, /api/v2/heartbeat, /api/v2/collections"
echo "📊 Connect to ChromaDB at: http://localhost:8000"

# Start health proxy for v1 API compatibility
echo "🔗 Starting health proxy for v1 API compatibility..."
if [ -f "health_proxy.py" ]; then
    PROXY_PORT=3000 python3 health_proxy.py &
    PROXY_PID=$!
    echo "📋 Health proxy started with PID: $PROXY_PID on port 3000"
else
    echo "⚠️ Health proxy not found, skipping"
fi

# Keep the script running and monitor both processes
wait $CHROMA_PID 