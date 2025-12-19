"""
DJ Set Tagger - FastAPI Backend
Main application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from backend.api import tracks, scan, settings, match, tags
from backend.services.database import init_db
from backend.config import settings as app_settings
from loguru import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting DJ Set Tagger...")
    
    # Initialize database
    await init_db()
    
    # Create directories if they don't exist
    os.makedirs(app_settings.config_dir, exist_ok=True)
    os.makedirs(app_settings.music_dir, exist_ok=True)
    
    logger.info(f"Music directory: {app_settings.music_dir}")
    logger.info(f"Config directory: {app_settings.config_dir}")
    
    yield
    
    logger.info("Shutting down DJ Set Tagger...")


app = FastAPI(
    title="DJ Set Tagger",
    description="Scan and tag DJ sets using 1001Tracklists metadata",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(tracks.router, prefix="/api/tracks", tags=["tracks"])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
app.include_router(match.router, prefix="/api/match", tags=["match"])
app.include_router(tags.router, prefix="/api/tags", tags=["tags"])
app.include_router(settings.router, prefix="/api/settings", tags=["settings"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {
        "message": "DJ Set Tagger API",
        "docs": "/docs",
        "version": "1.0.0"
    }
