"""Runtime bootstrap for Pluggy web API."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from ..core.download_manager import DownloadManager
from ..core.event_bus import EventBus
from ..core.settings_manager import SettingsManager
from ..core.sqlite_store import SqliteStore
from ..core.source_manager import SourceManager
from ..services.realdebrid_client import RealDebridClient
from ..sources.http_source import HTTPSource
from ..sources.open_directory import OpenDirectorySource
from ..sources.piratebay import PirateBaySource
from ..sources.plugin_loader import PluginContext, SourcePluginLoader, default_plugin_dirs
from ..sources.prowlarr import ProwlarrSource
from ..sources.rd_library import RealDebridLibrarySource
from ..sources.x1337 import X1337Source


@dataclass
class PluggyRuntime:
    """Shared service graph used by web endpoints."""

    store: SqliteStore
    settings: SettingsManager
    event_bus: EventBus
    realdebrid: RealDebridClient
    source_manager: SourceManager
    download_manager: DownloadManager


def build_runtime() -> PluggyRuntime:
    """Create and wire core services, mirroring desktop initialization."""

    data_dir = str(os.environ.get("PLUGGY_DATA_DIR", "") or "").strip()
    settings_dir = Path(data_dir).expanduser() if data_dir else (Path.home() / ".pluggy")
    store = SqliteStore(settings_dir)
    settings = SettingsManager(store=store)
    event_bus = EventBus()
    realdebrid = RealDebridClient(settings, event_bus)
    reliability = {
        "max_retries": int(settings.get("source_max_retries", 1) or 1),
        "retry_backoff_seconds": float(settings.get("source_retry_backoff_seconds", 0.6) or 0.6),
        "circuit_failure_threshold": int(settings.get("source_circuit_failure_threshold", 4) or 4),
        "circuit_cooldown_seconds": float(settings.get("source_circuit_cooldown_seconds", 90.0) or 90.0),
        "search_timeout_seconds": float(settings.get("source_search_timeout_seconds", 18.0) or 18.0),
        "early_return_seconds": float(settings.get("source_early_return_seconds", 8.0) or 8.0),
        "early_return_min_results": int(settings.get("source_early_return_min_results", 6) or 6),
        "prefer_http_completion": bool(settings.get("source_prefer_http_completion", True)),
    }
    source_manager = SourceManager(event_bus, reliability=reliability)
    download_manager = DownloadManager(realdebrid, event_bus, settings=settings)

    source_manager.register(PirateBaySource(settings))
    source_manager.register(X1337Source(settings))
    source_manager.register(HTTPSource(settings))
    source_manager.register(OpenDirectorySource(settings))
    source_manager.register(ProwlarrSource(settings))
    source_manager.register(RealDebridLibrarySource(realdebrid, settings))

    plugin_loader = SourcePluginLoader(default_plugin_dirs())
    plugin_context = PluginContext(settings=settings, rd_client=realdebrid, event_bus=event_bus)
    for src in plugin_loader.load(plugin_context):
        try:
            source_manager.register(src)
        except Exception as exc:
            print(f"Plugin source registration error ({getattr(src, 'name', type(src))}): {exc}")

    enabled_sources = settings.get("enabled_sources", {})
    if enabled_sources:
        for source_name, enabled in enabled_sources.items():
            source_manager.enable_source(source_name, enabled)

    return PluggyRuntime(
        store=store,
        settings=settings,
        event_bus=event_bus,
        realdebrid=realdebrid,
        source_manager=source_manager,
        download_manager=download_manager,
    )
