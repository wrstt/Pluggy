"""
Prowlarr Search Source

Integrates with a locally hosted Prowlarr instance (Indexer Manager).

Notes:
- Requires user-provided base URL + API key (or initialize.json auto-discovery when allowed).
- This does not attempt to bypass anti-bot protections on any upstream indexers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from .base import BaseSource
from ..models.search_result import SearchResult


class ProwlarrSource(BaseSource):
    name = "Prowlarr"

    def __init__(self, settings):
        self.settings = settings
        self.last_error = ""
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Pluggy; ProwlarrSource)",
                "Accept": "application/json,text/plain,*/*",
            }
        )
        self._base_url = "http://127.0.0.1:9696"
        self._api_key = ""
        self._timeout_seconds = 12.0
        self._limit = 100
        self._indexer_ids: List[int] = []
        self._category_ids: List[int] = []
        self._auto_fetch_key = True
        self.reload_from_settings()

    def reload_from_settings(self) -> None:
        self._base_url = str(self.settings.get("prowlarr_url", "http://127.0.0.1:9696") or "").strip().rstrip("/")
        self._api_key = str(self.settings.get("prowlarr_api_key", "") or "").strip()
        self._timeout_seconds = float(self.settings.get("prowlarr_request_timeout_seconds", 12.0) or 12.0)
        self._limit = int(self.settings.get("prowlarr_limit", 100) or 100)
        self._auto_fetch_key = bool(self.settings.get("prowlarr_auto_fetch_api_key", True))
        self._indexer_ids = self._normalize_int_list(self.settings.get("prowlarr_indexer_ids", []) or [])
        self._category_ids = self._normalize_int_list(self.settings.get("prowlarr_category_ids", []) or [])

    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        self.last_error = ""
        if not query or not str(query).strip():
            return []
        if not self._base_url:
            self.last_error = "Prowlarr is enabled but prowlarr_url is empty."
            return []

        api_key = self._get_api_key()
        if not api_key:
            self.last_error = "Prowlarr API key is missing (set prowlarr_api_key or enable auto-fetch)."
            return []

        offset = max(0, (int(page or 1) - 1) * max(1, self._limit))
        url = f"{self._base_url}/api/v1/search"
        params: Dict[str, Any] = {
            "Type": "search",
            "Query": str(query).strip(),
            "Offset": offset,
            "Limit": max(1, min(500, self._limit)),
        }
        if self._indexer_ids:
            params["IndexerIds"] = ",".join(str(x) for x in self._indexer_ids)
        if self._category_ids:
            params["Categories"] = ",".join(str(x) for x in self._category_ids)

        try:
            resp = self.session.get(
                url,
                params=params,
                headers={"X-Api-Key": api_key},
                timeout=max(2.0, self._timeout_seconds),
            )
            if resp.status_code == 401:
                self.last_error = "Prowlarr auth failed (401). Check your API key."
                return []
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, list):
                self.last_error = "Prowlarr returned unexpected response."
                return []
        except Exception as exc:
            self.last_error = f"Prowlarr request failed: {exc}"
            return []

        out: List[SearchResult] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or row.get("releaseTitle") or "").strip()
            if not title:
                continue

            # Prefer magnetUrl; fallback to guid/downloadUrl.
            magnet = str(row.get("magnetUrl") or "").strip()
            guid = str(row.get("guid") or "").strip()
            download_url = str(row.get("downloadUrl") or "").strip()
            primary = magnet or guid or download_url
            if not primary:
                continue

            size = int(row.get("size") or 0)
            seeds = int(row.get("seeders") or row.get("seed") or 0)
            leeches = int(row.get("leechers") or row.get("leech") or 0)

            candidates = []
            for cand in (magnet, guid, download_url):
                cand = (cand or "").strip()
                if cand and cand not in candidates:
                    candidates.append(cand)

            indexer = str(row.get("indexer") or row.get("indexerName") or "").strip()
            aggregated_sources = [indexer] if indexer else []

            infohash = SearchResult.extract_infohash(primary) if primary.lower().startswith("magnet:") else ""
            out.append(
                SearchResult(
                    title=title,
                    magnet=primary,
                    size=size,
                    seeds=seeds,
                    leeches=leeches,
                    source=self.name,
                    infohash=infohash,
                    category=str(row.get("categoryDesc") or row.get("category") or "software") if row.get("categoryDesc") or row.get("category") else "software",
                    upload_date=str(row.get("publishDate") or row.get("publishDateUtc") or "") or None,
                    link_candidates=candidates,
                    aggregated_sources=aggregated_sources,
                )
            )
        return out

    def _get_api_key(self) -> str:
        if self._api_key:
            return self._api_key
        if not self._auto_fetch_key:
            return ""
        # Prowlarr exposes initialize.json when auth is disabled; this is purely a convenience for local installs.
        try:
            resp = self.session.get(f"{self._base_url}/initialize.json", timeout=max(2.0, self._timeout_seconds))
            resp.raise_for_status()
            payload = resp.json()
            key = str((payload or {}).get("apiKey") or "").strip()
            if key:
                self._api_key = key
            return self._api_key
        except Exception:
            return ""

    @staticmethod
    def _normalize_int_list(values: Any) -> List[int]:
        out: List[int] = []
        if not isinstance(values, list):
            return out
        for v in values:
            try:
                num = int(v)
            except Exception:
                continue
            if num not in out and num > 0:
                out.append(num)
        return out
