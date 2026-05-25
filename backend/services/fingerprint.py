"""
Audio fingerprinting service for track identification and duplicate detection.
Uses Chromaprint for fingerprint generation and AcoustID for identification.
"""

import asyncio
import hashlib
import os
import shutil
import subprocess
from typing import Optional
from loguru import logger

try:
    import acoustid
    ACOUSTID_AVAILABLE = True
except ImportError:
    ACOUSTID_AVAILABLE = False
    logger.warning("pyacoustid not installed - AcoustID features disabled")


# ---------------------------------------------------------------------------
# fpcalc binary resolution
# ---------------------------------------------------------------------------
# GUI apps launched from Finder (e.g. Tauri bundles) inherit a restricted PATH
# that does NOT include /opt/homebrew/bin or /usr/local/bin, so a bare
# `fpcalc` lookup via subprocess will fail with FileNotFoundError even when
# the binary is installed via Homebrew. Resolve the absolute path once.
_FPCALC_SEARCH_PATHS = [
    "/opt/homebrew/bin/fpcalc",      # Apple Silicon Homebrew
    "/usr/local/bin/fpcalc",         # Intel Homebrew / manual installs
    "/opt/local/bin/fpcalc",         # MacPorts
    "/usr/bin/fpcalc",               # system / Linux packages
    "/snap/bin/fpcalc",              # Linux snap
]


def _resolve_fpcalc() -> Optional[str]:
    """Find the absolute path to fpcalc, checking PATH and common install locations."""
    # 1. Explicit override
    env_path = os.environ.get("FPCALC_PATH")
    if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
        return env_path
    # 2. PATH lookup (works when launched from a shell)
    found = shutil.which("fpcalc")
    if found:
        return found
    # 3. Known install locations (for GUI-launched bundled apps)
    for candidate in _FPCALC_SEARCH_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


FPCALC_BIN: Optional[str] = _resolve_fpcalc()
if FPCALC_BIN:
    logger.info(f"fpcalc resolved to: {FPCALC_BIN}")
else:
    logger.warning(
        "fpcalc (Chromaprint) not found in PATH or common locations. "
        "Install with `brew install chromaprint` or set FPCALC_PATH env var."
    )


async def generate_fingerprint(file_path: str) -> Optional[tuple[int, str]]:
    """
    Generate audio fingerprint using fpcalc (Chromaprint).
    
    Returns:
        Tuple of (duration_seconds, fingerprint_string) or None if failed
    """
    if not FPCALC_BIN:
        logger.error("fpcalc binary not available; cannot generate fingerprint")
        return None
    try:
        # Run fpcalc in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [FPCALC_BIN, '-json', file_path],
                capture_output=True,
                text=True,
                timeout=60
            )
        )
        
        if result.returncode != 0:
            logger.error(f"fpcalc failed for {file_path}: {result.stderr}")
            return None
        
        import json
        data = json.loads(result.stdout)
        duration = int(data.get('duration', 0))
        fingerprint = data.get('fingerprint', '')
        
        if not fingerprint:
            logger.warning(f"No fingerprint generated for {file_path}")
            return None
            
        return (duration, fingerprint)
        
    except subprocess.TimeoutExpired:
        logger.error(f"fpcalc timeout for {file_path}")
        return None
    except Exception as e:
        logger.error(f"Error generating fingerprint for {file_path}: {e}")
        return None


def fingerprint_to_hash(fingerprint: str) -> str:
    """
    Convert a fingerprint to a shorter hash for storage and comparison.
    Uses SHA256 truncated to 32 chars for reasonable uniqueness.
    """
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:32]


async def identify_with_acoustid(
    file_path: str,
    api_key: str
) -> Optional[dict]:
    """
    Identify a track using AcoustID API.
    
    Returns:
        Dict with recording info or None if not found
        {
            'title': str,
            'artist': str,
            'album': str,
            'musicbrainz_id': str,
            'score': float (0-1)
        }
    """
    if not ACOUSTID_AVAILABLE:
        logger.error("pyacoustid not available")
        return None
    
    if not api_key:
        logger.error("AcoustID API key not configured")
        return None
    
    try:
        # Run in thread pool since it's blocking I/O
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: list(acoustid.match(
                api_key,
                file_path,
                meta='recordings releases'
            ))
        )
        
        if not results:
            logger.info(f"No AcoustID match found for {file_path}")
            return None
        
        # Get best match
        best_score = 0
        best_result = None
        
        for score, recording_id, title, artist in results:
            if score > best_score:
                best_score = score
                best_result = {
                    'title': title,
                    'artist': artist,
                    'musicbrainz_recording_id': recording_id,
                    'score': score
                }
        
        if best_result and best_score >= 0.5:  # Only return if confidence >= 50%
            logger.info(f"AcoustID match for {file_path}: {best_result['artist']} - {best_result['title']} (score: {best_score:.2f})")
            return best_result
        else:
            logger.info(f"No confident AcoustID match for {file_path} (best score: {best_score:.2f})")
            return None
            
    except acoustid.NoBackendError:
        logger.error("Chromaprint not found - install libchromaprint-tools")
        return None
    except acoustid.FingerprintGenerationError as e:
        logger.error(f"Could not generate fingerprint for {file_path}: {e}")
        return None
    except acoustid.WebServiceError as e:
        logger.error(f"AcoustID API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error identifying track {file_path}: {e}")
        return None


