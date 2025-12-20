"""
Settings API endpoints
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from backend.config import settings
import json
import os
from loguru import logger

router = APIRouter()


class AppSettings(BaseModel):
    """Application settings model"""
    music_dir: str  # Legacy single directory (first in list)
    music_dirs: List[str]  # Multiple directories
    scan_extensions: List[str]
    fuzzy_threshold: int
    tracklists_delay: float
    min_duration_minutes: int


class SettingsUpdate(BaseModel):
    """Settings update model"""
    music_dir: str | None = None  # Legacy support
    music_dirs: List[str] | None = None  # Multiple directories
    scan_extensions: List[str] | None = None
    fuzzy_threshold: int | None = None
    tracklists_delay: float | None = None
    min_duration_minutes: int | None = None


def get_settings_file():
    """Get path to settings file"""
    return os.path.join(settings.config_dir, "settings.json")


def load_saved_settings() -> dict:
    """Load saved settings from file"""
    settings_file = get_settings_file()
    if os.path.exists(settings_file):
        with open(settings_file, "r") as f:
            return json.load(f)
    return {}


def save_settings(data: dict):
    """Save settings to file"""
    settings_file = get_settings_file()
    os.makedirs(os.path.dirname(settings_file), exist_ok=True)
    with open(settings_file, "w") as f:
        json.dump(data, f, indent=2)


@router.get("", response_model=AppSettings)
@router.get("/", response_model=AppSettings)
async def get_settings():
    """Get current application settings"""
    saved = load_saved_settings()
    
    # Handle music_dirs - migrate from music_dir if needed
    music_dirs = saved.get("music_dirs", [])
    if not music_dirs:
        # Migrate from single music_dir
        single_dir = saved.get("music_dir", settings.music_dir)
        music_dirs = [single_dir] if single_dir else []
    
    return AppSettings(
        music_dir=music_dirs[0] if music_dirs else settings.music_dir,
        music_dirs=music_dirs if music_dirs else [settings.music_dir],
        scan_extensions=saved.get("scan_extensions", settings.scan_extensions),
        fuzzy_threshold=saved.get("fuzzy_threshold", settings.fuzzy_threshold),
        tracklists_delay=saved.get("tracklists_delay", settings.tracklists_delay),
        min_duration_minutes=saved.get("min_duration_minutes", settings.min_duration_minutes)
    )


@router.patch("", response_model=AppSettings)
@router.patch("/", response_model=AppSettings)
async def update_settings(update: SettingsUpdate):
    """Update application settings"""
    current = load_saved_settings()
    
    update_data = update.model_dump(exclude_unset=True)
    
    # Handle music_dirs - validate all directories exist
    if "music_dirs" in update_data:
        invalid_dirs = [d for d in update_data["music_dirs"] if d and not os.path.exists(d)]
        if invalid_dirs:
            raise HTTPException(status_code=400, detail=f"Directories do not exist: {', '.join(invalid_dirs)}")
        # Keep music_dir in sync with first entry
        if update_data["music_dirs"]:
            update_data["music_dir"] = update_data["music_dirs"][0]
    
    # Legacy music_dir support
    if "music_dir" in update_data and "music_dirs" not in update_data:
        if update_data["music_dir"] and not os.path.exists(update_data["music_dir"]):
            raise HTTPException(status_code=400, detail="Music directory does not exist")
        # Update music_dirs to match
        current_dirs = current.get("music_dirs", [])
        if current_dirs:
            current_dirs[0] = update_data["music_dir"]
        else:
            current_dirs = [update_data["music_dir"]]
        update_data["music_dirs"] = current_dirs
    
    current.update(update_data)
    save_settings(current)
    logger.info(f"Settings updated: {update_data}")
    
    return await get_settings()


@router.get("/directories")
async def list_directories(path: str = "/"):
    """List directories for browsing"""
    try:
        entries = []
        for entry in os.scandir(path):
            if entry.is_dir() and not entry.name.startswith("."):
                entries.append({
                    "name": entry.name,
                    "path": entry.path
                })
        
        entries.sort(key=lambda x: x["name"].lower())
        
        return {
            "current": path,
            "parent": os.path.dirname(path) if path != "/" else None,
            "directories": entries
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Directory not found")
