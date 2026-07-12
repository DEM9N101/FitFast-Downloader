"""Scrape a fitgirl-repacks.site game page for its FuckingFast part links.

FitGirl posts list the FuckingFast mirror as inline anchors in the exact form
    https://fuckingfast.co/<id>#<Game>_--_fitgirl-repacks.site_--_.partNN.rar
so scraping is just: load the page past Cloudflare, grab every fuckingfast.co
anchor, natural-sort by part number, dedupe.
"""
from __future__ import annotations
import re

from camoufox.sync_api import Camoufox

FITGIRL_HOST_RE = re.compile(r"^https?://(www\.)?fitgirl-repacks\.site/", re.IGNORECASE)
FF_HREF_RE = re.compile(r"https?://fuckingfast\.co/[A-Za-z0-9]+", re.IGNORECASE)
_PART_RE = re.compile(r"\.part(\d+)\.", re.IGNORECASE)
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ScrapeError(Exception):
    pass


class ScrapeResult:
    """Links plus the game title parsed from the page (used for the subfolder)."""
    __slots__ = ("links", "title")

    def __init__(self, links: list[str], title: str | None):
        self.links = links
        self.title = title


def is_fitgirl_url(url: str) -> bool:
    return bool(FITGIRL_HOST_RE.match(url.strip()))


def _base_and_part(url: str) -> tuple[str, int]:
    """Split a link's filename fragment into (base_set_name, part_number).

    A repack can contain several archive sets (main game + bonus content);
    grouping by base name keeps each set contiguous instead of interleaving
    them by part number.
    """
    frag = url.split("#", 1)[1] if "#" in url else url
    m = _PART_RE.search(frag)
    part = int(m.group(1)) if m else 0
    base = frag[: m.start()] if m else frag
    return (base.lower(), part)


def _clean_title(raw: str) -> str | None:
    if not raw:
        return None
    # Strip common WordPress suffixes: " - FitGirl Repacks", " – FitGirl Repacks"
    t = re.split(r"\s+[-–—]\s+FitGirl", raw, maxsplit=1)[0].strip()
    t = _INVALID_CHARS.sub("_", t).strip("._- ")
    return t or None


def scrape_fitgirl_page(page_url: str, timeout_ms: int = 60_000) -> ScrapeResult:
    """Return the sorted, de-duplicated FuckingFast links on a FitGirl repack
    post plus the parsed game title. Raises ScrapeError on failure."""
    page_url = page_url.strip()
    if not is_fitgirl_url(page_url):
        raise ScrapeError("Not a fitgirl-repacks.site URL")

    links: list[str] = []
    title: str | None = None
    try:
        with Camoufox(headless=True, humanize=False, geoip=False) as browser:
            page = browser.new_page()
            page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2500)

            # Expand collapsible spoiler sections if present (links usually live
            # in the DOM regardless, but this is cheap insurance).
            try:
                page.eval_on_selector_all(
                    ".su-spoiler-title, .su-spoiler",
                    "els => els.forEach(e => { try { e.click(); } catch (_) {} })",
                )
                page.wait_for_timeout(500)
            except Exception:
                pass

            # Game title from the H1 (falls back to <title>)
            try:
                h1 = page.eval_on_selector(
                    "h1.entry-title", "e => e.textContent"
                )
                title = _clean_title(h1)
            except Exception:
                title = None
            if not title:
                title = _clean_title(page.title())

            hrefs = page.eval_on_selector_all(
                "a[href*='fuckingfast']",
                "els => els.map(e => e.href)",
            )
            seen: set[str] = set()
            for h in hrefs:
                m = FF_HREF_RE.match(h)
                if not m:
                    continue
                clean = h if "#" in h else m.group(0)
                key = clean.split("#", 1)[0]
                if key in seen:
                    continue
                seen.add(key)
                links.append(clean)
    except ScrapeError:
        raise
    except Exception as e:
        raise ScrapeError(f"Failed to load page: {e}") from e

    if not links:
        raise ScrapeError(
            "No FuckingFast links found on that page. Make sure it's a game "
            "repack page (not the homepage or an 'upcoming' post)."
        )

    links.sort(key=_base_and_part)
    return ScrapeResult(links, title)


def game_title_from_links(links: list[str]) -> str | None:
    """Best-effort game name from the shared filename prefix in the fragments."""
    for l in links:
        if "#" in l:
            frag = l.split("#", 1)[1]
            frag = re.split(r"_--_", frag)[0]  # "Game_--_fitgirl..." -> "Game"
            if frag and "bonus" not in frag.lower() and "optional" not in frag.lower():
                name = frag.replace("_", " ").strip()
                if name:
                    return name
    return None
