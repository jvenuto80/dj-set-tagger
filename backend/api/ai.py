"""
AI API endpoints — genre classification, metadata suggestions, Ollama management.
"""
import asyncio
from typing import Optional, List

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, update

from backend.services.database import get_db
from backend.models.track import Track
from backend.services.ai_genre import (
    get_genre_classifier,
    update_classifier_settings,
    list_available_models,
    unload_current_model,
)
from backend.services.mik import read_mik_tags
from loguru import logger

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class GenreResult(BaseModel):
    track_id: int
    genres: List[str]
    confidence: int
    reasoning: str
    mik_key: Optional[str] = None
    error: Optional[str] = None


class BatchGenreRequest(BaseModel):
    track_ids: List[int]


class OllamaSettings(BaseModel):
    model: Optional[str] = None
    host: Optional[str] = None
    reasoning_model: Optional[str] = None
    two_pass_enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# Background job state for batch classification
# ---------------------------------------------------------------------------

_genre_job = {
    "running": False,
    "progress": 0,
    "total": 0,
    "completed": 0,
    "errors": 0,
    "results": [],
}


# ---------------------------------------------------------------------------
# Phase 4 — confidence gating
# ---------------------------------------------------------------------------

AUTO_APPLY_THRESHOLD = 85   # >=  goes straight to matched_genre
NEEDS_REVIEW_THRESHOLD = 60  # 60-84 = needs_review, <60 = manual_review


def _gate_review_status(confidence) -> str:
    """Map a 0-100 confidence score to a review_status bucket."""
    try:
        c = int(confidence)
    except (TypeError, ValueError):
        return "manual_review"
    if c >= AUTO_APPLY_THRESHOLD:
        return "auto_applied"
    if c >= NEEDS_REVIEW_THRESHOLD:
        return "needs_review"
    return "manual_review"



# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status")
async def ai_status():
    """Check Ollama connection and model availability."""
    classifier = get_genre_classifier()
    status = await classifier.check_status()
    status["reasoning_model"] = classifier.reasoning_model
    status["two_pass_enabled"] = classifier.two_pass_enabled
    return status


@router.get("/models")
async def list_models():
    """List models installed in the connected Ollama instance."""
    classifier = get_genre_classifier()
    models = await list_available_models(host=classifier.host)
    return {
        "current_model": classifier.model,
        "host": classifier.host,
        "available_models": models,
        "reasoning_model": classifier.reasoning_model,
        "two_pass_enabled": classifier.two_pass_enabled,
    }


@router.post("/settings")
async def update_ai_settings(body: OllamaSettings):
    """Update Ollama model / host / two-pass settings."""
    classifier = await update_classifier_settings(
        model=body.model,
        host=body.host,
        reasoning_model=body.reasoning_model,
        two_pass_enabled=body.two_pass_enabled,
    )
    status = await classifier.check_status()
    status["reasoning_model"] = classifier.reasoning_model
    status["two_pass_enabled"] = classifier.two_pass_enabled
    return {"updated": True, **status}


@router.get("/classify-genre/{track_id}", response_model=GenreResult)
async def classify_genre(track_id: int):
    """Classify genre for a single track using Ollama."""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

        # Read MIK tags for extra context
        mik = read_mik_tags(track.filepath)

        metadata = {
            "track_id": track.id,
            "filename": track.filename,
            "directory": track.directory,
            "title": track.title or track.matched_title or "",
            "artist": track.artist or track.matched_artist or "",
            "album": track.album or track.matched_album or "",
            "genre": track.genre or track.matched_genre or "",
            "mik_key": mik.get("key", ""),
            "year": track.year or track.matched_year or "",
            "fingerprint_raw": track.fingerprint_raw,
            "duration": int(track.duration) if track.duration else None,
        }

        classifier = get_genre_classifier()
        ai_result = await classifier.classify_track(metadata)

        return GenreResult(
            track_id=track.id,
            genres=ai_result.get("genres", []),
            confidence=ai_result.get("confidence", 0),
            reasoning=ai_result.get("reasoning", ""),
            mik_key=mik.get("key"),
            error=ai_result.get("error"),
        )


