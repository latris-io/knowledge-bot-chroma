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

# Wait for ChromaDB to be ready
echo "⏳ Waiting for ChromaDB to initialize..."
RETRY_COUNT=0
MAX_RETRIES=60  # 60 seconds - more time for initialization

# First wait for the process to be listening
echo "🔌 Waiting for ChromaDB to start listening..."
sleep 15  # Give more initial time

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    # Test with more verbose output for debugging
    if curl -f http://localhost:8000/api/v1/heartbeat > /dev/null 2>&1; then
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
    curl -v http://localhost:8000/api/v1/heartbeat || echo "Health check failed"
    echo "📋 ChromaDB process status:"
    ps aux | grep chroma || echo "No ChromaDB process found"
    exit 1
fi

echo "🎉 ChromaDB is fully initialized and ready!"
echo "🌐 Health check endpoint: http://localhost:8000/api/v1/heartbeat"
echo "📊 Connect to ChromaDB at: http://localhost:8000"

# Keep the script running and monitor ChromaDB
wait $CHROMA_PID 