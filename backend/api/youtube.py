"""
YouTube API endpoints - list YouTube videos that may match a track so the user
can audibly compare against potential matches.
"""
import re
import webbrowser

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Optional
from sqlalchemy import select

from backend.services.database import get_db
from backend.services.youtube import search_youtube_candidates, YT_DLP_AVAILABLE
from backend.models.track import Track

router = APIRouter()

_AUDIO_EXTS = (".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg")
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _build_query(track: Track) -> str:
    """Build a YouTube search query from a track, preferring matched metadata."""
    artist = (track.matched_artist or track.artist or "").strip()
    title = (track.matched_title or track.title or "").strip()

    if artist and title:
        return f"{artist} - {title}"
    if title:
        return title
    if artist:
        return artist

    # Fall back to the filename with its extension stripped
    filename = track.filename or ""
    lowered = filename.lower()
    for ext in _AUDIO_EXTS:
        if lowered.endswith(ext):
            filename = filename[: -len(ext)]
            break
    return filename.strip()


@router.get("/{track_id}/candidates")
async def youtube_candidates(
    track_id: int,
    query: Optional[str] = Query(None, description="Override the search query"),
    limit: int = Query(6, ge=1, le=15),
):
    """List YouTube videos that may match the given track for manual comparison."""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")

        search_query = (query or "").strip() or _build_query(track)

    if not search_query:
        return {"query": "", "available": YT_DLP_AVAILABLE, "candidates": []}

    candidates = await search_youtube_candidates(search_query, limit=limit)
    return {
        "query": search_query,
        "available": YT_DLP_AVAILABLE,
        "candidates": candidates,
    }


@router.get("/open")
async def youtube_open(video_id: str = Query(..., description="YouTube video id")):
    """
    Open a YouTube watch URL in the host's default browser.

    The packaged app's webview can't reliably open new windows from inside the
    locally served embed iframe, so the iframe calls this same-origin endpoint
    and the backend process opens the link natively instead.
    """
    if not _VIDEO_ID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="Invalid video id")
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    return {"opened": bool(opened), "url": url}


@router.get("/embed/{video_id}", response_class=HTMLResponse)
async def youtube_embed(
    video_id: str,
    autoplay: int = Query(0, ge=0, le=1),
):
    """
    Serve a minimal HTML page that hosts the YouTube IFrame player.

    The packaged app's webview runs from a custom ``tauri://`` origin, which
    YouTube rejects with "Error 153 - Video player configuration error".
    By framing the player from this locally served page the referrer becomes
    ``http://127.0.0.1`` (a localhost origin YouTube accepts), so playback works.
    """
    if not _VIDEO_ID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="Invalid video id")

    autoplay_js = "1" if autoplay else "0"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>YouTube</title>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; background: #000; overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  #player {{ position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }}
  #fallback {{ position: absolute; inset: 0; display: none; flex-direction: column;
    align-items: center; justify-content: center; gap: 14px; text-align: center;
    padding: 24px; color: #e5e7eb; }}
  #fallback p {{ margin: 0; font-size: 14px; line-height: 1.4; color: #9ca3af; max-width: 320px; }}
  #fallback a {{ display: inline-flex; align-items: center; gap: 8px; text-decoration: none;
    background: #ef4444; color: #fff; padding: 10px 18px; border-radius: 8px;
    font-size: 14px; font-weight: 600; }}
  #fallback a:hover {{ background: #dc2626; }}
</style>
</head>
<body>
<div id="player"></div>
<div id="fallback">
  <p>This video's owner doesn't allow it to be played here.</p>
  <a id="watch" href="https://www.youtube.com/watch?v={video_id}">
    Watch on YouTube &#8599;
  </a>
</div>
<script src="https://www.youtube.com/iframe_api"></script>
<script>
  var VIDEO_ID = '{video_id}';
  var WATCH_URL = 'https://www.youtube.com/watch?v=' + VIDEO_ID;
  var fallbackShown = false;
  function openExternal(e) {{
    if (e) e.preventDefault();
    // This page is served from the local backend, so a same-origin call lets
    // the native backend process open the link in the system browser. This is
    // more reliable than window.open inside the Tauri webview iframe.
    try {{
      fetch('/api/youtube/open?video_id=' + encodeURIComponent(VIDEO_ID)).catch(function() {{}});
    }} catch (_) {{}}
    return false;
  }}
  function showFallback() {{
    if (fallbackShown) return;
    fallbackShown = true;
    var p = document.getElementById('player');
    if (p) p.style.display = 'none';
    document.getElementById('fallback').style.display = 'flex';
  }}
  document.getElementById('watch').addEventListener('click', openExternal);
  function onYouTubeIframeAPIReady() {{
    new YT.Player('player', {{
      host: 'https://www.youtube-nocookie.com',
      videoId: VIDEO_ID,
      playerVars: {{ autoplay: {autoplay_js}, rel: 0, modestbranding: 1, playsinline: 1 }},
      events: {{
        // Codes 101/150 = embedding disabled by owner; 153/2/5/100 = other config/availability errors.
        onError: function() {{ showFallback(); }}
      }}
    }});
  }}
  // If the API script fails to load (offline, blocked), fall back too.
  setTimeout(function() {{
    if (typeof YT === 'undefined' || !YT.Player) showFallback();
  }}, 6000);
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
