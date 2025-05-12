FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# ✅ Use the full Chroma FastAPI server
CMD ["uvicorn", "chromadb.server.fastapi_app:app", "--host", "0.0.0.0", "--port", "8000"]
