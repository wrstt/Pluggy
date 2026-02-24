"""
Open Directory Source
Finds direct file links from open directory listings and search-engine discovery.
"""
from typing import List, Set
from urllib.parse import urljoin, urlparse, parse_qs, unquote_plus
import re
import time

import requests
from bs4 import BeautifulSoup

from .base import BaseSource
from ..models.search_result import SearchResult


class BaseODAdapter:
    name = "base"
    domains = ()

    def can_handle(self, page_url: str) -> bool:
        host = (urlparse(page_url).netloc or "").lower()
        return any(host == d or host.endswith(f".{d}") for d in self.domains)

    def parse_page(self, owner, soup: BeautifulSoup, page_url: str, query_tokens: List[str], file_exts: List[str]):
        raise NotImplementedError


class GenericODAdapter(BaseODAdapter):
    name = "generic-index"
    domains = ()

    def can_handle(self, page_url: str) -> bool:
        return True

    def parse_page(self, owner, soup: BeautifulSoup, page_url: str, query_tokens: List[str], file_exts: List[str]):
        return owner._parse_directory_listing_generic(soup, page_url, query_tokens, file_exts)


class SuhrODAdapter(BaseODAdapter):
    name = "suhr"
    domains = ("suhr.ir",)

    def parse_page(self, owner, soup: BeautifulSoup, page_url: str, query_tokens: List[str], file_exts: List[str]):
        # suhr pages can include many nested plugin dirs; keep the same parser but domain-tagged.
        return owner._parse_directory_listing_generic(soup, page_url, query_tokens, file_exts)


