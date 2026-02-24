import time
import unittest

from pluggy.core.event_bus import EventBus, Events
from pluggy.core.source_manager import SourceManager
from pluggy.models.search_result import SearchResult
from pluggy.sources.base import BaseSource


class SlowSource(BaseSource):
    name = "SlowSourceFastReturn"

    def search(self, query: str, page: int = 1):
        time.sleep(5.0)
        return []


class FastSource(BaseSource):
    name = "FastSourceFastReturn"

    def search(self, query: str, page: int = 1):
        return [SearchResult(
            title="Fast Return App",
            magnet="magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            size=1,
            seeds=3,
            leeches=1,
            source=self.name,
            infohash="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )]


class TestSourceFastReturn(unittest.TestCase):
    def test_fast_return_skips_slow_sources(self):
        bus = EventBus()
        sm = SourceManager(bus, reliability={
            "search_timeout_seconds": 12.0,
            "early_return_seconds": 0.1,
            "early_return_min_results": 1,
            "max_retries": 0,
        })
        sm.register(FastSource())
        sm.register(SlowSource())

        cap = {}
        bus.subscribe(Events.SEARCH_COMPLETED, lambda d: cap.update(d if isinstance(d, dict) else {}))

        start = time.perf_counter()
        results = sm.search("x", page=1, per_page=10, filters={"enabled_sources": ["FastSourceFastReturn", "SlowSourceFastReturn"]})
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 2.0)
        self.assertEqual(len(results), 1)
        warnings = cap.get("source_warnings", {})
        self.assertIn("SlowSourceFastReturn", warnings)
        self.assertIn("fast results", warnings["SlowSourceFastReturn"].lower())


if __name__ == "__main__":
    unittest.main()
