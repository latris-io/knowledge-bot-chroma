FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# ✅ Use the full FastAPI server from Chroma
CMD ["uvicorn", "chromadb.server.fastapi_app:app", "--host", "0.0.0.0", "--port", "8000"]
