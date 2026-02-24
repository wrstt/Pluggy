"""
Source SDK
Versioned base interface for Pluggy search sources.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from ..models.search_result import SearchResult


class BaseSource(ABC):
    """
    Stable source contract for plugin and built-in implementations.
    """
    api_version = 1
    name = "UnnamedSource"
    last_error = ""

    @abstractmethod
    def search(self, query: str, page: int = 1) -> List[SearchResult]:
        """Return search results for a query."""
        raise NotImplementedError

    def reload_from_settings(self) -> None:
        """Optional hook called when source settings are reloaded."""
        return None

    def healthcheck(self) -> Dict[str, Any]:
        """Optional lightweight health payload for dashboards."""
        return {
            "name": self.name,
            "ok": not bool(self.last_error),
            "error": self.last_error,
            "api_version": self.api_version,
        }
