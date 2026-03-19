from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import logging
from loguru import logger
import os

from config import settings
from database import create_tables
from routers import users, documents, chat, projects

# Configure logging
logging.basicConfig(level=logging.INFO)
logger.add("logs/app.log", rotation="10 MB", retention="1 week")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting ChatIA application")
    await create_tables()
    yield
    # Shutdown
    logger.info("Shutting down ChatIA application")

app = FastAPI(
    title="ChatIA - PDF RAG Chat Application",
    description="Multi-user PDF document Q&A with RAG and MemoRAG",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
if os.path.exists("uploads"):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Routers
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
