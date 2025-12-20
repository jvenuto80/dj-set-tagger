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
from backend.models.track import Track, MatchCandidate
from backend.config import settings
from loguru import logger


class TrackMatcher:
    """Fuzzy matching engine for DJ tracks"""
    
    def __init__(self):
        self.threshold = settings.fuzzy_threshold
    
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
        match_type: str = "fuzzy"
    ) -> float:
        """Calculate a match confidence score between a track and a candidate"""
        scores = []
        
        track_artist = self.clean_string(track.artist or "")
        track_title = self.clean_string(track.title or track.filename)
        
        candidate_title = self.clean_string(candidate.get("title", ""))
        candidate_artist = self.clean_string(candidate.get("artist") or candidate.get("dj") or "")
        
        # Title match
        if track_title and candidate_title:
            title_score = fuzz.token_set_ratio(track_title, candidate_title)
            scores.append(("title", title_score, 0.5))  # 50% weight
        
        # Artist match (if available)
        if track_artist and candidate_artist:
            artist_score = fuzz.token_set_ratio(track_artist, candidate_artist)
            scores.append(("artist", artist_score, 0.3))  # 30% weight
        
        # Full name match (filename vs full title)
        track_full = self.clean_string(track.filename)
        candidate_full = self.clean_string(candidate.get("full_title", candidate.get("title", "")))
        if track_full and candidate_full:
            full_score = fuzz.token_set_ratio(track_full, candidate_full)
            scores.append(("full", full_score, 0.2))  # 20% weight
        
        # Calculate weighted average
        if not scores:
            return 0.0
        
        total_weight = sum(s[2] for s in scores)
        weighted_score = sum(s[1] * s[2] for s in scores) / total_weight
        
        return weighted_score
    
    async def find_matches_for_track(self, track: Track) -> List[Dict]:
        """Find potential matches for a track using Google search"""
        matches = []
        
        # Extract search terms
        search_terms = self.extract_search_terms(track)
        
        logger.info(f"Extracted search terms: {search_terms}")
        
        if not search_terms:
            logger.warning(f"No search terms extracted for track {track.id}")
            return matches
        
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
                score = self._calculate_google_result_score(track, result)
                logger.debug(f"Match score for {result.get('title', 'unknown')}: {score}")
                
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
                            
                            score = self.calculate_match_score(track, result)
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
            await self._fallback_search(track, search_terms, matches)
        
        # Sort by confidence
        matches.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        return matches[:10]  # Return top 10 matches
    
    def _calculate_google_result_score(self, track: Track, result: Dict) -> float:
        """Calculate match score for a Google search result"""
        scores = []
        
        track_artist = self.clean_string(track.artist or "")
        track_title = self.clean_string(track.title or track.filename)
        
        result_title = self.clean_string(result.get("title", ""))
        result_artist = self.clean_string(result.get("artist", ""))
        
        # Title match
        if track_title and result_title:
            title_score = fuzz.token_set_ratio(track_title, result_title)
            scores.append(("title", title_score, 0.4))
        
        # Artist match
        if track_artist and result_artist:
            artist_score = fuzz.token_set_ratio(track_artist, result_artist)
            scores.append(("artist", artist_score, 0.3))
        
        # Filename vs full title
        track_full = self.clean_string(track.filename)
        if track_full and result_title:
            full_score = fuzz.token_set_ratio(track_full, result_title)
            scores.append(("full", full_score, 0.2))
        
        # Bonus for having tracks
        num_tracks = len(result.get("tracks", []))
        if num_tracks > 0:
            track_bonus = min(num_tracks * 2, 20)  # Up to 20 bonus points
            scores.append(("tracks", track_bonus + 50, 0.1))
        
        if not scores:
            return 0.0
        
        total_weight = sum(s[2] for s in scores)
        weighted_score = sum(s[1] * s[2] for s in scores) / total_weight
        
        return weighted_score
    
    async def _fallback_search(self, track: Track, search_terms: List[str], matches: List[Dict]):
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
                    
                    score = self.calculate_match_score(track, result)
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
            
            # Auto-select best match if confidence is high enough
            best_match = matches[0]
            if best_match["confidence"] >= 85:
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
