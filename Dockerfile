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

# Create startup script for better initialization
COPY startup.sh /startup.sh
RUN chmod +x /startup.sh

# ✅ Launch the Chroma server with delayed startup for proper initialization
CMD ["/startup.sh"]