class OpenDirectorySource(BaseSource):
    name = "OpenDirectory"

    def __init__(self, settings):
        self.settings = settings
        self.last_error = ""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Pluggy/0.5"
        })
        self.last_fetch_mode = "seed"
        self.last_discovered_pages = 0
        self.last_adapter_used = "generic-index"
        self.last_blocked_count = 0
        self._adapters = [SuhrODAdapter(), GenericODAdapter()]

    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        self.last_error = ""
        self.last_fetch_mode = "seed"
        self.last_discovered_pages = 0
        self.last_adapter_used = "generic-index"
        self.last_blocked_count = 0

        if not bool(self.settings.get("open_directory_enabled", True)):
            return []
        q = (query or "").strip()
        if not q:
            return []

        max_results = int(self.settings.get("od_max_results", 40) or 40)
        roots_setting = self.settings.get("od_seed_urls", None)
        roots = list(roots_setting or [])
        if roots_setting is None:
            roots = ["http://suhr.ir/plugin/"]
        roots = self._canonicalize_roots(roots)

        results: List[SearchResult] = []
        visited_pages: Set[str] = set()
        fast_return_min = int(self.settings.get("od_fast_return_min_results", 6) or 6)
        fast_return_deadline = time.monotonic() + max(2.0, float(self.settings.get("od_fast_return_seconds", 9.0) or 9.0))

        # Domain-specific targeted probes first (fast win for known OD structures like suhr.ir/plugin).
        targeted_pages = self._build_targeted_candidate_pages(q, roots)
        targeted_checked = 0
        for page_url in targeted_pages:
            results.extend(self._crawl_open_dir_page(page_url, q, depth=0, visited_pages=visited_pages))
            targeted_checked += 1
            if results and targeted_checked >= 2:
                return self._dedupe_results(results)[:max_results]
            if len(results) >= max_results:
                return self._dedupe_results(results[:max_results])

        for root in roots:
            results.extend(self._crawl_open_dir_page(root, q, depth=0, visited_pages=visited_pages))
            if len(results) >= max(1, fast_return_min) and time.monotonic() >= fast_return_deadline:
                return self._dedupe_results(results)[:max_results]
            if len(results) >= max_results:
                return self._dedupe_results(results[:max_results])

        if bool(self.settings.get("od_use_search_engines", True)):
            self.last_fetch_mode = "engine"
            candidate_pages = self._discover_candidate_pages(q)
            self.last_discovered_pages = len(candidate_pages)
            for page_url in candidate_pages:
                results.extend(self._crawl_open_dir_page(page_url, q, depth=0, visited_pages=visited_pages))
                if len(results) >= max_results:
                    return self._dedupe_results(results[:max_results])

        out = self._dedupe_results(results)
        if not out and not self.last_error:
            self.last_error = "No open-directory file links found for this query."
        return out[:max_results]

    def _build_targeted_candidate_pages(self, query: str, roots: List[str]) -> List[str]:
        tokens = [t for t in re.split(r"\W+", (query or "").lower()) if len(t) >= 3]
        if not tokens:
            return []
        candidates: List[str] = []
        seen = set()
        for root in roots:
            parsed = urlparse(root)
            host = (parsed.netloc or "").lower()
            path = (parsed.path or "/").strip("/")
            if "suhr.ir" in host and path.startswith("plugin"):
                # Force suhr to HTTP; HTTPS often returns certificate/auth interstitial pages.
                base = f"http://{host}/plugin"
                primary = tokens[0]
                suhr_paths = [
                    f"{base}/mac/{primary}/",
                    f"{base}/windows/{primary}/",
                    f"{base}/win.mac/{primary}/",
                    f"{base}/{primary}/",
                ]
                for p in suhr_paths:
                    if p not in seen:
                        seen.add(p)
                        candidates.append(p)
        return candidates

    def _discover_candidate_pages(self, query: str) -> List[str]:
        templates = list(self.settings.get("od_engine_templates", []) or [])
        if not templates:
            templates = [
                "https://duckduckgo.com/html/?q={query}",
            ]
        max_pages = int(self.settings.get("od_max_candidate_pages", 12) or 12)
        dork = self._build_dork_query(query)
        found: List[str] = []
        seen = set()

        for template in templates:
            url = template.replace("{query}", requests.utils.quote(dork))
            try:
                response = self._request_with_retry(url)
                soup = BeautifulSoup(response.content, "html.parser")
                for a in soup.select("a.result__a[href], h2 a[href], a[href]"):
                    href = (a.get("href") or "").strip()
                    if not href:
                        continue
                    normalized = self._normalize_search_result_link(href, base=url)
                    if not normalized:
                        continue
                    if self._is_search_engine_host(normalized):
                        continue
                    if not self._is_allowed_page(normalized):
                        self.last_blocked_count += 1
                        continue
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    found.append(normalized)
                    if len(found) >= max_pages:
                        return found
                # Some engines include plain URL text snippets that are not anchor hrefs.
                for normalized in self._extract_http_urls_from_text(soup.get_text(" ", strip=True)):
                    if self._is_search_engine_host(normalized):
                        continue
                    if not self._is_allowed_page(normalized):
                        self.last_blocked_count += 1
                        continue
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    found.append(normalized)
                    if len(found) >= max_pages:
                        return found
            except Exception as e:
                self.last_error = f"OpenDirectory engine query failed: {e}"
                continue
        return found

    def _build_dork_query(self, query: str) -> str:
        exts = list(self.settings.get("od_file_extensions", []) or [])
        if not exts:
            exts = ["zip", "rar", "7z", "dmg", "pkg", "exe", "msi", "iso"]
        ext_part = " OR ".join([f'ext:{e}' for e in exts[:10]])
        # Keep OD discovery software-first and reduce common noisy hosts.
        noise_exclusions = (
            "-inurl:(jsp|pl|php|html|aspx|htm|cf|shtml) "
            "-inurl:(listen77|mp3raid|mp3toss|mp3drug|wallywashis|indexofmp3|theindexof)"
        )
        focus_terms = "(windows OR macos OR vst OR plugin OR installer OR portable)"
        return f'intitle:"index of" "{query}" {focus_terms} ({ext_part}) {noise_exclusions}'

    def _normalize_search_result_link(self, href: str, base: str) -> str:
        absolute = urljoin(base, href)
        parsed = urlparse(absolute)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            params = parse_qs(parsed.query)
            uddg = (params.get("uddg") or [""])[0]
            if uddg:
                absolute = unquote_plus(uddg)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            return ""
        return self._canonicalize_url_for_fetch(absolute)

    def _crawl_open_dir_page(self, page_url: str, query: str, depth: int, visited_pages: Set[str]) -> List[SearchResult]:
        page_url = self._canonicalize_url_for_fetch(page_url)
        max_depth = int(self.settings.get("od_max_depth", 1) or 1)
        if depth > max_depth:
            return []
        if not self._is_allowed_page(page_url):
            self.last_blocked_count += 1
            return []
        if page_url in visited_pages:
            return []
        visited_pages.add(page_url)

        try:
            response = self._request_with_retry(page_url)
        except Exception:
            return []
        soup = BeautifulSoup(response.content, "html.parser")
        query_tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
        file_exts = [("." + x.lower().lstrip(".")) for x in (self.settings.get("od_file_extensions", []) or [])]
        if not file_exts:
            file_exts = [".zip", ".rar", ".7z", ".dmg", ".pkg", ".exe", ".msi", ".iso", ".torrent"]

        adapter = self._select_adapter(page_url)
        self.last_adapter_used = getattr(adapter, "name", "generic-index")
        out, dirs_to_crawl = adapter.parse_page(self, soup, page_url, query_tokens, file_exts)

        max_subdirs = int(self.settings.get("od_max_subdirs_per_page", 8) or 8)
        for subdir in dirs_to_crawl[:max_subdirs]:
            out.extend(self._crawl_open_dir_page(subdir, query, depth + 1, visited_pages))

        return out

    def _select_adapter(self, page_url: str):
        for adapter in self._adapters:
            try:
                if adapter.can_handle(page_url):
                    return adapter
            except Exception:
                continue
        return GenericODAdapter()

    def _parse_directory_listing_generic(self, soup: BeautifulSoup, page_url: str, query_tokens: List[str], file_exts: List[str]):
        title = self._page_title(soup, page_url)
        page_context = f"{title} {page_url}".lower()
        page_host = (urlparse(page_url).netloc or "").lower()
        out: List[SearchResult] = []
        dirs_to_crawl: List[str] = []
        directory_fallback: List[SearchResult] = []
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href.startswith("#"):
                continue
            abs_url = urljoin(page_url, href)
            parsed = urlparse(abs_url)
            if parsed.scheme not in {"http", "https"}:
                continue
            if not self._is_allowed_page(abs_url):
                self.last_blocked_count += 1
                continue
            text = (a.get_text(" ", strip=True) or "").strip()
            lower_name = (text or parsed.path.rsplit("/", 1)[-1]).lower()
            match_blob = f"{lower_name} {page_context}"
            matches_query = (not query_tokens) or any(tok in match_blob for tok in query_tokens)

            if href.endswith("/") and href not in {"../", "./"} and (parsed.netloc or "").lower() == page_host:
                dirs_to_crawl.append(abs_url)
                if matches_query or not query_tokens:
                    directory_fallback.append(SearchResult(
                        title=f"{title} - {text or parsed.path.rsplit('/', 1)[-1]}",
                        magnet=abs_url,
                        size=0,
                        seeds=0,
                        leeches=0,
                        source=self.name,
                        infohash="",
                    ))
                continue
            if self._is_probable_directory_link(abs_url) and (parsed.netloc or "").lower() == page_host:
                dirs_to_crawl.append(abs_url)
                if matches_query or not query_tokens:
                    directory_fallback.append(SearchResult(
                        title=f"{title} - {text or parsed.path.rsplit('/', 1)[-1]}",
                        magnet=abs_url,
                        size=0,
                        seeds=0,
                        leeches=0,
                        source=self.name,
                        infohash="",
                    ))
                continue

            if file_exts and not any(parsed.path.lower().endswith(ext) for ext in file_exts):
                # Ignore non-file pages (html/article/index links) to keep OD results actionable.
                continue
            if query_tokens and not matches_query:
                continue

            size_bytes = self._extract_size_from_row(a)
            if not self._within_size_limit(size_bytes):
                self.last_blocked_count += 1
                continue

            out.append(SearchResult(
                title=f"{title} - {text or parsed.path.rsplit('/', 1)[-1]}",
                magnet=abs_url,
                size=size_bytes,
                seeds=0,
                leeches=0,
                source=self.name,
                infohash="",
            ))
        if not out and directory_fallback:
            out.extend(directory_fallback[:12])
        elif not out and dirs_to_crawl:
            for directory_url in dirs_to_crawl[:8]:
                leaf = (urlparse(directory_url).path or "/").rstrip("/").rsplit("/", 1)[-1] or "Directory"
                out.append(SearchResult(
                    title=f"{title} - {leaf}",
                    magnet=directory_url,
                    size=0,
                    seeds=0,
                    leeches=0,
                    source=self.name,
                    infohash="",
                ))
        return out, dirs_to_crawl

    def _is_probable_directory_link(self, url: str) -> bool:
        parsed = urlparse(url)
        path = (parsed.path or "").strip()
        if not path or path.endswith("/"):
            return False
        leaf = path.rsplit("/", 1)[-1]
        # If the final segment has no dot-extension, treat as crawlable directory candidate.
        return "." not in leaf

    def _extract_http_urls_from_text(self, text: str) -> List[str]:
        if not text:
            return []
        out = []
        seen = set()
        for raw in re.findall(r"https?://[^\s\"'<>]+", text):
            # Trim trailing punctuation commonly attached in snippets.
            candidate = raw.rstrip(").,;!?]")
            parsed = urlparse(candidate)
            if parsed.scheme not in {"http", "https"}:
                continue
            if not parsed.netloc:
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            out.append(candidate)
        return out

    def _is_search_engine_host(self, url: str) -> bool:
        host = (urlparse(url).netloc or "").lower()
        blocked = (
            "duckduckgo.com",
            "startpage.com",
            "google.",
            "bing.com",
            "searx.",
            "search.brave.com",
        )
        return any(token in host for token in blocked)

    def _extract_size_from_row(self, anchor) -> int:
        container = anchor.find_parent(["tr", "pre", "li", "div"])
        text = ""
        if container is not None:
            text = container.get_text(" ", strip=True)
        if not text:
            text = anchor.get_text(" ", strip=True)
        m = re.search(r"(\d+(?:\.\d+)?)\s*([KMGTP]i?B)", text, flags=re.IGNORECASE)
        if not m:
            # Some index pages show raw byte counts (e.g. 352825198) without unit.
            raw = re.search(r"\b(\d{7,12})\b", text)
            if not raw:
                return 0
            try:
                return int(raw.group(1))
            except Exception:
                return 0
        return SearchResult.normalize_size(f"{m.group(1)} {m.group(2)}")

    def _page_title(self, soup: BeautifulSoup, fallback: str) -> str:
        node = soup.select_one("title")
        if node:
            title = (node.get_text(" ", strip=True) or "").strip()
            if title:
                return title
        return fallback

    def _request_with_retry(self, url: str):
        url = self._canonicalize_url_for_fetch(url)
        timeout = float(self.settings.get("od_request_timeout_seconds", 10.0) or 10.0)
        retries = int(self.settings.get("od_request_retries", 1) or 1)
        backoff = float(self.settings.get("od_retry_backoff_seconds", 0.4) or 0.4)
        insecure_hosts = {
            str(host or "").strip().lower()
            for host in (self.settings.get("od_insecure_hosts", []) or [])
            if str(host or "").strip()
        }
        last_error = None
        for attempt in range(max(1, retries + 1)):
            try:
                response = self.session.get(url, timeout=max(1.0, timeout))
                response.raise_for_status()
                return response
            except requests.exceptions.SSLError as e:
                last_error = e
                parsed = urlparse(url)
                host = (parsed.netloc or "").lower()
                if parsed.scheme == "https":
                    # For known problematic OD hosts (e.g. suhr.ir expired cert), retry over plain HTTP.
                    http_url = parsed._replace(scheme="http").geturl()
                    try:
                        response = self.session.get(http_url, timeout=max(1.0, timeout))
                        response.raise_for_status()
                        return response
                    except requests.RequestException as http_exc:
                        last_error = http_exc
                if host in insecure_hosts:
                    try:
                        response = self.session.get(url, timeout=max(1.0, timeout), verify=False)
                        response.raise_for_status()
                        return response
                    except requests.RequestException as insecure_exc:
                        last_error = insecure_exc
            except requests.RequestException as e:
                last_error = e
                if attempt >= retries:
                    break
                delay = max(0.0, backoff) * (attempt + 1)
                if delay > 0:
                    time.sleep(delay)
        if last_error:
            raise last_error
        raise RuntimeError("OpenDirectory request failed")

    def _canonicalize_roots(self, roots: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for root in roots:
            normalized = self._canonicalize_url_for_fetch(str(root or "").strip())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
        return out

    def _canonicalize_url_for_fetch(self, url: str) -> str:
        parsed = urlparse(url or "")
        if parsed.scheme not in {"http", "https"}:
            return url
        host = (parsed.netloc or "").lower()
        if host == "suhr.ir" or host.endswith(".suhr.ir"):
            # suhr.ir frequently fails over TLS with cert/auth warnings;
            # force plain HTTP so crawler lands directly on index pages.
            return parsed._replace(scheme="http").geturl()
        return url

    def _dedupe_results(self, results: List[SearchResult]) -> List[SearchResult]:
        out = []
        seen = set()
        for r in results:
            key = (r.magnet or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def _is_allowed_page(self, url: str) -> bool:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        allowed = [d.lower().strip() for d in (self.settings.get("od_allowed_domains", []) or []) if str(d).strip()]
        if allowed and not any(host == d or host.endswith(f".{d}") for d in allowed):
            return False
        exclude = [p.lower().strip() for p in (self.settings.get("od_exclude_patterns", []) or []) if str(p).strip()]
        lower = url.lower()
        if any(p in lower for p in exclude):
            return False
        return True

    def _within_size_limit(self, size_bytes: int) -> bool:
        cap_gb = float(self.settings.get("od_max_file_size_gb", 0.0) or 0.0)
        if cap_gb <= 0 or size_bytes <= 0:
            return True
        cap_bytes = int(cap_gb * (1024 ** 3))
        return size_bytes <= cap_bytes

    def get_runtime_status(self) -> dict:
        return {
            "last_fetch_mode": self.last_fetch_mode,
            "last_discovered_pages": self.last_discovered_pages,
            "last_adapter_used": self.last_adapter_used,
            "blocked_count": self.last_blocked_count,
            "adapters": [getattr(a, "name", "unknown") for a in self._adapters],
            "last_error": self.last_error,
        }
