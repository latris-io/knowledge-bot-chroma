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
MAX_RETRIES=30  # 30 seconds

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f http://localhost:8000/api/v1/heartbeat > /dev/null 2>&1; then
        echo "✅ ChromaDB is ready and responding to health checks!"
        break
    else
        echo "⏳ ChromaDB not ready yet... (attempt $((RETRY_COUNT + 1))/$MAX_RETRIES)"
        sleep 1
        RETRY_COUNT=$((RETRY_COUNT + 1))
    fi
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "❌ ChromaDB failed to become ready within $MAX_RETRIES seconds"
    exit 1
fi

echo "🎉 ChromaDB is fully initialized and ready!"
echo "🌐 Health check endpoint: http://localhost:8000/api/v1/heartbeat"
echo "📊 Connect to ChromaDB at: http://localhost:8000"

# Keep the script running and monitor ChromaDB
wait $CHROMA_PID 