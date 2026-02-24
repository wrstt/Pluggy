"""
Settings Manager
Handles persistent application settings in user home directory
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import threading

from .request_context import get_profile_id, get_user_id, profile_settings_cache, user_settings_cache


class SettingsManager:
    """Manages application settings with persistence"""

    @staticmethod
    def _default_download_folder() -> Path:
        return Path.home() / "Downloads"

    REQUIRED_HTTP_SOURCE_TEMPLATES = [
        "http://palined.com/search/?q={query}",
        "https://nmac.to/?s={query}",
        "https://macked.app/?s={query}",
        "https://vstorrent.org/?s={query}",
        "https://audioz.download/?s={query}",
    ]
    REQUIRED_HTTP_DISCOVERY_ENGINES = [
        "https://duckduckgo.com/html/?q={query}",
        "https://html.duckduckgo.com/html/?q={query}",
        "https://www.startpage.com/sp/search?query={query}",
        "https://searx.be/search?q={query}",
    ]

    REQUIRED_PIRATEBAY_MIRRORS = [
        "https://www.piratebay.org",
        "https://tpb.party",
        "https://thepiratebay.zone",
        "https://pirateproxylive.org",
        "https://thepiratebay.org",
    ]

    REQUIRED_PIRATEBAY_APIS = [
        "https://apibay.org",
    ]

    REQUIRED_X1337_MIRRORS = [
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

    REQUIRED_OD_SEED_URLS = [
        "http://suhr.ir/plugin/",
        "https://the-eye.eu/public/",
        "https://www.eyeofjustice.com/od/",
        "https://whatintheworld.xyz/",
    ]
    REQUIRED_OD_ENGINE_TEMPLATES = [
        "https://duckduckgo.com/html/?q={query}",
        "https://www.startpage.com/sp/search?query={query}",
        "https://searx.be/search?q={query}",
    ]
    REQUIRED_OD_FILE_EXTENSIONS = [
        "zip", "rar", "7z", "dmg", "pkg", "exe", "msi", "iso", "torrent", "vst", "vst3", "au", "aax", "dll"
    ]

    DEFAULT_SETTINGS = {
        # Search
        "pagination_size": 20,
        "min_seeds": 0,
        "size_min_gb": 0.0,
        "size_max_gb": 100.0,
        
        # Sources
        "enabled_sources": {
            "PirateBay": False,
            "1337x": False,
            "RealDebrid Library": True,
            "HTTP": True,
            "OpenDirectory": True,
            "Prowlarr": False,
        },
        "piratebay_mirror_order": [
            "https://www.piratebay.org",
            "https://tpb.party",
            "https://thepiratebay.zone",
            "https://pirateproxylive.org",
            "https://thepiratebay.org",
        ],
        "piratebay_api_endpoints": [
            "https://apibay.org",
        ],
        "x1337_mirror_order": [
            "https://1337x.to",
            "https://www.1337x.to",
            "https://1337x.st",
            "https://x1337x.ws",
            "https://x1337x.eu",
            "https://1337xx.to",
            "https://www.1337xx.to",
            "https://1377x.to",
            "https://www.1377x.to",
        ],
        "http_detail_max_pages": 10,
        "http_links_per_detail": 12,
        "http_sources_enabled": True,
        "http_sources": [
            "http://palined.com/search/?q={query}",
            "https://nmac.to/?s={query}",
            "https://macked.app/?s={query}",
            "https://vstorrent.org/?s={query}",
            "https://audioz.download/?s={query}",
        ],
        "http_discovery_engine_templates": [
            "https://duckduckgo.com/html/?q={query}",
            "https://html.duckduckgo.com/html/?q={query}",
            "https://www.startpage.com/sp/search?query={query}",
            "https://searx.be/search?q={query}",
        ],
        "http_palined_primary_enabled": True,
        "http_detail_concurrency": 3,
        "http_time_budget_seconds": 50.0,
        "http_redirect_timeout_seconds": 8.0,
        "http_request_timeout_seconds": 15.0,
        "http_request_retries": 2,
        "http_retry_backoff_seconds": 0.8,
        "http_playwright_fallback_enabled": False,
        "http_playwright_headless": True,
        "http_playwright_timeout_seconds": 20.0,
        "http_playwright_expand_dynamic": True,
        "http_playwright_max_expand_cycles": 4,
        "http_source_overrides": {
            "nmac.to": {
                "playwright_enabled": False,
                "detail_max_pages": 10,
                "links_per_detail": 14,
                "request_timeout_seconds": 14.0,
                "time_budget_seconds": 55.0,
            },
            "macked.app": {
                "playwright_enabled": True,
                "playwright_timeout_seconds": 22.0,
                "playwright_expand_dynamic": True,
                "playwright_max_expand_cycles": 5,
                "detail_max_pages": 12,
                "links_per_detail": 14,
                "time_budget_seconds": 60.0,
            },
            "audioz.download": {
                "playwright_enabled": True,
                "playwright_timeout_seconds": 28.0,
                "playwright_expand_dynamic": True,
                "playwright_max_expand_cycles": 6,
                "detail_max_pages": 18,
                "links_per_detail": 18,
                "request_timeout_seconds": 18.0,
                "time_budget_seconds": 80.0,
            },
            "vstorrent.org": {
                "playwright_enabled": False,
                "detail_max_pages": 12,
                "links_per_detail": 14,
                "time_budget_seconds": 55.0,
            },
            "palined.com": {
                "playwright_enabled": False,
                "detail_max_pages": 8,
                "links_per_detail": 10,
                "time_budget_seconds": 30.0,
            },
        },
        "http_cache_ttl_seconds": 300.0,
        "http_allow_stale_cache": True,
        "http_background_refresh": True,
        "source_max_retries": 1,
        "source_retry_backoff_seconds": 0.6,
        "source_circuit_failure_threshold": 4,
        "source_circuit_cooldown_seconds": 90.0,
        "source_search_timeout_seconds": 14.0,
        "source_early_return_seconds": 5.0,
        "source_early_return_min_results": 3,
        "source_prefer_http_completion": True,

        # Open Directory
        "open_directory_enabled": True,
        "od_seed_urls": [
            "http://suhr.ir/plugin/",
            "https://the-eye.eu/public/",
            "https://www.eyeofjustice.com/od/",
            "https://whatintheworld.xyz/",
        ],
        "od_use_search_engines": True,
        "od_engine_templates": [
            "https://duckduckgo.com/html/?q={query}",
            "https://www.startpage.com/sp/search?query={query}",
            "https://searx.be/search?q={query}",
        ],
        "od_file_extensions": ["zip", "rar", "7z", "dmg", "pkg", "exe", "msi", "iso", "torrent", "vst", "vst3", "au", "aax", "dll"],
        "od_max_results": 40,
        "od_max_candidate_pages": 12,
        "od_max_depth": 2,
        "od_max_subdirs_per_page": 32,
        "od_fast_return_min_results": 6,
        "od_fast_return_seconds": 9.0,
        "od_request_timeout_seconds": 10.0,
        "od_request_retries": 1,
        "od_retry_backoff_seconds": 0.4,
        "od_allowed_domains": [],
        "od_exclude_patterns": ["/wp-admin/", "/cdn-cgi/"],
        "od_max_file_size_gb": 0.0,
        "od_insecure_hosts": ["suhr.ir"],
        
        # Downloads
        "download_folder": str(_default_download_folder.__func__()),
        "max_concurrent_downloads": 3,
        "download_backend": "native",
        
        # RealDebrid
        "rd_access_token": "",
        "rd_refresh_token": "",
        "rd_public_client_id": "X245A4XAIBGVM",
        "rd_client_id": "X245A4XAIBGVM",
        "rd_client_secret": "",
        "rd_device_code": "",
        "rd_library_source_enabled": True,
        "rd_request_timeout_seconds": 12.0,
        "rd_sharing_mode": "profile",  # "profile" | "shared"

        # Prowlarr (optional local integration)
        "prowlarr_url": "http://127.0.0.1:9696",
        "prowlarr_api_key": "",
        "prowlarr_auto_fetch_api_key": True,
        "prowlarr_request_timeout_seconds": 12.0,
        "prowlarr_limit": 100,
        "prowlarr_indexer_ids": [],
        "prowlarr_category_ids": [],

        # UI
        "window_width": 1200,
        "window_height": 800,
        "dark_theme": False,
        "ui_theme_pack": "pluggy-glass",
        "prefer_qlementine_style": True,
        "first_run_completed": False,
        "sources_bootstrap_completed": False,
    }
    
    def __init__(self, store=None):
        # Settings stored in user home
        data_dir = str(os.environ.get("PLUGGY_DATA_DIR", "") or "").strip()
        self.settings_dir = Path(data_dir).expanduser() if data_dir else (Path.home() / ".pluggy")
        self.settings_dir.mkdir(exist_ok=True)
        self.settings_file = self.settings_dir / "settings.json"

        # Optional SQLite store for multi-user/profile-scoped settings.
        self._store = store
        
        self._lock = threading.RLock()
        self._settings: Dict[str, Any] = {}
        self._load()

    def attach_store(self, store) -> None:
        self._store = store

    def _load(self):
        """Load settings from file"""
        with self._lock:
            if self.settings_file.exists():
                try:
                    with open(self.settings_file, 'r') as f:
                        loaded = json.load(f)
                        # Merge with defaults (adds new keys if they don't exist)
                        self._settings = {**self.DEFAULT_SETTINGS, **loaded}
                        # Deep-merge nested source flags so new sources get default states.
                        default_sources = self.DEFAULT_SETTINGS.get("enabled_sources", {})
                        loaded_sources = loaded.get("enabled_sources", {}) if isinstance(loaded, dict) else {}
                        self._settings["enabled_sources"] = {**default_sources, **loaded_sources}
                except Exception as e:
                    print(f"Error loading settings: {e}")
                    self._settings = self.DEFAULT_SETTINGS.copy()
            else:
                self._settings = self.DEFAULT_SETTINGS.copy()

            changed = self._ensure_required_source_urls()
            changed = self._normalize_download_folder_in(self._settings) or changed
            if changed and self.settings_file.exists():
                self._save()
            
            # Ensure download folder exists
            Path(self._settings["download_folder"]).mkdir(parents=True, exist_ok=True)

    def _sanitize_download_folder(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return str(self._default_download_folder())
        return str(Path(text).expanduser())

    def _normalize_download_folder_in(self, settings_obj: Dict[str, Any]) -> bool:
        if not isinstance(settings_obj, dict):
            return False
        normalized = self._sanitize_download_folder(settings_obj.get("download_folder"))
        changed = settings_obj.get("download_folder") != normalized
        settings_obj["download_folder"] = normalized
        return changed

    def _ensure_required_source_urls_on(self, settings_obj: Dict[str, Any]) -> Dict[str, Any]:
        """Return a sanitized settings dict with required keys/urls merged in."""
        with self._lock:
            original = self._settings
            try:
                self._settings = dict(settings_obj or {})
                self._settings = {**self.DEFAULT_SETTINGS, **self._settings}
                self._ensure_required_source_urls()
                self._normalize_download_folder_in(self._settings)
                return dict(self._settings)
            finally:
                self._settings = original

    def _load_profile_settings(self, profile_id: str) -> Dict[str, Any]:
        cached = profile_settings_cache.get()
        if cached is not None:
            return cached
        store = self._store
        base = dict(self.DEFAULT_SETTINGS)
        if store is None:
            profile_settings_cache.set(base)
            return base
        loaded = store.get_profile_settings(profile_id) or {}
        merged = {**base, **loaded}
        merged = self._ensure_required_source_urls_on(merged)
        # Auto-write back if missing row or keys were added by sanitizer.
        try:
            if loaded != merged:
                store.set_profile_settings(profile_id, merged)
        except Exception:
            pass
        profile_settings_cache.set(merged)
        return merged

    def _load_user_settings(self, user_id: int) -> Dict[str, Any]:
        cached = user_settings_cache.get()
        if cached is not None:
            return cached
        store = self._store
        if store is None:
            user_settings_cache.set({})
            return {}
        loaded = store.get_user_settings(int(user_id)) or {}
        user_settings_cache.set(loaded)
        return loaded

    def _active_settings_dict(self) -> Tuple[Optional[str], Optional[int], Optional[Dict[str, Any]]]:
        profile_id = get_profile_id()
        user_id = get_user_id()
        if profile_id:
            return profile_id, user_id, self._load_profile_settings(profile_id)
        return None, user_id, None

    def _merge_required_url_list(self, key: str, required: list[str]) -> bool:
        existing = self._settings.get(key, [])
        if not isinstance(existing, list):
            existing = []
        normalized = []
        for item in existing:
            text = str(item or "").strip()
            if text and text not in normalized:
                normalized.append(text)
        for item in required:
            text = str(item or "").strip()
            if text and text not in normalized:
                normalized.append(text)
        changed = normalized != existing
        self._settings[key] = normalized
        return changed

    def _ensure_required_source_urls(self) -> bool:
        # Keep baseline software sources always available; users can still disable providers.
        changed = False
        changed = self._merge_required_url_list("piratebay_mirror_order", self.REQUIRED_PIRATEBAY_MIRRORS) or changed
        changed = self._merge_required_url_list("piratebay_api_endpoints", self.REQUIRED_PIRATEBAY_APIS) or changed
        changed = self._merge_required_url_list("x1337_mirror_order", self.REQUIRED_X1337_MIRRORS) or changed
        changed = self._merge_required_url_list("http_sources", self.REQUIRED_HTTP_SOURCE_TEMPLATES) or changed
        changed = self._merge_required_url_list("http_discovery_engine_templates", self.REQUIRED_HTTP_DISCOVERY_ENGINES) or changed
        changed = self._merge_required_url_list("od_seed_urls", self.REQUIRED_OD_SEED_URLS) or changed
        # suhr.ir OD works reliably over HTTP; normalize legacy HTTPS seeds.
        normalized_od = []
        for raw in list(self._settings.get("od_seed_urls", []) or []):
            text = str(raw or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered.startswith("https://suhr.ir/"):
                text = "http://" + text[len("https://"):]
            if text not in normalized_od:
                normalized_od.append(text)
        if normalized_od != list(self._settings.get("od_seed_urls", []) or []):
            self._settings["od_seed_urls"] = normalized_od
            changed = True
        changed = self._merge_required_url_list("od_engine_templates", self.REQUIRED_OD_ENGINE_TEMPLATES) or changed
        changed = self._merge_required_url_list("od_file_extensions", self.REQUIRED_OD_FILE_EXTENSIONS) or changed
        if int(self._settings.get("od_max_depth", 1) or 1) < 2:
            self._settings["od_max_depth"] = 2
            changed = True
        od_subdirs = int(self._settings.get("od_max_subdirs_per_page", 32) or 32)
        if od_subdirs <= 0:
            self._settings["od_max_subdirs_per_page"] = 32
            changed = True
        elif od_subdirs > 64:
            # Legacy configs used very high crawl fan-out and can stall queries.
            self._settings["od_max_subdirs_per_page"] = 32
            changed = True
        if float(self._settings.get("od_fast_return_seconds", 0.0) or 0.0) <= 0:
            self._settings["od_fast_return_seconds"] = 9.0
            changed = True
        if int(self._settings.get("od_fast_return_min_results", 0) or 0) <= 0:
            self._settings["od_fast_return_min_results"] = 6
            changed = True
        if "http_sources_enabled" not in self._settings:
            self._settings["http_sources_enabled"] = True
            changed = True
        # Bootstrap all known providers enabled one time for fresh installs/migrations.
        if not bool(self._settings.get("sources_bootstrap_completed", False)):
            source_flags = self._settings.get("enabled_sources", {}) or {}
            if not isinstance(source_flags, dict):
                source_flags = {}
            for source_name in ("RealDebrid Library", "HTTP", "OpenDirectory"):
                if not bool(source_flags.get(source_name, False)):
                    source_flags[source_name] = True
                    changed = True
            self._settings["enabled_sources"] = source_flags
            self._settings["sources_bootstrap_completed"] = True
            changed = True
        # Force-enable core web sources for runtime stability baseline on migrated configs.
        if not bool(self._settings.get("sources_force_enable_v3_completed", False)):
            source_flags = self._settings.get("enabled_sources", {}) or {}
            if not isinstance(source_flags, dict):
                source_flags = {}
            for source_name in ("RealDebrid Library", "HTTP", "OpenDirectory"):
                if not bool(source_flags.get(source_name, False)):
                    source_flags[source_name] = True
                    changed = True
            self._settings["enabled_sources"] = source_flags
            self._settings["sources_force_enable_v3_completed"] = True
            changed = True
        return changed
    
    def _save(self):
        """Save settings to file"""
        with self._lock:
            try:
                self._normalize_download_folder_in(self._settings)
                Path(self._settings["download_folder"]).mkdir(parents=True, exist_ok=True)
                with open(self.settings_file, 'w') as f:
                    json.dump(self._settings, f, indent=2)
            except Exception as e:
                print(f"Error saving settings: {e}")
    
    def get(self, key: str, default=None) -> Any:
        """Get a setting value"""
        profile_id, user_id, scoped = self._active_settings_dict()
        if scoped is not None:
            # RD sharing: if enabled, read rd_* keys from user_settings.
            if str(key).startswith("rd_") and user_id and str(scoped.get("rd_sharing_mode", "profile")) == "shared":
                user_scoped = self._load_user_settings(int(user_id))
                if key in user_scoped:
                    return user_scoped.get(key, default)
            value = scoped.get(key, default)
            if key == "download_folder":
                return self._sanitize_download_folder(value)
            return value
        with self._lock:
            value = self._settings.get(key, default)
            if key == "download_folder":
                return self._sanitize_download_folder(value)
            return value
    
    def set(self, key: str, value: Any):
        """Set a setting value and save"""
        if key == "download_folder":
            value = self._sanitize_download_folder(value)
        profile_id, user_id, scoped = self._active_settings_dict()
        if scoped is not None and profile_id:
            store = self._store
            if store is None:
                return
            # RD sharing: write rd_* keys into user_settings when shared.
            if str(key).startswith("rd_") and user_id and str(scoped.get("rd_sharing_mode", "profile")) == "shared":
                user_scoped = self._load_user_settings(int(user_id))
                user_scoped[str(key)] = value
                store.set_user_settings(int(user_id), user_scoped)
                user_settings_cache.set(user_scoped)
                return
            scoped[str(key)] = value
            scoped = self._ensure_required_source_urls_on(scoped)
            store.set_profile_settings(profile_id, scoped)
            profile_settings_cache.set(scoped)
            return
        with self._lock:
            self._settings[str(key)] = value
            self._save()
    
    def update(self, settings_dict: Dict[str, Any]):
        """Update multiple settings at once"""
        settings_dict = dict(settings_dict or {})
        if "download_folder" in settings_dict:
            settings_dict["download_folder"] = self._sanitize_download_folder(settings_dict.get("download_folder"))
        profile_id, user_id, scoped = self._active_settings_dict()
        if scoped is not None and profile_id:
            store = self._store
            if store is None:
                return
            # Split RD keys if shared.
            sharing = user_id and str(scoped.get("rd_sharing_mode", "profile")) == "shared"
            if sharing:
                user_scoped = self._load_user_settings(int(user_id))
            else:
                user_scoped = None
            for k, v in (settings_dict or {}).items():
                if sharing and str(k).startswith("rd_") and user_scoped is not None:
                    user_scoped[str(k)] = v
                else:
                    scoped[str(k)] = v
            scoped = self._ensure_required_source_urls_on(scoped)
            store.set_profile_settings(profile_id, scoped)
            profile_settings_cache.set(scoped)
            if sharing and user_scoped is not None:
                store.set_user_settings(int(user_id), user_scoped)
                user_settings_cache.set(user_scoped)
            return
        with self._lock:
            self._settings.update(settings_dict)
            self._save()
    
    def get_all(self) -> Dict[str, Any]:
        """Get all settings"""
        profile_id, user_id, scoped = self._active_settings_dict()
        if scoped is not None:
            out = dict(scoped)
            if user_id and str(scoped.get("rd_sharing_mode", "profile")) == "shared":
                out.update(self._load_user_settings(int(user_id)))
            return out
        with self._lock:
            return self._settings.copy()
    
    def reset(self):
        """Reset to default settings"""
        profile_id, _, scoped = self._active_settings_dict()
        if scoped is not None and profile_id:
            store = self._store
            if store is None:
                return
            merged = self._ensure_required_source_urls_on(dict(self.DEFAULT_SETTINGS))
            store.set_profile_settings(profile_id, merged)
            profile_settings_cache.set(merged)
            return
        with self._lock:
            self._settings = self.DEFAULT_SETTINGS.copy()
            self._ensure_required_source_urls()
            self._save()
