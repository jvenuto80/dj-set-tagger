"""
Directory scanner service - scans directories for audio files
"""
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from sqlalchemy import select
from backend.services.database import get_db
from backend.models.track import Track
from backend.config import settings
from loguru import logger

# Scan state
_scan_status = {
    "running": False,
    "progress": 0,
    "total": 0,
    "current_file": None,
    "files_found": 0,
    "files_added": 0,
    "files_skipped": 0,
    "files_filtered": 0,
    "errors": []
}
_scan_stop_flag = False


def get_min_duration_setting() -> int:
    """Get minimum duration setting from saved settings"""
    settings_file = os.path.join(settings.config_dir, "settings.json")
    if os.path.exists(settings_file):
        with open(settings_file, "r") as f:
            saved = json.load(f)
            return saved.get("min_duration_minutes", 0)
    return 0


def get_music_dirs() -> List[str]:
    """Get list of music directories from saved settings"""
    settings_file = os.path.join(settings.config_dir, "settings.json")
    if os.path.exists(settings_file):
        with open(settings_file, "r") as f:
            saved = json.load(f)
            music_dirs = saved.get("music_dirs", [])
            if music_dirs:
                return [d for d in music_dirs if d and os.path.exists(d)]
            # Fallback to single music_dir
            music_dir = saved.get("music_dir", settings.music_dir)
            if music_dir and os.path.exists(music_dir):
                return [music_dir]
    # Default
    if os.path.exists(settings.music_dir):
        return [settings.music_dir]
    return []


async def get_scan_status():
    """Get current scan status"""
    return _scan_status.copy()


async def stop_current_scan():
    """Signal scan to stop"""
    global _scan_stop_flag
    _scan_stop_flag = True


def get_audio_extensions():
    """Get list of audio file extensions to scan"""
    return [f".{ext}" for ext in settings.scan_extensions]


def extract_metadata_from_file(filepath: str) -> dict:
    """Extract metadata from audio file using mutagen"""
    metadata = {
        "title": None,
        "artist": None,
        "album": None,
        "genre": None,
        "year": None,
        "duration": None,
        "bitrate": None,
        "sample_rate": None,
        "file_format": None
    }
    
    try:
        audio = MutagenFile(filepath, easy=True)
        
        if audio is None:
            return metadata
        
        # Get format
        metadata["file_format"] = Path(filepath).suffix.lower().lstrip(".")
        
        # Get duration
        if hasattr(audio, "info") and hasattr(audio.info, "length"):
            metadata["duration"] = audio.info.length
        
        # Get bitrate
        if hasattr(audio, "info") and hasattr(audio.info, "bitrate"):
            metadata["bitrate"] = audio.info.bitrate
        
        # Get sample rate
        if hasattr(audio, "info") and hasattr(audio.info, "sample_rate"):
            metadata["sample_rate"] = audio.info.sample_rate
        
        # Try to get tags
        if audio is not None:
            metadata["title"] = audio.get("title", [None])[0]
            metadata["artist"] = audio.get("artist", [None])[0]
            metadata["album"] = audio.get("album", [None])[0]
            metadata["genre"] = audio.get("genre", [None])[0]
            metadata["year"] = audio.get("date", [None])[0] or audio.get("year", [None])[0]
            
    except Exception as e:
        logger.warning(f"Error extracting metadata from {filepath}: {e}")
    
    return metadata


def parse_filename_for_metadata(filename: str) -> dict:
    """Parse filename to extract potential metadata"""
    metadata = {
        "title": None,
        "artist": None
    }
    
    # Remove extension
    name = Path(filename).stem
    
    # Common DJ set filename patterns:
    # "Artist - Title"
    # "Artist @ Event"
    # "Artist - Event - Date"
    # "Artist - Mix Name"
    
    # Try splitting by " - "
    if " - " in name:
        parts = name.split(" - ", 1)
        metadata["artist"] = parts[0].strip()
        metadata["title"] = parts[1].strip() if len(parts) > 1 else None
    
    # Try splitting by " @ "
    elif " @ " in name:
        parts = name.split(" @ ", 1)
        metadata["artist"] = parts[0].strip()
        metadata["title"] = parts[1].strip() if len(parts) > 1 else None
    
    else:
        # Use whole filename as title
        metadata["title"] = name.strip()
    
    return metadata


