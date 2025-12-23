"""
Tracks API endpoints
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import List, Optional
from backend.services.database import get_db
from backend.models.track import Track, TrackResponse, TrackUpdate
from backend.config import settings
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from loguru import logger
import os
import json

router = APIRouter()


def get_min_duration_seconds() -> int:
    """Get minimum duration setting in seconds"""
    from backend.config import settings
    settings_file = os.path.join(settings.config_dir, "settings.json")
    if os.path.exists(settings_file):
        with open(settings_file, "r") as f:
            saved = json.load(f)
            minutes = saved.get("min_duration_minutes", 0)
            return minutes * 60
    return 0


@router.get("", response_model=List[TrackResponse])
@router.get("/", response_model=List[TrackResponse])
async def get_tracks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=10000),
    status: Optional[str] = Query(None, description="Filter by status: pending, matched, tagged, error"),
    search: Optional[str] = Query(None, description="Search in filename or title"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    artist: Optional[str] = Query(None, description="Filter by artist"),
    album: Optional[str] = Query(None, description="Filter by album"),
    apply_duration_filter: bool = Query(True, description="Apply minimum duration filter from settings")
):
    """Get all scanned tracks with optional filtering"""
    from sqlalchemy import func
    
    async with get_db() as db:
        query = select(Track)
        count_query = select(func.count(Track.id))
        
        if status:
            query = query.where(Track.status == status)
            count_query = count_query.where(Track.status == status)
        
        if search:
            search_term = f"%{search}%"
            search_filter = (
                (Track.filename.ilike(search_term)) | 
                (Track.title.ilike(search_term)) |
                (Track.artist.ilike(search_term))
            )
            query = query.where(search_filter)
            count_query = count_query.where(search_filter)
        
        # Filter by genre (check both matched_genre and genre)
        if genre:
            genre_filter = (Track.matched_genre == genre) | (Track.genre == genre)
            query = query.where(genre_filter)
            count_query = count_query.where(genre_filter)
        
        # Filter by artist (check both matched_artist and artist)
        if artist:
            artist_filter = (Track.matched_artist == artist) | (Track.artist == artist)
            query = query.where(artist_filter)
            count_query = count_query.where(artist_filter)
        
        # Filter by album (check both matched_album and album)
        if album:
            album_filter = (Track.matched_album == album) | (Track.album == album)
            query = query.where(album_filter)
            count_query = count_query.where(album_filter)
        
        # Apply minimum duration filter
        if apply_duration_filter:
            min_duration = get_min_duration_seconds()
            if min_duration > 0:
                query = query.where(Track.duration >= min_duration)
                count_query = count_query.where(Track.duration >= min_duration)
        
        # Get total count before pagination
        total = await db.scalar(count_query)
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        tracks = result.scalars().all()
        
        return [TrackResponse.model_validate(t) for t in tracks]

@router.get("/stats")
async def get_track_stats():
    """Get statistics about scanned tracks"""
    async with get_db() as db:
        # Count by status
        from sqlalchemy import func
        
        # Get minimum duration filter
        min_duration = get_min_duration_seconds()
        
        # Total counts (unfiltered)
        total_all = await db.scalar(select(func.count(Track.id)))
        
        # Build filtered query
        if min_duration > 0:
            filtered_query = select(func.count(Track.id)).where(Track.duration >= min_duration)
            total = await db.scalar(filtered_query)
            pending = await db.scalar(select(func.count(Track.id)).where(
                (Track.status == "pending") & (Track.duration >= min_duration)
            ))
            matched = await db.scalar(select(func.count(Track.id)).where(
                (Track.status == "matched") & (Track.duration >= min_duration)
            ))
            tagged = await db.scalar(select(func.count(Track.id)).where(
                (Track.status == "tagged") & (Track.duration >= min_duration)
            ))
            errors = await db.scalar(select(func.count(Track.id)).where(
                (Track.status == "error") & (Track.duration >= min_duration)
            ))
            filtered_out = (total_all or 0) - (total or 0)
        else:
            total = total_all
            pending = await db.scalar(select(func.count(Track.id)).where(Track.status == "pending"))
            matched = await db.scalar(select(func.count(Track.id)).where(Track.status == "matched"))
            tagged = await db.scalar(select(func.count(Track.id)).where(Track.status == "tagged"))
            errors = await db.scalar(select(func.count(Track.id)).where(Track.status == "error"))
            filtered_out = 0
        
        return {
            "total": total or 0,
            "total_unfiltered": total_all or 0,
            "filtered_out": filtered_out,
            "pending": pending or 0,
            "matched": matched or 0,
            "tagged": tagged or 0,
            "errors": errors or 0
        }


@router.get("/filters")
async def get_track_filters():
    """Get unique values for filter dropdowns (genres, artists, albums)"""
    from sqlalchemy import func, distinct
    
    async with get_db() as db:
        min_duration = get_min_duration_seconds()
        
        # Base query with duration filter
        base_filter = Track.duration >= min_duration if min_duration > 0 else True
        
        # Get unique genres (prefer matched_genre, fallback to genre)
        genre_query = select(distinct(func.coalesce(Track.matched_genre, Track.genre))).where(
            base_filter
        ).where(
            func.coalesce(Track.matched_genre, Track.genre).isnot(None)
        ).where(
            func.coalesce(Track.matched_genre, Track.genre) != ''
        )
        genre_result = await db.execute(genre_query)
        genres = sorted([g for (g,) in genre_result.fetchall() if g])
        
        # Get unique artists (prefer matched_artist, fallback to artist)
        artist_query = select(distinct(func.coalesce(Track.matched_artist, Track.artist))).where(
            base_filter
        ).where(
            func.coalesce(Track.matched_artist, Track.artist).isnot(None)
        ).where(
            func.coalesce(Track.matched_artist, Track.artist) != ''
        )
        artist_result = await db.execute(artist_query)
        artists = sorted([a for (a,) in artist_result.fetchall() if a])
        
        # Get unique albums (prefer matched_album, fallback to album)
        album_query = select(distinct(func.coalesce(Track.matched_album, Track.album))).where(
            base_filter
        ).where(
            func.coalesce(Track.matched_album, Track.album).isnot(None)
        ).where(
            func.coalesce(Track.matched_album, Track.album) != ''
        )
        album_result = await db.execute(album_query)
        albums = sorted([a for (a,) in album_result.fetchall() if a])
        
        return {
            "genres": genres,
            "artists": artists,
            "albums": albums
        }


# NOTE: This route MUST come before /{track_id} routes to avoid being matched as a track_id
@router.get("/cover-search")
async def search_cover_art_by_query(query: str = Query(..., description="Search query for cover art")):
    """Search for cover art by query string (not tied to a specific track)"""
    from backend.services.google_search import GoogleSearchService
    
    search_service = GoogleSearchService()
    try:
        covers = await search_service.search_cover_art(query)
        return covers
    except Exception as e:
        logger.error(f"Cover art search error: {e}")
        return []


@router.get("/{track_id}", response_model=TrackResponse)
async def get_track(track_id: int):
    """Get a specific track by ID"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        return TrackResponse.model_validate(track)


