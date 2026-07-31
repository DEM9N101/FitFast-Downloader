"""Machine capability probes used to size FitFast's workers safely.

Each resolver runs a real Firefox (Camoufox), which costs hundreds of MB. On a
machine that is already busy, spawning too many is how you take the whole PC
down. These helpers let us pick a worker count the machine can actually afford
instead of trusting a fixed default.

Deliberately dependency-free: ctypes on Windows, /proc on Linux, and a safe
"unknown" answer everywhere else.
"""
from __future__ import annotations
import os

# Rough resident cost of one Camoufox instance. A real Firefox with a live page
# can pass 1 GB, and it grows while it runs, so we budget high on purpose:
# under-committing costs a little speed, over-committing takes the PC down.
BROWSER_BUDGET_MB = 900

# Never eat the machine's last reserves. Windows, aria2's cache, and whatever
# the user has open all need room, and free RAM drops once downloads ramp up.
HEADROOM_MB = 3072


def available_ram_mb() -> int | None:
    """Free physical RAM in MB, or None if we cannot tell."""
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return None
            return int(stat.ullAvailPhys // (1024 * 1024))
        except Exception:
            return None
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


def safe_resolver_workers(requested: int, jobs: int) -> tuple[int, str | None]:
    """Clamp the requested resolver count to what this machine can afford.

    Returns (workers, note). `note` is a short, plain-language explanation when
    we reduced the number, so the UI can tell the user why instead of silently
    behaving differently from their setting.
    """
    workers = max(1, min(requested, max(1, jobs)))
    if workers <= 1:
        return workers, None

    avail = available_ram_mb()
    if avail is None:
        return workers, None

    affordable = int((avail - HEADROOM_MB) // BROWSER_BUDGET_MB)
    if affordable < 1:
        affordable = 1
    if affordable >= workers:
        return workers, None

    note = (
        f"Using {affordable} link preparer(s) instead of {workers}: only "
        f"{avail // 1024} GB of memory is free right now. Close some apps for more speed."
    )
    return affordable, note
