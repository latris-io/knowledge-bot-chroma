FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# ✅ This is the correct way to launch the Chroma server
CMD ["chromadb", "run", "--host", "0.0.0.0", "--port", "8000"]
