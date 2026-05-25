"""
Advanced duplicate detection service.

Extends the existing exact-hash duplicate detection with:
  - Near-duplicate detection via Chromaprint fingerprint similarity
  - Quality-based resolution (bitrate, format, file size)
  - LLM-assisted disambiguation for remixes/edits/versions
"""
import asyncio
import json
import re
import struct
from collections import defaultdict
from typing import Optional, List, Dict, Any, Tuple

from loguru import logger

try:
    import ollama as ollama_sdk
except ImportError:
    ollama_sdk = None


# ---------------------------------------------------------------------------
# Chromaprint similarity scoring
# ---------------------------------------------------------------------------

def decode_chromaprint(fingerprint_str: str) -> List[int]:
    """
    Decode a base64-encoded Chromaprint fingerprint into a list of 32-bit integers.
    """
    import base64

    try:
        # Chromaprint fingerprints are base64-encoded, prefixed with algorithm byte
        raw = base64.b64decode(fingerprint_str)
        if len(raw) < 4:
            return []
        # Skip algorithm byte (first byte), then read as unsigned 32-bit ints
        # Actually fpcalc -json returns the raw base64 fingerprint
        # The fingerprint is a sequence of 32-bit unsigned integers
        algorithm = raw[0]
        data = raw[1:]
        count = len(data) // 4
        values = list(struct.unpack(f'<{count}I', data[:count * 4]))
        return values
    except Exception:
        # fpcalc may return a comma-separated integer string
        try:
            return [int(x) for x in fingerprint_str.split(',') if x.strip()]
        except Exception:
            return []


def chromaprint_similarity(fp1: str, fp2: str) -> float:
    """
    Compute similarity between two Chromaprint fingerprints.

    Uses bit-level comparison of the 32-bit integer arrays.
    Returns a similarity score between 0.0 (completely different) and 1.0 (identical).
    """
    ints1 = decode_chromaprint(fp1)
    ints2 = decode_chromaprint(fp2)

    if not ints1 or not ints2:
        return 0.0

    # Compare overlapping region
    min_len = min(len(ints1), len(ints2))
    if min_len == 0:
        return 0.0

    # Count matching bits
    total_bits = 0
    matching_bits = 0

    for i in range(min_len):
        xor = ints1[i] ^ ints2[i]
        # Count differing bits
        diff = bin(xor).count('1')
        matching_bits += 32 - diff
        total_bits += 32

    # Penalize length difference
    max_len = max(len(ints1), len(ints2))
    length_penalty = min_len / max_len

    similarity = (matching_bits / total_bits) * length_penalty if total_bits > 0 else 0.0
    return similarity


# ---------------------------------------------------------------------------
# Quality scoring for keep/discard decisions
# ---------------------------------------------------------------------------

# Format quality ranking (higher = better)
FORMAT_QUALITY = {
    "flac": 100,
    "wav": 95,
    "aac": 70,
    "m4a": 70,
    "ogg": 65,
    "mp3": 60,
}


def compute_quality_score(track: Dict[str, Any]) -> int:
    """
    Compute a quality score for a track to decide which duplicate to keep.
    Higher is better. Considers: format, bitrate, file size, metadata completeness.
    """
    score = 0

    # Format quality (0-100)
    fmt = (track.get("file_format") or "").lower().lstrip(".")
    score += FORMAT_QUALITY.get(fmt, 50)

    # Bitrate (0-50 points)
    bitrate = track.get("bitrate") or 0
    if bitrate > 0:
        # Normalize: 320kbps mp3 = 50pts, 128kbps = 20pts
        score += min(50, int(bitrate / 6400))  # 320000 / 6400 = 50

    # File size as tiebreaker (0-20 points)
    file_size = track.get("file_size") or 0
    if file_size > 0:
        # Larger files typically mean better quality for same format
        score += min(20, int(file_size / (5 * 1024 * 1024)))  # 100MB = 20pts

    # Metadata completeness bonus (0-30 points)
    for field in ("title", "artist", "album", "genre", "year"):
        if track.get(field):
            score += 6

    return score