@router.post("/classify-genre/{track_id}/apply")
async def apply_genre(track_id: int, genres: Optional[List[str]] = None):
    """
    Apply AI-classified genre to a track's matched_genre field.
    If genres list is provided, use that; otherwise classify first.
    """
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

        if not genres:
            # Classify first
            mik = read_mik_tags(track.filepath)
            metadata = {
                "track_id": track.id,
                "filename": track.filename,
                "directory": track.directory,
                "title": track.title or track.matched_title or "",
                "artist": track.artist or track.matched_artist or "",
                "album": track.album or track.matched_album or "",
                "genre": track.genre or track.matched_genre or "",
                "mik_key": mik.get("key", ""),
                "year": track.year or track.matched_year or "",
                "fingerprint_raw": track.fingerprint_raw,
                "duration": int(track.duration) if track.duration else None,
            }
            classifier = get_genre_classifier()
            ai_result = await classifier.classify_track(metadata)
            genres = ai_result.get("genres", [])

        if not genres:
            raise HTTPException(status_code=422, detail="No genres determined")

        genre_str = ";".join(genres)
        confidence = ai_result.get("confidence") if isinstance(ai_result, dict) else None
        reasoning = ai_result.get("reasoning") if isinstance(ai_result, dict) else None
        review_status = _gate_review_status(confidence)

        track.ai_genre = genre_str
        track.ai_genre_confidence = confidence if isinstance(confidence, int) else track.ai_genre_confidence
        track.ai_genre_source = get_genre_classifier().model
        track.ai_reasoning = reasoning or track.ai_reasoning
        track.review_status = review_status
        # Only push to matched_genre when classifier is confident (≥85)
        if review_status == "auto_applied":
            track.matched_genre = genre_str
        await db.commit()

        return {
            "track_id": track.id,
            "applied_genre": genre_str,
            "review_status": review_status,
            "confidence": confidence,
        }


@router.post("/classify-batch")
async def classify_batch(body: BatchGenreRequest, background_tasks: BackgroundTasks):
    """Start a batch genre classification job in the background."""
    global _genre_job

    if _genre_job["running"]:
        raise HTTPException(status_code=409, detail="Batch classification already running")

    _genre_job = {
        "running": True,
        "progress": 0,
        "total": len(body.track_ids),
        "completed": 0,
        "errors": 0,
        "results": [],
    }

    background_tasks.add_task(_run_batch_classification, body.track_ids)

    return {"started": True, "total": len(body.track_ids)}


@router.get("/classify-batch/status")
async def classify_batch_status():
    """Get status of the running batch classification job."""
    return _genre_job


@router.post("/classify-batch/stop")
async def stop_batch_classification():
    """Signal the batch classification to stop and unload the model from memory."""
    global _genre_job
    _genre_job["running"] = False
    unloaded = await unload_current_model()
    return {"stopped": True, "model_unloaded": unloaded}


@router.post("/unload")
async def unload_model():
    """Manually unload the current Ollama model from memory."""
    unloaded = await unload_current_model()
    return {"unloaded": unloaded}


@router.get("/enrichment/settings")
async def get_enrichment_settings_endpoint():
    """Return current enrichment configuration (excluding which keys are set)."""
    from backend.services.enrichment import load_enrichment_settings
    cfg = await load_enrichment_settings()
    return {
        "enabled": cfg["enabled"],
        "use_web_search": cfg["use_web_search"],
        "lastfm_api_key_set": bool(cfg["lastfm_api_key"]),
        "acoustid_api_key_set": bool(cfg["acoustid_api_key"]),
        "searxng_url": cfg["searxng_url"],
        "discogs_token_set": bool(cfg["discogs_token"]),
        "spotify_client_id_set": bool(cfg["spotify_client_id"]),
        "spotify_client_secret_set": bool(cfg["spotify_client_secret"]),
    }


