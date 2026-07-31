"""Persistent settings stored in %APPDATA%/FitFast/config.json."""
from __future__ import annotations
import json
import os
from pathlib import Path

APP_VERSION = "1.2.0"
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
    # 1 connection per file is REQUIRED for fuckingfast.co: it returns a
    # malformed Content-Range for bounded range requests, so every extra split
    # piece dies with "Invalid range header". Speed comes from running many
    # files at once instead. See app/downloader.py for the full explanation.
    "connections_per_file": 1,
    # Each file is a single stream now, so this is the main speed dial. 4 is a
    # safe default: enough streams to fill a fast line, few enough that the
    # host does not start throttling the IP. Users on slower lines often find
    # 2 is just as fast.
    "concurrent_files": 4,
    # How many stealth browsers resolve links at once. Big throughput lever
    # (one browser starves the downloader), but each is a real Firefox costing
    # hundreds of MB, so 2 is the safe default and the actual count is capped
    # at runtime by free RAM. See app/sysinfo.py.
    "resolver_workers": 2,
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
