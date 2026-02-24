"""
HTTP Source
Generic scraper for user-provided HTTP sources
"""
from typing import List
from ..models.search_result import SearchResult
from .base import BaseSource
import requests
from bs4 import BeautifulSoup
import re
import base64
import time
import threading
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from urllib.parse import urljoin, urlparse, parse_qs, unquote


@dataclass
class SourceHealthState:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    avg_latency_ms: float = 0.0
    last_error: str = ""
    last_success_at: float = 0.0


class BaseHTTPAdapter:
    """Adapter contract for source-specific parsing rules."""

    name = "base"
    version = "1.0"

    def can_handle(self, source_url: str, settings) -> bool:
        return False

    def parse(self, owner, html_content: bytes, source_url: str, query: str, limits: dict) -> List[SearchResult]:
        raise NotImplementedError


class GenericHTTPAdapter(BaseHTTPAdapter):
    """Fallback adapter using resilient heuristic extraction."""

    name = "generic"
    version = "1.0"

    def can_handle(self, source_url: str, settings) -> bool:
        return True

    def parse(self, owner, html_content: bytes, source_url: str, query: str, limits: dict) -> List[SearchResult]:
        return owner._parse_results_default(html_content, source_url, query, limits)


class DomainHTTPAdapter(BaseHTTPAdapter):
    """Base class for domain-specific source adapters."""

    domains = ()

    def can_handle(self, source_url: str, settings) -> bool:
        host = (urlparse(source_url).netloc or "").lower()
        return any(host == d or host.endswith(f".{d}") for d in self.domains)


class NmacHTTPAdapter(DomainHTTPAdapter):
    name = "nmac"
    version = "1.0"
    domains = ("nmac.to",)

    def parse(self, owner, html_content: bytes, source_url: str, query: str, limits: dict) -> List[SearchResult]:
        parsed = owner._parse_results_default(html_content, source_url, query, limits)
        if parsed:
            return parsed
        soup = BeautifulSoup(html_content, "html.parser")
        detail_links = owner._extract_candidate_detail_links_from_selectors(
            soup=soup,
            base_url=source_url,
            query=query,
            selectors=["article h2 a[href]", "h2.entry-title a[href]", "a[rel='bookmark'][href]"],
            reject_substrings=[],
        )
        return owner._crawl_detail_links(detail_links, limits=limits)


class AudiozHTTPAdapter(DomainHTTPAdapter):
    name = "audioz"
    version = "1.0"
    domains = ("audioz.download",)

    def parse(self, owner, html_content: bytes, source_url: str, query: str, limits: dict) -> List[SearchResult]:
        parsed = owner._parse_results_default(html_content, source_url, query, limits)
        if parsed:
            return parsed
        soup = BeautifulSoup(html_content, "html.parser")
        detail_links = owner._extract_candidate_detail_links_from_selectors(
            soup=soup,
            base_url=source_url,
            query=query,
            selectors=["a[rel='bookmark'][href]", "article a[href]"],
            reject_substrings=["/request/", "/audio-lounge/", "/rules"],
        )
        crawled = owner._crawl_detail_links(detail_links, limits=limits)
        if crawled:
            return crawled
        # Audioz frequently gates direct links; return listing/detail pages as actionable fallback.
        listing = owner._extract_listing_results(soup=soup, page_url=source_url, query=query, limits=limits)
        if listing:
            owner.last_error = "Audioz links are often gated; showing matching post pages."
            return listing
        return []


class MackedHTTPAdapter(DomainHTTPAdapter):
    name = "macked"
    version = "1.0"
    domains = ("macked.app",)

    def parse(self, owner, html_content: bytes, source_url: str, query: str, limits: dict) -> List[SearchResult]:
        parsed = owner._parse_results_default(html_content, source_url, query, limits)
        if parsed:
            return parsed
        soup = BeautifulSoup(html_content, "html.parser")
        direct = owner._extract_download_results_from_page(soup=soup, page_url=source_url, limits=limits)
        if direct:
            return direct
        detail_links = owner._extract_candidate_detail_links_from_selectors(
            soup=soup,
            base_url=source_url,
            query=query,
            selectors=["article h2 a[href]", "a[rel='bookmark'][href]"],
            reject_substrings=[],
        )
        return owner._crawl_detail_links(detail_links, limits=limits)


class VstorrentHTTPAdapter(DomainHTTPAdapter):
    name = "vstorrent"
    version = "1.0"
    domains = ("vstorrent.org",)

    def parse(self, owner, html_content: bytes, source_url: str, query: str, limits: dict) -> List[SearchResult]:
        parsed = owner._parse_results_default(html_content, source_url, query, limits)
        if parsed:
            return parsed
        soup = BeautifulSoup(html_content, "html.parser")
        detail_links = owner._extract_candidate_detail_links_from_selectors(
            soup=soup,
            base_url=source_url,
            query=query,
            selectors=["h2 a[href]", "h3 a[href]", "a[href*='/forum/']"],
            reject_substrings=[],
        )
        return owner._crawl_detail_links(detail_links, limits=limits)


class PalinedHTTPAdapter(DomainHTTPAdapter):
    name = "palined"
    version = "1.0"
    domains = ("palined.com",)

    def parse(self, owner, html_content: bytes, source_url: str, query: str, limits: dict) -> List[SearchResult]:
        # Palined is a query-builder shell; use it as a discovery strategy, then crawl discovered targets.
        discovered = owner._palined_discover_pages(query, limits=limits)
        if discovered:
            return owner._crawl_detail_links(discovered, limits=limits)
        # Fallback to generic parsing in case Palined changes and starts exposing direct links.
        return owner._parse_results_default(html_content, source_url, query, limits)


