"""
RealDebrid Library Source
Searches user's own RealDebrid torrent library.
"""
from typing import List

from ..models.search_result import SearchResult
from .base import BaseSource


class RealDebridLibrarySource(BaseSource):
    name = "RealDebrid Library"

    def __init__(self, rd_client, settings):
        self.rd_client = rd_client
        self.settings = settings
        self.last_error = ""

    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        self.last_error = ""
        if not self.settings.get("rd_library_source_enabled", False):
            return []
        if not self.rd_client.is_authenticated():
            self.last_error = "RealDebrid Library source is enabled but account is not authenticated."
            return []

        try:
            items = self.rd_client.list_torrents(page=page, limit=100)
        except Exception as e:
            self.last_error = f"RealDebrid Library error: {e}"
            return []

        q = (query or "").strip().lower()
        out: List[SearchResult] = []
        for item in items:
            name = str(item.get("filename", "") or item.get("original_filename", "")).strip()
            if not name:
                continue
            if q and q not in name.lower():
                continue

            torrent_id = str(item.get("id", "")).strip()
            links = item.get("links") or []
            direct_link = links[0] if isinstance(links, list) and links else ""
            size = int(item.get("bytes", 0) or 0)
            status = str(item.get("status", "") or "").strip()
            title = f"{name} [{status}]" if status else name

            out.append(SearchResult(
                title=title,
                magnet=direct_link,
                size=size,
                seeds=0,
                leeches=0,
                source=self.name,
                infohash="",
            ))
        return out
