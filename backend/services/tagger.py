"""
Audio file tagger service - writes metadata and cover art to audio files
"""
import os
import shutil
import asyncio
import aiohttp
from io import BytesIO
from typing import Optional, List, Tuple, Dict
from datetime import datetime
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TCON, TDRC, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis

from PIL import Image
from sqlalchemy import select

from backend.services.database import get_db
from backend.models.track import Track, TagPreview
from backend.config import settings
from loguru import logger


class AudioTagger:
    """Service for writing metadata to audio files"""
    
    async def download_cover_art(self, url: str) -> Optional[bytes]:
        """Download cover art from URL"""
        if not url:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
        except Exception as e:
            logger.error(f"Error downloading cover art: {e}")
        
        return None
    
    def resize_cover_art(self, image_data: bytes, max_size: int = 800) -> bytes:
        """Resize cover art to reasonable size"""
        try:
            img = Image.open(BytesIO(image_data))
            
            # Convert to RGB if necessary (for JPEG)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Resize if larger than max_size
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # Save to bytes
            output = BytesIO()
            img.save(output, format='JPEG', quality=90)
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error resizing cover art: {e}")
            return image_data
    
    async def write_album_artist(
        self,
        filepath: str,
        album: Optional[str] = None,
        artist: Optional[str] = None,
        genre: Optional[str] = None,
        album_artist: Optional[str] = None
    ) -> bool:
        """Write album, artist, genre, and album artist tags to a file (quick update for series)"""
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return False
        
        ext = os.path.splitext(filepath)[1].lower()
        
        try:
            if ext == '.mp3':
                try:
                    audio = ID3(filepath)
                except ID3NoHeaderError:
                    audio = ID3()
                
                if album:
                    audio['TALB'] = TALB(encoding=3, text=album)
                if artist:
                    audio['TPE1'] = TPE1(encoding=3, text=artist)
                if genre:
                    from mutagen.id3 import TCON
                    audio['TCON'] = TCON(encoding=3, text=genre)
                if album_artist:
                    from mutagen.id3 import TPE2
                    audio['TPE2'] = TPE2(encoding=3, text=album_artist)
                
                audio.save(filepath)
                logger.info(f"Updated album/artist/genre/album_artist tags for: {filepath}")
                return True
                
            elif ext == '.flac':
                audio = FLAC(filepath)
                if album:
                    audio['ALBUM'] = album
                if artist:
                    audio['ARTIST'] = artist
                if genre:
                    audio['GENRE'] = genre
                if album_artist:
                    audio['ALBUMARTIST'] = album_artist
                audio.save()
                logger.info(f"Updated album/artist/genre/album_artist tags for: {filepath}")
                return True
                
            elif ext in ['.m4a', '.aac', '.mp4']:
                audio = MP4(filepath)
                if album:
                    audio['\xa9alb'] = [album]
                if artist:
                    audio['\xa9ART'] = [artist]
                if genre:
                    audio['\xa9gen'] = [genre]
                if album_artist:
                    audio['aART'] = [album_artist]
                audio.save()
                logger.info(f"Updated album/artist/genre/album_artist tags for: {filepath}")
                return True
                
            elif ext == '.ogg':
                audio = OggVorbis(filepath)
                if album:
                    audio['ALBUM'] = [album]
                if artist:
                    audio['ARTIST'] = [artist]
                if genre:
                    audio['GENRE'] = [genre]
                if album_artist:
                    audio['ALBUMARTIST'] = [album_artist]
                audio.save()
                logger.info(f"Updated album/artist/genre/album_artist tags for: {filepath}")
                return True
            
            else:
                logger.warning(f"Unsupported format for quick tag update: {ext}")
                return False
                
        except Exception as e:
            logger.error(f"Error writing album/artist/genre/album_artist to {filepath}: {e}")
            return False
    
    def _write_album_artist_cover_sync(
        self,
        filepath: str,
        album: Optional[str] = None,
        artist: Optional[str] = None,
        genre: Optional[str] = None,
        album_artist: Optional[str] = None,
        cover_data: Optional[bytes] = None
    ) -> bool:
        """Synchronous version - Write album, artist, genre, album artist, and cover art tags to a file"""
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return False
        
        ext = os.path.splitext(filepath)[1].lower()
        
        try:
            if ext == '.mp3':
                try:
                    audio = ID3(filepath)
                except ID3NoHeaderError:
                    audio = ID3()
                
                if album:
                    audio['TALB'] = TALB(encoding=3, text=album)
                if artist:
                    audio['TPE1'] = TPE1(encoding=3, text=artist)
                if genre:
                    from mutagen.id3 import TCON
                    audio['TCON'] = TCON(encoding=3, text=genre)
                if album_artist:
                    from mutagen.id3 import TPE2
                    audio['TPE2'] = TPE2(encoding=3, text=album_artist)
                
                # Set cover art
                if cover_data:
                    audio['APIC'] = APIC(
                        encoding=3,
                        mime='image/jpeg',
                        type=3,  # Cover (front)
                        desc='Cover',
                        data=cover_data
                    )
                
                audio.save(filepath)
                return True
                
            elif ext == '.flac':
                audio = FLAC(filepath)
                if album:
                    audio['ALBUM'] = album
                if artist:
                    audio['ARTIST'] = artist
                if genre:
                    audio['GENRE'] = genre
                if album_artist:
                    audio['ALBUMARTIST'] = album_artist
                
                # Set cover art
                if cover_data:
                    from mutagen.flac import Picture
                    picture = Picture()
                    picture.type = 3  # Cover (front)
                    picture.mime = 'image/jpeg'
                    picture.desc = 'Cover'
                    picture.data = cover_data
                    # Get image dimensions
                    from PIL import Image
                    from io import BytesIO
                    img = Image.open(BytesIO(cover_data))
                    picture.width = img.width
                    picture.height = img.height
                    picture.depth = 24
                    audio.clear_pictures()
                    audio.add_picture(picture)
                
                audio.save()
                return True
                
            elif ext in ['.m4a', '.aac', '.mp4']:
                audio = MP4(filepath)
                if album:
                    audio['\xa9alb'] = [album]
                if artist:
                    audio['\xa9ART'] = [artist]
                if genre:
                    audio['\xa9gen'] = [genre]
                if album_artist:
                    audio['aART'] = [album_artist]
                
                # Set cover art
                if cover_data:
                    audio['covr'] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
                
                audio.save()
                return True
                
            elif ext == '.ogg':
                audio = OggVorbis(filepath)
                if album:
                    audio['ALBUM'] = [album]
                if artist:
                    audio['ARTIST'] = [artist]
                if genre:
                    audio['GENRE'] = [genre]
                if album_artist:
                    audio['ALBUMARTIST'] = [album_artist]
                
                # OGG cover art requires base64 encoding in METADATA_BLOCK_PICTURE
                if cover_data:
                    import base64
                    from mutagen.flac import Picture
                    picture = Picture()
                    picture.type = 3
                    picture.mime = 'image/jpeg'
                    picture.desc = 'Cover'
                    picture.data = cover_data
                    from PIL import Image
                    from io import BytesIO
                    img = Image.open(BytesIO(cover_data))
                    picture.width = img.width
                    picture.height = img.height
                    picture.depth = 24
                    audio['metadata_block_picture'] = [base64.b64encode(picture.write()).decode('ascii')]
                
                audio.save()
                return True
            
            else:
                logger.warning(f"Unsupported format for tag update with cover: {ext}")
                return False
                
        except Exception as e:
            logger.error(f"Error writing tags with cover to {filepath}: {e}")
            return False
    
    async def write_album_artist_cover(
        self,
        filepath: str,
        album: Optional[str] = None,
        artist: Optional[str] = None,
        genre: Optional[str] = None,
        album_artist: Optional[str] = None,
        cover_data: Optional[bytes] = None
    ) -> bool:
        """Async wrapper - runs file I/O in thread pool to not block event loop"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,  # Uses default thread pool
            self._write_album_artist_cover_sync,
            filepath, album, artist, genre, album_artist, cover_data
        )
    
    def tag_mp3(
        self,
        filepath: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        year: Optional[str] = None,
        cover_data: Optional[bytes] = None
    ) -> bool:
        """Tag an MP3 file"""
        try:
            # Try to get existing ID3 tags, or create new
            try:
                audio = ID3(filepath)
            except ID3NoHeaderError:
                audio = ID3()
            
            # Set tags
            if title:
                audio['TIT2'] = TIT2(encoding=3, text=title)
            if artist:
                audio['TPE1'] = TPE1(encoding=3, text=artist)
            if album:
                audio['TALB'] = TALB(encoding=3, text=album)
            if genre:
                audio['TCON'] = TCON(encoding=3, text=genre)
            if year:
                audio['TDRC'] = TDRC(encoding=3, text=str(year))
            
            # Set cover art
            if cover_data:
                audio['APIC'] = APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=cover_data
                )
            
            audio.save(filepath)
            return True
            
        except Exception as e:
            logger.error(f"Error tagging MP3 {filepath}: {e}")
            return False
    
    def tag_flac(
        self,
        filepath: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        year: Optional[str] = None,
        cover_data: Optional[bytes] = None
    ) -> bool:
        """Tag a FLAC file"""
        try:
            audio = FLAC(filepath)
            
            # Set tags
            if title:
                audio['TITLE'] = title
            if artist:
                audio['ARTIST'] = artist
            if album:
                audio['ALBUM'] = album
            if genre:
                audio['GENRE'] = genre
            if year:
                audio['DATE'] = str(year)
            
            # Set cover art
            if cover_data:
                picture = Picture()
                picture.type = 3  # Cover (front)
                picture.mime = 'image/jpeg'
                picture.desc = 'Cover'
                picture.data = cover_data
                
                # Get image dimensions
                img = Image.open(BytesIO(cover_data))
                picture.width = img.width
                picture.height = img.height
                picture.depth = 24
                
                # Clear existing pictures and add new one
                audio.clear_pictures()
                audio.add_picture(picture)
            
            audio.save()
            return True
            
        except Exception as e:
            logger.error(f"Error tagging FLAC {filepath}: {e}")
            return False
    
    def tag_m4a(
        self,
        filepath: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        year: Optional[str] = None,
        cover_data: Optional[bytes] = None
    ) -> bool:
        """Tag an M4A/AAC file"""
        try:
            audio = MP4(filepath)
            
            # Set tags using iTunes tags
            if title:
                audio['\xa9nam'] = [title]
            if artist:
                audio['\xa9ART'] = [artist]
            if album:
                audio['\xa9alb'] = [album]
            if genre:
                audio['\xa9gen'] = [genre]
            if year:
                audio['\xa9day'] = [str(year)]
            
            # Set cover art
            if cover_data:
                audio['covr'] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
            
            audio.save()
            return True
            
        except Exception as e:
            logger.error(f"Error tagging M4A {filepath}: {e}")
            return False
    
    def tag_ogg(
        self,
        filepath: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        year: Optional[str] = None,
        cover_data: Optional[bytes] = None
    ) -> bool:
        """Tag an OGG Vorbis file"""
        try:
            audio = OggVorbis(filepath)
            
            # Set tags
            if title:
                audio['TITLE'] = title
            if artist:
                audio['ARTIST'] = artist
            if album:
                audio['ALBUM'] = album
            if genre:
                audio['GENRE'] = genre
            if year:
                audio['DATE'] = str(year)
            
            # Note: OGG cover art is more complex, skipping for now
            # Would need to embed as METADATA_BLOCK_PICTURE
            
            audio.save()
            return True
            
        except Exception as e:
            logger.error(f"Error tagging OGG {filepath}: {e}")
            return False
    
    async def tag_file(
        self,
        filepath: str,
        title: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        year: Optional[str] = None,
        cover_url: Optional[str] = None
    ) -> bool:
        """Tag an audio file based on its format"""
        ext = Path(filepath).suffix.lower()
        
        # Download cover art if provided
        cover_data = None
        if cover_url:
            cover_data = await self.download_cover_art(cover_url)
            if cover_data:
                cover_data = self.resize_cover_art(cover_data)
        
        # Tag based on format
        if ext == '.mp3':
            return self.tag_mp3(filepath, title, artist, album, genre, year, cover_data)
        elif ext == '.flac':
            return self.tag_flac(filepath, title, artist, album, genre, year, cover_data)
        elif ext in ['.m4a', '.aac', '.mp4']:
            return self.tag_m4a(filepath, title, artist, album, genre, year, cover_data)
        elif ext == '.ogg':
            return self.tag_ogg(filepath, title, artist, album, genre, year, cover_data)
        else:
            logger.warning(f"Unsupported format for tagging: {ext}")
            return False
    
    def get_current_tags(self, filepath: str) -> Dict:
        """Get current tags from a file"""
        tags = {
            "title": None,
            "artist": None,
            "album": None,
            "genre": None,
            "year": None,
            "has_cover": False
        }
        
        try:
            audio = MutagenFile(filepath, easy=True)
            if audio:
                tags["title"] = audio.get("title", [None])[0]
                tags["artist"] = audio.get("artist", [None])[0]
                tags["album"] = audio.get("album", [None])[0]
                tags["genre"] = audio.get("genre", [None])[0]
                tags["year"] = audio.get("date", [None])[0] or audio.get("year", [None])[0]
            
            # Check for cover art (non-easy mode)
            audio_full = MutagenFile(filepath)
            if audio_full:
                if hasattr(audio_full, 'pictures') and audio_full.pictures:
                    tags["has_cover"] = True
                elif hasattr(audio_full, 'tags'):
                    if 'APIC:' in str(audio_full.tags) or 'APIC:Cover' in str(audio_full.tags):
                        tags["has_cover"] = True
                    if 'covr' in audio_full.tags:
                        tags["has_cover"] = True
                        
        except Exception as e:
            logger.error(f"Error reading tags from {filepath}: {e}")
        
        return tags


# Global tagger instance
_tagger: Optional[AudioTagger] = None


def get_tagger() -> AudioTagger:
    """Get or create AudioTagger instance"""
    global _tagger
    if _tagger is None:
        _tagger = AudioTagger()
    return _tagger


async def tag_track(track_id: int) -> bool:
    """Apply matched metadata to a track file"""
    tagger = get_tagger()
    
    async with get_db() as db:
        result = await db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        
        if not track:
            logger.error(f"Track {track_id} not found")
            return False
        
        if not os.path.exists(track.filepath):
            logger.error(f"File not found: {track.filepath}")
            track.status = "error"
            track.error_message = "File not found"
            await db.commit()
            return False
        
        logger.info(f"Tagging track: {track.filename}")
        
        try:
            success = await tagger.tag_file(
                filepath=track.filepath,
                title=track.matched_title or track.title,
                artist=track.matched_artist or track.artist,
                album=track.matched_album or track.album,
                genre=track.matched_genre or track.genre,
                year=track.matched_year or track.year,
                cover_url=track.matched_cover_url
            )
            
            if success:
                track.status = "tagged"
                track.tagged_at = datetime.utcnow()
                
                # Update current tags with matched values
                track.title = track.matched_title or track.title
                track.artist = track.matched_artist or track.artist
                track.genre = track.matched_genre or track.genre
                
                await db.commit()
                logger.info(f"Successfully tagged track {track_id}")
                return True
            else:
                track.status = "error"
                track.error_message = "Failed to write tags"
                await db.commit()
                return False
                
        except Exception as e:
            logger.error(f"Error tagging track {track_id}: {e}")
            track.status = "error"
            track.error_message = str(e)
            await db.commit()
            return False


async def batch_tag_tracks(
    track_ids: Optional[List[int]] = None,
    apply_all_matched: bool = False
):
    """Tag multiple tracks"""
    async with get_db() as db:
        query = select(Track.id)
        
        if track_ids:
            query = query.where(Track.id.in_(track_ids))
        elif apply_all_matched:
            query = query.where(Track.status == "matched")
        else:
            return
        
        result = await db.execute(query)
        ids_to_tag = [row[0] for row in result.fetchall()]
    
    logger.info(f"Batch tagging {len(ids_to_tag)} tracks")
    
    for track_id in ids_to_tag:
        await tag_track(track_id)


async def preview_tag_changes(track: Track) -> TagPreview:
    """Preview what tags would be changed"""
    tagger = get_tagger()
    
    current_tags = tagger.get_current_tags(track.filepath)
    
    new_tags = {
        "title": track.matched_title or track.title,
        "artist": track.matched_artist or track.artist,
        "album": track.matched_album or track.album,
        "genre": track.matched_genre or track.genre,
        "year": track.matched_year or track.year,
        "has_cover": bool(track.matched_cover_url)
    }
    
    changes = []
    for field in ["title", "artist", "album", "genre", "year"]:
        old_val = current_tags.get(field)
        new_val = new_tags.get(field)
        if old_val != new_val and new_val:
            changes.append({
                "field": field,
                "old_value": old_val,
                "new_value": new_val
            })
    
    if not current_tags.get("has_cover") and new_tags.get("has_cover"):
        changes.append({
            "field": "cover_art",
            "old_value": "None",
            "new_value": "Will be added"
        })
    
    return TagPreview(
        track_id=track.id,
        filename=track.filename,
        current_tags=current_tags,
        new_tags=new_tags,
        changes=changes
    )


async def rename_track_file(track: Track, new_filename: str) -> Tuple[bool, str]:
    """Rename a track file"""
    try:
        old_path = track.filepath
        directory = os.path.dirname(old_path)
        ext = Path(old_path).suffix
        
        # Sanitize filename
        safe_filename = "".join(c for c in new_filename if c.isalnum() or c in " -_()").strip()
        new_path = os.path.join(directory, f"{safe_filename}{ext}")
        
        # Check if new path already exists
        if os.path.exists(new_path) and new_path != old_path:
            logger.error(f"File already exists: {new_path}")
            return False, old_path
        
        # Rename file
        shutil.move(old_path, new_path)
        logger.info(f"Renamed: {old_path} -> {new_path}")
        
        return True, new_path
        
    except Exception as e:
        logger.error(f"Error renaming track: {e}")
        return False, track.filepath


async def batch_rename_tracks(
    track_ids: Optional[List[int]] = None,
    pattern: str = "{artist} - {title}"
):
    """Rename multiple tracks using a pattern"""
    async with get_db() as db:
        query = select(Track)
        
        if track_ids:
            query = query.where(Track.id.in_(track_ids))
        else:
            query = query.where(Track.status == "matched")
        
        result = await db.execute(query)
        tracks = result.scalars().all()
    
    logger.info(f"Batch renaming {len(tracks)} tracks with pattern: {pattern}")
    
    for track in tracks:
        # Build new filename from pattern
        new_filename = pattern
        
        replacements = {
            "{artist}": track.matched_artist or track.artist or "Unknown Artist",
            "{title}": track.matched_title or track.title or "Unknown Title",
            "{genre}": track.matched_genre or track.genre or "Unknown Genre",
            "{year}": track.matched_year or track.year or "",
            "{dj}": track.matched_dj or "",
            "{event}": track.matched_event or ""
        }
        
        for placeholder, value in replacements.items():
            new_filename = new_filename.replace(placeholder, value)
        
        # Clean up the filename
        new_filename = new_filename.strip(" -")
        
        if new_filename:
            success, new_path = await rename_track_file(track, new_filename)
            
            if success:
                async with get_db() as db:
                    result = await db.execute(select(Track).where(Track.id == track.id))
                    db_track = result.scalar_one_or_none()
                    if db_track:
                        db_track.filepath = new_path
                        db_track.filename = os.path.basename(new_path)
                        await db.commit()
