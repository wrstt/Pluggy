"""
Local source plugin loader/registry.
Loads Python plugins from trusted local directories only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional
import importlib.util
import inspect
import sys
import traceback

from .base import BaseSource


@dataclass
class PluginContext:
    settings: object
    rd_client: object | None = None
    event_bus: object | None = None


class SourceRegistry:
    """Registry for plugin-created source instances."""

    def __init__(self):
        self._sources: List[BaseSource] = []

    def add(self, source: BaseSource):
        if not isinstance(source, BaseSource):
            raise TypeError("Source must inherit BaseSource")
        if not getattr(source, "name", ""):
            raise ValueError("Source must define a non-empty name")
        self._sources.append(source)

    def add_factory(self, factory: Callable[[PluginContext], BaseSource], context: PluginContext):
        src = factory(context)
        self.add(src)

    def list(self) -> List[BaseSource]:
        return list(self._sources)


class SourcePluginLoader:
    """
    Loads source plugins from local files:
    - looks for register(registry, context) function OR
    - classes inheriting BaseSource with plugin_enabled = True
    """

    def __init__(self, plugin_dirs: Iterable[Path]):
        self.plugin_dirs = [Path(p) for p in plugin_dirs]
        self.last_errors: List[str] = []

    def discover_files(self) -> List[Path]:
        files: List[Path] = []
        for d in self.plugin_dirs:
            if not d.exists() or not d.is_dir():
                continue
            for f in sorted(d.glob("*.py")):
                if f.name.startswith("_"):
                    continue
                files.append(f)
        return files

    def load(self, context: PluginContext) -> List[BaseSource]:
        self.last_errors.clear()
        registry = SourceRegistry()
        for path in self.discover_files():
            try:
                self._load_file(path, registry, context)
            except Exception as e:
                self.last_errors.append(f"{path}: {e}")
        return registry.list()

    def _load_file(self, path: Path, registry: SourceRegistry, context: PluginContext):
        module_name = f"pluggy_source_plugin_{path.stem}_{abs(hash(str(path)))}"
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to create import spec")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            tb = traceback.format_exc(limit=5)
            raise RuntimeError(f"Plugin import failed\n{tb}") from None

        register_fn = getattr(module, "register", None)
        if callable(register_fn):
            register_fn(registry, context)
            return

        found_any = False
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is BaseSource:
                continue
            if not issubclass(obj, BaseSource):
                continue
            if not bool(getattr(obj, "plugin_enabled", False)):
                continue
            source = self._instantiate_source(obj, context)
            registry.add(source)
            found_any = True

        if not found_any:
            raise RuntimeError("No register() function or plugin_enabled BaseSource class found")

    def _instantiate_source(self, cls, context: PluginContext) -> BaseSource:
        """
        Try common constructor signatures in strict local plugin mode.
        """
        for args in [
            (context.settings, context.rd_client, context.event_bus),
            (context.settings, context.rd_client),
            (context.settings,),
            (),
        ]:
            try:
                return cls(*args)
            except TypeError:
                continue
        raise RuntimeError(f"Could not instantiate plugin source class {cls.__name__}")


def default_plugin_dirs() -> List[Path]:
    """
    Local-only plugin paths. No remote plugin loading is supported.
    """
    return [
        Path.home() / ".pluggy" / "plugins",
        Path.cwd() / "pluggy_plugins",
    ]
