"""
String matching helpers tuned for DJ / electronic music track identification.

The default rapidfuzz ``token_set_ratio`` over-matches for this domain: because
it scores on the intersection of token sets, "Track Name (Original Mix)" scores
100 against "Track Name (Reece Low Remix)" - the remix descriptor, which is the
*most* important distinguishing signal for a DJ, is ignored.

This module addresses that with:
  * Unicode transliteration (unidecode) so accented artist names normalise.
  * A title comparison that separates the *base title* from the *version /
    remix descriptor* and scores them independently, penalising a missing or
    mismatched descriptor instead of discarding it.
  * Levenshtein-based similarity (jellyfish) with a phonetic (metaphone)
    tiebreaker for artist names.
  * A structured filename parser that pulls out artist, base title, version,
    featured artists and catalogue number.

All functions are pure and deterministic (no I/O), so they are unit tested
directly.
"""
import re
from typing import Dict, Optional, Tuple

from unidecode import unidecode
import jellyfish


_AUDIO_EXT_RE = re.compile(r"\.(mp3|flac|wav|m4a|aac|ogg)$", re.IGNORECASE)
_BRACKET_RE = re.compile(r"[\(\[\{]([^\)\]\}]*)[\)\]\}]")
_PAREN_STRIP_RE = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_FEAT_RE = re.compile(
    r"\b(?:feat|ft|featuring|with)\b\.?\s+(.+?)(?:\s*[\(\[\{]|$)",
    re.IGNORECASE,
)
_CATALOG_RE = re.compile(r"\b([A-Z]{2,6}[\s\-]?\d{2,5})\b")

# Keywords that mark a bracketed/dashed segment as a *version* descriptor.
_VERSION_KEYWORDS = {
    "remix", "rmx", "edit", "mix", "dub", "vip", "bootleg", "rework",
    "flip", "version", "instrumental", "radio", "extended", "club",
    "rerub", "refix", "remaster", "remastered", "acoustic", "live",
}

# Descriptors that are equivalent to "no special version" (the canonical track).
_ORIGINAL_DESCRIPTORS = {"", "original", "original mix", "extended mix", "extended"}


def normalize(s: str) -> str:
    """Lowercase, transliterate and strip a string down to alphanumeric tokens."""
    if not s:
        return ""
    s = unidecode(s)
    s = s.lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def levenshtein_sim(a: str, b: str) -> float:
    """Normalised Levenshtein similarity in [0, 1] (operates on normalized text)."""
    a, b = normalize(a), normalize(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    distance = jellyfish.levenshtein_distance(a, b)
    return 1.0 - distance / max(len(a), len(b))


def split_version(title: str) -> Tuple[str, str]:
    """
    Split a title into (base_title, version_descriptor).

    The version is taken from bracketed segments that contain a version keyword
    (e.g. "(Reece Low Remix)", "[Extended Mix]"). Bracketed segments that are
    *not* versions (e.g. a label name) are dropped from the base but not treated
    as a version descriptor.
    """
    if not title:
        return "", ""

    versions = []
    for segment in _BRACKET_RE.findall(title):
        seg_norm = normalize(segment)
        if any(kw in seg_norm.split() for kw in _VERSION_KEYWORDS):
            versions.append(segment.strip())

    base = _PAREN_STRIP_RE.sub(" ", title)
    base = re.sub(r"\s+", " ", base).strip()
    version = " ".join(versions).strip()
    return base, version


def _canon_version(version: str) -> str:
    """Map 'original mix'/'' and friends to a single canonical empty descriptor."""
    norm = normalize(version)
    if norm in _ORIGINAL_DESCRIPTORS:
        return ""
    return norm


def title_similarity(a: str, b: str) -> float:
    """
    Compare two track titles, returning a score in [0, 100].

    Base title and version descriptor are scored separately so that a remix is
    not treated as identical to the original (or to a different remix).
    """
    base_a, ver_a = split_version(a)
    base_b, ver_b = split_version(b)

    base_sim = levenshtein_sim(base_a, base_b)

    canon_a, canon_b = _canon_version(ver_a), _canon_version(ver_b)
    if canon_a == canon_b:
        ver_sim = 1.0
    elif not canon_a or not canon_b:
        # One side is the original, the other a specific version - strong penalty.
        ver_sim = 0.4
    else:
        ver_sim = levenshtein_sim(canon_a, canon_b)

    return round((base_sim * 0.7 + ver_sim * 0.3) * 100, 1)


def normalize_artist(artist: str) -> str:
    """Normalise an artist string, stripping featured-artist clauses."""
    if not artist:
        return ""
    artist = _FEAT_RE.sub(" ", artist)
    return normalize(artist)


def artist_similarity(a: str, b: str) -> float:
    """Compare two artist names, returning a score in [0, 100] with phonetic tiebreak."""
    na, nb = normalize_artist(a), normalize_artist(b)
    if not na or not nb:
        return 0.0

    sim = levenshtein_sim(na, nb)

    # Phonetic tiebreaker: matching metaphone codes lift near-misses (spelling
    # variants of the same name) without overriding a strong literal match.
    try:
        if jellyfish.metaphone(na) == jellyfish.metaphone(nb):
            sim = max(sim, 0.9)
    except Exception:
        pass

    return round(sim * 100, 1)


def extract_feat(text: str) -> Optional[str]:
    """Extract featured artist(s) from a title/filename, if present."""
    match = _FEAT_RE.search(text or "")
    if match:
        return match.group(1).strip() or None
    return None


def extract_catalog(text: str) -> Optional[str]:
    """Extract a catalogue number (e.g. RP003, ABC-1234) from text, if present."""
    match = _CATALOG_RE.search(text or "")
    if match:
        return match.group(1).strip()
    return None


def parse_filename(filename: str) -> Dict[str, Optional[str]]:
    """
    Parse a DJ track filename into structured fields.

    Returns a dict with: artist, title, base_title, version, feat, catalog.
    Handles the common "Artist - Title (Version)" convention and falls back to
    treating the whole name as a title when no " - " separator is present.
    """
    name = _AUDIO_EXT_RE.sub("", filename or "").strip()

    artist: Optional[str] = None
    title: str = name
    if " - " in name:
        left, right = name.split(" - ", 1)
        artist = left.strip() or None
        title = right.strip()

    base_title, version = split_version(title)

    return {
        "artist": artist,
        "title": title or None,
        "base_title": base_title or None,
        "version": version or None,
        "feat": extract_feat(name),
        "catalog": extract_catalog(name),
    }
