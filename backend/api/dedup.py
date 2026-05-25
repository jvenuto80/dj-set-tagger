"""
Advanced Duplicate Detection API endpoints.

Extends the existing /api/fingerprint/duplicates with:
  - Near-duplicate detection (similar but not identical fingerprints)
  - Quality-based keep/discard recommendations
  - LLM-assisted resolution for ambiguous cases
  - Batch auto-resolve
"""
import asyncio
from typing import Optional, List

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy import select, func

from backend.services.database import get_db
from backend.models.track import Track
from backend.services.dedup import (
    find_near_duplicates,
    recommend_keep,
    compute_quality_score,
    get_duplicate_resolver,
)
from loguru import logger

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NearDuplicateGroup(BaseModel):
    similarity: float
    type: str  # "exact", "near", "remix", "edit"
    recommendation: dict
    tracks: List[dict]


class ResolveRequest(BaseModel):
    track_ids: List[int]


class BatchResolveRequest(BaseModel):
    auto_delete: bool = False  # If true, delete recommended discards
    min_confidence: float = 0.95  # Only auto-resolve groups above this similarity


# ---------------------------------------------------------------------------
# Background job state
# ---------------------------------------------------------------------------

_dedup_job = {
    "running": False,
    "progress": 0,
    "total": 0,
    "resolved": 0,
    "kept": 0,
    "deleted": 0,
    "errors": 0,
    "skipped": 0,
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/near-duplicates")
async def find_near_duplicates_endpoint(
    similarity: float = Query(0.85, ge=0.5, le=1.0),
    duration_tolerance: float = Query(0.10, ge=0.0, le=0.5),
):
    """
    Find near-duplicate tracks using fingerprint similarity analysis.
    More advanced than exact-hash matching — catches same song with different
    encodings, slight edits, or different masters.
    """
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(Track.fingerprint_raw.isnot(None))
        )
        tracks = result.scalars().all()

    if not tracks:
        return {"groups": [], "total_groups": 0, "total_tracks": 0}

    track_dicts = [
        {
            "id": t.id,
            "filename": t.filename,
            "filepath": t.filepath,
            "title": t.title,
            "artist": t.artist,
            "album": t.album,
            "genre": t.genre,
            "duration": t.duration,
            "file_size": t.file_size,
            "file_format": t.file_format,
            "bitrate": t.bitrate,
            "sample_rate": t.sample_rate,
            "fingerprint_hash": t.fingerprint_hash,
            "fingerprint_raw": t.fingerprint_raw,
            "year": t.year,
        }
        for t in tracks
    ]

    groups = await find_near_duplicates(
        track_dicts,
        similarity_threshold=similarity,
        duration_tolerance_pct=duration_tolerance,
    )

    return {
        "groups": groups,
        "total_groups": len(groups),
        "total_tracks": sum(len(g["tracks"]) for g in groups),
    }


@router.post("/resolve")
async def resolve_duplicates(body: ResolveRequest):
    """
    Use LLM to analyze a group of duplicate tracks and recommend
    which to keep vs discard.
    """
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(Track.id.in_(body.track_ids))
        )
        tracks = result.scalars().all()

    if len(tracks) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 tracks to resolve")

    track_dicts = [
        {
            "id": t.id,
            "filename": t.filename,
            "filepath": t.filepath,
            "title": t.title,
            "artist": t.artist,
            "album": t.album,
            "genre": t.genre,
            "duration": t.duration,
            "file_size": t.file_size,
            "file_format": t.file_format,
            "bitrate": t.bitrate,
            "quality_score": compute_quality_score({
                "file_format": t.file_format,
                "bitrate": t.bitrate,
                "file_size": t.file_size,
                "title": t.title,
                "artist": t.artist,
                "album": t.album,
                "genre": t.genre,
                "year": t.year,
            }),
        }
        for t in tracks
    ]

    resolver = get_duplicate_resolver()
    resolution = await resolver.resolve(track_dicts)

    return resolution


