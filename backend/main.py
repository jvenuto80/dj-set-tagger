"""
SetList - FastAPI Backend
Main application entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from backend.api import tracks, scan, settings, match, tags, fingerprint, ai, covers, dedup, library, youtube
from backend.services.database import init_db
from backend.config import settings as app_settings
from loguru import logger
import sys

# Configure logging to file
LOG_FILE = os.path.join(app_settings.config_dir, "app.log")
os.makedirs(app_settings.config_dir, exist_ok=True)

# Remove default handler and add custom ones
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
logger.add(
    LOG_FILE,
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("Starting SetList...")
    
    # Initialize database
    await init_db()

    # Make sure the enrichment cache table exists (artist/track metadata cache)
    try:
        from backend.services.enrichment import ensure_cache_table
        await ensure_cache_table()
    except Exception as e:
        logger.warning(f"Enrichment cache init skipped: {e}")

    # Initialize AI classifier from saved settings
    try:
        from backend.services.ai_genre import init_genre_classifier_from_db
        await init_genre_classifier_from_db()
    except Exception as e:
        logger.warning(f"AI classifier init skipped: {e}")
    
    # Create directories if they don't exist
    os.makedirs(app_settings.config_dir, exist_ok=True)
    os.makedirs(app_settings.music_dir, exist_ok=True)
    
    logger.info(f"Music directory: {app_settings.music_dir}")
    logger.info(f"Config directory: {app_settings.config_dir}")
    
    yield
    
    logger.info("Shutting down SetList...")


app = FastAPI(
    title="SetList",
    description="Organize and tag your music library - DJ sets, podcasts, radio shows, and albums",
    version="1.4.0",
    lifespan=lifespan
)

# CORS middleware for frontend (loopback + Tauri webview only — never expose to the network)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "ALLOWED_ORIGINS",
        "http://127.0.0.1:5050,http://127.0.0.1:5173,http://127.0.0.1:8080,http://localhost:5050,http://localhost:5173,http://localhost:8080,tauri://localhost,https://tauri.localhost,http://tauri.localhost"
    ).split(","),
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
app.include_router(fingerprint.router, prefix="/api", tags=["fingerprint"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(covers.router, prefix="/api/covers", tags=["covers"])
app.include_router(dedup.router, prefix="/api/dedup", tags=["dedup"])
app.include_router(library.router, prefix="/api/library", tags=["library"])
app.include_router(youtube.router, prefix="/api/youtube", tags=["youtube"])


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.4.0",
        # Always native now (Docker mode was removed). Kept in the response for
        # backward compatibility with older frontends that still read this key.
        "native": True
    }


@app.get("/api")
async def api_root():
    """API root endpoint"""
    return {
        "message": "SetList API",
        "docs": "/docs",
        "version": "1.4.0"
    }

# In native mode, serve the frontend from the built dist directory
_frontend_dir = os.environ.get("SETLIST_SERVE_FRONTEND")
if _frontend_dir and os.path.isdir(_frontend_dir):
    from starlette.responses import FileResponse
    
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dir, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend SPA - catch-all for non-API routes"""
        file_path = os.path.join(_frontend_dir, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_frontend_dir, "index.html"))
