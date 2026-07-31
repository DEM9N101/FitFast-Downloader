"""aria2c daemon wrapper using JSON-RPC.

Tuning notes, learned the hard way against fuckingfast.co:

  - ONE connection per file by default. The host answers a bounded range
    request (`Range: bytes=X-Y`) with a Content-Range that claims it will
    stream to the end of the file, even though it then sends exactly the
    requested length. The body is fine, the header is a lie, and aria2
    rejects the mismatch with errorCode=8 ("Invalid range header"). The net
    effect is that every split piece except the first one dies, so a
    multi-connection download is *slower* and eventually fails outright.
    Open-ended ranges (`bytes=X-`) are answered correctly, which is why
    resuming a partial file still works.
  - Throughput therefore comes from downloading MANY FILES at once rather
    than splitting each file into chunks.
  - No --lowest-speed-limit: it converts a temporary slowdown into a hard
    failure.
  - falloc for instant NTFS pre-allocation, 64 MB disk cache to batch writes.
"""
from __future__ import annotations
import io
import os
import socket
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

import requests

if __package__ in (None, ""):
    from paths import VENDOR_DIR
else:
    from .paths import VENDOR_DIR

ARIA2_PATH = VENDOR_DIR / "aria2c.exe"

ARIA2_RELEASE_URL = (
    "https://github.com/aria2/aria2/releases/download/"
    "release-1.37.0/aria2-1.37.0-win-64bit-build1.zip"
)
ARIA2_SHA256 = "67d015301eef0b612191212d564c5bb0a14b5b9c4796b76454276a4d28d9b288"

# Fake a real Firefox UA so origin servers don't fingerprint aria2c
DOWNLOAD_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) "
    "Gecko/20100101 Firefox/135.0"
)


class Aria2NotFound(Exception):
    pass


class Aria2RpcError(Exception):
    pass


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ensure_aria2c() -> Path:
    """Return path to aria2c.exe, downloading it if missing."""
    if ARIA2_PATH.exists():
        return ARIA2_PATH
    VENDOR_DIR.mkdir(parents=True, exist_ok=True)
    import hashlib

    with urllib.request.urlopen(ARIA2_RELEASE_URL, timeout=120) as r:
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != ARIA2_SHA256:
        raise Aria2NotFound(
            f"aria2 zip hash mismatch (expected {ARIA2_SHA256}, got {got})"
        )
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name.endswith("aria2c.exe"):
                with z.open(name) as src, open(ARIA2_PATH, "wb") as dst:
                    dst.write(src.read())
                break
    if not ARIA2_PATH.exists():
        raise Aria2NotFound("aria2c.exe not found in downloaded zip")
    return ARIA2_PATH


class Downloader:
    def __init__(self, connections_per_file: int = 1, concurrent_files: int = 8,
                 log_path: "str | Path | None" = None) -> None:
        self.connections_per_file = max(1, min(32, connections_per_file))
        # Since each file is a single stream, parallelism across files is the
        # only throughput lever, so allow a lot of them.
        self.concurrent_files = max(1, min(24, concurrent_files))
        self.log_path = log_path
        self.proc: subprocess.Popen | None = None
        self.port: int | None = None
        self.secret = "fgdl-" + os.urandom(8).hex()

    def start(self) -> None:
        if self.proc is not None:
            return
        exe = ensure_aria2c()
        self.port = _find_free_port()
        args = [
            str(exe),
            "--enable-rpc=true",
            f"--rpc-listen-port={self.port}",
            f"--rpc-secret={self.secret}",
            "--rpc-listen-all=false",
            "--rpc-allow-origin-all=false",
            f"--max-connection-per-server={self.connections_per_file}",
            f"--split={self.connections_per_file}",
            # Only relevant when splitting is enabled at all (see the class
            # docstring): tiny pieces are pure connection-setup overhead.
            "--min-split-size=4M",
            f"--max-concurrent-downloads={self.concurrent_files}",
            "--file-allocation=falloc",
            "--disk-cache=64M",
            "--continue=true",
            "--auto-file-renaming=false",
            "--allow-overwrite=false",
            "--check-certificate=true",
            # NOTE: deliberately no --lowest-speed-limit. It aborts downloads
            # that dip below the threshold, which turns a temporary CDN slowdown
            # into a hard failure. Slow-but-alive is always better than dead.
            "--console-log-level=warn",
            "--summary-interval=0",
            "--no-conf=true",
            f"--user-agent={DOWNLOAD_UA}",
            "--referer=https://fuckingfast.co/",
            "--max-tries=5",
            "--retry-wait=3",
            "--connect-timeout=15",
            "--timeout=60",
        ]
        if self.log_path is not None:
            args += [f"--log={self.log_path}", "--log-level=notice"]
        creation = 0
        if os.name == "nt":
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation,
        )
        deadline = time.time() + 10
        last_err: Exception | None = None
        while time.time() < deadline:
            try:
                self._rpc("aria2.getVersion")
                return
            except Exception as e:
                last_err = e
                time.sleep(0.2)
        self.stop()
        raise Aria2RpcError(f"aria2c RPC did not start in time: {last_err}")

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            self._rpc("aria2.shutdown")
        except Exception:
            try:
                self.proc.terminate()
            except Exception:
                pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def _rpc(self, method: str, *params):
        assert self.port is not None
        payload = {
            "jsonrpc": "2.0",
            "id": "fgdl",
            "method": method,
            "params": [f"token:{self.secret}"] + list(params),
        }
        r = requests.post(
            f"http://127.0.0.1:{self.port}/jsonrpc", json=payload, timeout=15
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise Aria2RpcError(data["error"])
        return data["result"]

    def add(self, url: str, out_dir: str, filename: str) -> str:
        opts = {
            "dir": str(out_dir),
            "out": filename,
        }
        return self._rpc("aria2.addUri", [url], opts)

    def change_url(self, gid: str, old_url: str, new_url: str) -> None:
        # aria2.changeUri: gid, fileIndex(1-based), delUris, addUris
        self._rpc("aria2.changeUri", gid, 1, [old_url], [new_url])

    def pause(self, gid: str):
        return self._rpc("aria2.pause", gid)

    def unpause(self, gid: str):
        return self._rpc("aria2.unpause", gid)

    def remove(self, gid: str) -> None:
        for method in ("aria2.remove", "aria2.forceRemove"):
            try:
                self._rpc(method, gid)
                break
            except Exception:
                continue
        try:
            self._rpc("aria2.removeDownloadResult", gid)
        except Exception:
            pass

    def status(self, gid: str) -> dict:
        return self._rpc(
            "aria2.tellStatus",
            gid,
            [
                "gid",
                "status",
                "totalLength",
                "completedLength",
                "downloadSpeed",
                "errorMessage",
                "errorCode",
                "connections",
                "numPieces",
                "pieceLength",
                "files",
            ],
        )

    def pause_all(self):
        return self._rpc("aria2.pauseAll")

    def unpause_all(self):
        return self._rpc("aria2.unpauseAll")

    def global_stat(self) -> dict:
        return self._rpc("aria2.getGlobalStat")
