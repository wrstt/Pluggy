"""
Request context for web runtime.

We use contextvars so a single global runtime (FastAPI app) can still serve
per-user/per-profile settings safely across concurrent requests.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class SessionContext:
    user_id: Optional[int] = None
    username: Optional[str] = None
    role: str = "user"
    profile_id: Optional[str] = None


current_session: ContextVar[SessionContext] = ContextVar("pluggy_current_session", default=SessionContext())
profile_settings_cache: ContextVar[Optional[Dict[str, Any]]] = ContextVar("pluggy_profile_settings_cache", default=None)
user_settings_cache: ContextVar[Optional[Dict[str, Any]]] = ContextVar("pluggy_user_settings_cache", default=None)


def set_session(ctx: SessionContext) -> None:
    current_session.set(ctx)
    profile_settings_cache.set(None)
    user_settings_cache.set(None)


def get_session() -> SessionContext:
    return current_session.get()


def get_profile_id() -> Optional[str]:
    return get_session().profile_id


def get_user_id() -> Optional[int]:
    return get_session().user_id

