"""Resource path helpers.

Supports normal execution and bundled executables (e.g., PyInstaller via _MEIPASS).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable


def resource_root() -> Path:
    # PyInstaller sets sys._MEIPASS to a temp folder containing bundled files
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    # package root: .../pluggy
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str | os.PathLike[str]) -> str:
    return str(resource_root().joinpath(*map(str, parts)))
