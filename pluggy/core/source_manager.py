"""
Source Manager
Manages torrent search sources with concurrent search, caching, and hot reload
"""
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from ..models.search_result import SearchResult
from .event_bus import EventBus, Events
import threading
import time
from collections import OrderedDict
import re
from urllib.parse import urlparse
from ..sources.base import BaseSource


class SearchCache:
    """LRU cache for search results"""
    
    def __init__(self, max_size=100, ttl_seconds=300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.RLock()
    
    def _make_key(self, query: str, page: int, filters: Dict) -> str:
        """Create cache key from search parameters"""
        filter_str = ",".join(f"{k}:{v}" for k, v in sorted(filters.items()))
        return f"{query}|{page}|{filter_str}"
    
    def get(self, query: str, page: int, filters: Dict) -> Optional[List[SearchResult]]:
        """Get cached results if still valid"""
        with self._lock:
            key = self._make_key(query, page, filters)
            if key in self._cache:
                timestamp, results = self._cache[key]
                if time.time() - timestamp < self.ttl_seconds:
                    # Move to end (LRU)
                    self._cache.move_to_end(key)
                    return results
                else:
                    del self._cache[key]
            return None
    
    def set(self, query: str, page: int, filters: Dict, results: List[SearchResult]):
        """Cache search results"""
        with self._lock:
            key = self._make_key(query, page, filters)
            self._cache[key] = (time.time(), results)
            self._cache.move_to_end(key)
            
            # Evict oldest if over size
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
    
    def clear(self):
        """Clear all cache"""
        with self._lock:
            self._cache.clear()


@dataclass
class SourceHealth:
    attempts: int = 0
    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0
    last_error: str = ""
    last_latency_ms: float = 0.0
    last_attempt_at: float = 0.0
    last_success_at: float = 0.0
    cooldown_until: float = 0.0
    circuit_open: bool = False
    skipped_due_circuit: int = 0


class SourceManager:
    """Manages torrent sources with concurrent search"""
    
    def __init__(self, event_bus: EventBus, reliability: Optional[Dict] = None):
        self.event_bus = event_bus
        self._sources: Dict[str, any] = {}
        self._enabled: Dict[str, bool] = {}
        self._lock = threading.RLock()
        self._cache = SearchCache()
        self._executor = ThreadPoolExecutor(max_workers=10)
        self._health: Dict[str, SourceHealth] = {}

        reliability = reliability or {}
        self._max_retries = int(reliability.get("max_retries", 0))
        self._retry_backoff_seconds = float(reliability.get("retry_backoff_seconds", 0.5))
        self._circuit_failure_threshold = int(reliability.get("circuit_failure_threshold", 3))
        self._circuit_cooldown_seconds = float(reliability.get("circuit_cooldown_seconds", 120.0))
        self._search_timeout_seconds = float(reliability.get("search_timeout_seconds", 12.0))
        self._early_return_seconds = float(reliability.get("early_return_seconds", 6.0))
        self._early_return_min_results = int(reliability.get("early_return_min_results", 1))
        # Keep HTTP discovery complete by default (do not fast-skip HTTP sources).
        self._prefer_http_completion = bool(reliability.get("prefer_http_completion", True))
    
    def register(self, source):
        """Register a search source"""
        if not isinstance(source, BaseSource):
            raise TypeError(f"Invalid source type for register(): {type(source)}. Expected BaseSource.")
        if not getattr(source, "name", ""):
            raise ValueError("Source must define non-empty 'name'.")
        if not callable(getattr(source, "search", None)):
            raise ValueError("Source must implement callable search(query, page).")
        with self._lock:
            source_name = source.name
            self._sources[source_name] = source
            self._enabled[source_name] = True
            self._health.setdefault(source_name, SourceHealth())
    
    def unregister(self, source_name: str):
        """Unregister a source"""
        with self._lock:
            if source_name in self._sources:
                del self._sources[source_name]
                del self._enabled[source_name]
                self._health.pop(source_name, None)
    
    def enable_source(self, source_name: str, enabled: bool = True):
        """Enable or disable a source"""
        with self._lock:
            if source_name in self._enabled:
                self._enabled[source_name] = enabled
    
    def get_enabled_sources(self) -> List[str]:
        """Get list of enabled source names"""
        with self._lock:
            return [name for name, enabled in self._enabled.items() if enabled]

    def get_source_names(self) -> List[str]:
        """Get all registered source names."""
        with self._lock:
            return list(self._sources.keys())

    def get_source_runtime_status(self, source_name: str) -> Dict:
        with self._lock:
            source = self._sources.get(source_name)
        if source is None:
            return {}
        getter = getattr(source, "get_runtime_status", None)
        if callable(getter):
            try:
                status = getter()
                if isinstance(status, dict):
                    return status
            except Exception:
                return {}
        return {}

    def is_source_enabled(self, source_name: str) -> bool:
        with self._lock:
            return bool(self._enabled.get(source_name, False))

    def get_source_health_snapshot(self) -> Dict[str, Dict]:
        with self._lock:
            now = time.time()
            out = {}
            for name, h in self._health.items():
                out[name] = {
                    "attempts": h.attempts,
                    "successes": h.successes,
                    "failures": h.failures,
                    "consecutive_failures": h.consecutive_failures,
                    "last_error": h.last_error,
                    "last_latency_ms": round(h.last_latency_ms, 2),
                    "last_attempt_at": h.last_attempt_at,
                    "last_success_at": h.last_success_at,
                    "circuit_open": h.circuit_open and now < h.cooldown_until,
                    "cooldown_until": h.cooldown_until,
                    "score": round(self._source_routing_score(name), 2),
                }
            return out
    
    def reload_sources(self, enabled_dict: Dict[str, bool]):
        """Hot reload source enable/disable state"""
        with self._lock:
            for source_name, enabled in enabled_dict.items():
                if source_name in self._enabled:
                    self._enabled[source_name] = enabled
            for source in self._sources.values():
                updater = getattr(source, "reload_from_settings", None)
                if callable(updater):
                    try:
                        updater()
                    except Exception:
                        pass
            self._cache.clear()
            self.event_bus.emit(Events.SOURCES_RELOADED)
    
    def search(
        self,
        query: str,
        page: int = 1,
        per_page: int = 20,
        filters: Optional[Dict] = None
    ) -> List[SearchResult]:
        """
        Concurrent multi-source search with deduplication
        
        Args:
            query: Search query
            page: Page number (1-indexed)
            per_page: Results per page
            filters: Dict with min_seeds, size_min, size_max, enabled_sources
        """
        if not query.strip():
            return []
        
        filters = filters or {}
        wait_for_all_sources = bool(filters.get("wait_for_all_sources", False))
        search_timeout_seconds = float(filters.get("source_timeout_seconds", self._search_timeout_seconds) or self._search_timeout_seconds)
        search_timeout_seconds = max(1.0, search_timeout_seconds)
        
        # Check cache first
        cached = self._cache.get(query, page, filters)
        if cached is not None:
            return cached
        
        self.event_bus.emit(Events.SEARCH_STARTED, {"query": query, "page": page})
        
        # Get enabled sources
        enabled_sources = self.get_enabled_sources()
        filter_sources = filters.get("enabled_sources", [])
        if filter_sources:
            enabled_sources = [s for s in enabled_sources if s in filter_sources]
        # Source routing score influences default execution order.
        enabled_sources = sorted(enabled_sources, key=self._source_routing_score, reverse=True)
        
        if not enabled_sources:
            self.event_bus.emit(Events.SEARCH_COMPLETED, {"results": [], "count": 0})
            return []
        
        # Concurrent search across all enabled sources
        all_results = []
        source_warnings: Dict[str, str] = {}
        futures = {}
        
        with self._lock:
            for source_name in enabled_sources:
                if source_name in self._sources:
                    blocked_reason = self._source_block_reason(source_name)
                    if blocked_reason:
                        source_warnings[source_name] = blocked_reason
                        continue
                    source = self._sources[source_name]
                    future = self._executor.submit(self._safe_search, source, query, page)
                    futures[future] = source_name

        if not futures:
            self.event_bus.emit(Events.SEARCH_COMPLETED, {
                "results": [],
                "count": 0,
                "total": 0,
                "source_warnings": source_warnings,
                "source_health": self.get_source_health_snapshot(),
            })
            return []
        
        # Collect results as they complete
        completed = 0
        total = len(futures)
        
        pending = set(futures.keys())
        search_started = time.monotonic()
        deadline = search_started + search_timeout_seconds
        fast_return_triggered = False

        while pending:
            now = time.monotonic()
            if now >= deadline:
                break

            # Poll in small slices so we can fast-return even if no new futures complete.
            done, not_done = wait(
                pending,
                timeout=min(0.25, max(0.0, deadline - now)),
                return_when=FIRST_COMPLETED
            )
            pending = set(not_done)

            for future in done:
                source_name = futures[future]
                try:
                    results, warning, attempts, latency_ms, ok = future.result()
                    all_results.extend(results)
                    if warning:
                        source_warnings[source_name] = warning
                    self._record_source_outcome(
                        source_name=source_name,
                        ok=ok,
                        error_message=warning or "",
                        latency_ms=latency_ms,
                        attempts=attempts,
                    )
                except Exception as e:
                    print(f"Search error in {source_name}: {e}")
                    source_warnings[source_name] = str(e)
                    self._record_source_outcome(
                        source_name=source_name,
                        ok=False,
                        error_message=str(e),
                        latency_ms=0.0,
                        attempts=1,
                    )

                completed += 1
                self.event_bus.emit(Events.SEARCH_PROGRESS, {
                    "completed": completed,
                    "total": total,
                    "source": source_name,
                    "warning": source_warnings.get(source_name, "")
                })

            elapsed = time.monotonic() - search_started
            pending_source_names = {futures[f] for f in pending}
            http_pending = any(name.lower() == "http" for name in pending_source_names)
            od_pending = any(name.lower() == "opendirectory" for name in pending_source_names)
            if (
                pending
                and len(all_results) >= max(1, self._early_return_min_results)
                and elapsed >= max(0.0, self._early_return_seconds)
                and not wait_for_all_sources
                and not (self._prefer_http_completion and (http_pending or od_pending))
            ):
                fast_return_triggered = True
                break

        for future in pending:
            source_name = futures[future]
            future.cancel()
            if fast_return_triggered:
                timeout_message = (
                    f"{source_name} skipped for fast results (slow source deferred)."
                )
            else:
                timeout_message = (
                    f"{source_name} timed out after {int(search_timeout_seconds)}s; "
                    "results from this source were skipped."
                )
            source_warnings[source_name] = timeout_message
            self._record_source_outcome(
                source_name=source_name,
                ok=False,
                error_message=timeout_message,
                latency_ms=0.0,
                attempts=1,
            )
            completed += 1
            self.event_bus.emit(Events.SEARCH_PROGRESS, {
                "completed": completed,
                "total": total,
                "source": source_name,
                "warning": timeout_message
            })
        
        # Deduplicate by infohash
        unique_results = self._deduplicate(all_results)
        
        # Aggregate similar items across sources into one unified result entry.
        unified_results = self._aggregate_results(unique_results)

        # Apply filters
        filtered = self._apply_filters(unified_results, filters)
        
        # Sort intelligently
        sorted_results = self._sort_results(filtered)
        
        # Paginate
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated = sorted_results[start_idx:end_idx]
        
        # Cache results
        self._cache.set(query, page, filters, paginated)
        
        self.event_bus.emit(Events.SEARCH_COMPLETED, {
            "results": paginated,
            "count": len(paginated),
            "total": len(sorted_results),
            "source_warnings": source_warnings,
            "source_health": self.get_source_health_snapshot(),
        })
        
        return paginated
    
    def _safe_search(self, source, query: str, page: int) -> Tuple[List[SearchResult], Optional[str], int, float, bool]:
        """
        Safely execute source search with retries and backoff.
        Returns: results, warning, attempts, latency_ms, ok
        """
        attempts = 0
        last_warning = ""
        last_latency_ms = 0.0
        for attempt in range(self._max_retries + 1):
            attempts += 1
            start = time.perf_counter()
            try:
                results = source.search(query, page)
                last_latency_ms = (time.perf_counter() - start) * 1000.0
                warning = getattr(source, "last_error", "") or ""
                # Treat warning-only + empty results as transient failure (retry-able).
                if warning and not results:
                    source_name = str(getattr(source, "name", "") or "").strip().lower()
                    if self._is_nonfatal_empty_warning(source_name, warning):
                        return [], None, attempts, last_latency_ms, True
                    last_warning = warning
                    if attempt < self._max_retries:
                        time.sleep(self._retry_backoff_seconds * (2 ** attempt))
                        continue
                    return [], warning, attempts, last_latency_ms, False
                return results, (warning or None), attempts, last_latency_ms, True
            except Exception as e:
                last_latency_ms = (time.perf_counter() - start) * 1000.0
                last_warning = str(e)
                print(f"Source search error: {e}")
                if attempt < self._max_retries:
                    time.sleep(self._retry_backoff_seconds * (2 ** attempt))
                    continue
                return [], str(e), attempts, last_latency_ms, False

        return [], (last_warning or None), attempts, last_latency_ms, False

    def _is_nonfatal_empty_warning(self, source_name: str, warning: str) -> bool:
        normalized = (warning or "").strip().lower()
        if not normalized:
            return False
        if source_name == "opendirectory":
            return normalized.startswith("no open-directory file links found")
        return False

    def _source_routing_score(self, source_name: str) -> float:
        """Higher is better; used to route queries across enabled sources."""
        h = self._health.get(source_name)
        if not h or h.attempts == 0:
            return 100.0
        success_rate = h.successes / max(1, h.attempts)
        latency_penalty = min(h.last_latency_ms / 150.0, 25.0)
        failure_penalty = h.consecutive_failures * 8.0
        circuit_penalty = 40.0 if (h.circuit_open and time.time() < h.cooldown_until) else 0.0
        return (40.0 + success_rate * 60.0) - latency_penalty - failure_penalty - circuit_penalty

    def _source_block_reason(self, source_name: str) -> str:
        h = self._health.get(source_name)
        if not h:
            return ""
        now = time.time()
        if h.circuit_open and now < h.cooldown_until:
            h.skipped_due_circuit += 1
            remain = int(max(1, h.cooldown_until - now))
            return f"Circuit open after failures; retrying automatically in {remain}s."
        if h.circuit_open and now >= h.cooldown_until:
            # Half-open attempt allowed now.
            h.circuit_open = False
            h.consecutive_failures = 0
            h.cooldown_until = 0.0
        return ""

    def _record_source_outcome(self, source_name: str, ok: bool, error_message: str, latency_ms: float, attempts: int):
        with self._lock:
            h = self._health.setdefault(source_name, SourceHealth())
            h.attempts += max(1, attempts)
            h.last_attempt_at = time.time()
            h.last_latency_ms = float(latency_ms or 0.0)
            if ok:
                h.successes += 1
                h.consecutive_failures = 0
                h.last_error = ""
                h.last_success_at = h.last_attempt_at
                h.circuit_open = False
                h.cooldown_until = 0.0
            else:
                h.failures += 1
                h.consecutive_failures += 1
                h.last_error = error_message
                if h.consecutive_failures >= self._circuit_failure_threshold:
                    h.circuit_open = True
                    h.cooldown_until = time.time() + self._circuit_cooldown_seconds
    
    def _deduplicate(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Deduplicate results by infohash, keeping best seed count
        """
        seen_hash: Dict[str, SearchResult] = {}
        seen_nonhash: Dict[str, SearchResult] = {}
        
        for result in results:
            if not result.infohash:
                # Keep non-magnet/direct-link entries deduped by URL.
                key = (result.magnet or "").strip().lower()
                if not key:
                    key = (result.title or "").strip().lower()
                if not key:
                    continue
                if key not in seen_nonhash:
                    seen_nonhash[key] = result
                continue
            
            if result.infohash not in seen_hash:
                seen_hash[result.infohash] = result
            else:
                # Keep result with higher seeds
                if result.seeds > seen_hash[result.infohash].seeds:
                    seen_hash[result.infohash] = result
        
        return list(seen_hash.values()) + list(seen_nonhash.values())
    
    def _apply_filters(self, results: List[SearchResult], filters: Dict) -> List[SearchResult]:
        """Apply search filters"""
        filtered = results
        
        # Min seeds filter
        min_seeds = filters.get("min_seeds", 0)
        if min_seeds > 0:
            filtered = [r for r in filtered if r.seeds >= min_seeds]
        
        # Size range filter (in GB)
        size_min = filters.get("size_min_gb", 0) * 1_000_000_000
        size_max = filters.get("size_max_gb", 999) * 1_000_000_000
        filtered = [r for r in filtered if size_min <= r.size <= size_max]
        
        return filtered

    def _aggregate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Merge same program/version across all sources and keep all links in one place.
        """
        grouped: Dict[str, SearchResult] = {}
        group_meta: Dict[str, Dict] = {}
        passthrough: List[SearchResult] = []

        for result in results:
            # Initialize candidate metadata for every result.
            self._ensure_link_candidate(result, result)

            key = self._content_key(result)
            if not key:
                passthrough.append(result)
                continue

            resolved_key = key
            if key not in grouped:
                fuzzy_key = self._find_compatible_group_key(key, group_meta)
                if fuzzy_key:
                    resolved_key = fuzzy_key

            if resolved_key not in grouped:
                grouped[resolved_key] = result
                stem, version = resolved_key.split("|", 1)
                group_meta[resolved_key] = {
                    "version": version,
                    "tokens": set(stem.split()),
                }
            else:
                grouped[resolved_key] = self._merge_result(grouped[resolved_key], result)

        return list(grouped.values()) + passthrough

    def _find_compatible_group_key(self, key: str, group_meta: Dict[str, Dict]) -> str:
        """Find an existing grouping key with same version and strong name overlap."""
        stem, version = key.split("|", 1)
        tokens = set(stem.split())
        if not tokens:
            return ""
        for existing_key, meta in group_meta.items():
            if meta.get("version") != version:
                continue
            existing_tokens = meta.get("tokens", set())
            if not existing_tokens:
                continue
            inter = len(tokens & existing_tokens)
            union = len(tokens | existing_tokens)
            similarity = inter / union if union else 0.0
            if similarity >= 0.50:
                return existing_key
        return ""

    def _merge_result(self, base: SearchResult, incoming: SearchResult) -> SearchResult:
        """Merge another result into the base unified entry."""
        self._ensure_link_candidate(base, incoming)

        for source_name in [base.source, incoming.source]:
            if source_name and source_name not in base.aggregated_sources:
                base.aggregated_sources.append(source_name)

        # Merge and de-dup link candidates.
        seen = set()
        merged_candidates = []
        for candidate in base.link_candidates + incoming.link_candidates:
            url = (candidate.get("url") or "").strip()
            if not url:
                continue
            if url in seen:
                continue
            seen.add(url)
            merged_candidates.append(candidate)

        merged_candidates.sort(key=lambda c: c.get("quality", 0), reverse=True)
        base.link_candidates = merged_candidates

        # Best candidate becomes primary download link.
        if merged_candidates:
            best = merged_candidates[0]
            base.magnet = best.get("url", base.magnet)
            base.link_quality = int(best.get("quality", 0))

        # Prefer better availability for display/ranking.
        if incoming.seeds > base.seeds:
            base.seeds = incoming.seeds
            base.leeches = incoming.leeches

        # Keep larger size when available.
        if incoming.size > base.size:
            base.size = incoming.size

        # Prefer title carrying clearer version markers.
        if self._title_specificity_score(incoming.title) > self._title_specificity_score(base.title):
            base.title = incoming.title

        source_count = len(base.aggregated_sources)
        if source_count > 1:
            base.source = f"{base.aggregated_sources[0]} +{source_count - 1}"
        return base

    def _ensure_link_candidate(self, target: SearchResult, source_result: SearchResult):
        """Ensure source_result link exists inside target.link_candidates."""
        if not target.aggregated_sources:
            target.aggregated_sources = [target.source] if target.source else []

        url = (source_result.magnet or "").strip()
        if not url:
            return

        quality = self._link_quality(source_result)
        candidate = {
            "url": url,
            "source": source_result.source,
            "quality": quality,
            "seeds": source_result.seeds,
            "leeches": source_result.leeches,
            "size": source_result.size,
        }

        if not target.link_candidates:
            target.link_candidates = [candidate]
            target.link_quality = quality
            return

        for existing in target.link_candidates:
            if existing.get("url") == url:
                existing["quality"] = max(existing.get("quality", 0), quality)
                return
        target.link_candidates.append(candidate)

    def _link_quality(self, result: SearchResult) -> int:
        """
        Score link quality for default selection.
        Torrent links primarily use seeds; HTTP links use host/path signals.
        """
        link = (result.magnet or "").strip().lower()
        score = 0

        if result.infohash or link.startswith("magnet:"):
            score += min(max(result.seeds, 0), 5000)
            score += min(max(result.leeches, 0), 500) // 2
            return score

        # HTTP/direct links
        parsed = urlparse(link)
        host = (parsed.netloc or "").lower()
        path = (parsed.path or "").lower()

        if parsed.scheme == "https":
            score += 25
        if any(path.endswith(ext) for ext in [".zip", ".rar", ".7z", ".dmg", ".pkg", ".exe", ".msi", ".iso"]):
            score += 30
        if "/file/" in path or "/download/" in path or "/dl/" in path:
            score += 20

        host_weights = {
            "rapidgator": 22,
            "nitroflare": 20,
            "katfile": 17,
            "ddownload": 17,
            "turbobit": 14,
            "uploadgig": 14,
            "mega.nz": 24,
            "mediafire": 18,
            "pixeldrain": 16,
            "workupload": 12,
        }
        for key, weight in host_weights.items():
            if key in host:
                score += weight
                break

        # Mild quality proxy by file size when available.
        if result.size > 0:
            score += min(result.size // 500_000_000, 15)  # +1 per 500MB up to +15
        return score

    def _content_key(self, result: SearchResult) -> str:
        """
        Generate a program+version key for cross-source grouping.
        Keeps version in key so 2023 and 2024 do not collapse.
        """
        title = (result.title or "").lower()
        title = re.sub(r"\[[^\]]+\]|\([^)]+\)", " ", title)
        title = re.sub(r"[^a-z0-9.+]+", " ", title).strip()
        if not title:
            return ""

        version = self._extract_version_key(title)
        tokens = [t for t in title.split() if t and not t.isdigit()]
        stop = {
            "x64", "x86", "win", "windows", "mac", "linux", "multilingual", "incl",
            "keygen", "crack", "repack", "proper", "portable", "final", "build",
            "adobe", "microsoft", "corel", "apple",
        }
        core = [t for t in tokens if t not in stop]
        if not core:
            core = tokens
        stem = " ".join(core[:6]).strip()
        if not stem:
            return ""
        return f"{stem}|{version or 'nover'}"

    def _extract_version_key(self, title: str) -> str:
        patterns = [
            r"\b(20\d{2}(?:\.\d+)*)\b",
            r"\bv(\d+(?:\.\d+){0,3})\b",
            r"\b(\d+\.\d+(?:\.\d+)*)\b",
        ]
        for pattern in patterns:
            m = re.search(pattern, title)
            if m:
                return m.group(1)
        return ""

    def _title_specificity_score(self, title: str) -> int:
        t = (title or "").lower()
        score = len(t)
        if re.search(r"\b20\d{2}\b", t):
            score += 30
        if re.search(r"\bv\d+(\.\d+)*\b", t):
            score += 20
        return score
    
    def _sort_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Intelligent sorting with version awareness:
        1. Detect version numbers in titles
        2. Group by base name (e.g., "Photoshop" groups all versions)
        3. Within groups, sort by version (newest first)
        4. Across groups, sort by seeds
        5. Use size as tiebreaker (larger = better quality)
        
        Example:
        - "Adobe Photoshop 2024 v25.0" (50 seeds)
        - "Adobe Photoshop 2023 v24.0" (100 seeds) 
        - "GIMP 2.10" (30 seeds)
        
        Result order:
        1. Photoshop 2024 (newest version, good seeds)
        2. Photoshop 2023 (older version but high seeds)
        3. GIMP 2.10
        """
        import re
        
        # Enhanced sorting: version-aware + seeds + size
        def sort_key(result: SearchResult):
            title = result.title.lower()
            
            # Extract version number if present
            # Patterns: v1.2.3, 2023, version 4.5, etc.
            version_match = re.search(r'v?(\d+)\.?(\d*)\.?(\d*)', title)
            version_score = 0
            
            if version_match:
                # Convert version to comparable number
                # v2024.1.0 = 2024010000
                # v1.2.3 = 1020300
                major = int(version_match.group(1) or 0)
                minor = int(version_match.group(2) or 0)
                patch = int(version_match.group(3) or 0)
                version_score = (major * 1000000) + (minor * 1000) + patch
            
            # Detect quality indicators in title
            quality_bonus = 0
            if any(term in title for term in ['repack', 'proper', 'real']):
                quality_bonus += 10
            if 'crack' in title or 'keygen' in title:
                quality_bonus += 5
            if '1080p' in title or '4k' in title:
                quality_bonus += 8
            
            # Primary sort: seeds (most important for availability)
            # Secondary: version (newer is better)
            # Tertiary: size (larger usually means better quality)
            # Quaternary: quality indicators
            
            return (
                -result.seeds,  # Negative for descending (more seeds = better)
                -getattr(result, "link_quality", 0),  # Better HTTP/torrent link candidate first
                -version_score,  # Negative for descending (higher version = better)
                -result.size,  # Negative for descending (larger = better)
                -quality_bonus  # Negative for descending
            )
        
        return sorted(results, key=sort_key)
    
    def shutdown(self):
        """Shutdown executor"""
        self._executor.shutdown(wait=False)
