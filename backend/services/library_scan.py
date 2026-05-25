"""
Library Scan Review service — scans the library with AI, generates suggested
changes, and lets the user approve/reject each one before applying.

Workflow:
  1. User triggers a library scan (full or selected tracks)
  2. Backend classifies genres, checks cover art, reads MIK tags
  3. Results are stored as "pending suggestions" (not applied)
  4. User reviews suggestions in the UI with checkboxes
  5. User approves selected suggestions → tags are written

Nothing is written to files until the user explicitly approves.
"""
import asyncio
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update
from loguru import logger

from backend.services.database import get_db
from backend.models.track import Track
from backend.services.ai_genre import get_genre_classifier
from backend.services.mik import read_mik_tags
from backend.services.cover_art import extract_embedded_cover, cover_art_quality_score
from backend.services.tagger import get_tagger, tag_track


# ---------------------------------------------------------------------------
# Confidence gating (matches backend/api/ai.py thresholds)
# ---------------------------------------------------------------------------

_AUTO_APPLY_THRESHOLD = 85
_NEEDS_REVIEW_THRESHOLD = 60


def _gate_review_status(confidence) -> str:
    try:
        c = int(confidence)
    except (TypeError, ValueError):
        return "manual_review"
    if c >= _AUTO_APPLY_THRESHOLD:
        return "auto_applied"
    if c >= _NEEDS_REVIEW_THRESHOLD:
        return "needs_review"
    return "manual_review"


# ---------------------------------------------------------------------------
# Suggestion storage (in-memory for the active scan session)
# ---------------------------------------------------------------------------

# Each suggestion: {
#   track_id, filename, filepath,
#   current: {title, artist, album, genre, year, has_cover, mik_bpm, mik_key, mik_energy},
#   suggested: {genre, cover_url, ...},
#   ai_confidence, ai_reasoning,
#   cover_quality: {score, issues},
#   selected: bool (user checkbox state, default True),
#   status: "pending" | "approved" | "rejected" | "applied" | "error"
# }

_scan_session = {
    "running": False,
    "progress": 0,
    "total": 0,
    "phase": "",  # "scanning" | "classifying" | "complete"
    "suggestions": [],  # List of suggestion dicts
    "errors": 0,
    "scan_id": None,  # Unique ID for this scan session
}


def get_scan_session() -> dict:
    """Get the current scan session state."""
    return {
        "running": _scan_session["running"],
        "progress": _scan_session["progress"],
        "total": _scan_session["total"],
        "phase": _scan_session["phase"],
        "suggestion_count": len(_scan_session["suggestions"]),
        "errors": _scan_session["errors"],
        "scan_id": _scan_session["scan_id"],
    }


