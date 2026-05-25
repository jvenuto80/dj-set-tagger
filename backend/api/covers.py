"""
Cover Art API endpoints — multi-source search, quality assessment, embedded art info.
"""
import asyncio
import base64
from typing import Optional, List

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, update

from backend.services.database import get_db
from backend.models.track import Track
from backend.services.cover_art import (
    get_cover_search,
    extract_embedded_cover,
    cover_art_quality_score,
)
from backend.services.ai_cover import get_cover_assessor
from loguru import logger

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CoverSearchRequest(BaseModel):
    artist: Optional[str] = ""
    title: Optional[str] = ""
    album: Optional[str] = ""
    query: Optional[str] = ""


class CoverAssessResult(BaseModel):
    track_id: int
    has_cover: bool
    resolution: Optional[str] = None
    size_kb: int = 0
    heuristic_score: int = 0
    heuristic_issues: List[str] = []
    ai_score: Optional[int] = None
    ai_valid: Optional[bool] = None
    ai_matches: Optional[bool] = None
    ai_issues: List[str] = []
    ai_description: Optional[str] = None


# ---------------------------------------------------------------------------
# Background job state for batch cover fix
# ---------------------------------------------------------------------------

_cover_job = {
    "running": False,
    "progress": 0,
    "total": 0,
    "fixed": 0,
    "skipped": 0,
    "errors": 0,
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/search")
async def search_covers(
    artist: str = Query(""),
    title: str = Query(""),
    album: str = Query(""),
    query: str = Query(""),
    max_results: int = Query(20, ge=1, le=50),
):
    """
    Search all cover art sources (MusicBrainz, iTunes, Discogs) in parallel.
    """
    searcher = get_cover_search()
    covers = await searcher.search(
        artist=artist,
        title=title,
        album=album,
        query=query,
        max_results=max_results,
    )
    return covers


@router.get("/search/{track_id}")
async def search_covers_for_track(track_id: int, query: Optional[str] = None):
    """
    Search cover art for a specific track, using its metadata as the query.
    """
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

    artist = track.artist or track.matched_artist or ""
    title = track.title or track.matched_title or ""
    album = track.album or track.matched_album or ""

    searcher = get_cover_search()
    covers = await searcher.search(
        artist=artist,
        title=title,
        album=album,
        query=query or "",
    )
    return covers


@router.get("/embedded/{track_id}")
async def get_embedded_cover(track_id: int):
    """
    Get info about the cover art currently embedded in the audio file.
    Returns metadata only (not the image data) to keep response small.
    """
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

    info = await asyncio.to_thread(extract_embedded_cover, track.filepath)
    if not info:
        return {"has_cover": False, "resolution": None, "size_kb": 0, "mime": None}

    return {
        "has_cover": True,
        "resolution": f"{info['width']}x{info['height']}",
        "width": info["width"],
        "height": info["height"],
        "size_kb": info["size"] // 1024,
        "mime": info["mime"],
    }


@router.get("/embedded/{track_id}/image")
async def get_embedded_cover_image(track_id: int):
    """
    Return the actual embedded cover art image bytes.
    """
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

    info = await asyncio.to_thread(extract_embedded_cover, track.filepath)
    if not info:
        raise HTTPException(status_code=404, detail="No cover art embedded")

    return Response(
        content=info["data"],
        media_type=info.get("mime", "image/jpeg"),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/assess/{track_id}", response_model=CoverAssessResult)
async def assess_cover(track_id: int, use_ai: bool = Query(True)):
    """
    Assess cover art quality for a track.

    Performs a fast heuristic check (resolution, file size, aspect ratio).
    If use_ai=true AND a vision model is available, also runs AI assessment.
    """
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

    # Extract embedded cover
    info = await asyncio.to_thread(extract_embedded_cover, track.filepath)
    heuristic = cover_art_quality_score(info)

    result_data = CoverAssessResult(
        track_id=track.id,
        has_cover=info is not None,
        resolution=heuristic.get("resolution"),
        size_kb=heuristic.get("size_kb", 0),
        heuristic_score=heuristic.get("score", 0),
        heuristic_issues=heuristic.get("issues", []),
    )

    # AI assessment if requested and cover exists
    if use_ai and info and info.get("data"):
        assessor = get_cover_assessor()
        status = await assessor.check_status()
        if status.get("available"):
            ai_result = await assessor.assess(
                image_data=info["data"],
                title=track.title or track.matched_title or "",
                artist=track.artist or track.matched_artist or "",
                album=track.album or track.matched_album or "",
                genre=track.genre or track.matched_genre or "",
            )
            result_data.ai_score = ai_result.get("quality_score")
            result_data.ai_valid = ai_result.get("is_valid_cover")
            result_data.ai_matches = ai_result.get("matches_metadata")
            result_data.ai_issues = ai_result.get("issues", [])
            result_data.ai_description = ai_result.get("description")

    return result_data


@router.post("/fix-batch")
async def fix_batch_covers(background_tasks: BackgroundTasks):
    """
    Background job: find all tracks with missing or low-quality covers,
    search for better ones, and update matched_cover_url.
    """
    global _cover_job

    if _cover_job["running"]:
        raise HTTPException(status_code=409, detail="Cover fix job already running")

    _cover_job = {
        "running": True,
        "progress": 0,
        "total": 0,
        "fixed": 0,
        "skipped": 0,
        "errors": 0,
    }

    background_tasks.add_task(_run_batch_cover_fix)
    return {"started": True}


@router.get("/fix-batch/status")
async def fix_batch_status():
    """Get status of the batch cover fix job."""
    return _cover_job


@router.post("/fix-batch/stop")
async def stop_fix_batch():
    """Stop the batch cover fix job."""
    global _cover_job
    _cover_job["running"] = False
    return {"stopped": True}


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------


async def _run_batch_cover_fix():
    """Find tracks with missing/bad covers and search for replacements."""
    global _cover_job

    # Get all tracks
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(
                Track.status.in_(["pending", "matched", "tagged"])
            )
        )
        tracks = result.scalars().all()

    _cover_job["total"] = len(tracks)
    searcher = get_cover_search()

    for i, track in enumerate(tracks):
        if not _cover_job["running"]:
            break

        _cover_job["progress"] = i + 1

        try:
            # Check if track already has a good cover URL
            if track.matched_cover_url:
                _cover_job["skipped"] += 1
                continue

            # Check embedded cover quality
            info = await asyncio.to_thread(extract_embedded_cover, track.filepath)
            heuristic = cover_art_quality_score(info)

            # Skip if existing cover is good enough (score >= 70)
            if info and heuristic.get("score", 0) >= 70:
                _cover_job["skipped"] += 1
                continue

            # Search for cover art
            artist = track.artist or track.matched_artist or ""
            title = track.title or track.matched_title or ""
            album = track.album or track.matched_album or ""

            if not artist and not title and not album:
                _cover_job["skipped"] += 1
                continue

            covers = await searcher.search(
                artist=artist,
                title=title,
                album=album,
                max_results=1,
            )

            if covers:
                async with get_db() as db:
                    await db.execute(
                        update(Track)
                        .where(Track.id == track.id)
                        .values(matched_cover_url=covers[0]["url"])
                    )
                    await db.commit()
                _cover_job["fixed"] += 1
            else:
                _cover_job["skipped"] += 1

            # Rate limit
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Cover fix error for track {track.id}: {e}")
            _cover_job["errors"] += 1

    _cover_job["running"] = False
    logger.info(
        f"Batch cover fix complete: {_cover_job['fixed']} fixed, "
        f"{_cover_job['skipped']} skipped, {_cover_job['errors']} errors"
    )
