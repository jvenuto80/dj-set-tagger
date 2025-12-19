"""
Tags API endpoints - for writing metadata to files
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from typing import List, Optional
from backend.services.tagger import tag_track, batch_tag_tracks, preview_tag_changes
from backend.services.database import get_db
from backend.models.track import Track, TagPreview
from sqlalchemy import select
from loguru import logger

router = APIRouter()


@router.post("/{track_id}/apply")
async def apply_tags(track_id: int):
    """Apply matched metadata to track file"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        if track.status != "matched":
            raise HTTPException(
                status_code=400, 
                detail="Track must be matched before tagging"
            )
        
        success = await tag_track(track_id)
        
        if success:
            return {"message": "Tags applied successfully", "track_id": track_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to apply tags")


@router.post("/batch/apply")
async def batch_apply_tags(
    background_tasks: BackgroundTasks,
    track_ids: Optional[List[int]] = None,
    apply_all_matched: bool = Query(False, description="Apply tags to all matched tracks")
):
    """Apply tags to multiple tracks"""
    # Run batch tagging in background
    background_tasks.add_task(batch_tag_tracks, track_ids, apply_all_matched)
    
    return {"message": "Batch tagging started"}


@router.get("/{track_id}/preview", response_model=TagPreview)
async def preview_tags(track_id: int):
    """Preview what tags would be written to a track"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        preview = await preview_tag_changes(track)
        return preview


@router.post("/{track_id}/rename")
async def rename_track(
    track_id: int,
    new_filename: str = Query(..., description="New filename (without extension)")
):
    """Rename a track file based on metadata"""
    from backend.services.tagger import rename_track_file
    
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        success, new_path = await rename_track_file(track, new_filename)
        
        if success:
            # Update database with new path
            track.filepath = new_path
            track.filename = new_filename
            await db.commit()
            
            return {"message": "Track renamed", "new_path": new_path}
        else:
            raise HTTPException(status_code=500, detail="Failed to rename track")


@router.post("/batch/rename")
async def batch_rename(
    background_tasks: BackgroundTasks,
    track_ids: Optional[List[int]] = None,
    pattern: str = Query(
        "{artist} - {title}",
        description="Rename pattern using placeholders: {artist}, {title}, {genre}, {year}"
    )
):
    """Rename multiple tracks using a pattern"""
    from backend.services.tagger import batch_rename_tracks
    
    background_tasks.add_task(batch_rename_tracks, track_ids, pattern)
    
    return {"message": "Batch rename started", "pattern": pattern}
