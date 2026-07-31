"""Resolve fuckingfast.co URLs to signed direct download URLs via Camoufox.

The flow (confirmed by probing the site 2026-07-12):
  1. Load the page — Camoufox silently passes Cloudflare's JS challenge.
  2. Block ad domains + neuter window.open so popups don't fire.
  3. Click the DOWNLOAD button twice. The second click triggers an HTMX
     POST to /f/<id>/go whose response header `hx-redirect` contains the
     pre-signed https://dl.fuckingfast.co/dl/<token> URL.
  4. That signed URL is Range-capable and needs no cookies to download.
"""
from __future__ import annotations
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from camoufox.sync_api import Camoufox

LINK_RE = re.compile(r"^https?://fuckingfast\.co/[a-z0-9]+", re.IGNORECASE)
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
FIREFOX_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) "
    "Gecko/20100101 Firefox/135.0"
)


class ResolveError(Exception):
    pass


def valid_url(line: str) -> bool:
    return bool(LINK_RE.match(line.strip()))


def sanitize_filename(name: str) -> str:
    cleaned = _INVALID_CHARS.sub("_", name).strip()
    return cleaned or "download.bin"


def filename_from_fragment(url: str) -> str | None:
    if "#" in url:
        frag = url.split("#", 1)[1]
        if frag:
            return sanitize_filename(frag)
    return None


def common_folder_name(filenames: list[str], fallback: str | None = None) -> str:
    """Compute a subfolder name from a list of filenames.

    Strategy: longest common prefix, strip trailing .part\\d* + punctuation,
    sanitize for Windows, fall back to a timestamped name if the result
    is unusable.
    """
    if not filenames:
        return fallback or f"fitgirl_download_{datetime.now():%Y%m%d_%H%M%S}"
    if len(filenames) == 1:
        base = re.sub(r"\.part\d+\.(rar|r\d+|zip|7z)$", "", filenames[0], flags=re.IGNORECASE)
        base = re.sub(r"\.(rar|zip|7z)$", "", base, flags=re.IGNORECASE)
        base = base.strip("._- ")
        if len(base) < 3:
            base = fallback or f"fitgirl_download_{datetime.now():%Y%m%d_%H%M%S}"
        return sanitize_filename(base)

    prefix = filenames[0]
    for name in filenames[1:]:
        while prefix and not name.startswith(prefix):
            prefix = prefix[:-1]
        if not prefix:
            break

    prefix = re.sub(r"\.part\d*$", "", prefix, flags=re.IGNORECASE)
    prefix = prefix.rstrip("._- ")
    if len(prefix) < 3:
        prefix = fallback or f"fitgirl_download_{datetime.now():%Y%m%d_%H%M%S}"
    return sanitize_filename(prefix)


def unique_folder(base_dir: str | Path, name: str) -> Path:
    base = Path(base_dir)
    candidate = base / name
    counter = 2
    while candidate.exists() and any(candidate.iterdir()):
        candidate = base / f"{name} ({counter})"
        counter += 1
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


_AD_KEYWORDS = ("c8yq5.sbs", "doubleclick.net", "googlesyndication",
                "googletagmanager", ".sbs/?tag=", "adservice", "adnxs")

# All we need from the page is a response header, so heavy visual assets are
# dead weight. Blocking these cuts each browser's memory a lot (the main cause
# of the out-of-memory crash) and speeds up resolving, since the page stops
# pulling megabytes of ad imagery.
#
# Stylesheets are deliberately NOT blocked: Playwright refuses to click an
# element it considers invisible, and the download button's visibility can
# depend on CSS. Images/media/fonts are the bulk of the memory anyway.
_BLOCKED_RESOURCE_TYPES = frozenset({"image", "media", "font"})

# Restart a browser after this many resolves. Firefox creeps upward in memory
# over a long batch; a periodic clean restart costs a second and keeps a
# 130-file run flat instead of ballooning.
RECYCLE_AFTER = 25