@router.get("/{track_id}/cover-options")
async def get_cover_options(track_id: int, query: Optional[str] = None):
    """Search for cover art options for a track - collects from match results and searches web"""
    from backend.services.google_search import GoogleSearchService
    from backend.models.track import MatchCandidate
    
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        covers = []
        
        # First, collect covers from existing match results
        match_result = await db.execute(
            select(MatchCandidate).where(MatchCandidate.track_id == track_id)
        )
        matches = match_result.scalars().all()
        
        for match in matches:
            if match.cover_url:
                covers.append({
                    'url': match.cover_url,
                    'source': match.source or 'Match Result',
                    'title': match.title or ''
                })
        
        # If we don't have enough covers, search for more
        if len(covers) < 6:
            search_query = query or f"{track.artist or ''} {track.title or track.filename}".strip()
            search_service = GoogleSearchService()
            try:
                additional_covers = await search_service.search_cover_art(search_query)
                for cover in additional_covers:
                    if cover['url'] not in [c['url'] for c in covers]:
                        covers.append(cover)
            except Exception as e:
                # If search fails, just return what we have from matches
                pass
        
        return covers


@router.patch("/{track_id}", response_model=TrackResponse)
async def update_track(track_id: int, update: TrackUpdate):
    """Update track metadata"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        # Update fields
        update_data = update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(track, field, value)
        
        await db.commit()
        await db.refresh(track)
        
        return TrackResponse.model_validate(track)


@router.delete("/{track_id}")
async def delete_track(track_id: int):
    """Remove a track from the database (does not delete the file)"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        await db.delete(track)
        await db.commit()
        
        return {"message": "Track removed from database"}


@router.delete("/{track_id}/file")
async def delete_track_file(track_id: int):
    """Delete a track's file from disk AND remove from database"""
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        filepath = track.filepath
        filename = track.filename
        
        # Security check: Ensure file is within allowed music directories
        # Load configured scan directories from settings
        from backend.api.settings import load_saved_settings
        saved_settings = load_saved_settings()
        allowed_dirs = saved_settings.get("music_dirs", [settings.MUSIC_DIR])
        if not allowed_dirs:
            allowed_dirs = [settings.MUSIC_DIR]
        
        real_filepath = os.path.realpath(filepath)
        is_allowed = any(
            real_filepath.startswith(os.path.realpath(allowed_dir))
            for allowed_dir in allowed_dirs
        )
        
        if not is_allowed:
            logger.warning(f"Attempted to delete file outside allowed directories: {filepath}")
            raise HTTPException(
                status_code=403, 
                detail="Cannot delete files outside the configured music directories"
            )
        
        # Check if file exists
        if not os.path.exists(filepath):
            # File already gone, just remove from database
            await db.delete(track)
            await db.commit()
            return {"message": f"File not found on disk, removed {filename} from database"}
        
        # Try to delete the file
        try:
            os.remove(filepath)
            logger.info(f"Deleted file: {filepath}")
        except OSError as e:
            logger.error(f"Failed to delete file {filepath}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")
        
        # Remove from database
        await db.delete(track)
        await db.commit()
        
        return {"message": f"Deleted {filename}", "filepath": filepath}


