import tempfile
import textwrap
import unittest
from pathlib import Path

from pluggy.sources.base import BaseSource
from pluggy.sources.plugin_loader import PluginContext, SourcePluginLoader
from pluggy.core.settings_manager import SettingsManager
from pluggy.models.search_result import SearchResult


class TestPluginLoader(unittest.TestCase):
    def test_load_register_function_plugin(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "my_plugin.py"
            p.write_text(textwrap.dedent("""
                from pluggy.sources.base import BaseSource
                from pluggy.models.search_result import SearchResult

                class MySource(BaseSource):
                    name = "MyPluginSource"
                    def search(self, query: str, page: int = 1):
                        return [SearchResult(
                            title=f"{query} result",
                            magnet="magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                            size=1,
                            seeds=1,
                            leeches=0,
                            source=self.name,
                            infohash="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                        )]

                def register(registry, context):
                    registry.add(MySource())
            """), encoding="utf-8")

            loader = SourcePluginLoader([Path(td)])
            sources = loader.load(PluginContext(settings=SettingsManager()))
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0].name, "MyPluginSource")
            self.assertEqual(loader.last_errors, [])

    def test_load_class_plugin_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "class_plugin.py"
            p.write_text(textwrap.dedent("""
                from pluggy.sources.base import BaseSource
                from pluggy.models.search_result import SearchResult

                class ClassPlugin(BaseSource):
                    plugin_enabled = True
                    name = "ClassPlugin"
                    def search(self, query: str, page: int = 1):
                        return [SearchResult(
                            title="ok",
                            magnet="magnet:?xt=urn:btih:BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
                            size=1,
                            seeds=2,
                            leeches=0,
                            source=self.name,
                            infohash="BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
                        )]
            """), encoding="utf-8")

            loader = SourcePluginLoader([Path(td)])
            sources = loader.load(PluginContext(settings=SettingsManager()))
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0].name, "ClassPlugin")

    def test_invalid_plugin_reports_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad_plugin.py"
            p.write_text("x = 1\n", encoding="utf-8")
            loader = SourcePluginLoader([Path(td)])
            sources = loader.load(PluginContext(settings=SettingsManager()))
            self.assertEqual(sources, [])
            self.assertEqual(len(loader.last_errors), 1)
            self.assertIn("No register()", loader.last_errors[0])


if __name__ == "__main__":
    unittest.main()
