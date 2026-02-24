"""
VST Torrents Source
Specialized scraper for audio software torrents
Example of site-specific pagination and category handling
"""
from typing import List
from ..models.search_result import SearchResult
import requests
from bs4 import BeautifulSoup
import re


class VSTTorrentsSource:
    """
    VST Torrents specialized source
    
    This demonstrates how to handle:
    - Multi-page pagination
    - Category-specific searches
    - Site-specific HTML structures
    - Download link extraction patterns
    """
    
    name = "VSTTorrents"
    
    BASE_URL = "https://vsttorrent.com"  # Example - replace with actual if different
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
        })
    
    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        """
        Search VST torrents
        
        VST sites often have:
        - Category filters (VST, AU, AAX, samples)
        - Version numbers in titles
        - Multiple download links per page
        - Pagination via page parameter
        """
        results = []
        
        try:
            # Build search URL with pagination
            # Format varies by site - this is a common pattern
            search_url = f"{self.BASE_URL}/search"
            
            params = {
                'q': query,
                'page': page,
                # Common VST categories
                'cat': 'all'  # or specific: vst, au, aax, samples
            }
            
            response = self.session.get(search_url, params=params, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # VST sites often use article/post structures
            # Adapt these selectors to actual site structure
            posts = soup.select('.post, .entry, .torrent-item, article')
            
            for post in posts:
                try:
                    result = self._parse_post(post)
                    if result:
                        results.append(result)
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"VSTTorrents search error: {e}")
        
        return results
    
    def _parse_post(self, post) -> SearchResult:
        """
        Parse a VST torrent post
        
        VST torrents typically have:
        - Plugin name + version in title
        - Format info (VST, VST3, AU, AAX)
        - Operating system (Mac/Win)
        - Magnet or download links in post body
        """
        # Extract title
        # Common selectors for titles
        title_elem = (
            post.select_one('.title a') or
            post.select_one('h2 a') or
            post.select_one('.entry-title a') or
            post.select_one('h3 a')
        )
        
        if not title_elem:
            return None
        
        title = title_elem.get_text(strip=True)
        
        # Look for magnet link
        # VST sites may have magnets in post content
        magnet_elem = post.select_one('a[href^="magnet:"]')
        
        if not magnet_elem:
            # Sometimes need to visit detail page
            detail_url = title_elem.get('href', '')
            if detail_url and not detail_url.startswith('http'):
                detail_url = self.BASE_URL + detail_url
            
            if detail_url:
                magnet = self._get_magnet_from_page(detail_url)
            else:
                return None
        else:
            magnet = magnet_elem['href']
        
        if not magnet:
            return None
        
        infohash = SearchResult.extract_infohash(magnet)
        if not infohash:
            return None
        
        # Extract metadata
        seeds, leeches, size_bytes = self._extract_metadata(post, title)
        
        return SearchResult(
            title=title,
            magnet=magnet,
            size=size_bytes,
            seeds=seeds,
            leeches=leeches,
            source=self.name,
            infohash=infohash
        )
    
    def _get_magnet_from_page(self, url: str) -> str:
        """Fetch magnet from detail page"""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for magnet link
            magnet_elem = soup.select_one('a[href^="magnet:"]')
            if magnet_elem:
                return magnet_elem['href']
            
            # Fallback: look in download buttons or links
            download_links = soup.select('a[href*="download"], .download-btn, a[class*="magnet"]')
            for link in download_links:
                href = link.get('href', '')
                if href.startswith('magnet:'):
                    return href
        
        except Exception as e:
            pass
        
        return ""
    
    def _extract_metadata(self, post, title: str) -> tuple:
        """
        Extract seeds, leeches, and size
        
        VST torrents often don't show seed/leech counts prominently
        We can infer quality from:
        - Release date (newer = potentially more seeds)
        - Comments/downloads count
        - File size (reasonable for VST plugins)
        """
        seeds = 0
        leeches = 0
        size_bytes = 0
        
        # Get post text content
        content = post.get_text()
        
        # Look for size information
        # Common patterns: "Size: 1.2 GB", "1.2GB", etc.
        size_match = re.search(r'(?:size|filesize)[:\s]*([\d.]+)\s*([KMGT]i?B)', content, re.IGNORECASE)
        if size_match:
            size_str = f"{size_match.group(1)} {size_match.group(2)}"
            size_bytes = SearchResult.normalize_size(size_str)
        else:
            # Fallback: look for any size mention
            size_match = re.search(r'([\d.]+)\s*([KMGT]i?B)', content)
            if size_match:
                size_str = f"{size_match.group(1)} {size_match.group(2)}"
                size_bytes = SearchResult.normalize_size(size_str)
        
        # VST sites rarely show seeds/leeches
        # Can estimate based on age or comments
        comments_elem = post.select_one('.comments-count, .comment-count')
        if comments_elem:
            try:
                comments = int(re.search(r'\d+', comments_elem.get_text()).group())
                # Estimate: popular posts likely have more seeds
                seeds = min(100, comments * 5)
            except:
                seeds = 1
        else:
            # Default: assume at least 1 seed if torrent is listed
            seeds = 1
        
        leeches = max(0, seeds // 3)  # Rough estimate
        
        return (seeds, leeches, size_bytes)
    
    def search_by_category(self, query: str, category: str, page: int = 1) -> List[SearchResult]:
        """
        Search with category filter
        
        Categories:
        - 'vst': VST plugins
        - 'samples': Sample libraries
        - 'daw': Digital Audio Workstations
        - 'all': All categories
        """
        # This would modify the search params
        # Implementation depends on site structure
        return self.search(query, page)
