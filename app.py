"""File & folder comparison tool — tkinter GUI.

Run: python3 app.py
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

LOG_PATH = Path(__file__).resolve().parent / "files_comparison.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"),
              logging.StreamHandler()])
log = logging.getLogger("files_comparison")
log.info("=== app module loaded, log file: %s ===", LOG_PATH)

import diff_engine as de

# --- visual theme ---------------------------------------------------------
BG = "#eef0f4"          # window background
CARD = "#ffffff"        # panels / content surfaces
BORDER = "#d9dde3"
TEXT = "#1f2328"
MUTED = "#65707e"
ACCENT = "#2f6df6"
ACCENT_DK = "#1f56d8"

FONT_UI = ("", 12)
FONT_BOLD = ("", 13, "bold")
FONT_TITLE = ("", 16, "bold")
FONT_MONO = ("Menlo", 12)
GUTTER_WIDTH = 6

ROW_COLORS = {
    de.CHANGED: "#fff2c4",
    de.ADDED: "#d5f2db",
    de.REMOVED: "#ffdcdb",
    de.BLANK: "#eef0f3",
}
PAD_BG = "#e7eaef"
GUTTER_BG = "#f7f8fa"
GUTTER_FG = "#a0a8b4"

STATUS_COLORS = {
    de.IDENTICAL: "",
    de.DIFFERENT: "#fff2c4",
    de.LEFT_ONLY: "#dce9fd",
    de.RIGHT_ONLY: "#d5f2db",
    de.TYPE_MISMATCH: "#eadffd",
    de.BINARY: "#e8eaee",
    de.ERROR: "#ffc9c9",
}

STATUS_LABELS = {
    de.IDENTICAL: "Identical",
    de.DIFFERENT: "Different",
    de.LEFT_ONLY: "Left only",
    de.RIGHT_ONLY: "Right only",
    de.TYPE_MISMATCH: "File vs folder",
    de.BINARY: "Binary differ",
    de.ERROR: "Error",
}


def _apply_style(root: tk.Misc):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=TEXT, font=FONT_UI,
                    fieldbackground=CARD, bordercolor=BORDER)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Title.TLabel", font=FONT_TITLE)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Status.TLabel", foreground=MUTED, font=("", 11))
    style.configure("Panel.TLabel", background=CARD, font=FONT_BOLD)
    style.configure("TButton", padding=(12, 5))
    style.configure("Accent.TButton", background=ACCENT, foreground="white",
                    borderwidth=0, focuscolor=ACCENT)
    style.map("Accent.TButton",
              background=[("pressed", ACCENT_DK), ("active", ACCENT_DK)],
              foreground=[("disabled", "#ffffff")])
    style.configure("TCheckbutton", background=BG)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("TEntry", padding=5)
    style.configure("Treeview", background=CARD, fieldbackground=CARD,
                    borderwidth=0, rowheight=26)
    style.configure("Treeview.Heading", font=FONT_BOLD, padding=(8, 6),
                    background=BG)
    style.configure("TScrollbar", background=BG, troughcolor=BG,
                    borderwidth=0, arrowcolor=MUTED)
    root.option_add("*Text.selectBackground", "#b9d2fb")


class DiffView(ttk.Frame):
    """Side-by-side diff: line-number gutter + text pane per side, synced scrolling."""

    def __init__(self, master):
        super().__init__(master)
        self.left_gutter = tk.Text(self, width=GUTTER_WIDTH, wrap="none",
                                   font=FONT_MONO, bg=GUTTER_BG, fg=GUTTER_FG,
                                   bd=0, takefocus=0, cursor="arrow")
        self.right_gutter = tk.Text(self, width=GUTTER_WIDTH, wrap="none",
                                    font=FONT_MONO, bg=GUTTER_BG, fg=GUTTER_FG,
                                    bd=0, takefocus=0, cursor="arrow")
        for g in (self.left_gutter, self.right_gutter):
            g.tag_configure("num", justify="right")
        self.left_text = tk.Text(self, wrap="none", font=FONT_MONO, bd=0,
                                 bg=CARD, undo=False, spacing1=1, spacing3=1)
        self.right_text = tk.Text(self, wrap="none", font=FONT_MONO, bd=0,
                                  bg=CARD, undo=False, spacing1=1, spacing3=1)
        self._widgets = (self.left_gutter, self.left_text,
                         self.right_gutter, self.right_text)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self._xview)
        for w in self._widgets:
            w.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set,
                        padx=4, highlightthickness=0)
            w.bind("<MouseWheel>", self._on_wheel)
            for kind, color in ROW_COLORS.items():
                w.tag_configure(kind, background=color)
            w.tag_configure("pad", background=PAD_BG)

        sep = tk.Frame(self, width=1, bg=BORDER)
        self.left_gutter.grid(row=0, column=0, sticky="ns")
        self.left_text.grid(row=0, column=1, sticky="nsew")
        sep.grid(row=0, column=2, sticky="ns")
        self.right_gutter.grid(row=0, column=3, sticky="ns")
        self.right_text.grid(row=0, column=4, sticky="nsew")
        vsb.grid(row=0, column=5, sticky="ns")
        hsb.grid(row=1, column=0, columnspan=6, sticky="ew")
        self.status = ttk.Label(self, anchor="w", style="Status.TLabel")
        self.status.grid(row=2, column=0, columnspan=6, sticky="ew",
                         padx=6, pady=(2, 0))
        self.columnconfigure(1, weight=1)
        self.columnconfigure(4, weight=1)
        self.rowconfigure(0, weight=1)

    def _yview(self, *args):
        for w in self._widgets:
            w.yview(*args)

    def _xview(self, *args):
        for w in (self.left_text, self.right_text):
            w.xview(*args)

    def _on_wheel(self, event):
        delta = -1 if event.delta > 0 else 1
        for w in self._widgets:
            w.yview_scroll(delta, "units")
        return "break"

    def show_result(self, result: de.FileResult):
        for w in self._widgets:
            w.configure(state="normal")
            w.delete("1.0", "end")

        for row in result.rows:
            for gutter, pane, cell in (
                (self.left_gutter, self.left_text, row.left),
                (self.right_gutter, self.right_text, row.right),
            ):
                if cell is None:
                    gutter.insert("end", "\n", ("num", "pad"))
                    pane.insert("end", "\n", "pad")
                else:
                    gutter.insert("end", f"{cell.lineno}\n", ("num", cell.kind))
                    pane.insert("end", cell.text + "\n", cell.kind)

        for w in self._widgets:
            w.configure(state="disabled")
            w.yview_moveto(0)

        prefix = (result.note + " — ") if result.note else ""
        if result.identical:
            self.status.configure(text=prefix + "Files are identical")
        else:
            s = result.summary
            parts = [f"{s.get(k, 0)} {k}" for k in (de.CHANGED, de.ADDED, de.REMOVED) if s.get(k)]
            if s.get(de.BLANK):
                parts.append(f"{s[de.BLANK]} blank (ignored)")
            self.status.configure(text=prefix + "Differences: " + ", ".join(parts))


class FolderView(ttk.Frame):
    """Treeview of compare_dirs results; double-click a differing file to open a diff."""

    def __init__(self, master, on_open_file):
        super().__init__(master)
        self._on_open_file = on_open_file
        self._entries: dict[str, de.DirEntry] = {}

        cols = ("status", "side")
        self.tree = ttk.Treeview(self, columns=cols, show="tree headings")
        self.tree.heading("#0", text="Path")
        self.tree.heading("status", text="Status")
        self.tree.heading("side", text="Type")
        self.tree.column("#0", width=500)
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("side", width=90, anchor="center")
        for status, color in STATUS_COLORS.items():
            if color:
                self.tree.tag_configure(status, background=color)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.status = ttk.Label(self, anchor="w", style="Status.TLabel")
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew",
                         padx=4, pady=(4, 0))
        self.tree.bind("<Double-1>", self._on_double_click)

    def show_entries(self, entries: list[de.DirEntry]):
        self.tree.delete(*self.tree.get_children())
        self._entries.clear()
        counts: dict[str, int] = {}

        # entries are sorted by relpath, so parents always precede their children
        for entry in entries:
            counts[entry.status] = counts.get(entry.status, 0) + 1
            parent = entry.relpath.rsplit("/", 1)[0] if "/" in entry.relpath else ""
            iid = self.tree.insert(parent, "end", iid=entry.relpath,
                                   text=entry.relpath.split("/")[-1],
                                   values=(STATUS_LABELS.get(entry.status, entry.status),
                                           "Folder" if entry.is_dir else "File"),
                                   tags=(entry.status,))
            self._entries[iid] = entry

        parts = [f"{counts[k]} {STATUS_LABELS.get(k, k).lower()}"
                 for k in (de.DIFFERENT, de.LEFT_ONLY, de.RIGHT_ONLY, de.BINARY,
                           de.TYPE_MISMATCH, de.ERROR) if counts.get(k)]
        total = len(entries)
        self.status.configure(
            text=f"{total} items — " + (", ".join(parts) if parts else "all identical")
            + "   (double-click a different file to view its diff)")

    def _on_double_click(self, event):
        iid = self.tree.identify_row(event.y)
        entry = self._entries.get(iid)
        if entry and entry.status in (de.DIFFERENT, de.BINARY):
            self._on_open_file(entry)


class SidePanel(tk.Frame):
    """Half-width card with a title, path entry and browse buttons."""

    def __init__(self, master, app, title, var):
        super().__init__(master, bg=CARD, padx=10, pady=8,
                         highlightthickness=1, highlightbackground=BORDER)
        self.var = var
        tk.Label(self, text=title, bg=CARD, fg=MUTED,
                 font=("", 10, "bold")).pack(anchor="w")

        row = tk.Frame(self, bg=CARD)
        row.pack(fill="x", pady=(4, 0))
        self.entry = ttk.Entry(row, textvariable=var)
        self.entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="File…", width=7,
                   command=lambda: app._pick(var, False)).pack(side="left", padx=(4, 2))
        ttk.Button(row, text="Folder…", width=8,
                   command=lambda: app._pick(var, True)).pack(side="left")


ICON_PATH = Path(__file__).resolve().parent / "icon.png"


def _load_icon(root: tk.Misc):
    try:
        if ICON_PATH.exists():
            img = tk.PhotoImage(file=str(ICON_PATH))
            root.iconphoto(True, img)   # True = applies to future Toplevels too
            return img
    except tk.TclError:
        log.exception("failed to load icon %s", ICON_PATH)
    return None


def _maximize(win: tk.Misc):
    """Fill the screen without entering native fullscreen."""
    try:
        win.state("zoomed")  # Windows / most X11 WMs
    except tk.TclError:
        w = win.winfo_screenwidth()
        h = win.winfo_screenheight()
        win.geometry(f"{w}x{h}+0+0")  # macOS


class CompareApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Files Comparison")
        _maximize(self)
        self.configure(bg=BG)
        _apply_style(self)
        self._icon = _load_icon(self)
        self._queue: queue.Queue = queue.Queue()
        log.info("app init: Tk %s", tk.TkVersion)

        brand = ttk.Frame(self, padding=(12, 12, 12, 2))
        brand.pack(fill="x")
        ttk.Label(brand, text="Files Comparison",
                  style="Title.TLabel").pack(side="left")
        ttk.Label(brand, text="side-by-side diff for files & folders",
                  style="Muted.TLabel").pack(side="left", padx=10, pady=(4, 0))

        self.left_var = tk.StringVar()
        self.right_var = tk.StringVar()

        panels = ttk.Frame(self, padding=(12, 4, 12, 0))
        panels.pack(fill="x")
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)
        self.left_panel = SidePanel(panels, self, "LEFT", self.left_var)
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.right_panel = SidePanel(panels, self, "RIGHT", self.right_var)
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        opts = ttk.Frame(self, padding=(12, 8, 12, 8))
        opts.pack(fill="x")
        self.opt_ws = tk.BooleanVar()
        self.opt_case = tk.BooleanVar()
        self.opt_blank = tk.BooleanVar()
        self.opt_recursive = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Ignore whitespace", variable=self.opt_ws).pack(side="left")
        ttk.Checkbutton(opts, text="Ignore case", variable=self.opt_case).pack(side="left", padx=8)
        ttk.Checkbutton(opts, text="Ignore blank lines", variable=self.opt_blank).pack(side="left")
        ttk.Checkbutton(opts, text="Include subfolders", variable=self.opt_recursive).pack(side="left", padx=8)
        self.compare_btn = ttk.Button(opts, text="Compare", style="Accent.TButton",
                                      command=self.compare)
        self.compare_btn.pack(side="right")

        self.content = ttk.Frame(self)
        self.content.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self._content_widget = None
        self._show_hint()

    def _diff_options(self) -> de.DiffOptions:
        return de.DiffOptions(
            ignore_whitespace=self.opt_ws.get(),
            ignore_case=self.opt_case.get(),
            ignore_blank_lines=self.opt_blank.get(),
            recursive=self.opt_recursive.get())

    def _pick(self, var: tk.StringVar, is_dir: bool):
        side = "left" if var is self.left_var else "right"
        log.info("browse clicked: %s %s", side, "folder" if is_dir else "file")
        # macOS: the native dialog can open behind this window — pin it on top
        self.attributes("-topmost", True)
        try:
            if is_dir:
                path = filedialog.askdirectory(parent=self)
            else:
                path = filedialog.askopenfilename(parent=self)
        finally:
            self.attributes("-topmost", False)
        log.info("picker returned: %r", path)
        if path:
            var.set(path)
            self._compare_if_ready()

    def _compare_if_ready(self):
        log.debug("compare_if_ready: left=%r right=%r",
                  self.left_var.get(), self.right_var.get())
        if self.left_var.get() and self.right_var.get():
            self.compare()

    def _show_hint(self):
        self._set_content(ttk.Label(
            self.content,
            text="Pick a file or folder on each side above — the comparison runs automatically.",
            style="Muted.TLabel", anchor="center"))

    def _set_content(self, widget):
        if self._content_widget is not None:
            self._content_widget.destroy()
        self._content_widget = widget
        widget.pack(fill="both", expand=True)

    def compare(self):
        left, right = Path(self.left_var.get()), Path(self.right_var.get())
        log.info("compare: left=%s right=%s", left, right)
        if not left.exists() or not right.exists():
            log.warning("compare aborted: left.exists()=%s right.exists()=%s",
                        left.exists(), right.exists())
            messagebox.showerror("Files Comparison", "Both paths must exist.")
            return
        if left.is_file() != right.is_file():
            log.warning("compare aborted: left.is_file()=%s right.is_file()=%s",
                        left.is_file(), right.is_file())
            messagebox.showerror("Files Comparison",
                                 "Pick two files or two folders — not one of each.")
            return

        self.compare_btn.configure(state="disabled", text="Comparing…")
        options = self._diff_options()
        if left.is_dir():
            work = lambda: ("dirs", de.compare_dirs(left, right, options))
        else:
            work = lambda: ("file", de.compare_files(left, right, options))

        def run():
            try:
                self._queue.put(work())
            except Exception:
                log.exception("compare worker failed")
                self._queue.put(("error", None))
        threading.Thread(target=run, daemon=True).start()
        self.after(60, self._poll)

    def _poll(self):
        try:
            kind, result = self._queue.get_nowait()
        except queue.Empty:
            self.after(60, self._poll)
            return
        self.compare_btn.configure(state="normal", text="Compare")
        log.info("compare finished: kind=%s", kind)

        if kind == "error":
            messagebox.showerror("Files Comparison",
                                 "Comparison failed — see files_comparison.log")
        elif kind == "dirs":
            log.info("folder result: %d entries", len(result))
            view = FolderView(self.content, self._open_file_diff)
            view.show_entries(result)
            self._set_content(view)
        elif result.error:
            log.warning("file compare error: %s", result.error)
            messagebox.showerror("Files Comparison", result.error)
        elif result.is_binary:
            label = "Binary files are identical" if result.identical else "Binary files differ"
            log.info("binary file result: identical=%s", result.identical)
            self._set_content(ttk.Label(self.content, text=label, anchor="center"))
        else:
            log.info("file result: %d rows, identical=%s, summary=%s",
                     len(result.rows), result.identical, result.summary)
            view = DiffView(self.content)
            view.show_result(result)
            self._set_content(view)

    def _open_file_diff(self, entry: de.DirEntry):
        win = tk.Toplevel(self)
        win.title(f"{entry.left_path.name} ↔ {entry.right_path.name}")
        win.configure(bg=BG)
        _maximize(win)
        view = DiffView(win)
        view.pack(fill="both", expand=True)
        options = self._diff_options()
        lp, rp = entry.left_path, entry.right_path
        q: queue.Queue = queue.Queue()

        threading.Thread(
            target=lambda: q.put(de.compare_files(lp, rp, options)),
            daemon=True).start()

        def poll():
            try:
                result = q.get_nowait()
            except queue.Empty:
                if win.winfo_exists():
                    self.after(60, poll)
                return
            if win.winfo_exists():
                if result.is_binary:
                    view.status.configure(
                        text="Binary files are identical" if result.identical
                        else "Binary files differ")
                elif result.error:
                    view.status.configure(text=result.error)
                else:
                    view.show_result(result)

        self.after(60, poll)


if __name__ == "__main__":
    CompareApp().mainloop()
