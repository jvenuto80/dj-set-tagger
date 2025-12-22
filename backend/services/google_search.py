"""
Web Search-based tracklist discovery
Searches for DJ set tracklists across multiple sources and extracts track information
Uses DuckDuckGo HTML search (less restrictive than Google)
"""
import re
import asyncio
import random
import aiohttp
from typing import List, Dict, Optional, Any
from urllib.parse import quote_plus, urlparse, parse_qs
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
from loguru import logger


class GoogleTracklistSearch:
    """Search the web for tracklist information and scrape from various sources"""
    
    # DuckDuckGo HTML endpoint (doesn't require JavaScript)
    DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
    GOOGLE_SEARCH_URL = "https://www.google.com/search"
    
    # Known tracklist sources with their parsers
    KNOWN_SOURCES = {
        "1001tracklists.com": "parse_1001tracklists",
        "mixesdb.com": "parse_mixesdb",
        "discogs.com": "parse_discogs",
        "musicbrainz.org": "parse_musicbrainz",
        "djmag.com": "parse_generic",
        "reddit.com": "parse_reddit",
        "setlist.fm": "parse_setlistfm",
    }
    
    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self.delay = 2.0  # Delay between requests
        
    async def _get_browser(self) -> Browser:
        """Get or create browser instance"""
        if self._browser is None or not self._browser.is_connected():
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu'
                ]
            )
        return self._browser
    
    async def _fetch_page(self, url: str, wait_time: float = 2.0) -> Optional[BeautifulSoup]:
        """Fetch a page using Playwright"""
        browser = await self._get_browser()
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        try:
            await asyncio.sleep(self.delay + random.uniform(0.5, 1.5))
            logger.debug(f"Fetching: {url}")
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(wait_time)
            
            content = await page.content()
            return BeautifulSoup(content, "lxml")
            
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
        finally:
            await page.close()
    
    def _build_search_query(self, artist: str, title: str, extra_terms: List[str] = None) -> str:
        """Build an optimized search query for DJ set tracklist discovery"""
        query_parts = []
        
        # Add artist if available
        if artist:
            query_parts.append(f'"{artist.strip()}"')
        
        # Add title
        if title:
            # Clean up common patterns
            clean_title = re.sub(r'\.(mp3|flac|wav|m4a)$', '', title, flags=re.IGNORECASE)
            clean_title = re.sub(r'^\d+[-_\s]*', '', clean_title)  # Remove track numbers
            clean_title = clean_title.replace('_', ' ').replace('-', ' - ')
            query_parts.append(clean_title)
        
        # Add DJ/tracklist keywords (broader to catch more results)
        query_parts.append("tracklist")
        
        # Add extra search terms
        if extra_terms:
            query_parts.extend(extra_terms)
        
        return " ".join(query_parts)
    
    async def search_google(self, query: str, num_results: int = 10) -> List[Dict]:
        """
        Search the web and return relevant results
        Uses DuckDuckGo HTML for better reliability
        
        Returns list of dicts with: url, title, snippet, domain
        """
        # Try DuckDuckGo lite (simpler interface)
        results = await self._search_duckduckgo_lite(query, num_results)
        
        if results:
            return results
        
        # Fallback to scraping Google
        return await self._search_google_fallback(query, num_results)
    
    async def _search_duckduckgo_lite(self, query: str, num_results: int = 10) -> List[Dict]:
        """Search using DuckDuckGo lite interface (no JavaScript)"""
        import aiohttp
        
        logger.info(f"Searching DuckDuckGo Lite: {query}")
        
        try:
            # DuckDuckGo Lite endpoint
            url = "https://lite.duckduckgo.com/lite/"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data={"q": query, "kl": ""},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                        "Accept": "text/html,application/xhtml+xml",
                    }
                ) as response:
                    if response.status != 200:
                        logger.warning(f"DuckDuckGo returned status {response.status}")
                        return []
                    
                    html = await response.text()
            
            soup = BeautifulSoup(html, "lxml")
            results = []
            
            # DuckDuckGo Lite uses tables for results
            # Results are in <a class="result-link"> or plain table cells
            links = soup.select('a.result-link') or soup.select('td a[href^="http"]')
            
            for link in links[:num_results * 2]:  # Get extra in case some are filtered
                try:
                    href = link.get('href', '')
                    
                    # Skip internal DDG links
                    if not href.startswith('http') or 'duckduckgo.com' in href:
                        continue
                    
                    title = link.get_text(strip=True)
                    if not title or len(title) < 3:
                        continue
                    
                    domain = urlparse(href).netloc.replace('www.', '')
                    
                    results.append({
                        "url": href,
                        "title": title,
                        "snippet": "",
                        "domain": domain
                    })
                    
                    if len(results) >= num_results:
                        break
                    
                except Exception as e:
                    logger.debug(f"Error parsing DDG result: {e}")
                    continue
            
            logger.info(f"Found {len(results)} DuckDuckGo results")
            return results
            
        except Exception as e:
            logger.error(f"DuckDuckGo Lite search error: {e}")
            return []
    
    async def _search_google_fallback(self, query: str, num_results: int = 10) -> List[Dict]:
        """Fallback to Google search using Playwright"""
        encoded_query = quote_plus(query)
        search_url = f"{self.GOOGLE_SEARCH_URL}?q={encoded_query}&num={num_results}"
        
        logger.info(f"Searching Google (fallback): {query}")
        
        soup = await self._fetch_page(search_url, wait_time=3.0)
        if not soup:
            return []
        
        results = []
        
        # Parse Google search results
        search_divs = soup.select('div.g') or soup.select('div[data-hveid]')
        
        for div in search_divs[:num_results]:
            try:
                link = div.select_one('a[href^="http"]') or div.select_one('a[href^="/url"]')
                if not link:
                    continue
                
                href = link.get('href', '')
                
                if href.startswith('/url?'):
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    href = qs.get('q', [href])[0]
                
                if 'google.com' in href:
                    continue
                
                title_elem = div.select_one('h3') or link
                title = title_elem.get_text(strip=True) if title_elem else ""
                
                snippet_elem = div.select_one('div[data-sncf]') or div.select_one('span.st') or div.select_one('div.VwiC3b')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                
                domain = urlparse(href).netloc.replace('www.', '')
                
                results.append({
                    "url": href,
                    "title": title,
                    "snippet": snippet,
                    "domain": domain
                })
                
            except Exception as e:
                logger.debug(f"Error parsing Google result: {e}")
                continue
        
        logger.info(f"Found {len(results)} Google results")
        return results
    
    async def scrape_tracklist_from_url(self, url: str) -> Optional[Dict]:
        """
        Scrape tracklist information from a URL
        Returns dict with: title, artist, tracks, genres, date, source_url
        """
        domain = urlparse(url).netloc.replace('www.', '')
        
        soup = await self._fetch_page(url, wait_time=3.0)
        if not soup:
            return None
        
        # Try domain-specific parser first
        parser_name = self.KNOWN_SOURCES.get(domain)
        if parser_name and hasattr(self, parser_name):
            parser = getattr(self, parser_name)
            result = parser(soup, url)
            if result and result.get('tracks'):
                return result
        
        # Fall back to generic parser
        return self.parse_generic(soup, url)
    
    def parse_1001tracklists(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """Parse 1001Tracklists page"""
        result = {
            "source": "1001tracklists",
            "source_url": url,
            "tracks": [],
            "title": "",
            "artist": "",
            "genres": [],
            "date": "",
            "cover_url": ""
        }
        
        # Get cover art
        result["cover_url"] = self._extract_cover_art(soup, url)
        
        # Get title
        title_elem = soup.select_one('h1#pageTitle, h1.tlTitle, meta[property="og:title"]')
        if title_elem:
            result["title"] = title_elem.get('content') if title_elem.name == 'meta' else title_elem.get_text(strip=True)
        
        # Get DJ/Artist
        dj_elem = soup.select_one('meta[name="description"]')
        if dj_elem:
            desc = dj_elem.get('content', '')
            # Extract DJ name from description
            match = re.search(r'^([^-–]+)\s*[-–]', desc)
            if match:
                result["artist"] = match.group(1).strip()
        
        # Get tracks
        track_rows = soup.select('div.tlpItem, div.trackItem, tr.tlpItem')
        for idx, row in enumerate(track_rows, 1):
            track_info = self._extract_track_from_1001(row, idx)
            if track_info:
                result["tracks"].append(track_info)
        
        # Get genres
        genre_elems = soup.select('a[href*="/genre/"]')
        result["genres"] = list(set(g.get_text(strip=True) for g in genre_elems[:5]))
        
        # Get date
        date_elem = soup.select_one('span.recording-date, div.dateDiv')
        if date_elem:
            result["date"] = date_elem.get_text(strip=True)
        
        return result if result["tracks"] else None
    
    def _extract_track_from_1001(self, row, position: int) -> Optional[Dict]:
        """Extract track info from a 1001tracklists row"""
        try:
            # Try various selectors for track title
            title_elem = row.select_one('span.trackValue, a.trackValue, div.trackTitle')
            if not title_elem:
                return None
            
            track_text = title_elem.get_text(strip=True)
            
            # Parse "Artist - Title" format
            artist, title = "", track_text
            if " - " in track_text:
                parts = track_text.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip() if len(parts) > 1 else ""
            
            # Get time if available
            time_elem = row.select_one('span.cueValueField, span.timeValue')
            time = time_elem.get_text(strip=True) if time_elem else ""
            
            return {
                "position": position,
                "artist": artist,
                "title": title,
                "time": time
            }
        except Exception:
            return None
    
    def parse_mixesdb(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """Parse MixesDB page"""
        result = {
            "source": "mixesdb",
            "source_url": url,
            "tracks": [],
            "title": "",
            "artist": "",
            "genres": [],
            "date": "",
            "cover_url": ""
        }
        
        # Get cover art
        result["cover_url"] = self._extract_cover_art(soup, url)
        
        # Get title from h1 or page title
        title_elem = soup.select_one('h1.firstHeading, h1')
        if title_elem:
            result["title"] = title_elem.get_text(strip=True)
        
        # Parse tracklist table
        tracklist_section = soup.find(string=re.compile(r'Tracklist|Track\s*list', re.I))
        if tracklist_section:
            parent = tracklist_section.find_parent(['div', 'section', 'table'])
            if parent:
                # Look for ordered list or table
                tracks = parent.select('li, tr')
                for idx, track in enumerate(tracks, 1):
                    text = track.get_text(strip=True)
                    if text and len(text) > 5:
                        artist, title = self._parse_track_string(text)
                        result["tracks"].append({
                            "position": idx,
                            "artist": artist,
                            "title": title
                        })
        
        return result if result["tracks"] else None
    
    def parse_discogs(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """Parse Discogs page"""
        result = {
            "source": "discogs",
            "source_url": url,
            "tracks": [],
            "title": "",
            "artist": "",
            "genres": [],
            "date": "",
            "cover_url": ""
        }
        
        # Get cover art
        result["cover_url"] = self._extract_cover_art(soup, url)
        
        # Get title
        title_elem = soup.select_one('h1.title_1q3xW')
        if title_elem:
            result["title"] = title_elem.get_text(strip=True)
        
        # Get artist
        artist_elem = soup.select_one('a[href*="/artist/"]')
        if artist_elem:
            result["artist"] = artist_elem.get_text(strip=True)
        
        # Get tracks from tracklist
        track_rows = soup.select('tr.tracklist_track')
        for idx, row in enumerate(track_rows, 1):
            title_elem = row.select_one('span.trackTitle_CTKp4, td.trackTitle')
            if title_elem:
                result["tracks"].append({
                    "position": idx,
                    "artist": result.get("artist", ""),
                    "title": title_elem.get_text(strip=True)
                })
        
        # Get genres
        genre_elems = soup.select('a[href*="/genre/"], a[href*="/style/"]')
        result["genres"] = list(set(g.get_text(strip=True) for g in genre_elems[:5]))
        
        return result if result["tracks"] else None
    
    def parse_reddit(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """Parse Reddit post for tracklist"""
        result = {
            "source": "reddit",
            "source_url": url,
            "tracks": [],
            "title": "",
            "artist": "",
            "genres": [],
            "date": "",
            "cover_url": ""
        }
        
        # Get cover art
        result["cover_url"] = self._extract_cover_art(soup, url)
        
        # Get post title
        title_elem = soup.select_one('h1, [data-testid="post-title"]')
        if title_elem:
            result["title"] = title_elem.get_text(strip=True)
        
        # Get post content
        content_elem = soup.select_one('[data-testid="post-content"], div.md, div.usertext-body')
        if content_elem:
            text = content_elem.get_text()
            result["tracks"] = self._extract_tracks_from_text(text)
        
        return result if result["tracks"] else None
    
    def parse_setlistfm(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """Parse Setlist.fm page"""
        result = {
            "source": "setlistfm",
            "source_url": url,
            "tracks": [],
            "title": "",
            "artist": "",
            "genres": [],
            "date": "",
            "cover_url": ""
        }
        
        # Get cover art
        result["cover_url"] = self._extract_cover_art(soup, url)
        
        # Get artist
        artist_elem = soup.select_one('h1 a[href*="/setlists/"]')
        if artist_elem:
            result["artist"] = artist_elem.get_text(strip=True)
        
        # Get venue/event info for title
        venue_elem = soup.select_one('a[href*="/venue/"]')
        date_elem = soup.select_one('span.dateString')
        if venue_elem or date_elem:
            parts = []
            if venue_elem:
                parts.append(venue_elem.get_text(strip=True))
            if date_elem:
                result["date"] = date_elem.get_text(strip=True)
                parts.append(result["date"])
            result["title"] = " @ ".join(parts)
        
        # Get songs
        song_elems = soup.select('li.song a.songLabel')
        for idx, song in enumerate(song_elems, 1):
            result["tracks"].append({
                "position": idx,
                "artist": result.get("artist", ""),
                "title": song.get_text(strip=True)
            })
        
        return result if result["tracks"] else None
    
    def parse_musicbrainz(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """Parse MusicBrainz page"""
        result = {
            "source": "musicbrainz",
            "source_url": url,
            "tracks": [],
            "title": "",
            "artist": "",
            "genres": [],
            "date": "",
            "cover_url": ""
        }
        
        # Get cover art
        result["cover_url"] = self._extract_cover_art(soup, url)
        
        # Get title
        title_elem = soup.select_one('h1 bdi, h1')
        if title_elem:
            result["title"] = title_elem.get_text(strip=True)
        
        # Get artist
        artist_elem = soup.select_one('p.subheader a[href*="/artist/"]')
        if artist_elem:
            result["artist"] = artist_elem.get_text(strip=True)
        
        # Get tracks
        track_rows = soup.select('table.medium tbody tr')
        for idx, row in enumerate(track_rows, 1):
            title_elem = row.select_one('td.title a bdi')
            if title_elem:
                result["tracks"].append({
                    "position": idx,
                    "artist": result.get("artist", ""),
                    "title": title_elem.get_text(strip=True)
                })
        
        return result if result["tracks"] else None
    
    def parse_generic(self, soup: BeautifulSoup, url: str) -> Optional[Dict]:
        """Generic parser that tries to extract tracklist from any page"""
        result = {
            "source": "web",
            "source_url": url,
            "tracks": [],
            "title": "",
            "artist": "",
            "genres": [],
            "date": "",
            "cover_url": ""
        }
        
        # Get page title
        title_elem = soup.select_one('h1, title')
        if title_elem:
            result["title"] = title_elem.get_text(strip=True)[:200]
        
        # Try to extract cover art from various sources
        result["cover_url"] = self._extract_cover_art(soup, url)
        
        # Look for tracklist patterns in the page
        page_text = soup.get_text()
        result["tracks"] = self._extract_tracks_from_text(page_text)
        
        # Also try to find structured tracklists
        if not result["tracks"]:
            result["tracks"] = self._find_structured_tracklist(soup)
        
        return result if result["tracks"] else None
    
    def _extract_cover_art(self, soup: BeautifulSoup, url: str) -> str:
        """Extract cover art URL from page using various methods"""
        cover_url = ""
        
        # Method 1: Open Graph image (most common for sharing)
        og_image = soup.select_one('meta[property="og:image"]')
        if og_image and og_image.get('content'):
            cover_url = og_image.get('content', '')
            if cover_url and self._is_valid_image_url(cover_url):
                return cover_url
        
        # Method 2: Twitter card image
        twitter_image = soup.select_one('meta[name="twitter:image"], meta[property="twitter:image"]')
        if twitter_image and twitter_image.get('content'):
            cover_url = twitter_image.get('content', '')
            if cover_url and self._is_valid_image_url(cover_url):
                return cover_url
        
        # Method 3: Schema.org image
        schema_image = soup.select_one('[itemprop="image"]')
        if schema_image:
            cover_url = schema_image.get('src') or schema_image.get('content', '')
            if cover_url and self._is_valid_image_url(cover_url):
                return cover_url
        
        # Method 4: Look for album/cover art specific classes
        cover_selectors = [
            'img.cover', 'img.album-cover', 'img.artwork', 'img.album-art',
            '.cover img', '.album-cover img', '.artwork img',
            '[class*="cover"] img', '[class*="artwork"] img',
            'img[alt*="cover"]', 'img[alt*="artwork"]',
            '.tracklist-cover img', '.release-cover img',
        ]
        for selector in cover_selectors:
            img = soup.select_one(selector)
            if img:
                cover_url = img.get('src', '')
                if cover_url and self._is_valid_image_url(cover_url):
                    return self._make_absolute_url(cover_url, url)
        
        # Method 5: First large image in main content
        main_content = soup.select_one('main, article, .content, #content, .main')
        if main_content:
            for img in main_content.select('img[src]'):
                src = img.get('src', '')
                # Skip small images, icons, avatars
                width = img.get('width', '')
                height = img.get('height', '')
                if width and int(width) < 100:
                    continue
                if height and int(height) < 100:
                    continue
                # Skip common non-cover patterns
                if any(skip in src.lower() for skip in ['icon', 'avatar', 'logo', 'banner', 'ad', 'button', 'sprite']):
                    continue
                if self._is_valid_image_url(src):
                    return self._make_absolute_url(src, url)
        
        return ""
    
    def _is_valid_image_url(self, url: str) -> bool:
        """Check if URL looks like a valid image"""
        if not url:
            return False
        url_lower = url.lower()
        # Check for image extensions or image CDN patterns
        image_patterns = ['.jpg', '.jpeg', '.png', '.webp', '.gif', 'image/', '/images/', 'artwork', 'cover']
        return any(p in url_lower for p in image_patterns) or url.startswith('data:image')
    
    def _make_absolute_url(self, url: str, base_url: str) -> str:
        """Convert relative URL to absolute"""
        if url.startswith('http://') or url.startswith('https://') or url.startswith('data:'):
            return url
        from urllib.parse import urljoin
        return urljoin(base_url, url)
        
        return result if result["tracks"] else None
    
    def _extract_tracks_from_text(self, text: str) -> List[Dict]:
        """Extract tracks from unstructured text using patterns"""
        tracks = []
        
        # Common tracklist patterns:
        # 1. "01. Artist - Title"
        # 2. "1) Artist - Title"
        # 3. "[00:00] Artist - Title"
        # 4. "Artist - Title [Label]"
        
        patterns = [
            # Numbered tracks: "01. Artist - Title" or "1. Artist - Title"
            r'^\s*(\d{1,3})[\.\)\]]\s*(.+?)\s*[-–—]\s*(.+?)(?:\s*[\[\(].+?[\]\)])?$',
            # Time-stamped: "[00:00] Artist - Title"
            r'^\s*\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*(.+?)\s*[-–—]\s*(.+?)$',
            # Simple: "Artist - Title"
            r'^\s*([A-Z][^-–—\n]{2,40})\s*[-–—]\s*([^-–—\n]{3,80})$',
        ]
        
        lines = text.split('\n')
        seen = set()
        position = 1
        
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            
            for pattern in patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    
                    # Determine artist and title based on pattern
                    if len(groups) == 3:
                        # First group might be number/time
                        if groups[0].isdigit() or ':' in groups[0]:
                            artist = groups[1].strip()
                            title = groups[2].strip()
                        else:
                            artist = groups[0].strip()
                            title = groups[1].strip()
                    elif len(groups) == 2:
                        artist = groups[0].strip()
                        title = groups[1].strip()
                    else:
                        continue
                    
                    # Validate and dedupe
                    key = f"{artist.lower()}|{title.lower()}"
                    if key in seen:
                        continue
                    if len(artist) < 2 or len(title) < 2:
                        continue
                    if len(artist) > 100 or len(title) > 150:
                        continue
                    
                    seen.add(key)
                    tracks.append({
                        "position": position,
                        "artist": artist,
                        "title": title
                    })
                    position += 1
                    break
        
        return tracks
    
    def _find_structured_tracklist(self, soup: BeautifulSoup) -> List[Dict]:
        """Find tracklist in structured HTML elements"""
        tracks = []
        
        # Try ordered lists
        for ol in soup.select('ol'):
            items = ol.select('li')
            if len(items) >= 3:  # Minimum 3 tracks
                for idx, li in enumerate(items, 1):
                    text = li.get_text(strip=True)
                    artist, title = self._parse_track_string(text)
                    if title:
                        tracks.append({
                            "position": idx,
                            "artist": artist,
                            "title": title
                        })
        
        if tracks:
            return tracks
        
        # Try tables
        for table in soup.select('table'):
            rows = table.select('tr')
            if len(rows) >= 3:
                for idx, row in enumerate(rows, 1):
                    cells = row.select('td')
                    if len(cells) >= 2:
                        # Assume first cell is artist, second is title
                        artist = cells[0].get_text(strip=True)
                        title = cells[1].get_text(strip=True)
                        if artist and title:
                            tracks.append({
                                "position": idx,
                                "artist": artist,
                                "title": title
                            })
        
        return tracks
    
    def _parse_track_string(self, text: str) -> tuple:
        """Parse a track string into artist and title"""
        # Remove numbering
        text = re.sub(r'^\s*\d+[\.\)\]]\s*', '', text)
        text = re.sub(r'^\s*\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*', '', text)
        
        # Split on common separators
        for sep in [' - ', ' – ', ' — ', ' / ']:
            if sep in text:
                parts = text.split(sep, 1)
                return parts[0].strip(), parts[1].strip()
        
        return "", text.strip()
    
    async def search_for_tracklist(
        self,
        artist: str = "",
        title: str = "",
        filename: str = "",
        max_results: int = 5
    ) -> List[Dict]:
        """
        Main entry point: Search for and extract tracklist information
        
        Returns list of potential tracklist matches with extracted track data
        """
        results = []
        
        # Build search queries - try multiple variations
        queries = []
        
        # Extract key terms from filename for better matching
        key_terms = ""
        if filename:
            # Get the distinctive part of the filename (often the set/mix name)
            clean_name = re.sub(r'\.(mp3|flac|wav|m4a)$', '', filename, flags=re.IGNORECASE)
            clean_name = re.sub(r'^\d+[-_\s]*', '', clean_name)  # Remove track numbers
            clean_name = re.sub(r'\s*\(\d{4}[-/]\d{2}[-/]\d{2}\)', '', clean_name)  # Remove dates in parens
            clean_name = re.sub(r'\s*Part\s*\d+\s*$', '', clean_name, flags=re.IGNORECASE)  # Remove Part X
            clean_name = clean_name.replace('_', ' ').replace(' - ', ' ')
            key_terms = clean_name.strip()
        
        # Query 1: Artist + title/filename with tracklist keyword
        if artist or title:
            query = self._build_search_query(artist, title or filename)
            queries.append(query)
        
        # Query 2: Key terms without quotes (catches name variations like "J. Scott G." -> "Jesse Scott Giaquinta")
        if key_terms:
            queries.append(f'{key_terms} tracklist')
        
        # Query 3: Site-specific search for 1001tracklists
        if artist:
            queries.append(f'site:1001tracklists.com "{artist}"')
        
        # Query 4: Site-specific search for MixesDB (great for older/obscure mixes)
        if key_terms:
            queries.append(f'site:mixesdb.com {key_terms}')
        
        # Query 5: If we have both artist and a distinctive title, try without artist
        if artist and title and len(title) > 10:
            clean_title = re.sub(r'\.(mp3|flac|wav|m4a)$', '', title, flags=re.IGNORECASE)
            queries.append(f'{clean_title} dj mix tracklist')
        
        # Execute searches
        seen_urls = set()
        for query in queries[:5]:  # Limit to 5 queries
            try:
                search_results = await self.search_google(query, num_results=5)
                
                for sr in search_results:
                    url = sr["url"]
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    
                    # Skip non-relevant domains
                    domain = sr["domain"]
                    if any(skip in domain for skip in ['youtube.com', 'spotify.com', 'soundcloud.com', 'apple.com', 'amazon.com']):
                        continue
                    
                    # Try to scrape tracklist from this URL
                    logger.info(f"Scraping tracklist from: {url}")
                    tracklist_data = await self.scrape_tracklist_from_url(url)
                    
                    if tracklist_data and tracklist_data.get("tracks"):
                        tracklist_data["search_title"] = sr["title"]
                        tracklist_data["search_snippet"] = sr["snippet"]
                        results.append(tracklist_data)
                        
                        if len(results) >= max_results:
                            break
                
                if len(results) >= max_results:
                    break
                    
                # Delay between queries
                await asyncio.sleep(2.0)
                
            except Exception as e:
                logger.error(f"Error in search query '{query}': {e}")
                continue
        
        return results
    
    async def close(self):
        """Clean up browser resources"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


# Module-level singleton
_search_instance: Optional[GoogleTracklistSearch] = None


async def get_google_search() -> GoogleTracklistSearch:
    """Get or create the global search instance"""
    global _search_instance
    if _search_instance is None:
        _search_instance = GoogleTracklistSearch()
    return _search_instance


async def search_tracklists_google(
    artist: str = "",
    title: str = "",
    filename: str = ""
) -> List[Dict]:
    """
    Convenience function to search for tracklists using Google
    
    Args:
        artist: Artist/DJ name
        title: Track/set title
        filename: Original filename
        
    Returns:
        List of tracklist results with extracted tracks
    """
    search = await get_google_search()
    return await search.search_for_tracklist(
        artist=artist,
        title=title,
        filename=filename
    )


class GoogleSearchService:
    """Service wrapper for cover art and general search functionality"""
    
    def __init__(self):
        self.search = GoogleTracklistSearch()
    
    async def search_cover_art(self, query: str, num_results: int = 20) -> List[Dict]:
        """
        Search for cover art images by scraping pages from web search results
        
        Args:
            query: Search query (artist + title)
            num_results: Maximum number of results to return
            
        Returns:
            List of dicts with: url, source, title
        """
        covers = []
        logger.info(f"Searching for cover art: {query}")
        
        # Use the existing DDG search which works better
        search_queries = [
            f"{query} album cover",
            f"{query} discogs",
            f"{query} artwork soundcloud"
        ]
        
        async with aiohttp.ClientSession() as session:
            for search_query in search_queries:
                try:
                    # Use DuckDuckGo HTML (the one that works in _search_duckduckgo_lite)
                    url = "https://lite.duckduckgo.com/lite/"
                    
                    logger.debug(f"Searching DDG for covers: {search_query}")
                    
                    async with session.post(
                        url,
                        data={"q": search_query, "kl": ""},
                        headers={
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                            "Accept": "text/html,application/xhtml+xml",
                        },
                        allow_redirects=True
                    ) as response:
                        # DDG Lite may return 202 on first request, then redirect
                        if response.status not in [200, 202]:
                            logger.warning(f"DDG returned status {response.status}")
                            continue
                        html = await response.text()
                    
                    soup = BeautifulSoup(html, "lxml")
                    
                    # Find result URLs - DDG Lite uses table-based layout
                    links = soup.select('a.result-link') or soup.select('td a[href^="http"]')
                    logger.debug(f"Found {len(links)} DDG links for covers")
                    
                    for link in links[:10]:
                        href = link.get('href', '')
                        if not href.startswith('http') or 'duckduckgo.com' in href:
                            continue
                        
                        logger.debug(f"Extracting covers from: {href}")
                        
                        # Fetch the page and extract cover image
                        try:
                            page_covers = await self._extract_covers_from_page(href, session)
                            logger.debug(f"Found {len(page_covers)} covers from {href}")
                            for cover in page_covers:
                                if cover['url'] not in [c['url'] for c in covers]:
                                    covers.append(cover)
                                    if len(covers) >= num_results:
                                        logger.info(f"Returning {len(covers)} cover options")
                                        return covers
                        except Exception as e:
                            logger.debug(f"Error extracting covers from {href}: {e}")
                            continue
                    
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Cover art search error: {e}")
                    continue
        
        logger.info(f"Returning {len(covers)} cover options")
        return covers
    
    async def _extract_covers_from_page(self, url: str, session: aiohttp.ClientSession) -> List[Dict]:
        """Extract cover art images from a page"""
        covers = []
        domain = urlparse(url).netloc.replace('www.', '')
        
        try:
            async with session.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                },
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    return covers
                html = await response.text()
            
            soup = BeautifulSoup(html, "lxml")
            
            # Extract OG image
            og_image = soup.select_one('meta[property="og:image"]')
            if og_image and og_image.get('content'):
                img_url = og_image['content']
                if img_url.startswith('http') and self._is_valid_image_url(img_url):
                    covers.append({
                        'url': img_url,
                        'source': domain,
                        'title': soup.title.string if soup.title else domain
                    })
            
            # Extract Twitter card image
            twitter_image = soup.select_one('meta[name="twitter:image"]')
            if twitter_image and twitter_image.get('content'):
                img_url = twitter_image['content']
                if img_url.startswith('http') and img_url not in [c['url'] for c in covers]:
                    if self._is_valid_image_url(img_url):
                        covers.append({
                            'url': img_url,
                            'source': domain,
                            'title': soup.title.string if soup.title else domain
                        })
            
            # Site-specific selectors
            image_selectors = [
                # Discogs
                'img[data-lightbox]',
                'img.cover',
                # SoundCloud
                'img.sc-artwork',
                'img[src*="artworks-"]',
                # Mixcloud
                'img.album-art',
                'img[src*="cloudcasts"]',
                # General
                '.cover-art img',
                '.album-cover img',
                'img[alt*="cover" i]',
                'img[alt*="artwork" i]',
            ]
            
            for selector in image_selectors:
                for img in soup.select(selector)[:3]:
                    src = img.get('src') or img.get('data-src')
                    if src and src not in [c['url'] for c in covers]:
                        # Make absolute URL
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            parsed = urlparse(url)
                            src = f"{parsed.scheme}://{parsed.netloc}{src}"
                        
                        if src.startswith('http') and self._is_valid_image_url(src):
                            covers.append({
                                'url': src,
                                'source': domain,
                                'title': img.get('alt', domain)
                            })
            
        except Exception as e:
            logger.debug(f"Error extracting covers from {url}: {e}")
        
        return covers[:5]  # Return max 5 per page
    
    def _is_valid_image_url(self, url: str) -> bool:
        """Check if URL is likely a valid cover image"""
        # Skip small images, icons, etc.
        skip_patterns = [
            'icon', 'logo', 'avatar', 'profile', 'badge',
            '1x1', 'placeholder', 'default', 'blank',
            '.gif', '.svg', 'sprite'
        ]
        url_lower = url.lower()
        return not any(pattern in url_lower for pattern in skip_patterns)
