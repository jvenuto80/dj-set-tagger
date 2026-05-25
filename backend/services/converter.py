"""
Audio format conversion service.

Provides FLAC → MP3 (and other lossless → lossy) conversion using ffmpeg.
Preserves all metadata tags and cover art during conversion.
Optionally replaces the original file or keeps both.

Requires ffmpeg to be installed on the system.
"""
import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

from loguru import logger


# ---------------------------------------------------------------------------
# ffmpeg binary resolution
# ---------------------------------------------------------------------------
# GUI apps launched from Finder (e.g. Tauri bundles) inherit a restricted PATH
# that does NOT include /opt/homebrew/bin or /usr/local/bin, so a bare
# `ffmpeg` lookup via subprocess will fail with FileNotFoundError even when
# the binary is installed via Homebrew. Resolve the absolute path once.
_FFMPEG_SEARCH_PATHS = [
    "/opt/homebrew/bin/ffmpeg",      # Apple Silicon Homebrew
    "/usr/local/bin/ffmpeg",         # Intel Homebrew / manual installs
    "/opt/local/bin/ffmpeg",         # MacPorts
    "/usr/bin/ffmpeg",               # system / Linux packages
    "/snap/bin/ffmpeg",              # Linux snap
]


def _resolve_ffmpeg() -> Optional[str]:
    """Find the absolute path to ffmpeg, checking PATH and common install locations."""
    env_path = os.environ.get("FFMPEG_PATH")
    if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
        return env_path
    found = shutil.which("ffmpeg")
    if found:
        return found
    for candidate in _FFMPEG_SEARCH_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


FFMPEG_BIN: Optional[str] = _resolve_ffmpeg()
if FFMPEG_BIN:
    logger.info(f"ffmpeg resolved to: {FFMPEG_BIN}")
else:
    logger.warning(
        "ffmpeg not found in PATH or common locations. "
        "Install with `brew install ffmpeg` or set FFMPEG_PATH env var."
    )


