from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from chromadb import PersistentClient
from chromadb.config import Settings
import os

app = FastAPI()
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_store")

client = PersistentClient(path=CHROMA_DIR)

@app.get("/")
def health_check():
    return {"status": "chroma server is running"}

# Future: Add /add, /query, /delete endpoints here
