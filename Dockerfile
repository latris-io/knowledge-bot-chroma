FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Default port Render exposes (even if you set ENV)
EXPOSE 8000

CMD ["python", "-m", "chromadb.cli", "start", "--host", "0.0.0.0", "--port", "8000"]
