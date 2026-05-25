"""
Track enrichment service — fetches authoritative metadata from external
sources (MusicBrainz, Last.fm, AcoustID, SearXNG) and aggregates it into
a single bundle that the AI genre classifier can use as grounding context.

Design goals:
    * Parallel fan-out per track (asyncio.gather) so latency is bounded by
      the slowest source rather than the sum.
    * Aggressive per-artist caching in SQLite so a full library scan only
      pays the network cost once per unique artist.
    * Graceful degradation — any source failure is logged and skipped; the
      LLM gets whatever did come back.
    * Source-agnostic output schema so the prompt template stays stable
      even as we add/remove sources later.

This is a pure RAG step; no LLM calls happen here.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import aiohttp
from loguru import logger

from backend.services.database import async_session
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "SetList/1.0 (https://github.com/jvenuto80/setlist)"

MB_API = "https://musicbrainz.org/ws/2"
LASTFM_API = "https://ws.audioscrobbler.com/2.0/"
ACOUSTID_API = "https://api.acoustid.org/v2/lookup"
DISCOGS_API = "https://api.discogs.com"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API = "https://api.spotify.com/v1"

# Cache TTL — 90 days. Artist genre tagging rarely changes.
CACHE_TTL_SECONDS = 90 * 24 * 60 * 60

# Per-call network timeout. Set generously since we don't care about speed.
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)

# MusicBrainz asks clients to throttle to 1 req/sec from a given IP.
_MB_LOCK = asyncio.Lock()
_MB_LAST_CALL = 0.0

# Spotify client-credentials token cache (process-wide, refreshed on expiry).
_SPOTIFY_TOKEN: Optional[str] = None
_SPOTIFY_TOKEN_EXPIRES: float = 0.0
_SPOTIFY_LOCK = asyncio.Lock()


# ---------------------------------------------------------------------------
# Bundle schema
# ---------------------------------------------------------------------------

@dataclass
class EnrichmentBundle:
    """Aggregated metadata pulled from external sources for one artist/track."""

    # Source-specific tag lists (each can be empty)
    musicbrainz_tags: List[str] = field(default_factory=list)
    lastfm_artist_tags: List[str] = field(default_factory=list)
    lastfm_track_tags: List[str] = field(default_factory=list)
    acoustid_genres: List[str] = field(default_factory=list)
    discogs_genres: List[str] = field(default_factory=list)
    discogs_styles: List[str] = field(default_factory=list)
    spotify_artist_genres: List[str] = field(default_factory=list)
    web_snippets: List[str] = field(default_factory=list)

    # Authoritative IDs/names we discovered
    musicbrainz_artist_id: Optional[str] = None
    musicbrainz_recording_id: Optional[str] = None
    canonical_artist: Optional[str] = None
    canonical_title: Optional[str] = None
    canonical_album: Optional[str] = None
    canonical_year: Optional[str] = None

    # Bookkeeping
    sources_used: List[str] = field(default_factory=list)
    sources_failed: List[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        """Render the bundle as a human/LLM readable block for the prompt."""
        lines: List[str] = []

        if self.canonical_artist or self.canonical_title:
            lines.append(
                f"Canonical (verified): {self.canonical_artist or '?'} — "
                f"{self.canonical_title or '?'}"
                + (f" [{self.canonical_album}]" if self.canonical_album else "")
                + (f" ({self.canonical_year})" if self.canonical_year else "")
            )

        if self.musicbrainz_tags:
            lines.append(f"MusicBrainz tags: {', '.join(self.musicbrainz_tags[:15])}")
        if self.lastfm_artist_tags:
            lines.append(
                f"Last.fm artist tags: {', '.join(self.lastfm_artist_tags[:10])}"
            )
        if self.lastfm_track_tags:
            lines.append(
                f"Last.fm track tags: {', '.join(self.lastfm_track_tags[:10])}"
            )
        if self.acoustid_genres:
            lines.append(f"AcoustID genres: {', '.join(self.acoustid_genres[:10])}")
        if self.discogs_genres or self.discogs_styles:
            parts = []
            if self.discogs_genres:
                parts.append(f"genres: {', '.join(self.discogs_genres[:6])}")
            if self.discogs_styles:
                parts.append(f"styles: {', '.join(self.discogs_styles[:10])}")
            lines.append("Discogs " + " | ".join(parts))
        if self.spotify_artist_genres:
            lines.append(
                f"Spotify artist genres: {', '.join(self.spotify_artist_genres[:10])}"
            )

        if self.web_snippets:
            lines.append("Web search snippets:")
            for i, snip in enumerate(self.web_snippets[:5], 1):
                snip = snip.strip().replace("\n", " ")[:240]
                lines.append(f"  {i}. {snip}")

        if not lines:
            return "(no external enrichment data available)"

        if self.sources_used:
            lines.append(f"[sources: {', '.join(self.sources_used)}]")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Cache layer (SQLite, lives in the existing dj_tagger.db)
# ---------------------------------------------------------------------------

async def ensure_cache_table() -> None:
    """Create the artist_enrichment cache table if missing.

    Idempotent — safe to call on every app start.
    """
    async with async_session() as session:
        await session.execute(text("""
            CREATE TABLE IF NOT EXISTS artist_enrichment (
                cache_key   TEXT PRIMARY KEY,
                bundle_json TEXT NOT NULL,
                fetched_at  INTEGER NOT NULL
            )
        """))
        await session.commit()


def _cache_key(artist: str, title: Optional[str] = None) -> str:
    """Build a normalized cache key. Falls back to artist-only when title is empty."""
    a = (artist or "").strip().lower()
    t = (title or "").strip().lower()
    return f"{a}|{t}" if t else a


async def _cache_get(key: str) -> Optional[EnrichmentBundle]:
    async with async_session() as session:
        row = (await session.execute(
            text("SELECT bundle_json, fetched_at FROM artist_enrichment "
                 "WHERE cache_key = :k"),
            {"k": key},
        )).fetchone()
    if not row:
        return None
    bundle_json, fetched_at = row
    if (time.time() - fetched_at) > CACHE_TTL_SECONDS:
        return None  # stale
    try:
        data = json.loads(bundle_json)
        return EnrichmentBundle(**data)
    except Exception as e:
        logger.warning(f"Bad enrichment cache row for {key}: {e}")
        return None


async def _cache_put(key: str, bundle: EnrichmentBundle) -> None:
    async with async_session() as session:
        await session.execute(
            text("""
                INSERT INTO artist_enrichment (cache_key, bundle_json, fetched_at)
                VALUES (:k, :j, :t)
                ON CONFLICT(cache_key) DO UPDATE SET
                    bundle_json = excluded.bundle_json,
                    fetched_at  = excluded.fetched_at
            """),
            {"k": key, "j": json.dumps(bundle.to_dict()), "t": int(time.time())},
        )
        await session.commit()


async def clear_enrichment_cache() -> int:
    """Wipe the cache. Returns rows deleted."""
    async with async_session() as session:
        result = await session.execute(text("DELETE FROM artist_enrichment"))
        await session.commit()
        return result.rowcount or 0


# ---------------------------------------------------------------------------
# Individual source fetchers
# ---------------------------------------------------------------------------

async def _mb_throttle() -> None:
    """Enforce MusicBrainz's 1 req/sec policy across the whole process."""
    global _MB_LAST_CALL
    async with _MB_LOCK:
        wait = 1.05 - (time.time() - _MB_LAST_CALL)
        if wait > 0:
            await asyncio.sleep(wait)
        _MB_LAST_CALL = time.time()


