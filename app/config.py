"""Persistent settings stored in %APPDATA%/FitFast/config.json."""
from __future__ import annotations
import json
import os
from pathlib import Path

APP_VERSION = "1.1.0"
GITHUB_REPO = "DEM9N101/FitFast-Downloader"
REPO_URL = f"https://github.com/{GITHUB_REPO}"
ISSUES_URL = f"{REPO_URL}/issues/new"
RELEASES_URL = f"{REPO_URL}/releases/latest"

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home() / ".config"))) / "FitFast"
CONFIG_FILE = APP_DIR / "config.json"
LOG_DIR = APP_DIR / "logs"
LOG_FILE = LOG_DIR / "fitfast.log"

DEFAULTS: dict = {
    "destination": str(Path.home() / "Downloads"),
    "connections_per_file": 16,
    "concurrent_files": 3,
    "window_geometry": "980x720",
    "appearance": "dark",
    "auto_reresolve": True,
    "stall_threshold_mbps": 1.0,
    "peak_speed_bps": 0,
    "auto_extract": True,
    "delete_archives_after": False,
}


def load() -> dict:
    if not CONFIG_FILE.exists():
        return dict(DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update({k: v for k, v in data.items() if k in DEFAULTS})
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save(config: dict) -> None:
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError:
        pass
