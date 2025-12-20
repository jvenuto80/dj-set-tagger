"""
1001Tracklists API integration - scraping and searching
Uses Playwright for JavaScript-heavy pages (bypasses Cloudflare Turnstile)
Based on https://github.com/jvenuto80/1001-tracklists-api
"""
import re
import asyncio
import random
from typing import List, Dict, Optional, Any
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
from backend.config import settings
from loguru import logger


class CaptchaException(Exception):
    """Raised when a captcha is detected"""
    pass


class TracklistsAPI:
    """Async wrapper for 1001Tracklists.com scraping using Playwright"""
    
    BASE_URL = "https://www.1001tracklists.com"
    SEARCH_URL = "https://www.1001tracklists.com/search/result.php"
    
    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self.delay = settings.tracklists_delay
        self.max_retries = 3
        self.captcha_detected = False
    
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
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu'
                ]
            )
        return self._browser
    
    def _detect_captcha(self, text: str) -> bool:
        """Detect various forms of captcha/blocking"""
        captcha_indicators = [
            "turnstile-container" in text.lower(),
            "please verify you are human" in text.lower(),
            "access denied" in text.lower(),
            "please wait, you will be forwarded" in text.lower(),
        ]
        return any(captcha_indicators)
    
    async def _get_soup(self, url: str, wait_for_content: bool = True) -> BeautifulSoup:
        """Fetch URL using Playwright and return BeautifulSoup object"""
        browser = await self._get_browser()
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        try:
            # Add random delay to seem more human
            delay = self.delay + random.uniform(0.5, 2.0)
            await asyncio.sleep(delay)
            
            logger.debug(f"Navigating to {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Wait for any Cloudflare challenge to resolve
            # Turnstile usually completes within 5-10 seconds
            try:
                await page.wait_for_selector("body", timeout=5000)
                # Wait a bit more for dynamic content
                if wait_for_content:
                    await asyncio.sleep(3)
            except Exception:
                pass
            
            # Get page content
            text = await page.content()
            
            # Check for captcha that didn't resolve
            if self._detect_captcha(text) and "turnstile" in text.lower():
                # Wait longer for turnstile to complete
                logger.info("Waiting for Turnstile captcha to resolve...")
                await asyncio.sleep(10)
                text = await page.content()
                
                if self._detect_captcha(text):
                    self.captcha_detected = True
                    logger.warning(f"Captcha could not be resolved on {url}")
                    raise CaptchaException("Turnstile captcha could not be automatically resolved")
            
            self.captcha_detected = False
            soup = BeautifulSoup(text, "lxml")
            
            # Log page title for debugging
            if soup.title:
                logger.debug(f"Page title: {soup.title.text}")
            
            return soup
            
        except CaptchaException:
            raise
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            raise
        finally:
            await page.close()
    
    async def search(self, query: str, search_type: str = "all") -> List[Dict]:
        """
        Search 1001tracklists.com
        
        Args:
            query: Search query
            search_type: Type of search - "all", "tracklists", "tracks", "djs"
        
        Returns:
            List of search results
        """
        encoded_query = quote_plus(query)
        
        # 1001tracklists uses different endpoints for different searches
        search_urls = {
            "tracklists": f"{self.BASE_URL}/search/tracklist.php?q={encoded_query}",
            "tracks": f"{self.BASE_URL}/search/track.php?q={encoded_query}",
            "djs": f"{self.BASE_URL}/search/dj.php?q={encoded_query}",
            "all": f"{self.BASE_URL}/search/result.php?q={encoded_query}"
        }
        
        url = search_urls.get(search_type, search_urls["all"])
        logger.info(f"Searching 1001tracklists: {url}")
        
        await asyncio.sleep(self.delay)  # Rate limiting
        
        try:
            soup = await self._get_soup(url)
            results = []
            
            # Log page title for debugging
            if soup.title:
                logger.debug(f"Page title: {soup.title.text}")
            
            # Parse search results based on type
            if search_type == "tracklists" or search_type == "all":
                tracklist_results = self._parse_tracklist_search_results(soup)
                logger.info(f"Found {len(tracklist_results)} tracklist results")
                results.extend(tracklist_results)
            
            if search_type == "tracks" or search_type == "all":
                track_results = self._parse_track_search_results(soup)
                logger.info(f"Found {len(track_results)} track results")
                results.extend(track_results)
            
            # If no results from main parsing, try alternative parsing methods
            if not results:
                logger.info("No results from standard parsing, trying alternative methods...")
                alt_results = self._parse_any_tracklist_links(soup)
                logger.info(f"Found {len(alt_results)} results from alternative parsing")
                results.extend(alt_results)
            
            return results
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def _parse_any_tracklist_links(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse any tracklist links from the page as fallback"""
        results = []
        seen_urls = set()
        
        # Look for any links containing /tracklist/
        for link in soup.find_all("a", href=re.compile(r"/tracklist/")):
            try:
                href = link.get("href", "")
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                
                title = link.text.strip()
                if not title or len(title) < 3:
                    continue
                
                url = href if href.startswith("http") else self.BASE_URL + href
                
                results.append({
                    "type": "tracklist",
                    "title": title,
                    "url": url,
                    "dj": None
                })
            except Exception as e:
                logger.debug(f"Error parsing link: {e}")
        
        return results
    
    def _parse_tracklist_search_results(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse tracklist search results from page"""
        results = []
        
        # Find tracklist links
        for item in soup.find_all("div", class_="tlLink"):
            try:
                link = item.find("a")
                if not link:
                    continue
                
                title = link.text.strip()
                url = link.get("href", "")
                if not url.startswith("http"):
                    url = self.BASE_URL + url
                
                # Try to extract DJ name
                dj = None
                dj_elem = item.find("span", class_="artistName")
                if dj_elem:
                    dj = dj_elem.text.strip()
                
                results.append({
                    "type": "tracklist",
                    "title": title,
                    "url": url,
                    "dj": dj
                })
                
            except Exception as e:
                logger.debug(f"Error parsing tracklist result: {e}")
        
        return results
    
    def _parse_track_search_results(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse track search results from page"""
        results = []
        
        # Find track items
        for item in soup.find_all("div", class_="tlpItem"):
            try:
                track_info = self._parse_track_div(item)
                if track_info:
                    track_info["type"] = "track"
                    results.append(track_info)
            except Exception as e:
                logger.debug(f"Error parsing track result: {e}")
        
        return results
    
    def _parse_track_div(self, div: BeautifulSoup) -> Optional[Dict]:
        """Parse individual track div"""
        try:
            track_value = div.find("span", class_="trackValue")
            if not track_value:
                return None
            
            full_title = track_value.text.strip().replace('\xa0', ' ')
            
            # Split into artist and title
            if " - " in full_title:
                artist, title = full_title.split(" - ", 1)
            else:
                artist = None
                title = full_title
            
            # Get metadata
            meta_data = {}
            for meta in div.find_all("meta"):
                itemprop = meta.get("itemprop")
                content = meta.get("content")
                if itemprop and content:
                    meta_data[itemprop] = content
            
            genre = meta_data.get("genre")
            url = meta_data.get("url")
            
            # Get label
            labels = []
            for label_span in div.find_all("span", title="label"):
                labels.append(label_span.text.strip())
            
            return {
                "full_title": full_title,
                "title": title,
                "artist": artist,
                "genre": genre,
                "url": url,
                "labels": labels
            }
            
        except Exception as e:
            logger.debug(f"Error parsing track div: {e}")
            return None
    
    async def get_tracklist(self, url: str) -> Optional[Dict]:
        """
        Fetch detailed tracklist information
        
        Args:
            url: URL of the tracklist page
            
        Returns:
            Dictionary with tracklist details
        """
        await asyncio.sleep(self.delay)  # Rate limiting
        
        try:
            soup = await self._get_soup(url)
            
            # Get title
            title = soup.title.text if soup.title else ""
            
            # Get tracklist ID from URL
            tracklist_id = url.split("tracklist/")[1].split("/")[0] if "tracklist/" in url else None
            
            # Get left pane metadata
            left_pane = soup.find("div", id="left")
            metadata = self._parse_tracklist_metadata(left_pane) if left_pane else {}
            
            # Get tracks
            tracks = []
            track_divs = soup.find_all("div", class_="tlpItem")
            for track_div in track_divs:
                track_info = self._parse_track_div(track_div)
                if track_info:
                    tracks.append(track_info)
            
            # Get cue times
            cues = [div.text.strip() for div in soup.find_all("div", class_="cueValueField")]
            
            # Get cover image
            cover_url = None
            og_image = soup.find("meta", property="og:image")
            if og_image:
                cover_url = og_image.get("content")
            
            return {
                "tracklist_id": tracklist_id,
                "url": url,
                "title": title,
                "tracks": tracks,
                "cues": cues,
                "cover_url": cover_url,
                **metadata
            }
            
        except Exception as e:
            logger.error(f"Error fetching tracklist {url}: {e}")
            return None
    
    def _parse_tracklist_metadata(self, left_pane: BeautifulSoup) -> Dict:
        """Parse metadata from tracklist left pane"""
        metadata = {
            "djs": [],
            "genres": [],
            "date_recorded": None,
            "sources": {},
            "num_tracks": 0
        }
        
        try:
            # Get date recorded
            date_span = left_pane.find("span", title="tracklist recording date")
            if date_span:
                date_td = date_span.parent.parent.find_all("td")
                if len(date_td) > 1:
                    metadata["date_recorded"] = date_td[1].text.strip()
            
            # Get genres
            genre_td = left_pane.find("td", id="tl_music_styles")
            if genre_td:
                metadata["genres"] = [g.strip() for g in genre_td.text.split(",")]
            
            # Get DJs and sources
            for table in left_pane.find_all("table", class_="sideTop"):
                link = table.find("a")
                if link:
                    href = link.get("href", "")
                    name = link.text.strip()
                    
                    if "/dj/" in href:
                        metadata["djs"].append(name)
                    elif "/source/" in href:
                        # Find source type
                        td = link.parent.parent.parent.find("td")
                        if td:
                            source_type = td.contents[0] if td.contents else "source"
                            metadata["sources"][str(source_type).strip()] = name
            
            # Get track count
            text = left_pane.text
            if "IDed" in text:
                try:
                    total = text.split("IDed")[1].split("short")[0].strip().split("/")[1].split()[0]
                    metadata["num_tracks"] = int(total)
                except:
                    pass
                    
        except Exception as e:
            logger.debug(f"Error parsing tracklist metadata: {e}")
        
        return metadata
    
    async def search_dj(self, dj_name: str) -> List[Dict]:
        """Search for a specific DJ's tracklists"""
        encoded_name = quote_plus(dj_name)
        url = f"{self.BASE_URL}/dj/{encoded_name}/index.html"
        
        await asyncio.sleep(self.delay)
        
        try:
            soup = await self._get_soup(url)
            
            # Try to find DJ page redirect
            results = []
            
            # Look for tracklist links on DJ page
            for link in soup.find_all("a", href=re.compile(r"/tracklist/")):
                title = link.text.strip()
                href = link.get("href", "")
                if href and not href.startswith("http"):
                    href = self.BASE_URL + href
                
                if title:
                    results.append({
                        "type": "tracklist",
                        "title": title,
                        "url": href,
                        "dj": dj_name
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching for DJ {dj_name}: {e}")
            return []
    
    async def close(self):
        """Close the Playwright browser and stop playwright"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
    
    async def search_source(self, source_name: str) -> List[Dict]:
        """
        Search for tracklists by source/show name
        Tries to find the source page directly
        """
        # Normalize source name for URL
        normalized = source_name.lower()
        normalized = re.sub(r'[^\w\s-]', '', normalized)
        normalized = re.sub(r'\s+', '-', normalized)
        
        url = f"{self.BASE_URL}/source/{normalized}/index.html"
        logger.info(f"Trying source URL: {url}")
        
        await asyncio.sleep(self.delay)
        
        try:
            soup = await self._get_soup(url)
            return self._parse_any_tracklist_links(soup)
        except Exception as e:
            logger.error(f"Error searching source {source_name}: {e}")
            return []
    
    async def search_combined(self, query: str) -> List[Dict]:
        """
        Combined search strategy - tries multiple methods
        """
        all_results = []
        seen_urls = set()
        
        # 1. Try standard search
        logger.info(f"Trying standard search for: {query}")
        results = await self.search(query, "tracklists")
        for r in results:
            if r.get("url") not in seen_urls:
                seen_urls.add(r.get("url"))
                all_results.append(r)
        
        # 2. If query looks like a show name with episode number, try source search
        show_match = re.match(r'(.+?)[\s_-]*(\d{2,4})[\s_-]*$', query)
        if show_match and not all_results:
            show_name = show_match.group(1).strip()
            episode = show_match.group(2)
            logger.info(f"Trying source search for show: {show_name}")
            source_results = await self.search_source(show_name)
            for r in source_results:
                if r.get("url") not in seen_urls:
                    # Check if episode number is in title
                    if episode in r.get("title", ""):
                        seen_urls.add(r.get("url"))
                        all_results.append(r)
        
        return all_results


# Global API instance
_api: Optional[TracklistsAPI] = None


def get_tracklists_api() -> TracklistsAPI:
    """Get or create TracklistsAPI instance"""
    global _api
    if _api is None:
        _api = TracklistsAPI()
    return _api


async def search_1001tracklists(query: str) -> List[Dict]:
    """Convenience function to search 1001tracklists"""
    api = get_tracklists_api()
    # Use combined search for better results
    return await api.search_combined(query)


async def get_tracklist_details(url: str) -> Optional[Dict]:
    """Convenience function to get tracklist details"""
    api = get_tracklists_api()
    return await api.get_tracklist(url)
