"""First-run setup: make sure the Camoufox stealth browser is installed.

The browser (~a few hundred MB) is NOT bundled in the release — it's fetched
once on first launch into the per-user Camoufox cache. Subsequent launches see
it and skip straight to the app.
"""
from __future__ import annotations


def browser_ready() -> bool:
    """True if the Camoufox browser is already installed for this user."""
    try:
        from camoufox.pkgman import installed_verstr
        installed_verstr()
        return True
    except Exception:
        return False


def ensure_browser(status_cb=None) -> None:
    """Download + install the Camoufox browser if missing or outdated.

    ``status_cb(str)`` receives human-readable progress lines. Raises on hard
    failure (caller should surface it).
    """
    def say(msg: str) -> None:
        if status_cb:
            try:
                status_cb(msg)
            except Exception:
                pass

    from camoufox.__main__ import CamoufoxUpdate

    upd = CamoufoxUpdate()
    if upd.is_updated_needed():
        say("Downloading the stealth browser (one-time, a few hundred MB)…")
        upd.update()
        say("Browser installed.")
    else:
        say("Browser already installed.")

    # GeoIP DB (optional; flaky download — never fatal)
    try:
        from camoufox.locale import ALLOW_GEOIP, download_mmdb
        if ALLOW_GEOIP:
            say("Fetching GeoIP database…")
            download_mmdb()
    except Exception:
        pass

    # Default addons (best effort)
    try:
        from camoufox.addons import DefaultAddons, maybe_download_addons
        say("Fetching browser add-ons…")
        maybe_download_addons(list(DefaultAddons))
    except Exception:
        pass

    say("Setup complete.")
