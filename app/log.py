"""Logging + crash capture so users can report problems.

Everything the app does of note goes to %APPDATA%/FitFast/logs/fitfast.log.
When something breaks, we can point the user at that file (or show the tail in
the error dialog) so they can paste it into a GitHub issue.
"""
from __future__ import annotations
import logging
import platform
import sys
import traceback
from logging.handlers import RotatingFileHandler

if __package__ in (None, ""):
    from config import LOG_DIR, LOG_FILE, APP_VERSION
else:
    from .config import LOG_DIR, LOG_FILE, APP_VERSION

_logger: logging.Logger | None = None


def setup_logging() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("fitfast")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # Also echo to stderr in dev (harmless no-op when stderr is a null sink).
    try:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    except Exception:
        pass
    logger.info("=" * 60)
    logger.info("FitFast %s starting on %s (%s)", APP_VERSION,
                platform.platform(), sys.version.split()[0])
    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    return _logger or setup_logging()


def log_exception(context: str, exc: BaseException) -> str:
    """Log an exception with traceback. Returns the formatted traceback text."""
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    get_logger().error("Error in %s:\n%s", context, tb)
    return tb


def read_log_tail(max_lines: int = 60) -> str:
    """Return the last ``max_lines`` of the log file, for the error dialog."""
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-max_lines:])
    except Exception:
        return "(no log file yet)"


def environment_summary() -> str:
    """One-line environment string to include in bug reports."""
    return f"FitFast {APP_VERSION} | {platform.platform()} | Python {sys.version.split()[0]}"
