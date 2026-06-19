"""
Fuzzy matching service - matches local tracks with tracklist information
Uses Google search to find tracklists from various sources
"""
import re
import asyncio
from typing import List, Dict, Optional, Tuple
from rapidfuzz import fuzz, process
from sqlalchemy import select
from backend.services.database import get_db
from backend.services.tracklists_api import search_1001tracklists, get_tracklist_details
from backend.services.google_search import search_tracklists_google
from backend.services import string_match as sm
from backend.models.track import Track, MatchCandidate
from backend.config import settings
from loguru import logger


class TrackMatcher:
    """Fuzzy matching engine for DJ tracks"""
    
    def __init__(self):
        self.threshold = settings.fuzzy_threshold
        # Minimum confidence gap between the best and second-best candidate
        # required to auto-accept (gap-aware ranking - avoids auto-accepting
        # when two candidates are nearly tied).
        self.auto_accept_gap = 8.0
    
    def clean_string(self, s: str) -> str:
        """Clean string for better matching"""
        if not s:
            return ""
        
        # Convert to lowercase
        s = s.lower()
        
        # Remove common file artifacts
        s = re.sub(r'\[.*?\]', '', s)  # Remove [anything in brackets]
        s = re.sub(r'\(.*?\)', '', s)  # Remove (anything in parens)
        s = re.sub(r'_', ' ', s)       # Replace underscores
        s = re.sub(r'-{2,}', ' ', s)   # Replace multiple dashes
        
        # Remove file extensions
        s = re.sub(r'\.(mp3|flac|wav|m4a|aac|ogg)$', '', s, flags=re.IGNORECASE)
        
        # Remove common DJ set prefixes/suffixes
        patterns_to_remove = [
            r'\d{4}[-./]\d{2}[-./]\d{2}',  # Dates
            r'\d{2}[-./]\d{2}[-./]\d{4}',  # Dates (alternate)
            r'\b(live|set|mix|dj|@|podcast|episode|ep\.?|vol\.?)\b',
            r'\b(320|128|flac|wav|mp3)\b',  # Quality indicators
            r'\b(part|pt\.?)\s*\d+\b',       # Part numbers
        ]
        
        for pattern in patterns_to_remove:
            s = re.sub(pattern, '', s, flags=re.IGNORECASE)
        
        # Clean up whitespace
        s = re.sub(r'\s+', ' ', s).strip()
        
        return s
    
    def extract_search_terms(self, track: Track) -> List[str]:
        """Extract search terms from a track"""
        terms = []
        
        # Try artist name
        if track.artist:
            cleaned = self.clean_string(track.artist)
            if cleaned and len(cleaned) >= 3:
                terms.append(cleaned)
        
        # Try title
        if track.title:
            cleaned = self.clean_string(track.title)
            if cleaned and len(cleaned) >= 3:
                terms.append(cleaned)
        
        # Try filename
        if track.filename:
            cleaned = self.clean_string(track.filename)
            if cleaned and len(cleaned) >= 3:
                terms.append(cleaned)
            
            # Also try extracting "Artist - Title" pattern from filename
            if " - " in track.filename:
                parts = track.filename.split(" - ")
                for part in parts[:2]:  # First two parts
                    cleaned = self.clean_string(part)
                    if cleaned and len(cleaned) >= 3 and cleaned not in terms:
                        terms.append(cleaned)
        
        return terms
    
    def calculate_match_score(
        self,
        track: Track,
        candidate: Dict,
        match_type: str = "fuzzy",
        acoustid_identity: Optional[Dict] = None,
    ) -> float:
        """Calculate a match confidence score between a track and a candidate"""
        return self._score_candidate(track, candidate, acoustid_identity)

    def _score_candidate(
        self,
        track: Track,
        candidate: Dict,
        acoustid_identity: Optional[Dict] = None,
    ) -> float:
        """
        Weighted match score (0-100) using version-aware string matching.

        Unlike token_set_ratio, the title comparison keeps remix/version
        descriptors significant, so an "Original Mix" no longer scores 100
        against a "Remix". When a confident AcoustID fingerprint identity is
        supplied, agreement with it becomes the dominant signal.
        """
        scores: List[Tuple[str, float, float]] = []

        track_title = track.title or track.filename or ""
        track_artist = track.artist or ""
        track_full = track.filename or ""

        cand_title = candidate.get("title", "") or ""
        cand_artist = candidate.get("artist") or candidate.get("dj") or ""
        cand_full = candidate.get("full_title", cand_title) or ""

        # Title match (version-aware)
        if track_title and cand_title:
            scores.append(("title", sm.title_similarity(track_title, cand_title), 0.5))

        # Artist match (with phonetic tiebreak)
        if track_artist and cand_artist:
            scores.append(("artist", sm.artist_similarity(track_artist, cand_artist), 0.3))

        # Filename vs candidate full title
        if track_full and cand_full:
            scores.append(("full", sm.title_similarity(track_full, cand_full), 0.2))

        # Bonus for tracklists that actually contain tracks
        num_tracks = len(candidate.get("tracks", []))
        if num_tracks > 0:
            scores.append(("tracks", min(50 + num_tracks * 2, 70), 0.1))

        # AcoustID agreement - the highest-weight signal when a confident
        # fingerprint identity exists. Candidates matching the fingerprinted
        # artist/title are pulled to the top; disagreeing ones are pushed down.
        if acoustid_identity:
            ai_title = acoustid_identity.get("title") or ""
            ai_artist = acoustid_identity.get("artist") or ""
            ai_score = float(acoustid_identity.get("score") or 0.0)
            agreement: List[float] = []
            if ai_title and cand_title:
                agreement.append(sm.title_similarity(ai_title, cand_title))
            if ai_artist and cand_artist:
                agreement.append(sm.artist_similarity(ai_artist, cand_artist))
            if agreement and ai_score > 0:
                scores.append(("acoustid", sum(agreement) / len(agreement), 4.0 * ai_score))

        if not scores:
            return 0.0

        total_weight = sum(w for _, _, w in scores)
        if total_weight <= 0:
            return 0.0
        return sum(value * weight for _, value, weight in scores) / total_weight
    
    async def find_matches_for_track(self, track: Track) -> List[Dict]:
        """Find potential matches for a track using Google search"""
        matches = []
        
        # Extract search terms
        search_terms = self.extract_search_terms(track)
        
        logger.info(f"Extracted search terms: {search_terms}")
        
        if not search_terms:
            logger.warning(f"No search terms extracted for track {track.id}")
            return matches

        # Audio fingerprint identity (AcoustID). When confident this is the
        # strongest signal we have for obscure tracks, so it both seeds a
        # candidate and biases scoring of web results toward agreement with it.
        acoustid_identity = await self.identify_with_fingerprint(track)
        if acoustid_identity:
            logger.info(
                f"AcoustID identity: {acoustid_identity.get('artist')} - "
                f"{acoustid_identity.get('title')} "
                f"(score {acoustid_identity.get('score', 0):.2f})"
            )
        
        # Build artist and title from search terms
        artist = track.artist or ""
        title = track.title or ""
        filename = track.filename or ""
        
        # If no metadata, try to extract from filename
        if not artist and not title and filename:
            clean_name = self.clean_string(filename)
            if " - " in filename:
                parts = filename.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip() if len(parts) > 1 else clean_name
            else:
                title = clean_name
        
        try:
            # PRIMARY: Search using Google
            logger.info(f"Searching Google for tracklist: artist='{artist}', title='{title}'")
            google_results = await search_tracklists_google(
                artist=artist,
                title=title,
                filename=filename
            )
            
            logger.info(f"Got {len(google_results)} results from Google search")
            
            # Process Google results
            for result in google_results:
                # Calculate match score
                score = self._calculate_google_result_score(track, result, acoustid_identity)
                logger.info(f"Match score for '{result.get('title', 'unknown')}' from {result.get('source', 'unknown')}: {score:.1f} (threshold: {self.threshold})")
                
                if score >= self.threshold:
                    # Convert to standard format
                    match_data = {
                        "title": result.get("title", ""),
                        "artist": result.get("artist", ""),
                        "url": result.get("source_url", ""),
                        "cover_url": result.get("cover_url", ""),
                        "source": result.get("source", "web"),
                        "tracks": result.get("tracks", []),
                        "num_tracks": len(result.get("tracks", [])),
                        "genres": result.get("genres", []),
                        "genre": result.get("genres", [""])[0] if result.get("genres") else "",
                        "date_recorded": result.get("date", ""),
                        "dj": result.get("artist", ""),
                        "confidence": score,
                        "match_type": "google_search"
                    }
                    matches.append(match_data)
            
            # FALLBACK: If Google didn't find enough results, try direct 1001tracklists
            if len(matches) < 2:
                logger.info("Trying direct 1001tracklists search as fallback...")
                seen_urls = set(m.get("url", "") for m in matches)
                
                for term in search_terms[:2]:
                    try:
                        results = await search_1001tracklists(term)
                        logger.info(f"Got {len(results)} results from 1001tracklists for: {term}")
                        
                        for result in results:
                            url = result.get("url", "")
                            if url in seen_urls:
                                continue
                            seen_urls.add(url)
                            
                            score = self.calculate_match_score(track, result, acoustid_identity=acoustid_identity)
                            if score >= self.threshold:
                                matches.append({
                                    **result,
                                    "confidence": score,
                                    "match_type": "1001tracklists_direct"
                                })
                        
                        await asyncio.sleep(1.0)
                        
                    except Exception as e:
                        logger.warning(f"1001tracklists fallback failed for '{term}': {e}")
            
        except Exception as e:
            logger.error(f"Error in Google search: {e}")
            # Fall back to 1001tracklists only
            logger.info("Falling back to 1001tracklists search only...")
            await self._fallback_search(track, search_terms, matches, acoustid_identity)

        # Seed a candidate directly from a confident AcoustID fingerprint match -
        # this is how genuinely obscure tracks (absent from tracklist sites) get
        # identified at all.
        if acoustid_identity and acoustid_identity.get("score", 0) >= 0.85:
            matches.append({
                "title": acoustid_identity.get("title", ""),
                "artist": acoustid_identity.get("artist", ""),
                "url": "",
                "cover_url": "",
                "source": "acoustid",
                "tracks": [],
                "num_tracks": 0,
                "genre": "",
                "confidence": min(99.0, float(acoustid_identity["score"]) * 100),
                "match_type": "acoustid_fingerprint",
            })
        
        # Sort by confidence
        matches.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        return matches[:10]  # Return top 10 matches
    
    async def identify_with_fingerprint(self, track: Track) -> Optional[Dict]:
        """
        Look up the track's audio fingerprint via AcoustID.

        Returns a dict with title/artist/score (0-1) when a reasonably confident
        match is found, else None. Never raises - fingerprinting is best-effort.
        """
        try:
            filepath = getattr(track, "filepath", None)
            if not filepath:
                return None

            from backend.api.settings import load_saved_settings
            from backend.services.fingerprint import identify_with_acoustid

            saved = await load_saved_settings()
            api_key = (saved or {}).get("acoustid_api_key", "")
            if not api_key:
                return None

            result = await identify_with_acoustid(filepath, api_key)
            if result and result.get("score", 0) >= 0.5:
                return result
        except Exception as e:
            logger.warning(f"AcoustID fingerprint lookup failed: {e}")
        return None

    def _calculate_google_result_score(
        self,
        track: Track,
        result: Dict,
        acoustid_identity: Optional[Dict] = None,
    ) -> float:
        """Calculate match score for a Google search result"""
        return self._score_candidate(track, result, acoustid_identity)
    
    async def _fallback_search(self, track: Track, search_terms: List[str], matches: List[Dict], acoustid_identity: Optional[Dict] = None):
        """Fallback to 1001tracklists direct search"""
        seen_urls = set(m.get("url", "") for m in matches)
        
        for term in search_terms[:3]:
            try:
                logger.info(f"Searching 1001tracklists for: {term}")
                results = await search_1001tracklists(term)
                logger.info(f"Got {len(results)} results for term: {term}")
                
                for result in results:
                    url = result.get("url", "")
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    
                    score = self.calculate_match_score(track, result, acoustid_identity=acoustid_identity)
                    logger.debug(f"Match score for {result.get('title', 'unknown')}: {score}")
                    
                    if score >= self.threshold:
                        matches.append({
                            **result,
                            "confidence": score,
                            "match_type": "1001tracklists_fallback"
                        })
                
                await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error searching for term '{term}': {e}")
    
    async def enrich_match_with_tracklist_details(self, match: Dict) -> Dict:
        """Fetch full tracklist details for a match"""
        url = match.get("url")
        if not url or "/tracklist/" not in url:
            return match
        
        try:
            details = await get_tracklist_details(url)
            if details:
                match.update({
                    "cover_url": details.get("cover_url"),
                    "djs": details.get("djs", []),
                    "genres": details.get("genres", []),
                    "date_recorded": details.get("date_recorded"),
                    "sources": details.get("sources", {}),
                    "num_tracks": details.get("num_tracks", 0)
                })
                
                # Set primary values
                if details.get("djs"):
                    match["dj"] = details["djs"][0]
                if details.get("genres"):
                    match["genre"] = details["genres"][0]
                if details.get("sources"):
                    # Get event name if available
                    for key, value in details["sources"].items():
                        if "festival" in key.lower() or "event" in key.lower():
                            match["event"] = value
                            break
        except Exception as e:
            logger.error(f"Error enriching match: {e}")
        
        return match


