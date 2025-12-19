"""
Scan API endpoints
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from typing import Optional
from backend.services.scanner import scan_directory, get_scan_status
from backend.config import settings
from loguru import logger

router = APIRouter()


@router.post("/start")
async def start_scan(
    background_tasks: BackgroundTasks,
    directory: Optional[str] = Query(None, description="Directory to scan (defaults to MUSIC_DIR)")
):
    """Start scanning a directory for audio files"""
    scan_path = directory or settings.music_dir
    
    logger.info(f"Starting scan of {scan_path}")
    
    # Add scan task to background
    background_tasks.add_task(scan_directory, scan_path)
    
    return {
        "message": "Scan started",
        "directory": scan_path
    }


@router.get("/status")
async def scan_status():
    """Get the current scan status"""
    status = await get_scan_status()
    return status


@router.post("/stop")
async def stop_scan():
    """Stop the current scan"""
    from backend.services.scanner import stop_current_scan
    await stop_current_scan()
    return {"message": "Scan stop requested"}
