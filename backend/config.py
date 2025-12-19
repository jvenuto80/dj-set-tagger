"""
Application configuration settings
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Directory settings
    music_dir: str = os.environ.get("MUSIC_DIR", "/music")
    config_dir: str = os.environ.get("CONFIG_DIR", "/config")
    
    # Scan settings
    scan_extensions: List[str] = ["mp3", "flac", "wav", "m4a", "aac", "ogg"]
    
    # Database
    database_url: str = ""
    
    # 1001Tracklists settings
    tracklists_delay: float = 2.0  # Delay between requests to avoid rate limiting
    
    # Matching settings
    fuzzy_threshold: int = 70  # Minimum fuzzy match score (0-100)
    
    class Config:
        env_prefix = ""
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set database URL based on config dir
        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{self.config_dir}/dj_tagger.db"
        
        # Parse scan extensions if provided as comma-separated string
        ext_env = os.environ.get("SCAN_EXTENSIONS", "")
        if ext_env:
            self.scan_extensions = [e.strip().lower() for e in ext_env.split(",")]


settings = Settings()
