"""
Track database model and Pydantic schemas
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any
from backend.services.database import Base


class Track(Base):
    """SQLAlchemy model for audio tracks"""
    __tablename__ = "tracks"
    
    id = Column(Integer, primary_key=True, index=True)
    filepath = Column(String, unique=True, nullable=False)
    filename = Column(String, nullable=False)
    directory = Column(String, nullable=False)
    
    # Current metadata (from file)
    title = Column(String, nullable=True)
    artist = Column(String, nullable=True)
    album = Column(String, nullable=True)
    album_artist = Column(String, nullable=True)
    genre = Column(String, nullable=True)
    year = Column(String, nullable=True)
    duration = Column(Float, nullable=True)  # in seconds
    
    # File info
    file_size = Column(Integer, nullable=True)  # in bytes
    file_format = Column(String, nullable=True)  # mp3, flac, etc.
    bitrate = Column(Integer, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    
    # Matched metadata (from tracklist search)
    matched_title = Column(String, nullable=True)
    matched_artist = Column(String, nullable=True)
    matched_album = Column(String, nullable=True)
    matched_album_artist = Column(String, nullable=True)
    matched_genre = Column(String, nullable=True)
    matched_year = Column(String, nullable=True)
    matched_cover_url = Column(String, nullable=True)
    matched_tracklist_url = Column(String, nullable=True)
    matched_dj = Column(String, nullable=True)
    matched_event = Column(String, nullable=True)
    match_confidence = Column(Float, nullable=True)  # 0-100
    match_source = Column(String, nullable=True)  # "google", "1001tracklists", etc.
    
    # Status tracking
    status = Column(String, default="pending")  # pending, matched, tagged, error
    error_message = Column(Text, nullable=True)
    series_tagged = Column(Boolean, default=False)  # True if tagged via Series page
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tagged_at = Column(DateTime, nullable=True)
    
    # Relationships
    match_candidates = relationship("MatchCandidate", back_populates="track", cascade="all, delete-orphan")


class MatchCandidate(Base):
    """SQLAlchemy model for match candidates from tracklist search"""
    __tablename__ = "match_candidates"
    
    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, ForeignKey("tracks.id"), nullable=False)
    
    # Match info
    title = Column(String, nullable=False)
    artist = Column(String, nullable=True)
    genre = Column(String, nullable=True)
    cover_url = Column(String, nullable=True)
    tracklist_url = Column(String, nullable=True)
    tracklist_id = Column(String, nullable=True)
    dj = Column(String, nullable=True)
    event = Column(String, nullable=True)
    date_recorded = Column(String, nullable=True)
    source = Column(String, nullable=True)  # "google", "1001tracklists", "mixesdb", etc.
    
    # Extracted tracks from this tracklist (stored as JSON)
    extracted_tracks = Column(JSON, nullable=True)  # List of {position, artist, title, time}
    num_tracks = Column(Integer, nullable=True)
    
    # Confidence score
    confidence = Column(Float, nullable=False)  # 0-100
    match_type = Column(String, nullable=True)  # "google_search", "1001tracklists_direct", etc.
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    track = relationship("Track", back_populates="match_candidates")


# Pydantic schemas for API

class TrackBase(BaseModel):
    """Base track schema"""
    filepath: str
    filename: str
    directory: str


class TrackResponse(BaseModel):
    """Track response schema"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    filepath: str
    filename: str
    directory: str
    
    # Current metadata
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[str] = None
    duration: Optional[float] = None
    
    # File info
    file_size: Optional[int] = None
    file_format: Optional[str] = None
    bitrate: Optional[int] = None
    
    # Matched metadata
    matched_title: Optional[str] = None
    matched_artist: Optional[str] = None
    matched_album: Optional[str] = None
    matched_album_artist: Optional[str] = None
    matched_genre: Optional[str] = None
    matched_year: Optional[str] = None
    matched_cover_url: Optional[str] = None
    matched_tracklist_url: Optional[str] = None
    matched_dj: Optional[str] = None
    matched_event: Optional[str] = None
    match_confidence: Optional[float] = None
    
    # Status
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    tagged_at: Optional[datetime] = None


class TrackUpdate(BaseModel):
    """Track update schema"""
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[str] = None
    matched_title: Optional[str] = None
    matched_artist: Optional[str] = None
    matched_album: Optional[str] = None
    matched_album_artist: Optional[str] = None
    matched_genre: Optional[str] = None
    matched_year: Optional[str] = None
    matched_cover_url: Optional[str] = None
    status: Optional[str] = None


class MatchResult(BaseModel):
    """Match result schema"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    track_id: int
    title: str
    artist: Optional[str] = None
    genre: Optional[str] = None
    cover_url: Optional[str] = None
    tracklist_url: Optional[str] = None
    dj: Optional[str] = None
    event: Optional[str] = None
    date_recorded: Optional[str] = None
    source: Optional[str] = None
    extracted_tracks: Optional[List[Any]] = None
    num_tracks: Optional[int] = None
    confidence: float
    match_type: Optional[str] = None


class TagPreview(BaseModel):
    """Preview of tag changes"""
    track_id: int
    filename: str
    
    current_tags: dict
    new_tags: dict
    changes: List[dict]  # List of {field, old_value, new_value}
