"""
Mixed In Key integration service - reads and protects MIK-written tags.

Mixed In Key writes to these tag fields:
  MP3 (ID3):
    - TBPM (BPM)
    - TKEY (Initial Key, e.g. "8A", "11B")
    - TXXX:ENERGY LEVEL (Energy 1-10)
    - TXXX:MixedInKey (cue points / analysis data)
    - COMM (Comments - sometimes contains MIK data)
  FLAC/OGG (Vorbis Comments):
    - BPM
    - INITIALKEY
    - ENERGYLEVEL / ENERGY LEVEL
  M4A/AAC (MP4 atoms):
    - tmpo (BPM as integer)
    - ----:com.apple.iTunes:initialkey
    - ----:com.apple.iTunes:ENERGYLEVEL
"""
import os
from typing import Optional, Dict, Any
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from loguru import logger


# Tag frame IDs that Mixed In Key owns — SetList must never overwrite these
MIK_PROTECTED_ID3_FRAMES = {
    "TBPM",         # BPM
    "TKEY",         # Initial key
}

# TXXX frames with these descriptions are MIK-owned
MIK_PROTECTED_TXXX_DESCRIPTIONS = {
    "ENERGY LEVEL",
    "ENERGYLEVEL",
    "MixedInKey",
}

# Vorbis comment keys (FLAC, OGG) that MIK owns
MIK_PROTECTED_VORBIS_KEYS = {
    "BPM",
    "INITIALKEY",
    "INITIAL KEY",
    "ENERGYLEVEL",
    "ENERGY LEVEL",
}

# MP4 atoms that MIK owns
MIK_PROTECTED_MP4_ATOMS = {
    "tmpo",                                  # BPM
    "----:com.apple.iTunes:initialkey",      # Key
    "----:com.apple.iTunes:INITIALKEY",
    "----:com.apple.iTunes:ENERGYLEVEL",     # Energy
    "----:com.apple.iTunes:ENERGY LEVEL",
}


def read_mik_tags(filepath: str) -> Dict[str, Any]:
    """
    Read Mixed In Key-specific tags from an audio file.
    
    Returns dict with keys: bpm, key, energy, raw_frames
    - bpm: float or None
    - key: str or None (e.g. "8A", "11B", "Gm")
    - energy: int or None (1-10)
    - raw_frames: dict of all MIK-related raw tag data for reference
    """
    result = {
        "bpm": None,
        "key": None,
        "energy": None,
        "raw_frames": {},
    }

    if not os.path.exists(filepath):
        return result

    ext = Path(filepath).suffix.lower()

    try:
        if ext == ".mp3":
            result = _read_mik_id3(filepath)
        elif ext == ".flac":
            result = _read_mik_vorbis(filepath, fmt="flac")
        elif ext == ".ogg":
            result = _read_mik_vorbis(filepath, fmt="ogg")
        elif ext in (".m4a", ".aac", ".mp4"):
            result = _read_mik_mp4(filepath)
    except Exception as e:
        logger.debug(f"Could not read MIK tags from {filepath}: {e}")

    return result


def _read_mik_id3(filepath: str) -> Dict[str, Any]:
    """Read MIK tags from ID3 (MP3) file."""
    result = {"bpm": None, "key": None, "energy": None, "raw_frames": {}}

    try:
        audio = ID3(filepath)
    except ID3NoHeaderError:
        return result

    # BPM
    if "TBPM" in audio:
        raw = str(audio["TBPM"])
        result["raw_frames"]["TBPM"] = raw
        try:
            result["bpm"] = float(raw)
        except ValueError:
            pass

    # Key
    if "TKEY" in audio:
        raw = str(audio["TKEY"])
        result["raw_frames"]["TKEY"] = raw
        result["key"] = raw.strip()

    # TXXX frames (energy, cue data)
    for frame_id, frame in audio.items():
        if frame_id.startswith("TXXX:"):
            desc = frame.desc if hasattr(frame, "desc") else frame_id[5:]
            if desc.upper() in {d.upper() for d in MIK_PROTECTED_TXXX_DESCRIPTIONS}:
                raw = str(frame)
                result["raw_frames"][f"TXXX:{desc}"] = raw
                if desc.upper() in ("ENERGY LEVEL", "ENERGYLEVEL"):
                    try:
                        result["energy"] = int(raw)
                    except ValueError:
                        pass

    return result


