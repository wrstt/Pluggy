"""FastAPI app exposing Pluggy core features for web clients."""

from __future__ import annotations

from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, TimeoutError as FutureTimeoutError, wait
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Any, Dict, List, Optional
import threading
import time
import uuid
import re
import os
import subprocess

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import sqlite3

from ..models.download_job import DownloadJob, JobStatus
from ..models.search_result import SearchResult
from ..utils.file_utils import get_unique_filename, sanitize_filename
from ..core.request_context import SessionContext, get_session as get_request_session, set_session
from .custom_links import CustomLinkStore
from .runtime import PluggyRuntime, build_runtime


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _to_provider_health(consecutive_failures: int, circuit_open: bool) -> str:
    if circuit_open:
        return "offline"
    if consecutive_failures >= 6:
        return "degraded"
    return "healthy"


def _to_transfer_status(status: JobStatus) -> str:
    if status in {JobStatus.ERROR, JobStatus.CANCELLED}:
        return "failed"
    return status.value


SOFTWARE_HINTS = {
    "vst",
    "vst3",
    "plugin",
    "plugins",
    "windows",
    "win",
    "win64",
    "mac",
    "macos",
    "osx",
    "dmg",
    "au",
    "aax",
    "ableton",
    "cubase",
    "fl",
    "studio",
    "kontakt",
    "audio",
    "driver",
    "installer",
    "software",
    "app",
}

MEDIA_HINTS = {
    "1080p",
    "2160p",
    "720p",
    "x264",
    "x265",
    "bluray",
    "brrip",
    "webrip",
    "hdrip",
    "dvdrip",
    "netflix",
    "season",
    "episode",
    "s01",
    "s02",
    "e01",
    "movie",
    "tv",
}

SOURCE_PURPOSES = {
    "PirateBay": "General torrent indexer used for broad software discovery.",
    "1337x": "General torrent indexer with strong seeded torrent coverage.",
    "HTTP": "HTTP scraping adapter focused on direct software and plugin links.",
    "OpenDirectory": "Open-directory crawler for direct Windows/macOS package files.",
    "Prowlarr": "Prowlarr local indexer manager (uses your configured indexers).",
    "RealDebrid Library": "Your own RealDebrid cloud library entries.",
}

PLATFORM_TOKENS = {
    "windows": {"windows", "win", "win64", "exe", "msi"},
    "mac": {"mac", "macos", "osx", "dmg", "pkg"},
    "linux": {"linux", "appimage", "deb", "rpm"},
    "android": {"android", "apk"},
    "emulator": {"emulator", "rom", "bios"},
}

CONTENT_TOKENS = {
    "pc-games": {"pc", "game", "games", "steam", "gog"},
    "roms": {"rom", "roms", "iso", "bios"},
    "mods": {"mod", "mods", "patch"},
    "tools": {"tool", "tools", "utility", "trainer", "editor"},
    "software": {"software", "app", "application", "plugin"},
}

LICENSE_TOKENS = {
    "free": {"freeware", "free"},
    "paid": {"paid", "commercial"},
    "open-source": {"open-source", "oss", "gpl", "mit", "apache"},
    "public-domain": {"public-domain", "publicdomain"},
}

FORMAT_TOKENS = {
    "zip": {"zip"},
    "7z": {"7z"},
    "iso": {"iso"},
    "installer": {"exe", "msi", "pkg", "dmg", "installer"},
}


def _csv_tokens(value: str) -> set[str]:
    return {piece.strip().lower() for piece in (value or "").split(",") if piece.strip()}


def _result_meta(result: SearchResult) -> Dict[str, Any]:
    candidates = list(result.link_candidates or [])
    if not candidates:
        return {}
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    meta = first.get("meta", {}) if isinstance(first, dict) else {}
    return meta if isinstance(meta, dict) else {}


def _result_token_pool(result: SearchResult) -> set[str]:
    text = (result.title or "").lower()
    meta = _result_meta(result)
    pools = [text]
    for key in ("platforms", "tags", "formats"):
        pools.extend([str(x).lower() for x in (meta.get(key) or [])])
    pools.append(str(meta.get("contentType") or "").lower())
    pools.append(str(meta.get("licenseType") or "").lower())
    tokens: set[str] = set()
    for blob in pools:
        tokens.update(piece for piece in blob.replace("/", " ").replace("-", " ").split() if piece)
    return tokens


def _infer_trust(result: SearchResult) -> int:
    meta = _result_meta(result)
    if "trust" in meta:
        try:
            return int(max(0, min(100, int(meta.get("trust", 0)))))
        except Exception:
            pass
    relevance = max(0, _software_score(result.title) - _media_noise_score(result.title))
    return int(max(0, min(100, int((result.link_quality or result.seeds) + relevance))))


def _matches_filter_group(requested: set[str], token_map: Dict[str, set[str]], token_pool: set[str]) -> bool:
    if not requested:
        return True
    for request_token in requested:
        if request_token in token_pool:
            return True
        mapped = token_map.get(request_token, set())
        if mapped.intersection(token_pool):
            return True
    return False


def _search_sort_key(result: SearchResult, sort_by: str):
    trust = _infer_trust(result)
    if sort_by == "seeds":
        return (max(0, result.seeds), max(0, result.size), trust)
    if sort_by == "size":
        return (max(0, result.size), max(0, result.seeds), trust)
    if sort_by == "title":
        return (result.title or "").lower()
    if sort_by == "trust":
        return (trust, max(0, result.seeds), max(0, result.size))
    return _software_sort_key(result)


def _filter_and_sort_results(
    results: List[SearchResult],
    include_media: bool,
    platform: str,
    content_type: str,
    license_type: str,
    file_format: str,
    safety: str,
    sort_by: str,
    query: str = "",
) -> List[SearchResult]:
    baseline = _software_filter(results, include_media=include_media)
    platform_req = _csv_tokens(platform)
    content_req = _csv_tokens(content_type)
    license_req = _csv_tokens(license_type)
    format_req = _csv_tokens(file_format)
    safety_mode = (safety or "balanced").strip().lower()

    filtered: List[SearchResult] = []
    for result in baseline:
        pool = _result_token_pool(result)
        trust = _infer_trust(result)
        if safety_mode == "strict" and trust < 70:
            continue
        if not _matches_filter_group(platform_req, PLATFORM_TOKENS, pool):
            continue
        if not _matches_filter_group(content_req, CONTENT_TOKENS, pool):
            continue
        if not _matches_filter_group(license_req, LICENSE_TOKENS, pool):
            continue
        if not _matches_filter_group(format_req, FORMAT_TOKENS, pool):
            continue
        filtered.append(result)

    query_tokens = [t for t in re.split(r"\W+", (query or "").lower()) if len(t) >= 2]

    def query_boost(result: SearchResult) -> int:
        if not query_tokens:
            return 0
        title_low = (result.title or "").lower()
        link_low = (_pick_best_link(result) or "").lower()
        matched = sum(1 for tok in query_tokens if tok in title_low or tok in link_low)
        if matched <= 0:
            return 0
        # Favor complete token coverage, then partial coverage.
        full_coverage_bonus = 120 if matched >= len(query_tokens) else 0
        source_bonus = 20 if str(result.source or "").lower() == "opendirectory" else 0
        return full_coverage_bonus + (matched * 25) + source_bonus

    reverse = sort_by not in {"title"}
    if sort_by == "title":
        return sorted(filtered, key=lambda r: (_search_sort_key(r, sort_by), -query_boost(r)))
    return sorted(filtered, key=lambda r: (query_boost(r), _search_sort_key(r, sort_by)), reverse=reverse)