class Resolver:
    """Single persistent Camoufox browser reused across all resolves."""

    def __init__(self) -> None:
        self._cm = None
        self._browser = None
        self._lock = threading.Lock()
        self._closed = False
        self._resolves_since_start = 0

    def _ensure_browser(self) -> None:
        # Periodic clean restart keeps memory flat over a long batch.
        if self._browser is not None and self._resolves_since_start >= RECYCLE_AFTER:
            self._hard_reset()
        if self._browser is not None:
            return
        self._resolves_since_start = 0
        # humanize=False: fuckingfast.co uses Cloudflare's passive JS challenge,
        # not behavioural analysis, so mouse-movement simulation just slows us
        # down and can push click actions past their timeout on repeat visits.
        self._cm = Camoufox(headless=True, humanize=False, geoip=False)
        self._browser = self._cm.__enter__()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._cm is not None:
                try:
                    self._cm.__exit__(None, None, None)
                except Exception:
                    pass
            self._cm = None
            self._browser = None

    def _hard_reset(self) -> None:
        try:
            if self._cm is not None:
                self._cm.__exit__(None, None, None)
        except Exception:
            pass
        self._cm = None
        self._browser = None

    def resolve(self, url: str, retries: int = 1) -> tuple[str, str]:
        """Return (signed_url, filename). Raises ResolveError on failure."""
        with self._lock:
            if self._closed:
                raise ResolveError("resolver has been closed")
            last_err: Exception | None = None
            for attempt in range(retries + 1):
                try:
                    return self._resolve_once(url)
                except Exception as e:
                    last_err = e
                    self._hard_reset()
                    time.sleep(2.0)
            raise ResolveError(f"resolve failed after retries: {last_err}") from last_err

    def _resolve_once(self, url: str) -> tuple[str, str]:
        self._ensure_browser()
        assert self._browser is not None
        self._resolves_since_start += 1
        page = self._browser.new_page()

        def _route(route):
            try:
                req = route.request
                if req.resource_type in _BLOCKED_RESOURCE_TYPES:
                    route.abort()
                    return
                if any(k in req.url for k in _AD_KEYWORDS):
                    route.abort()
                    return
                route.continue_()
            except Exception:
                # A route can die if the page navigates mid-flight; never let
                # that kill the resolve.
                try:
                    route.continue_()
                except Exception:
                    pass

        page.route("**/*", _route)

        captured: dict = {"signed_url": None}

        def on_response(resp):
            try:
                if "/f/" in resp.url and resp.url.rstrip("/").endswith("/go"):
                    hx = resp.headers.get("hx-redirect") or resp.headers.get("HX-Redirect")
                    if hx:
                        captured["signed_url"] = hx
            except Exception:
                pass

        page.on("response", on_response)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(2500)

            title = ""
            try:
                title = page.title() or ""
            except Exception:
                pass

            try:
                page.evaluate("window.open = function(){ return null; }")
            except Exception:
                pass

            page.click("a.link-button", timeout=30_000)
            page.wait_for_timeout(1200)

            page.click("a.link-button", timeout=30_000)

            deadline = time.time() + 20
            while captured["signed_url"] is None and time.time() < deadline:
                page.wait_for_timeout(200)

            if not captured["signed_url"]:
                raise ResolveError("no hx-redirect header captured after 20s")

            filename = self._pick_filename(url, title)
            return captured["signed_url"], filename
        finally:
            try:
                page.close()
            except Exception:
                pass

    @staticmethod
    def _pick_filename(url: str, title: str) -> str:
        if title and title.strip() and title.strip().lower() not in ("fuckingfast", "fuckingfast.co"):
            return sanitize_filename(title.strip())
        frag = filename_from_fragment(url)
        if frag:
            return frag
        m = re.search(r"/([a-z0-9]+)$", url.split("#", 1)[0])
        return f"{m.group(1) if m else 'download'}.bin"
