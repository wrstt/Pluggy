"""
PirateBay Search Source
Automated ad-free scraping with mirror support
"""
from typing import List
from ..models.search_result import SearchResult
from .base import BaseSource
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote


class PirateBaySource(BaseSource):
    """PirateBay torrent search source - bypasses all ads"""
    
    name = "PirateBay"
    
    # Working mirrors/proxies in priority order
    MIRRORS = [
        "https://www.piratebay.org",
        "https://tpb.party",
        "https://thepiratebay.zone",
        "https://pirateproxylive.org",
        "https://thepiratebay.org",
    ]
    API_ENDPOINTS = [
        "https://apibay.org",
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
        })
        self.api_endpoints = list(self.API_ENDPOINTS)
        self.reload_from_settings()

    def reload_from_settings(self):
        custom_mirrors = []
        custom_api = []
        if self.settings is not None:
            custom_mirrors = list(self.settings.get("piratebay_mirror_order", []) or [])
            custom_api = list(self.settings.get("piratebay_api_endpoints", []) or [])
        if custom_mirrors:
            deduped = []
            for m in custom_mirrors + self.MIRRORS:
                if m and m not in deduped:
                    deduped.append(m.rstrip("/"))
            self.mirrors = deduped
        else:
            self.mirrors = list(self.MIRRORS)
        if custom_api:
            deduped_api = []
            for a in custom_api + self.API_ENDPOINTS:
                if a and a not in deduped_api:
                    deduped_api.append(a.rstrip("/"))
            self.api_endpoints = deduped_api
        else:
            self.api_endpoints = list(self.API_ENDPOINTS)
        if self.base_url not in self.mirrors:
            self.base_url = self.mirrors[0]
    
    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        """
        Search PirateBay for torrents
        
        Automated process (no ads):
        1. Direct HTTP request to search page
        2. Parse HTML table structure
        3. Extract magnet links directly (they're in the search results!)
        4. No need to visit detail pages - magnets are already there
        """
        self.last_error = ""

        # 1) Prefer the API path for reliability (works even when HTML mirrors drift).
        api_results = self._search_via_api(query)
        if api_results:
            return api_results

        # PirateBay uses 0-indexed pages
        page_num = max(0, page - 1)
        encoded_query = quote(query)

        # 2) Fallback to HTML mirror scraping.
        mirror_order = [self.base_url] + [m for m in self.mirrors if m != self.base_url]

        last_exception = None
        for mirror in mirror_order:
            search_url = f"{mirror}/search/{encoded_query}/{page_num}/99/0"
            try:
                response = self.session.get(search_url, timeout=15)
                response.raise_for_status()
                if self._looks_like_parked_or_blocked_page(response.text):
                    last_exception = Exception("Mirror returned parked/block page.")
                    continue

                soup = BeautifulSoup(response.content, 'html.parser')
                results = self._parse_search_page(soup)

                # Treat non-empty parse as healthy mirror and persist it.
                if results:
                    self.base_url = mirror
                    return results

            except Exception as e:
                last_exception = e
                print(f"PirateBay search error ({mirror}): {e}")
                continue

        if last_exception is not None:
            self.last_error = f"All PirateBay mirrors failed: {last_exception}"

        return []

    def _search_via_api(self, query: str) -> List[SearchResult]:
        encoded_query = quote(query)
        errors = []
        for base in self.api_endpoints:
            url = f"{base}/q.php?q={encoded_query}"
            try:
                response = self.session.get(url, timeout=12, headers={
                    "User-Agent": self.session.headers.get("User-Agent", "Mozilla/5.0"),
                    "Accept": "application/json,text/plain,*/*",
                })
                response.raise_for_status()
                rows = response.json()
                if not isinstance(rows, list):
                    continue
                results = self._parse_api_rows(rows)
                if results:
                    return results
            except Exception as e:
                errors.append(str(e))
                continue

        if errors:
            self.last_error = f"PirateBay API failed: {errors[-1]}"
        return []

    def _parse_api_rows(self, rows: List[dict]) -> List[SearchResult]:
        results: List[SearchResult] = []
        for row in rows:
            try:
                name = (row.get("name") or "").strip()
                infohash = (row.get("info_hash") or "").strip().upper()
                if not name or not infohash or len(infohash) != 40:
                    continue
                if infohash == "0000000000000000000000000000000000000000":
                    continue

                size = int(row.get("size") or 0)
                seeds = int(row.get("seeders") or 0)
                leeches = int(row.get("leechers") or 0)
                magnet = self._build_magnet(infohash, name)
                results.append(SearchResult(
                    title=name,
                    magnet=magnet,
                    size=max(0, size),
                    seeds=max(0, seeds),
                    leeches=max(0, leeches),
                    source=self.name,
                    infohash=infohash,
                ))
            except Exception:
                continue
        return results

    def _build_magnet(self, infohash: str, title: str) -> str:
        trackers = [
            "udp://tracker.opentrackr.org:1337/announce",
            "udp://open.stealth.si:80/announce",
            "udp://tracker.torrent.eu.org:451/announce",
            "udp://exodus.desync.com:6969/announce",
        ]
        tr = "".join([f"&tr={quote(t, safe='')}" for t in trackers])
        return f"magnet:?xt=urn:btih:{infohash}&dn={quote(title, safe='')}{tr}"

    def _looks_like_parked_or_blocked_page(self, html: str) -> bool:
        low = (html or "").lower()
        blocked_signals = [
            "fastpanel",
            "view more possible reasons",
            "cloudflare",
            "captcha",
            "just a moment",
            "ddos protection",
        ]
        return any(sig in low for sig in blocked_signals)

    def _parse_search_page(self, soup: BeautifulSoup) -> List[SearchResult]:
        """Parse the page into results across old/new TPB layouts."""
        results: List[SearchResult] = []

        # Older mirrors include <tbody>; newer mirrors often don't.
        torrent_rows = soup.select("#searchResult tr")

        for row in torrent_rows:
            try:
                result = self._parse_row(row)
                if result:
                    results.append(result)
            except Exception:
                continue

        return results
    
    def _parse_row(self, row) -> SearchResult:
        """Parse a single torrent row"""
        # Skip header/invalid rows
        if not row.find_all("td"):
            return None

        # Extract title (legacy and current layouts)
        title_elem = row.select_one('.detName a') or row.select_one('td:nth-of-type(2) a[href*="/torrent/"]')
        if not title_elem:
            return None
        
        title = title_elem.get_text(strip=True)
        
        # Extract magnet link - it's directly in the row!
        magnet_elem = row.select_one('a[href^="magnet:"]')
        if not magnet_elem:
            return None
        
        magnet = magnet_elem['href']
        infohash = SearchResult.extract_infohash(magnet)
        if not infohash:
            return None
        
        # Extract seeds/leeches (layout-dependent column positions)
        def _parse_int_from_selectors(selectors):
            for selector in selectors:
                elem = row.select_one(selector)
                if not elem:
                    continue
                text = elem.get_text(strip=True).replace(",", "")
                if text.isdigit():
                    return int(text)
            return 0

        seeds = _parse_int_from_selectors([
            'td:nth-of-type(6)',  # current TPB mirror layout
            'td:nth-of-type(3)',  # legacy TPB layout
        ])
        leeches = _parse_int_from_selectors([
            'td:nth-of-type(7)',  # current TPB mirror layout
            'td:nth-of-type(4)',  # legacy TPB layout
        ])
        
        # Extract size from description or explicit size column
        desc_elem = row.select_one('.detDesc')
        size_bytes = 0
        if desc_elem:
            desc_text = desc_elem.get_text()
            # Format: "Uploaded ..., Size 1.5 GiB, ..."
            if 'Size' in desc_text:
                try:
                    size_part = desc_text.split('Size')[1].split(',')[0].strip()
                    size_bytes = SearchResult.normalize_size(size_part)
                except:
                    size_bytes = 0
        else:
            size_elem = row.select_one('td:nth-of-type(5)')
            if size_elem:
                size_bytes = SearchResult.normalize_size(size_elem.get_text(strip=True))

        return SearchResult(
            title=title,
            magnet=magnet,
            size=size_bytes,
            seeds=seeds,
            leeches=leeches,
            source=self.name,
            infohash=infohash
        )
