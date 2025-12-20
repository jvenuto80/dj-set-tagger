"""
Scan API endpoints
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from typing import Optional
from backend.services.scanner import scan_directory, get_scan_status, get_music_dirs
from backend.config import settings
from loguru import logger

router = APIRouter()


@router.post("/start")
async def start_scan(
    background_tasks: BackgroundTasks,
    directory: Optional[str] = Query(None, description="Directory to scan (defaults to all configured music dirs)")
):
    """Start scanning a directory for audio files"""
    if directory:
        scan_path = directory
        logger.info(f"Starting scan of single directory: {scan_path}")
    else:
        # Scan all configured directories
        music_dirs = get_music_dirs()
        scan_path = music_dirs if music_dirs else [settings.music_dir]
        logger.info(f"Starting scan of all configured directories: {scan_path}")
    
    # Add scan task to background - pass None to scan all dirs, or specific dir
    background_tasks.add_task(scan_directory, directory)
    
    return {
        "message": "Scan started",
        "directories": scan_path if isinstance(scan_path, list) else [scan_path]
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