async def identify_with_acoustid_extended(
    file_path: str,
    api_key: str
) -> Optional[dict]:
    """
    Identify a track using AcoustID API with extended metadata from MusicBrainz.

    Returns more detailed info including album, year, etc.

    Raises:
        RuntimeError: with a user-actionable message when fingerprinting or the
            AcoustID API call fails for a reason the user can fix (missing
            fpcalc binary, missing pyacoustid module, network/API errors).
    """
    if not ACOUSTID_AVAILABLE:
        raise RuntimeError(
            "pyacoustid Python module is not installed. "
            "Reinstall the backend dependencies (pip install -r requirements.txt)."
        )

    if not api_key:
        raise RuntimeError("AcoustID API key is empty.")

    if not FPCALC_BIN:
        raise RuntimeError(
            "fpcalc (Chromaprint) binary not found. Install it with "
            "`brew install chromaprint` (macOS) or set the FPCALC_PATH env var."
        )

    if not os.path.exists(file_path):
        raise RuntimeError(f"Audio file not found on disk: {file_path}")

    # Generate fingerprint using our resolved absolute fpcalc path (works inside
    # Tauri sidecars where PATH does not include /opt/homebrew/bin)
    fp = await generate_fingerprint(file_path)
    if not fp:
        raise RuntimeError(
            "Failed to generate audio fingerprint. Check the backend log for "
            "the fpcalc error (the file may be unreadable or in an unsupported format)."
        )
    duration, fingerprint = fp

    try:
        loop = asyncio.get_event_loop()

        def do_lookup():
            return acoustid.lookup(
                api_key,
                fingerprint,
                duration,
                meta='recordings releases releasegroups'
            )

        try:
            response = await loop.run_in_executor(None, do_lookup)
        except Exception as e:
            # Network error, invalid API key, AcoustID 5xx, etc.
            logger.error(f"AcoustID lookup error: {e}")
            raise RuntimeError(f"AcoustID API request failed: {e}")

        if not response or 'results' not in response:
            logger.warning(f"No AcoustID 'results' key for {file_path}. Raw response: {response!r}")
            status = (response or {}).get('status')
            err = (response or {}).get('error') or {}
            if status and status != 'ok':
                raise RuntimeError(
                    f"AcoustID returned status={status!r} "
                    f"({err.get('message') or err or 'no message'}). "
                    f"Check your API key in Settings."
                )
            return None

        results = response['results']
        if not results:
            logger.warning(f"AcoustID returned 0 results for {file_path}. Raw response: {response!r}")
            return None

        # Log all results for debugging
        logger.info(f"AcoustID returned {len(results)} results for {file_path}")

        # Find best match with recordings
        for result in sorted(results, key=lambda x: x.get('score', 0), reverse=True):
            score = result.get('score', 0)
            logger.info(f"  Result score: {score:.2f}")

            if score < 0.5:
                logger.info(f"  Skipping low score result")
                continue

            recordings = result.get('recordings', [])
            if not recordings:
                logger.info(f"  No recordings in this result")
                continue

            # Log all recordings for this result
            logger.info(f"  Found {len(recordings)} recordings:")
            for i, rec in enumerate(recordings[:5]):  # Log first 5
                rec_artists = rec.get('artists', [])
                rec_artist = rec_artists[0]['name'] if rec_artists else 'Unknown'
                rec_title = rec.get('title', 'Unknown')
                logger.info(f"    {i+1}. {rec_artist} - {rec_title}")

            # Return ALL recordings so user can pick the right one
            all_recordings = []
            for rec in recordings:
                rec_artists = rec.get('artists', [])
                artist_name = rec_artists[0]['name'] if rec_artists else None

                # Try to get album info from releases
                releases = rec.get('releases', [])
                album_name = None
                year = None

                if releases:
                    release = releases[0]
                    album_name = release.get('title')
                    date = release.get('date', {})
                    if date:
                        year = str(date.get('year', ''))

                all_recordings.append({
                    'title': rec.get('title'),
                    'artist': artist_name,
                    'album': album_name,
                    'year': year,
                    'musicbrainz_recording_id': rec.get('id'),
                })

            # Return best guess as primary, but include alternatives
            primary = all_recordings[0] if all_recordings else None
            if primary:
                primary['score'] = score
                primary['alternatives'] = all_recordings[1:10] if len(all_recordings) > 1 else []

            return primary

        return None

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Error in extended AcoustID lookup: {e}")
        raise RuntimeError(f"Unexpected error during AcoustID lookup: {e}")


async def find_duplicates_by_fingerprint(
    tracks: list,
    threshold: float = 0.9
) -> list[list[dict]]:
    """
    Find duplicate tracks based on fingerprint similarity.
    
    Args:
        tracks: List of track dicts with 'id', 'file_path', 'fingerprint_hash' fields
        threshold: Similarity threshold (0-1) for considering tracks as duplicates
    
    Returns:
        List of duplicate groups, where each group is a list of track dicts
    """
    # Group by fingerprint hash for exact duplicates
    hash_groups = {}
    
    for track in tracks:
        fp_hash = track.get('fingerprint_hash')
        if not fp_hash:
            continue
            
        if fp_hash not in hash_groups:
            hash_groups[fp_hash] = []
        hash_groups[fp_hash].append(track)
    
    # Return groups with more than one track
    duplicates = [
        group for group in hash_groups.values()
        if len(group) > 1
    ]
    
    return duplicates


async def check_fpcalc_available() -> bool:
    """Check if fpcalc (Chromaprint) is available."""
    if not FPCALC_BIN:
        return False
    try:
        result = subprocess.run(
            [FPCALC_BIN, '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False