class EnrichmentSettings(BaseModel):
    enabled: Optional[bool] = None
    use_web_search: Optional[bool] = None
    lastfm_api_key: Optional[str] = None
    searxng_url: Optional[str] = None
    discogs_token: Optional[str] = None
    spotify_client_id: Optional[str] = None
    spotify_client_secret: Optional[str] = None


@router.post("/enrichment/settings")
async def update_enrichment_settings(body: EnrichmentSettings):
    """Persist enrichment configuration."""
    from backend.services.database import load_saved_settings_db, save_settings_db
    saved = await load_saved_settings_db()
    if body.enabled is not None:
        saved["enrichment_enabled"] = body.enabled
    if body.use_web_search is not None:
        saved["enrichment_web_search"] = body.use_web_search
    if body.lastfm_api_key is not None:
        saved["lastfm_api_key"] = body.lastfm_api_key
    if body.searxng_url is not None:
        saved["searxng_url"] = body.searxng_url
    if body.discogs_token is not None:
        saved["discogs_token"] = body.discogs_token
    if body.spotify_client_id is not None:
        saved["spotify_client_id"] = body.spotify_client_id
    if body.spotify_client_secret is not None:
        saved["spotify_client_secret"] = body.spotify_client_secret
    await save_settings_db(saved)
    return {"saved": True}


@router.post("/enrichment/cache/clear")
async def clear_enrichment_cache_endpoint():
    """Wipe the per-artist enrichment cache (forces re-fetch on next scan)."""
    from backend.services.enrichment import clear_enrichment_cache
    deleted = await clear_enrichment_cache()
    return {"cleared": True, "rows_deleted": deleted}


@router.post("/enrichment/test")
async def test_enrichment(artist: str, title: Optional[str] = None):
    """Run enrichment for a single artist/title and return the raw bundle.

    Useful from the Settings UI to verify API keys work end-to-end.
    """
    from backend.services.enrichment import enrich_track, load_enrichment_settings
    cfg = await load_enrichment_settings()
    bundle = await enrich_track(
        artist=artist,
        title=title,
        lastfm_api_key=cfg["lastfm_api_key"],
        acoustid_api_key=cfg["acoustid_api_key"],
        searxng_url=cfg["searxng_url"],
        discogs_token=cfg["discogs_token"],
        spotify_client_id=cfg["spotify_client_id"],
        spotify_client_secret=cfg["spotify_client_secret"],
        use_web_search=cfg["use_web_search"],
        use_cache=False,  # always live-fetch when testing
    )
    return {
        "prompt_block": bundle.to_prompt_block(),
        "bundle": bundle.to_dict(),
    }


@router.get("/mik-tags/{track_id}")
async def get_mik_tags(track_id: int):
    """Read Mixed In Key tags for a track."""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

        mik = read_mik_tags(track.filepath)
        return {
            "track_id": track.id,
            "filename": track.filename,
            "bpm": mik["bpm"],
            "key": mik["key"],
            "energy": mik["energy"],
            "raw_frames": mik["raw_frames"],
        }


# ---------------------------------------------------------------------------
# Background job runner
# ---------------------------------------------------------------------------


