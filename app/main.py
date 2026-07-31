"""Entry point + orchestration. Wires UI to Resolver + Downloader."""
from __future__ import annotations
import queue
import sys
import threading
import time
import traceback
from collections import deque
from pathlib import Path
from tkinter import messagebox

# Support both `python -m app.main` (relative) and `python app/main.py` (absolute)
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app import config as config_mod
    from app.downloader import Downloader, Aria2NotFound, Aria2RpcError
    from app.resolver import (
        Resolver, ResolveError, valid_url, filename_from_fragment,
        common_folder_name, unique_folder, sanitize_filename,
    )
    from app.scraper import scrape_fitgirl_page, game_title_from_links, ScrapeError, is_fitgirl_url
    from app.extractor import extract_all, find_unrar
    from app.log import setup_logging, get_logger, log_exception
    from app.sysinfo import safe_resolver_workers
    from app.ui import MainWindow, format_bytes, format_speed, format_eta
else:
    from . import config as config_mod
    from .downloader import Downloader, Aria2NotFound, Aria2RpcError
    from .resolver import (
        Resolver, ResolveError, valid_url, filename_from_fragment,
        common_folder_name, unique_folder, sanitize_filename,
    )
    from .scraper import scrape_fitgirl_page, game_title_from_links, ScrapeError, is_fitgirl_url
    from .extractor import extract_all, find_unrar
    from .log import setup_logging, get_logger, log_exception
    from .sysinfo import safe_resolver_workers
    from .ui import MainWindow, format_bytes, format_speed, format_eta


class Job:
    __slots__ = ("url", "guess_name", "state", "filename", "signed_url", "gid",
                 "error", "total", "completed", "speed", "reresolve_count",
                 "download_started_at", "permit_held", "retry_count")

    def __init__(self, url: str, guess_name: str):
        self.url = url
        self.guess_name = guess_name
        self.state = "queued"           # queued | resolving | downloading | done | error | paused
        self.filename = guess_name
        self.signed_url: str | None = None
        self.gid: str | None = None
        self.error: str | None = None
        self.total: int = 0
        self.completed: int = 0
        self.speed: int = 0
        self.reresolve_count: int = 0
        self.retry_count: int = 0
        self.download_started_at: float = 0.0
        # True while this job holds an in-flight permit (from first fresh
        # resolve until it reaches a terminal done/error). Keeps a bounded
        # number of freshly-signed URLs alive so they don't expire unused.
        self.permit_held: bool = False


class StallMonitor:
    """Track per-gid throughput and flag files running much slower than peers.

    Rules (kept conservative to avoid re-resolve churn):
      - Need at least 45 s of active downloading before we consider a file
      - Speed averaged over that window
      - Trigger if avg speed < user threshold AND
        (either only 1 file is active, OR the file is < 30% of the fastest peer)
      - Per-job cap of 3 total re-resolves
    """
    WINDOW_S = 45.0
    MIN_ACTIVE_S = 40.0
    RELATIVE_FLOOR = 0.30
    MAX_RERESOLVES = 3

    def __init__(self, absolute_floor_bps: float = 1_048_576.0) -> None:
        self.absolute_floor_bps = absolute_floor_bps
        self.samples: dict[str, deque] = {}

    def set_floor_mbps(self, mbps: float) -> None:
        self.absolute_floor_bps = max(0.0, mbps) * 1_048_576.0

    def record(self, gid: str, completed: int) -> None:
        now = time.time()
        buf = self.samples.setdefault(gid, deque())
        buf.append((now, completed))
        while buf and now - buf[0][0] > self.WINDOW_S:
            buf.popleft()

    def forget(self, gid: str) -> None:
        self.samples.pop(gid, None)

    def _avg_speed(self, gid: str) -> float | None:
        buf = self.samples.get(gid)
        if not buf or len(buf) < 4:
            return None
        oldest_t, oldest_b = buf[0]
        newest_t, newest_b = buf[-1]
        elapsed = newest_t - oldest_t
        if elapsed < self.MIN_ACTIVE_S:
            return None
        return (newest_b - oldest_b) / elapsed if elapsed > 0 else None

    def stalled_gid(self, active_gids: list[str], reresolve_counts: dict[str, int]) -> tuple[str, float] | None:
        """Return (gid, its_avg_speed_bps) for the worst active file if it's stalled.

        Deliberately conservative. A file is only worth swapping when there's
        proof the pipe can do better right now: at least two files are active,
        at least one of them is genuinely fast, and the slow one is far below
        both the absolute floor and that fast peer. If EVERY file is slow, the
        bottleneck is the pipe or the whole CDN, and re-resolving just burns a
        browser for nothing, so we do nothing.
        """
        speeds: dict[str, float] = {}
        for g in active_gids:
            v = self._avg_speed(g)
            if v is not None:
                speeds[g] = v
        if len(speeds) < 2:
            return None
        peak = max(speeds.values())
        # Need a clearly-healthy peer as evidence the line isn't just maxed out.
        if peak < self.absolute_floor_bps * 2:
            return None
        candidates: list[tuple[str, float]] = []
        for g, v in speeds.items():
            if reresolve_counts.get(g, 0) >= self.MAX_RERESOLVES:
                continue
            if v < self.absolute_floor_bps and v < peak * self.RELATIVE_FLOOR:
                candidates.append((g, v))
        if not candidates:
            return None
        candidates.sort(key=lambda t: t[1])
        return candidates[0]


