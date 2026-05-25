"""
API endpoints for audio fingerprinting and track identification.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import select
from loguru import logger
import asyncio

from backend.services.database import get_db
from backend.models.track import Track
from backend.services.fingerprint import (
    generate_fingerprint,
    fingerprint_to_hash,
    identify_with_acoustid_extended,
    find_duplicates_by_fingerprint,
    check_fpcalc_available
)
from backend.config import settings
from backend.api.settings import load_saved_settings

router = APIRouter(prefix="/fingerprint", tags=["fingerprint"])

# Global state for fingerprint generation with lock for thread safety
fingerprint_state_lock = asyncio.Lock()
fingerprint_state = {
    "is_running": False,
    "should_cancel": False,
    "processed": 0,
    "failed": 0,
    "total": 0
}


class IdentifyRequest(BaseModel):
    track_id: int


class IdentifyResponse(BaseModel):
    success: bool
    track_id: int
    result: Optional[dict] = None
    message: str


class FingerprintStatusResponse(BaseModel):
    fpcalc_available: bool
    acoustid_configured: bool
    total_tracks: int
    fingerprinted_tracks: int
    is_generating: bool = False
    generation_progress: Optional[dict] = None


class DuplicateGroup(BaseModel):
    fingerprint_hash: str
    tracks: List[dict]


class DuplicatesResponse(BaseModel):
    duplicate_groups: List[DuplicateGroup]
    total_duplicates: int


class GenerateFingerprintsResponse(BaseModel):
    success: bool
    processed: int
    failed: int
    message: str


@router.get("/status", response_model=FingerprintStatusResponse)
async def get_fingerprint_status():
    """Get fingerprinting system status."""
    from sqlalchemy import func
    
    fpcalc_ok = await check_fpcalc_available()
    saved = await load_saved_settings()
    acoustid_key = saved.get('acoustid_api_key', '')
    
    async with get_db() as db:
        total = await db.scalar(select(func.count(Track.id)))
        fingerprinted = await db.scalar(
            select(func.count(Track.id)).where(Track.fingerprint_hash.isnot(None))
        )
    
    progress = None
    async with fingerprint_state_lock:
        is_running = fingerprint_state["is_running"]
        if is_running:
            progress = {
                "processed": fingerprint_state["processed"],
                "failed": fingerprint_state["failed"],
                "total": fingerprint_state["total"]
            }
    
    return FingerprintStatusResponse(
        fpcalc_available=fpcalc_ok,
        acoustid_configured=bool(acoustid_key),
        total_tracks=total or 0,
        fingerprinted_tracks=fingerprinted or 0,
        is_generating=is_running,
        generation_progress=progress
    )


@router.post("/stop")
async def stop_fingerprint_generation():
    """Stop the running fingerprint generation process."""
    async with fingerprint_state_lock:
        if not fingerprint_state["is_running"]:
            return {"success": False, "message": "No fingerprint generation is running"}
        
        fingerprint_state["should_cancel"] = True
    logger.info("Fingerprint generation cancellation requested")
    return {"success": True, "message": "Cancellation requested"}


@router.post("/identify", response_model=IdentifyResponse)
async def identify_track(request: IdentifyRequest):
    """
    Identify a track using AcoustID audio fingerprinting.
    Returns metadata from MusicBrainz if a match is found.
    """
    saved = await load_saved_settings()
    acoustid_key = saved.get('acoustid_api_key', '')
    if not acoustid_key:
        raise HTTPException(
            status_code=400,
            detail="AcoustID API key not configured. Add it in Settings."
        )
    
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(Track.id == request.track_id)
        )
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Identify using AcoustID
        try:
            match_result = await identify_with_acoustid_extended(
                track.filepath,
                acoustid_key
            )
        except RuntimeError as e:
            # Surface specific, user-actionable errors (fpcalc missing, API error, etc.)
            raise HTTPException(status_code=500, detail=str(e))

        if match_result:
            return IdentifyResponse(
                success=True,
                track_id=track.id,
                result=match_result,
                message=f"Match found: {match_result.get('artist')} - {match_result.get('title')} (confidence: {match_result.get('score', 0):.0%})"
            )
        else:
            return IdentifyResponse(
                success=False,
                track_id=track.id,
                result=None,
                message="No match found in AcoustID database (low score or unknown recording)"
            )


@router.post("/identify/{track_id}/apply")
async def apply_identification(track_id: int, metadata: dict):
    """Apply identified metadata to a track."""
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(Track.id == track_id)
        )
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Update matched metadata
        if metadata.get('title'):
            track.matched_title = metadata['title']
        if metadata.get('artist'):
            track.matched_artist = metadata['artist']
        if metadata.get('album'):
            track.matched_album = metadata['album']
        if metadata.get('year'):
            track.matched_year = metadata['year']
        
        track.match_source = 'acoustid'
        track.match_confidence = metadata.get('score', 0) * 100
        track.status = 'matched'
        
        await db.commit()
        
        return {"success": True, "message": "Metadata applied"}


@router.post("/generate", response_model=GenerateFingerprintsResponse)
async def generate_fingerprints_endpoint(
    background_tasks: BackgroundTasks,
    overwrite: bool = False,
    workers: int = 4
):
    """
    Generate fingerprints for all tracks in the library.
    Dispatches the work to a background task and returns immediately.
    Poll /fingerprint/status for progress.

    Args:
        overwrite: Regenerate fingerprints even if they exist
        workers: Number of parallel workers (default 4, max 16)
    """
    global fingerprint_state

    # Check if already running
    async with fingerprint_state_lock:
        if fingerprint_state["is_running"]:
            raise HTTPException(
                status_code=409,
                detail="Fingerprint generation already in progress. Stop it first or wait for completion."
            )

    fpcalc_ok = await check_fpcalc_available()
    if not fpcalc_ok:
        raise HTTPException(
            status_code=500,
            detail="fpcalc (Chromaprint) not available. Install with: brew install chromaprint"
        )

    # Limit workers to reasonable range
    workers = max(1, min(workers, 16))

    # Count tracks that will be processed (without holding DB connection
    # for the long-running work)
    async with get_db() as db:
        if overwrite:
            count_result = await db.execute(select(Track))
        else:
            count_result = await db.execute(
                select(Track).where(Track.fingerprint_hash.is_(None))
            )
        track_count = len(count_result.scalars().all())

    if track_count == 0:
        return GenerateFingerprintsResponse(
            success=True,
            processed=0,
            failed=0,
            message="All tracks already have fingerprints"
        )

    # Mark as running before returning so clients see is_running=True immediately
    async with fingerprint_state_lock:
        fingerprint_state["is_running"] = True
        fingerprint_state["should_cancel"] = False
        fingerprint_state["processed"] = 0
        fingerprint_state["failed"] = 0
        fingerprint_state["total"] = track_count

    # Dispatch the actual work as a background task
    asyncio.create_task(_run_fingerprint_generation(overwrite=overwrite, workers=workers))

    return GenerateFingerprintsResponse(
        success=True,
        processed=0,
        failed=0,
        message=f"Started fingerprint generation for {track_count} tracks. Poll /fingerprint/status for progress."
    )


async def _run_fingerprint_generation(overwrite: bool, workers: int):
    """Background worker: generate fingerprints for all tracks needing them."""
    global fingerprint_state
    try:
        async with get_db() as db:
            if overwrite:
                result = await db.execute(select(Track))
            else:
                result = await db.execute(
                    select(Track).where(Track.fingerprint_hash.is_(None))
                )
            tracks = result.scalars().all()

            semaphore = asyncio.Semaphore(workers)

            async def process_track(track):
                if fingerprint_state["should_cancel"]:
                    return (track.id, None, None, "Cancelled")
                async with semaphore:
                    if fingerprint_state["should_cancel"]:
                        return (track.id, None, None, "Cancelled")
                    try:
                        fp_result = await generate_fingerprint(track.filepath)
                        if fp_result:
                            duration, fingerprint = fp_result
                            fingerprint_state["processed"] += 1
                            return (track.id, fingerprint_to_hash(fingerprint), fingerprint, None)
                        else:
                            fingerprint_state["failed"] += 1
                            return (track.id, None, None, "No fingerprint generated")
                    except Exception as e:
                        logger.error(f"Error fingerprinting {track.filepath}: {e}")
                        fingerprint_state["failed"] += 1
                        return (track.id, None, None, str(e))

            logger.info(f"Generating fingerprints for {len(tracks)} tracks using {workers} workers")
            results = await asyncio.gather(*[process_track(t) for t in tracks])

            processed = 0
            failed = 0
            cancelled = 0
            track_map = {t.id: t for t in tracks}

            for track_id, fp_hash, fp_raw, error in results:
                if error == "Cancelled":
                    cancelled += 1
                elif fp_hash:
                    track_map[track_id].fingerprint_hash = fp_hash
                    track_map[track_id].fingerprint_raw = fp_raw
                    processed += 1
                else:
                    failed += 1

            await db.commit()

            was_cancelled = fingerprint_state["should_cancel"]
            if was_cancelled:
                logger.info(
                    f"Fingerprint generation cancelled: {processed} processed, "
                    f"{failed} failed, {cancelled} skipped"
                )
            else:
                logger.info(
                    f"Fingerprint generation complete: {processed} processed, {failed} failed"
                )
    except Exception as e:
        logger.exception(f"Fingerprint generation crashed: {e}")
    finally:
        async with fingerprint_state_lock:
            fingerprint_state["is_running"] = False
            fingerprint_state["should_cancel"] = False


@router.get("/duplicates", response_model=DuplicatesResponse)
async def find_duplicates():
    """Find duplicate tracks based on audio fingerprint."""
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(Track.fingerprint_hash.isnot(None))
        )
        tracks = result.scalars().all()
        
        # Convert to dicts for the duplicate finder
        track_dicts = [
            {
                'id': t.id,
                'filename': t.filename,
                'filepath': t.filepath,
                'title': t.title,
                'artist': t.artist,
                'album': t.album,
                'duration': t.duration,
                'file_size': t.file_size,
                'fingerprint_hash': t.fingerprint_hash
            }
            for t in tracks
        ]
        
        duplicates = await find_duplicates_by_fingerprint(track_dicts)
        
        duplicate_groups = [
            DuplicateGroup(
                fingerprint_hash=group[0]['fingerprint_hash'],
                tracks=group
            )
            for group in duplicates
        ]
        
        total = sum(len(g.tracks) for g in duplicate_groups)
        
        return DuplicatesResponse(
            duplicate_groups=duplicate_groups,
            total_duplicates=total
        )


@router.post("/generate/{track_id}")
async def generate_single_fingerprint(track_id: int):
    """Generate fingerprint for a single track."""
    fpcalc_ok = await check_fpcalc_available()
    if not fpcalc_ok:
        raise HTTPException(
            status_code=500,
            detail="fpcalc (Chromaprint) not available"
        )
    
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(Track.id == track_id)
        )
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        fp_result = await generate_fingerprint(track.filepath)
        if fp_result:
            duration, fingerprint = fp_result
            track.fingerprint_hash = fingerprint_to_hash(fingerprint)
            track.fingerprint_raw = fingerprint
            await db.commit()
            
            return {
                "success": True,
                "fingerprint_hash": track.fingerprint_hash,
                "message": "Fingerprint generated"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate fingerprint"
            )
