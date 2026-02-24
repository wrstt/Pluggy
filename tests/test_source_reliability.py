import unittest

from pluggy.core.event_bus import EventBus, Events
from pluggy.core.source_manager import SourceManager
from pluggy.models.search_result import SearchResult
from pluggy.sources.base import BaseSource


class FlakySource(BaseSource):
    name = "Flaky"

    def __init__(self):
        self.calls = 0

    def search(self, query: str, page: int = 1):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient fail")
        return [SearchResult(
            title="Flaky App 1.0",
            magnet="magnet:?xt=urn:btih:EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE",
            size=100,
            seeds=5,
            leeches=1,
            source=self.name,
            infohash="EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE",
        )]


class AlwaysFailSource(BaseSource):
    name = "AlwaysFail"

    def __init__(self):
        self.calls = 0

    def search(self, query: str, page: int = 1):
        self.calls += 1
        raise RuntimeError("hard fail")


class TestSourceReliability(unittest.TestCase):
    def test_retry_recovers_transient_failure(self):
        sm = SourceManager(EventBus(), reliability={
            "max_retries": 1,
            "retry_backoff_seconds": 0.0,
            "circuit_failure_threshold": 3,
            "circuit_cooldown_seconds": 60.0,
        })
        src = FlakySource()
        sm.register(src)
        results = sm.search("x", page=1, per_page=10, filters={"enabled_sources": ["Flaky"]})
        self.assertEqual(len(results), 1)
        self.assertEqual(src.calls, 2)
        health = sm.get_source_health_snapshot()["Flaky"]
        self.assertGreaterEqual(health["successes"], 1)

    def test_circuit_opens_and_skips_source(self):
        bus = EventBus()
        sm = SourceManager(bus, reliability={
            "max_retries": 0,
            "retry_backoff_seconds": 0.0,
            "circuit_failure_threshold": 2,
            "circuit_cooldown_seconds": 120.0,
        })
        src = AlwaysFailSource()
        sm.register(src)

        cap = {}
        bus.subscribe(Events.SEARCH_COMPLETED, lambda d: cap.update(d if isinstance(d, dict) else {}))

        sm.search("a-1", page=1, per_page=10, filters={"enabled_sources": ["AlwaysFail"]})
        sm.search("a-2", page=1, per_page=10, filters={"enabled_sources": ["AlwaysFail"]})
        calls_after_open = src.calls
        sm.search("a-3", page=1, per_page=10, filters={"enabled_sources": ["AlwaysFail"]})

        self.assertEqual(src.calls, calls_after_open)
        warnings = cap.get("source_warnings", {})
        self.assertIn("AlwaysFail", warnings)
        self.assertIn("Circuit open", warnings["AlwaysFail"])


if __name__ == "__main__":
    unittest.main()
