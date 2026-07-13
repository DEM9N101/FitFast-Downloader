"""CustomTkinter UI widgets. Pure view code — no orchestration."""
from __future__ import annotations
import tkinter as tk
import webbrowser
from tkinter import filedialog

import customtkinter as ctk

if __package__ in (None, ""):
    from config import APP_VERSION, REPO_URL, ISSUES_URL, RELEASES_URL, LOG_FILE
    from log import read_log_tail, environment_summary
else:
    from .config import APP_VERSION, REPO_URL, ISSUES_URL, RELEASES_URL, LOG_FILE
    from .log import read_log_tail, environment_summary


ctk.set_default_color_theme("blue")


class Tooltip:
    """A small hover bubble that explains a control in plain language."""

    def __init__(self, widget, text: str, wraplength: int = 320):
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self._tip: tk.Toplevel | None = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(350, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        except Exception:
            return
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        self._tip.attributes("-topmost", True)
        frame = tk.Frame(self._tip, background="#1f2937", borderwidth=1, relief="solid")
        frame.pack()
        label = tk.Label(
            frame, text=self.text, justify="left", wraplength=self.wraplength,
            background="#1f2937", foreground="#e5e7eb",
            font=("Segoe UI", 9), padx=10, pady=7,
        )
        label.pack()

    def _hide(self, _event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def info_icon(parent, text: str):
    """A small circled-i help marker that shows ``text`` on hover."""
    lbl = ctk.CTkLabel(
        parent, text=" ⓘ ", width=18,
        font=ctk.CTkFont(size=13),
        text_color=("gray45", "gray60"),
    )
    Tooltip(lbl, text)
    return lbl


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

        # Help button floats in the top-right corner.
        self.help_button = ctk.CTkButton(
            self.root, text="Help / About", width=110, height=28,
            fg_color=("gray75", "gray25"), hover_color=("gray65", "gray35"),
            command=self._show_help,
        )
        self.help_button.place(relx=1.0, x=-16, y=18, anchor="ne")

        subheader = ctk.CTkLabel(
            self.root,
            text="Paste a FitGirl page to auto-grab every link, or paste FuckingFast links directly. "
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
        _fg_label = ctk.CTkLabel(fitgirl, text="FitGirl page  ⓘ", anchor="w")
        _fg_label.grid(row=0, column=0, padx=(8, 8), pady=8, sticky="w")
        Tooltip(_fg_label,
                "Paste the web address of a FitGirl game page here and click Fetch links. "
                "FitFast opens the page and copies every download link for you, so you don't "
                "have to open them one by one.")
        self.fitgirl_entry = ctk.CTkEntry(
            fitgirl,
            placeholder_text="Paste a fitgirl-repacks.site game URL to auto-grab every FuckingFast link",
        )
        self.fitgirl_entry.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="ew")
        self.fetch_button = ctk.CTkButton(fitgirl, text="Fetch links", width=110)
        self.fetch_button.grid(row=0, column=2, padx=(0, 8), pady=8)
        Tooltip(self.fetch_button,
                "Opens the FitGirl page above and copies all of its download links into the box below.")

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

        _sub_label = ctk.CTkLabel(options, text="Subfolder  ⓘ", anchor="w")
        _sub_label.grid(row=1, column=0, padx=(8, 8), pady=(0, 8), sticky="w")
        Tooltip(_sub_label,
                "The name of the new folder FitFast makes inside your destination. All of the "
                "game's files go in here, so your Downloads folder stays tidy. Leave blank to "
                "name it automatically after the game.")
        self.subfolder_var = tk.StringVar(value="")
        self.subfolder_entry = ctk.CTkEntry(
            options, textvariable=self.subfolder_var,
            placeholder_text="Auto-detected from filenames",
        )
        self.subfolder_entry.grid(row=1, column=1, columnspan=2, padx=(0, 8), pady=(0, 8), sticky="ew")

        speed = ctk.CTkFrame(options, fg_color="transparent")
        speed.grid(row=2, column=0, columnspan=3, padx=(4, 4), pady=(0, 8), sticky="ew")

        _conns_label = ctk.CTkLabel(speed, text="Connections/file  ⓘ")
        _conns_label.grid(row=0, column=0, padx=(8, 4), pady=6)
        Tooltip(_conns_label,
                "How many pieces each file is split into and grabbed at the same time. More can be "
                "faster. 16 is a safe choice for almost everyone; try 24 or 32 only on a very fast line.")
        self.conns_option = ctk.CTkOptionMenu(
            speed, values=["4", "8", "16", "24", "32"], width=80,
        )
        self.conns_option.set(str(self._config.get("connections_per_file", 16)))
        self.conns_option.grid(row=0, column=1, padx=(0, 24), pady=6)

        _conc_label = ctk.CTkLabel(speed, text="Concurrent files  ⓘ")
        _conc_label.grid(row=0, column=2, padx=(0, 4), pady=6)
        Tooltip(_conc_label,
                "How many files download at the same time. If your internet feels maxed out or "
                "unstable, lower this. Most people are fine with 3.")
        self.concurrent_option = ctk.CTkOptionMenu(
            speed, values=["1", "2", "3", "4", "5", "6"], width=80,
        )
        self.concurrent_option.set(str(self._config.get("concurrent_files", 3)))
        self.concurrent_option.grid(row=0, column=3, padx=(0, 8), pady=6)

        self.auto_reresolve_var = tk.BooleanVar(value=bool(self._config.get("auto_reresolve", True)))
        self.auto_reresolve_check = ctk.CTkCheckBox(
            speed,
            text="Auto re-resolve stalled files (swap to a faster server)  ⓘ",
            variable=self.auto_reresolve_var,
        )
        self.auto_reresolve_check.grid(row=1, column=0, columnspan=5, padx=(8, 8), pady=(4, 4), sticky="w")
        Tooltip(self.auto_reresolve_check,
                "fuckingfast.co has fast and slow servers. If one file gets stuck on a slow one, "
                "FitFast quietly grabs a fresh link and keeps going from where it stopped, so a "
                "single slow file doesn't hold up the whole batch. Recommended: on.")

        self.auto_extract_var = tk.BooleanVar(value=bool(self._config.get("auto_extract", True)))
        self.auto_extract_check = ctk.CTkCheckBox(
            speed,
            text="Auto-extract .rar when downloads finish  ⓘ",
            variable=self.auto_extract_var,
            command=self._sync_extract_controls,
        )
        self.auto_extract_check.grid(row=2, column=0, columnspan=2, padx=(8, 8), pady=(4, 4), sticky="w")
        Tooltip(self.auto_extract_check,
                "When every download finishes, FitFast unzips the .rar files for you automatically "
                "and leaves a ready-to-install game folder. No need to unzip by hand.")

        self.delete_after_var = tk.BooleanVar(value=bool(self._config.get("delete_archives_after", False)))
        self.delete_after_check = ctk.CTkCheckBox(
            speed,
            text="Delete .rar archives after extracting  ⓘ",
            variable=self.delete_after_var,
        )
        self.delete_after_check.grid(row=2, column=2, columnspan=3, padx=(8, 8), pady=(4, 4), sticky="w")
        Tooltip(self.delete_after_check,
                "After a successful unzip, delete the .rar parts to save disk space. Off by default, "
                "so you keep the archives until you're sure the game installs correctly.")

        self.speedtest_button = ctk.CTkButton(
            speed, text="Test my pipe", width=140,
            fg_color=("gray70", "gray30"), hover_color=("gray60", "gray40"),
        )
        self.speedtest_button.grid(row=0, column=4, padx=(20, 8), pady=6)
        Tooltip(self.speedtest_button,
                "Runs a quick speed test to show the fastest download speed your internet can reach "
                "right now. Handy for telling whether a slow download is the game host or your line.")

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

    # ---------------------------------------------------------------- toasts
    def show_toast(self, message: str, kind: str = "success", duration_ms: int = 4500) -> None:
        """Pop a coloured notification (green success / red error / blue info)."""
        self._hide_toast()
        palette = {
            "success": ("#1b7a3d", "#eafff1", "✓"),
            "error": ("#8b1a1a", "#ffe9e9", "✕"),
            "info": ("#1f5fa8", "#e9f2ff", "ℹ"),
        }
        bg, fg, icon = palette.get(kind, palette["info"])
        self._toast = ctk.CTkFrame(self.root, fg_color=bg, corner_radius=10)
        ctk.CTkLabel(
            self._toast, text=f"   {icon}   {message}   ", text_color=fg,
            font=ctk.CTkFont(size=13, weight="bold"), wraplength=780,
        ).pack(padx=12, pady=9)
        self._toast.place(relx=0.5, rely=1.0, y=-42, anchor="s")
        self._toast_after = self.root.after(duration_ms, self._hide_toast)

    def _hide_toast(self) -> None:
        after_id = getattr(self, "_toast_after", None)
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            self._toast_after = None
        toast = getattr(self, "_toast", None)
        if toast is not None:
            try:
                toast.destroy()
            except Exception:
                pass
            self._toast = None

    # ---------------------------------------------------------- error report
    def show_error_report(self, title: str, message: str, details: str = "") -> None:
        """Modal dialog with a plain explanation plus a copyable technical block
        the user can paste straight into a GitHub issue."""
        report = (
            f"{environment_summary()}\n\n"
            f"What I was doing: {title}\n\n"
            f"{message}\n\n"
            f"--- technical details ---\n{details or '(none)'}\n\n"
            f"--- recent log ---\n{read_log_tail(50)}"
        )

        dlg = ctk.CTkToplevel(self.root)
        dlg.title("FitFast - something went wrong")
        dlg.geometry("640x520")
        dlg.transient(self.root)
        dlg.grab_set()

        ctk.CTkLabel(
            dlg, text="Something went wrong", font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(padx=20, pady=(18, 4), anchor="w")
        ctk.CTkLabel(
            dlg, text=message, wraplength=590, justify="left",
            font=ctk.CTkFont(size=12),
        ).pack(padx=20, pady=(0, 8), anchor="w")
        ctk.CTkLabel(
            dlg,
            text="If this keeps happening, report it so it can be fixed. Click Copy details, "
                 "then Report on GitHub, and paste (Ctrl+V) into the box that opens.",
            wraplength=590, justify="left", font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray65"),
        ).pack(padx=20, pady=(0, 8), anchor="w")

        box = ctk.CTkTextbox(dlg, height=250, font=ctk.CTkFont(family="Consolas", size=11))
        box.pack(padx=20, pady=(0, 10), fill="both", expand=True)
        box.insert("1.0", report)
        box.configure(state="disabled")

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(padx=20, pady=(0, 16), fill="x")

        def copy_details():
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(report)
                copy_btn.configure(text="Copied ✓")
                dlg.after(1200, lambda: copy_btn.configure(text="Copy details"))
            except Exception:
                pass

        def report_github():
            copy_details()
            webbrowser.open(ISSUES_URL)

        copy_btn = ctk.CTkButton(btns, text="Copy details", command=copy_details, width=130)
        copy_btn.pack(side="left")
        ctk.CTkButton(btns, text="Report on GitHub", command=report_github, width=160).pack(side="left", padx=8)
        ctk.CTkButton(
            btns, text="Close", command=dlg.destroy, width=90,
            fg_color=("gray70", "gray30"), hover_color=("gray60", "gray40"),
        ).pack(side="right")

    # ----------------------------------------------------------------- about
    def _show_help(self) -> None:
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("FitFast - Help & About")
        dlg.geometry("560x460")
        dlg.transient(self.root)
        dlg.grab_set()

        ctk.CTkLabel(dlg, text="FitFast Downloader", font=ctk.CTkFont(size=18, weight="bold")).pack(
            padx=20, pady=(18, 0), anchor="w"
        )
        ctk.CTkLabel(dlg, text=f"Version {APP_VERSION}", text_color=("gray35", "gray65")).pack(
            padx=20, pady=(0, 10), anchor="w"
        )

        steps = (
            "How to use it, in three steps:\n\n"
            "1.  Paste a FitGirl game page link in the FitGirl page box and click Fetch links.\n"
            "     (Or paste fuckingfast.co links straight into the Links box, one per line.)\n\n"
            "2.  Choose where to save it with Browse. FitFast makes a tidy folder named after\n"
            "     the game inside that place.\n\n"
            "3.  Click Start Downloads. Leave it running. When it is done, your game is\n"
            "     downloaded and unzipped, ready to install.\n\n"
            "Hover the ⓘ marks in the app for a short explanation of each setting.\n\n"
            "First launch downloads a stealth browser once (a few hundred MB). That is normal\n"
            "and only happens the first time."
        )
        ctk.CTkLabel(dlg, text=steps, justify="left", font=ctk.CTkFont(size=12)).pack(
            padx=20, pady=(0, 10), anchor="w"
        )

        links = ctk.CTkFrame(dlg, fg_color="transparent")
        links.pack(padx=20, pady=(4, 8), fill="x")
        ctk.CTkButton(links, text="Project page", width=140,
                      command=lambda: webbrowser.open(REPO_URL)).pack(side="left")
        ctk.CTkButton(links, text="Report a problem", width=150,
                      command=lambda: webbrowser.open(ISSUES_URL)).pack(side="left", padx=8)
        ctk.CTkButton(links, text="Open log file", width=130,
                      fg_color=("gray70", "gray30"), hover_color=("gray60", "gray40"),
                      command=lambda: webbrowser.open(str(LOG_FILE.parent))).pack(side="left")

        ctk.CTkLabel(
            dlg,
            text="Not affiliated with FitGirl or fuckingfast.co. Use at your own discretion.",
            font=ctk.CTkFont(size=10), text_color=("gray40", "gray60"), wraplength=510, justify="left",
        ).pack(padx=20, pady=(6, 14), anchor="w")

    def run_first_time_setup(self, worker) -> bool:
        """Show a modal setup dialog while ``worker(status_cb)`` runs in a thread.

        Returns True on success, False on failure. ``worker`` receives a
        thread-safe status callback it can call with progress strings.
        """
        import threading

        dlg = ctk.CTkToplevel(self.root)
        dlg.title("FitFast - first-time setup")
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