def _custom_link_to_result(link: Dict[str, Any], query: str) -> Optional[SearchResult]:
    if not link.get("enabled", True):
        return None
    title = str(link.get("title") or "").strip()
    url = str(link.get("url") or "").strip()
    if not title or not url:
        return None
    q = (query or "").strip().lower()
    tags = [str(x).strip().lower() for x in (link.get("tags") or []) if str(x).strip()]
    searchable = " ".join(
        [
            title.lower(),
            url.lower(),
            str(link.get("description") or "").lower(),
            " ".join(tags),
            " ".join([str(x).lower() for x in (link.get("platforms") or [])]),
        ]
    )
    if q and not all(token in searchable for token in q.split()):
        return None
    link_id = str(link.get("id") or "custom-link")
    provider = "Curated Links"
    if "opendirectory" in tags or "ftp" in tags or url.lower().startswith("ftp://"):
        provider = "OpenDirectory"
    return SearchResult(
        title=title,
        magnet=url,
        size=0,
        seeds=max(0, int(link.get("trust", 0) // 5)),
        leeches=0,
        source=provider,
        infohash=f"custom_{link_id}",
        category=str(link.get("contentType") or "software"),
        upload_date=None,
        link_candidates=[
            {
                "url": url,
                "quality": int(link.get("trust", 0)),
                "meta": {
                    "description": str(link.get("description") or ""),
                    "contentType": str(link.get("contentType") or "software"),
                    "licenseType": str(link.get("licenseType") or "unknown"),
                    "platforms": list(link.get("platforms") or []),
                    "formats": list(link.get("formats") or []),
                    "tags": list(link.get("tags") or []),
                    "trust": int(link.get("trust", 0)),
                },
            }
        ],
        aggregated_sources=["Curated Links"],
        link_quality=int(link.get("trust", 0)),
    )


class TransferCreateRequest(BaseModel):
    sourceResultId: str


class SourceSelectionRequest(BaseModel):
    sourceResultId: str


class ProviderToggleRequest(BaseModel):
    enabled: bool


class AuthBootstrapRequest(BaseModel):
    username: str
    password: str


class AuthLoginRequest(BaseModel):
    username: str
    password: str


class AuthSignupRequest(BaseModel):
    username: str
    password: str


class ProfileCreateRequest(BaseModel):
    name: str = ""


class ProfileSelectRequest(BaseModel):
    profileId: str


class ProfileThemeRequest(BaseModel):
    themeId: str


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    avatar: Optional[str] = None
    themeId: Optional[str] = None


class SearchJobCreateRequest(BaseModel):
    q: str
    page: int = 1
    per_page: int = 20
    include_media: bool = False
    include_custom: bool = True
    mode: str = "deep"  # "fast" | "deep"
    source_timeout_seconds: Optional[float] = None
    enabled_sources: Optional[List[str]] = None
    cache_bust: Optional[str] = None


class LinkSourceCreateRequest(BaseModel):
    id: Optional[str] = None
    title: str
    url: str
    description: Optional[str] = ""
    contentType: Optional[str] = "software"
    licenseType: Optional[str] = "unknown"
    platforms: Optional[List[str]] = None
    formats: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    trust: Optional[int] = 70
    enabled: Optional[bool] = True


class LinkSourceImportRequest(BaseModel):
    lines: List[str]
    contentType: Optional[str] = "software"
    licenseType: Optional[str] = "unknown"
    platforms: Optional[List[str]] = None
    formats: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    trust: Optional[int] = 65


class LinkSourceBulkToggleRequest(BaseModel):
    enabled: bool


class SearchResultRegistry:
    """Tracks search results so a frontend can enqueue by result id."""

    def __init__(self):
        self._items: Dict[str, SearchResult] = {}
        self._lock = RLock()

    def upsert_many(self, entries: Dict[str, SearchResult]) -> None:
        with self._lock:
            self._items.update(entries)

    def get(self, source_result_id: str) -> Optional[SearchResult]:
        with self._lock:
            return self._items.get(source_result_id)

    def entries(self):
        with self._lock:
            return list(self._items.items())


def _pick_best_link(result: SearchResult) -> str:
    candidates = sorted(result.link_candidates or [], key=lambda c: int(c.get("quality", 0)), reverse=True)
    if candidates:
        return str(candidates[0].get("url") or "").strip()
    return (result.magnet or "").strip()


def _provider_id(source_name: str) -> str:
    return source_name.lower().replace(" ", "-")


def _size_bytes_to_text(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    amount = float(max(value, 0))
    for unit in units:
        if amount < 1024.0:
            return f"{amount:.2f} {unit}"
        amount /= 1024.0
    return f"{amount:.2f} PB"


def _software_score(title: str) -> int:
    low = (title or "").lower()
    score = 0
    for token in SOFTWARE_HINTS:
        if token in low:
            score += 8
    if "windows" in low or "win" in low:
        score += 6
    if "mac" in low or "macos" in low or "osx" in low or "dmg" in low:
        score += 6
    if "vst" in low or "plugin" in low:
        score += 10
    return score


def _media_noise_score(title: str) -> int:
    low = (title or "").lower()
    score = 0
    for token in MEDIA_HINTS:
        if token in low:
            score += 12
    return score


def _software_sort_key(result: SearchResult):
    title = result.title or ""
    software = _software_score(title)
    media = _media_noise_score(title)
    torrent_bonus = 4 if _pick_best_link(result).lower().startswith("magnet:") else 0
    quality = int(getattr(result, "link_quality", 0) or 0)
    return (
        software - media,
        torrent_bonus,
        max(0, result.seeds),
        quality,
        max(0, result.size),
    )


def _software_filter(results: List[SearchResult], include_media: bool) -> List[SearchResult]:
    if include_media:
        return sorted(results, key=_software_sort_key, reverse=True)
    filtered = [r for r in results if (_software_score(r.title) > 0) or (_media_noise_score(r.title) < 12)]
    return sorted(filtered, key=_software_sort_key, reverse=True)


def _serialize_search_results(query: str, results: List[SearchResult]) -> Dict:
    groups: List[Dict] = []
    registry_updates: Dict[str, SearchResult] = {}

    for index, result in enumerate(results, start=1):
        item_id = result.infohash or f"item_{index}"
        source_result_id = f"src_{item_id}_{index}"
        primary_url = _pick_best_link(result)
        protocol = "torrent" if primary_url.lower().startswith("magnet:") else "http"
        relevance = max(0, _software_score(result.title) - _media_noise_score(result.title))
        meta = _result_meta(result)
        trust = _infer_trust(result)

        registry_copy = SearchResult(
            title=result.title,
            magnet=primary_url,
            size=result.size,
            seeds=result.seeds,
            leeches=result.leeches,
            source=result.source,
            infohash=result.infohash,
            category=result.category,
            upload_date=result.upload_date,
            link_candidates=list(result.link_candidates or []),
            aggregated_sources=list(result.aggregated_sources or []),
            link_quality=result.link_quality,
        )
        registry_updates[source_result_id] = registry_copy

        groups.append(
            {
                "item": {
                    "id": item_id,
                    "title": result.title,
                    "aliases": [],
                    "category": result.category or "software",
                    "updatedAt": _utc_now_iso(),
                },
                "sources": [
                    {
                        "id": source_result_id,
                        "itemId": item_id,
                        "protocol": protocol,
                        "provider": result.source,
                        "sizeBytes": int(result.size),
                        "seeders": int(result.seeds),
                        "peers": int(result.leeches),
                        "publishedAt": _utc_now_iso(),
                        "trustScore": trust,
                        "qualityLabel": "stable" if result.seeds >= 25 else "unknown",
                        "raw": {
                            "title": result.title,
                            "linkCandidates": list(result.link_candidates or []),
                            "aggregatedSources": list(result.aggregated_sources or []),
                            "infohash": result.infohash,
                            "description": str(meta.get("description") or ""),
                            "contentType": str(meta.get("contentType") or result.category or "software"),
                            "licenseType": str(meta.get("licenseType") or "unknown"),
                            "platforms": list(meta.get("platforms") or []),
                            "formats": list(meta.get("formats") or []),
                            "tags": list(meta.get("tags") or []),
                            "softwareScore": _software_score(result.title),
                            "mediaNoise": _media_noise_score(result.title),
                            "relevance": relevance,
                        },
                    }
                ],
            }
        )

    return {"query": query, "groups": groups, "count": len(groups), "registry_updates": registry_updates}


def _serialize_transfer(job: DownloadJob, source_result_id: Optional[str]) -> Dict:
    return {
        "id": job.job_id,
        "sourceResultId": source_result_id or "",
        "status": _to_transfer_status(job.status),
        "progress": int(job.progress),
        "speed": job.speed_formatted if job.speed_kbps > 0 else None,
        "error": job.error,
        "createdAt": datetime.fromtimestamp(job.start_time, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "updatedAt": datetime.fromtimestamp(job.end_time or job.start_time, tz=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
    }


def _provider_name_from_id(runtime: PluggyRuntime, provider_id: str) -> Optional[str]:
    for name in runtime.source_manager.get_source_names():
        if _provider_id(name) == provider_id:
            return name
    return None


def create_app(runtime: Optional[PluggyRuntime] = None) -> FastAPI:
    runtime = runtime or build_runtime()
    registry = SearchResultRegistry()
    legacy_links_path = Path(__file__).resolve().parents[2] / ".reports" / "custom-link-sources.json"
    links_path = runtime.settings.settings_dir / "custom-link-sources.json"
    if legacy_links_path.exists() and not links_path.exists():
        try:
            links_path.parent.mkdir(parents=True, exist_ok=True)
            links_path.write_text(legacy_links_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    links_store = CustomLinkStore(links_path)
    transfer_to_source_result: Dict[str, str] = {}
    home_cache: Dict[str, Any] = {"updated": 0.0, "payload": None}
    home_cache_lock = RLock()
    home_build_lock = RLock()
    home_build_inflight = {"full": False}
    search_jobs_lock = RLock()
    search_jobs: Dict[str, Dict[str, Any]] = {}
    audit_log: deque[Dict[str, Any]] = deque(maxlen=500)
    audit_lock = RLock()

    def _read_cookie(request: Request, name: str) -> str:
        raw = request.headers.get("cookie") or ""
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        for part in parts:
            if part.startswith(f"{name}="):
                return part.split("=", 1)[1].strip()
        return ""

    def _secure_cookie(request: Optional[Request] = None) -> bool:
        # Hosted deployments should set secure cookies.
        # - Local contained/dev builds can keep this false.
        env = str(os.environ.get("PLUGGY_SECURE_COOKIES", "") or "").strip().lower()
        if env in {"1", "true", "yes", "on"}:
            return True
        if env in {"0", "false", "no", "off"}:
            return False
        if request is None:
            return False
        proto = str(request.headers.get("x-forwarded-proto") or "").strip().lower()
        return proto == "https"

    def _allow_signup() -> bool:
        env = str(os.environ.get("PLUGGY_ALLOW_SIGNUP", "") or "").strip().lower()
        if env in {"0", "false", "no", "off"}:
            return False
        return True

    def _allow_shutdown() -> bool:
        env = str(os.environ.get("PLUGGY_ALLOW_SHUTDOWN", "") or "").strip().lower()
        if env in {"0", "false", "no", "off"}:
            return False
        return True

    def _require_user(request: Request):
        # Context is set by middleware; enforce at handler boundary too.
        ctx = runtime  # keep closure reference
        sess = None
        # session context stored via contextvars; only check presence.
        from ..core.request_context import get_session

        current = get_session()
        if not current.user_id:
            raise HTTPException(status_code=401, detail="Login required.")
        return current

    async def session_context_middleware(request: Request, call_next):
        token = _read_cookie(request, "pluggy_session")
        ctx = SessionContext()
        if token:
            session = runtime.store.get_session(token)
            if session:
                user, profile_id = session
                ctx = SessionContext(
                    user_id=user.id,
                    username=user.username,
                    role=user.role or "user",
                    profile_id=profile_id,
                )
        set_session(ctx)

        path = request.url.path or ""
        # Allow health + auth endpoints without session.
        if path == "/health" or path.startswith("/api/auth/"):
            return await call_next(request)
        # Enforce auth for all other API endpoints.
        if path.startswith("/api/") and not ctx.user_id:
            return JSONResponse(
                {"error": {"code": "UNAUTHORIZED", "message": "Login required"}},
                status_code=401,
            )
        # Enforce profile selection for API usage; allow profile management endpoints.
        if path.startswith("/api/") and ctx.user_id and not ctx.profile_id:
            if path == "/api/profiles" or path.startswith("/api/profiles/"):
                return await call_next(request)
            return JSONResponse(
                {
                    "error": {
                        "code": "PROFILE_REQUIRED",
                        "message": "Select a profile to continue.",
                    }
                },
                status_code=409,
            )
        return await call_next(request)

    def record_audit(event: str, detail: Dict[str, Any]) -> None:
        with audit_lock:
            audit_log.appendleft(
                {
                    "at": _utc_now_iso(),
                    "event": event,
                    "detail": detail,
                }
            )

    app = FastAPI(title="Pluggy API", version="1.3.0")
    app.middleware("http")(session_context_middleware)

    @app.get("/health")
    def health() -> Dict:
        return {"ok": True, "time": _utc_now_iso()}

    @app.get("/api/auth/status")
    def auth_status(request: Request) -> Dict[str, Any]:
        token = _read_cookie(request, "pluggy_session")
        session = runtime.store.get_session(token) if token else None
        needs_bootstrap = runtime.store.count_users() == 0
        if not session:
            return {
                "needsBootstrap": needs_bootstrap,
                "authenticated": False,
                "username": None,
                "role": None,
                "profileId": None,
                "profiles": [],
            }
        user, profile_id = session
        profiles = runtime.store.list_profiles(user.id)
        return {
            "needsBootstrap": False,
            "authenticated": True,
            "userId": user.id,
            "username": user.username,
            "role": user.role,
            "profileId": profile_id,
            "profiles": [
                {"id": p.id, "name": p.name, "avatar": p.avatar, "themeId": p.theme_id}
                for p in profiles
            ],
        }

    @app.post("/api/auth/bootstrap")
    def auth_bootstrap(request: Request, body: AuthBootstrapRequest) -> Response:
        if runtime.store.count_users() != 0:
            raise HTTPException(status_code=409, detail="Bootstrap already completed.")
        user = runtime.store.create_user(body.username, body.password, role="admin")
        token = runtime.store.create_session(user.id)
        resp = JSONResponse(
            {
                "ok": True,
                "authenticated": True,
                "username": user.username,
                "role": user.role,
            }
        )
        resp.set_cookie(
            "pluggy_session",
            token,
            httponly=True,
            samesite="lax",
            secure=_secure_cookie(request),
            max_age=60 * 60 * 24 * 7,
            path="/",
        )
        return resp

    @app.post("/api/auth/login")
    def auth_login(request: Request, body: AuthLoginRequest) -> Response:
        user = runtime.store.authenticate(body.username, body.password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials.")
        token = runtime.store.create_session(user.id)
        resp = JSONResponse(
            {
                "ok": True,
                "authenticated": True,
                "username": user.username,
                "role": user.role,
            }
        )
        resp.set_cookie(
            "pluggy_session",
            token,
            httponly=True,
            samesite="lax",
            secure=_secure_cookie(request),
            max_age=60 * 60 * 24 * 7,
            path="/",
        )
        return resp

    @app.post("/api/auth/signup")
    def auth_signup(request: Request, body: AuthSignupRequest) -> Response:
        # Local-first signup. If you want to disable this for hosted deployments,
        # gate it behind an env var or setting later.
        if not _allow_signup():
            raise HTTPException(status_code=403, detail="Signups are disabled on this server.")
        try:
            user = runtime.store.create_user(body.username, body.password, role="user")
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Username already exists.")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        token = runtime.store.create_session(user.id)
        resp = JSONResponse(
            {
                "ok": True,
                "authenticated": True,
                "username": user.username,
                "role": user.role,
            }
        )
        resp.set_cookie(
            "pluggy_session",
            token,
            httponly=True,
            samesite="lax",
            secure=_secure_cookie(request),
            max_age=60 * 60 * 24 * 7,
            path="/",
        )
        return resp

    @app.post("/api/auth/logout")
    def auth_logout(request: Request) -> Response:
        token = _read_cookie(request, "pluggy_session")
        if token:
            runtime.store.delete_session(token)
        resp = JSONResponse({"ok": True})
        resp.set_cookie("pluggy_session", "", httponly=True, samesite="lax", secure=_secure_cookie(request), max_age=0, path="/")
        return resp

    @app.get("/api/profiles")
    def profiles_list(request: Request) -> Dict[str, Any]:
        ctx = _require_user(request)
        profiles = runtime.store.list_profiles(int(ctx.user_id or 0))
        return {"profiles": [{"id": p.id, "name": p.name, "avatar": p.avatar, "themeId": p.theme_id} for p in profiles]}

    @app.post("/api/profiles")
    def profiles_create(request: Request, body: ProfileCreateRequest) -> Dict[str, Any]:
        ctx = _require_user(request)
        profile = runtime.store.create_profile(int(ctx.user_id or 0), body.name)
        # Initialize profile settings on creation so first run is consistent.
        runtime.store.set_profile_settings(profile.id, runtime.settings._ensure_required_source_urls_on(dict(runtime.settings.DEFAULT_SETTINGS)))
        return {"ok": True, "profile": {"id": profile.id, "name": profile.name, "avatar": profile.avatar, "themeId": profile.theme_id}}

    @app.post("/api/profiles/select")
    def profiles_select(request: Request, body: ProfileSelectRequest) -> Dict[str, Any]:
        token = _read_cookie(request, "pluggy_session")
        if not token:
            raise HTTPException(status_code=401, detail="Login required.")
        session = runtime.store.get_session(token)
        if not session:
            raise HTTPException(status_code=401, detail="Session expired.")
        user, _ = session
        profile = runtime.store.get_profile(body.profileId)
        if not profile or profile.user_id != user.id:
            raise HTTPException(status_code=404, detail="Profile not found.")
        runtime.store.set_session_profile(token, profile.id)
        return {"ok": True, "profileId": profile.id}

    @app.post("/api/profiles/theme")
    def profiles_set_theme(request: Request, body: ProfileThemeRequest) -> Dict[str, Any]:
        ctx = _require_user(request)
        if not ctx.profile_id:
            raise HTTPException(status_code=409, detail="Select a profile first.")
        runtime.store.set_profile_theme(str(ctx.profile_id), str(body.themeId or ""))
        return {"ok": True, "profileId": ctx.profile_id, "themeId": str(body.themeId or "")}

    @app.patch("/api/profiles/{profile_id}")
    def profiles_update(request: Request, profile_id: str, body: ProfileUpdateRequest) -> Dict[str, Any]:
        ctx = _require_user(request)
        profile = runtime.store.get_profile(profile_id)
        if not profile or profile.user_id != int(ctx.user_id or 0):
            raise HTTPException(status_code=404, detail="Profile not found.")

        name = None
        if body.name is not None:
            safe = str(body.name or "").strip()
            if len(safe) < 2:
                raise HTTPException(status_code=400, detail="Profile name must be at least 2 characters.")
            if len(safe) > 32:
                safe = safe[:32]
            name = safe

        avatar = None
        if body.avatar is not None:
            raw = str(body.avatar or "")
            if raw and not raw.startswith("data:image/"):
                raise HTTPException(status_code=400, detail="Avatar must be a data:image/* URL.")
            # Keep avatars small (base64 URLs can be large); this is plenty for a 256px PNG.
            if len(raw) > 320_000:
                raise HTTPException(status_code=413, detail="Avatar too large.")
            avatar = raw

        theme_id = None
        if body.themeId is not None:
            theme_id = str(body.themeId or "").strip()

        runtime.store.update_profile(profile_id, name=name, avatar=avatar, theme_id=theme_id)
        updated = runtime.store.get_profile(profile_id)
        return {"ok": True, "profile": {"id": updated.id, "name": updated.name, "avatar": updated.avatar, "themeId": updated.theme_id}}

    @app.delete("/api/profiles/{profile_id}")
    def profiles_delete(request: Request, profile_id: str) -> Dict[str, Any]:
        ctx = _require_user(request)
        profile = runtime.store.get_profile(profile_id)
        if not profile or profile.user_id != int(ctx.user_id or 0):
            raise HTTPException(status_code=404, detail="Profile not found.")
        runtime.store.delete_profile(profile_id)
        record_audit("profile.deleted", {"id": profile_id})
        return {"ok": True}

    @app.get("/api/session")
    def api_session() -> Dict:
        user = {"id": "local-user", "name": "local-user"}
        if runtime.realdebrid.is_authenticated():
            try:
                rd_user = runtime.realdebrid.get_user_info()
                user = {
                    "id": str(rd_user.get("id", "local-user")),
                    "name": str(rd_user.get("username", "local-user")),
                }
            except Exception:
                pass
        return {
            "user": user,
            "rdConnected": runtime.realdebrid.is_authenticated(),
        }

    @app.post("/api/session/rd/connect")
    def connect_rd() -> Dict:
        try:
            payload = runtime.realdebrid.start_device_auth()
            record_audit("rd.connect.started", {"ok": True})
            return {
                "ok": True,
                "rdConnected": runtime.realdebrid.is_authenticated(),
                "status": "pending",
                "device": {
                    "userCode": payload.get("user_code"),
                    "verificationUrl": payload.get("verification_url"),
                    "expiresIn": payload.get("expires_in"),
                    "deviceCode": payload.get("device_code"),
                },
            }
        except Exception as exc:
            record_audit("rd.connect.failed", {"ok": False, "error": str(exc)})
            raise HTTPException(status_code=502, detail=f"RealDebrid auth failed: {exc}") from exc

    @app.get("/api/session/rd/status")
    def rd_status(poll: bool = Query(False)) -> Dict:
        connected = runtime.realdebrid.is_authenticated()
        rd_device_code = str(runtime.settings.get("rd_device_code", "") or "").strip()
        payload: Dict[str, Any] = {
            "rdConnected": connected,
            "status": "connected" if connected else ("pending" if rd_device_code else "disconnected"),
        }
        if connected:
            try:
                payload["account"] = runtime.realdebrid.get_user_info()
            except Exception:
                pass
            return payload

        if poll and rd_device_code:
            try:
                check = runtime.realdebrid.check_device_auth_now()
                payload["status"] = check.get("status", payload["status"])
                payload["message"] = check.get("message", "")
                payload["rdConnected"] = runtime.realdebrid.is_authenticated()
                if payload["rdConnected"]:
                    payload["status"] = "connected"
            except Exception as exc:
                payload["status"] = "failed"
                payload["message"] = str(exc)
        return payload

    @app.post("/api/session/rd/check")
    def rd_check() -> Dict:
        check = runtime.realdebrid.check_device_auth_now()
        record_audit("rd.check", {"status": check.get("status", "failed"), "message": check.get("message", "")})
        return {
            "ok": True,
            "status": check.get("status", "failed"),
            "message": check.get("message", ""),
            "rdConnected": runtime.realdebrid.is_authenticated(),
        }

    @app.post("/api/session/rd/logout")
    def rd_logout() -> Dict:
        runtime.realdebrid.stop_polling()
        runtime.realdebrid.logout()
        runtime.settings.set("rd_device_code", "")
        record_audit("rd.logout", {"ok": True})
        return {"ok": True, "rdConnected": False}

    @app.get("/api/search")
    def search(
        q: str = Query("", min_length=1),
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100),
        min_seeds: int = Query(0, ge=0),
        profile: str = Query("software"),
        include_media: bool = Query(False),
        platform: str = Query(""),
        content_type: str = Query(""),
        license_type: str = Query(""),
        file_format: str = Query(""),
        safety: str = Query("balanced"),
        sort_by: str = Query("relevance"),
        include_custom: bool = Query(True),
        wait_all_sources: bool = Query(True),
        source_timeout_seconds: float = Query(16.0, ge=3.0, le=60.0),
        cache_bust: str = Query(""),
    ) -> Dict:
        filters = {
            "min_seeds": min_seeds,
            "size_min_gb": 0,
            "size_max_gb": 999,
            "wait_for_all_sources": wait_all_sources,
            "source_timeout_seconds": source_timeout_seconds,
        }
        if cache_bust.strip():
            filters["cache_bust"] = cache_bust.strip()
        # Build a stable result set first, then apply pagination once for all sources (including curated links).
        fetch_limit = max(100, min(500, page * per_page * 3))
        results = runtime.source_manager.search(q, page=1, per_page=fetch_limit, filters=filters)
        # OD reliability guard: run a dedicated OD pass when primary sweep returns nothing/too little.
        if runtime.settings.get("open_directory_enabled", True):
            low_signal = len(results) < 8
            od_missing = not any((getattr(r, "source", "") or "").lower() == "opendirectory" for r in results)
            if low_signal or od_missing:
                od_filters = dict(filters)
                od_filters["enabled_sources"] = ["OpenDirectory"]
                od_filters["source_timeout_seconds"] = max(float(source_timeout_seconds), 18.0)
                od_results = runtime.source_manager.search(q, page=1, per_page=fetch_limit, filters=od_filters)
                # Hard fallback: query OD source directly when manager-level pass is still empty.
                if not od_results:
                    direct_od_source = None
                    with runtime.source_manager._lock:
                        direct_od_source = runtime.source_manager._sources.get("OpenDirectory")
                    if direct_od_source is not None:
                        try:
                            direct_timeout = max(4.0, min(10.0, float(source_timeout_seconds)))
                            with ThreadPoolExecutor(max_workers=1) as direct_pool:
                                direct_future = direct_pool.submit(direct_od_source.search, q, 1)
                                od_results = direct_future.result(timeout=direct_timeout)
                        except FutureTimeoutError:
                            od_results = []
                        except Exception:
                            od_results = []
                if od_results:
                    seen = {
                        ((r.infohash or "").lower(), (r.magnet or "").lower(), (r.title or "").lower())
                        for r in results
                    }
                    for od_row in od_results:
                        key = (
                            (od_row.infohash or "").lower(),
                            (od_row.magnet or "").lower(),
                            (od_row.title or "").lower(),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append(od_row)
        if include_custom:
            for link in links_store.list(enabled_only=True):
                maybe = _custom_link_to_result(link, q)
                if maybe:
                    results.append(maybe)

        if profile in {"software", "pc-games", "roms-homebrew"}:
            results = _filter_and_sort_results(
                results,
                include_media=include_media,
                platform=platform,
                content_type=content_type,
                license_type=license_type,
                file_format=file_format,
                safety=safety,
                sort_by=sort_by,
                query=q,
            )

        total_results = len(results)
        start_idx = max(0, (page - 1) * per_page)
        end_idx = start_idx + per_page
        page_results = results[start_idx:end_idx]

        payload = _serialize_search_results(q, page_results)
        registry.upsert_many(payload.pop("registry_updates"))
        payload["page"] = page
        payload["perPage"] = per_page
        payload["hasMore"] = end_idx < total_results
        payload["waitAllSources"] = wait_all_sources
        return payload

    def _job_snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": job["id"],
            "query": job["query"],
            "status": job["status"],
            "phase": job["phase"],
            "mode": job["mode"],
            "createdAt": job["createdAt"],
            "updatedAt": job["updatedAt"],
            "message": job.get("message") or "",
            "partial": bool(job.get("partial", False)),
            "progress": job.get("progress") or {},
            "timings": job.get("timings") or {},
            "sources": job.get("sources") or {},
            "result": job.get("result") or {},
        }

    def _start_search_job(body: SearchJobCreateRequest) -> Dict[str, Any]:
        q = (body.q or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="q is required")
        page = max(1, int(body.page or 1))
        per_page = max(1, min(100, int(body.per_page or 20)))

        mode = (body.mode or "deep").strip().lower()
        if mode not in {"fast", "deep"}:
            mode = "deep"

        if body.source_timeout_seconds is not None:
            source_timeout_seconds = float(body.source_timeout_seconds)
        else:
            source_timeout_seconds = 10.0 if mode == "fast" else 20.0
        source_timeout_seconds = float(max(3.0, min(60.0, source_timeout_seconds)))

        fetch_limit = max(120, min(600, page * per_page * 3))

        enabled_sources = body.enabled_sources
        if not enabled_sources and mode == "fast":
            enabled_sources = ["OpenDirectory", "HTTP", "Prowlarr", "RealDebrid Library"]

        job_id = f"sj_{uuid.uuid4().hex[:12]}"
        now = _utc_now_iso()
        job: Dict[str, Any] = {
            "id": job_id,
            "query": q,
            "status": "running",
            "phase": "init",
            "mode": mode,
            "createdAt": now,
            "updatedAt": now,
            "message": "",
            "partial": True,
            "cancelRequested": False,
            "progress": {"totalSources": 0, "completedSources": 0, "firstResultAt": None},
            "timings": {"wallMs": 0, "cpuMs": 0, "netWaitMs": 0, "startedAtMono": 0.0, "startedCpu": 0.0},
            "sources": {},
            "result": {"groups": [], "count": 0, "page": page, "perPage": per_page, "hasMore": False},
            "_internal": {
                "page": page,
                "per_page": per_page,
                "fetch_limit": fetch_limit,
                "source_timeout_seconds": source_timeout_seconds,
                "include_media": bool(body.include_media),
                "include_custom": bool(body.include_custom),
                "enabled_sources": enabled_sources,
                "cache_bust": (body.cache_bust or "").strip(),
                # executor is created after we know how many sources will run
                "executor": None,
            },
        }

        with search_jobs_lock:
            # GC old jobs (bounded memory).
            ttl_seconds = 45 * 60
            max_jobs = 80
            now_mono = monotonic()
            to_delete = []
            if len(search_jobs) >= max_jobs:
                # delete oldest first
                ordered = sorted(search_jobs.values(), key=lambda j: j.get("timings", {}).get("startedAtMono", 0))
                for stale in ordered[: max(0, len(search_jobs) - max_jobs + 1)]:
                    to_delete.append(stale.get("id"))
            for jid, existing in list(search_jobs.items()):
                started = float(existing.get("timings", {}).get("startedAtMono", 0) or 0)
                if started and (now_mono - started) > ttl_seconds:
                    to_delete.append(jid)
            for jid in set([x for x in to_delete if x]):
                search_jobs.pop(jid, None)

            search_jobs[job_id] = job

        # Capture session context so background threads keep profile/user scope.
        ctx = get_request_session()
        ctx_snapshot = SessionContext(
            user_id=ctx.user_id,
            username=ctx.username,
            role=ctx.role or "user",
            profile_id=ctx.profile_id,
        )

        def runner() -> None:
            set_session(ctx_snapshot)
            started_mono = monotonic()
            started_cpu = time.process_time()
            with search_jobs_lock:
                job["timings"]["startedAtMono"] = started_mono
                job["timings"]["startedCpu"] = started_cpu
            try:
                internal = job["_internal"]
                enabled = runtime.source_manager.get_enabled_sources()
                if internal["enabled_sources"]:
                    allowed = set(str(x) for x in internal["enabled_sources"])
                    enabled = [s for s in enabled if s in allowed]
                enabled = sorted(enabled, key=runtime.source_manager._source_routing_score, reverse=True)
                internal["executor"] = ThreadPoolExecutor(max_workers=max(2, min(8, len(enabled) or 2)))

                with search_jobs_lock:
                    job["phase"] = "querying"
                    job["progress"]["totalSources"] = len(enabled)
                    job["updatedAt"] = _utc_now_iso()
                    for name in enabled:
                        job["sources"][name] = {"status": "pending", "warning": "", "elapsedMs": 0, "attempts": 0}

                futures: Dict[Any, str] = {}
                for source_name in enabled:
                    if job["cancelRequested"]:
                        break
                    reason = runtime.source_manager._source_block_reason(source_name)
                    if reason:
                        with search_jobs_lock:
                            job["sources"][source_name]["status"] = "skipped"
                            job["sources"][source_name]["warning"] = reason
                            job["progress"]["completedSources"] += 1
                            job["updatedAt"] = _utc_now_iso()
                        continue
                    with runtime.source_manager._lock:
                        source_obj = runtime.source_manager._sources.get(source_name)
                    if not source_obj:
                        continue
                    with search_jobs_lock:
                        job["sources"][source_name]["status"] = "running"
                        job["updatedAt"] = _utc_now_iso()
                    def _call_safe_search(obj=source_obj, query=q):
                        set_session(ctx_snapshot)
                        return runtime.source_manager._safe_search(obj, query, 1)

                    fut = internal["executor"].submit(_call_safe_search)
                    futures[fut] = source_name

                all_results: List[SearchResult] = []
                deadline = started_mono + max(3.0, float(internal["source_timeout_seconds"]))
                pending = set(futures.keys())

                while pending and not job["cancelRequested"]:
                    now_m = monotonic()
                    if now_m >= deadline:
                        break
                    done, not_done = wait(
                        pending, timeout=min(0.25, max(0.0, deadline - now_m)), return_when=FIRST_COMPLETED
                    )
                    pending = set(not_done)
                    for fut in done:
                        source_name = futures.get(fut, "source")
                        try:
                            results, warning, attempts, latency_ms, ok = fut.result()
                        except Exception as exc:
                            results, warning, attempts, latency_ms, ok = [], str(exc), 1, 0.0, False
                        if results:
                            all_results.extend(results)
                        runtime.source_manager._record_source_outcome(
                            source_name=source_name,
                            ok=bool(ok),
                            error_message=str(warning or ""),
                            latency_ms=float(latency_ms or 0.0),
                            attempts=int(attempts or 1),
                        )
                        with search_jobs_lock:
                            st = job["sources"].get(source_name, {})
                            st["status"] = "done" if ok else "error"
                            st["warning"] = str(warning or "")
                            st["elapsedMs"] = int(latency_ms or 0.0)
                            st["attempts"] = int(attempts or 1)
                            job["sources"][source_name] = st
                            job["progress"]["completedSources"] += 1

                            unique = runtime.source_manager._deduplicate(all_results)
                            unified = runtime.source_manager._aggregate_results(unique)
                            ranked = _software_filter(unified, include_media=bool(internal["include_media"]))

                            start_idx = max(0, (internal["page"] - 1) * internal["per_page"])
                            end_idx = start_idx + internal["per_page"]
                            page_results = ranked[start_idx:end_idx]
                            payload = _serialize_search_results(q, page_results)
                            registry.upsert_many(payload.pop("registry_updates"))
                            total_results = len(ranked)
                            job["result"] = {
                                "groups": payload.get("groups", []),
                                "count": payload.get("count", 0),
                                "page": internal["page"],
                                "perPage": internal["per_page"],
                                "hasMore": end_idx < total_results,
                            }
                            if job["progress"]["firstResultAt"] is None and job["result"]["count"] > 0:
                                job["progress"]["firstResultAt"] = _utc_now_iso()
                            job["phase"] = "querying"
                            job["partial"] = True
                            job["updatedAt"] = _utc_now_iso()

                for fut in list(pending):
                    fut.cancel()
                    source_name = futures.get(fut, "source")
                    with search_jobs_lock:
                        st = job["sources"].get(source_name, {})
                        if st.get("status") in {"done", "error"}:
                            continue
                        st["status"] = "cancelled" if job["cancelRequested"] else "timeout"
                        st["warning"] = (
                            "Cancelled by user."
                            if job["cancelRequested"]
                            else f"Timed out after {int(internal['source_timeout_seconds'])}s."
                        )
                        job["sources"][source_name] = st
                        job["progress"]["completedSources"] += 1
                        job["updatedAt"] = _utc_now_iso()

                with search_jobs_lock:
                    job["phase"] = "ranking"
                    job["updatedAt"] = _utc_now_iso()

                unique = runtime.source_manager._deduplicate(all_results)
                unified = runtime.source_manager._aggregate_results(unique)
                if internal["include_custom"]:
                    for link in links_store.list(enabled_only=True):
                        maybe = _custom_link_to_result(link, q)
                        if maybe:
                            unified.append(maybe)
                ranked = _software_filter(unified, include_media=bool(internal["include_media"]))

                start_idx = max(0, (internal["page"] - 1) * internal["per_page"])
                end_idx = start_idx + internal["per_page"]
                page_results = ranked[start_idx:end_idx]
                payload = _serialize_search_results(q, page_results)
                registry.upsert_many(payload.pop("registry_updates"))
                total_results = len(ranked)

                with search_jobs_lock:
                    job["result"] = {
                        "groups": payload.get("groups", []),
                        "count": payload.get("count", 0),
                        "page": internal["page"],
                        "perPage": internal["per_page"],
                        "hasMore": end_idx < total_results,
                    }
                    job["timings"]["wallMs"] = int((monotonic() - started_mono) * 1000)
                    job["timings"]["cpuMs"] = int(max(0.0, (time.process_time() - started_cpu)) * 1000)
                    job["timings"]["netWaitMs"] = int(max(0, job["timings"]["wallMs"] - job["timings"]["cpuMs"]))
                    job["status"] = "cancelled" if job["cancelRequested"] else "done"
                    job["phase"] = "done"
                    job["partial"] = False
                    job["updatedAt"] = _utc_now_iso()
            except Exception as exc:
                with search_jobs_lock:
                    job["status"] = "error"
                    job["phase"] = "done"
                    job["message"] = str(exc)
                    job["updatedAt"] = _utc_now_iso()
            finally:
                try:
                    executor = job["_internal"].get("executor")
                    if executor is not None:
                        executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass

        threading.Thread(target=runner, daemon=True).start()
        return {"jobId": job_id}

    @app.post("/api/search/jobs")
    def create_search_job(body: SearchJobCreateRequest) -> Dict[str, Any]:
        return _start_search_job(body)

    @app.get("/api/search/jobs/{job_id}")
    def get_search_job(job_id: str) -> Dict[str, Any]:
        with search_jobs_lock:
            job = search_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Search job not found.")
        return _job_snapshot(job)

    @app.post("/api/search/jobs/{job_id}/cancel")
    def cancel_search_job(job_id: str) -> Dict[str, Any]:
        with search_jobs_lock:
            job = search_jobs.get(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Search job not found.")
            job["cancelRequested"] = True
            job["status"] = "cancelling"
            job["message"] = "Cancelling…"
            job["updatedAt"] = _utc_now_iso()
        return {"ok": True}

    @app.get("/api/link-sources")
    def get_link_sources(enabled_only: bool = Query(False), export: bool = Query(False)) -> Dict:
        links = links_store.list(enabled_only=enabled_only)
        if export:
            return {"ok": True, "exportedAt": _utc_now_iso(), "count": len(links), "links": links}
        return {"links": links}

    @app.post("/api/link-sources")
    def create_or_update_link_source(body: LinkSourceCreateRequest) -> Dict:
        try:
            link = links_store.upsert(body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_audit("link-source.upsert", {"id": link.get("id"), "title": link.get("title")})
        return {"ok": True, "link": link}

    @app.post("/api/link-sources/import")
    def import_link_sources(body: LinkSourceImportRequest) -> Dict:
        defaults = body.model_dump()
        lines = defaults.pop("lines", [])
        try:
            created = links_store.import_lines(lines=lines, defaults=defaults)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record_audit("link-source.import", {"count": len(created)})
        return {"ok": True, "created": created, "count": len(created)}

    @app.post("/api/link-sources/bulk-toggle")
    def bulk_toggle_link_sources(body: LinkSourceBulkToggleRequest) -> Dict:
        count = links_store.set_enabled_for_all(body.enabled)
        record_audit("link-source.bulk-toggle", {"enabled": body.enabled, "count": count})
        return {"ok": True, "count": count, "enabled": body.enabled}

    @app.get("/api/link-sources/suggestions")
    def get_link_source_suggestions() -> Dict:
        links = links_store.list(enabled_only=False)
        tags = sorted({str(tag).lower() for link in links for tag in (link.get("tags") or []) if str(tag).strip()})
        platforms = sorted(
            {str(platform).lower() for link in links for platform in (link.get("platforms") or []) if str(platform).strip()}
        )
        return {"tags": tags[:60], "platforms": platforms[:40]}

    @app.delete("/api/link-sources/{link_id}")
    def delete_link_source(link_id: str) -> Dict:
        removed = links_store.delete(link_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Link source not found.")
        record_audit("link-source.delete", {"id": link_id})
        return {"ok": True}

    @app.get("/api/home")
    def home(force_refresh: bool = Query(False)) -> Dict:
        ctx = get_request_session()
        ctx_snapshot = SessionContext(
            user_id=ctx.user_id,
            username=ctx.username,
            role=ctx.role or "user",
            profile_id=ctx.profile_id,
        )
        with home_cache_lock:
            if not force_refresh and home_cache["payload"] and (monotonic() - home_cache["updated"]) < 300:
                return home_cache["payload"]

        rails_config = [
            ("vst", "Top VST Torrents", "vst plugin"),
            ("windows", "Windows Downloads", "windows software"),
            ("mac", "macOS Downloads", "macos dmg"),
            ("audio", "Audio Production Tools", "ableton plugin torrent"),
        ]
        providers_payload = providers()
        providers_online = len([p for p in providers_payload["providers"] if p["health"] != "offline"])

        def build_rails(
            config: List[tuple[str, str, str]],
            enabled_sources: Optional[List[str]],
            timeout_seconds: float,
        ) -> List[Dict[str, Any]]:
            def build_one(rail_id: str, rail_title: str, query: str) -> Dict[str, Any]:
                set_session(ctx_snapshot)
                filters: Dict[str, Any] = {
                    "min_seeds": 0,
                    "size_min_gb": 0,
                    "size_max_gb": 999,
                    "wait_for_all_sources": False,
                    "source_timeout_seconds": float(timeout_seconds),
                }
                if enabled_sources:
                    filters["enabled_sources"] = enabled_sources
                raw = runtime.source_manager.search(query, page=1, per_page=12, filters=filters)
                ranked = _software_filter(raw, include_media=False)[:8]
                serialized = _serialize_search_results(query, ranked)
                registry.upsert_many(serialized.pop("registry_updates"))
                items = []
                for group in serialized.get("groups", []):
                    item = group.get("item", {})
                    source = (group.get("sources") or [{}])[0]
                    items.append(
                        {
                            "id": item.get("id"),
                            "title": item.get("title"),
                            "provider": source.get("provider"),
                            "subtitle": f"{source.get('provider', 'source')} • {source.get('seeders', 0)} seeds",
                            "protocol": source.get("protocol", "torrent"),
                            "sourceResultId": source.get("id"),
                        }
                    )
                return {"id": rail_id, "title": rail_title, "items": items}

            rails_local: List[Dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=min(4, len(config))) as pool:
                futures = [
                    pool.submit(build_one, rail_id, rail_title, query)
                    for rail_id, rail_title, query in config
                ]
                for future in futures:
                    try:
                        rails_local.append(future.result(timeout=max(2.0, timeout_seconds + 1.0)))
                    except Exception:
                        rails_local.append({"id": "unknown", "title": "Rail", "items": []})

            order = {rail_id: idx for idx, (rail_id, _, _) in enumerate(config)}
            rails_local.sort(key=lambda r: order.get(str(r.get("id") or ""), 999))
            return rails_local

        # Fast first paint: prioritize sources that don't usually require anti-bot challenges.
        # Use targeted OD-friendly queries so the first screen isn't empty even on cold start.
        fast_sources = ["OpenDirectory", "HTTP", "Prowlarr", "RealDebrid Library"]
        fast_config = [
            ("vst", "Top VST Torrents", "antares"),
            ("windows", "Windows Downloads", "sennheiser"),
            ("mac", "macOS Downloads", "antares mac"),
            ("audio", "Audio Production Tools", "sennheiser ambeo"),
        ]
        rails = build_rails(fast_config, enabled_sources=fast_sources, timeout_seconds=6.0)
        populated = sum(
            1
            for rail in rails
            if isinstance(rail.get("items"), list) and len(rail.get("items") or []) > 0
        )
        partial = populated < 2

        def build_full_in_background() -> None:
            set_session(ctx_snapshot)
            try:
                full_rails = build_rails(rails_config, enabled_sources=None, timeout_seconds=12.0)
                full_payload = {
                    "rails": full_rails,
                    "health": {
                        "rdConnected": runtime.realdebrid.is_authenticated(),
                        "providersOnline": providers_online,
                        "providersTotal": len(providers_payload["providers"]),
                        "lastIndexRefreshAt": _utc_now_iso(),
                    },
                    "partial": False,
                }
                with home_cache_lock:
                    home_cache["updated"] = monotonic()
                    home_cache["payload"] = full_payload
            finally:
                with home_build_lock:
                    home_build_inflight["full"] = False

        if partial:
            with home_build_lock:
                if not home_build_inflight["full"]:
                    home_build_inflight["full"] = True
                    import threading

                    threading.Thread(target=build_full_in_background, daemon=True).start()

        payload = {
            "rails": rails,
            "health": {
                "rdConnected": runtime.realdebrid.is_authenticated(),
                "providersOnline": providers_online,
                "providersTotal": len(providers_payload["providers"]),
                "lastIndexRefreshAt": _utc_now_iso(),
            },
            "partial": partial,
        }
        with home_cache_lock:
            home_cache["updated"] = monotonic()
            home_cache["payload"] = payload
        return payload

    @app.get("/api/providers")
    def providers() -> Dict:
        health = runtime.source_manager.get_source_health_snapshot()
        providers_payload = []
        for name in runtime.source_manager.get_source_names():
            source_health = health.get(name, {})
            health_state = _to_provider_health(
                int(source_health.get("consecutive_failures", 0)),
                bool(source_health.get("circuit_open", False)),
            )
            if name == "RealDebrid Library" and not runtime.realdebrid.is_authenticated():
                health_state = "healthy"
            providers_payload.append(
                {
                    "id": _provider_id(name),
                    "name": name,
                    "kind": "source",
                    "enabled": runtime.source_manager.is_source_enabled(name),
                    "health": health_state,
                    "lastSyncAt": _utc_now_iso(),
                    "weight": int(source_health.get("score", 100)),
                    "purpose": SOURCE_PURPOSES.get(name, "Search provider"),
                    "sourceHealth": source_health,
                }
            )
        return {"providers": providers_payload}

    @app.get("/api/providers/{provider_id}/details")
    def provider_details(provider_id: str) -> Dict:
        source_name = _provider_name_from_id(runtime, provider_id)
        if not source_name:
            raise HTTPException(status_code=404, detail="Provider not found.")

        health = runtime.source_manager.get_source_health_snapshot().get(source_name, {})
        runtime_status = runtime.source_manager.get_source_runtime_status(source_name)
        source_obj = None
        with runtime.source_manager._lock:
            source_obj = runtime.source_manager._sources.get(source_name)
        healthcheck = source_obj.healthcheck() if source_obj and hasattr(source_obj, "healthcheck") else {}

        return {
            "provider": {
                "id": provider_id,
                "name": source_name,
                "enabled": runtime.source_manager.is_source_enabled(source_name),
                "purpose": SOURCE_PURPOSES.get(source_name, "Search provider"),
            },
            "health": health,
            "runtime": runtime_status,
            "healthcheck": healthcheck,
        }

    @app.post("/api/providers/{provider_id}/test")
    def provider_test(provider_id: str, body: Dict[str, Any] = Body(default={})):  # noqa: B008
        source_name = _provider_name_from_id(runtime, provider_id)
        if not source_name:
            raise HTTPException(status_code=404, detail="Provider not found.")

        query = str(body.get("query") or "vst plugin").strip() or "vst plugin"
        timeout_seconds = float(body.get("timeoutSeconds") or 10.0)
        source_obj = None
        with runtime.source_manager._lock:
            source_obj = runtime.source_manager._sources.get(source_name)
        if not source_obj:
            raise HTTPException(status_code=404, detail="Provider source object not found.")

        started = monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(source_obj.search, query, 1)
                results = future.result(timeout=max(1.0, timeout_seconds))
            warning = str(getattr(source_obj, "last_error", "") or "").strip()
            elapsed_ms = int((monotonic() - started) * 1000)
            if warning and not results:
                return {
                    "ok": False,
                    "latencyMs": elapsed_ms,
                    "resultCount": 0,
                    "detail": warning,
                    "sampleTitles": [],
                }
            return {
                "ok": True,
                "latencyMs": elapsed_ms,
                "resultCount": len(results or []),
                "detail": "reachable",
                "sampleTitles": [r.title for r in (results or [])[:3]],
            }
        except FutureTimeoutError:
            record_audit("provider.test.timeout", {"providerId": provider_id, "query": query})
            return {"ok": False, "latencyMs": int((monotonic() - started) * 1000), "detail": "timeout"}
        except Exception as exc:
            record_audit("provider.test.error", {"providerId": provider_id, "query": query, "error": str(exc)})
            return {
                "ok": False,
                "latencyMs": int((monotonic() - started) * 1000),
                "detail": str(exc),
            }

    @app.post("/api/providers/{provider_id}/toggle")
    def toggle_provider(provider_id: str, body: ProviderToggleRequest) -> Dict:
        source_name = _provider_name_from_id(runtime, provider_id)
        if not source_name:
            raise HTTPException(status_code=404, detail="Provider not found.")
        runtime.source_manager.enable_source(source_name, body.enabled)
        enabled_sources = runtime.settings.get("enabled_sources", {}) or {}
        enabled_sources[source_name] = body.enabled
        runtime.settings.set("enabled_sources", enabled_sources)
        record_audit("provider.toggle", {"providerId": provider_id, "enabled": body.enabled})
        return {"ok": True, "providerId": provider_id, "enabled": body.enabled}

    @app.get("/api/settings")
    def get_settings() -> Dict:
        return {"settings": runtime.settings.get_all()}

    @app.get("/api/settings/schema")
    def get_settings_schema() -> Dict:
        return {
            "groups": [
                {
                    "id": "search",
                    "title": "Search",
                    "keys": ["pagination_size", "min_seeds", "size_min_gb", "size_max_gb"],
                },
                {
                    "id": "sources",
                    "title": "Sources",
                    "keys": ["enabled_sources", "rd_library_source_enabled", "open_directory_enabled"],
                },
                {
                    "id": "downloads",
                    "title": "Downloads",
                    "keys": ["download_folder", "max_concurrent_downloads", "download_backend"],
                },
                {
                    "id": "realdebrid",
                    "title": "RealDebrid",
                    "keys": ["rd_request_timeout_seconds", "rd_library_source_enabled"],
                },
                {
                    "id": "http",
                    "title": "HTTP Sources",
                    "keys": ["http_detail_max_pages", "http_request_timeout_seconds", "http_playwright_fallback_enabled"],
                },
                {
                    "id": "opendirectory",
                    "title": "Open Directory",
                    "keys": ["od_seed_urls", "od_file_extensions", "od_max_results"],
                },
            ]
        }

    @app.patch("/api/settings")
    def patch_settings(body: Dict[str, Any] = Body(default={})):  # noqa: B008
        updates = {k: v for k, v in body.items() if v is not None}
        if not updates:
            return {"ok": True, "settings": runtime.settings.get_all()}

        if "max_concurrent_downloads" in updates:
            runtime.download_manager.set_max_concurrent(int(updates["max_concurrent_downloads"]))
        if "download_backend" in updates:
            runtime.download_manager.set_download_backend(str(updates["download_backend"]))

        runtime.settings.update(updates)
        record_audit("settings.patch", {"keys": sorted(updates.keys())})

        if "enabled_sources" in updates and isinstance(updates["enabled_sources"], dict):
            runtime.source_manager.reload_sources(updates["enabled_sources"])

        return {"ok": True, "settings": runtime.settings.get_all()}

    @app.post("/api/settings/reset")
    def reset_settings() -> Dict:
        runtime.settings.reset()
        runtime.source_manager.reload_sources(runtime.settings.get("enabled_sources", {}))
        runtime.download_manager.set_download_backend(runtime.settings.get("download_backend", "native"))
        runtime.download_manager.set_max_concurrent(int(runtime.settings.get("max_concurrent_downloads", 3)))
        record_audit("settings.reset", {"ok": True})
        return {"ok": True, "settings": runtime.settings.get_all()}

    @app.get("/api/audit")
    def get_audit(limit: int = Query(200, ge=1, le=500)) -> Dict:
        with audit_lock:
            items = list(audit_log)[:limit]
        return {"events": items}

    @app.post("/api/audit/clear")
    def clear_audit() -> Dict:
        with audit_lock:
            audit_log.clear()
        record_audit("audit.cleared", {"ok": True})
        return {"ok": True}

    @app.get("/api/system/capabilities")
    def system_capabilities() -> Dict:
        backends = []
        selected = runtime.download_manager.get_download_backend()
        for name, backend in runtime.download_manager._backends.items():
            available = backend.is_available()
            purpose = "Portable builtin downloader with pause/resume" if name == "native" else "High-speed aria2c downloader"
            backends.append(
                {
                    "id": name,
                    "selected": name == selected,
                    "available": bool(available),
                    "purpose": purpose,
                }
            )

        providers_payload = providers()["providers"]
        return {
            "downloadBackends": backends,
            "providers": providers_payload,
            "focus": {
                "goal": "software, pc-games, and homebrew link discovery",
                "includes": [
                    "VST",
                    "Windows installers",
                    "macOS installers",
                    "audio production tools",
                    "PC games metadata search",
                    "ROM/homebrew links",
                ],
                "excludes": ["general movie/tv ranking bias"],
            },
        }

    @app.post("/api/system/verify")
    def system_verify() -> Dict:
        report: Dict[str, Any] = {
            "generatedAt": _utc_now_iso(),
            "focus": "software-and-plugin discovery",
            "rd": {},
            "backends": [],
            "providers": [],
            "summary": {},
        }

        rd_connected = runtime.realdebrid.is_authenticated()
        report["rd"]["connected"] = rd_connected
        if rd_connected:
            try:
                info = runtime.realdebrid.get_user_info()
                report["rd"]["user"] = {"id": info.get("id"), "username": info.get("username")}
                report["rd"]["status"] = "ok"
            except Exception as exc:
                report["rd"]["status"] = "error"
                report["rd"]["error"] = str(exc)
        else:
            report["rd"]["status"] = "not_connected"

        selected_backend = runtime.download_manager.get_download_backend()
        for name, backend in runtime.download_manager._backends.items():
            available = backend.is_available()
            report["backends"].append(
                {
                    "id": name,
                    "available": bool(available),
                    "selected": bool(name == selected_backend),
                    "purpose": "native requests downloader" if name == "native" else "aria2 external downloader",
                }
            )

        all_providers = providers()["providers"]
        healthy = 0
        for provider in all_providers:
            provider_id = provider["id"]
            test = provider_test(provider_id, body={"query": "vst plugin", "timeoutSeconds": 8})
            entry = {
                "id": provider_id,
                "name": provider["name"],
                "enabled": provider["enabled"],
                "health": provider["health"],
                "test": test,
            }
            if test.get("ok"):
                healthy += 1
            report["providers"].append(entry)

        report["summary"] = {
            "providersTotal": len(all_providers),
            "providersHealthy": healthy,
            "providersTested": len(report["providers"]),
            "selectedBackend": selected_backend,
            "softwareMode": True,
        }
        record_audit("system.verify", {"providersTested": len(report["providers"]), "healthy": healthy})
        return report

    @app.post("/api/system/shutdown")
    def system_shutdown() -> Dict[str, Any]:
        if not _allow_shutdown():
            raise HTTPException(status_code=403, detail="Shutdown is disabled on this server.")
        # Best-effort shutdown for contained builds; frontend will also attempt window.close().
        import os
        import threading
        import time

        def _exit_soon():
            time.sleep(0.35)
            os._exit(0)  # intentional hard exit for local-contained app

        threading.Thread(target=_exit_soon, daemon=True).start()
        return {"ok": True}

    @app.post("/api/system/reset-local-data")
    def system_reset_local_data() -> Dict[str, Any]:
        if not _allow_shutdown():
            raise HTTPException(status_code=403, detail="Reset local data is disabled on this server.")

        data_dir_env = str(os.environ.get("PLUGGY_DATA_DIR", "") or "").strip()
        data_dir = Path(data_dir_env).expanduser() if data_dir_env else runtime.settings.settings_dir
        data_dir = data_dir.resolve()
        home_dir = Path.home().resolve()

        # Guard against deleting an unsafe path due to misconfiguration.
        if data_dir in {Path("/"), home_dir} or len(data_dir.parts) < 3:
            raise HTTPException(status_code=400, detail="Refusing to reset an unsafe data directory path.")

        # Remove local data after the process exits so SQLite files are not in use.
        helper = (
            "import shutil,sys,time; "
            "p=sys.argv[1]; "
            "time.sleep(1.0); "
            "shutil.rmtree(p, ignore_errors=True)"
        )
        try:
            subprocess.Popen(
                ["/usr/bin/python3", "-c", helper, str(data_dir)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to schedule local data reset: {exc}") from exc

        record_audit("system.reset_local_data", {"dataDir": str(data_dir)})

        import threading
        import time

        def _exit_soon():
            time.sleep(0.35)
            os._exit(0)

        threading.Thread(target=_exit_soon, daemon=True).start()
        return {"ok": True, "dataDir": str(data_dir), "shuttingDown": True}

    @app.get("/api/transfers")
    def list_transfers(status: Optional[str] = None) -> Dict:
        serialized = [
            _serialize_transfer(job, transfer_to_source_result.get(job.job_id))
            for job in runtime.download_manager.get_all_jobs().values()
        ]
        if status:
            serialized = [entry for entry in serialized if entry["status"] == status]
        return {"transfers": serialized}

    @app.post("/api/transfers")
    def create_transfer(body: TransferCreateRequest) -> Dict:
        selected = registry.get(body.sourceResultId)
        if not selected:
            raise HTTPException(status_code=404, detail="Unknown source result id. Perform search again.")

        url = _pick_best_link(selected)
        if not url:
            raise HTTPException(status_code=422, detail="Selected result has no usable link.")

        download_folder = Path(runtime.settings.get("download_folder"))
        download_folder.mkdir(parents=True, exist_ok=True)

        file_name = sanitize_filename(f"{selected.title}.bin")
        output_path = get_unique_filename(download_folder, file_name)

        if url.lower().startswith("magnet:"):
            job = runtime.download_manager.queue_download(selected.title, output_path, magnet=url)
        else:
            job = runtime.download_manager.queue_download(selected.title, output_path, direct_url=url)
        transfer_to_source_result[job.job_id] = body.sourceResultId
        record_audit(
            "transfer.created",
            {
                "jobId": job.job_id,
                "sourceResultId": body.sourceResultId,
                "protocol": "torrent" if url.lower().startswith("magnet:") else "http",
            },
        )

        return {"ok": True, "transfer": {"id": job.job_id, "status": _to_transfer_status(job.status)}}

    @app.post("/api/transfers/{transfer_id}/retry")
    def retry_transfer(transfer_id: str) -> Dict:
        job = runtime.download_manager.retry_download(transfer_id)
        if not job:
            raise HTTPException(status_code=404, detail="Transfer not retryable or not found.")
        if transfer_id in transfer_to_source_result:
            transfer_to_source_result[job.job_id] = transfer_to_source_result[transfer_id]
        record_audit("transfer.retry", {"from": transfer_id, "to": job.job_id})
        return {"ok": True, "transfer": {"id": job.job_id, "status": _to_transfer_status(job.status)}}

    @app.post("/api/transfers/{transfer_id}/cancel")
    def cancel_transfer(transfer_id: str) -> Dict:
        job = runtime.download_manager.get_job(transfer_id)
        if not job:
            raise HTTPException(status_code=404, detail="Transfer not found.")
        runtime.download_manager.cancel_download(transfer_id)
        record_audit("transfer.cancel", {"jobId": transfer_id})
        return {"ok": True}

    @app.post("/api/transfers/{transfer_id}/pause")
    def pause_transfer(transfer_id: str) -> Dict:
        job = runtime.download_manager.get_job(transfer_id)
        if not job:
            raise HTTPException(status_code=404, detail="Transfer not found.")
        runtime.download_manager.pause_download(transfer_id)
        record_audit("transfer.pause", {"jobId": transfer_id})
        return {"ok": True}

    @app.post("/api/transfers/{transfer_id}/resume")
    def resume_transfer(transfer_id: str) -> Dict:
        job = runtime.download_manager.get_job(transfer_id)
        if not job:
            raise HTTPException(status_code=404, detail="Transfer not found.")
        runtime.download_manager.resume_download(transfer_id)
        record_audit("transfer.resume", {"jobId": transfer_id})
        return {"ok": True}

    @app.delete("/api/transfers/{transfer_id}")
    def delete_transfer(transfer_id: str, delete_file: bool = Query(False)) -> Dict:
        job = runtime.download_manager.get_job(transfer_id)
        if not job:
            raise HTTPException(status_code=404, detail="Transfer not found.")
        runtime.download_manager.delete_download(transfer_id, delete_file=delete_file)
        transfer_to_source_result.pop(transfer_id, None)
        record_audit("transfer.delete", {"jobId": transfer_id, "deleteFile": bool(delete_file)})
        return {"ok": True}

    @app.get("/api/item/{item_id}")
    def get_item(item_id: str) -> Dict:
        matched = []
        for source_id, result in registry.entries():
            if result.infohash == item_id or source_id.startswith(f"src_{item_id}_"):
                matched.append((source_id, result))
        if not matched:
            raise HTTPException(status_code=404, detail="Item not found in current search session.")
        _, top = matched[0]
        releases = []
        for srid, result in matched:
            link = _pick_best_link(result)
            releases.append(
                {
                    "id": srid,
                    "provider": result.source,
                    "protocol": "torrent" if link.lower().startswith("magnet:") else "http",
                    "size": _size_bytes_to_text(result.size),
                    "seeders": result.seeds,
                }
            )
        releases.sort(key=lambda row: (1 if row["protocol"] == "torrent" else 0, row["seeders"]), reverse=True)
        return {
            "item": {
                "id": item_id,
                "title": top.title,
                "aliases": [],
                "category": top.category or "software",
                "updatedAt": _utc_now_iso(),
            },
            "releases": releases,
            "fileTree": None,
        }

    @app.post("/api/rd")
    def send_to_rd(body: SourceSelectionRequest) -> Dict:
        return create_transfer(TransferCreateRequest(sourceResultId=body.sourceResultId))

    return app


app = create_app()
