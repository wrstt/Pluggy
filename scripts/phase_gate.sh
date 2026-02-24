#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON_BIN:-$ROOT/.venv/bin/python}"

echo "[1/3] Compile check"
"$PY" -m py_compile $(rg --files pluggy -g '*.py')

echo "[2/3] Unit tests"
"$PY" -m unittest discover -s tests -p 'test_*.py' -v

echo "[3/3] Smoke check (source manager deterministic)"
"$PY" - <<'PY'
from pluggy.core.event_bus import EventBus
from pluggy.core.source_manager import SourceManager
from pluggy.models.search_result import SearchResult
from pluggy.sources.base import BaseSource

class S(BaseSource):
    name = "S"
    def search(self, query: str, page: int = 1):
        return [SearchResult(
            title="App 2026 v1.0",
            magnet="magnet:?xt=urn:btih:DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
            size=123,
            seeds=3,
            leeches=1,
            source="S",
            infohash="DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD",
        )]

sm=SourceManager(EventBus())
sm.register(S())
r=sm.search("app",1,10,{"enabled_sources":["S"]})
assert len(r)==1
assert r[0].source.startswith("S")
print("smoke-ok")
PY

echo "Phase gate passed"