class PlaywrightFallbackAdapter(BaseHTTPAdapter):
    """Optional browser-rendered fetch fallback for JS-heavy pages."""

    name = "playwright-fallback"
    version = "1.0"

    def __init__(self):
        self._sync_playwright = None
        self._availability_error = ""
        self._runtime_ready = True
        self._runtime_error = ""
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            self._sync_playwright = sync_playwright
        except Exception as e:
            self._availability_error = str(e)

    def can_handle(self, source_url: str, settings) -> bool:
        return bool(settings.get("http_playwright_fallback_enabled", True))

    def is_available(self) -> bool:
        return self._sync_playwright is not None

    def availability_error(self) -> str:
        return self._availability_error

    def runtime_ready(self) -> bool:
        return self._runtime_ready

    def runtime_error(self) -> str:
        return self._runtime_error

    def fetch_html(
        self,
        url: str,
        timeout_ms: int = 20000,
        headless: bool = True,
        expand_dynamic: bool = True,
        max_expand_cycles: int = 4,
    ):
        if not self._sync_playwright:
            raise RuntimeError(
                "Playwright fallback unavailable. Install with `pip install playwright` "
                "and run `playwright install chromium`."
            )
        try:
            with self._sync_playwright() as pw:
                browser = pw.chromium.launch(headless=headless)
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=max(1000, int(timeout_ms)))
                self._wait_network_idle(page, timeout_ms=min(10000, max(1000, int(timeout_ms))))
                if expand_dynamic:
                    self._expand_dynamic_content(
                        page=page,
                        timeout_ms=max(300, min(2500, int(timeout_ms // 6))),
                        max_cycles=max(1, int(max_expand_cycles)),
                    )
                html = page.content()
                final_url = page.url
                browser.close()
                return html.encode("utf-8", errors="ignore"), final_url
        except Exception as e:
            message = str(e)
            if "Executable doesn't exist" in message or "download new browsers" in message:
                self._runtime_ready = False
                self._runtime_error = (
                    "Playwright browser runtime is missing. "
                    "Run `playwright install chromium` in your Python environment."
                )
                raise RuntimeError(self._runtime_error)
            raise

    def _wait_network_idle(self, page, timeout_ms: int):
        try:
            page.wait_for_load_state("networkidle", timeout=max(300, int(timeout_ms)))
        except Exception:
            # Many search result pages keep long polling connections open.
            pass

    def _expand_dynamic_content(self, page, timeout_ms: int, max_cycles: int):
        """
        Generic dynamic-navigation pass inspired by "complex navigation" workflows:
        try load-more interactions and bounded infinite-scroll sweeps until no growth.
        """
        previous_count = self._count_candidate_nodes(page)
        for _ in range(max_cycles):
            clicked = self._click_load_more_candidates(page, timeout_ms=timeout_ms, max_clicks=2)
            scrolled = self._infinite_scroll_once(page, timeout_ms=timeout_ms)
            current_count = self._count_candidate_nodes(page)
            if current_count <= previous_count and not clicked and not scrolled:
                break
            previous_count = current_count

    def _count_candidate_nodes(self, page) -> int:
        try:
            return int(page.evaluate(
                """() => {
                    const selectors = [
                        "a[href]",
                        "article a[href]",
                        "h1 a[href], h2 a[href], h3 a[href]",
                        "[class*='result'] a[href]",
                        "[class*='post'] a[href]"
                    ];
                    let total = 0;
                    for (const sel of selectors) {
                        total += document.querySelectorAll(sel).length;
                    }
                    return total;
                }"""
            ) or 0)
        except Exception:
            return 0

    def _click_load_more_candidates(self, page, timeout_ms: int, max_clicks: int) -> bool:
        selectors = [
            "button:has-text('Load more')",
            "button:has-text('Show more')",
            "button:has-text('More')",
            "a:has-text('Load more')",
            "a:has-text('Show more')",
            "[class*='load-more']",
            "[class*='show-more']",
            "[data-testid*='load-more']",
        ]
        clicked_any = False
        clicks_done = 0
        for selector in selectors:
            if clicks_done >= max_clicks:
                break
            try:
                locator = page.locator(selector).first
                if locator.count() <= 0:
                    continue
                if not locator.is_visible():
                    continue
                before = self._count_candidate_nodes(page)
                locator.click(timeout=max(300, timeout_ms))
                self._wait_for_node_growth(page, before_count=before, timeout_ms=timeout_ms)
                self._wait_network_idle(page, timeout_ms=timeout_ms)
                clicked_any = True
                clicks_done += 1
            except Exception:
                continue
        return clicked_any

    def _infinite_scroll_once(self, page, timeout_ms: int) -> bool:
        try:
            before_height = int(page.evaluate("() => document.body ? document.body.scrollHeight : 0") or 0)
            before_count = self._count_candidate_nodes(page)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._wait_for_node_growth(page, before_count=before_count, timeout_ms=timeout_ms)
            self._wait_network_idle(page, timeout_ms=timeout_ms)
            after_height = int(page.evaluate("() => document.body ? document.body.scrollHeight : 0") or 0)
            after_count = self._count_candidate_nodes(page)
            return after_height > before_height or after_count > before_count
        except Exception:
            return False

    def _wait_for_node_growth(self, page, before_count: int, timeout_ms: int):
        timeout_ms = max(200, int(timeout_ms))
        try:
            page.wait_for_function(
                """(prev) => {
                    const count =
                        document.querySelectorAll("a[href]").length +
                        document.querySelectorAll("article a[href]").length +
                        document.querySelectorAll("h1 a[href], h2 a[href], h3 a[href]").length;
                    return count > prev;
                }""",
                arg=int(before_count),
                timeout=timeout_ms,
            )
        except Exception:
            pass


class HTTPSource(BaseSource):
    """Generic HTTP source for custom URLs"""
    
    name = "HTTP"
    
    def __init__(self, settings):
        """
        Initialize with settings manager to access URLs
        
        Args:
            settings: SettingsManager instance
        """
        self.settings = settings
        self.last_error = ""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self._lock = threading.RLock()
        self._cache = {}
        self._health = {}
        self._refresh_pool = ThreadPoolExecutor(max_workers=2)
        self._adapters = [
            PalinedHTTPAdapter(),
            NmacHTTPAdapter(),
            AudiozHTTPAdapter(),
            MackedHTTPAdapter(),
            VstorrentHTTPAdapter(),
            GenericHTTPAdapter(),
        ]
        self._playwright_adapter = PlaywrightFallbackAdapter()
        self.last_adapter_used = "generic"
        self.last_fetch_mode = "http"

    def _build_parse_limits(self, for_test: bool = False, source_url: str = "") -> dict:
        """
        Build bounded parse settings to keep HTTP scraping responsive.
        """
        if for_test:
            limits = {
                "max_detail_pages": 6,
                "max_links_per_detail": 8,
                "time_budget_seconds": 35.0,
                "redirect_timeout": 6.0,
                "request_timeout_seconds": 12.0,
                "request_retries": 2,
                "retry_backoff_seconds": 0.8,
                "detail_concurrency": 3,
            }
            return self._apply_source_limit_overrides(limits, source_url)
        limits = {
            "max_detail_pages": int(self.settings.get("http_detail_max_pages", 10) or 10),
            "max_links_per_detail": int(self.settings.get("http_links_per_detail", 12) or 12),
            "time_budget_seconds": float(self.settings.get("http_time_budget_seconds", 50.0) or 50.0),
            "redirect_timeout": float(self.settings.get("http_redirect_timeout_seconds", 8.0) or 8.0),
            "request_timeout_seconds": float(self.settings.get("http_request_timeout_seconds", 15.0) or 15.0),
            "request_retries": int(self.settings.get("http_request_retries", 2) or 2),
            "retry_backoff_seconds": float(self.settings.get("http_retry_backoff_seconds", 0.8) or 0.8),
            "detail_concurrency": int(self.settings.get("http_detail_concurrency", 3) or 3),
        }
        return self._apply_source_limit_overrides(limits, source_url)
    
    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        """
        Search all configured HTTP sources
        
        Args:
            query: Search query
            page: Page number (may not be supported by all sources)
            
        Returns:
            List of SearchResult objects
        """
        results = []
        self.last_error = ""
        errors = []
        
        # Check if HTTP sources are enabled
        if not self.settings.get("http_sources_enabled", False):
            return results
        
        # Get configured URLs
        source_urls = self.settings.get("http_sources", [])
        if not source_urls:
            return results

        if bool(self.settings.get("http_palined_primary_enabled", True)):
            try:
                primary_results = self._palined_primary_search(query=query, page=page)
                if primary_results:
                    results.extend(primary_results)
            except Exception as e:
                errors.append(f"palined-primary: {e}")
        
        for url_template in source_urls:
            try:
                cached = self._cache_get(url_template, query, page)
                if cached is not None:
                    results.extend(cached)
                    if bool(self.settings.get("http_background_refresh", True)):
                        self._refresh_pool.submit(self._refresh_single_source, url_template, query, page)
                    continue

                # Replace {query} placeholder with actual query
                encoded_query = requests.utils.quote(query)
                search_url = url_template.replace("{query}", encoded_query)

                t0 = time.perf_counter()
                source_results = self._query_single_source(url_template, search_url, query, for_test=False)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                results.extend(source_results)
                self._record_health(url_template, ok=bool(source_results), latency_ms=latency_ms, error="")
                self._cache_set(url_template, query, page, source_results)
                
            except Exception as e:
                err = f"{url_template}: {e}"
                errors.append(err)
                self._record_health(url_template, ok=False, latency_ms=0.0, error=str(e))
                print(f"HTTP source error for {url_template}: {e}")
                continue
        
        if not results and errors:
            self.last_error = "HTTP source errors: " + " | ".join(errors[:3])

        return results

    def _palined_primary_search(self, query: str, page: int) -> List[SearchResult]:
        """
        Use Palined-style open-directory dorks as a primary HTTP discovery pass.
        """
        limits = self._build_parse_limits(for_test=False)
        discovered = self._palined_discover_pages(query, limits=limits)
        if not discovered:
            return []
        # Cache under a virtual key so repeated searches reuse expensive discovery.
        cache_key = "palined-primary://discover"
        cached = self._cache_get(cache_key, query, page)
        if cached is not None:
            return cached
        t0 = time.perf_counter()
        parsed = self._crawl_detail_links(discovered, limits=limits)
        if not parsed:
            parsed = self._listing_urls_to_results(
                discovered,
                query=query,
                max_count=max(6, int(limits.get("max_detail_pages", 10))),
            )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        self._record_health(cache_key, ok=bool(parsed), latency_ms=latency_ms, error="" if parsed else "no-results")
        self._cache_set(cache_key, query, page, parsed)
        return parsed

    def _palined_discover_pages(self, query: str, limits: dict) -> List[str]:
        """
        Build a Palined-style dork and discover candidate pages via search engines.
        """
        q = (query or "").strip()
        if not q:
            return []
        dork = self._build_palined_dork_query(q)
        engine_templates = list(self.settings.get("http_discovery_engine_templates", []) or [])
        if not engine_templates:
            engine_templates = [
                "https://duckduckgo.com/html/?q={query}",
                "https://html.duckduckgo.com/html/?q={query}",
                "https://www.startpage.com/sp/search?query={query}",
                "https://searx.be/search?q={query}",
            ]
        max_pages = max(4, int(limits.get("max_detail_pages", 10)))
        discovered: List[str] = []
        seen = set()
        for tpl in engine_templates:
            url = tpl.replace("{query}", requests.utils.quote(dork))
            try:
                response = self._request_with_retry(
                    url=url,
                    timeout_seconds=float(limits.get("request_timeout_seconds", 15.0)),
                    retries=int(limits.get("request_retries", 2)),
                    backoff_seconds=float(limits.get("retry_backoff_seconds", 0.8)),
                )
                soup = BeautifulSoup(response.content, "html.parser")
                for a in soup.select("a.result__a[href], h2 a[href], a[href]"):
                    href = (a.get("href") or "").strip()
                    if not href:
                        continue
                    normalized = self._normalize_possible_redirect_link(href, url)
                    if not normalized or not normalized.startswith("http"):
                        continue
                    lower = normalized.lower()
                    if "duckduckgo.com" in lower or "google." in lower or "palined.com" in lower:
                        continue
                    if self._is_noise_discovery_link(normalized):
                        continue
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    discovered.append(normalized)
                    if len(discovered) >= max_pages:
                        return discovered
                for normalized in self._extract_http_urls_from_text(soup.get_text(" ", strip=True)):
                    lower = normalized.lower()
                    if "duckduckgo.com" in lower or "google." in lower or "palined.com" in lower:
                        continue
                    if self._is_noise_discovery_link(normalized):
                        continue
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    discovered.append(normalized)
                    if len(discovered) >= max_pages:
                        return discovered
            except Exception:
                continue
        return discovered

    def _build_palined_dork_query(self, query: str) -> str:
        ext_focus = "(zip|rar|7z|dmg|pkg|exe|msi|iso|vst|vst3|dll|torrent)"
        return (
            f'"{query}" intitle:"index of" '
            f'(windows|macos|vst|plugin|installer|portable) {ext_focus} '
            "-inurl:(jsp|pl|php|html|aspx|htm|cf|shtml) "
            "-inurl:(hypem|unknownsecret|sirens|writeups|trimediacentral|articlescentral|listen77|mp3raid|mp3toss|mp3drug|theindexof|index_of|wallywashis|indexofmp3)"
        )

    def _extract_http_urls_from_text(self, text: str) -> List[str]:
        if not text:
            return []
        out = []
        seen = set()
        for raw in re.findall(r"https?://[^\s\"'<>]+", text):
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

    def _is_noise_discovery_link(self, url: str) -> bool:
        lower = url.lower()
        host = (urlparse(url).netloc or "").lower()
        if any(x in host for x in ["startpage.com", "duckduckgo.com", "google.", "bing.com", "searx."]):
            return True
        noisy_paths = [
            "/blog", "/press", "/help", "/privacy", "/terms", "/about", "/compare-", "/browser-on-",
        ]
        return any(path in lower for path in noisy_paths)

    def test_url_template(self, url_template: str, query: str = "test") -> dict:
        """
        Validate one HTTP source template and return diagnostics.
        """
        self.last_error = ""
        template = (url_template or "").strip()
        if not template:
            return {"ok": False, "error": "Template is empty.", "count": 0, "warning": "", "samples": []}

        if "{query}" not in template:
            return {
                "ok": False,
                "error": "Template must include {query}.",
                "count": 0,
                "warning": "",
                "samples": []
            }

        encoded_query = requests.utils.quote((query or "test").strip())
        search_url = template.replace("{query}", encoded_query)

        try:
            limits = self._build_parse_limits(for_test=True, source_url=search_url)
            response = self._request_with_retry(
                url=search_url,
                timeout_seconds=float(limits.get("request_timeout_seconds", 12.0)),
                retries=int(limits.get("request_retries", 2)),
                backoff_seconds=float(limits.get("retry_backoff_seconds", 0.8)),
            )
            adapter = self._select_adapter(search_url)
            results = adapter.parse(
                self,
                response.content,
                search_url,
                query or "test",
                limits=limits
            )
            return {
                "ok": len(results) > 0,
                "error": "",
                "count": len(results),
                "warning": self.last_error,
                "samples": [{"title": r.title, "link": r.magnet} for r in results[:5]]
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Request failed: {e}",
                "count": 0,
                "warning": self.last_error,
                "samples": []
            }

    def _query_single_source(self, url_template: str, search_url: str, query: str, for_test: bool = False) -> List[SearchResult]:
        limits = self._build_parse_limits(for_test=for_test, source_url=search_url)
        adapter = self._select_adapter(search_url)
        self.last_adapter_used = getattr(adapter, "name", "generic")
        self.last_fetch_mode = "http"
        request_error = None
        parsed_results = []
        fetched_html = None

        try:
            response = self._request_with_retry(
                url=search_url,
                timeout_seconds=float(limits.get("request_timeout_seconds", 15.0)),
                retries=int(limits.get("request_retries", 2)),
                backoff_seconds=float(limits.get("retry_backoff_seconds", 0.8)),
            )
            fetched_html = response.content
            parsed_results = adapter.parse(self, response.content, search_url, query, limits=limits)
            if parsed_results:
                return parsed_results
        except Exception as e:
            request_error = e

        if fetched_html:
            try:
                soup = BeautifulSoup(fetched_html, "html.parser")
                listing_results = self._extract_listing_results(soup=soup, page_url=search_url, query=query, limits=limits)
                if listing_results:
                    self.last_error = "HTTP fallback: direct links unavailable, showing likely detail pages."
                    return listing_results
            except Exception:
                pass

        if self._should_use_playwright_fallback(search_url):
            try:
                fetch_kwargs = {
                    "url": search_url,
                    "timeout_ms": int(float(self._source_override(search_url).get("playwright_timeout_seconds", self.settings.get("http_playwright_timeout_seconds", 20.0)) or 20.0) * 1000),
                    "headless": bool(self.settings.get("http_playwright_headless", True)),
                    "expand_dynamic": bool(self._source_override(search_url).get("playwright_expand_dynamic", self.settings.get("http_playwright_expand_dynamic", True))),
                    "max_expand_cycles": int(self._source_override(search_url).get("playwright_max_expand_cycles", self.settings.get("http_playwright_max_expand_cycles", 4)) or 4),
                }
                try:
                    html_bytes, final_url = self._playwright_adapter.fetch_html(**fetch_kwargs)
                except TypeError:
                    # Backward compatibility for test stubs/adapters with the old signature.
                    html_bytes, final_url = self._playwright_adapter.fetch_html(
                        fetch_kwargs["url"],
                        fetch_kwargs["timeout_ms"],
                        fetch_kwargs["headless"],
                    )
                adapter_for_rendered = self._select_adapter(final_url or search_url)
                self.last_adapter_used = getattr(adapter_for_rendered, "name", self.last_adapter_used)
                self.last_fetch_mode = "playwright"
                pw_results = adapter_for_rendered.parse(
                    self, html_bytes, final_url or search_url, query, limits=limits
                )
                if pw_results:
                    self.last_error = "Used Playwright fallback for dynamic page rendering."
                return pw_results
            except Exception as pw_e:
                short_pw = str(pw_e).strip()
                if len(short_pw) > 160:
                    short_pw = short_pw[:157] + "..."
                if request_error:
                    short_req = str(request_error).strip()
                    if len(short_req) > 120:
                        short_req = short_req[:117] + "..."
                    if "Playwright browser runtime is missing" in short_pw:
                        self.last_error = f"HTTP request failed ({short_req})."
                    else:
                        self.last_error = (
                            f"HTTP request failed ({short_req}). Playwright fallback unavailable ({short_pw})."
                        )
                    return []
                self.last_error = f"Playwright fallback unavailable ({short_pw})."
                return []

        if request_error:
            short_req = str(request_error).strip()
            if len(short_req) > 160:
                short_req = short_req[:157] + "..."
            # Soft-fail for source-level resilience: caller can continue with other sources.
            self.last_error = f"HTTP fetch failed for this source ({short_req})."
            return []
        return parsed_results

    def get_runtime_status(self) -> dict:
        return {
            "adapter_count": len(self._adapters),
            "adapters": [
                {
                    "name": getattr(a, "name", "unknown"),
                    "domains": list(getattr(a, "domains", ()) or []),
                }
                for a in self._adapters
            ],
            "playwright_enabled": bool(self.settings.get("http_playwright_fallback_enabled", True)),
            "playwright_expand_dynamic": bool(self.settings.get("http_playwright_expand_dynamic", True)),
            "playwright_max_expand_cycles": int(self.settings.get("http_playwright_max_expand_cycles", 4) or 4),
            "playwright_available": bool(self._playwright_adapter.is_available()),
            "playwright_error": self._playwright_adapter.availability_error(),
            "playwright_runtime_ready": bool(getattr(self._playwright_adapter, "runtime_ready", lambda: True)()),
            "playwright_runtime_error": str(getattr(self._playwright_adapter, "runtime_error", lambda: "")() or ""),
            "last_adapter_used": self.last_adapter_used,
            "last_fetch_mode": self.last_fetch_mode,
            "last_error": self.last_error,
        }

    def _should_use_playwright_fallback(self, source_url: str = "") -> bool:
        if not self._playwright_adapter.can_handle("", self.settings):
            return False
        if source_url:
            override = self._source_override(source_url)
            if "playwright_enabled" in override and not bool(override.get("playwright_enabled")):
                return False
        if not self._playwright_adapter.is_available():
            return False
        runtime_ready = bool(getattr(self._playwright_adapter, "runtime_ready", lambda: True)())
        if not runtime_ready:
            # Auto-disable runtime-broken fallback so packaged users stay seamless.
            try:
                if bool(self.settings.get("http_playwright_fallback_enabled", True)):
                    self.settings.set("http_playwright_fallback_enabled", False)
            except Exception:
                pass
            return False
        return True

    def _source_override(self, source_url: str) -> dict:
        host = (urlparse(source_url).netloc or "").lower()
        if not host:
            return {}
        raw = self.settings.get("http_source_overrides", {}) or {}
        if not isinstance(raw, dict):
            return {}
        for domain, override in raw.items():
            d = str(domain or "").lower().strip()
            if not d:
                continue
            if host == d or host.endswith(f".{d}"):
                return override if isinstance(override, dict) else {}
        return {}

    def _apply_source_limit_overrides(self, limits: dict, source_url: str) -> dict:
        out = dict(limits)
        override = self._source_override(source_url)
        if not override:
            return out
        if "detail_max_pages" in override:
            out["max_detail_pages"] = max(1, int(override.get("detail_max_pages") or out["max_detail_pages"]))
        if "links_per_detail" in override:
            out["max_links_per_detail"] = max(1, int(override.get("links_per_detail") or out["max_links_per_detail"]))
        if "request_timeout_seconds" in override:
            out["request_timeout_seconds"] = max(1.0, float(override.get("request_timeout_seconds") or out["request_timeout_seconds"]))
        if "time_budget_seconds" in override:
            out["time_budget_seconds"] = max(3.0, float(override.get("time_budget_seconds") or out["time_budget_seconds"]))
        if "detail_concurrency" in override:
            out["detail_concurrency"] = max(1, int(override.get("detail_concurrency") or out["detail_concurrency"]))
        return out

    def _request_with_retry(
        self,
        url: str,
        timeout_seconds: float,
        retries: int,
        backoff_seconds: float,
        allow_redirects: bool = True,
    ):
        """GET with bounded retry/backoff for transient network/server failures."""
        last_error = None
        total_attempts = max(1, int(retries) + 1)
        for attempt in range(total_attempts):
            try:
                response = self.session.get(
                    url,
                    timeout=max(1.0, float(timeout_seconds)),
                    allow_redirects=allow_redirects,
                )
                if response.status_code >= 500:
                    response.raise_for_status()
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= total_attempts - 1:
                    break
                delay = max(0.0, float(backoff_seconds)) * (attempt + 1)
                if delay > 0:
                    time.sleep(delay)
        if last_error:
            raise last_error
        raise RuntimeError("HTTP request failed with unknown error")

    def _refresh_single_source(self, url_template: str, query: str, page: int):
        try:
            encoded_query = requests.utils.quote(query)
            search_url = url_template.replace("{query}", encoded_query)
            t0 = time.perf_counter()
            refreshed = self._query_single_source(url_template, search_url, query, for_test=False)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self._record_health(url_template, ok=bool(refreshed), latency_ms=latency_ms, error="")
            self._cache_set(url_template, query, page, refreshed)
        except Exception as e:
            self._record_health(url_template, ok=False, latency_ms=0.0, error=str(e))

    def _cache_key(self, url_template: str, query: str, page: int) -> str:
        return f"{url_template}|{query.lower().strip()}|{page}"

    def _cache_get(self, url_template: str, query: str, page: int):
        ttl = float(self.settings.get("http_cache_ttl_seconds", 300.0) or 300.0)
        allow_stale = bool(self.settings.get("http_allow_stale_cache", True))
        key = self._cache_key(url_template, query, page)
        with self._lock:
            payload = self._cache.get(key)
        if not payload:
            return None
        ts, data = payload
        age = time.time() - ts
        if age <= ttl:
            return data
        if allow_stale:
            self.last_error = "Using stale HTTP cache while refreshing in background."
            return data
        return None

    def _cache_set(self, url_template: str, query: str, page: int, data: List[SearchResult]):
        key = self._cache_key(url_template, query, page)
        with self._lock:
            self._cache[key] = (time.time(), data)

    def _select_adapter(self, source_url: str) -> BaseHTTPAdapter:
        for adapter in self._adapters:
            try:
                if adapter.can_handle(source_url, self.settings):
                    return adapter
            except Exception:
                continue
        return GenericHTTPAdapter()

    def _record_health(self, source_template: str, ok: bool, latency_ms: float, error: str):
        with self._lock:
            state = self._health.get(source_template, SourceHealthState())
            state.attempts += 1
            if ok:
                state.successes += 1
                state.last_error = ""
                state.last_success_at = time.time()
            else:
                state.failures += 1
                state.last_error = error
            if latency_ms > 0:
                if state.avg_latency_ms <= 0:
                    state.avg_latency_ms = latency_ms
                else:
                    state.avg_latency_ms = (state.avg_latency_ms * 0.8) + (latency_ms * 0.2)
            self._health[source_template] = state

    def get_health_snapshot(self) -> dict:
        with self._lock:
            return {
                k: {
                    "attempts": v.attempts,
                    "successes": v.successes,
                    "failures": v.failures,
                    "avg_latency_ms": round(v.avg_latency_ms, 2),
                    "last_error": v.last_error,
                    "last_success_at": v.last_success_at,
                }
                for k, v in self._health.items()
            }

    def _parse_results_default(self, html_content: bytes, source_url: str, query: str, limits: dict) -> List[SearchResult]:
        """
        Parse HTML content to extract torrent results
        
        This is a generic parser that looks for common patterns.
        Users should provide properly structured pages.
        
        Args:
            html_content: Raw HTML bytes
            source_url: Original URL for debugging
            
        Returns:
            List of SearchResult objects
        """
        results = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Strategy 1: Look for magnet links on the current page.
            magnet_links = soup.find_all('a', href=re.compile(r'^magnet:\?', re.IGNORECASE))
            
            for link in magnet_links:
                try:
                    magnet = link.get('href', '')
                    if not magnet:
                        continue
                    
                    # Extract infohash
                    infohash = SearchResult.extract_infohash(magnet)
                    if not infohash:
                        continue
                    
                    # Try to get title from link text or nearby elements
                    title = link.get_text(strip=True)
                    if not title or len(title) < 3:
                        # Try parent or sibling elements
                        parent = link.parent
                        if parent:
                            title = parent.get_text(strip=True)
                    
                    # Clean up title (remove extra whitespace)
                    title = re.sub(r'\s+', ' ', title).strip()
                    if not title or len(title) < 3:
                        title = f"Torrent {infohash[:8]}"
                    
                    # Try to extract metadata from nearby text
                    seeds, leeches, size_bytes = self._extract_metadata(link)
                    
                    result = SearchResult(
                        title=title,
                        magnet=magnet,
                        size=size_bytes,
                        seeds=seeds,
                        leeches=leeches,
                        source="HTTP",
                        infohash=infohash
                    )
                    
                    results.append(result)
                    
                except Exception as e:
                    print(f"Error parsing result: {e}")
                    continue

            if results:
                return results

            # Strategy 2: If no magnets on index/listing pages, discover detail pages
            # and extract download links (some sites keep links on post pages).
            detail_links = self._extract_candidate_detail_links(soup, source_url, query)
            detail_results = self._crawl_detail_links(detail_links, limits=limits)

            if detail_results:
                return detail_results

            listing_results = self._extract_listing_results(soup, source_url, query, limits=limits)
            if listing_results:
                self.last_error = "HTTP fallback: direct links unavailable, showing likely detail pages."
                return listing_results

            # Strategy 3: If site appears gated (captcha/login for links), publish warning.
            gated_msg = self._detect_gated_content(soup.get_text(" ", strip=True).lower())
            if gated_msg:
                self.last_error = gated_msg
            elif detail_links:
                self.last_error = "No direct download links were found on detail pages for this query."
            
        except Exception as e:
            print(f"HTML parsing error: {e}")
        
        return results

    def _extract_listing_results(self, soup: BeautifulSoup, page_url: str, query: str, limits: dict) -> List[SearchResult]:
        links = self._extract_candidate_detail_links(soup, page_url, query)
        max_count = max(4, int(limits.get("max_detail_pages", 10)))
        return self._listing_urls_to_results(links, query=query, max_count=max_count)

    def _listing_urls_to_results(self, links: List[str], query: str, max_count: int = 10) -> List[SearchResult]:
        out: List[SearchResult] = []
        fallback_pool: List[SearchResult] = []
        qtokens = [t for t in re.split(r"\W+", (query or "").lower()) if len(t) >= 2]
        for link in links[:max_count]:
            parsed = urlparse(link)
            if parsed.scheme not in {"http", "https"}:
                continue
            lower = link.lower()
            if self._is_excluded_non_download_link(lower):
                continue
            if lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".css", ".js", ".xml")):
                continue
            title = parsed.path.rsplit("/", 1)[-1] or parsed.netloc
            title = re.sub(r"[-_]+", " ", title)
            title = re.sub(r"\s+", " ", title).strip() or parsed.netloc
            result = SearchResult(
                title=title[:140],
                magnet=link,
                size=0,
                seeds=0,
                leeches=0,
                source="HTTP",
                infohash="",
            )
            if qtokens and not any(tok in lower or tok in title.lower() for tok in qtokens):
                fallback_pool.append(result)
                continue
            out.append(result)
        if not out and fallback_pool:
            out.extend(fallback_pool[:max_count])
        return out

    def _extract_candidate_detail_links(self, soup: BeautifulSoup, base_url: str, query: str) -> List[str]:
        """Extract likely post/detail URLs from a listing page."""
        selectors = [
            "h1 a[href]", "h2 a[href]", "h3 a[href]",
            "a[rel='bookmark'][href]",
            "article a[href]",
            "a[href*='download_']",
            "a[href*='/download/']",
            "a[href*='topic']",
            "a[href*='release']",
            "a[href*='post']",
        ]
        return self._extract_candidate_detail_links_from_selectors(
            soup=soup,
            base_url=base_url,
            query=query,
            selectors=selectors,
            reject_substrings=[],
        )

    def _extract_candidate_detail_links_from_selectors(
        self,
        soup: BeautifulSoup,
        base_url: str,
        query: str,
        selectors: List[str],
        reject_substrings: List[str],
    ) -> List[str]:
        candidates = []
        reject = [x.lower() for x in (reject_substrings or [])]
        for selector in selectors:
            for a in soup.select(selector):
                href = (a.get("href") or "").strip()
                if not href:
                    continue
                abs_url = urljoin(base_url, href)
                lower = abs_url.lower()
                if reject and any(token in lower for token in reject):
                    continue
                if self._is_likely_detail_url(abs_url, base_url, query):
                    score = self._score_candidate_detail_url(abs_url, base_url, query)
                    candidates.append((score, abs_url))

        # Stable dedupe preserving order
        seen = set()
        deduped = []
        for _, u in sorted(candidates, key=lambda item: item[0], reverse=True):
            if u in seen:
                continue
            seen.add(u)
            deduped.append(u)
        return deduped

    def _crawl_detail_links(self, detail_links: List[str], limits: dict) -> List[SearchResult]:
        detail_results = []
        deadline = time.monotonic() + max(5.0, float(limits.get("time_budget_seconds", 50.0)))
        max_pages = max(1, int(limits.get("max_detail_pages", 10)))
        targets = detail_links[:max_pages]
        if not targets:
            return []
        workers = min(max(1, int(limits.get("detail_concurrency", 3))), len(targets))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_url = {
                pool.submit(self._parse_detail_page, detail_url, limits=limits, deadline=deadline): detail_url
                for detail_url in targets
            }
            pending = set(future_to_url.keys())
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.last_error = "HTTP source parsing timed out before all detail pages were checked."
                    break
                done, not_done = wait(
                    pending,
                    timeout=min(0.25, max(0.01, remaining)),
                    return_when=FIRST_COMPLETED,
                )
                pending = set(not_done)
                for future in done:
                    try:
                        detail_results.extend(future.result())
                    except Exception as e:
                        url = future_to_url.get(future, "unknown")
                        print(f"Detail parse error ({url}): {e}")
            for future in pending:
                future.cancel()
        return detail_results

    def _score_candidate_detail_url(self, candidate_url: str, base_url: str, query: str) -> int:
        parsed = urlparse(candidate_url)
        path = (parsed.path or "").lower()
        score = 0
        if any(tok in path for tok in ["/topic", "/release", "/download", "/post", "/torrent"]):
            score += 3
        if re.search(r"/\d{3,}", path):
            score += 2
        q = (query or "").strip().lower()
        if q:
            words = [w for w in re.split(r"\W+", q) if len(w) > 2][:3]
            if words and any(w in path for w in words):
                score += 2
        if parsed.netloc == urlparse(base_url).netloc:
            score += 1
        return score

    def _is_likely_detail_url(self, candidate_url: str, base_url: str, query: str) -> bool:
        """Heuristic to keep article/post links and drop nav/category/pagination."""
        parsed = urlparse(candidate_url)
        base = urlparse(base_url)
        if not parsed.scheme.startswith("http"):
            return False
        if parsed.netloc and parsed.netloc != base.netloc:
            return False

        path = (parsed.path or "").lower()
        if not path or path in ["/", "/now/"]:
            return False
        if any(x in path for x in ["/page/", "/category/", "/tag/", "/author/", "/feed", "/comments", "/wp-"]):
            return False
        if "/request/" in path:
            return False
        if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js", ".xml")):
            return False

        q = (query or "").strip().lower()
        if q:
            token = q.split()[0]
            if token and token in path:
                return True
        return True

    def _parse_detail_page(self, detail_url: str, limits: dict, deadline: float) -> List[SearchResult]:
        """Parse one detail page and extract magnets/direct download links."""
        if time.monotonic() >= deadline:
            return []
        try:
            response = self._request_with_retry(
                url=detail_url,
                timeout_seconds=float(limits.get("request_timeout_seconds", 15.0)),
                retries=int(limits.get("request_retries", 2)),
                backoff_seconds=float(limits.get("retry_backoff_seconds", 0.8)),
            )
            soup = BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            print(f"Detail page fetch error ({detail_url}): {e}")
            return []

        title = self._extract_page_title(soup, detail_url)
        links = []
        max_links = max(1, int(limits.get("max_links_per_detail", 12)))
        for node in soup.find_all(["a", "button"], recursive=True):
            for raw_href in self._extract_link_candidates_from_node(node):
                decoded_href = self._normalize_possible_redirect_link(raw_href, detail_url)
                if self._is_download_like_link(decoded_href):
                    links.append(decoded_href)
                    if len(links) >= max_links:
                        break
            if len(links) >= max_links:
                break

        # Dedupe links
        seen = set()
        deduped_links = []
        for link in links:
            if link in seen:
                continue
            seen.add(link)
            deduped_links.append(link)

        if not deduped_links:
            gated_msg = self._detect_gated_content(soup.get_text(" ", strip=True).lower())
            if gated_msg:
                self.last_error = gated_msg
            return []

        results = []
        for link in deduped_links[:max_links]:
            infohash = SearchResult.extract_infohash(link)
            seeds, leeches, size_bytes = self._extract_metadata(soup)
            results.append(SearchResult(
                title=title,
                magnet=link,  # may be magnet or direct URL
                size=size_bytes,
                seeds=seeds,
                leeches=leeches,
                source="HTTP",
                infohash=infohash
            ))
        return results

    def _extract_download_results_from_page(self, soup: BeautifulSoup, page_url: str, limits: dict) -> List[SearchResult]:
        title = self._extract_page_title(soup, page_url)
        links = []
        max_links = max(1, int(limits.get("max_links_per_detail", 12)))
        for node in soup.find_all(["a", "button"], recursive=True):
            for raw_href in self._extract_link_candidates_from_node(node):
                decoded_href = self._normalize_possible_redirect_link(raw_href, page_url)
                if self._is_download_like_link(decoded_href):
                    links.append(decoded_href)
                    if len(links) >= max_links:
                        break
            if len(links) >= max_links:
                break
        deduped = []
        seen = set()
        for link in links:
            if link in seen:
                continue
            seen.add(link)
            deduped.append(link)
        out = []
        for link in deduped:
            infohash = SearchResult.extract_infohash(link)
            seeds, leeches, size_bytes = self._extract_metadata(soup)
            out.append(SearchResult(
                title=title,
                magnet=link,
                size=size_bytes,
                seeds=seeds,
                leeches=leeches,
                source="HTTP",
                infohash=infohash
            ))
        return out

    def _extract_link_candidates_from_node(self, node) -> List[str]:
        candidates = []
        for attr in ["href", "data-href", "data-url"]:
            value = (node.get(attr) or "").strip()
            if value:
                candidates.append(value)

        onclick = (node.get("onclick") or "").strip()
        if onclick:
            for match in re.findall(r"(https?://[^'\"\s)]+|magnet:\?[^'\"\s)]+)", onclick, flags=re.IGNORECASE):
                candidates.append(match)

        return candidates

    def _extract_page_title(self, soup: BeautifulSoup, fallback_url: str) -> str:
        for selector in ["h1", "title", "meta[property='og:title']"]:
            node = soup.select_one(selector)
            if not node:
                continue
            if selector.startswith("meta"):
                text = (node.get("content") or "").strip()
            else:
                text = node.get_text(" ", strip=True)
            if text:
                return re.sub(r"\s+", " ", text).strip()
        return fallback_url

    def _normalize_possible_redirect_link(self, href: str, page_url: str) -> str:
        """Decode common wrappers and return an absolute target URL."""
        absolute = urljoin(page_url, href)
        parsed = urlparse(absolute)

        # Pattern: /ads/<base64-url>
        if "/ads/" in parsed.path:
            token = parsed.path.rsplit("/", 1)[-1]
            decoded = self._decode_base64_url(token)
            if decoded:
                return decoded

        # Pattern: redirect params like ?url=... or ?u=...
        query = parse_qs(parsed.query)
        for key in ["url", "u", "target", "to", "r"]:
            if key in query and query[key]:
                value = unquote(query[key][0]).strip()
                decoded = self._decode_base64_url(value) or value
                if decoded.startswith("http") or decoded.startswith("magnet:"):
                    return decoded

        # Pattern: encoded target in fragment (#url=...)
        if parsed.fragment:
            frag_pairs = parse_qs(parsed.fragment)
            for key in ["url", "u", "target", "to", "r"]:
                if key in frag_pairs and frag_pairs[key]:
                    frag_value = unquote(frag_pairs[key][0]).strip()
                    decoded = self._decode_base64_url(frag_value) or frag_value
                    if decoded.startswith("http") or decoded.startswith("magnet:"):
                        return decoded

        # Pattern: href.li/?https://example
        if "href.li/" in absolute and "?" in absolute:
            tail = absolute.split("?", 1)[1]
            if tail.startswith("http"):
                return tail

        # Follow redirects only when the URL looks like a wrapper.
        if self._looks_like_redirect_wrapper(absolute):
            return self._follow_redirects(absolute)
        return absolute

    def _looks_like_redirect_wrapper(self, url: str) -> bool:
        lower = url.lower()
        markers = [
            "/ads/",
            "/go/",
            "/goto/",
            "/redirect",
            "redirect=",
            "url=",
            "target=",
            "out=",
            "href.li/",
        ]
        return any(m in lower for m in markers)

    def _decode_base64_url(self, token: str) -> str:
        """Best-effort base64 decode for URL wrappers."""
        try:
            # URL-safe base64 padding
            padded = token + "=" * (-len(token) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="ignore").strip()
            if decoded.startswith("http") or decoded.startswith("magnet:"):
                return decoded
        except Exception:
            pass
        return ""

    def _follow_redirects(self, url: str) -> str:
        """Best-effort redirect resolver for ad wrappers and shorteners."""
        timeout_value = float(self.settings.get("http_redirect_timeout_seconds", 8.0) or 8.0)
        try:
            # HEAD is faster, but many hosts block it; fallback to GET.
            response = self.session.head(url, timeout=timeout_value, allow_redirects=True)
            if response.status_code < 400 and response.url:
                return response.url
        except Exception:
            pass

        try:
            response = self._request_with_retry(
                url=url,
                timeout_seconds=timeout_value,
                retries=1,
                backoff_seconds=0.2,
                allow_redirects=True,
            )
            if response.url:
                return response.url
        except Exception:
            pass
        return url

    def _is_download_like_link(self, href: str) -> bool:
        """Heuristic for magnet/direct-download/file-host links."""
        lower = href.lower()
        if lower.startswith("magnet:"):
            return True
        if not lower.startswith("http"):
            return False
        if self._is_excluded_non_download_link(lower):
            return False

        # Direct file extensions
        if any(lower.endswith(ext) for ext in [
            ".torrent", ".zip", ".rar", ".7z", ".dmg", ".pkg", ".exe", ".msi",
            ".deb", ".rpm", ".iso", ".apk", ".mpkg",
        ]):
            return True

        host_indicators = [
            "rapidgator", "nitroflare", "katfile", "ddownload", "turbobit",
            "uploadgig", "clicknupload", "takefile", "1fichier", "mega.nz",
            "mediafire", "gofile", "workupload", "pixeldrain", "drop.download",
        ]
        path_indicators = ["/download", "/dl/", "/get/", "/file/", "/attachment/"]
        query_indicators = ["download=1", "attachment=", "filename=", "file=", "torrent="]

        return (
            any(x in lower for x in host_indicators)
            or any(x in lower for x in path_indicators)
            or any(x in lower for x in query_indicators)
        )

    def _is_excluded_non_download_link(self, href_lower: str) -> bool:
        """Drop common affiliate/help links that look like file hosts but are not files."""
        excluded_patterns = [
            "webmaster=",
            "/payment",
            "/account/registration",
            "linksnappy",
            "how-to-download",
            "best_multihoster",
            "/audio-lounge/",
            "/user/",
            "/login",
            "/signup",
            "/register",
            "/privacy",
            "/terms",
            "/contact",
        ]
        return any(p in href_lower for p in excluded_patterns)

    def _detect_gated_content(self, page_text_lower: str) -> str:
        """Detect pages that intentionally hide links behind captcha/login."""
        gated_phrases = [
            "click to show download links",
            "show download links",
            "links are hidden",
            "you must be registered",
            "login to view links",
            "guest cannot",
            "captcha",
            "recaptcha",
        ]
        if any(phrase in page_text_lower for phrase in gated_phrases):
            return "HTTP source appears gated (captcha/login), so download links may be hidden."
        return ""
    
    def _extract_metadata(self, link_element) -> tuple:
        """
        Try to extract seeds, leeches, and size from nearby text
        
        Args:
            link_element: BeautifulSoup element containing the magnet link
            
        Returns:
            Tuple of (seeds, leeches, size_bytes)
        """
        seeds = 0
        leeches = 0
        size_bytes = 0
        
        try:
            # Get text from parent row/container
            container = link_element.find_parent(['tr', 'div', 'li', 'article', 'section'])
            if not container:
                return (seeds, leeches, size_bytes)
            
            text = container.get_text()
            
            # Look for seed/leech patterns
            # Common patterns: "Seeds: 123" or "S:123" or just numbers in cells
            seed_match = re.search(r'(?:seed|s)(?:ers)?[:\s]+(\d+)', text, re.IGNORECASE)
            if seed_match:
                seeds = int(seed_match.group(1))
            
            leech_match = re.search(r'(?:leech|l|peer)(?:ers)?[:\s]+(\d+)', text, re.IGNORECASE)
            if leech_match:
                leeches = int(leech_match.group(1))
            
            # Look for size patterns
            # Common patterns: "1.5 GB" "500 MB" "2.3 GiB"
            size_match = re.search(r'([\d.]+)\s*([KMGT]i?B)', text, re.IGNORECASE)
            if size_match:
                size_str = f"{size_match.group(1)} {size_match.group(2)}"
                size_bytes = SearchResult.normalize_size(size_str)
            
        except Exception as e:
            print(f"Metadata extraction error: {e}")
        
        return (seeds, leeches, size_bytes)
