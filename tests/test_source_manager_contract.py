import unittest

from pluggy.core.event_bus import EventBus
from pluggy.core.source_manager import SourceManager
from pluggy.models.search_result import SearchResult
from pluggy.sources.base import BaseSource


class DummySource(BaseSource):
    name = "Dummy"

    def search(self, query: str, page: int = 1):
        return [SearchResult(
            title=f"{query} 1.0",
            magnet="magnet:?xt=urn:btih:CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
            size=100,
            seeds=10,
            leeches=1,
            source=self.name,
            infohash="CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        )]


class TestSourceManagerContract(unittest.TestCase):
    def test_register_requires_basesource(self):
        sm = SourceManager(EventBus())

        class Invalid:
            name = "X"
            def search(self, query, page=1):
                return []

        with self.assertRaises(TypeError):
            sm.register(Invalid())

    def test_register_and_search(self):
        sm = SourceManager(EventBus())
        sm.register(DummySource())
        results = sm.search("hello", page=1, per_page=10, filters={"enabled_sources": ["Dummy"]})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source, "Dummy")
        self.assertTrue(len(results[0].link_candidates) >= 1)


if __name__ == "__main__":
    unittest.main()