async def _run_batch_classification(track_ids: List[int]):
    """Background task: classify genres for a list of track IDs."""
    global _genre_job

    classifier = get_genre_classifier()

    # Load all tracks
    tracks_meta = []
    async with get_db() as db:
        for tid in track_ids:
            if not _genre_job["running"]:
                break
            result = await db.execute(select(Track).where(Track.id == tid))
            track = result.scalar_one_or_none()
            if not track:
                _genre_job["errors"] += 1
                continue

            mik = read_mik_tags(track.filepath)
            tracks_meta.append({
                "track_id": track.id,
                "filename": track.filename,
                "directory": track.directory,
                "title": track.title or track.matched_title or "",
                "artist": track.artist or track.matched_artist or "",
                "album": track.album or track.matched_album or "",
                "genre": track.genre or track.matched_genre or "",
                "mik_key": mik.get("key", ""),
                "year": track.year or track.matched_year or "",
                "fingerprint_raw": track.fingerprint_raw,
                "duration": int(track.duration) if track.duration else None,
            })

    if not _genre_job["running"]:
        logger.info("Batch classification stopped before processing")
        return

    # Classify in batches of 10
    batch_size = 10
    for i in range(0, len(tracks_meta), batch_size):
        if not _genre_job["running"]:
            break

        batch = tracks_meta[i : i + batch_size]
        try:
            results = await classifier.classify_batch(batch, batch_size=batch_size)

            # Apply results to database
            async with get_db() as db:
                for meta, res in zip(batch, results):
                    if res.get("genres"):
                        genre_str = ";".join(res["genres"])
                        confidence = res.get("confidence")
                        review_status = _gate_review_status(confidence)
                        update_values = {
                            "ai_genre": genre_str,
                            "ai_genre_confidence": confidence,
                            "ai_genre_source": classifier.model,
                            "ai_reasoning": res.get("reasoning"),
                            "review_status": review_status,
                        }
                        # Only push to matched_genre on high confidence
                        if review_status == "auto_applied":
                            update_values["matched_genre"] = genre_str
                        await db.execute(
                            update(Track)
                            .where(Track.id == meta["track_id"])
                            .values(**update_values)
                        )
                        _genre_job["results"].append({
                            "track_id": meta["track_id"],
                            "genres": res["genres"],
                            "confidence": confidence,
                            "review_status": review_status,
                        })
                    else:
                        _genre_job["errors"] += 1

                    _genre_job["completed"] += 1
                    _genre_job["progress"] = int(
                        (_genre_job["completed"] / _genre_job["total"]) * 100
                    )

                await db.commit()

        except Exception as e:
            logger.error(f"Batch classification error: {e}")
            _genre_job["errors"] += len(batch)
            _genre_job["completed"] += len(batch)
            _genre_job["progress"] = int(
                (_genre_job["completed"] / _genre_job["total"]) * 100
            )

    _genre_job["running"] = False
    logger.info(
        f"Batch classification complete: {_genre_job['completed']} processed, "
        f"{_genre_job['errors']} errors"
    )
    # Free the model from RAM/VRAM now that the batch is done
    try:
        await unload_current_model()
    except Exception as e:
        logger.warning(f"Could not unload model after batch: {e}")


# ---------------------------------------------------------------------------
# Phase 4 — Review queue + cross-track consistency pass
# ---------------------------------------------------------------------------


class ReviewDecision(BaseModel):
    genres: Optional[List[str]] = None  # optional manual override


@router.get("/review-queue")
async def get_review_queue(
    status: Optional[str] = None,
    limit: int = 200,
    skip: int = 0,
):
    """List tracks awaiting human review.

    ``status`` filters by review_status (needs_review|manual_review|approved|rejected|auto_applied).
    Defaults to needs_review + manual_review.
    """
    from sqlalchemy import or_
    async with get_db() as db:
        q = select(Track)
        if status:
            q = q.where(Track.review_status == status)
        else:
            q = q.where(or_(
                Track.review_status == "needs_review",
                Track.review_status == "manual_review",
            ))
        q = q.order_by(Track.ai_genre_confidence.asc().nullslast()).offset(skip).limit(limit)
        result = await db.execute(q)
        tracks = result.scalars().all()
        return [
            {
                "id": t.id,
                "filename": t.filename,
                "title": t.matched_title or t.title,
                "artist": t.matched_artist or t.artist,
                "album": t.matched_album or t.album,
                "current_genre": t.matched_genre,
                "ai_genre": t.ai_genre,
                "ai_genre_confidence": t.ai_genre_confidence,
                "ai_reasoning": t.ai_reasoning,
                "review_status": t.review_status,
                "consistency_flag": t.consistency_flag,
            }
            for t in tracks
        ]


