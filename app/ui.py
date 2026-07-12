"""CustomTkinter UI widgets. Pure view code — no orchestration."""
from __future__ import annotations
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk


ctk.set_default_color_theme("blue")


def format_bytes(n: float) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def format_speed(bps: float) -> str:
    return f"{format_bytes(bps)}/s"


def format_eta(seconds: float) -> str:
    if seconds is None or seconds <= 0 or seconds > 24 * 3600:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class JobRow(ctk.CTkFrame):
    """One download row: filename, status badge, progress bar, stats."""

    def __init__(self, master, filename: str, url: str):
        super().__init__(master, fg_color="transparent")
        self.filename = filename
        self.url = url

        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 0))
        top.grid_columnconfigure(0, weight=1)

        self.name_label = ctk.CTkLabel(
            top, text=filename, anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.name_label.grid(row=0, column=0, sticky="ew")

        self.status_label = ctk.CTkLabel(top, text="Queued", anchor="e", width=110)
        self.status_label.grid(row=0, column=1, sticky="e")

        self.progress = ctk.CTkProgressBar(self, height=8)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", padx=6, pady=(4, 2))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=6, pady=(0, 4))
        bottom.grid_columnconfigure(0, weight=1)

        self.stats_label = ctk.CTkLabel(
            bottom, text="", anchor="w",
            font=ctk.CTkFont(size=10),
            text_color=("gray30", "gray70"),
        )
        self.stats_label.grid(row=0, column=0, sticky="ew")

    def set_status(self, text: str, color: str | None = None) -> None:
        self.status_label.configure(text=text)
        if color:
            self.status_label.configure(text_color=color)

    def set_progress(self, fraction: float) -> None:
        self.progress.set(max(0.0, min(1.0, fraction)))

    def set_stats(self, text: str) -> None:
        self.stats_label.configure(text=text)


class MainWindow:
    def __init__(self, config: dict):
        ctk.set_appearance_mode(config.get("appearance", "dark"))
        self.root = ctk.CTk()
        self.root.title("FitFast Downloader")
        self.root.geometry(config.get("window_geometry", "980x720"))
        self.root.minsize(780, 620)

        self.rows: dict[str, JobRow] = {}
        self._config = config

        self._build_layout()

    def _build_layout(self):
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            self.root, text="FitFast Downloader",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header.grid(row=0, column=0, padx=16, pady=(16, 4), sticky="w")

        subheader = ctk.CTkLabel(
            self.root,
            text="Paste a FitGirl page to auto-grab every link — or paste FuckingFast links directly. "
                 "Pick a folder, hit Start.",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70"),
        )
        subheader.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

        top = ctk.CTkFrame(self.root)
        top.grid(row=2, column=0, padx=16, pady=8, sticky="nsew")
        top.grid_columnconfigure(0, weight=1)
        top.grid_rowconfigure(2, weight=1)

        # --- FitGirl auto-fetch row: paste ONE game page, extract all links ---
        fitgirl = ctk.CTkFrame(top)
        fitgirl.grid(row=0, column=0, padx=12, pady=(10, 6), sticky="ew")
        fitgirl.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(fitgirl, text="FitGirl page:", anchor="w").grid(
            row=0, column=0, padx=(8, 8), pady=8, sticky="w"
        )
        self.fitgirl_entry = ctk.CTkEntry(
            fitgirl,
            placeholder_text="Paste a fitgirl-repacks.site game URL to auto-grab every FuckingFast link",
        )
        self.fitgirl_entry.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="ew")
        self.fetch_button = ctk.CTkButton(fitgirl, text="Fetch links", width=110)
        self.fetch_button.grid(row=0, column=2, padx=(0, 8), pady=8)

        ctk.CTkLabel(top, text="Links (one per line):", anchor="w").grid(
            row=1, column=0, padx=12, pady=(2, 2), sticky="w"
        )
        self.links_textbox = ctk.CTkTextbox(top, height=130)
        self.links_textbox.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="nsew")

        options = ctk.CTkFrame(top)
        options.grid(row=3, column=0, padx=12, pady=(0, 10), sticky="ew")
        options.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(options, text="Destination:", anchor="w").grid(
            row=0, column=0, padx=(8, 8), pady=8, sticky="w"
        )
        self.dest_entry = ctk.CTkEntry(options)
        self.dest_entry.insert(0, self._config.get("destination", ""))
        self.dest_entry.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="ew")
        self.browse_button = ctk.CTkButton(options, text="Browse...", width=100, command=self._on_browse)
        self.browse_button.grid(row=0, column=2, padx=(0, 8), pady=8)

        ctk.CTkLabel(options, text="Subfolder:", anchor="w").grid(
            row=1, column=0, padx=(8, 8), pady=(0, 8), sticky="w"
        )
        self.subfolder_var = tk.StringVar(value="")
        self.subfolder_entry = ctk.CTkEntry(
            options, textvariable=self.subfolder_var,
            placeholder_text="Auto-detected from filenames",
        )
        self.subfolder_entry.grid(row=1, column=1, columnspan=2, padx=(0, 8), pady=(0, 8), sticky="ew")

        speed = ctk.CTkFrame(options, fg_color="transparent")
        speed.grid(row=2, column=0, columnspan=3, padx=(4, 4), pady=(0, 8), sticky="ew")

        ctk.CTkLabel(speed, text="Connections/file:").grid(row=0, column=0, padx=(8, 4), pady=6)
        self.conns_option = ctk.CTkOptionMenu(
            speed, values=["4", "8", "16", "24", "32"], width=80,
        )
        self.conns_option.set(str(self._config.get("connections_per_file", 16)))
        self.conns_option.grid(row=0, column=1, padx=(0, 24), pady=6)

        ctk.CTkLabel(speed, text="Concurrent files:").grid(row=0, column=2, padx=(0, 4), pady=6)
        self.concurrent_option = ctk.CTkOptionMenu(
            speed, values=["1", "2", "3", "4", "5", "6"], width=80,
        )
        self.concurrent_option.set(str(self._config.get("concurrent_files", 3)))
        self.concurrent_option.grid(row=0, column=3, padx=(0, 8), pady=6)

        self.auto_reresolve_var = tk.BooleanVar(value=bool(self._config.get("auto_reresolve", True)))
        self.auto_reresolve_check = ctk.CTkCheckBox(
            speed,
            text="Auto re-resolve stalled files (swap to fresh CDN edge)",
            variable=self.auto_reresolve_var,
        )
        self.auto_reresolve_check.grid(row=1, column=0, columnspan=4, padx=(8, 8), pady=(4, 4), sticky="w")

        self.auto_extract_var = tk.BooleanVar(value=bool(self._config.get("auto_extract", True)))
        self.auto_extract_check = ctk.CTkCheckBox(
            speed,
            text="Auto-extract .rar when downloads finish",
            variable=self.auto_extract_var,
            command=self._sync_extract_controls,
        )
        self.auto_extract_check.grid(row=2, column=0, columnspan=2, padx=(8, 8), pady=(4, 4), sticky="w")

        self.delete_after_var = tk.BooleanVar(value=bool(self._config.get("delete_archives_after", False)))
        self.delete_after_check = ctk.CTkCheckBox(
            speed,
            text="Delete .rar archives after extracting",
            variable=self.delete_after_var,
        )
        self.delete_after_check.grid(row=2, column=2, columnspan=2, padx=(8, 8), pady=(4, 4), sticky="w")

        self.speedtest_button = ctk.CTkButton(
            speed, text="Test my pipe", width=140,
            fg_color=("gray70", "gray30"), hover_color=("gray60", "gray40"),
        )
        self.speedtest_button.grid(row=0, column=4, padx=(20, 8), pady=6)

        buttons = ctk.CTkFrame(top, fg_color="transparent")
        buttons.grid(row=4, column=0, padx=12, pady=(0, 12), sticky="ew")
        buttons.grid_columnconfigure((0, 1, 2), weight=1)

        self.start_button = ctk.CTkButton(
            buttons, text="Start Downloads", height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.start_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.pause_button = ctk.CTkButton(
            buttons, text="Pause All", height=40, state="disabled",
            fg_color="gray30", hover_color="gray40",
        )
        self.pause_button.grid(row=0, column=1, padx=6, sticky="ew")
        self.cancel_button = ctk.CTkButton(
            buttons, text="Cancel All", height=40, state="disabled",
            fg_color="#8b1a1a", hover_color="#a52020",
        )
        self.cancel_button.grid(row=0, column=2, padx=(6, 0), sticky="ew")

        bottom = ctk.CTkFrame(self.root)
        bottom.grid(row=3, column=0, padx=16, pady=(0, 8), sticky="nsew")
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_rowconfigure(1, weight=1)

        self.root.grid_rowconfigure(3, weight=2)

        ctk.CTkLabel(bottom, text="Downloads:", anchor="w").grid(
            row=0, column=0, padx=12, pady=(10, 2), sticky="w"
        )
        self.rows_frame = ctk.CTkScrollableFrame(bottom, height=280)
        self.rows_frame.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="nsew")
        self.rows_frame.grid_columnconfigure(0, weight=1)

        self.status_bar = ctk.CTkLabel(
            self.root, text="Ready.", anchor="w",
            font=ctk.CTkFont(size=11),
        )
        self.status_bar.grid(row=4, column=0, padx=16, pady=(0, 12), sticky="ew")

    def _on_browse(self):
        current = self.dest_entry.get() or ""
        chosen = filedialog.askdirectory(
            title="Choose destination folder", initialdir=current,
        )
        if chosen:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, chosen)

    def clear_rows(self):
        for row in self.rows.values():
            row.destroy()
        self.rows.clear()

    def add_row(self, key: str, filename: str, url: str) -> JobRow:
        row = JobRow(self.rows_frame, filename, url)
        row.grid(row=len(self.rows), column=0, sticky="ew", padx=4, pady=2)
        self.rows[key] = row
        return row

    def get_links(self) -> list[str]:
        return [
            line.strip()
            for line in self.links_textbox.get("1.0", "end").splitlines()
            if line.strip()
        ]

    def get_fitgirl_url(self) -> str:
        return self.fitgirl_entry.get().strip()

    def set_links_text(self, text: str) -> None:
        self.links_textbox.delete("1.0", "end")
        self.links_textbox.insert("1.0", text)

    def set_subfolder(self, name: str) -> None:
        self.subfolder_var.set(name)

    def set_fetch_state(self, fetching: bool) -> None:
        if fetching:
            self.fetch_button.configure(state="disabled", text="Fetching...")
            self.fitgirl_entry.configure(state="disabled")
        else:
            self.fetch_button.configure(state="normal", text="Fetch links")
            self.fitgirl_entry.configure(state="normal")

    def get_destination(self) -> str:
        return self.dest_entry.get().strip()

    def get_subfolder_override(self) -> str:
        return self.subfolder_var.get().strip()

    def get_connections(self) -> int:
        try:
            return int(self.conns_option.get())
        except ValueError:
            return 16

    def get_concurrent(self) -> int:
        try:
            return int(self.concurrent_option.get())
        except ValueError:
            return 3

    def get_auto_reresolve(self) -> bool:
        return bool(self.auto_reresolve_var.get())

    def get_auto_extract(self) -> bool:
        return bool(self.auto_extract_var.get())

    def get_delete_after(self) -> bool:
        return bool(self.delete_after_var.get())

    def _sync_extract_controls(self) -> None:
        # Delete-after only makes sense when auto-extract is on.
        if self.auto_extract_var.get():
            self.delete_after_check.configure(state="normal")
        else:
            self.delete_after_check.configure(state="disabled")

    def set_status_bar(self, text: str) -> None:
        self.status_bar.configure(text=text)

    def set_downloading_state(self, downloading: bool) -> None:
        if downloading:
            self.start_button.configure(state="disabled")
            self.pause_button.configure(state="normal")
            self.cancel_button.configure(state="normal")
            self.links_textbox.configure(state="disabled")
            self.dest_entry.configure(state="disabled")
            self.browse_button.configure(state="disabled")
            self.subfolder_entry.configure(state="disabled")
            self.speedtest_button.configure(state="disabled")
            self.fetch_button.configure(state="disabled")
            self.fitgirl_entry.configure(state="disabled")
        else:
            self.start_button.configure(state="normal")
            self.pause_button.configure(state="disabled", text="Pause All")
            self.cancel_button.configure(state="disabled")
            self.links_textbox.configure(state="normal")
            self.dest_entry.configure(state="normal")
            self.browse_button.configure(state="normal")
            self.subfolder_entry.configure(state="normal")
            self.speedtest_button.configure(state="normal")
            self.fetch_button.configure(state="normal", text="Fetch links")
            self.fitgirl_entry.configure(state="normal")

    def set_paused_state(self, paused: bool) -> None:
        self.pause_button.configure(text="Resume All" if paused else "Pause All")

    def run_first_time_setup(self, worker) -> bool:
        """Show a modal setup dialog while ``worker(status_cb)`` runs in a thread.

        Returns True on success, False on failure. ``worker`` receives a
        thread-safe status callback it can call with progress strings.
        """
        import threading

        dlg = ctk.CTkToplevel(self.root)
        dlg.title("FitFast — first-time setup")
        dlg.geometry("460x200")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg, text="Setting up FitFast",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(padx=20, pady=(22, 6))
        status = ctk.CTkLabel(
            dlg, text="Preparing…", wraplength=410,
            font=ctk.CTkFont(size=12),
        )
        status.pack(padx=20, pady=(0, 12))
        bar = ctk.CTkProgressBar(dlg, mode="indeterminate", width=400)
        bar.pack(padx=20, pady=(0, 8))
        bar.start()

        result = {"ok": False, "error": None, "done": False}

        def status_cb(msg: str) -> None:
            self.root.after(0, lambda: status.configure(text=msg))

        def run():
            try:
                worker(status_cb)
                result["ok"] = True
            except Exception as e:
                result["error"] = str(e)
            finally:
                result["done"] = True

        threading.Thread(target=run, daemon=True, name="first-run").start()

        # Pump the dialog until the worker finishes.
        while not result["done"]:
            dlg.update()
            self.root.update()
            dlg.after(60)
        bar.stop()
        dlg.grab_release()
        dlg.destroy()
        if not result["ok"] and result["error"]:
            from tkinter import messagebox
            messagebox.showerror(
                "Setup failed",
                f"Couldn't finish first-time setup:\n\n{result['error']}\n\n"
                "Check your internet connection and relaunch.",
            )
        return result["ok"]