def _read_mik_vorbis(filepath: str, fmt: str = "flac") -> Dict[str, Any]:
    """Read MIK tags from Vorbis comments (FLAC/OGG)."""
    result = {"bpm": None, "key": None, "energy": None, "raw_frames": {}}

    if fmt == "flac":
        audio = FLAC(filepath)
    else:
        audio = OggVorbis(filepath)

    for key in MIK_PROTECTED_VORBIS_KEYS:
        # Vorbis keys are case-insensitive; try exact and upper
        for try_key in (key, key.upper(), key.lower()):
            vals = audio.get(try_key)
            if vals:
                raw = vals[0] if isinstance(vals, list) else str(vals)
                result["raw_frames"][key] = raw

                if key in ("BPM",):
                    try:
                        result["bpm"] = float(raw)
                    except ValueError:
                        pass
                elif key in ("INITIALKEY", "INITIAL KEY"):
                    result["key"] = raw.strip()
                elif key in ("ENERGYLEVEL", "ENERGY LEVEL"):
                    try:
                        result["energy"] = int(raw)
                    except ValueError:
                        pass
                break

    return result


def _read_mik_mp4(filepath: str) -> Dict[str, Any]:
    """Read MIK tags from MP4/M4A atoms."""
    result = {"bpm": None, "key": None, "energy": None, "raw_frames": {}}

    audio = MP4(filepath)
    tags = audio.tags or {}

    # BPM (tmpo is stored as list of ints)
    if "tmpo" in tags:
        val = tags["tmpo"]
        if isinstance(val, list) and val:
            result["bpm"] = float(val[0])
            result["raw_frames"]["tmpo"] = val[0]

    # Freeform iTunes atoms
    for atom in MIK_PROTECTED_MP4_ATOMS:
        if atom == "tmpo":
            continue
        if atom in tags:
            val = tags[atom]
            if isinstance(val, list) and val:
                raw = val[0]
                # Freeform atoms are bytes
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                result["raw_frames"][atom] = raw

                if "initialkey" in atom.lower():
                    result["key"] = raw.strip()
                elif "energylevel" in atom.lower() or "energy level" in atom.lower():
                    try:
                        result["energy"] = int(raw.strip())
                    except ValueError:
                        pass

    return result


def get_protected_frame_ids(filepath: str) -> set:
    """
    Return the set of tag frame IDs that are MIK-protected for a given file.
    The tagger should skip writing to any of these.
    """
    ext = Path(filepath).suffix.lower()

    if ext == ".mp3":
        # Build full set including any TXXX frames present
        protected = set(MIK_PROTECTED_ID3_FRAMES)
        try:
            audio = ID3(filepath)
            for frame_id, frame in audio.items():
                if frame_id.startswith("TXXX:"):
                    desc = frame.desc if hasattr(frame, "desc") else frame_id[5:]
                    if desc.upper() in {d.upper() for d in MIK_PROTECTED_TXXX_DESCRIPTIONS}:
                        protected.add(frame_id)
        except (ID3NoHeaderError, Exception):
            pass
        return protected

    elif ext == ".flac":
        return {k.upper() for k in MIK_PROTECTED_VORBIS_KEYS}

    elif ext == ".ogg":
        return {k.upper() for k in MIK_PROTECTED_VORBIS_KEYS}

    elif ext in (".m4a", ".aac", ".mp4"):
        return set(MIK_PROTECTED_MP4_ATOMS)

    return set()