async def fetch_musicbrainz(
    session: aiohttp.ClientSession,
    artist: str,
    title: Optional[str],
    bundle: EnrichmentBundle,
) -> None:
    """Look up artist + (optional) recording in MusicBrainz, collect tags."""
    if not artist:
        return
    try:
        # 1. Resolve artist -> MBID + tags
        await _mb_throttle()
        params = {
            "query": f'artist:"{artist}"',
            "fmt": "json",
            "limit": 1,
        }
        async with session.get(
            f"{MB_API}/artist", params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as r:
            if r.status != 200:
                bundle.sources_failed.append(f"musicbrainz({r.status})")
                return
            data = await r.json()

        artists = data.get("artists") or []
        if not artists:
            return
        a0 = artists[0]
        bundle.musicbrainz_artist_id = a0.get("id")
        bundle.canonical_artist = a0.get("name") or bundle.canonical_artist
        artist_tags = [t["name"] for t in (a0.get("tags") or []) if t.get("name")]

        # 2. Optionally find recording for richer per-track tags
        recording_tags: List[str] = []
        if title:
            await _mb_throttle()
            params = {
                "query": f'recording:"{title}" AND arid:{bundle.musicbrainz_artist_id}'
                         if bundle.musicbrainz_artist_id
                         else f'recording:"{title}" AND artist:"{artist}"',
                "fmt": "json",
                "limit": 1,
            }
            async with session.get(
                f"{MB_API}/recording", params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            ) as r:
                if r.status == 200:
                    rdata = await r.json()
                    recs = rdata.get("recordings") or []
                    if recs:
                        rec = recs[0]
                        bundle.musicbrainz_recording_id = rec.get("id")
                        bundle.canonical_title = rec.get("title") or bundle.canonical_title
                        recording_tags = [
                            t["name"] for t in (rec.get("tags") or [])
                            if t.get("name")
                        ]
                        releases = rec.get("releases") or []
                        if releases:
                            r0 = releases[0]
                            bundle.canonical_album = r0.get("title") or bundle.canonical_album
                            bundle.canonical_year = (
                                (r0.get("date") or "")[:4] or bundle.canonical_year
                            )

        # Merge with simple dedupe, preserving order
        seen = set()
        for t in artist_tags + recording_tags:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                bundle.musicbrainz_tags.append(t)
        bundle.sources_used.append("musicbrainz")
    except asyncio.TimeoutError:
        bundle.sources_failed.append("musicbrainz(timeout)")
    except Exception as e:
        logger.warning(f"MusicBrainz fetch failed for {artist}: {e}")
        bundle.sources_failed.append(f"musicbrainz({type(e).__name__})")


async def fetch_lastfm(
    session: aiohttp.ClientSession,
    artist: str,
    title: Optional[str],
    api_key: str,
    bundle: EnrichmentBundle,
) -> None:
    """Pull artist and track tags from Last.fm."""
    if not artist or not api_key:
        return
    try:
        # Artist tags
        params = {
            "method": "artist.gettoptags",
            "artist": artist,
            "api_key": api_key,
            "format": "json",
            "autocorrect": "1",
        }
        async with session.get(LASTFM_API, params=params) as r:
            if r.status == 200:
                data = await r.json()
                tags = (data.get("toptags") or {}).get("tag") or []
                if isinstance(tags, dict):
                    tags = [tags]
                # Last.fm tags are user-voted; filter very weak ones.
                bundle.lastfm_artist_tags = [
                    t["name"] for t in tags
                    if t.get("name") and int(t.get("count", 0)) >= 5
                ][:15]

        # Track tags (more specific to the song)
        if title:
            params = {
                "method": "track.gettoptags",
                "artist": artist,
                "track": title,
                "api_key": api_key,
                "format": "json",
                "autocorrect": "1",
            }
            async with session.get(LASTFM_API, params=params) as r:
                if r.status == 200:
                    data = await r.json()
                    tags = (data.get("toptags") or {}).get("tag") or []
                    if isinstance(tags, dict):
                        tags = [tags]
                    bundle.lastfm_track_tags = [
                        t["name"] for t in tags
                        if t.get("name") and int(t.get("count", 0)) >= 5
                    ][:15]

        if bundle.lastfm_artist_tags or bundle.lastfm_track_tags:
            bundle.sources_used.append("lastfm")
    except asyncio.TimeoutError:
        bundle.sources_failed.append("lastfm(timeout)")
    except Exception as e:
        logger.warning(f"Last.fm fetch failed for {artist}: {e}")
        bundle.sources_failed.append(f"lastfm({type(e).__name__})")


async def fetch_acoustid_genres(
    session: aiohttp.ClientSession,
    fingerprint: Optional[str],
    duration: Optional[int],
    api_key: str,
    bundle: EnrichmentBundle,
) -> None:
    """Use the AcoustID HTTP API to pull recording -> release-group genres.

    pyacoustid's `match()` doesn't return genre info; the raw `/v2/lookup`
    endpoint with `meta=recordings+releasegroups+tracks+sources` does.
    """
    if not fingerprint or not duration or not api_key:
        return
    try:
        params = {
            "client": api_key,
            "duration": str(int(duration)),
            "fingerprint": fingerprint,
            "meta": "recordings+releasegroups+tracks+compress",
            "format": "json",
        }
        async with session.post(ACOUSTID_API, data=params) as r:
            if r.status != 200:
                bundle.sources_failed.append(f"acoustid({r.status})")
                return
            data = await r.json()

        if data.get("status") != "ok":
            return

        results = data.get("results") or []
        if not results:
            return

        # Pick the highest scoring result and harvest tags from its
        # recordings and release groups.
        best = max(results, key=lambda x: x.get("score", 0))
        tags: List[str] = []
        for rec in best.get("recordings") or []:
            if not bundle.musicbrainz_recording_id:
                bundle.musicbrainz_recording_id = rec.get("id")
            if not bundle.canonical_title:
                bundle.canonical_title = rec.get("title")
            if not bundle.canonical_artist:
                artists = rec.get("artists") or []
                if artists:
                    bundle.canonical_artist = artists[0].get("name")
            for g in rec.get("tags") or []:
                if g.get("name"):
                    tags.append(g["name"])
            for rg in rec.get("releasegroups") or []:
                for g in rg.get("tags") or []:
                    if g.get("name"):
                        tags.append(g["name"])

        # Dedupe preserving order
        seen = set()
        for t in tags:
            tl = t.lower()
            if tl not in seen:
                seen.add(tl)
                bundle.acoustid_genres.append(t)

        if bundle.acoustid_genres or bundle.musicbrainz_recording_id:
            bundle.sources_used.append("acoustid")
    except asyncio.TimeoutError:
        bundle.sources_failed.append("acoustid(timeout)")
    except Exception as e:
        logger.warning(f"AcoustID enrichment failed: {e}")
        bundle.sources_failed.append(f"acoustid({type(e).__name__})")


async def fetch_searxng(
    session: aiohttp.ClientSession,
    artist: str,
    title: Optional[str],
    base_url: str,
    bundle: EnrichmentBundle,
) -> None:
    """Run a web search via a local SearXNG instance and collect snippets.

    Used as a last-resort grounding source when DB lookups returned little.
    """
    if not artist or not base_url:
        return
    try:
        # Build query — combine artist + title + 'genre' to bias results.
        q = artist
        if title:
            q += f" {title}"
        q += " genre"

        url = base_url.rstrip("/") + "/search"
        params = {
            "q": q,
            "format": "json",
            "language": "en",
            "safesearch": "0",
        }
        async with session.get(url, params=params) as r:
            if r.status != 200:
                bundle.sources_failed.append(f"searxng({r.status})")
                return
            data = await r.json()

        snippets: List[str] = []
        for res in (data.get("results") or [])[:8]:
            title_s = (res.get("title") or "").strip()
            content = (res.get("content") or "").strip()
            if not title_s and not content:
                continue
            snippets.append(f"{title_s} — {content}" if title_s else content)
        bundle.web_snippets = snippets
        if snippets:
            bundle.sources_used.append("searxng")
    except asyncio.TimeoutError:
        bundle.sources_failed.append("searxng(timeout)")
    except Exception as e:
        logger.warning(f"SearXNG fetch failed for {artist}: {e}")
        bundle.sources_failed.append(f"searxng({type(e).__name__})")


# ---------------------------------------------------------------------------
# Public API — enrich a single track
# ---------------------------------------------------------------------------

async def fetch_discogs(
    session: aiohttp.ClientSession,
    artist: str,
    title: Optional[str],
    token: str,
    bundle: EnrichmentBundle,
) -> None:
    """Search Discogs for the release and harvest its genre[] / style[] arrays.

    Discogs returns curated, human-editor-maintained genre tags per release.
    Use the `release` type because it carries both genre and style; `artist`
    type returns no genre data.
    """
    if not artist or not token:
        return
    try:
        params = {
            "q": f"{artist} {title}" if title else artist,
            "type": "release",
            "per_page": "5",
            "token": token,
        }
        headers = {"User-Agent": USER_AGENT}
        async with session.get(
            f"{DISCOGS_API}/database/search", params=params, headers=headers
        ) as r:
            if r.status != 200:
                bundle.sources_failed.append(f"discogs({r.status})")
                return
            data = await r.json()

        genres_seen, styles_seen = set(), set()
        for res in (data.get("results") or [])[:5]:
            for g in res.get("genre") or []:
                if g and g.lower() not in genres_seen:
                    genres_seen.add(g.lower())
                    bundle.discogs_genres.append(g)
            for s in res.get("style") or []:
                if s and s.lower() not in styles_seen:
                    styles_seen.add(s.lower())
                    bundle.discogs_styles.append(s)
            if not bundle.canonical_year:
                yr = res.get("year")
                if yr:
                    bundle.canonical_year = str(yr)

        if bundle.discogs_genres or bundle.discogs_styles:
            bundle.sources_used.append("discogs")
    except asyncio.TimeoutError:
        bundle.sources_failed.append("discogs(timeout)")
    except Exception as e:
        logger.warning(f"Discogs fetch failed for {artist}: {e}")
        bundle.sources_failed.append(f"discogs({type(e).__name__})")


async def _spotify_token(
    session: aiohttp.ClientSession, client_id: str, client_secret: str
) -> Optional[str]:
    """Get (or refresh) a Spotify client-credentials bearer token.

    Tokens last 1 hour; we keep one in module-level cache and reuse it.
    """
    global _SPOTIFY_TOKEN, _SPOTIFY_TOKEN_EXPIRES
    async with _SPOTIFY_LOCK:
        if _SPOTIFY_TOKEN and time.time() < _SPOTIFY_TOKEN_EXPIRES - 60:
            return _SPOTIFY_TOKEN
        import base64
        creds = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        headers = {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            async with session.post(
                SPOTIFY_TOKEN_URL,
                headers=headers,
                data={"grant_type": "client_credentials"},
            ) as r:
                if r.status != 200:
                    logger.warning(f"Spotify token request failed: HTTP {r.status}")
                    return None
                data = await r.json()
            _SPOTIFY_TOKEN = data.get("access_token")
            _SPOTIFY_TOKEN_EXPIRES = time.time() + int(data.get("expires_in", 3600))
            return _SPOTIFY_TOKEN
        except Exception as e:
            logger.warning(f"Spotify token request error: {e}")
            return None


async def fetch_spotify(
    session: aiohttp.ClientSession,
    artist: str,
    client_id: str,
    client_secret: str,
    bundle: EnrichmentBundle,
) -> None:
    """Look up the artist on Spotify and harvest its curated `genres[]` list.

    Spotify maintains a tight, well-curated genre taxonomy per artist that's
    often a stronger signal than Last.fm tags for mainstream artists.
    """
    if not artist or not client_id or not client_secret:
        return
    try:
        token = await _spotify_token(session, client_id, client_secret)
        if not token:
            bundle.sources_failed.append("spotify(no-token)")
            return
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "q": f'artist:"{artist}"',
            "type": "artist",
            "limit": "1",
        }
        async with session.get(
            f"{SPOTIFY_API}/search", params=params, headers=headers
        ) as r:
            if r.status != 200:
                bundle.sources_failed.append(f"spotify({r.status})")
                return
            data = await r.json()
        items = ((data.get("artists") or {}).get("items")) or []
        if not items:
            return
        a = items[0]
        genres = [g for g in (a.get("genres") or []) if g]
        bundle.spotify_artist_genres = genres[:15]
        if genres:
            bundle.sources_used.append("spotify")
    except asyncio.TimeoutError:
        bundle.sources_failed.append("spotify(timeout)")
    except Exception as e:
        logger.warning(f"Spotify fetch failed for {artist}: {e}")
        bundle.sources_failed.append(f"spotify({type(e).__name__})")


async def enrich_track(
    artist: str,
    title: Optional[str] = None,
    *,
    fingerprint: Optional[str] = None,
    duration: Optional[int] = None,
    lastfm_api_key: str = "",
    acoustid_api_key: str = "",
    searxng_url: str = "",
    discogs_token: str = "",
    spotify_client_id: str = "",
    spotify_client_secret: str = "",
    use_cache: bool = True,
    use_web_search: bool = True,
) -> EnrichmentBundle:
    """Fan out to all configured external sources and return an aggregated bundle.

    Caching:
        Keyed by (artist, title). Per-artist-only entries are also possible if
        title is None. AcoustID lookups are skipped on cache hit since the
        fingerprint already mapped to canonical metadata.
    """
    artist = (artist or "").strip()
    title = (title or "").strip() or None

    if not artist and not fingerprint:
        return EnrichmentBundle()

    key = _cache_key(artist, title)
    if use_cache and artist:
        cached = await _cache_get(key)
        if cached is not None:
            logger.debug(f"Enrichment cache hit: {key}")
            return cached

    bundle = EnrichmentBundle(canonical_artist=artist or None, canonical_title=title)

    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        tasks = []

        # AcoustID first when we have a fingerprint — it can give us canonical
        # artist/title that the other fetchers will then refine.
        if fingerprint and duration and acoustid_api_key:
            tasks.append(fetch_acoustid_genres(
                session, fingerprint, duration, acoustid_api_key, bundle
            ))

        if artist:
            tasks.append(fetch_musicbrainz(session, artist, title, bundle))
            if lastfm_api_key:
                tasks.append(fetch_lastfm(session, artist, title, lastfm_api_key, bundle))
            if discogs_token:
                tasks.append(fetch_discogs(session, artist, title, discogs_token, bundle))
            if spotify_client_id and spotify_client_secret:
                tasks.append(fetch_spotify(
                    session, artist, spotify_client_id, spotify_client_secret, bundle
                ))
            if use_web_search and searxng_url:
                tasks.append(fetch_searxng(session, artist, title, searxng_url, bundle))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    if artist and use_cache:
        try:
            await _cache_put(key, bundle)
        except Exception as e:
            logger.warning(f"Could not write enrichment cache for {key}: {e}")

    return bundle


# ---------------------------------------------------------------------------
# Settings helper — load enrichment config from the app settings table
# ---------------------------------------------------------------------------

async def load_enrichment_settings() -> Dict[str, Any]:
    """Return a dict of enrichment-related settings with sane defaults."""
    from backend.services.database import load_saved_settings_db
    from backend.config import settings as app_settings

    saved = await load_saved_settings_db()
    return {
        "enabled": bool(saved.get("enrichment_enabled", True)),
        "lastfm_api_key": saved.get("lastfm_api_key", ""),
        "searxng_url": saved.get("searxng_url", ""),
        "use_web_search": bool(saved.get("enrichment_web_search", True)),
        "discogs_token": saved.get("discogs_token", ""),
        "spotify_client_id": saved.get("spotify_client_id", ""),
        "spotify_client_secret": saved.get("spotify_client_secret", ""),
        # AcoustID key already lives on the app settings object
        "acoustid_api_key": saved.get("acoustid_api_key") or app_settings.acoustid_api_key or "",
    }