@router.get("/series/detect")
async def detect_series(
    min_tracks: int = Query(2, description="Minimum tracks to form a series"),
    include_tagged: bool = Query(False, description="Include already series-tagged tracks in detection")
):
    """Detect podcast/radio show series dynamically by analyzing filename patterns and directories"""
    import re
    from collections import defaultdict
    
    # Get minimum duration filter
    min_duration = get_min_duration_seconds()
    
    def clean_filename(filename: str) -> str:
        """Clean filename for comparison"""
        # Remove file extension
        name = re.sub(r'\.(mp3|flac|wav|m4a|aac|ogg)$', '', filename, flags=re.IGNORECASE)
        # Clean up underscores and multiple spaces
        name = re.sub(r'_', ' ', name)
        # Replace hyphens between letters (word separators) but NOT between digits (dates)
        name = re.sub(r'(?<=[a-zA-Z])-(?=[a-zA-Z])', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name
    
    def extract_series_name(filename: str) -> tuple:
        """Extract potential series name and episode number from filename"""
        name = clean_filename(filename)
        episode = None
        
        # Remove date patterns first (various formats)
        # "(20 July 2016)" or "(July 2016)" or "(2016)"
        name = re.sub(r'\s*\([^)]*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[^)]*\d{4}[^)]*\)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\(\d{4}\)', '', name)
        
        # Radio recording format: "(YYYY-MM-DD HH.MM.SS Day)" after underscores become spaces
        # Must come BEFORE the simpler YYYY-MM-DD pattern to match the full thing
        name = re.sub(r'\s*\(\d{4}-\d{2}-\d{2}\s+\d{2}\.\d{2}\.\d{2}\s+\w+\)', '', name)
        
        # Radio recording format: "(MM.DD.YY Day. HH:MM)" 
        name = re.sub(r'\s*\(\d{2}\.\d{2}\.\d{2}\s+\w+\.?\s+\d{1,2}[:.]\d{2}\)', '', name)
        
        # "2024-01-15" or "2024.01.15" format (simpler, after more complex patterns)
        name = re.sub(r'\s*[\(\[]?\d{4}[\-\.]\d{2}[\-\.]\d{2}[\)\]]?', '', name)
        # Trailing dates like "- 2024-01-15"
        name = re.sub(r'\s*-\s*\d{4}-\d{2}-\d{2}\s*$', '', name)
        
        # Clean up any remaining time/day patterns like "10.58.00 Monday)"
        name = re.sub(r'\s+\d{2}\.\d{2}\.\d{2}\s+\w+\)?', '', name)
        
        # Remove month+year patterns like "January 2006 Mix" or "July 2005 Mix"
        name = re.sub(r'\s*(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\s*(mix)?\s*', ' ', name, flags=re.IGNORECASE)
        
        # Remove Part N patterns
        name = re.sub(r'\s*part\s*\d+\s*$', '', name, flags=re.IGNORECASE)
        
        # Extract episode number BEFORE further cleaning
        # Pattern: "Name 123" where 123 is episode
        ep_match = re.search(r'\s+(\d{2,4})\s*$', name)
        if ep_match:
            episode = ep_match.group(1)
            name = name[:ep_match.start()].strip()
        
        # Pattern: "Episode XXX" or "EP XXX" or "#XXX" or "- XXX"
        if not episode:
            ep_match = re.search(r'[\s\-_]*(episode|ep\.?|#)\s*(\d{1,4})', name, re.IGNORECASE)
            if ep_match:
                episode = ep_match.group(2)
                name = name[:ep_match.start()].strip()
        
        # Pattern: leading track number "01 - Name" or "01-Name"
        name = re.sub(r'^\d{1,2}[\s\-_]+', '', name)
        
        # Clean up trailing separators
        name = re.sub(r'[\s\-_]+$', '', name)
        
        # Normalize for grouping (lowercase, remove special chars for comparison)
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return name, normalized, episode
    
    def get_name_tokens(name: str) -> set:
        """Get significant tokens from a name for fuzzy matching"""
        # Normalize and split into words
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        words = normalized.split()
        # Filter out very short words and common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'mix', 'dj', 'live'}
        return {w for w in words if len(w) > 2 and w not in stop_words}
    
    def similarity_score(name1: str, name2: str) -> float:
        """Calculate similarity between two names using token overlap"""
        tokens1 = get_name_tokens(name1)
        tokens2 = get_name_tokens(name2)
        if not tokens1 or not tokens2:
            return 0.0
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        jaccard = intersection / union if union > 0 else 0.0
        
        # Also check if one is a subset of the other (e.g., "patterns" subset of "gai barone patterns")
        # If the smaller set is fully contained in the larger, that's a strong match
        smaller, larger = (tokens1, tokens2) if len(tokens1) <= len(tokens2) else (tokens2, tokens1)
        if smaller and smaller.issubset(larger):
            # Full containment - return high score based on how much of the larger is covered
            containment_score = len(smaller) / len(larger)
            # Use the better of Jaccard or containment, but boost containment
            return max(jaccard, 0.5 + containment_score * 0.5)
        
        return jaccard
    
    def find_common_prefix(names: list) -> str:
        """Find common prefix among a list of names"""
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        
        sorted_names = sorted(names, key=len)
        shortest = sorted_names[0]
        
        for i in range(len(shortest), 0, -1):
            prefix = shortest[:i]
            if all(n.startswith(prefix) for n in names):
                prefix = re.sub(r'[\s\-_]+$', '', prefix)
                if len(prefix) > 3:
                    return prefix
        return names[0]
    
    async with get_db() as db:
        # Build query with duration filter
        query = select(Track)
        
        # Optionally exclude already series-tagged tracks
        if not include_tagged:
            query = query.where(
                or_(Track.series_tagged == False, Track.series_tagged == None)
            )
        
        if min_duration > 0:
            query = query.where(Track.duration >= min_duration)
        
        result = await db.execute(query)
        tracks = result.scalars().all()
        
        # METHOD 1: Group by normalized filename pattern
        series_groups = defaultdict(list)
        
        for track in tracks:
            display_name, normalized, episode = extract_series_name(track.filename)
            
            if normalized and len(normalized) > 3:
                series_groups[normalized].append({
                    'track_id': track.id,
                    'filename': track.filename,
                    'display_name': display_name,
                    'current_album': track.album,
                    'matched_album': track.matched_album,
                    'current_artist': track.artist,
                    'current_genre': track.genre,
                    'matched_genre': track.matched_genre,
                    'current_album_artist': track.album_artist,
                    'matched_album_artist': track.matched_album_artist,
                    'episode': episode,
                    'directory': track.directory,
                })
        
        # METHOD 2: Group by directory (files in same folder often belong together)
        dir_groups = defaultdict(list)
        for track in tracks:
            dir_groups[track.directory].append({
                'track_id': track.id,
                'filename': track.filename,
                'display_name': clean_filename(track.filename),
                'current_album': track.album,
                'matched_album': track.matched_album,
                'current_artist': track.artist,
                'current_genre': track.genre,
                'matched_genre': track.matched_genre,
                'current_album_artist': track.album_artist,
                'matched_album_artist': track.matched_album_artist,
                'episode': None,
                'directory': track.directory,
            })
        
        # Merge directory groups that have 2+ tracks and aren't already in series_groups
        # Only count tracks as "existing" if they're in groups that meet min_tracks threshold
        existing_track_ids = set()
        for tracks_list in series_groups.values():
            if len(tracks_list) >= min_tracks:
                for t in tracks_list:
                    existing_track_ids.add(t['track_id'])
        
        for dir_path, dir_tracks in dir_groups.items():
            if len(dir_tracks) >= min_tracks:
                # Check if these tracks are mostly NOT in existing series
                new_tracks = [t for t in dir_tracks if t['track_id'] not in existing_track_ids]
                if len(new_tracks) >= min_tracks:
                    # Use directory name as series name
                    dir_name = dir_path.split('/')[-1] if '/' in dir_path else dir_path
                    # Clean up the directory name
                    dir_name = re.sub(r'^\d+\s*[-_]\s*', '', dir_name)  # Remove leading numbers
                    normalized_dir = re.sub(r'[^\w\s]', '', dir_name.lower()).strip()
                    if normalized_dir and len(normalized_dir) > 3:
                        # Add album_artist fields to directory-based tracks
                        for t in new_tracks:
                            t['display_name'] = dir_name
                        series_groups[f"dir:{normalized_dir}"] = new_tracks
        
        # METHOD 3: Try to merge similar series using fuzzy matching
        series_keys = list(series_groups.keys())
        merged = set()
        
        for i, key1 in enumerate(series_keys):
            if key1 in merged:
                continue
            for key2 in series_keys[i+1:]:
                if key2 in merged:
                    continue
                # Calculate similarity - use 50% threshold for more aggressive merging
                if similarity_score(key1, key2) > 0.5:  # 50% token overlap
                    # Merge key2 into key1
                    series_groups[key1].extend(series_groups[key2])
                    merged.add(key2)
        
        # Remove merged keys
        for key in merged:
            del series_groups[key]
        
        # Rebuild existing_track_ids based on groups that meet min_tracks after merging
        # Exclude directory-based groups (dir:*) from blocking orphan detection since they're less precise
        existing_track_ids = set()
        for norm_key, tracks_list in series_groups.items():
            if len(tracks_list) >= min_tracks and not norm_key.startswith('dir:'):
                for t in tracks_list:
                    existing_track_ids.add(t['track_id'])
        
        # METHOD 4: Find orphan tracks that match existing TAGGED series
        # This helps when you add a single new file that belongs to an already-tagged series
        if not include_tagged:
            # Get all tagged series albums
            tagged_query = select(Track).where(Track.series_tagged == True)
            if min_duration > 0:
                tagged_query = tagged_query.where(Track.duration >= min_duration)
            tagged_result = await db.execute(tagged_query)
            tagged_tracks = tagged_result.scalars().all()
            
            # Build a map of album names to their metadata
            tagged_series_map = {}  # normalized album name -> {album, artist, genre, album_artist, tracks}
            for track in tagged_tracks:
                album = track.matched_album or track.album
                if album:
                    album_normalized = re.sub(r'[^\w\s]', '', album.lower()).strip()
                    if album_normalized not in tagged_series_map:
                        tagged_series_map[album_normalized] = {
                            'album': album,
                            'artist': track.matched_artist or track.artist,
                            'genre': track.matched_genre or track.genre or '',
                            'album_artist': track.matched_album_artist or track.album_artist or '',
                            'cover_url': track.matched_cover_url,
                            'tracks': []
                        }
            
            # Check untagged tracks that aren't in any series yet
            for track in tracks:
                if track.id in existing_track_ids:
                    continue  # Already in a series group
                
                display_name, normalized, episode = extract_series_name(track.filename)
                
                # Collect ALL matching series with their scores
                matches = []
                for album_normalized, series_info in tagged_series_map.items():
                    score = similarity_score(normalized, album_normalized)
                    if score > 0.5:
                        matches.append({
                            'album': series_info['album'],
                            'artist': series_info['artist'],
                            'genre': series_info['genre'],
                            'album_artist': series_info['album_artist'],
                            'cover_url': series_info['cover_url'],
                            'score': score
                        })
                
                # If we found matches, use the best one as primary but include alternatives
                if matches:
                    # Sort by score descending
                    matches.sort(key=lambda x: -x['score'])
                    best_match = matches[0]
                    alternative_matches = matches[1:5]  # Keep up to 4 alternatives
                    
                    orphan_key = f"orphan:{track.id}"
                    series_groups[orphan_key] = [{
                        'track_id': track.id,
                        'filename': track.filename,
                        'display_name': display_name,
                        'current_album': track.album,
                        'matched_album': track.matched_album,
                        'current_artist': track.artist,
                        'current_genre': track.genre,
                        'matched_genre': track.matched_genre,
                        'current_album_artist': track.album_artist,
                        'matched_album_artist': track.matched_album_artist,
                        'episode': episode,
                        'directory': track.directory,
                        'suggested_album': best_match['album'],
                        'suggested_artist': best_match['artist'],
                        'suggested_genre': best_match['genre'],
                        'suggested_album_artist': best_match['album_artist'],
                        'matched_series': best_match['album'],  # Mark that this matches an existing series
                        'alternative_matches': alternative_matches,  # Include other potential matches
                    }]
                    existing_track_ids.add(track.id)
        
        # METHOD 5: Group by existing album metadata (for CD albums with tags)
        # This helps detect albums that already have album tags but aren't series_tagged
        album_groups = defaultdict(list)
        for track in tracks:
            if track.id in existing_track_ids:
                continue  # Already in another group
            
            album = track.album or track.matched_album
            if album and len(album) > 2:
                album_normalized = re.sub(r'[^\w\s]', '', album.lower()).strip()
                if album_normalized:
                    album_groups[album_normalized].append({
                        'track_id': track.id,
                        'filename': track.filename,
                        'display_name': clean_filename(track.filename),
                        'current_album': track.album,
                        'matched_album': track.matched_album,
                        'current_artist': track.artist,
                        'current_genre': track.genre,
                        'matched_genre': track.matched_genre,
                        'current_album_artist': track.album_artist,
                        'matched_album_artist': track.matched_album_artist,
                        'episode': None,
                        'directory': track.directory,
                        'suggested_album': album,  # Use existing album as suggestion
                        'suggested_artist': track.artist,
                        'suggested_genre': track.genre or '',
                        'suggested_album_artist': track.album_artist or '',
                        'is_album_group': True,  # Mark as album-based group
                    })
        
        # Add album groups that meet minimum tracks
        for album_norm, album_tracks in album_groups.items():
            if len(album_tracks) >= min_tracks:
                album_key = f"album:{album_norm}"
                series_groups[album_key] = album_tracks
                for t in album_tracks:
                    existing_track_ids.add(t['track_id'])
        
        # Build final series list
        series_list = []
        for normalized, track_list in series_groups.items():
            # For orphan tracks (single tracks matching existing series), allow min_tracks=1
            is_orphan = normalized.startswith('orphan:')
            effective_min = 1 if is_orphan else min_tracks
            
            if len(track_list) >= effective_min:
                # Check if tracks already have suggestions (orphans do)
                if track_list[0].get('matched_series'):
                    # Orphan track - use the pre-set suggestions
                    series_name = track_list[0]['suggested_album']
                    suggested_artist = track_list[0]['suggested_artist']
                    suggested_genre = track_list[0]['suggested_genre']
                    suggested_album_artist = track_list[0]['suggested_album_artist']
                else:
                    display_names = [t['display_name'] for t in track_list]
                    
                    name_counts = defaultdict(int)
                    for n in display_names:
                        name_counts[n] += 1
                    
                    if max(name_counts.values()) > 1:
                        series_name = max(name_counts.keys(), key=lambda x: name_counts[x])
                    else:
                        series_name = find_common_prefix(display_names)
                    
                    # Get most common artist
                    artists = [t['current_artist'] for t in track_list if t['current_artist']]
                    artist_counts = defaultdict(int)
                    for a in artists:
                        artist_counts[a] += 1
                    suggested_artist = max(artist_counts.keys(), key=lambda x: artist_counts[x]) if artist_counts else 'Various'
                    
                    # Get most common genre (prefer matched_genre, fall back to current_genre)
                    genres = [t.get('matched_genre') or t.get('current_genre') for t in track_list if t.get('matched_genre') or t.get('current_genre')]
                    genre_counts = defaultdict(int)
                    for g in genres:
                        genre_counts[g] += 1
                    suggested_genre = max(genre_counts.keys(), key=lambda x: genre_counts[x]) if genre_counts else ''
                    
                    # Get most common album_artist (prefer matched_album_artist, fall back to current_album_artist)
                    album_artists = [t.get('matched_album_artist') or t.get('current_album_artist') for t in track_list if t.get('matched_album_artist') or t.get('current_album_artist')]
                    album_artist_counts = defaultdict(int)
                    for aa in album_artists:
                        album_artist_counts[aa] += 1
                    suggested_album_artist = max(album_artist_counts.keys(), key=lambda x: album_artist_counts[x]) if album_artist_counts else ''
                
                for t in track_list:
                    if not t.get('matched_series'):  # Don't overwrite orphan suggestions
                        t['suggested_album'] = series_name
                        t['suggested_artist'] = suggested_artist
                        t['suggested_genre'] = suggested_genre
                        t['suggested_album_artist'] = suggested_album_artist
                
                # Deduplicate tracks by ID
                seen_ids = set()
                unique_tracks = []
                for t in track_list:
                    if t['track_id'] not in seen_ids:
                        seen_ids.add(t['track_id'])
                        unique_tracks.append(t)
                
                if len(unique_tracks) >= effective_min:
                    series_entry = {
                        'series_name': series_name,
                        'track_count': len(unique_tracks),
                        'tracks': sorted(unique_tracks, key=lambda x: (int(x['episode']) if x['episode'] and x['episode'].isdigit() else 0, x['filename'])),
                        'suggested_album': series_name,
                        'suggested_artist': suggested_artist,
                        'suggested_genre': suggested_genre,
                        'suggested_album_artist': suggested_album_artist
                    }
                    # Mark if this is an orphan track suggestion
                    if is_orphan:
                        series_entry['is_orphan'] = True
                        series_entry['matched_series'] = track_list[0].get('matched_series')
                        # Include alternative matches if available
                        if track_list[0].get('alternative_matches'):
                            series_entry['alternative_matches'] = track_list[0].get('alternative_matches')
                    # Mark if this is an album-based group (from existing metadata)
                    if normalized.startswith('album:'):
                        series_entry['is_album_group'] = True
                    series_list.append(series_entry)
        
        return sorted(series_list, key=lambda x: (-1 if x.get('is_orphan') else 0, -x['track_count']))


@router.get("/series/tagged")
async def get_tagged_series(min_tracks: int = Query(2, description="Minimum tracks to form a series")):
    """Get series that have already been tagged (series_tagged=True)"""
    import re
    from collections import defaultdict
    
    # Get minimum duration filter
    min_duration = get_min_duration_seconds()
    
    def clean_filename(filename: str) -> str:
        """Clean filename for comparison"""
        name = re.sub(r'\.(mp3|flac|wav|m4a|aac|ogg)$', '', filename, flags=re.IGNORECASE)
        name = re.sub(r'_', ' ', name)
        # Replace hyphens between letters (word separators) but NOT between digits (dates)
        name = re.sub(r'(?<=[a-zA-Z])-(?=[a-zA-Z])', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name
    
    def extract_series_name(filename: str) -> tuple:
        """Extract potential series name and episode number from filename"""
        name = clean_filename(filename)
        episode = None
        
        # Remove date patterns
        name = re.sub(r'\s*\([^)]*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[^)]*\d{4}[^)]*\)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*\(\d{4}\)', '', name)
        name = re.sub(r'\s*\(\d{4}-\d{2}-\d{2}\s+\d{2}\.\d{2}\.\d{2}\s+\w+\)', '', name)
        name = re.sub(r'\s*\(\d{2}\.\d{2}\.\d{2}\s+\w+\.?\s+\d{1,2}[:.]\d{2}\)', '', name)
        name = re.sub(r'\s*[\(\[]?\d{4}[\-\.]\d{2}[\-\.]\d{2}[\)\]]?', '', name)
        name = re.sub(r'\s*-\s*\d{4}-\d{2}-\d{2}\s*$', '', name)
        name = re.sub(r'\s+\d{2}\.\d{2}\.\d{2}\s+\w+\)?', '', name)
        name = re.sub(r'\s*(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\s*(mix)?\s*', ' ', name, flags=re.IGNORECASE)
        name = re.sub(r'\s*part\s*\d+\s*$', '', name, flags=re.IGNORECASE)
        
        ep_match = re.search(r'\s+(\d{2,4})\s*$', name)
        if ep_match:
            episode = ep_match.group(1)
            name = name[:ep_match.start()].strip()
        
        if not episode:
            ep_match = re.search(r'[\s\-_]*(episode|ep\.?|#)\s*(\d{1,4})', name, re.IGNORECASE)
            if ep_match:
                episode = ep_match.group(2)
                name = name[:ep_match.start()].strip()
        
        name = re.sub(r'^\d{1,2}[\s\-_]+', '', name)
        name = re.sub(r'[\s\-_]+$', '', name)
        
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return name, normalized, episode
    
    async with get_db() as db:
        # Get only already-tagged tracks
        query = select(Track).where(Track.series_tagged == True)
        if min_duration > 0:
            query = query.where(Track.duration >= min_duration)
        
        result = await db.execute(query)
        tracks = result.scalars().all()
        
        # Group by album + artist + genre combination (since they're already tagged)
        album_artist_genre_groups = defaultdict(list)
        
        for track in tracks:
            album_key = track.matched_album or track.album or 'Unknown'
            artist_key = track.matched_artist or track.artist or 'Unknown'
            genre_key = track.matched_genre or track.genre or ''
            # Create composite key for album + artist + genre
            group_key = (album_key, artist_key, genre_key)
            display_name, normalized, episode = extract_series_name(track.filename)
            
            album_artist_genre_groups[group_key].append({
                'track_id': track.id,
                'filename': track.filename,
                'display_name': display_name,
                'current_album': track.album,
                'matched_album': track.matched_album,
                'current_artist': track.artist,
                'matched_artist': track.matched_artist,
                'current_genre': track.genre,
                'matched_genre': track.matched_genre,
                'current_album_artist': track.album_artist,
                'matched_album_artist': track.matched_album_artist,
                'matched_cover_url': track.matched_cover_url,
                'episode': episode,
                'directory': track.directory,
            })
        
        # Build series list
        series_list = []
        for (album_name, artist_name, genre_name), track_list in album_artist_genre_groups.items():
            if len(track_list) >= min_tracks:
                # Display name shows album, artist, and genre if set
                display_parts = [album_name]
                if artist_name and artist_name != 'Unknown' and artist_name != 'Various':
                    display_parts.append(artist_name)
                if genre_name:
                    display_parts.append(genre_name)
                
                if len(display_parts) > 1:
                    display_name = f"{display_parts[0]} ({', '.join(display_parts[1:])})"
                else:
                    display_name = album_name
                
                # Get most common album_artist from tagged series tracks
                album_artists = [t.get('matched_album_artist') or t.get('current_album_artist') for t in track_list if t.get('matched_album_artist') or t.get('current_album_artist')]
                album_artist_counts = defaultdict(int)
                for aa in album_artists:
                    album_artist_counts[aa] += 1
                suggested_album_artist = max(album_artist_counts.keys(), key=lambda x: album_artist_counts[x]) if album_artist_counts else ''
                
                # Check if all tracks share the same cover URL
                cover_urls = [t.get('matched_cover_url') for t in track_list if t.get('matched_cover_url')]
                shared_cover_url = None
                if cover_urls and len(set(cover_urls)) == 1:
                    shared_cover_url = cover_urls[0]
                
                series_list.append({
                    'series_name': display_name,
                    'track_count': len(track_list),
                    'tracks': sorted(track_list, key=lambda x: (int(x['episode']) if x['episode'] and x['episode'].isdigit() else 0, x['filename'])),
                    'suggested_album': album_name,
                    'suggested_artist': artist_name,
                    'suggested_genre': genre_name,
                    'suggested_album_artist': suggested_album_artist,
                    'cover_url': shared_cover_url,
                    'is_tagged': True
                })
        
        return sorted(series_list, key=lambda x: -x['track_count'])


# Job status tracking for background tagging operations
import uuid
from datetime import datetime

tagging_jobs = {}  # job_id -> job status dict


@router.get("/musicbrainz/search")
async def search_musicbrainz(
    query: str = Query(..., description="Album name to search for"),
    artist: Optional[str] = Query(None, description="Artist name to narrow results")
):
    """Search MusicBrainz for album/release information"""
    from backend.services.musicbrainz import search_album
    
    results = await search_album(query, artist, limit=10)
    return {"results": results}


@router.get("/musicbrainz/release/{release_id}")
async def get_musicbrainz_release(release_id: str):
    """Get track listing and details for a MusicBrainz release"""
    from backend.services.musicbrainz import get_release_tracks, get_cover_art_url
    
    tracks = await get_release_tracks(release_id)
    cover_url = await get_cover_art_url(release_id)
    
    return {
        "release_id": release_id,
        "tracks": tracks,
        "cover_url": cover_url
    }


@router.post("/musicbrainz/search-by-tracks")
async def search_musicbrainz_by_tracks(track_names: List[str]):
    """Search MusicBrainz by matching track names to identify an album"""
    from backend.services.musicbrainz import search_by_tracks
    
    if len(track_names) < 2:
        raise HTTPException(status_code=400, detail="At least 2 track names required")
    
    results = await search_by_tracks(track_names, limit=5)
    return {"results": results}


@router.get("/stream/{track_id}")
async def stream_track(track_id: int):
    """Stream audio file for playback"""
    from fastapi.responses import FileResponse
    import mimetypes
    
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            raise HTTPException(status_code=404, detail="Track not found")
        
        if not os.path.exists(track.filepath):
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        # Determine media type
        mime_type, _ = mimetypes.guess_type(track.filepath)
        if not mime_type:
            # Default based on extension
            ext = os.path.splitext(track.filepath)[1].lower()
            mime_types = {
                '.mp3': 'audio/mpeg',
                '.m4a': 'audio/mp4',
                '.flac': 'audio/flac',
                '.wav': 'audio/wav',
                '.ogg': 'audio/ogg',
                '.aac': 'audio/aac',
            }
            mime_type = mime_types.get(ext, 'audio/mpeg')
        
        return FileResponse(
            track.filepath,
            media_type=mime_type,
            filename=track.filename
        )


@router.post("/series/apply-album")
async def apply_series_album_endpoint(
    background_tasks: BackgroundTasks,
    track_ids: List[int],
    album: str = Query(..., description="Album name to apply"),
    artist: Optional[str] = Query(None, description="Artist name to apply"),
    genre: Optional[str] = Query(None, description="Genre to apply"),
    album_artist: Optional[str] = Query(None, description="Album Artist to apply"),
    cover_url: Optional[str] = Query(None, description="Cover art URL to download and embed")
):
    """Apply album (and optionally artist/genre/album_artist/cover) to multiple tracks.
    Runs in background for large batches. Returns a job_id to poll for status."""
    
    # For small batches (< 5 tracks), run synchronously for instant feedback
    if len(track_ids) < 5:
        return await _apply_series_sync(track_ids, album, artist, genre, album_artist, cover_url)
    
    # For larger batches, run in background
    job_id = str(uuid.uuid4())[:8]
    tagging_jobs[job_id] = {
        'status': 'starting',
        'total': len(track_ids),
        'processed': 0,
        'written': 0,
        'errors': [],
        'started_at': datetime.now().isoformat(),
        'completed_at': None
    }
    
    background_tasks.add_task(
        _apply_series_background,
        job_id, track_ids, album, artist, genre, album_artist, cover_url
    )
    
    return {
        "message": f"Tagging {len(track_ids)} tracks in background",
        "job_id": job_id,
        "background": True
    }


@router.get("/series/apply-album/status/{job_id}")
async def get_tagging_job_status(job_id: str):
    """Get status of a background tagging job"""
    if job_id not in tagging_jobs:
        # Return a not_found status instead of 404, so frontend can clean up gracefully
        return {"status": "not_found", "job_id": job_id}
    return tagging_jobs[job_id]


async def _apply_series_sync(track_ids, album, artist, genre, album_artist, cover_url):
    """Synchronous version for small batches"""
    from backend.services.tagger import AudioTagger
    
    tagger = AudioTagger()
    written = 0
    errors = []
    successful_track_ids = []
    
    # Download cover art once if URL provided
    cover_data = None
    if cover_url:
        try:
            cover_data = await tagger.download_cover_art(cover_url)
            if cover_data:
                cover_data = tagger.resize_cover_art(cover_data)
        except Exception as e:
            logger.error(f"Failed to download cover art: {e}")
    
    # Build track info list
    tracks_to_process = []
    async with get_db() as db:
        for track_id in track_ids:
            result = await db.execute(select(Track).where(Track.id == track_id))
            track = result.scalar_one_or_none()
            if track:
                tracks_to_process.append({
                    'track_id': track.id,
                    'filepath': track.filepath,
                    'filename': track.filename
                })
    
    # Process files
    for track_info in tracks_to_process:
        try:
            success = await tagger.write_album_artist_cover(
                track_info['filepath'], album, artist, genre, album_artist, cover_data
            )
            if success:
                written += 1
                successful_track_ids.append(track_info['track_id'])
            else:
                errors.append({'filename': track_info['filename'], 'error': 'Write failed'})
        except Exception as e:
            errors.append({'filename': track_info['filename'], 'error': str(e)})
    
    # Update database
    if successful_track_ids:
        async with get_db() as db:
            for track_id in successful_track_ids:
                result = await db.execute(select(Track).where(Track.id == track_id))
                track = result.scalar_one_or_none()
                if track:
                    track.matched_album = album
                    track.album = album
                    if artist:
                        track.matched_artist = artist
                        track.artist = artist
                    if genre:
                        track.matched_genre = genre
                        track.genre = genre
                    if album_artist:
                        track.matched_album_artist = album_artist
                        track.album_artist = album_artist
                    if cover_url:
                        track.matched_cover_url = cover_url
                    if track.status == "pending":
                        track.status = "matched"
                    track.series_tagged = True
            await db.commit()
    
    message = f"Successfully tagged {written} tracks" if not errors else f"Tagged {written} tracks, {len(errors)} errors"
    return {
        "message": message,
        "updated": written,
        "written": written,
        "errors": errors,
        "total_files": len(tracks_to_process)
    }


async def _apply_series_background(job_id, track_ids, album, artist, genre, album_artist, cover_url):
    """Background task for tagging large batches - processes files concurrently"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from backend.services.tagger import AudioTagger
    
    job = tagging_jobs[job_id]
    job['status'] = 'downloading_cover'
    
    tagger = AudioTagger()
    successful_track_ids = []
    
    # Download cover art once
    cover_data = None
    if cover_url:
        try:
            cover_data = await tagger.download_cover_art(cover_url)
            if cover_data:
                cover_data = tagger.resize_cover_art(cover_data)
                logger.info(f"[Job {job_id}] Downloaded cover art")
        except Exception as e:
            logger.error(f"[Job {job_id}] Failed to download cover art: {e}")
    
    job['status'] = 'loading_tracks'
    
    # Build track info list
    tracks_to_process = []
    async with get_db() as db:
        for track_id in track_ids:
            result = await db.execute(select(Track).where(Track.id == track_id))
            track = result.scalar_one_or_none()
            if track:
                tracks_to_process.append({
                    'track_id': track.id,
                    'filepath': track.filepath,
                    'filename': track.filename
                })
    
    job['status'] = 'tagging'
    job['total'] = len(tracks_to_process)
    
    # Process files one at a time with timeout for network shares
    FILE_TIMEOUT = 120  # 2 minute timeout per file
    
    for i, track_info in enumerate(tracks_to_process):
        try:
            logger.info(f"[Job {job_id}] Processing {i+1}/{len(tracks_to_process)}: {track_info['filename']}")
            
            # Use timeout to prevent hanging on slow network shares
            try:
                success = await asyncio.wait_for(
                    tagger.write_album_artist_cover(
                        track_info['filepath'], album, artist, genre, album_artist, cover_data
                    ),
                    timeout=FILE_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error(f"[Job {job_id}] Timeout writing to {track_info['filename']}")
                success = False
            
            if success:
                job['written'] += 1
                successful_track_ids.append(track_info['track_id'])
            else:
                job['errors'].append({'filename': track_info['filename'], 'error': 'Write failed or timed out'})
                
        except Exception as e:
            logger.error(f"[Job {job_id}] Error tagging {track_info['filename']}: {e}")
            job['errors'].append({'filename': track_info['filename'], 'error': str(e)})
        
        job['processed'] = i + 1
        
        # Yield to allow other tasks to run
        await asyncio.sleep(0.01)
    
    job['status'] = 'updating_database'
    
    # Update database in a single transaction
    if successful_track_ids:
        async with get_db() as db:
            # Use bulk update for efficiency
            result = await db.execute(
                select(Track).where(Track.id.in_(successful_track_ids))
            )
            tracks = result.scalars().all()
            
            for track in tracks:
                track.matched_album = album
                track.album = album
                if artist:
                    track.matched_artist = artist
                    track.artist = artist
                if genre:
                    track.matched_genre = genre
                    track.genre = genre
                if album_artist:
                    track.matched_album_artist = album_artist
                    track.album_artist = album_artist
                if cover_url:
                    track.matched_cover_url = cover_url
                if track.status == "pending":
                    track.status = "matched"
                track.series_tagged = True
            
            await db.commit()
    
    job['status'] = 'completed'
    job['completed_at'] = datetime.now().isoformat()
    
    logger.info(f"[Job {job_id}] Completed: {job['written']}/{job['total']} tracks tagged")
    
    # Clean up old jobs after 5 minutes
    await asyncio.sleep(300)
    if job_id in tagging_jobs:
        del tagging_jobs[job_id]


@router.post("/resync")
async def resync_database():
    """Re-read file tags and update database to match actual file contents.
    This fixes any db/file mismatches by reading the actual tags from files."""
    from backend.services.tagger import AudioTagger
    from mutagen import File as MutagenFile
    from mutagen.easyid3 import EasyID3
    from mutagen.mp4 import MP4
    from mutagen.flac import FLAC
    
    tagger = AudioTagger()
    updated = 0
    errors = []
    checked = 0
    
    async with get_db() as db:
        result = await db.execute(select(Track))
        tracks = result.scalars().all()
        
        for track in tracks:
            checked += 1
            try:
                if not os.path.exists(track.filepath):
                    errors.append({'filename': track.filename, 'error': 'File not found'})
                    continue
                
                # Read actual tags from file
                audio = MutagenFile(track.filepath, easy=True)
                if audio is None:
                    continue
                
                file_album = None
                file_artist = None
                file_title = None
                
                # Handle different formats
                if isinstance(audio, MP4):
                    file_album = audio.tags.get('\xa9alb', [None])[0] if audio.tags else None
                    file_artist = audio.tags.get('\xa9ART', [None])[0] if audio.tags else None
                    file_title = audio.tags.get('\xa9nam', [None])[0] if audio.tags else None
                elif hasattr(audio, 'get'):
                    file_album = audio.get('album', [None])[0] if audio.get('album') else None
                    file_artist = audio.get('artist', [None])[0] if audio.get('artist') else None
                    file_title = audio.get('title', [None])[0] if audio.get('title') else None
                
                # Check if db is out of sync with file
                needs_update = False
                
                # If file has tags that differ from DB, update DB to match file
                if file_album and track.album != file_album:
                    track.album = file_album
                    track.matched_album = file_album
                    needs_update = True
                
                if file_artist and track.artist != file_artist:
                    track.artist = file_artist
                    track.matched_artist = file_artist
                    needs_update = True
                    
                if file_title and track.title != file_title:
                    track.title = file_title
                    track.matched_title = file_title
                    needs_update = True
                
                # If file has album tag, mark as series_tagged
                # If file has NO album tag, clear series_tagged
                if file_album:
                    if not track.series_tagged:
                        track.series_tagged = True
                        needs_update = True
                else:
                    if track.series_tagged:
                        track.series_tagged = False
                        track.matched_album = None
                        needs_update = True
                
                if needs_update:
                    updated += 1
                    
            except Exception as e:
                errors.append({'filename': track.filename, 'error': str(e)})
                logger.error(f"Error resyncing {track.filepath}: {e}")
        
        await db.commit()
    
    return {
        "message": f"Resynced {updated} tracks out of {checked} checked",
        "checked": checked,
        "updated": updated,
        "errors": errors
    }


@router.post("/series/backfill-markers")
async def backfill_series_markers():
    """
    Backfill series markers to file metadata for all tracks that are series_tagged
    in the database but may not have the marker written to the file.
    
    This is useful after upgrading to ensure existing tagged tracks will be
    recognized on fresh installs.
    """
    from backend.services.tagger import AudioTagger
    
    tagger = AudioTagger()
    updated = 0
    skipped = 0
    errors = []
    
    async with get_db() as db:
        # Get all series-tagged tracks
        result = await db.execute(
            select(Track).where(Track.series_tagged == True)
        )
        tracks = result.scalars().all()
        
        logger.info(f"Backfilling series markers for {len(tracks)} tagged tracks")
        
        for track in tracks:
            try:
                if not os.path.exists(track.filepath):
                    skipped += 1
                    continue
                
                # Write the series marker (this will add TIT1/GROUPING tag)
                # We pass the existing album to trigger the marker write
                album = track.album or track.matched_album
                if album:
                    success = await tagger.write_album_artist(
                        track.filepath,
                        album=album,
                        artist=None,
                        genre=None,
                        album_artist=None
                    )
                    if success:
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
                    
            except Exception as e:
                errors.append({'filename': track.filename, 'error': str(e)})
                logger.error(f"Error backfilling marker for {track.filepath}: {e}")
    
    logger.info(f"Backfill complete: {updated} updated, {skipped} skipped, {len(errors)} errors")
    
    return {
        "message": f"Backfilled series markers for {updated} tracks",
        "updated": updated,
        "skipped": skipped,
        "errors": errors
    }


@router.post("/series/remove-from-series")
async def remove_from_series(track_ids: List[int]):
    """
    Remove tracks from their series by clearing album tag and series_tagged flag.
    Also removes the series marker from the file metadata.
    """
    from backend.services.tagger import AudioTagger
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    from mutagen.oggvorbis import OggVorbis
    
    updated = 0
    errors = []
    
    async with get_db() as db:
        result = await db.execute(
            select(Track).where(Track.id.in_(track_ids))
        )
        tracks = result.scalars().all()
        
        logger.info(f"Removing {len(tracks)} tracks from series")
        
        for track in tracks:
            try:
                if not os.path.exists(track.filepath):
                    errors.append({'filename': track.filename, 'error': 'File not found'})
                    continue
                
                ext = os.path.splitext(track.filepath)[1].lower()
                
                # Clear album and series marker from file
                try:
                    if ext == '.mp3':
                        audio = ID3(track.filepath)
                        # Remove album tag
                        if 'TALB' in audio:
                            del audio['TALB']
                        # Remove series marker
                        if 'TIT1' in audio:
                            del audio['TIT1']
                        audio.save(track.filepath)
                        
                    elif ext == '.flac':
                        audio = FLAC(track.filepath)
                        if 'ALBUM' in audio:
                            del audio['ALBUM']
                        if 'GROUPING' in audio:
                            del audio['GROUPING']
                        audio.save()
                        
                    elif ext in ['.m4a', '.aac', '.mp4']:
                        audio = MP4(track.filepath)
                        if '\xa9alb' in audio:
                            del audio['\xa9alb']
                        if '\xa9grp' in audio:
                            del audio['\xa9grp']
                        audio.save()
                        
                    elif ext == '.ogg':
                        audio = OggVorbis(track.filepath)
                        if 'ALBUM' in audio:
                            del audio['ALBUM']
                        if 'GROUPING' in audio:
                            del audio['GROUPING']
                        audio.save()
                        
                except Exception as e:
                    logger.warning(f"Could not clear file tags for {track.filepath}: {e}")
                
                # Clear database fields
                track.album = None
                track.matched_album = None
                track.series_tagged = False
                updated += 1
                
                logger.info(f"Removed from series: {track.filename}")
                
            except Exception as e:
                errors.append({'filename': track.filename, 'error': str(e)})
                logger.error(f"Error removing {track.filepath} from series: {e}")
        
        await db.commit()
    
    return {
        "message": f"Removed {updated} tracks from series",
        "updated": updated,
        "errors": errors
    }
