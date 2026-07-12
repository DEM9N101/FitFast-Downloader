"""Post-download RAR extraction via the bundled UnRAR.exe.

FitGirl repacks arrive as multi-volume RAR sets (``*.part01.rar`` …). Pointing
UnRAR at the first volume automatically joins the rest, so we just locate each
first volume in the folder and extract it. Falls back to a system WinRAR/UnRAR
install if the bundled binary is somehow missing.
"""
from __future__ import annotations
import os
import re
import subprocess
import threading
from pathlib import Path

if __package__ in (None, ""):
    from paths import VENDOR_DIR
else:
    from .paths import VENDOR_DIR

BUNDLED_UNRAR = VENDOR_DIR / "UnRAR.exe"

# First volume of a multi-part set: part01 / part001 / part1 (with any digits
# that reduce to 1). Also a plain single-volume .rar with no .partNN.
_FIRST_VOL_RE = re.compile(r"\.part0*1\.rar$", re.IGNORECASE)
_ANY_PART_RE = re.compile(r"\.part\d+\.rar$", re.IGNORECASE)
_PERCENT_RE = re.compile(rb"(\d{1,3})%")

_SYSTEM_CANDIDATES = [
    r"C:\Program Files\WinRAR\UnRAR.exe",
    r"C:\Program Files\WinRAR\Rar.exe",
    r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
    r"C:\Program Files (x86)\WinRAR\Rar.exe",
]


class ExtractError(Exception):
    pass


def find_unrar() -> Path | None:
    if BUNDLED_UNRAR.exists():
        return BUNDLED_UNRAR
    for c in _SYSTEM_CANDIDATES:
        p = Path(c)
        if p.exists():
            return p
    return None


def find_first_volumes(folder: str | Path) -> list[Path]:
    """Return the first-volume archive of every RAR set in ``folder``."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    rars = sorted(folder.glob("*.rar"))
    firsts: list[Path] = []
    for r in rars:
        name = r.name
        if _FIRST_VOL_RE.search(name):
            firsts.append(r)
        elif not _ANY_PART_RE.search(name):
            # A .rar with no .partNN at all == a single-volume archive.
            firsts.append(r)
    return firsts


def extract_archive(
    archive: str | Path,
    dest_dir: str | Path,
    on_progress=None,
    unrar: Path | None = None,
) -> None:
    """Extract one archive (and its sibling volumes) into ``dest_dir``.

    ``on_progress`` is called with an int percentage 0-100 as UnRAR reports it.
    Raises ExtractError on non-zero exit.
    """
    unrar = unrar or find_unrar()
    if unrar is None:
        raise ExtractError(
            "No UnRAR/WinRAR found. Install WinRAR or 7-Zip, or extract the "
            ".rar files manually."
        )
    archive = Path(archive)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # x = extract with full paths, -o+ = overwrite, -y = assume yes,
    # trailing backslash on dest tells UnRAR it's a directory.
    args = [str(unrar), "x", "-o+", "-y", str(archive), str(dest_dir) + os.sep]
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=creation,
    )

    # UnRAR prints "\b\b\b\b45%" style updates; read raw bytes and pull the
    # last percentage we see.
    last_pct = -1
    buf = b""
    assert proc.stdout is not None
    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buf += chunk
        for m in _PERCENT_RE.finditer(buf):
            pct = int(m.group(1))
            if 0 <= pct <= 100 and pct != last_pct:
                last_pct = pct
                if on_progress:
                    try:
                        on_progress(pct)
                    except Exception:
                        pass
        buf = buf[-64:]  # keep tail in case a % straddles a read boundary

    ret = proc.wait()
    if ret != 0:
        raise ExtractError(f"UnRAR exited with code {ret} on {archive.name}")


def extract_all(
    folder: str | Path,
    delete_after: bool = False,
    on_set_start=None,
    on_progress=None,
    on_set_done=None,
) -> tuple[int, int]:
    """Extract every RAR set found in ``folder``.

    Returns (succeeded, failed). Callbacks:
      on_set_start(archive_name, index, total)
      on_progress(percent)
      on_set_done(archive_name, ok, error_or_None)
    """
    firsts = find_first_volumes(folder)
    total = len(firsts)
    ok_count = 0
    fail_count = 0
    for i, archive in enumerate(firsts, 1):
        if on_set_start:
            on_set_start(archive.name, i, total)
        try:
            extract_archive(archive, folder, on_progress=on_progress)
            ok_count += 1
            if on_set_done:
                on_set_done(archive.name, True, None)
            if delete_after:
                _delete_set(archive)
        except ExtractError as e:
            fail_count += 1
            if on_set_done:
                on_set_done(archive.name, False, str(e))
    return ok_count, fail_count


def _delete_set(first_volume: Path) -> None:
    """Delete every volume belonging to a set once it's safely extracted."""
    folder = first_volume.parent
    # part01.rar -> match part\d+.rar with same prefix; else just the file.
    base = re.sub(r"\.part0*1\.rar$", "", first_volume.name, flags=re.IGNORECASE)
    if base != first_volume.name:
        for f in folder.glob(base + ".part*.rar"):
            try:
                f.unlink()
            except OSError:
                pass
    else:
        try:
            first_volume.unlink()
        except OSError:
            pass
