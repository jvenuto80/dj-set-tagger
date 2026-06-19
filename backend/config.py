"""
Application configuration settings
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import os


def normalize_scan_extensions(value, *, allow_none: bool = False):
    """Normalize extension values to lowercase non-empty strings."""
    if value is None:
        if allow_none:
            return None
        raise ValueError("scan_extensions cannot be None")

    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError("scan_extensions must be a list or comma-separated string")

    normalized = []
    for item in items:
        cleaned = str(item).strip().lower().lstrip(".")
        if not cleaned:
            continue
        normalized.append(cleaned)

    if not normalized:
        raise ValueError("scan_extensions must include at least one extension")

    return normalized


def validate_fuzzy_threshold(value: int) -> int:
    if not 0 <= value <= 100:
        raise ValueError("fuzzy_threshold must be between 0 and 100")
    return value


def validate_tracklists_delay(value: float) -> float:
    if value < 0:
        raise ValueError("tracklists_delay must be >= 0")
    return value


def validate_min_duration_minutes(value: int) -> int:
    if value < 0:
        raise ValueError("min_duration_minutes must be >= 0")
    return value


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Directory settings (defaults to native paths under the user's home dir)
    music_dir: str = os.environ.get("MUSIC_DIR", os.path.expanduser("~/Music"))
    config_dir: str = os.environ.get("CONFIG_DIR", os.path.expanduser("~/.setlist"))
    
    # Scan settings
    scan_extensions: List[str] = ["mp3", "flac", "wav", "m4a", "aac", "ogg"]
    
    # Database
    database_url: str = ""
    
    # 1001Tracklists settings
    tracklists_delay: float = 2.0  # Delay between requests to avoid rate limiting
    
    # Matching settings
    fuzzy_threshold: int = 50  # Minimum fuzzy match score (0-100)
    
    # Filter settings
    min_duration_minutes: int = 0  # Minimum track duration in minutes (0 = no filter)
    
    # AcoustID API key for audio fingerprint identification
    acoustid_api_key: str = ""

    @field_validator("scan_extensions", mode="before")
    @classmethod
    def _validate_scan_extensions(cls, value):
        return normalize_scan_extensions(value)

    @field_validator("fuzzy_threshold")
    @classmethod
    def _validate_fuzzy_threshold(cls, value: int) -> int:
        return validate_fuzzy_threshold(value)

    @field_validator("tracklists_delay")
    @classmethod
    def _validate_tracklists_delay(cls, value: float) -> float:
        return validate_tracklists_delay(value)

    @field_validator("min_duration_minutes")
    @classmethod
    def _validate_min_duration_minutes(cls, value: int) -> int:
        return validate_min_duration_minutes(value)
    
    class Config:
        env_prefix = ""
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set database URL based on config dir
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{self.config_dir}/dj_tagger.db"


settings = Settings()
