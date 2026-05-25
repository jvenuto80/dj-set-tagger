"""
Multi-source cover art search service.

Searches multiple sources in parallel for the best cover art:
  1. MusicBrainz Cover Art Archive (free, no auth)
  2. iTunes Search API (free, no auth, already exists — we reuse it)
  3. Discogs API (free with user-agent, higher quality)
  4. DuckDuckGo scraping fallback (existing logic)

Also provides utilities for extracting embedded cover art from files
and assessing cover art quality via Ollama vision models.
"""
import asyncio
import base64
import json as json_mod
from io import BytesIO
from typing import Optional, List, Dict, Any
from urllib.parse import quote

import aiohttp
from PIL import Image
from loguru import logger

# MusicBrainz / Cover Art Archive
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
COVER_ART_ARCHIVE = "https://coverartarchive.org"
USER_AGENT = "SetList/1.0 (https://github.com/jvenuto80/setlist)"

# Discogs
DISCOGS_API = "https://api.discogs.com"


class CoverArtSearch:
    """Search multiple sources for cover art."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Unified search — queries all sources in parallel
    # ------------------------------------------------------------------

    async def search(
        self,
        artist: str = "",
        title: str = "",
        album: str = "",
        query: str = "",
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search all cover art sources in parallel.

        Returns list of {url, source, title, width, height} sorted by quality.
        """
        search_term = query or f"{artist} {title}".strip() or album
        if not search_term:
            return []

        tasks = [
            self._search_musicbrainz(artist, album or title),
            self._search_itunes(search_term),
            self._search_discogs(artist, album or title),
        ]

        results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        all_covers: List[Dict[str, Any]] = []
        seen_urls = set()

        for result in results_lists:
            if isinstance(result, Exception):
                logger.debug(f"Cover source error: {result}")
                continue
            for cover in result:
                url = cover.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_covers.append(cover)

        # Sort: prefer larger images, then by source priority
        source_priority = {"Cover Art Archive": 0, "Discogs": 1, "iTunes": 2}
        all_covers.sort(
            key=lambda c: (
                source_priority.get(c.get("source", ""), 9),
                -(c.get("width", 0) or 0),
            )
        )

        return all_covers[:max_results]

    # ------------------------------------------------------------------
    # MusicBrainz Cover Art Archive
    # ------------------------------------------------------------------

    async def _search_musicbrainz(
        self, artist: str, album: str
    ) -> List[Dict[str, Any]]:
        """Search MusicBrainz for releases and fetch covers from Cover Art Archive."""
        covers = []
        if not artist and not album:
            return covers

        session = await self._get_session()

        # Search for releases
        query_parts = []
        if artist:
            query_parts.append(f'artist:"{artist}"')
        if album:
            query_parts.append(f'release:"{album}"')
        query_str = " AND ".join(query_parts)

        try:
            async with session.get(
                f"{MUSICBRAINZ_API}/release",
                params={"query": query_str, "fmt": "json", "limit": 5},
                headers={"Accept": "application/json"},
            ) as resp:
                if resp.status != 200:
                    return covers
                data = await resp.json()

            for release in data.get("releases", []):
                release_id = release.get("id")
                if not release_id:
                    continue

                # Check Cover Art Archive for this release
                try:
                    async with session.get(
                        f"{COVER_ART_ARCHIVE}/release/{release_id}",
                        allow_redirects=True,
                    ) as caa_resp:
                        if caa_resp.status != 200:
                            continue
                        caa_data = await caa_resp.json()

                    for image in caa_data.get("images", []):
                        if image.get("front", False):
                            img_url = image.get("image", "")
                            thumbnails = image.get("thumbnails", {})
                            # Prefer large thumbnail, fall back to full
                            url = (
                                thumbnails.get("1200")
                                or thumbnails.get("large")
                                or thumbnails.get("500")
                                or img_url
                            )
                            if url:
                                # Extract artist names
                                artist_credit = release.get("artist-credit", [])
                                artist_name = ", ".join(
                                    ac.get("artist", {}).get("name", "")
                                    for ac in artist_credit
                                    if "artist" in ac
                                )
                                covers.append({
                                    "url": url,
                                    "source": "Cover Art Archive",
                                    "title": f"{artist_name} - {release.get('title', '')}",
                                    "width": 1200,
                                    "height": 1200,
                                    "release_id": release_id,
                                })
                except Exception:
                    continue

                await asyncio.sleep(0.25)  # Rate limit

        except Exception as e:
            logger.debug(f"MusicBrainz cover search error: {e}")

        return covers

    # ------------------------------------------------------------------
    # iTunes Search API
    # ------------------------------------------------------------------

    async def _search_itunes(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search iTunes for cover art — free, fast, no auth."""
        covers = []
        session = await self._get_session()

        try:
            params = {
                "term": query,
                "media": "music",
                "entity": "album",
                "limit": limit,
            }
            async with session.get(
                "https://itunes.apple.com/search", params=params
            ) as resp:
                if resp.status != 200:
                    return covers
                text = await resp.text()
                data = json_mod.loads(text)

            seen = set()
            for result in data.get("results", []):
                artwork = result.get("artworkUrl100", "")
                if not artwork:
                    continue
                # Upgrade to 1400x1400 (max available from Apple)
                hi_res = artwork.replace("100x100bb", "1400x1400bb")
                if hi_res in seen:
                    continue
                seen.add(hi_res)
                covers.append({
                    "url": hi_res,
                    "source": "iTunes",
                    "title": f"{result.get('artistName', '')} - {result.get('collectionName', '')}",
                    "width": 1400,
                    "height": 1400,
                })
        except Exception as e:
            logger.debug(f"iTunes cover search error: {e}")

        return covers

    # ------------------------------------------------------------------
    # Discogs API (free tier, user-agent auth only)
    # ------------------------------------------------------------------

    async def _search_discogs(
        self, artist: str, title: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search Discogs for release cover art."""
        covers = []
        if not artist and not title:
            return covers

        session = await self._get_session()
        query = f"{artist} {title}".strip()

        try:
            params = {
                "q": query,
                "type": "release",
                "per_page": limit,
            }
            async with session.get(
                f"{DISCOGS_API}/database/search",
                params=params,
                headers={"Accept": "application/json"},
            ) as resp:
                if resp.status == 429:
                    logger.debug("Discogs rate limited")
                    return covers
                if resp.status != 200:
                    return covers
                data = await resp.json()

            for result in data.get("results", []):
                cover_url = result.get("cover_image", "")
                thumb_url = result.get("thumb", "")
                url = cover_url or thumb_url
                if not url or "spacer.gif" in url:
                    continue
                covers.append({
                    "url": url,
                    "source": "Discogs",
                    "title": result.get("title", ""),
                    "width": 600 if cover_url else 150,
                    "height": 600 if cover_url else 150,
                    "discogs_id": result.get("id"),
                })

        except Exception as e:
            logger.debug(f"Discogs cover search error: {e}")

        return covers


# ---------------------------------------------------------------------------
# Embedded cover art extraction
# ---------------------------------------------------------------------------

def extract_embedded_cover(filepath: str) -> Optional[Dict[str, Any]]:
    """
    Extract embedded cover art from an audio file.

    Returns {data: bytes, mime: str, width: int, height: int, size: int}
    or None if no cover is embedded.
    """
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3, ID3NoHeaderError
    from mutagen.mp4 import MP4
    from mutagen.flac import FLAC
    from mutagen.oggvorbis import OggVorbis
    import os
    from pathlib import Path

    if not os.path.exists(filepath):
        return None

    ext = Path(filepath).suffix.lower()

    try:
        if ext == ".mp3":
            try:
                audio = ID3(filepath)
            except ID3NoHeaderError:
                return None
            for key in audio:
                if key.startswith("APIC"):
                    frame = audio[key]
                    return _image_info(frame.data, frame.mime)
            return None

        elif ext == ".flac":
            audio = FLAC(filepath)
            if audio.pictures:
                pic = audio.pictures[0]
                return _image_info(pic.data, pic.mime)
            return None

        elif ext in (".m4a", ".aac", ".mp4"):
            audio = MP4(filepath)
            covrs = audio.tags.get("covr", []) if audio.tags else []
            if covrs:
                data = bytes(covrs[0])
                fmt = covrs[0].imageformat if hasattr(covrs[0], "imageformat") else None
                mime = "image/png" if fmt == 14 else "image/jpeg"
                return _image_info(data, mime)
            return None

        elif ext == ".ogg":
            audio = OggVorbis(filepath)
            pics = audio.get("metadata_block_picture", [])
            if pics:
                from mutagen.flac import Picture
                pic = Picture(base64.b64decode(pics[0]))
                return _image_info(pic.data, pic.mime)
            return None

    except Exception as e:
        logger.debug(f"Error extracting cover from {filepath}: {e}")

    return None


def _image_info(data: bytes, mime: str = "image/jpeg") -> Dict[str, Any]:
    """Build cover info dict from raw image bytes."""
    info = {"data": data, "mime": mime, "size": len(data), "width": 0, "height": 0}
    try:
        img = Image.open(BytesIO(data))
        info["width"] = img.width
        info["height"] = img.height
    except Exception:
        pass
    return info


def cover_art_quality_score(info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Quick heuristic quality assessment of embedded cover art.
    Returns {score: 0-100, issues: [str], resolution: "WxH", size_kb: int}
    """
    if not info:
        return {"score": 0, "issues": ["No cover art embedded"], "resolution": None, "size_kb": 0}

    score = 100
    issues = []
    w, h = info.get("width", 0), info.get("height", 0)
    size_kb = info.get("size", 0) // 1024

    # Resolution checks
    if w == 0 or h == 0:
        score -= 30
        issues.append("Could not determine resolution")
    elif w < 300 or h < 300:
        score -= 40
        issues.append(f"Low resolution ({w}x{h})")
    elif w < 500 or h < 500:
        score -= 15
        issues.append(f"Medium resolution ({w}x{h}), could be better")

    # Aspect ratio (should be ~1:1 for album art)
    if w > 0 and h > 0:
        ratio = max(w, h) / min(w, h)
        if ratio > 1.3:
            score -= 20
            issues.append(f"Non-square aspect ratio ({w}x{h})")

    # File size checks
    if size_kb < 10:
        score -= 30
        issues.append(f"Very small file ({size_kb}KB) — likely a placeholder")
    elif size_kb < 30:
        score -= 15
        issues.append(f"Small file ({size_kb}KB) — may be low quality")

    return {
        "score": max(0, score),
        "issues": issues,
        "resolution": f"{w}x{h}" if w and h else None,
        "size_kb": size_kb,
    }


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_search: Optional[CoverArtSearch] = None


def get_cover_search() -> CoverArtSearch:
    global _search
    if _search is None:
        _search = CoverArtSearch()
    return _search
