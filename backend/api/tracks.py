"""
Tracks API endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from backend.services.database import get_db
from backend.models.track import Track, TrackResponse, TrackUpdate
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/", response_model=List[TrackResponse])
async def get_tracks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = Query(None, description="Filter by status: pending, matched, tagged, error"),
    search: Optional[str] = Query(None, description="Search in filename or title")
):
    """Get all scanned tracks with optional filtering"""
    async with get_db() as db:
        query = select(Track)
        
        if status:
            query = query.where(Track.status == status)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                (Track.filename.ilike(search_term)) | 
                (Track.title.ilike(search_term)) |
                (Track.artist.ilike(search_term))
            )
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        tracks = result.scalars().all()
        
        return [TrackResponse.model_validate(t) for t in tracks]


@router.get("/stats")
async def get_track_stats():
    """Get statistics about scanned tracks"""
    async with get_db() as db:
        # Count by status
        from sqlalchemy import func
        
        total = await db.scalar(select(func.count(Track.id)))
        pending = await db.scalar(select(func.count(Track.id)).where(Track.status == "pending"))
        matched = await db.scalar(select(func.count(Track.id)).where(Track.status == "matched"))
        tagged = await db.scalar(select(func.count(Track.id)).where(Track.status == "tagged"))
        errors = await db.scalar(select(func.count(Track.id)).where(Track.status == "error"))
        
        return {
            "total": total or 0,
            "pending": pending or 0,
            "matched": matched or 0,
            "tagged": tagged or 0,
            "errors": errors or 0
        }


@router.get("/{track_id}", response_model=TrackResponse)
async def get_track(track_id: int):
    """Get a specific track by ID"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        return TrackResponse.model_validate(track)


@router.patch("/{track_id}", response_model=TrackResponse)
async def update_track(track_id: int, update: TrackUpdate):
    """Update track metadata"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Update fields
        update_data = update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(track, field, value)
        
        await db.commit()
        await db.refresh(track)
        
        return TrackResponse.model_validate(track)


@router.delete("/{track_id}")
async def delete_track(track_id: int):
    """Remove a track from the database (does not delete the file)"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        await db.delete(track)
        await db.commit()
        
        return {"message": "Track removed from database"}
