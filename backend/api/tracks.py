"""
Tracks API endpoints
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from backend.services.database import get_db
from backend.models.track import Track, TrackResponse, TrackUpdate
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
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = Query(None, description="Filter by status: pending, matched, tagged, error"),
    search: Optional[str] = Query(None, description="Search in filename or title"),
    apply_duration_filter: bool = Query(True, description="Apply minimum duration filter from settings")
):
    """Get all scanned tracks with optional filtering"""
    async with get_db() as db:
        query = select(Track)
        
        if status:
            query = query.where(Track.status == status)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                (Track.filename.ilike(search_term)) | 
                (Track.title.ilike(search_term)) |
                (Track.artist.ilike(search_term))
            )
        
        # Apply minimum duration filter
        if apply_duration_filter:
            min_duration = get_min_duration_seconds()
            if min_duration > 0:
                query = query.where(Track.duration >= min_duration)
        
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


@router.get("/series/detect")
async def detect_series(min_tracks: int = Query(2, description="Minimum tracks to form a series")):
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
        # "2024-01-15" or "2024.01.15" format
        name = re.sub(r'\s*[\(\[]?\d{4}[\-\.]\d{2}[\-\.]\d{2}[\)\]]?', '', name)
        # Trailing dates like "- 2024-01-15"
        name = re.sub(r'\s*-\s*\d{4}-\d{2}-\d{2}\s*$', '', name)
        
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
        return intersection / union if union > 0 else 0.0
    
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
        # Build query with duration filter and exclude already series-tagged tracks
        # Use or_ to handle NULL values (series_tagged IS NULL OR series_tagged = False)
        query = select(Track).where(
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
                'episode': None,
                'directory': track.directory,
            })
        
        # Merge directory groups that have 2+ tracks and aren't already in series_groups
        existing_track_ids = set()
        for tracks_list in series_groups.values():
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
                        series_groups[f"dir:{normalized_dir}"] = new_tracks
                        for t in new_tracks:
                            t['display_name'] = dir_name
        
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
        
        # Build final series list
        series_list = []
        for normalized, track_list in series_groups.items():
            if len(track_list) >= min_tracks:
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
                
                for t in track_list:
                    t['suggested_album'] = series_name
                    t['suggested_artist'] = suggested_artist
                
                # Deduplicate tracks by ID
                seen_ids = set()
                unique_tracks = []
                for t in track_list:
                    if t['track_id'] not in seen_ids:
                        seen_ids.add(t['track_id'])
                        unique_tracks.append(t)
                
                if len(unique_tracks) >= min_tracks:
                    series_list.append({
                        'series_name': series_name,
                        'track_count': len(unique_tracks),
                        'tracks': sorted(unique_tracks, key=lambda x: (int(x['episode']) if x['episode'] and x['episode'].isdigit() else 0, x['filename'])),
                        'suggested_album': series_name,
                        'suggested_artist': suggested_artist
                    })
        
        return sorted(series_list, key=lambda x: -x['track_count'])
        # Build query with duration filter
        query = select(Track)
        if min_duration > 0:
            query = query.where(Track.duration >= min_duration)
        
        result = await db.execute(query)
        tracks = result.scalars().all()
        
        # Group tracks by normalized series name
        series_groups = defaultdict(list)
        
        for track in tracks:
            display_name, normalized, episode = extract_series_name(track.filename)
            
            if normalized and len(normalized) > 3:  # Skip very short names
                series_groups[normalized].append({
                    'track_id': track.id,
                    'filename': track.filename,
                    'display_name': display_name,
                    'current_album': track.album,
                    'matched_album': track.matched_album,
                    'current_artist': track.artist,
                    'episode': episode,
                })
        
        # Filter to only groups with multiple tracks (actual series)
        series_list = []
        for normalized, track_list in series_groups.items():
            if len(track_list) >= min_tracks:
                # Get the best display name (most common or use common prefix)
                display_names = [t['display_name'] for t in track_list]
                
                # Try to find a good series name
                # Count occurrences of each display name
                name_counts = defaultdict(int)
                for n in display_names:
                    name_counts[n] += 1
                
                # Use most common name, or find common prefix if all different
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
                
                # Prepare track list with suggested values
                for t in track_list:
                    t['suggested_album'] = series_name
                    t['suggested_artist'] = suggested_artist
                
                series_list.append({
                    'series_name': series_name,
                    'track_count': len(track_list),
                    'tracks': sorted(track_list, key=lambda x: (int(x['episode']) if x['episode'] and x['episode'].isdigit() else 0, x['filename'])),
                    'suggested_album': series_name,
                    'suggested_artist': suggested_artist
                })
        
        # Sort by track count (most tracks first)
        return sorted(series_list, key=lambda x: -x['track_count'])


@router.post("/series/apply-album")
async def apply_series_album_endpoint(
    track_ids: List[int],
    album: str = Query(..., description="Album name to apply"),
    artist: Optional[str] = Query(None, description="Artist name to apply")
):
    """Apply album (and optionally artist) to multiple tracks and write to files immediately"""
    from backend.services.tagger import AudioTagger
    
    tagger = AudioTagger()
    updated = 0
    written = 0
    tracks_to_write = []
    
    # First, update database records
    async with get_db() as db:
        for track_id in track_ids:
            result = await db.execute(select(Track).where(Track.id == track_id))
            track = result.scalar_one_or_none()
            
            if track:
                # Update matched fields
                track.matched_album = album
                track.album = album  # Also update current
                if artist:
                    track.matched_artist = artist
                    track.artist = artist
                if track.status == "pending":
                    track.status = "matched"
                
                # Mark as series tagged so it doesn't show up again
                track.series_tagged = True
                updated += 1
                
                # Save filepath for file writing later
                tracks_to_write.append(track.filepath)
        
        await db.commit()
    
    # Now write to files outside of db transaction to avoid locking
    for filepath in tracks_to_write:
        try:
            success = await tagger.write_album_artist(filepath, album, artist)
            if success:
                written += 1
        except Exception as e:
            logger.error(f"Failed to write tags to {filepath}: {e}")
    
    return {
        "message": f"Updated {updated} tracks, wrote tags to {written} files", 
        "updated": updated,
        "written": written
    }
