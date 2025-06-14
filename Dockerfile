FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for health checks
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Create data directory for persistence
RUN mkdir -p /chroma/chroma

EXPOSE 8000

# Add health check with longer start period for ChromaDB initialization
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/api/v1/heartbeat || exit 1

# ✅ Launch the Chroma server with persistent storage
CMD ["chroma", "run", "--host", "0.0.0.0", "--port", "8000", "--path", "/chroma/chroma"]
