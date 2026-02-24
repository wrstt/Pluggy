"""
1337x Search Source
Automated ad-free scraping with direct magnet extraction
"""
from typing import List
from ..models.search_result import SearchResult
from .base import BaseSource
import requests
from bs4 import BeautifulSoup
import re
import time


class X1337Source(BaseSource):
    """1337x torrent search source - bypasses all ads"""
    
    name = "1337x"
    
    # Mirror URLs in priority order
    MIRRORS = [
        "https://1337x.to",
        "https://www.1337x.to",
        "https://1337x.st",
        "https://x1337x.ws",
        "https://x1337x.eu",
        "https://1337xx.to",
        "https://www.1337xx.to",
        "https://1377x.to",
        "https://www.1377x.to",
    ]
    
    def __init__(self, settings=None):
        self.settings = settings
        self.mirrors = list(self.MIRRORS)
        self.base_url = self.mirrors[0]
        self.last_error = ""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        self._detail_timeout_seconds = 6.0
        self._detail_budget_seconds = 20.0
        self._max_detail_fetches = 10
        self.reload_from_settings()

    def reload_from_settings(self):
        custom_mirrors = []
        if self.settings is not None:
            custom_mirrors = list(self.settings.get("x1337_mirror_order", []) or [])
        if custom_mirrors:
            deduped = []
            for m in custom_mirrors + self.MIRRORS:
                if m and m not in deduped:
                    deduped.append(m.rstrip("/"))
            self.mirrors = deduped
        else:
            self.mirrors = list(self.MIRRORS)
        if self.base_url not in self.mirrors:
            self.base_url = self.mirrors[0]
        if self.settings is not None:
            self._detail_timeout_seconds = float(self.settings.get("x1337_detail_timeout_seconds", 6.0) or 6.0)
            self._detail_budget_seconds = float(self.settings.get("x1337_detail_budget_seconds", 20.0) or 20.0)
            self._max_detail_fetches = int(self.settings.get("x1337_max_detail_fetches", 10) or 10)
    
    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        """
        Search 1337x for torrents
        
        Mimics the manual process but automated:
        1. HTTP request to search page (no browser = no ads)
        2. Parse HTML to find torrent listings
        3. Extract magnet links directly from detail pages
        4. No popups, no JavaScript, pure data extraction
        """
        self.last_error = ""
        encoded_query = requests.utils.quote(query)
        mirror_order = [self.base_url] + [m for m in self.mirrors if m != self.base_url]
        errors = []

        for mirror in mirror_order:
            try:
                results = self._search_on_mirror(mirror, encoded_query, page)
                if results:
                    self.base_url = mirror
                    return results
            except Exception as e:
                errors.append(str(e))
                print(f"1337x search error ({mirror}): {e}")
                continue

        if errors:
            if all("Cloudflare challenge" in e for e in errors):
                self.last_error = "Blocked by Cloudflare challenge on all 1337x mirrors."
            else:
                self.last_error = f"All 1337x mirrors failed: {errors[-1]}"

        return []

    def _search_on_mirror(self, mirror: str, encoded_query: str, page: int) -> List[SearchResult]:
        """Try a single mirror and parse search rows."""
        search_url = f"{mirror}/search/{encoded_query}/{page}/"
        response = self.session.get(search_url, timeout=15)

        # Most 1337x mirrors are fronted by Cloudflare and can return challenge pages.
        if response.status_code == 403 and "Just a moment" in response.text:
            raise Exception("Cloudflare challenge (403)")

        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        torrent_rows = soup.select('.table-list tbody tr')
        candidates = []
        for row in torrent_rows:
            candidate = self._parse_listing_row(row, mirror)
            if candidate:
                candidates.append(candidate)

        results: List[SearchResult] = []
        deadline = time.monotonic() + max(5.0, self._detail_budget_seconds)
        max_fetches = max(1, self._max_detail_fetches)

        for candidate in candidates[:max_fetches]:
            if time.monotonic() >= deadline:
                self.last_error = "1337x detail-page lookup timed out; partial results shown."
                break
            try:
                result = self._build_result_from_candidate(candidate, deadline)
                if result:
                    results.append(result)
            except Exception:
                continue

        return results
    
    def _parse_listing_row(self, row, mirror_base: str):
        """Parse metadata from one search-row and return a detail-page candidate."""
        # Get torrent detail link
        name_elem = row.select_one('.name a:nth-of-type(2)')
        if not name_elem:
            return None
        
        title = name_elem.get_text(strip=True)
        detail_path = name_elem.get('href', '')
        if not detail_path:
            return None
        
        if detail_path.startswith("http://") or detail_path.startswith("https://"):
            detail_url = detail_path
        else:
            detail_url = mirror_base.rstrip("/") + detail_path
        
        # Extract metadata from search page
        seeds_elem = row.select_one('.seeds')
        leeches_elem = row.select_one('.leeches')
        size_elem = row.select_one('.size')
        
        seeds = 0
        leeches = 0
        if seeds_elem:
            try:
                seeds = int(seeds_elem.get_text(strip=True))
            except:
                seeds = 0
        
        if leeches_elem:
            try:
                leeches = int(leeches_elem.get_text(strip=True))
            except:
                leeches = 0
        
        size_bytes = 0
        if size_elem:
            size_text = size_elem.get_text(strip=True)
            size_bytes = SearchResult.normalize_size(size_text)
        
        return {
            "title": title,
            "detail_url": detail_url,
            "size_bytes": size_bytes,
            "seeds": seeds,
            "leeches": leeches,
        }

    def _build_result_from_candidate(self, candidate: dict, deadline: float):
        remaining = max(0.5, deadline - time.monotonic())
        timeout = min(max(1.0, self._detail_timeout_seconds), remaining)
        magnet = self._get_magnet_link(candidate["detail_url"], timeout=timeout)
        if not magnet:
            return None

        infohash = SearchResult.extract_infohash(magnet)
        if not infohash:
            return None

        return SearchResult(
            title=candidate["title"],
            magnet=magnet,
            size=candidate["size_bytes"],
            seeds=candidate["seeds"],
            leeches=candidate["leeches"],
            source=self.name,
            infohash=infohash
        )
    
    def _get_magnet_link(self, detail_url: str, timeout: float = 10.0) -> str:
        """
        Get magnet link from detail page
        
        This simulates clicking on a torrent and finding the magnet link,
        but without any browser, popups, or ads
        """
        try:
            # Direct HTTP request - no ads, no popups
            response = self.session.get(detail_url, timeout=timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find magnet link
            magnet_elem = soup.select_one('a[href^="magnet:"]')
            
            if magnet_elem:
                return magnet_elem['href']
            
            # Fallback: sometimes magnet is in a different format
            # Look for any link containing magnet:
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link['href']
                if href.startswith('magnet:'):
                    return href
        
        except Exception as e:
            # Fail silently for individual torrents
            pass
        
        return ""