# Global matcher instance
_matcher: Optional[TrackMatcher] = None


def get_matcher() -> TrackMatcher:
    """Get or create TrackMatcher instance"""
    global _matcher
    if _matcher is None:
        _matcher = TrackMatcher()
    return _matcher


async def find_matches(track_id: int):
    """Find and save matches for a track"""
    matcher = get_matcher()
    
    async with get_db() as db:
        # Get track
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            logger.error(f"Track {track_id} not found")
            return
        
        logger.info(f"Finding matches for track: {track.filename}")
        
        try:
            # Find matches
            matches = await matcher.find_matches_for_track(track)
            
            if not matches:
                logger.info(f"No matches found for track {track_id}")
                track.status = "pending"  # Keep as pending if no matches
                await db.commit()
                return
            
            # Enrich top matches with tracklist details
            for i, match in enumerate(matches[:3]):
                matches[i] = await matcher.enrich_match_with_tracklist_details(match)
            
            # Clear existing match candidates
            await db.execute(
                MatchCandidate.__table__.delete().where(MatchCandidate.track_id == track_id)
            )
            
            # Save match candidates
            for match in matches:
                candidate = MatchCandidate(
                    track_id=track_id,
                    title=match.get("title", ""),
                    artist=match.get("artist") or match.get("dj"),
                    genre=match.get("genre"),
                    cover_url=match.get("cover_url"),
                    tracklist_url=match.get("url"),
                    tracklist_id=match.get("tracklist_id"),
                    dj=match.get("dj"),
                    event=match.get("event"),
                    date_recorded=match.get("date_recorded"),
                    source=match.get("source", ""),
                    extracted_tracks=match.get("tracks"),  # Store extracted tracks as JSON
                    num_tracks=match.get("num_tracks", len(match.get("tracks", []))),
                    confidence=match.get("confidence", 0),
                    match_type=match.get("match_type", "fuzzy")
                )
                db.add(candidate)
            
            # Auto-select best match if confidence is high enough.
            # Gap-aware: don't auto-accept when the runner-up is nearly tied
            # (ambiguous) - unless the best match is a confident audio
            # fingerprint, which we trust outright.
            best_match = matches[0]
            second_conf = matches[1]["confidence"] if len(matches) > 1 else 0.0
            is_fingerprint = best_match.get("match_type") == "acoustid_fingerprint"
            gap_ok = len(matches) == 1 or (best_match["confidence"] - second_conf) >= self.auto_accept_gap

            if best_match["confidence"] >= 85 and (gap_ok or is_fingerprint):
                track.matched_title = best_match.get("title")
                track.matched_artist = best_match.get("artist") or best_match.get("dj")
                track.matched_genre = best_match.get("genre")
                track.matched_cover_url = best_match.get("cover_url")
                track.matched_tracklist_url = best_match.get("url")
                track.matched_dj = best_match.get("dj")
                track.matched_event = best_match.get("event")
                track.match_confidence = best_match["confidence"]
                track.match_source = best_match.get("source", "")
                track.status = "matched"
            else:
                track.status = "pending"  # Needs manual review
            
            await db.commit()
            logger.info(f"Found {len(matches)} matches for track {track_id}")
            
        except Exception as e:
            logger.error(f"Error finding matches for track {track_id}: {e}")
            track.status = "error"
            track.error_message = str(e)
            await db.commit()


async def batch_match_tracks(
    track_ids: Optional[List[int]] = None,
    status_filter: Optional[str] = None
):
    """Match multiple tracks"""
    async with get_db() as db:
        # Build query
        query = select(Track.id)
        
        if track_ids:
            query = query.where(Track.id.in_(track_ids))
        elif status_filter:
            query = query.where(Track.status == status_filter)
        else:
            query = query.where(Track.status == "pending")
        
        result = await db.execute(query)
        ids_to_match = [row[0] for row in result.fetchall()]
    
    logger.info(f"Batch matching {len(ids_to_match)} tracks")
    
    for track_id in ids_to_match:
        await find_matches(track_id)
        await asyncio.sleep(2.0)  # Delay between tracks to avoid rate limiting
