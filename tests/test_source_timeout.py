import time
import unittest

from pluggy.core.event_bus import EventBus, Events
from pluggy.core.source_manager import SourceManager
from pluggy.models.search_result import SearchResult
from pluggy.sources.base import BaseSource


class SlowSource(BaseSource):
    name = "SlowSource"

    def search(self, query: str, page: int = 1):
        time.sleep(2.0)
        return []


class FastSource(BaseSource):
    name = "FastSource"

    def search(self, query: str, page: int = 1):
        return [SearchResult(
            title="Fast App 1.0",
            magnet="magnet:?xt=urn:btih:FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",
            size=100,
            seeds=11,
            leeches=1,
            source=self.name,
            infohash="FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",
        )]


class TestSourceTimeout(unittest.TestCase):
    def test_search_returns_when_one_source_hangs(self):
        bus = EventBus()
        sm = SourceManager(bus, reliability={
            "max_retries": 0,
            "retry_backoff_seconds": 0.0,
            "circuit_failure_threshold": 3,
            "circuit_cooldown_seconds": 60.0,
            "search_timeout_seconds": 1.0,
        })
        sm.register(SlowSource())
        sm.register(FastSource())

        cap = {}
        bus.subscribe(Events.SEARCH_COMPLETED, lambda d: cap.update(d if isinstance(d, dict) else {}))

        started = time.perf_counter()
        results = sm.search("demo", page=1, per_page=10, filters={"enabled_sources": ["SlowSource", "FastSource"]})
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 1.8)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "FastSource")
        warnings = cap.get("source_warnings", {})
        self.assertIn("SlowSource", warnings)
        self.assertIn("timed out", warnings["SlowSource"].lower())


if __name__ == "__main__":
    unittest.main()
