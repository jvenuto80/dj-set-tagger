"""
Match API endpoints - for finding track matches on 1001Tracklists
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from typing import List, Optional
from backend.services.matcher import find_matches, batch_match_tracks
from backend.services.database import get_db
from backend.models.track import Track, MatchResult
from sqlalchemy import select
from loguru import logger

router = APIRouter()


@router.post("/{track_id}")
async def match_track(
    track_id: int,
    background_tasks: BackgroundTasks
):
    """Find matches for a specific track"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Run matching in background
        background_tasks.add_task(find_matches, track_id)
        
        return {"message": "Matching started", "track_id": track_id}


@router.post("/batch")
async def batch_match(
    background_tasks: BackgroundTasks,
    track_ids: Optional[List[int]] = None,
    status_filter: Optional[str] = Query(None, description="Match all tracks with this status")
):
    """Match multiple tracks at once"""
    # Run batch matching in background
    background_tasks.add_task(batch_match_tracks, track_ids, status_filter)
    
    return {"message": "Batch matching started"}


@router.get("/{track_id}/results", response_model=List[MatchResult])
async def get_match_results(track_id: int):
    """Get match results for a track"""
    async with get_db() as db:
        from backend.models.track import MatchCandidate
        
        result = await db.execute(
            select(MatchCandidate)
            .where(MatchCandidate.track_id == track_id)
            .order_by(MatchCandidate.confidence.desc())
        )
        matches = result.scalars().all()
        
        return [MatchResult.model_validate(m) for m in matches]


@router.post("/{track_id}/select/{match_id}")
async def select_match(track_id: int, match_id: int):
    """Select a specific match result for a track"""
    async with get_db() as db:
        from backend.models.track import MatchCandidate
        
        # Get the track
        track_result = await db.execute(select(Track).where(Track.id == track_id))
        track = track_result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Get the match
        match_result = await db.execute(
            select(MatchCandidate)
            .where(MatchCandidate.id == match_id)
            .where(MatchCandidate.track_id == track_id)
        )
        match = match_result.scalar_one_or_none()
        
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")
        
        # Update track with match data
        track.matched_title = match.title
        track.matched_artist = match.artist
        track.matched_genre = match.genre
        track.matched_cover_url = match.cover_url
        track.matched_tracklist_url = match.tracklist_url
        track.match_confidence = match.confidence
        track.status = "matched"
        
        await db.commit()
        
        return {"message": "Match selected", "track_id": track_id}


@router.post("/search")
async def search_tracklists(query: str):
    """Search 1001Tracklists directly"""
    from backend.services.tracklists_api import search_1001tracklists
    
    results = await search_1001tracklists(query)
    return {"results": results}
