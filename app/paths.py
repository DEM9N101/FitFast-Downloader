"""Resolve bundled-resource paths in both dev and PyInstaller-frozen runs."""
from __future__ import annotations
import sys
from pathlib import Path


def resource_dir() -> Path:
    """Directory that contains bundled read-only resources (the vendor folder).

    - Dev run: the project root (parent of the app package).
    - PyInstaller: sys._MEIPASS (onefile temp dir, or the onedir _internal dir).
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


VENDOR_DIR = resource_dir() / "vendor"
