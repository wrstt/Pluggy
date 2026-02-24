from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse
from uuid import uuid4


class CustomLinkStore:
    """Simple JSON-backed store for curated external links."""

    DEFAULT_LINKS: List[Dict[str, Any]] = [
        {
            "id": "bootstrap-suhr-plugin",
            "title": "Suhr Plugin Directory",
            "url": "http://suhr.ir/plugin/",
            "description": "Open directory for plugin packages.",
            "contentType": "software",
            "licenseType": "unknown",
            "platforms": ["windows", "mac"],
            "formats": ["installer", "zip", "7z"],
            "tags": ["opendirectory", "plugins", "vst"],
            "trust": 72,
            "enabled": True,
        },
        {
            "id": "bootstrap-the-eye",
            "title": "The Eye",
            "url": "https://the-eye.eu/",
            "description": "Large public index of mirrored archives and directory content.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["zip", "7z", "iso"],
            "tags": ["opendirectory", "archive", "mirror"],
            "trust": 76,
            "enabled": True,
        },
        {
            "id": "bootstrap-weboas",
            "title": "WebOAS Directories",
            "url": "https://weboas.is/",
            "description": "Curated links including open-directory style resources.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["zip", "7z"],
            "tags": ["opendirectory", "index"],
            "trust": 68,
            "enabled": False,
        },
        {
            "id": "bootstrap-archive-org",
            "title": "Internet Archive",
            "url": "https://archive.org/",
            "description": "Public archive for software and historical packages.",
            "contentType": "software",
            "licenseType": "public-domain",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["zip", "iso"],
            "tags": ["archive", "mirror", "software"],
            "trust": 92,
            "enabled": True,
        },
        {
            "id": "bootstrap-filelisting",
            "title": "FileListing Index Search",
            "url": "https://filelisting.com/",
            "description": "Index-of finder for open directory style pages.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["zip", "7z", "iso"],
            "tags": ["opendirectory", "search"],
            "trust": 62,
            "enabled": False,
        },
        {
            "id": "bootstrap-ftp-gnu",
            "title": "GNU FTP",
            "url": "ftp://ftp.gnu.org/gnu/",
            "description": "Official FTP mirror for GNU packages.",
            "contentType": "software",
            "licenseType": "open-source",
            "platforms": ["linux", "mac", "windows"],
            "formats": ["zip", "tar"],
            "tags": ["ftp", "opensource", "mirror"],
            "trust": 88,
            "enabled": False,
        },
        {
            "id": "bootstrap-ftp-debian",
            "title": "Debian FTP",
            "url": "ftp://ftp.debian.org/debian/",
            "description": "Debian package FTP mirror.",
            "contentType": "software",
            "licenseType": "open-source",
            "platforms": ["linux"],
            "formats": ["installer", "iso"],
            "tags": ["ftp", "mirror", "packages"],
            "trust": 86,
            "enabled": False,
        },
        {
            "id": "bootstrap-open-dir-eyeofjustice",
            "title": "Eye of Justice OD",
            "url": "https://www.eyeofjustice.com/od/",
            "description": "Open directory reference hub.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac"],
            "formats": ["zip", "7z"],
            "tags": ["opendirectory", "index"],
            "trust": 64,
            "enabled": False,
        },
        {
            "id": "bootstrap-opendirsearch-abifog",
            "title": "OpenDir Search (Abifog)",
            "url": "https://opendirsearch.abifog.com/",
            "description": "Search engine focused on open directory pages.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["zip", "7z", "iso"],
            "tags": ["opendirectory", "search", "index"],
            "trust": 63,
            "enabled": False,
        },
        {
            "id": "bootstrap-odcrawler",
            "title": "ODCrawler",
            "url": "https://odcrawler.xyz/",
            "description": "Crawler-style index for directory listings.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["zip", "7z", "iso"],
            "tags": ["opendirectory", "crawler", "search"],
            "trust": 60,
            "enabled": False,
        },
        {
            "id": "bootstrap-filesearch-link",
            "title": "FileSearch Link",
            "url": "https://filesearch.link/",
            "description": "File and directory index search portal.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["zip", "7z", "iso"],
            "tags": ["opendirectory", "search"],
            "trust": 61,
            "enabled": False,
        },
        {
            "id": "bootstrap-filechef",
            "title": "FileChef",
            "url": "https://www.filechef.com/",
            "description": "Public file search engine for indexed downloads.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["zip", "7z", "iso"],
            "tags": ["search", "index", "files"],
            "trust": 60,
            "enabled": False,
        },
        {
            "id": "bootstrap-mmnt",
            "title": "MMNT Search",
            "url": "https://www.mmnt.ru/int/",
            "description": "Legacy index search for public file listings.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["zip", "7z", "iso"],
            "tags": ["search", "index", "opendirectory"],
            "trust": 58,
            "enabled": False,
        },
        {
            "id": "bootstrap-the-eye-torrentables",
            "title": "Torrentables",
            "url": "https://w3abhishek.github.io/torrentables/",
            "description": "Directory of public torrent/open indexing resources.",
            "contentType": "tools",
            "licenseType": "unknown",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["torrent", "magnet"],
            "tags": ["index", "torrent", "opendirectory"],
            "trust": 66,
            "enabled": False,
        },
        {
            "id": "bootstrap-ftp-videolan",
            "title": "VideoLAN FTP",
            "url": "ftp://ftp.videolan.org/pub/",
            "description": "Official FTP mirror for VLC and related packages.",
            "contentType": "software",
            "licenseType": "open-source",
            "platforms": ["windows", "mac", "linux"],
            "formats": ["installer", "zip", "dmg"],
            "tags": ["ftp", "mirror", "opensource"],
            "trust": 90,
            "enabled": False,
        },
        {
            "id": "bootstrap-ftp-freebsd",
            "title": "FreeBSD FTP",
            "url": "ftp://ftp.freebsd.org/pub/FreeBSD/",
            "description": "Official FreeBSD FTP mirror.",
            "contentType": "software",
            "licenseType": "open-source",
            "platforms": ["mac", "linux"],
            "formats": ["iso", "txz"],
            "tags": ["ftp", "mirror", "opensource"],
            "trust": 89,
            "enabled": False,
        },
        {
            "id": "bootstrap-ftp-kernel",
            "title": "Kernel.org FTP",
            "url": "ftp://ftp.kernel.org/pub/",
            "description": "Official Linux kernel FTP mirror.",
            "contentType": "software",
            "licenseType": "open-source",
            "platforms": ["linux", "mac"],
            "formats": ["tar", "xz"],
            "tags": ["ftp", "mirror", "opensource"],
            "trust": 91,
            "enabled": False,
        },
    ]

    def __init__(self, path: Path):
        self._path = path
        self._lock = RLock()
        self._links: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self._path.exists():
                self._links = []
                self._seed_defaults()
                self._ensure_suhr_http_link()
                return
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                links = payload.get("links", []) if isinstance(payload, dict) else []
                self._links = [self._normalize(link) for link in links if isinstance(link, dict)]
                self._seed_defaults()
                self._ensure_suhr_http_link()
            except Exception:
                self._links = []
                self._seed_defaults()
                self._ensure_suhr_http_link()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"links": self._links}
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _seed_defaults(self) -> None:
        existing_urls = {str(link.get("url") or "").strip().lower() for link in self._links}
        changed = False
        for default in self.DEFAULT_LINKS:
            normalized = self._normalize(default)
            normalized_url = str(normalized.get("url") or "").strip().lower()
            if not normalized_url or normalized_url in existing_urls:
                continue
            self._links.append(normalized)
            existing_urls.add(normalized_url)
            changed = True
        if changed:
            self._save()

    def _ensure_suhr_http_link(self) -> None:
        changed = False
        suhr_links = []
        for link in self._links:
            url = str(link.get("url") or "").strip().lower()
            if "suhr.ir/plugin" in url:
                suhr_links.append(link)
                if url.startswith("https://"):
                    link["url"] = "http://suhr.ir/plugin"
                    changed = True
        if not suhr_links:
            self._links.append(self._normalize(self.DEFAULT_LINKS[0]))
            changed = True
        if changed:
            self._save()

    def _normalize(self, link: Dict[str, Any]) -> Dict[str, Any]:
        link_id = str(link.get("id") or f"custom-{uuid4().hex[:10]}")
        normalized_url = self._normalize_url(str(link.get("url") or "").strip())
        tags = [str(t).strip().lower() for t in (link.get("tags") or []) if str(t).strip()]
        platforms = [str(t).strip().lower() for t in (link.get("platforms") or []) if str(t).strip()]
        formats = [str(t).strip().lower() for t in (link.get("formats") or []) if str(t).strip()]
        trust_input = int(max(0, min(100, int(link.get("trust", 70)))))
        trust = self._auto_trust_score(normalized_url, trust_input, tags)
        return {
            "id": link_id,
            "title": str(link.get("title") or "").strip(),
            "url": normalized_url,
            "description": str(link.get("description") or "").strip(),
            "contentType": str(link.get("contentType") or "software").strip().lower(),
            "licenseType": str(link.get("licenseType") or "unknown").strip().lower(),
            "platforms": platforms,
            "formats": formats,
            "tags": tags,
            "trust": trust,
            "enabled": bool(link.get("enabled", True)),
        }

    def _normalize_url(self, url: str) -> str:
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            scheme = (parsed.scheme or "https").lower()
            netloc = parsed.netloc.lower()
            path = parsed.path.rstrip("/")
            if netloc == "suhr.ir" or netloc.endswith(".suhr.ir"):
                scheme = "http"
            normalized = parsed._replace(scheme=scheme, netloc=netloc, path=path, params="", query=parsed.query, fragment="")
            return urlunparse(normalized)
        except Exception:
            return url

    def _auto_trust_score(self, url: str, base: int, tags: List[str]) -> int:
        score = base
        low = url.lower()
        if low.startswith("https://"):
            score += 6
        if any(host in low for host in ("archive.org", "github.com", "sourceforge.net", "itch.io", "gog.com", "nexusmods.com")):
            score += 12
        if any(tag in {"homebrew", "opensource", "open-source"} for tag in tags):
            score += 5
        if any(token in low for token in ("pastebin", "shortener", "adf.ly")):
            score -= 15
        return int(max(0, min(100, score)))

    def list(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            links = list(self._links)
        if enabled_only:
            links = [l for l in links if l.get("enabled", True)]
        return links

    def upsert(self, link: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize(link)
        if not normalized["title"] or not normalized["url"]:
            raise ValueError("title and url are required")
        with self._lock:
            duplicate = next((l for l in self._links if l.get("url") == normalized["url"] and l.get("id") != normalized["id"]), None)
            if duplicate:
                raise ValueError("duplicate url already exists")
            for idx, existing in enumerate(self._links):
                if existing["id"] == normalized["id"]:
                    self._links[idx] = normalized
                    self._save()
                    return normalized
            self._links.append(normalized)
            self._save()
        return normalized

    def import_lines(self, lines: List[str], defaults: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        defaults = defaults or {}
        created: List[Dict[str, Any]] = []
        for line in lines:
            url = str(line).strip()
            if not url:
                continue
            title = url.replace("https://", "").replace("http://", "").split("/")[0]
            payload = {
                "title": title,
                "url": url,
                "description": str(defaults.get("description") or ""),
                "contentType": str(defaults.get("contentType") or "software"),
                "licenseType": str(defaults.get("licenseType") or "unknown"),
                "platforms": list(defaults.get("platforms") or []),
                "formats": list(defaults.get("formats") or []),
                "tags": list(defaults.get("tags") or []),
                "trust": int(defaults.get("trust", 65)),
                "enabled": True,
            }
            try:
                created.append(self.upsert(payload))
            except ValueError:
                continue
        return created

    def delete(self, link_id: str) -> bool:
        with self._lock:
            original_len = len(self._links)
            self._links = [l for l in self._links if l.get("id") != link_id]
            changed = len(self._links) != original_len
            if changed:
                self._save()
            return changed

    def set_enabled_for_all(self, enabled: bool) -> int:
        with self._lock:
            for link in self._links:
                link["enabled"] = bool(enabled)
            self._save()
            return len(self._links)