class App:
    POLL_INTERVAL_MS = 500
    # How many times a failed download is given a fresh link before we call it
    # dead. Signed URLs expire and CDN edges drop, so most failures are
    # temporary and worth another go.
    MAX_DOWNLOAD_RETRIES = 3

    def __init__(self) -> None:
        self.config = config_mod.load()
        self.window = MainWindow(self.config)
        self.window.start_button.configure(command=self._on_start)
        self.window.pause_button.configure(command=self._on_pause_toggle)
        self.window.cancel_button.configure(command=self._on_cancel)
        self.window.speedtest_button.configure(command=self._on_speedtest)
        self.window.fetch_button.configure(command=self._on_fetch_fitgirl)
        self.window.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.jobs: list[Job] = []
        self.jobs_lock = threading.Lock()
        self.dest_folder: Path | None = None
        self.paused = False
        self.running = False

        self.resolvers: list[Resolver] = []
        self.downloader: Downloader | None = None
        self.resolve_queue: "queue.Queue[Job]" = queue.Queue()
        self.reresolve_queue: "queue.Queue[Job]" = queue.Queue()
        self.resolver_threads: list[threading.Thread] = []
        self.shutdown_event = threading.Event()
        # Bounds how many freshly-signed URLs may be alive at once, so aria2
        # stays fed but signed links get used before they expire. Sized in
        # _on_start as concurrent_files + resolver_workers.
        self.inflight_sem: threading.Semaphore | None = None
        self._last_reresolve_at: float = 0.0

        self.stall_monitor = StallMonitor(
            absolute_floor_bps=float(self.config.get("stall_threshold_mbps", 1.0)) * 1_048_576.0,
        )
        self.reresolve_counts: dict[str, int] = {}   # gid -> count (of the ACTIVE gid; ephemeral)
        self._peak_agg_speed: int = int(self.config.get("peak_speed_bps") or 0)
        self._speedtest_thread: threading.Thread | None = None
        self._speedtest_stop = threading.Event()
        self._fetch_thread: threading.Thread | None = None
        self._extract_thread: threading.Thread | None = None

    def _tk_exception(self, exc_type, exc_value, exc_tb) -> None:
        """Catch-all for exceptions raised inside Tk callbacks."""
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        get_logger().error("Unhandled UI error:\n%s", tb)
        try:
            self.window.show_error_report(
                "using the app",
                "FitFast hit an unexpected error. It has been written to the log. "
                "You can keep using the app, but if this happens again please report it.",
                tb,
            )
        except Exception:
            pass

    def run(self) -> None:
        setup_logging()
        # Route every uncaught Tk-callback error into our friendly dialog + log.
        self.window.root.report_callback_exception = self._tk_exception
        # First-time setup: fetch the Camoufox browser if it isn't installed yet.
        try:
            from app.bootstrap import browser_ready, ensure_browser
        except ImportError:
            from .bootstrap import browser_ready, ensure_browser
        if not browser_ready():
            self.window.root.update()
            ok = self.window.run_first_time_setup(ensure_browser)
            if not ok:
                self.window.set_status_bar(
                    "First-time setup didn't finish. Relaunch to try again."
                )
        self.window.set_status_bar("Ready. Paste a FitGirl page or FuckingFast links, then Start.")
        self.window.root.after(self.POLL_INTERVAL_MS, self._tick)
        try:
            self.window.root.mainloop()
        finally:
            self._teardown()

    def _on_fetch_fitgirl(self) -> None:
        """Scrape a FitGirl game page for all its FuckingFast links (threaded)."""
        if self.running:
            return
        if self._fetch_thread is not None and self._fetch_thread.is_alive():
            return
        url = self.window.get_fitgirl_url()
        if not url:
            messagebox.showinfo(
                "Paste a FitGirl page",
                "Paste a fitgirl-repacks.site game page URL first, then click Fetch links.",
            )
            return
        if not is_fitgirl_url(url):
            messagebox.showerror(
                "Not a FitGirl URL",
                "That doesn't look like a fitgirl-repacks.site link. Paste the game's "
                "page URL (e.g. https://fitgirl-repacks.site/some-game/).",
            )
            return
        self.window.set_fetch_state(True)
        self.window.set_status_bar("Fetching links from FitGirl (passing Cloudflare)...")
        self._fetch_thread = threading.Thread(
            target=self._fetch_worker, args=(url,), daemon=True, name="fitgirl-fetch",
        )
        self._fetch_thread.start()

    def _fetch_worker(self, url: str) -> None:
        get_logger().info("Fetching FitGirl page: %s", url)
        try:
            result = scrape_fitgirl_page(url)
        except ScrapeError as e:
            self._schedule_ui(lambda: self._fetch_done(None, None, str(e), ""))
            return
        except Exception as e:
            tb = log_exception("fetching FitGirl page", e)
            self._schedule_ui(lambda: self._fetch_done(None, None, str(e), tb))
            return
        # Prefer the clean game name from filenames, fall back to page title.
        subfolder = game_title_from_links(result.links) or result.title or ""
        get_logger().info("Fetched %d links (%s)", len(result.links), subfolder or "no title")
        self._schedule_ui(lambda: self._fetch_done(result.links, subfolder, None, ""))

    def _fetch_done(self, links, subfolder, error, details="") -> None:
        self.window.set_fetch_state(False)
        if error:
            self.window.set_status_bar("Fetch failed.")
            self.window.show_toast("Couldn't fetch links from that page", "error")
            self.window.show_error_report(
                "fetching links from a FitGirl page",
                "FitFast couldn't get the download links from that page. "
                + error
                + "\n\nMake sure the address is a FitGirl game page (not the homepage or an "
                "'upcoming' post), and that you are connected to the internet.",
                details,
            )
            return
        self.window.set_links_text("\n".join(links))
        if subfolder:
            self.window.set_subfolder(subfolder)
        name = f" for {subfolder}" if subfolder else ""
        self.window.set_status_bar(
            f"Fetched {len(links)} link(s). Review, pick a folder, then Start Downloads."
        )
        self.window.show_toast(f"Fetched {len(links)} links{name}. Ready to download.", "success")

    def _on_start(self) -> None:
        if self.running:
            return

        raw_lines = self.window.get_links()
        urls: list[str] = []
        skipped = 0
        for line in raw_lines:
            if line.startswith("#"):
                continue
            if valid_url(line):
                urls.append(line.split()[0])
            elif line:
                skipped += 1

        if not urls:
            messagebox.showerror(
                "No valid links",
                "Paste at least one fuckingfast.co URL and try again.",
            )
            return

        dest_root = self.window.get_destination()
        if not dest_root:
            messagebox.showerror("Missing destination", "Choose a destination folder.")
            return
        dest_root_path = Path(dest_root).expanduser()
        try:
            dest_root_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Destination not writable", f"{e}")
            return

        # Compute subfolder name from URL fragments upfront so downloads
        # start immediately (before Camoufox even resolves).
        guessed_names = [filename_from_fragment(u) or "" for u in urls]
        guessed_names = [n for n in guessed_names if n]
        override = self.window.get_subfolder_override()
        if override:
            subfolder_name = sanitize_filename(override)
        else:
            subfolder_name = common_folder_name(guessed_names)

        try:
            self.dest_folder = unique_folder(dest_root_path, subfolder_name)
        except OSError as e:
            messagebox.showerror("Cannot create subfolder", f"{e}")
            return

        # Persist choices
        self.config["destination"] = str(dest_root_path)
        self.config["connections_per_file"] = self.window.get_connections()
        self.config["concurrent_files"] = self.window.get_concurrent()
        self.config["resolver_workers"] = self.window.get_resolver_workers()
        self.config["auto_reresolve"] = self.window.get_auto_reresolve()
        self.config["auto_extract"] = self.window.get_auto_extract()
        self.config["delete_archives_after"] = self.window.get_delete_after()
        config_mod.save(self.config)

        # Build jobs & UI rows
        self.window.clear_rows()
        with self.jobs_lock:
            self.jobs.clear()
            for i, u in enumerate(urls):
                guess = filename_from_fragment(u) or f"part{i+1:02d}.bin"
                job = Job(u, guess)
                self.jobs.append(job)
                row = self.window.add_row(str(id(job)), guess, u)
                row.set_status("Queued")

        # Boot downloader + resolver
        try:
            aria2_log = None
            try:
                config_mod.LOG_DIR.mkdir(parents=True, exist_ok=True)
                aria2_log = config_mod.LOG_DIR / "aria2.log"
            except Exception:
                aria2_log = None
            self.downloader = Downloader(
                connections_per_file=self.window.get_connections(),
                concurrent_files=self.window.get_concurrent(),
                log_path=aria2_log,
            )
            self.downloader.start()
        except (Aria2NotFound, Aria2RpcError) as e:
            tb = log_exception("starting the download engine", e)
            self.window.show_error_report(
                "starting the download engine",
                "FitFast couldn't start its download engine (aria2c). This usually means "
                "an antivirus blocked it or the app files are incomplete. Try reinstalling, "
                "and add an antivirus exception for FitFast if needed.",
                tb,
            )
            self.downloader = None
            return
        get_logger().info("Starting %d download(s) into %s", len(self.jobs), self.dest_folder)

        self.shutdown_event.clear()
        # Reset per-session tuning state
        self.stall_monitor = StallMonitor(
            absolute_floor_bps=float(self.config.get("stall_threshold_mbps", 1.0)) * 1_048_576.0,
        )
        self.reresolve_counts.clear()
        self._last_reresolve_at = 0.0
        # Drain any leftover items from a previous session
        for q in (self.resolve_queue, self.reresolve_queue):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        with self.jobs_lock:
            for job in self.jobs:
                job.permit_held = False
                self.resolve_queue.put(job)

        # Parallel resolver pool. More browsers => links get resolved fast
        # enough to keep the downloader saturated instead of starving it.
        # Each browser is a real Firefox, so the count is capped by free RAM:
        # a too-eager pool is what takes the whole machine down.
        n_workers, ram_note = safe_resolver_workers(
            self.window.get_resolver_workers(), len(self.jobs)
        )
        if ram_note:
            get_logger().warning("Resolver pool reduced: %s", ram_note)
            self.window.show_toast(ram_note, "info", 7000)
        concurrent = self.window.get_concurrent()
        # Allow a little prefetch beyond the active download slots so a worker
        # always has somewhere to put a freshly-resolved URL.
        self.inflight_sem = threading.BoundedSemaphore(concurrent + n_workers)
        self.resolvers = []
        self.resolver_threads = []
        for i in range(n_workers):
            r = Resolver()
            self.resolvers.append(r)
            t = threading.Thread(
                target=self._resolver_loop, args=(r,),
                name=f"resolver-{i+1}", daemon=True,
            )
            t.start()
            self.resolver_threads.append(t)

        self.running = True
        self.paused = False
        self.window.set_downloading_state(True)
        self.window.set_status_bar(
            f"Downloading {len(self.jobs)} file(s) to {self.dest_folder}"
        )
        if skipped:
            self.window.set_status_bar(
                self.window.status_bar.cget("text")
                + f" (skipped {skipped} invalid line(s))"
            )

    def _resolver_loop(self, resolver: "Resolver") -> None:
        """One worker: owns a single browser. Re-resolves (which already hold an
        in-flight permit) always take priority; fresh jobs are only picked up
        once a permit is free, which paces resolving to just ahead of the
        downloads and keeps signed URLs from expiring unused.
        """
        while not self.shutdown_event.is_set():
            # 1) Re-resolves first. They already hold a permit, so no gating.
            try:
                job = self.reresolve_queue.get_nowait()
                self._handle_resolve(resolver, job, is_reresolve=True)
                continue
            except queue.Empty:
                pass

            # 2) Fresh job, but only if we can reserve an in-flight slot.
            sem = self.inflight_sem
            if sem is None:
                return
            if not sem.acquire(timeout=0.3):
                continue  # pipeline full; loop back and re-check re-resolves
            try:
                job = self.resolve_queue.get(timeout=0.3)
            except queue.Empty:
                sem.release()  # nothing to do; hand the slot back
                continue
            job.permit_held = True
            self._handle_resolve(resolver, job, is_reresolve=False)

    def _handle_resolve(self, resolver: "Resolver", job: "Job", is_reresolve: bool) -> None:
        if self.shutdown_event.is_set() or job is None:
            return
        status_text = "Re-resolving (was slow)..." if is_reresolve else "Resolving..."
        self._set_state(job, "resolving", status_text)

        try:
            signed_url, filename = resolver.resolve(job.url)
        except (ResolveError, Exception) as e:
            self._set_state(job, "error", f"Error: {e}", error=str(e))
            self._release_permit(job)
            return

        job.signed_url = signed_url
        # On re-resolve, preserve the existing filename so aria2 finds the
        # .aria2 control file and resumes; on fresh resolve, adopt the new one.
        if is_reresolve:
            target_filename = job.filename
        else:
            job.filename = filename
            target_filename = filename
            self._schedule_ui(lambda j=job: self._rename_row(j))

        try:
            gid = self.downloader.add(signed_url, str(self.dest_folder), target_filename)
        except Exception as e:
            self._set_state(job, "error", f"aria2 add failed: {e}", error=str(e))
            self._release_permit(job)
            return
        job.gid = gid
        job.download_started_at = time.time()
        self._set_state(job, "downloading", "Resuming..." if is_reresolve else "Starting...")

    def _release_permit(self, job: "Job") -> None:
        """Release a job's in-flight permit exactly once."""
        if job.permit_held:
            job.permit_held = False
            if self.inflight_sem is not None:
                try:
                    self.inflight_sem.release()
                except Exception:
                    pass

    def _rename_row(self, job: Job) -> None:
        row = self.window.rows.get(str(id(job)))
        if row is not None:
            row.name_label.configure(text=job.filename)
            row.filename = job.filename

    def _set_state(self, job: Job, state: str, status_text: str, error: str | None = None) -> None:
        job.state = state
        if error is not None:
            job.error = error
        color = None
        if state == "error":
            color = "#ff6b6b"
        elif state == "done":
            color = "#00c853"
        elif state == "downloading":
            color = "#42a5f5"
        elif state == "resolving":
            color = "#ffa726"
        self._schedule_ui(lambda: self._apply_row_state(job, status_text, color))

    def _apply_row_state(self, job: Job, status_text: str, color: str | None) -> None:
        row = self.window.rows.get(str(id(job)))
        if row is None:
            return
        row.set_status(status_text, color)

    def _schedule_ui(self, fn) -> None:
        try:
            self.window.root.after(0, fn)
        except Exception:
            pass

    def _tick(self) -> None:
        try:
            self._poll_and_update()
        except Exception:
            traceback.print_exc()
        finally:
            self.window.root.after(self.POLL_INTERVAL_MS, self._tick)

    def _poll_and_update(self) -> None:
        if not self.running or self.downloader is None:
            return

        total_completed = 0
        done_bytes = 0
        agg_speed = 0
        done_count = 0
        error_count = 0
        resolved_count = 0
        active_gids: list[str] = []

        with self.jobs_lock:
            jobs = list(self.jobs)

        for job in jobs:
            if job.state in ("done", "error"):
                self._release_permit(job)
                if job.state == "done":
                    done_count += 1
                    resolved_count += 1
                    done_bytes += job.total
                    total_completed += job.total
                elif job.state == "error":
                    error_count += 1
                continue

            if job.gid is None:
                continue
            resolved_count += 1

            try:
                st = self.downloader.status(job.gid)
            except Exception:
                continue

            job.total = int(st.get("totalLength") or 0)
            job.completed = int(st.get("completedLength") or 0)
            job.speed = int(st.get("downloadSpeed") or 0)
            status = st.get("status", "")
            err_msg = st.get("errorMessage") or ""

            total_completed += job.completed
            agg_speed += job.speed

            if status == "active" and job.gid:
                self.stall_monitor.record(job.gid, job.completed)
                active_gids.append(job.gid)

            row = self.window.rows.get(str(id(job)))
            if row is not None:
                frac = (job.completed / job.total) if job.total else 0
                row.set_progress(frac)
                if job.total:
                    pct = frac * 100
                    if job.speed > 0:
                        eta = (job.total - job.completed) / job.speed
                        stats = (
                            f"{format_bytes(job.completed)} / {format_bytes(job.total)}"
                            f"  •  {format_speed(job.speed)}  •  ETA {format_eta(eta)}"
                        )
                    else:
                        stats = f"{format_bytes(job.completed)} / {format_bytes(job.total)}"
                    row.set_stats(stats)
                    if status == "active":
                        row.set_status(f"{pct:.1f}%", "#42a5f5")

                if status == "complete":
                    row.set_progress(1.0)
                    row.set_status("Done", "#00c853")
                    row.set_stats(f"{format_bytes(job.total)}  •  Complete")
                    job.state = "done"
                    if job.gid:
                        self.stall_monitor.forget(job.gid)
                    self._release_permit(job)
                elif status == "error":
                    if job.gid:
                        self.stall_monitor.forget(job.gid)
                    # A failed download is usually recoverable: signed URLs go
                    # stale and CDN edges drop out. Get a fresh link and resume
                    # from the partial rather than writing the file off.
                    if job.retry_count < self.MAX_DOWNLOAD_RETRIES:
                        job.retry_count += 1
                        row.set_status(
                            f"Retrying ({job.retry_count}/{self.MAX_DOWNLOAD_RETRIES})...",
                            "#ffa726",
                        )
                        row.set_stats(err_msg or "download failed, getting a fresh link")
                        get_logger().warning(
                            "Download failed (%s), retry %d/%d: %s",
                            err_msg or "unknown", job.retry_count,
                            self.MAX_DOWNLOAD_RETRIES, job.filename,
                        )
                        try:
                            self.downloader.remove(job.gid)
                        except Exception:
                            pass
                        job.gid = None
                        job.signed_url = None
                        job.state = "resolving"
                        self.reresolve_queue.put(job)
                    else:
                        row.set_status("Error", "#ff6b6b")
                        row.set_stats(err_msg or "aria2 reported error")
                        job.state = "error"
                        job.error = err_msg
                        self._release_permit(job)
                elif status == "paused":
                    row.set_status("Paused", "#bdbdbd")
                elif status == "waiting":
                    row.set_status("Waiting", "#bdbdbd")

        # Track peak aggregate — useful for the user to know what the pipe can do
        if agg_speed > self._peak_agg_speed:
            self._peak_agg_speed = agg_speed
            self.config["peak_speed_bps"] = agg_speed

        # Auto re-resolve: swap the slowest badly-underperforming file for a
        # fresh signed URL. aria2's .aria2 control file lets it resume. Gated by
        # a cooldown so we never swap more than one file every 15 s (avoids the
        # thrash where a starved batch murders its own downloads).
        if (self.window.get_auto_reresolve() and active_gids
                and time.time() - self._last_reresolve_at > 15.0):
            stalled = self.stall_monitor.stalled_gid(active_gids, self.reresolve_counts)
            if stalled is not None:
                stalled_gid, avg_bps = stalled
                target_job = next((j for j in jobs if j.gid == stalled_gid), None)
                if target_job is not None:
                    self._trigger_reresolve(target_job, avg_bps)
                    self._last_reresolve_at = time.time()

        active = len(jobs) - done_count - error_count
        # Honest totals: total_completed is real downloaded bytes. We can't know
        # the size of files not yet resolved, so we show files done/total and
        # bytes downloaded rather than a fake "of X GB" that only counted the
        # handful resolved so far. ETA is estimated from the average size of the
        # files that HAVE finished, once we have at least one.
        status_line = (
            f"{done_count}/{len(jobs)} files done"
            + (f", {error_count} failed" if error_count else "")
            + f"  •  resolved {resolved_count}/{len(jobs)}"
            + f"  •  {format_bytes(total_completed)} downloaded"
            + f"  •  {format_speed(agg_speed)} now"
            + f"  •  peak {format_speed(self._peak_agg_speed)}"
        )
        if done_count > 0 and agg_speed > 0:
            avg_size = done_bytes / done_count
            remaining_files = max(0, len(jobs) - done_count - error_count)
            active_partial = total_completed - done_bytes
            remaining_bytes = max(0.0, avg_size * remaining_files - active_partial)
            if remaining_bytes > 0:
                status_line += f"  •  ETA {format_eta(remaining_bytes / agg_speed)}"
        self.window.set_status_bar(status_line)

        if active == 0 and self.running:
            self._all_finished(done_count, error_count)

    def _trigger_reresolve(self, job: Job, avg_bps: float) -> None:
        """Kill an underperforming download and re-queue it for a fresh signed URL."""
        if job.gid is None or job.state != "downloading":
            return
        old_gid = job.gid
        self.reresolve_counts[old_gid] = self.reresolve_counts.get(old_gid, 0) + 1
        job.reresolve_count += 1
        self.stall_monitor.forget(old_gid)

        try:
            self.downloader.remove(old_gid)
        except Exception:
            pass

        job.gid = None
        job.signed_url = None

        row = self.window.rows.get(str(id(job)))
        if row is not None:
            row.set_status(
                f"Slow ({format_speed(avg_bps)}), swapping to a faster server...",
                "#ffa726",
            )
        self.reresolve_queue.put(job)

    def _all_finished(self, done_count: int, error_count: int, extract_ok: bool = True) -> None:
        self.running = False
        self.window.set_downloading_state(False)
        summary = f"All done. {done_count} succeeded"
        if error_count:
            summary += f", {error_count} failed"
        summary += f". Saved to {self.dest_folder}"
        self.window.set_status_bar(summary)
        get_logger().info("Batch finished: %d ok, %d failed", done_count, error_count)
        # Cleanup workers
        try:
            self.shutdown_event.set()
            if self.resolvers:
                resolvers = self.resolvers
                self.resolvers = []
                for r in resolvers:
                    threading.Thread(target=r.close, daemon=True).start()
            self.resolver_threads = []
            if self.downloader is not None:
                threading.Thread(target=self.downloader.stop, daemon=True).start()
                self.downloader = None
        except Exception:
            pass

        will_extract = (
            extract_ok
            and done_count > 0
            and self.dest_folder is not None
            and self.window.get_auto_extract()
            and find_unrar() is not None
        )
        if extract_ok and done_count > 0:
            if error_count == 0:
                self.window.show_toast(
                    f"All {done_count} files downloaded"
                    + (". Unzipping now…" if will_extract else "."),
                    "success",
                )
            else:
                self.window.show_toast(
                    f"{done_count} downloaded, {error_count} failed. "
                    "Re-run to retry the failed ones.",
                    "info", 6000,
                )

        # Auto-extract the downloaded archives, if enabled and anything succeeded.
        if will_extract:
            self._start_extraction()

    def _start_extraction(self) -> None:
        if self._extract_thread is not None and self._extract_thread.is_alive():
            return
        if find_unrar() is None:
            self.window.set_status_bar(
                "Downloads done. Skipping extraction: no UnRAR/WinRAR found."
            )
            return
        folder = self.dest_folder
        delete_after = self.window.get_delete_after()
        self.window.set_downloading_state(True)  # keep controls locked during extract
        self.window.pause_button.configure(state="disabled")
        self.window.cancel_button.configure(state="disabled")
        self._extract_thread = threading.Thread(
            target=self._extract_worker, args=(folder, delete_after), daemon=True,
            name="extractor",
        )
        self._extract_thread.start()

    def _extract_worker(self, folder, delete_after) -> None:
        state = {"i": 0, "total": 0, "name": ""}

        def on_start(name, i, total):
            state.update(i=i, total=total, name=name)
            self._schedule_ui(lambda: self.window.set_status_bar(
                f"Extracting [{i}/{total}] {name} ..."
            ))

        def on_prog(pct):
            self._schedule_ui(lambda: self.window.set_status_bar(
                f"Extracting [{state['i']}/{state['total']}] {state['name']}  •  {pct}%"
            ))

        def on_done(name, ok, err):
            if not ok:
                self._schedule_ui(lambda: self.window.set_status_bar(
                    f"Extract failed for {name}: {err}"
                ))

        toast_kind = "success"
        toast_msg = ""
        try:
            ok, fail = extract_all(
                folder, delete_after=delete_after,
                on_set_start=on_start, on_progress=on_prog, on_set_done=on_done,
            )
            msg = f"Extraction complete: {ok} archive set(s) unpacked"
            if fail:
                msg += f", {fail} failed"
            msg += f". Ready in {folder}"
            get_logger().info("Extraction: %d ok, %d failed", ok, fail)
            if fail:
                toast_kind = "info"
                toast_msg = f"Unzipped {ok} set(s), {fail} failed. Your files are in the game folder."
            else:
                toast_msg = "Done. Game unzipped and ready to install."
        except Exception as e:
            log_exception("extracting archives", e)
            msg = f"Extraction error: {e}"
            toast_kind = "error"
            toast_msg = "Downloads finished, but unzipping failed. You can unzip the .rar files by hand."

        def finish():
            self.window.set_downloading_state(False)
            self.window.set_status_bar(msg)
            if toast_msg:
                self.window.show_toast(toast_msg, toast_kind, 6000)

        self._schedule_ui(finish)

    def _on_pause_toggle(self) -> None:
        if self.downloader is None:
            return
        try:
            if self.paused:
                self.downloader.unpause_all()
                self.paused = False
            else:
                self.downloader.pause_all()
                self.paused = True
            self.window.set_paused_state(self.paused)
        except Exception as e:
            messagebox.showerror("Pause/Resume failed", str(e))

    def _on_cancel(self) -> None:
        if not self.running:
            return
        if not messagebox.askyesno(
            "Cancel downloads?",
            "Stop all downloads? Partial files will be kept, so you can resume later "
            "by pasting the same links back.",
        ):
            return
        self.shutdown_event.set()
        if self.downloader is not None:
            try:
                self.downloader.pause_all()
            except Exception:
                pass
            with self.jobs_lock:
                for job in self.jobs:
                    if job.gid:
                        try:
                            self.downloader.remove(job.gid)
                        except Exception:
                            pass
        self._all_finished(
            done_count=sum(1 for j in self.jobs if j.state == "done"),
            error_count=sum(1 for j in self.jobs if j.state == "error"),
            extract_ok=False,
        )
        self.window.set_status_bar("Cancelled.")

    def _on_speedtest(self) -> None:
        """Run a ~15s download from Cloudflare's public speedtest to gauge the pipe.

        Uses a temporary aria2c instance so it doesn't interfere with anything.
        """
        if self._speedtest_thread is not None and self._speedtest_thread.is_alive():
            return
        self.window.speedtest_button.configure(state="disabled", text="Testing...")
        self._speedtest_stop.clear()
        self._speedtest_thread = threading.Thread(
            target=self._speedtest_worker, daemon=True, name="speedtest",
        )
        self._speedtest_thread.start()

    def _speedtest_worker(self) -> None:
        """Download a large chunk from speed.cloudflare.com for ~15s, report peak."""
        import tempfile

        test_url = "https://speed.cloudflare.com/__down?bytes=800000000"  # 800 MB
        peak_bps = 0
        avg_bps = 0
        error: str | None = None
        tmpdir = tempfile.mkdtemp(prefix="fgdl-speedtest-")
        d = Downloader(connections_per_file=16, concurrent_files=1)
        try:
            self._schedule_ui(
                lambda: self.window.set_status_bar(
                    "Speed test: booting aria2c..."
                )
            )
            d.start()
            gid = d.add(test_url, tmpdir, "cf_speedtest.bin")
            deadline = time.time() + 15.0
            while time.time() < deadline and not self._speedtest_stop.is_set():
                time.sleep(0.5)
                try:
                    st = d.status(gid)
                except Exception:
                    continue
                spd = int(st.get("downloadSpeed") or 0)
                done = int(st.get("completedLength") or 0)
                if spd > peak_bps:
                    peak_bps = spd
                self._schedule_ui(
                    lambda spd=spd, done=done: self.window.set_status_bar(
                        f"Speed test: {format_speed(spd)}  •  {format_bytes(done)} downloaded"
                    )
                )
                if st.get("status") == "complete":
                    break
            # Compute average over the last 10 s using aria2's completedLength
            try:
                st = d.status(gid)
                done_final = int(st.get("completedLength") or 0)
                avg_bps = done_final / 15.0
            except Exception:
                pass
            try:
                d.remove(gid)
            except Exception:
                pass
        except Exception as e:
            error = str(e)
        finally:
            try:
                d.stop()
            except Exception:
                pass
            try:
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

        def finish():
            self.window.speedtest_button.configure(state="normal", text="Test my pipe")
            if error:
                self.window.set_status_bar(f"Speed test failed: {error}")
                messagebox.showerror("Speed test failed", error)
                return
            msg = (
                f"Cloudflare speed test: peak {format_speed(peak_bps)}"
                f", avg over test {format_speed(avg_bps)}."
            )
            self.window.set_status_bar(msg)
            interpretation = (
                "This is what your ISP + local network can sustain to a fast CDN.\n\n"
                "If your fuckingfast downloads run much slower than this, the "
                "bottleneck is fuckingfast's CDN edges (not your pipe). "
                "Auto re-resolve will swap slow edges for you.\n\n"
                "If the fuckingfast download matches this speed, your pipe is "
                "already maxed and there's no faster path."
            )
            messagebox.showinfo("Speed test result", f"{msg}\n\n{interpretation}")

        self._schedule_ui(finish)

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno(
                "Quit while downloading?",
                "Downloads are in progress. Quit anyway? "
                "Partial files will be kept and can be resumed.",
            ):
                return
        try:
            self.config["window_geometry"] = self.window.root.winfo_geometry()
            config_mod.save(self.config)
        except Exception:
            pass
        self._teardown()
        try:
            self.window.root.destroy()
        except Exception:
            pass

    def _teardown(self) -> None:
        self.shutdown_event.set()
        self._speedtest_stop.set()
        try:
            if self.downloader is not None:
                self.downloader.stop()
        except Exception:
            pass
        try:
            for r in self.resolvers:
                try:
                    r.close()
                except Exception:
                    pass
            self.resolvers = []
        except Exception:
            pass


def main() -> int:
    try:
        setup_logging()
    except Exception:
        pass
    try:
        App().run()
        return 0
    except Exception as e:
        try:
            tb = log_exception("app startup", e)
        except Exception:
            tb = traceback.format_exc()
        traceback.print_exc()
        try:
            from tkinter import Tk
            from app.config import LOG_FILE
            messagebox.showerror(
                "FitFast could not start",
                f"{e}\n\nDetails were written to:\n{LOG_FILE}\n\n"
                "Please report this at the project's GitHub issues page and attach that file.",
            )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
