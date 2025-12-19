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
    music_dir: str
    scan_extensions: List[str]
    fuzzy_threshold: int
    tracklists_delay: float


class SettingsUpdate(BaseModel):
    """Settings update model"""
    music_dir: str | None = None
    scan_extensions: List[str] | None = None
    fuzzy_threshold: int | None = None
    tracklists_delay: float | None = None


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


@router.get("/", response_model=AppSettings)
async def get_settings():
    """Get current application settings"""
    saved = load_saved_settings()
    
    return AppSettings(
        music_dir=saved.get("music_dir", settings.music_dir),
        scan_extensions=saved.get("scan_extensions", settings.scan_extensions),
        fuzzy_threshold=saved.get("fuzzy_threshold", settings.fuzzy_threshold),
        tracklists_delay=saved.get("tracklists_delay", settings.tracklists_delay)
    )


@router.patch("/", response_model=AppSettings)
async def update_settings(update: SettingsUpdate):
    """Update application settings"""
    current = load_saved_settings()
    
    update_data = update.model_dump(exclude_unset=True)
    current.update(update_data)
    
    # Validate music_dir exists
    if "music_dir" in update_data:
        if not os.path.exists(update_data["music_dir"]):
            raise HTTPException(status_code=400, detail="Music directory does not exist")
    
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