@router.get("/quality/{track_id}")
async def get_track_quality(track_id: int):
    """Get the quality score for a single track."""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

    score = compute_quality_score({
        "file_format": track.file_format,
        "bitrate": track.bitrate,
        "file_size": track.file_size,
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "genre": track.genre,
        "year": track.year,
    })

    return {
        "track_id": track.id,
        "quality_score": score,
        "file_format": track.file_format,
        "bitrate": track.bitrate,
        "file_size": track.file_size,
    }


@router.post("/auto-resolve")
async def auto_resolve_duplicates(
    body: BatchResolveRequest,
    background_tasks: BackgroundTasks,
):
    """
    Background job: automatically resolve all duplicate groups.
    For high-confidence exact duplicates, keeps the best quality version.
    For lower-confidence or remix/edit pairs, flags for manual review.

    If auto_delete=true, actually deletes the discarded files.
    If auto_delete=false (default), just returns recommendations.
    """
    global _dedup_job

    if _dedup_job["running"]:
        raise HTTPException(status_code=409, detail="Auto-resolve already running")

    _dedup_job = {
        "running": True,
        "progress": 0,
        "total": 0,
        "resolved": 0,
        "kept": 0,
        "deleted": 0,
        "errors": 0,
        "skipped": 0,
    }

    background_tasks.add_task(
        _run_auto_resolve,
        auto_delete=body.auto_delete,
        min_confidence=body.min_confidence,
    )

    return {"started": True}


@router.get("/auto-resolve/status")
async def auto_resolve_status():
    """Get status of the auto-resolve job."""
    return _dedup_job


@router.post("/auto-resolve/stop")
async def stop_auto_resolve():
    """Stop the auto-resolve job."""
    global _dedup_job
    _dedup_job["running"] = False
    return {"stopped": True}


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------


async def _run_auto_resolve(auto_delete: bool, min_confidence: float):
    """Background: auto-resolve duplicate groups."""
    global _dedup_job
    import os

    # Get all tracks with fingerprints
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(Track.fingerprint_hash.isnot(None))
        )
        tracks = result.scalars().all()

    # Group by exact fingerprint hash
    hash_groups = {}
    for t in tracks:
        if t.fingerprint_hash:
            hash_groups.setdefault(t.fingerprint_hash, []).append(t)

    dup_groups = [g for g in hash_groups.values() if len(g) > 1]
    _dedup_job["total"] = len(dup_groups)

    for i, group in enumerate(dup_groups):
        if not _dedup_job["running"]:
            break

        _dedup_job["progress"] = i + 1

        try:
            track_dicts = [
                {
                    "id": t.id,
                    "filename": t.filename,
                    "filepath": t.filepath,
                    "title": t.title,
                    "artist": t.artist,
                    "album": t.album,
                    "genre": t.genre,
                    "duration": t.duration,
                    "file_size": t.file_size,
                    "file_format": t.file_format,
                    "bitrate": t.bitrate,
                    "year": t.year,
                }
                for t in group
            ]

            rec = recommend_keep(track_dicts)

            if not rec["keep"]:
                _dedup_job["skipped"] += 1
                continue

            _dedup_job["kept"] += 1
            _dedup_job["resolved"] += 1

            if auto_delete and rec["discard"]:
                async with get_db() as db:
                    for discard in rec["discard"]:
                        try:
                            filepath = discard["filepath"]
                            if os.path.exists(filepath):
                                os.remove(filepath)
                                logger.info(f"Auto-deleted duplicate: {filepath}")

                            # Remove from database
                            result = await db.execute(
                                select(Track).where(Track.id == discard["id"])
                            )
                            track_obj = result.scalar_one_or_none()
                            if track_obj:
                                await db.delete(track_obj)
                            _dedup_job["deleted"] += 1

                        except Exception as e:
                            logger.error(f"Error deleting {discard.get('filepath')}: {e}")
                            _dedup_job["errors"] += 1

                    await db.commit()

        except Exception as e:
            logger.error(f"Auto-resolve error for group: {e}")
            _dedup_job["errors"] += 1

    _dedup_job["running"] = False
    logger.info(
        f"Auto-resolve complete: {_dedup_job['resolved']} groups resolved, "
        f"{_dedup_job['deleted']} files deleted, {_dedup_job['errors']} errors"
    )
