"""
MusicBrainz API service for album/CD lookups
"""
import aiohttp
import asyncio
from loguru import logger
from typing import Optional, List, Dict

# MusicBrainz API endpoint
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
USER_AGENT = "SetList/1.0 (https://github.com/jvenuto80/setlist)"


async def search_album(query: str, artist: str = None, limit: int = 10) -> List[Dict]:
    """
    Search MusicBrainz for albums/releases matching the query.
    
    Args:
        query: Album name to search for
        artist: Optional artist name to narrow results
        limit: Maximum number of results to return
        
    Returns:
        List of album matches with metadata
    """
    results = []
    
    try:
        # Build search query
        search_query = f'release:"{query}"'
        if artist:
            search_query += f' AND artist:"{artist}"'
        
        params = {
            'query': search_query,
            'fmt': 'json',
            'limit': limit
        }
        
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MUSICBRAINZ_API}/release",
                params=params,
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    for release in data.get('releases', []):
                        # Extract artist info
                        artist_credit = release.get('artist-credit', [])
                        artists = []
                        for ac in artist_credit:
                            if 'artist' in ac:
                                artists.append(ac['artist'].get('name', ''))
                        artist_name = ', '.join(artists) if artists else ''
                        
                        # Get release info
                        result = {
                            'id': release.get('id'),
                            'title': release.get('title', ''),
                            'artist': artist_name,
                            'date': release.get('date', ''),
                            'country': release.get('country', ''),
                            'track_count': release.get('track-count', 0),
                            'score': release.get('score', 0),
                            'disambiguation': release.get('disambiguation', ''),
                            'release_group_id': release.get('release-group', {}).get('id'),
                            'primary_type': release.get('release-group', {}).get('primary-type', ''),
                        }
                        
                        # Get label info if available
                        label_info = release.get('label-info', [])
                        if label_info:
                            labels = [li.get('label', {}).get('name', '') for li in label_info if li.get('label')]
                            result['label'] = ', '.join(labels)
                        
                        results.append(result)
                        
                elif response.status == 503:
                    logger.warning("MusicBrainz API rate limited, waiting...")
                    await asyncio.sleep(1)
                else:
                    logger.error(f"MusicBrainz API error: {response.status}")
                    
    except Exception as e:
        logger.error(f"Error searching MusicBrainz: {e}")
    
    return results


async def get_release_tracks(release_id: str) -> List[Dict]:
    """
    Get track listing for a specific MusicBrainz release.
    
    Args:
        release_id: MusicBrainz release ID
        
    Returns:
        List of tracks with title, position, duration
    """
    tracks = []
    
    try:
        params = {
            'fmt': 'json',
            'inc': 'recordings'
        }
        
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{MUSICBRAINZ_API}/release/{release_id}",
                params=params,
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Get tracks from media
                    for medium in data.get('media', []):
                        disc_number = medium.get('position', 1)
                        for track in medium.get('tracks', []):
                            tracks.append({
                                'position': track.get('position', 0),
                                'disc': disc_number,
                                'title': track.get('title', ''),
                                'duration_ms': track.get('length'),
                                'recording_id': track.get('recording', {}).get('id'),
                            })
                            
    except Exception as e:
        logger.error(f"Error getting release tracks from MusicBrainz: {e}")
    
    return tracks


async def search_by_tracks(track_names: List[str], limit: int = 5) -> List[Dict]:
    """
    Search for albums by matching track names.
    Useful for identifying an album when you have the track listing.
    
    Args:
        track_names: List of track names from the files
        limit: Maximum results to return
        
    Returns:
        List of potential album matches
    """
    results = []
    
    try:
        # Search for each track and collect release info
        release_scores = {}  # release_id -> {info, match_count}
        
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            for track_name in track_names[:5]:  # Limit to first 5 tracks to avoid rate limiting
                # Clean track name
                clean_name = track_name.strip()
                if not clean_name:
                    continue
                
                params = {
                    'query': f'recording:"{clean_name}"',
                    'fmt': 'json',
                    'limit': 10
                }
                
                try:
                    async with session.get(
                        f"{MUSICBRAINZ_API}/recording",
                        params=params,
                        headers=headers
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            for recording in data.get('recordings', []):
                                # Get releases this recording appears on
                                for release in recording.get('releases', []):
                                    release_id = release.get('id')
                                    if release_id:
                                        if release_id not in release_scores:
                                            # Extract artist info
                                            artist_credit = recording.get('artist-credit', [])
                                            artists = []
                                            for ac in artist_credit:
                                                if 'artist' in ac:
                                                    artists.append(ac['artist'].get('name', ''))
                                            artist_name = ', '.join(artists) if artists else ''
                                            
                                            release_scores[release_id] = {
                                                'id': release_id,
                                                'title': release.get('title', ''),
                                                'artist': artist_name,
                                                'track_count': release.get('track-count', 0),
                                                'match_count': 0
                                            }
                                        release_scores[release_id]['match_count'] += 1
                                        
                except Exception as e:
                    logger.warning(f"Error searching for track '{track_name}': {e}")
                
                # Rate limiting - MusicBrainz allows 1 request per second
                await asyncio.sleep(1.1)
        
        # Sort by number of matching tracks
        sorted_releases = sorted(
            release_scores.values(),
            key=lambda x: -x['match_count']
        )
        
        results = sorted_releases[:limit]
        
    except Exception as e:
        logger.error(f"Error searching MusicBrainz by tracks: {e}")
    
    return results


async def get_cover_art_url(release_id: str) -> Optional[str]:
    """
    Get cover art URL from Cover Art Archive for a MusicBrainz release.
    
    Args:
        release_id: MusicBrainz release ID
        
    Returns:
        URL to cover art image or None
    """
    try:
        headers = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://coverartarchive.org/release/{release_id}",
                headers=headers,
                allow_redirects=True
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    images = data.get('images', [])
                    
                    # Prefer front cover
                    for img in images:
                        if img.get('front'):
                            return img.get('image') or img.get('thumbnails', {}).get('large')
                    
                    # Fall back to first image
                    if images:
                        return images[0].get('image') or images[0].get('thumbnails', {}).get('large')
                        
    except Exception as e:
        logger.debug(f"No cover art found for release {release_id}: {e}")
    
    return None
