"""
YouTube candidate search service.

Uses yt-dlp's flat search (no API key, no quota) to return candidate videos
for a track so the user can audibly compare against potential matches. This is
a deliberately lightweight, read-only lookup: it never downloads audio, it only
extracts search-result metadata (title, channel, duration, thumbnail, url).
"""
import asyncio
from typing import List, Dict, Optional

from loguru import logger

try:
    import yt_dlp

    YT_DLP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when dependency missing
    yt_dlp = None
    YT_DLP_AVAILABLE = False


_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": True,   # don't resolve each video fully - just search metadata
    "skip_download": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "socket_timeout": 15,
}


def _pick_thumbnail(entry: Dict) -> Optional[str]:
    """Choose a reasonable thumbnail URL for a flat search entry."""
    if entry.get("thumbnail"):
        return entry["thumbnail"]

    thumbs = entry.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url")

    video_id = entry.get("id")
    if video_id:
        return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    return None


def _search_sync(query: str, limit: int) -> List[Dict]:
    """Blocking yt-dlp search. Run via asyncio.to_thread."""
    with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

    entries = (info or {}).get("entries") or []
    results: List[Dict] = []
    for entry in entries:
        if not entry:
            continue
        video_id = entry.get("id")
        if not video_id:
            continue
        results.append(
            {
                "id": video_id,
                "title": entry.get("title"),
                "uploader": entry.get("uploader") or entry.get("channel"),
                "duration": entry.get("duration"),
                "view_count": entry.get("view_count"),
                "url": entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
                "thumbnail": _pick_thumbnail(entry),
                "embed_url": f"https://www.youtube.com/embed/{video_id}",
            }
        )
    return results


async def search_youtube_candidates(query: str, limit: int = 6) -> List[Dict]:
    """
    Search YouTube for candidate videos matching the query.

    Returns an empty list (never raises) if yt-dlp is unavailable, the query is
    empty, or the search fails - callers treat this as "no candidates".
    """
    if not YT_DLP_AVAILABLE:
        logger.warning("yt-dlp not installed; YouTube candidate search unavailable")
        return []

    query = (query or "").strip()
    if not query:
        return []

    limit = max(1, min(limit, 15))

    try:
        return await asyncio.to_thread(_search_sync, query, limit)
    except Exception as exc:
        logger.error(f"YouTube search failed for '{query}': {exc}")
        return []
