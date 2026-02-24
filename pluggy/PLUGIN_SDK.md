# Pluggy Source Plugin SDK (v1)

Local-only plugin loading is supported from:
- `~/.pluggy/plugins`
- `<project>/pluggy_plugins`

## Source contract
Plugins must implement `BaseSource` (`pluggy.sources.base.BaseSource`).

Required:
- `name: str`
- `search(query: str, page: int = 1) -> list[SearchResult]`

Optional:
- `reload_from_settings()`
- `healthcheck()`

## Plugin registration options

### Option A: `register(registry, context)` function
```python
from pluggy.sources.base import BaseSource
from pluggy.models.search_result import SearchResult

class MySource(BaseSource):
    name = "MySource"
    def search(self, query: str, page: int = 1):
        return [SearchResult(
            title=f"{query} sample",
            magnet="magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            size=1,
            seeds=1,
            leeches=0,
            source=self.name,
            infohash="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )]

def register(registry, context):
    registry.add(MySource())
```

### Option B: class auto-discovery
Set `plugin_enabled = True` on your `BaseSource` subclass. The loader will instantiate it.

## Safety and scope
- No remote plugin installation.
- Plugins are plain local Python files.
- Invalid plugins are skipped and logged as plugin load warnings.
