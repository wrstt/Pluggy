import unittest
from unittest.mock import patch
import requests
from bs4 import BeautifulSoup

from pluggy.sources.http_source import HTTPSource
from pluggy.models.search_result import SearchResult


class _Settings:
    def __init__(self):
        self.data = {
            "http_sources_enabled": True,
            "http_sources": ["https://example.com/search?q={query}"],
            "http_cache_ttl_seconds": 300.0,
            "http_allow_stale_cache": True,
            "http_background_refresh": False,
            "http_detail_max_pages": 2,
            "http_links_per_detail": 4,
            "http_time_budget_seconds": 5.0,
            "http_redirect_timeout_seconds": 2.0,
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    def update(self, values):
        self.data.update(values)

    def set(self, key, value):
        self.data[key] = value


def _dummy_result():
    return [SearchResult(
        title="Example Download",
        magnet="https://example.com/file.zip",
        size=1234,
        seeds=0,
        leeches=0,
        source="HTTP",
        infohash="",
    )]


class TestHTTPSourceFramework(unittest.TestCase):
    def test_domain_adapter_registry_selects_known_domains(self):
        src = HTTPSource(_Settings())
        self.assertEqual(src._select_adapter("https://nmac.to/?s=test").name, "nmac")
        self.assertEqual(src._select_adapter("https://audioz.download/?s=test").name, "audioz")
        self.assertEqual(src._select_adapter("https://macked.app/?s=test").name, "macked")
        self.assertEqual(src._select_adapter("https://vstorrent.org/?s=test").name, "vstorrent")
        self.assertEqual(src._select_adapter("https://unknown.example/search?q=test").name, "generic")

    def test_incremental_cache_reuses_previous_query(self):
        src = HTTPSource(_Settings())
        with patch.object(src, "_query_single_source", return_value=_dummy_result()) as mocked:
            first = src.search("example", 1)
            second = src.search("example", 1)
            self.assertEqual(len(first), 1)
            self.assertEqual(len(second), 1)
            self.assertEqual(mocked.call_count, 1)

    def test_health_records_failure_state(self):
        src = HTTPSource(_Settings())
        with patch.object(src, "_query_single_source", side_effect=RuntimeError("boom")):
            out = src.search("example", 1)
            self.assertEqual(out, [])
            snap = src.get_health_snapshot()
            self.assertIn("https://example.com/search?q={query}", snap)
            state = snap["https://example.com/search?q={query}"]
            self.assertGreaterEqual(state["failures"], 1)
            self.assertIn("boom", state["last_error"])

    def test_request_with_retry_recovers_after_timeout(self):
        src = HTTPSource(_Settings())

        class _Response:
            status_code = 200
            url = "https://example.com/search?q=test"
            content = b"<html></html>"

            def raise_for_status(self):
                return None

        with patch.object(
            src.session,
            "get",
            side_effect=[requests.Timeout("slow"), _Response()],
        ) as mocked_get:
            response = src._request_with_retry(
                url="https://example.com/search?q=test",
                timeout_seconds=1.0,
                retries=1,
                backoff_seconds=0.0,
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(mocked_get.call_count, 2)

    def test_redirect_wrapper_normalization_handles_query_and_fragment(self):
        src = HTTPSource(_Settings())
        out_query = src._normalize_possible_redirect_link(
            "/go?url=https%3A%2F%2Ffiles.example.com%2Fpack.zip",
            "https://example.com/post/1",
        )
        self.assertEqual(out_query, "https://files.example.com/pack.zip")

        out_fragment = src._normalize_possible_redirect_link(
            "https://redir.example/path#url=https%3A%2F%2Ffiles.example.com%2Fa.torrent",
            "https://example.com/post/1",
        )
        self.assertEqual(out_fragment, "https://files.example.com/a.torrent")

    def test_download_link_detection_covers_extensions_and_query(self):
        src = HTTPSource(_Settings())
        self.assertTrue(src._is_download_like_link("https://site.test/releases/app.pkg"))
        self.assertTrue(src._is_download_like_link("https://site.test/redirect?download=1&file=abc"))
        self.assertFalse(src._is_download_like_link("https://site.test/login"))

    def test_excludes_request_detail_pages(self):
        src = HTTPSource(_Settings())
        self.assertFalse(
            src._is_likely_detail_url(
                "https://audioz.download/request/123-example.html",
                "https://audioz.download/?s=abc",
                "abc",
            )
        )

    def test_extract_link_candidates_from_data_attrs_and_onclick(self):
        src = HTTPSource(_Settings())
        soup = BeautifulSoup(
            '<a data-url="https://files.example.com/a.zip" onclick="window.open(\'https://x.test/dl\')">x</a>',
            "html.parser",
        )
        node = soup.find("a")
        links = src._extract_link_candidates_from_node(node)
        self.assertIn("https://files.example.com/a.zip", links)
        self.assertIn("https://x.test/dl", links)

    def test_playwright_fallback_recovers_when_http_request_fails(self):
        src = HTTPSource(_Settings())
        src.settings.update({"http_playwright_fallback_enabled": True})

        class _PlaywrightStub:
            def can_handle(self, source_url, settings):
                return True
            def is_available(self):
                return True
            def fetch_html(self, url, timeout_ms=20000, headless=True):
                return (
                    b'<html><body><a href="magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA">OK</a></body></html>',
                    url,
                )

        src._playwright_adapter = _PlaywrightStub()
        with patch.object(src, "_request_with_retry", side_effect=requests.RequestException("boom")):
            out = src._query_single_source(
                "https://example.com/search?q={query}",
                "https://example.com/search?q=ableton",
                "ableton",
                for_test=True,
            )
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0].source, "HTTP")
            self.assertIn("Playwright fallback", src.last_error)

    def test_playwright_fallback_disabled_does_not_mask_http_error(self):
        src = HTTPSource(_Settings())
        src.settings.update({"http_playwright_fallback_enabled": False})
        with patch.object(src, "_request_with_retry", side_effect=requests.RequestException("boom")):
            out = src._query_single_source(
                "https://example.com/search?q={query}",
                "https://example.com/search?q=ableton",
                "ableton",
                for_test=True,
            )
            self.assertEqual(out, [])
            self.assertIn("HTTP fetch failed for this source", src.last_error)


if __name__ == "__main__":
    unittest.main()
