import unittest
from unittest.mock import patch

from pluggy.sources.open_directory import OpenDirectorySource


class _Settings:
    def __init__(self):
        self.data = {
            "open_directory_enabled": True,
            "od_seed_urls": ["https://example.test/dir/"],
            "od_use_search_engines": False,
            "od_engine_templates": ["https://duckduckgo.com/html/?q={query}"],
            "od_file_extensions": ["zip", "rar", "7z"],
            "od_max_results": 20,
            "od_max_candidate_pages": 8,
            "od_max_depth": 1,
            "od_max_subdirs_per_page": 5,
            "od_request_timeout_seconds": 2.0,
            "od_request_retries": 0,
            "od_retry_backoff_seconds": 0.0,
            "od_allowed_domains": [],
            "od_exclude_patterns": [],
            "od_max_file_size_gb": 0.0,
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class _Resp:
    def __init__(self, html: bytes):
        self.content = html

    def raise_for_status(self):
        return None


class TestOpenDirectorySource(unittest.TestCase):
    def test_seed_directory_returns_direct_files(self):
        src = OpenDirectorySource(_Settings())
        listing = b"""
        <html><title>Index of /dir</title><body>
        <a href='Ableton-Live-12.zip'>Ableton-Live-12.zip</a>
        <a href='other.txt'>other.txt</a>
        </body></html>
        """
        with patch.object(src, "_request_with_retry", return_value=_Resp(listing)):
            out = src.search("ableton", 1)
            self.assertEqual(len(out), 1)
            self.assertIn("ableton-live-12.zip", out[0].magnet.lower())
            self.assertEqual(out[0].source, "OpenDirectory")

    def test_engine_discovery_normalizes_duckduckgo_uddg(self):
        settings = _Settings()
        settings.set("od_use_search_engines", True)
        settings.set("od_seed_urls", [])
        src = OpenDirectorySource(settings)

        search_html = b"""
        <html><body>
          <a class='result__a' href='https://duckduckgo.com/l/?uddg=https%3A%2F%2Ffiles.example%2Fmusic%2F'>x</a>
        </body></html>
        """
        od_html = b"""
        <html><title>Index of /music</title><body>
          <a href='Ableton-Pack.rar'>Ableton-Pack.rar</a>
        </body></html>
        """

        calls = {"n": 0}

        def _fake_request(url):
            calls["n"] += 1
            if "duckduckgo.com/html/" in url:
                return _Resp(search_html)
            return _Resp(od_html)

        with patch.object(src, "_request_with_retry", side_effect=_fake_request):
            out = src.search("ableton", 1)
            self.assertEqual(len(out), 1)
            self.assertIn("ableton-pack.rar", out[0].magnet.lower())
            self.assertEqual(src.last_fetch_mode, "engine")
            self.assertGreaterEqual(src.last_discovered_pages, 1)

    def test_allowed_domains_filter_blocks_non_allowed_hosts(self):
        settings = _Settings()
        settings.set("od_allowed_domains", ["allowed.test"])
        src = OpenDirectorySource(settings)
        listing = b"<html><a href='Ableton.zip'>Ableton.zip</a></html>"
        with patch.object(src, "_request_with_retry", return_value=_Resp(listing)):
            out = src.search("ableton", 1)
            self.assertEqual(out, [])
            self.assertGreaterEqual(src.last_blocked_count, 1)

    def test_max_size_cap_filters_large_files(self):
        settings = _Settings()
        settings.set("od_max_file_size_gb", 1.0)
        src = OpenDirectorySource(settings)
        listing = b"""
        <html>
          <div><a href='Ableton-Large.zip'>Ableton-Large.zip</a>  3.2 GB</div>
          <div><a href='Ableton-Small.zip'>Ableton-Small.zip</a>  500 MB</div>
        </html>
        """
        with patch.object(src, "_request_with_retry", return_value=_Resp(listing)):
            out = src.search("ableton", 1)
            self.assertEqual(len(out), 1)
            self.assertIn("small", out[0].magnet.lower())
            self.assertGreaterEqual(src.last_blocked_count, 1)

    def test_runtime_reports_domain_adapter(self):
        settings = _Settings()
        settings.set("od_seed_urls", ["https://suhr.ir/plugin/"])
        src = OpenDirectorySource(settings)
        listing = b"<html><a href='Ableton.zip'>Ableton.zip</a></html>"
        with patch.object(src, "_request_with_retry", return_value=_Resp(listing)):
            src.search("ableton", 1)
            runtime = src.get_runtime_status()
            self.assertEqual(runtime.get("last_adapter_used"), "suhr")


if __name__ == "__main__":
    unittest.main()