async def scan_directory(directory: str = None):
    """Scan directory(ies) for audio files and add to database
    
    If directory is provided, scan only that directory.
    If directory is None, scan all configured music_dirs.
    """
    global _scan_status, _scan_stop_flag
    
    _scan_stop_flag = False
    _scan_status = {
        "running": True,
        "progress": 0,
        "total": 0,
        "current_file": None,
        "files_found": 0,
        "files_added": 0,
        "files_skipped": 0,
        "files_filtered": 0,
        "errors": []
    }
    
    # Determine directories to scan
    if directory:
        directories = [directory]
    else:
        directories = get_music_dirs()
    
    if not directories:
        logger.error("No valid music directories configured")
        _scan_status["errors"].append("No valid music directories configured")
        _scan_status["running"] = False
        return
    
    extensions = get_audio_extensions()
    audio_files: List[str] = []
    
    logger.info(f"Scanning directories: {directories}")
    logger.info(f"Looking for extensions: {extensions}")
    
    # First pass: find all audio files from all directories
    try:
        for scan_dir in directories:
            if _scan_stop_flag:
                break
            
            if not os.path.exists(scan_dir):
                logger.warning(f"Directory does not exist, skipping: {scan_dir}")
                continue
                
            logger.info(f"Scanning: {scan_dir}")
            for root, dirs, files in os.walk(scan_dir):
                if _scan_stop_flag:
                    break
                    
                for file in files:
                    if any(file.lower().endswith(ext) for ext in extensions):
                        audio_files.append(os.path.join(root, file))
        
        _scan_status["total"] = len(audio_files)
        _scan_status["files_found"] = len(audio_files)
        logger.info(f"Found {len(audio_files)} audio files across {len(directories)} directories")
        
    except Exception as e:
        logger.error(f"Error scanning directory: {e}")
        _scan_status["errors"].append(str(e))
        _scan_status["running"] = False
        return
    
    # Second pass: process files and add to database
    async with get_db() as db:
        for i, filepath in enumerate(audio_files):
            if _scan_stop_flag:
                logger.info("Scan stopped by user")
                break
            
            _scan_status["progress"] = i + 1
            _scan_status["current_file"] = os.path.basename(filepath)
            
            try:
                # Check if already in database
                existing = await db.execute(
                    select(Track).where(Track.filepath == filepath)
                )
                if existing.scalar_one_or_none():
                    _scan_status["files_skipped"] += 1
                    continue
                
                # Extract metadata
                metadata = extract_metadata_from_file(filepath)
                filename_meta = parse_filename_for_metadata(os.path.basename(filepath))
                
                # Prefer file metadata, fall back to filename parsing
                title = metadata["title"] or filename_meta["title"]
                artist = metadata["artist"] or filename_meta["artist"]
                
                # Check minimum duration filter
                min_duration = get_min_duration_setting()
                if min_duration > 0 and metadata["duration"]:
                    min_seconds = min_duration * 60
                    if metadata["duration"] < min_seconds:
                        _scan_status["files_filtered"] += 1
                        logger.debug(f"Skipping {filepath}: duration {metadata['duration']}s < {min_seconds}s minimum")
                        continue
                
                # Get file size
                file_size = os.path.getsize(filepath)
                
                # Create track record
                track = Track(
                    filepath=filepath,
                    filename=os.path.basename(filepath),
                    directory=os.path.dirname(filepath),
                    title=title,
                    artist=artist,
                    album=metadata["album"],
                    genre=metadata["genre"],
                    year=metadata["year"],
                    duration=metadata["duration"],
                    file_size=file_size,
                    file_format=metadata["file_format"],
                    bitrate=metadata["bitrate"],
                    sample_rate=metadata["sample_rate"],
                    status="pending"
                )
                
                db.add(track)
                _scan_status["files_added"] += 1
                
                # Commit in batches of 100
                if _scan_status["files_added"] % 100 == 0:
                    await db.commit()
                    logger.info(f"Processed {i + 1}/{len(audio_files)} files")
                
            except Exception as e:
                logger.error(f"Error processing {filepath}: {e}")
                _scan_status["errors"].append(f"{filepath}: {str(e)}")
        
        # Final commit
        await db.commit()
    
    _scan_status["running"] = False
    _scan_status["current_file"] = None
    
    logger.info(f"Scan complete. Added: {_scan_status['files_added']}, Skipped: {_scan_status['files_skipped']}, Filtered: {_scan_status['files_filtered']}")