def recommend_keep(tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Given a group of duplicate tracks, recommend which one to keep.
    Returns {keep: track_dict, discard: [track_dicts], reason: str}
    """
    if not tracks:
        return {"keep": None, "discard": [], "reason": "No tracks"}

    scored = [(compute_quality_score(t), t) for t in tracks]
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best_track = scored[0]
    discards = [t for _, t in scored[1:]]

    # Build reason
    reasons = []
    best_fmt = (best_track.get("file_format") or "unknown").upper()
    best_bitrate = best_track.get("bitrate") or 0

    if best_fmt in ("FLAC", "WAV"):
        reasons.append(f"lossless format ({best_fmt})")
    elif best_bitrate:
        reasons.append(f"highest bitrate ({best_bitrate // 1000}kbps {best_fmt})")
    else:
        reasons.append(f"best quality score ({best_score})")

    best_size = best_track.get("file_size") or 0
    if best_size:
        reasons.append(f"largest file ({best_size / (1024 * 1024):.1f}MB)")

    return {
        "keep": {**best_track, "quality_score": best_score},
        "discard": [{**t, "quality_score": s} for s, t in scored[1:]],
        "reason": "; ".join(reasons),
    }


# ---------------------------------------------------------------------------
# Near-duplicate finder
# ---------------------------------------------------------------------------

async def find_near_duplicates(
    tracks: List[Dict[str, Any]],
    similarity_threshold: float = 0.85,
    duration_tolerance_pct: float = 0.10,
) -> List[Dict[str, Any]]:
    """
    Find near-duplicate tracks using fingerprint similarity + duration comparison.

    Requires tracks to have 'fingerprint_raw' (the Chromaprint string) and 'duration'.

    Args:
        tracks: List of track dicts
        similarity_threshold: Minimum fingerprint similarity (0-1) to consider as near-duplicate
        duration_tolerance_pct: Maximum duration difference as fraction (0.10 = 10%)

    Returns:
        List of near-duplicate group dicts:
        {
            similarity: float,
            type: "exact" | "near" | "remix" | "edit",
            recommendation: {keep, discard, reason},
            tracks: [track_dicts],
        }
    """
    # Filter to tracks that have raw fingerprints
    fp_tracks = [t for t in tracks if t.get("fingerprint_raw")]

    if len(fp_tracks) < 2:
        return []

    logger.info(f"Checking {len(fp_tracks)} tracks for near-duplicates (threshold={similarity_threshold})")

    groups: List[Dict[str, Any]] = []
    used_ids = set()

    # Compare pairs — O(n²) but filtered by duration to reduce work
    # Group by rough duration buckets first
    duration_buckets: Dict[int, List[Dict]] = defaultdict(list)
    for t in fp_tracks:
        dur = t.get("duration") or 0
        # 30-second buckets
        bucket = int(dur // 30)
        duration_buckets[bucket].append(t)

    for bucket_key, bucket_tracks in duration_buckets.items():
        # Also check adjacent buckets for edge cases
        adjacent = []
        for adj_key in (bucket_key - 1, bucket_key, bucket_key + 1):
            adjacent.extend(duration_buckets.get(adj_key, []))

        # Deduplicate
        seen_adj_ids = set()
        unique_adjacent = []
        for t in adjacent:
            if t["id"] not in seen_adj_ids:
                seen_adj_ids.add(t["id"])
                unique_adjacent.append(t)

        for i, t1 in enumerate(unique_adjacent):
            if t1["id"] in used_ids:
                continue

            for j in range(i + 1, len(unique_adjacent)):
                t2 = unique_adjacent[j]
                if t2["id"] in used_ids:
                    continue

                # Duration check first (cheap)
                dur1 = t1.get("duration") or 0
                dur2 = t2.get("duration") or 0
                if dur1 > 0 and dur2 > 0:
                    diff = abs(dur1 - dur2) / max(dur1, dur2)
                    if diff > duration_tolerance_pct:
                        continue

                # Fingerprint similarity (expensive)
                sim = chromaprint_similarity(t1["fingerprint_raw"], t2["fingerprint_raw"])

                if sim >= similarity_threshold:
                    # Determine type
                    if sim >= 0.98:
                        dup_type = "exact"
                    elif sim >= 0.92:
                        dup_type = "near"
                    elif _looks_like_remix(t1, t2):
                        dup_type = "remix"
                    else:
                        dup_type = "edit"

                    group_tracks = [t1, t2]
                    rec = recommend_keep(group_tracks)

                    groups.append({
                        "similarity": round(sim, 4),
                        "type": dup_type,
                        "recommendation": rec,
                        "tracks": group_tracks,
                    })

                    used_ids.add(t1["id"])
                    used_ids.add(t2["id"])
                    break  # Move to next t1

    logger.info(f"Found {len(groups)} near-duplicate groups")
    return groups


def _looks_like_remix(t1: Dict, t2: Dict) -> bool:
    """Heuristic: check if filenames/titles suggest remix/edit variants."""
    remix_markers = (
        "remix", "rmx", "edit", "mix", "dub", "radio edit",
        "extended", "club mix", "original mix", "vip", "bootleg",
        "rework", "remaster", "acoustic", "instrumental", "live",
    )
    for t in (t1, t2):
        name = (t.get("title") or t.get("filename") or "").lower()
        if any(m in name for m in remix_markers):
            return True
    return False


# ---------------------------------------------------------------------------
# LLM-assisted duplicate resolution
# ---------------------------------------------------------------------------

RESOLVE_PROMPT = """You are a music library management assistant. I have found duplicate audio files and need help deciding which to keep.

Duplicate group:
{tracks_json}

For each track I show: filename, title, artist, album, format, bitrate, file size, duration, quality score.

Rules:
1. Prefer lossless formats (FLAC, WAV) over lossy (MP3, AAC, OGG).
2. For same format, prefer higher bitrate.
3. If one is a remix/edit and the other is the original, suggest keeping BOTH.
4. If metadata is more complete on one version, prefer that one.
5. Consider filename — it may indicate "radio edit", "extended mix", "remaster", etc.

Respond with ONLY valid JSON:
{{"keep": [list of track IDs to keep], "delete": [list of track IDs to delete], "reasoning": "explanation", "are_different_versions": false}}

If the tracks are genuinely different versions (remix vs original, live vs studio), set are_different_versions to true and put ALL IDs in "keep"."""


class DuplicateResolver:
    """Use Ollama to help resolve ambiguous duplicate groups."""

    def __init__(
        self,
        model: str = "qwen3:32b",
        host: str = "http://localhost:11434",
    ):
        self.model = model
        self.host = host
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if ollama_sdk is None:
                raise RuntimeError("ollama package not installed")
            self._client = ollama_sdk.Client(host=self.host)
        return self._client

    async def resolve(
        self, tracks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Ask LLM which duplicates to keep/discard.

        Returns {keep: [ids], delete: [ids], reasoning: str, are_different_versions: bool}
        """
        # Build compact track info for prompt
        tracks_info = []
        for t in tracks:
            tracks_info.append({
                "id": t.get("id"),
                "filename": t.get("filename"),
                "title": t.get("title"),
                "artist": t.get("artist"),
                "album": t.get("album"),
                "format": t.get("file_format"),
                "bitrate": t.get("bitrate"),
                "file_size_mb": round((t.get("file_size") or 0) / (1024 * 1024), 1),
                "duration_sec": round(t.get("duration") or 0, 1),
                "quality_score": t.get("quality_score", 0),
            })

        prompt = RESOLVE_PROMPT.format(tracks_json=json.dumps(tracks_info, indent=2))

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.2, "num_predict": 512},
                    format="json",
                ),
            )

            content = response.get("message", {}).get("content", "")
            if hasattr(response, "message"):
                content = response.message.content

            return self._parse_response(content, tracks)

        except Exception as e:
            logger.error(f"LLM duplicate resolution error: {e}")
            # Fall back to quality-based
            rec = recommend_keep(tracks)
            return {
                "keep": [rec["keep"]["id"]] if rec["keep"] else [],
                "delete": [t["id"] for t in rec["discard"]],
                "reasoning": f"Automatic (LLM unavailable): {rec['reason']}",
                "are_different_versions": False,
            }

    def _parse_response(
        self, content: str, tracks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Parse LLM response."""
        fallback_rec = recommend_keep(tracks)
        fallback = {
            "keep": [fallback_rec["keep"]["id"]] if fallback_rec["keep"] else [],
            "delete": [t["id"] for t in fallback_rec["discard"]],
            "reasoning": f"Fallback: {fallback_rec['reason']}",
            "are_different_versions": False,
        }

        try:
            text = content.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            try:
                data = json.loads(text.strip())
            except json.JSONDecodeError:
                match = re.search(r"\{[\s\S]*\}", text)
                if match:
                    data = json.loads(match.group())
                else:
                    return fallback

            valid_ids = {t["id"] for t in tracks}
            keep_ids = [i for i in data.get("keep", []) if i in valid_ids]
            delete_ids = [i for i in data.get("delete", []) if i in valid_ids]

            return {
                "keep": keep_ids,
                "delete": delete_ids,
                "reasoning": data.get("reasoning", ""),
                "are_different_versions": data.get("are_different_versions", False),
            }

        except Exception as e:
            logger.warning(f"Error parsing duplicate resolution: {e}")
            return fallback


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_resolver: Optional[DuplicateResolver] = None


def get_duplicate_resolver() -> DuplicateResolver:
    global _resolver
    if _resolver is None:
        _resolver = DuplicateResolver()
    return _resolver