async def check_ffmpeg_available() -> bool:
    """Check if ffmpeg is installed and accessible."""
    if not FFMPEG_BIN:
        return False
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [FFMPEG_BIN, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


async def convert_to_mp3(
    filepath: str,
    bitrate: int = 320,
    replace_original: bool = False,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert an audio file to MP3 using ffmpeg.
    Preserves all metadata tags, cover art, and MIK data.

    Args:
        filepath: Path to the source audio file
        bitrate: MP3 bitrate in kbps (128, 192, 256, 320)
        replace_original: If True, delete the original after successful conversion
        output_dir: Custom output directory (default: same directory as source)

    Returns:
        {success, output_path, original_size, new_size, message}
    """
    if not os.path.exists(filepath):
        return {"success": False, "message": f"File not found: {filepath}"}

    ext = Path(filepath).suffix.lower()
    if ext == ".mp3":
        return {"success": False, "message": "File is already MP3"}

    # Validate bitrate
    bitrate = max(128, min(320, bitrate))

    # Determine output path
    source_dir = os.path.dirname(filepath)
    stem = Path(filepath).stem
    dest_dir = output_dir or source_dir
    output_path = os.path.join(dest_dir, f"{stem}.mp3")

    # Avoid overwriting existing files
    if os.path.exists(output_path):
        counter = 1
        while os.path.exists(output_path):
            output_path = os.path.join(dest_dir, f"{stem}_{counter}.mp3")
            counter += 1

    original_size = os.path.getsize(filepath)

    try:
        # ffmpeg command:
        # -i input: source file
        # -codec:a libmp3lame: use LAME MP3 encoder
        # -b:a 320k: bitrate
        # -map_metadata 0: copy all metadata from input
        # -id3v2_version 3: use ID3v2.3 (most compatible)
        # -write_id3v1 1: also write ID3v1 tags
        # -y: overwrite output without asking
        cmd = [
            FFMPEG_BIN,
            "-i", filepath,
            "-codec:a", "libmp3lame",
            "-b:a", f"{bitrate}k",
            "-map_metadata", "0",
            "-id3v2_version", "3",
            "-write_id3v1", "1",
            "-y",
            output_path,
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max per file
        )

        if result.returncode != 0:
            # Clean up partial output
            if os.path.exists(output_path):
                os.remove(output_path)
            logger.error(f"ffmpeg conversion failed: {result.stderr[:500]}")
            return {
                "success": False,
                "message": f"Conversion failed: {result.stderr[:200]}",
            }

        new_size = os.path.getsize(output_path)

        # Verify the output file is valid
        if new_size < 1024:  # Less than 1KB is suspicious
            os.remove(output_path)
            return {"success": False, "message": "Output file too small — conversion likely failed"}

        # Replace original if requested
        if replace_original:
            os.remove(filepath)
            logger.info(f"Deleted original: {filepath}")

        logger.info(
            f"Converted {filepath} → {output_path} "
            f"({original_size // 1024}KB → {new_size // 1024}KB, {bitrate}kbps)"
        )

        return {
            "success": True,
            "output_path": output_path,
            "original_path": filepath,
            "original_size": original_size,
            "new_size": new_size,
            "bitrate": bitrate,
            "space_saved": original_size - new_size if replace_original else 0,
            "message": "Conversion successful",
        }

    except subprocess.TimeoutExpired:
        if os.path.exists(output_path):
            os.remove(output_path)
        return {"success": False, "message": "Conversion timed out (>5 minutes)"}
    except Exception as e:
        if os.path.exists(output_path):
            os.remove(output_path)
        logger.error(f"Conversion error: {e}")
        return {"success": False, "message": str(e)}


# ---------------------------------------------------------------------------
# Batch conversion with progress tracking
# ---------------------------------------------------------------------------

_convert_job = {
    "running": False,
    "progress": 0,
    "total": 0,
    "converted": 0,
    "errors": 0,
    "space_saved": 0,
    "results": [],
}


def get_convert_status() -> dict:
    return _convert_job.copy()


async def batch_convert_to_mp3(
    filepaths: List[str],
    bitrate: int = 320,
    replace_original: bool = False,
    output_dir: Optional[str] = None,
):
    """
    Convert multiple files to MP3 in the background.
    Updates Track rows in the database when `replace_original=True` so the
    library doesn't end up pointing at deleted files.
    """
    global _convert_job

    _convert_job = {
        "running": True,
        "progress": 0,
        "total": len(filepaths),
        "converted": 0,
        "errors": 0,
        "space_saved": 0,
        "results": [],
    }

    try:
        for i, fp in enumerate(filepaths):
            if not _convert_job["running"]:
                break

            _convert_job["progress"] = i + 1

            try:
                result = await convert_to_mp3(
                    fp,
                    bitrate=bitrate,
                    replace_original=replace_original,
                    output_dir=output_dir,
                )
            except Exception as e:
                logger.exception(f"Unexpected error converting {fp}")
                result = {"success": False, "message": str(e)}

            _convert_job["results"].append({
                "filepath": fp,
                "success": result["success"],
                "message": result["message"],
                "output_path": result.get("output_path"),
            })

            if result["success"]:
                _convert_job["converted"] += 1
                _convert_job["space_saved"] += result.get("space_saved", 0)
                # If we replaced the original, update the Track row so the
                # library doesn't keep pointing at the deleted source file.
                if replace_original and result.get("output_path"):
                    try:
                        await _update_track_after_replace(
                            old_path=fp,
                            new_path=result["output_path"],
                        )
                    except Exception as e:
                        logger.error(f"Failed to update DB after convert {fp}: {e}")
            else:
                _convert_job["errors"] += 1

        logger.info(
            f"Batch conversion complete: {_convert_job['converted']} converted, "
            f"{_convert_job['errors']} errors, "
            f"{_convert_job['space_saved'] // (1024 * 1024)}MB saved"
        )
    except Exception:
        logger.exception("Batch conversion crashed")
    finally:
        # Always clear the running flag so a future job can start.
        _convert_job["running"] = False


async def _update_track_after_replace(old_path: str, new_path: str) -> None:
    """Point the Track row at the new MP3 file after replace-conversion."""
    # Imported lazily to avoid a circular import (services -> models -> db).
    from sqlalchemy import select
    from backend.services.database import get_db
    from backend.models.track import Track

    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.filepath == old_path))
        track = result.scalar_one_or_none()
        if track is None:
            return
        new_size = os.path.getsize(new_path) if os.path.exists(new_path) else track.file_size
        track.filepath = new_path
        track.filename = os.path.basename(new_path)
        track.file_format = "mp3"
        track.file_size = new_size
        # Fingerprint changes for the new encoded file; invalidate so the user
        # can regenerate it on the Duplicates page.
        track.fingerprint_hash = None
        track.fingerprint_raw = None
        await db.commit()


def stop_conversion():
    global _convert_job
    _convert_job["running"] = False