def get_suggestions(
    status_filter: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    """Get paginated suggestions from the current scan session."""
    suggestions = _scan_session["suggestions"]

    if status_filter:
        suggestions = [s for s in suggestions if s["status"] == status_filter]

    total = len(suggestions)
    page = suggestions[offset : offset + limit]

    # Strip large data for the list view (cover bytes etc)
    slim = []
    for s in page:
        slim.append({
            "track_id": s["track_id"],
            "filename": s["filename"],
            "filepath": s["filepath"],
            "current": s["current"],
            "suggested": s["suggested"],
            "ai_confidence": s["ai_confidence"],
            "ai_reasoning": s["ai_reasoning"],
            "cover_quality": s["cover_quality"],
            "selected": s["selected"],
            "status": s["status"],
            "changes": s.get("changes", []),
        })

    return {"suggestions": slim, "total": total, "offset": offset, "limit": limit}


def update_selection(track_ids: List[int], selected: bool):
    """Toggle the selected state for specific suggestions."""
    id_set = set(track_ids)
    for s in _scan_session["suggestions"]:
        if s["track_id"] in id_set:
            s["selected"] = selected


def select_all(selected: bool):
    """Select or deselect all suggestions."""
    for s in _scan_session["suggestions"]:
        s["selected"] = selected


# ---------------------------------------------------------------------------
# Full library scan
# ---------------------------------------------------------------------------


async def run_library_scan(
    track_ids: Optional[List[int]] = None,
    classify_genre: bool = True,
    check_covers: bool = True,
    force_reclassify: bool = False,
):
    """
    Scan tracks and generate suggestions. Does NOT modify any files.

    Args:
        track_ids: Specific track IDs to scan (None = all tracks)
        classify_genre: Run AI genre classification
        check_covers: Check cover art quality
        force_reclassify: If False (default), reuse cached AI genre results from the DB
            for any track that already has `ai_genre` populated. Set True to re-run the
            classifier on every track.
    """
    global _scan_session

    _scan_session = {
        "running": True,
        "progress": 0,
        "total": 0,
        "phase": "scanning",
        "suggestions": [],
        "errors": 0,
        "scan_id": datetime.utcnow().isoformat(),
    }

    try:
        await _run_library_scan_inner(
            track_ids=track_ids,
            classify_genre=classify_genre,
            check_covers=check_covers,
            force_reclassify=force_reclassify,
        )
    except Exception:
        logger.exception("Library scan crashed")
        _scan_session["phase"] = "error"
        _scan_session["errors"] = (_scan_session.get("errors") or 0) + 1
    finally:
        _scan_session["running"] = False


async def _run_library_scan_inner(
    track_ids: Optional[List[int]] = None,
    classify_genre: bool = True,
    check_covers: bool = True,
    force_reclassify: bool = False,
):
    """Body of the library scan (separated from outer guard for try/finally)."""
    global _scan_session

    # Load tracks
    async with get_db() as db:
        if track_ids:
            result = await db.execute(
                select(Track).where(Track.id.in_(track_ids))
            )
        else:
            result = await db.execute(select(Track))
        tracks = result.scalars().all()

    _scan_session["total"] = len(tracks)
    logger.info(f"Library scan started: {len(tracks)} tracks")

    classifier = get_genre_classifier() if classify_genre else None

    # Process tracks in batches for genre classification
    batch_size = 10
    all_track_meta = []

    for i, track in enumerate(tracks):
        if not _scan_session["running"]:
            break

        _scan_session["progress"] = i + 1
        _scan_session["phase"] = "scanning"

        try:
            # Read current tags from file
            tagger = get_tagger()
            current_tags = await asyncio.to_thread(tagger.get_current_tags, track.filepath)

            # Read MIK tags
            mik = await asyncio.to_thread(read_mik_tags, track.filepath)

            # Check cover art quality
            cover_quality = {"score": 100, "issues": []}
            if check_covers:
                cover_info = await asyncio.to_thread(extract_embedded_cover, track.filepath)
                cover_quality = cover_art_quality_score(cover_info)

            meta = {
                "track_id": track.id,
                "filename": track.filename,
                "filepath": track.filepath,
                "directory": track.directory,
                "title": track.title or track.matched_title or "",
                "artist": track.artist or track.matched_artist or "",
                "album": track.album or track.matched_album or "",
                "genre": track.genre or track.matched_genre or "",
                "year": track.year or track.matched_year or "",
                "mik_key": mik.get("key", ""),
                "mik_bpm": mik.get("bpm"),
                "mik_energy": mik.get("energy"),
                "current_tags": current_tags,
                "cover_quality": cover_quality,
                "file_format": track.file_format,
            }
            all_track_meta.append(meta)

        except Exception as e:
            logger.error(f"Error scanning track {track.id}: {e}")
            _scan_session["errors"] += 1

    # Genre classification phase
    if classifier and _scan_session["running"]:
        _scan_session["phase"] = "classifying"

        # Split into cached vs needs-classification
        to_classify = []
        cached_results: List[tuple] = []  # list of (meta, genre_result) reused from DB
        if force_reclassify:
            to_classify = list(all_track_meta)
        else:
            # Reload current AI fields per track (the meta dict was built before this phase)
            track_ids_in_scan = [m["track_id"] for m in all_track_meta]
            async with get_db() as db:
                rows = (await db.execute(
                    select(
                        Track.id, Track.ai_genre, Track.ai_genre_confidence,
                        Track.ai_genre_source, Track.ai_reasoning,
                    ).where(Track.id.in_(track_ids_in_scan))
                )).all()
            cache_map = {r[0]: r for r in rows}
            for meta in all_track_meta:
                row = cache_map.get(meta["track_id"])
                if row and row[1]:  # has ai_genre
                    genre_result = {
                        "genres": [g.strip() for g in row[1].split(";") if g.strip()],
                        "confidence": row[2] or 0,
                        "reasoning": row[4] or "",
                        "cached": True,
                    }
                    cached_results.append((meta, genre_result))
                else:
                    to_classify.append(meta)

        logger.info(
            f"Library scan: {len(cached_results)} tracks reused from cache, "
            f"{len(to_classify)} tracks need classification"
        )

        # Emit suggestions for cached tracks immediately
        for meta, genre_result in cached_results:
            suggestion = _build_suggestion(meta, genre_result)
            if suggestion["changes"]:
                _scan_session["suggestions"].append(suggestion)
        _scan_session["progress"] = len(cached_results)

        for batch_start in range(0, len(to_classify), batch_size):
            if not _scan_session["running"]:
                break

            batch = to_classify[batch_start : batch_start + batch_size]

            try:
                genre_results = await classifier.classify_batch(batch, batch_size=batch_size)

                # Persist results to DB immediately so a stopped/closed scan retains its work
                async with get_db() as db:
                    for meta, genre_result in zip(batch, genre_results):
                        genres = genre_result.get("genres") or []
                        if genres:
                            genre_str = ";".join(genres)
                            confidence = genre_result.get("confidence")
                            review_status = _gate_review_status(confidence)
                            update_values = {
                                "ai_genre": genre_str,
                                "ai_genre_confidence": confidence,
                                "ai_genre_source": classifier.model,
                                "ai_reasoning": genre_result.get("reasoning"),
                                "review_status": review_status,
                            }
                            if review_status == "auto_applied":
                                update_values["matched_genre"] = genre_str
                            await db.execute(
                                update(Track)
                                .where(Track.id == meta["track_id"])
                                .values(**update_values)
                            )
                    await db.commit()

                for meta, genre_result in zip(batch, genre_results):
                    suggestion = _build_suggestion(meta, genre_result)
                    if suggestion["changes"]:  # Only add if there are actual changes
                        _scan_session["suggestions"].append(suggestion)

            except Exception as e:
                logger.error(f"Genre classification batch error: {e}")
                _scan_session["errors"] += len(batch)
                # Still add suggestions without genre for cover issues
                for meta in batch:
                    suggestion = _build_suggestion(meta, None)
                    if suggestion["changes"]:
                        _scan_session["suggestions"].append(suggestion)

            _scan_session["progress"] = min(
                _scan_session["total"],
                len(cached_results) + batch_start + batch_size,
            )
    else:
        # No genre classification — just check covers/tags
        for meta in all_track_meta:
            suggestion = _build_suggestion(meta, None)
            if suggestion["changes"]:
                _scan_session["suggestions"].append(suggestion)

    _scan_session["phase"] = "complete"
    logger.info(
        f"Library scan complete: {len(_scan_session['suggestions'])} suggestions, "
        f"{_scan_session['errors']} errors"
    )


def _build_suggestion(
    meta: Dict[str, Any],
    genre_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a suggestion dict from track metadata and AI results."""
    current = meta["current_tags"]
    current["mik_bpm"] = meta.get("mik_bpm")
    current["mik_key"] = meta.get("mik_key")
    current["mik_energy"] = meta.get("mik_energy")

    suggested = {}
    changes = []

    # Genre suggestion
    if genre_result and genre_result.get("genres"):
        new_genre = ";".join(genre_result["genres"])
        old_genre = current.get("genre") or ""
        if new_genre.lower() != old_genre.lower():
            suggested["genre"] = new_genre
            changes.append({
                "field": "genre",
                "old_value": old_genre or "(none)",
                "new_value": new_genre,
            })

    # Cover art issues
    cover_q = meta.get("cover_quality", {})
    if cover_q.get("score", 100) < 50:
        changes.append({
            "field": "cover_art",
            "old_value": f"Quality: {cover_q.get('score', 0)}/100",
            "new_value": "Needs replacement",
        })
        suggested["needs_cover"] = True

    if not current.get("has_cover"):
        changes.append({
            "field": "cover_art",
            "old_value": "(none)",
            "new_value": "Missing — search needed",
        })
        suggested["needs_cover"] = True

    return {
        "track_id": meta["track_id"],
        "filename": meta["filename"],
        "filepath": meta["filepath"],
        "current": current,
        "suggested": suggested,
        "ai_confidence": genre_result.get("confidence", 0) if genre_result else 0,
        "ai_reasoning": genre_result.get("reasoning", "") if genre_result else "",
        "cover_quality": cover_q,
        "selected": True,  # Default: selected for approval
        "status": "pending",
        "changes": changes,
    }


# ---------------------------------------------------------------------------
# Apply approved suggestions
# ---------------------------------------------------------------------------


async def apply_approved_suggestions() -> Dict[str, Any]:
    """
    Apply only the selected+pending suggestions to files.
    Returns summary of what was applied.
    """
    selected = [
        s for s in _scan_session["suggestions"]
        if s["selected"] and s["status"] == "pending"
    ]

    if not selected:
        return {"applied": 0, "errors": 0, "message": "No suggestions selected"}

    applied = 0
    errors = 0
    tagger = get_tagger()

    for suggestion in selected:
        try:
            track_id = suggestion["track_id"]
            genre = suggestion["suggested"].get("genre")

            if genre:
                # Update the database
                async with get_db() as db:
                    result = await db.execute(
                        select(Track).where(Track.id == track_id)
                    )
                    track = result.scalar_one_or_none()
                    if not track:
                        suggestion["status"] = "error"
                        errors += 1
                        continue

                    # Write genre to file
                    ext = os.path.splitext(track.filepath)[1].lower()
                    success = False

                    if ext == '.mp3':
                        success = tagger.tag_mp3(track.filepath, genre=genre)
                    elif ext == '.flac':
                        success = tagger.tag_flac(track.filepath, genre=genre)
                    elif ext in ('.m4a', '.aac', '.mp4'):
                        success = tagger.tag_m4a(track.filepath, genre=genre)
                    elif ext == '.ogg':
                        success = tagger.tag_ogg(track.filepath, genre=genre)

                    if success:
                        track.genre = genre
                        track.matched_genre = genre
                        track.ai_genre = genre
                        track.ai_genre_confidence = suggestion["ai_confidence"]
                        track.ai_genre_source = get_genre_classifier().model
                        await db.commit()
                        suggestion["status"] = "applied"
                        applied += 1
                    else:
                        suggestion["status"] = "error"
                        errors += 1
            else:
                # No genre change — mark as applied (was cover-only suggestion)
                suggestion["status"] = "applied"
                applied += 1

        except Exception as e:
            logger.error(f"Error applying suggestion for track {suggestion['track_id']}: {e}")
            suggestion["status"] = "error"
            errors += 1

    return {
        "applied": applied,
        "errors": errors,
        "message": f"Applied {applied} changes ({errors} errors)",
    }


async def reject_suggestions(track_ids: List[int]):
    """Mark specific suggestions as rejected."""
    id_set = set(track_ids)
    for s in _scan_session["suggestions"]:
        if s["track_id"] in id_set:
            s["status"] = "rejected"


def stop_scan():
    """Stop the running scan."""
    global _scan_session
    _scan_session["running"] = False