@router.get("/review-queue/stats")
async def get_review_queue_stats():
    """Counts of tracks in each review bucket."""
    from sqlalchemy import func
    async with get_db() as db:
        q = (
            select(Track.review_status, func.count(Track.id))
            .where(Track.review_status.isnot(None))
            .group_by(Track.review_status)
        )
        rows = (await db.execute(q)).all()
        return {status: count for status, count in rows}


@router.post("/review/{track_id}/approve")
async def approve_review(track_id: int, body: Optional[ReviewDecision] = None):
    """Approve the AI's genre (optionally overriding with manual list)."""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

        genres = (body.genres if body and body.genres else None)
        if genres:
            genre_str = ";".join(genres)
            track.ai_genre = genre_str
        else:
            genre_str = track.ai_genre

        if not genre_str:
            raise HTTPException(status_code=422, detail="No genre to approve")

        track.matched_genre = genre_str
        track.review_status = "approved"
        await db.commit()
        return {"track_id": track.id, "applied_genre": genre_str, "review_status": "approved"}


@router.post("/review/{track_id}/reject")
async def reject_review(track_id: int):
    """Reject the AI suggestion (clears ai_genre, leaves matched_genre alone)."""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        track.review_status = "rejected"
        await db.commit()
        return {"track_id": track.id, "review_status": "rejected"}


def _primary_genre(genre_str: Optional[str]) -> Optional[str]:
    if not genre_str:
        return None
    first = genre_str.split(";")[0].strip()
    return first.lower() or None


@router.post("/consistency-pass")
async def run_consistency_pass(min_tracks_per_artist: int = 3, confidence_override_floor: int = 90):
    """Cross-track consistency check.

    For each artist with >= ``min_tracks_per_artist`` AI-classified tracks, find the majority
    primary genre. Any track whose primary genre differs AND whose confidence is below
    ``confidence_override_floor`` is downgraded to needs_review with a consistency_flag note.
    """
    from collections import Counter, defaultdict
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(Track.ai_genre.isnot(None))
        )
        tracks = result.scalars().all()

    by_artist: dict = defaultdict(list)
    for t in tracks:
        artist = (t.matched_artist or t.artist or "").strip().lower()
        if not artist:
            continue
        by_artist[artist].append(t)

    artists_checked = 0
    flagged = 0
    cleared = 0
    async with get_db() as db:
        for artist, group in by_artist.items():
            if len(group) < min_tracks_per_artist:
                # Clear any stale flags on small groups
                for t in group:
                    if t.consistency_flag:
                        t.consistency_flag = None
                        cleared += 1
                continue
            artists_checked += 1
            primaries = [p for p in (_primary_genre(t.ai_genre) for t in group) if p]
            if not primaries:
                continue
            counts = Counter(primaries)
            majority_genre, majority_count = counts.most_common(1)[0]
            # Only act if there's a clear majority (>50% of tracks)
            if majority_count <= len(group) / 2:
                for t in group:
                    if t.consistency_flag:
                        t.consistency_flag = None
                        cleared += 1
                continue

            for t in group:
                tp = _primary_genre(t.ai_genre)
                if tp and tp != majority_genre:
                    confidence = t.ai_genre_confidence or 0
                    note = f"Artist majority: {majority_genre.title()} (this track: {tp.title()})"
                    if confidence < confidence_override_floor:
                        t.consistency_flag = note
                        # Downgrade auto_applied outliers so a human can confirm
                        if t.review_status == "auto_applied":
                            t.review_status = "needs_review"
                            # Pull back the matched_genre so the outlier doesn't get tagged
                            if t.matched_genre == t.ai_genre:
                                t.matched_genre = None
                        flagged += 1
                    else:
                        # High-confidence dissent: keep but annotate
                        t.consistency_flag = note
                        flagged += 1
                elif t.consistency_flag:
                    t.consistency_flag = None
                    cleared += 1
        await db.commit()

    return {
        "artists_checked": artists_checked,
        "tracks_flagged": flagged,
        "tracks_cleared": cleared,
        "total_artists": len(by_artist),
    }

