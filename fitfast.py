"""FitFast Downloader — frozen-app entry point.

In a windowed PyInstaller build sys.stdout/sys.stderr are None, which can crash
libraries that print progress (tqdm, click). Give them a harmless sink before
anything else runs.
"""
import sys


class _NullWriter:
    def write(self, *_a, **_k):
        return 0

    def flush(self):
        pass


if sys.stdout is None:
    sys.stdout = _NullWriter()
if sys.stderr is None:
    sys.stderr = _NullWriter()

def _selftest() -> int:
    """Exercise the real pipeline from inside the frozen exe. Prints evidence."""
    import time
    print("frozen:", getattr(sys, "frozen", False))
    from app.paths import VENDOR_DIR
    print("VENDOR_DIR:", VENDOR_DIR)
    from app.downloader import ARIA2_PATH, Downloader
    from app.extractor import find_unrar
    print("aria2c present:", ARIA2_PATH.exists(), ARIA2_PATH)
    print("unrar found:", find_unrar())

    d = Downloader()
    d.start()
    print("aria2c RPC version:", d._rpc("aria2.getVersion").get("version"))
    d.stop()

    from app.resolver import Resolver
    r = Resolver()
    try:
        url = "https://fuckingfast.co/kfjevd8b97ok#test.part01.rar"
        t0 = time.time()
        signed, fname = r.resolve(url)
        print(f"resolved in {time.time()-t0:.1f}s: {fname}")
        print("signed ok:", signed.startswith("https://dl.fuckingfast.co/dl/"))
    finally:
        r.close()
    print("SELFTEST_OK")
    return 0


from app.main import main

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
