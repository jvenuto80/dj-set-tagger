"""
Library Scan Review API — scan library with AI, preview suggestions,
approve/reject with checkboxes, then apply.
Also includes FLAC-to-MP3 conversion endpoints.
"""
import asyncio
from typing import Optional, List

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy import select

from backend.services.database import get_db
from backend.models.track import Track
from backend.services.library_scan import (
    run_library_scan,
    get_scan_session,
    get_suggestions,
    update_selection,
    select_all,
    apply_approved_suggestions,
    reject_suggestions,
    stop_scan,
)
from backend.services.converter import (
    check_ffmpeg_available,
    convert_to_mp3,
    batch_convert_to_mp3,
    get_convert_status,
    stop_conversion,
)
from loguru import logger

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    track_ids: Optional[List[int]] = None  # None = full library
    classify_genre: bool = True
    check_covers: bool = True
    force_reclassify: bool = False  # Re-run AI even on tracks with cached results


class SelectionUpdate(BaseModel):
    track_ids: List[int]
    selected: bool


class SelectAllUpdate(BaseModel):
    selected: bool


class RejectRequest(BaseModel):
    track_ids: List[int]


class ConvertRequest(BaseModel):
    track_ids: Optional[List[int]] = None  # None = all non-MP3 tracks in library
    bitrate: int = 320
    replace_original: bool = False


# ---------------------------------------------------------------------------
# Library Scan Review endpoints
# ---------------------------------------------------------------------------


@router.post("/scan")
async def start_library_scan(body: ScanRequest, background_tasks: BackgroundTasks):
    """
    Start an AI-powered library scan. Generates suggestions but does NOT
    modify any files. User must review and approve changes.
    """
    session = get_scan_session()
    if session["running"]:
        raise HTTPException(status_code=409, detail="Scan already running")

    background_tasks.add_task(
        run_library_scan,
        track_ids=body.track_ids,
        classify_genre=body.classify_genre,
        check_covers=body.check_covers,
        force_reclassify=body.force_reclassify,
    )

    return {"started": True, "track_count": len(body.track_ids) if body.track_ids else "all"}


@router.get("/scan/status")
async def scan_status():
    """Get the current scan session status."""
    return get_scan_session()


@router.post("/scan/stop")
async def stop_library_scan():
    """Stop the running library scan."""
    stop_scan()
    return {"stopped": True}


@router.get("/suggestions")
async def list_suggestions(
    status: Optional[str] = Query(None, regex="^(pending|approved|rejected|applied|error)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get paginated list of suggestions from the last scan.
    Each suggestion shows what would change and lets the user accept/reject.
    """
    return get_suggestions(status_filter=status, offset=offset, limit=limit)


@router.post("/suggestions/select")
async def update_suggestion_selection(body: SelectionUpdate):
    """Toggle the selected (checkbox) state for specific track suggestions."""
    update_selection(body.track_ids, body.selected)
    return {"updated": len(body.track_ids), "selected": body.selected}


@router.post("/suggestions/select-all")
async def select_all_suggestions(body: SelectAllUpdate):
    """Select or deselect all suggestions."""
    select_all(body.selected)
    return {"selected": body.selected}


@router.post("/suggestions/reject")
async def reject_track_suggestions(body: RejectRequest):
    """Mark specific suggestions as rejected (won't be applied)."""
    await reject_suggestions(body.track_ids)
    return {"rejected": len(body.track_ids)}


@router.post("/suggestions/apply")
async def apply_suggestions():
    """
    Apply all selected+pending suggestions to the actual audio files.
    Only runs after user review and approval.
    """
    session = get_scan_session()
    if session["running"]:
        raise HTTPException(status_code=409, detail="Scan still running, wait for completion")

    result = await apply_approved_suggestions()
    return result


# ---------------------------------------------------------------------------
# Conversion endpoints
# ---------------------------------------------------------------------------


@router.get("/convert/status")
async def conversion_status():
    """Check ffmpeg availability and get batch conversion status."""
    ffmpeg_ok = await check_ffmpeg_available()
    job = get_convert_status()
    return {
        "ffmpeg_available": ffmpeg_ok,
        **job,
    }


@router.post("/convert/to-mp3")
async def convert_tracks_to_mp3(
    body: ConvertRequest,
    background_tasks: BackgroundTasks,
):
    """
    Convert selected tracks (FLAC, WAV, etc.) to MP3.
    Preserves all tags and cover art.
    """
    ffmpeg_ok = await check_ffmpeg_available()
    if not ffmpeg_ok:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg not found. Install via: brew install ffmpeg",
        )

    job = get_convert_status()
    if job["running"]:
        raise HTTPException(status_code=409, detail="Conversion already running")

    # Get file paths for the requested track IDs (or all non-MP3 tracks if None)
    async with get_db() as db:
        if body.track_ids:
            result = await db.execute(
                select(Track).where(Track.id.in_(body.track_ids))
            )
        else:
            result = await db.execute(select(Track))
        tracks = result.scalars().all()

    # Only convert non-MP3 files
    to_convert = [
        t.filepath for t in tracks
        if t.file_format and t.file_format.lower() != "mp3"
    ]

    if not to_convert:
        return {"started": False, "message": "No non-MP3 tracks to convert"}

    background_tasks.add_task(
        batch_convert_to_mp3,
        filepaths=to_convert,
        bitrate=body.bitrate,
        replace_original=body.replace_original,
    )

    return {
        "started": True,
        "converting": len(to_convert),
        "skipped_mp3": len(tracks) - len(to_convert),
        "bitrate": body.bitrate,
        "replace_original": body.replace_original,
    }


@router.post("/convert/stop")
async def stop_batch_conversion():
    """Stop the running batch conversion."""
    stop_conversion()
    return {"stopped": True}
