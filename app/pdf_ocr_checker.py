"""
PDF OCR Checker - Drag & Drop Tool
Checks PDFs for text content (OCR). Renames files based on their OCR status
using configurable suffixes. Supports light/dark mode, persistent statistics,
and an options menu to customize suffix behavior.
"""

import os
import sys
import json
import fitz  # PyMuPDF
import threading
import concurrent.futures
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

# Skip any single file that takes longer than this to scan for OCR text.
PER_FILE_TIMEOUT = 5.0


def _long_path(path):
    """Return a Windows long-path-prefixed version of `path` so file operations
    work for paths longer than the legacy 260-character MAX_PATH limit.
    On non-Windows platforms, returns the path unchanged."""
    if sys.platform != "win32" or not path:
        return path
    abs_path = os.path.abspath(path)
    if abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path

# Try to import tkinterdnd2 for drag-and-drop support
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

# --------------- Paths ---------------
# All data files are stored next to this script, regardless of where it's launched from.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "ocr_checker_log.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "ocr_checker_config.json")
ERROR_LOG_FILE = os.path.join(SCRIPT_DIR, "ocr_checker_errors.log")


# --------------- Config (Settings Persistence) ---------------

DEFAULT_CONFIG = {
    "no_ocr_suffix": "_OCR-me",
    "has_ocr_suffix": "_OCR-ok",
    "rename_no_ocr": True,
    "rename_has_ocr": False,
    "remove_suffix_mode": False,
    "dark_mode": True,
    "font_size": 10,
}


def load_config():
    """Load settings from the config JSON file next to this script.
    Returns the default settings if the file doesn't exist or is corrupted."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # Merge with defaults so any new keys added in future versions are present
        merged = {**DEFAULT_CONFIG, **cfg}
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    """Save settings to the config JSON file next to this script."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# --------------- Log File (Persistent Statistics) ---------------

def load_stats():
    """Load cumulative statistics from the log JSON file.
    Returns zeroed stats if the file doesn't exist or is corrupted."""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("cumulative", {
            "total": 0, "has_ocr": 0, "no_ocr_renamed": 0,
            "has_ocr_renamed": 0, "already_tagged": 0, "errors": 0, "sessions": 0
        }), data.get("history", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "total": 0, "has_ocr": 0, "no_ocr_renamed": 0,
            "has_ocr_renamed": 0, "already_tagged": 0, "errors": 0, "sessions": 0
        }, []


def save_stats(cumulative, history):
    """Save cumulative statistics and session history to the log JSON file."""
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump({"cumulative": cumulative, "history": history}, f, indent=2)


def reset_stats():
    """Delete all statistics by overwriting the log file with empty data."""
    save_stats({
        "total": 0, "has_ocr": 0, "no_ocr_renamed": 0,
        "has_ocr_renamed": 0, "already_tagged": 0, "errors": 0, "sessions": 0
    }, [])


# --------------- Error Log ---------------

def log_error(message):
    """Append an error message with timestamp to the error log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def clear_error_log():
    """Clear the error log file by overwriting it with empty content."""
    with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")


# --------------- Core Logic ---------------

def pdf_has_text(filepath, min_chars=10):
    """Check if a PDF has extractable text (i.e., is OCR'd / searchable).
    Returns True if the PDF contains at least `min_chars` non-whitespace characters.
    """
    try:
        doc = fitz.open(_long_path(filepath))
        total_text = 0
        for page in doc:
            text = page.get_text().strip()
            total_text += len(text)
            if total_text >= min_chars:
                doc.close()
                return True
        doc.close()
        return total_text >= min_chars
    except Exception as e:
        raise RuntimeError(f"Could not read PDF: {e}")


def pdf_has_text_with_timeout(filepath, timeout=PER_FILE_TIMEOUT, min_chars=10):
    """Run pdf_has_text in a worker thread and abort if it exceeds `timeout`.
    Raises TimeoutError if the scan exceeds the timeout. The orphaned worker
    thread is daemonized and will exit with the process."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(pdf_has_text, filepath, min_chars)
    try:
        result = future.result(timeout=timeout)
        executor.shutdown(wait=False)
        return result
    except concurrent.futures.TimeoutError:
        executor.shutdown(wait=False)
        raise TimeoutError(f"timed out after {timeout:.1f}s")


def _sanitize_suffix(suffix):
    """Remove any characters from a suffix that could cause path traversal or
    invalid file names. Only allows alphanumeric, hyphen, underscore, and dot."""
    return "".join(c for c in suffix if c.isalnum() or c in "-_.")


def rename_file(filepath, suffix):
    """Add a suffix before the .pdf extension.
    Example with suffix='_OCR-me': report.pdf -> report_OCR-me.pdf
    Returns (new_path, True) if renamed, or (original_path, False) if already tagged.
    """
    suffix = _sanitize_suffix(suffix)
    if not suffix:
        return filepath, False

    directory = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    name, ext = os.path.splitext(basename)

    # Don't add suffix if it already has it
    if name.endswith(suffix):
        return filepath, False

    new_name = f"{name}{suffix}{ext}"
    new_path = os.path.join(directory, new_name)

    # Handle name collision by appending a number
    counter = 1
    while os.path.exists(_long_path(new_path)):
        new_name = f"{name}{suffix}_{counter}{ext}"
        new_path = os.path.join(directory, new_name)
        counter += 1

    os.rename(_long_path(filepath), _long_path(new_path))
    return new_path, True


def remove_suffix_from_file(filepath, suffixes):
    """Remove any of the given suffixes from a PDF file name.
    Example: report_OCR-me.pdf -> report.pdf
    Returns (new_path, removed_suffix) if renamed, or (original_path, None) if no suffix found.
    """
    directory = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    name, ext = os.path.splitext(basename)

    for suffix in suffixes:
        suffix = _sanitize_suffix(suffix)
        if suffix and name.endswith(suffix):
            new_name = name[:-len(suffix)] + ext
            new_path = os.path.join(directory, new_name)

            # Handle name collision
            if os.path.exists(_long_path(new_path)):
                counter = 1
                base = name[:-len(suffix)]
                while os.path.exists(_long_path(new_path)):
                    new_name = f"{base}_{counter}{ext}"
                    new_path = os.path.join(directory, new_name)
                    counter += 1

            os.rename(_long_path(filepath), _long_path(new_path))
            return new_path, suffix

    return filepath, None


def process_files(filepaths, config, log_callback, done_callback, abort_event=None):
    """Process a list of PDF file paths using the current config settings.
    Checks each file for OCR and renames based on the enabled suffix options.
    """
    no_ocr_suffix = config["no_ocr_suffix"]
    has_ocr_suffix = config["has_ocr_suffix"]
    do_rename_no_ocr = config["rename_no_ocr"]
    do_rename_has_ocr = config["rename_has_ocr"]

    # Build a list of all active suffixes to check for "already tagged"
    active_suffixes = []
    if do_rename_no_ocr and no_ocr_suffix:
        active_suffixes.append(no_ocr_suffix)
    if do_rename_has_ocr and has_ocr_suffix:
        active_suffixes.append(has_ocr_suffix)

    results = {
        "total": 0, "has_ocr": 0, "no_ocr_renamed": 0,
        "has_ocr_renamed": 0, "already_tagged": 0, "errors": 0,
        "timed_out": 0, "aborted": False
    }

    for filepath in filepaths:
        if abort_event is not None and abort_event.is_set():
            log_callback("")
            log_callback("--- Aborted by user ---")
            results["aborted"] = True
            break

        filepath = filepath.strip().strip('"').strip("'")
        if not filepath.lower().endswith(".pdf"):
            log_callback(f"  SKIP     {os.path.basename(filepath)} (not a PDF)")
            continue

        if not os.path.isfile(_long_path(filepath)):
            error_msg = f"File not found: {filepath}"
            log_callback(f"  ERROR    {error_msg}")
            log_error(error_msg)
            results["errors"] += 1
            continue

        results["total"] += 1
        basename = os.path.basename(filepath)
        name_no_ext = os.path.splitext(basename)[0]

        # Check if already tagged with any active suffix
        already = False
        for sfx in active_suffixes:
            if name_no_ext.endswith(sfx):
                log_callback(f"  SKIP     {basename} (already tagged {sfx})")
                results["already_tagged"] += 1
                already = True
                break
        if already:
            continue

        try:
            has_text = pdf_has_text_with_timeout(filepath)
        except TimeoutError as e:
            log_callback(f"  SKIP     {basename} ({e})")
            results["timed_out"] += 1
            continue
        except RuntimeError as e:
            error_msg = f"{basename}: {e}"
            log_callback(f"  ERROR    {error_msg}")
            log_error(error_msg)
            results["errors"] += 1
            continue

        if has_text:
            # PDF has searchable text
            if do_rename_has_ocr and has_ocr_suffix:
                new_path, renamed = rename_file(filepath, has_ocr_suffix)
                if renamed:
                    new_name = os.path.basename(new_path)
                    log_callback(f"  TAGGED   {basename} -> {new_name}")
                    results["has_ocr_renamed"] += 1
                else:
                    log_callback(f"  OK       {basename} — has OCR (already tagged)")
                    results["has_ocr"] += 1
            else:
                log_callback(f"  OK       {basename} — has OCR / searchable text")
                results["has_ocr"] += 1
        else:
            # PDF has NO searchable text
            if do_rename_no_ocr and no_ocr_suffix:
                new_path, renamed = rename_file(filepath, no_ocr_suffix)
                if renamed:
                    new_name = os.path.basename(new_path)
                    log_callback(f"  RENAMED  {basename} -> {new_name}")
                    results["no_ocr_renamed"] += 1
                else:
                    log_callback(f"  NO-OCR   {basename} (already tagged)")
                    results["has_ocr"] += 1
            else:
                log_callback(f"  NO-OCR   {basename} — no searchable text (rename disabled)")
                results["has_ocr"] += 1

    # Print session summary
    log_callback("")
    log_callback(f"--- Session Results ---")
    log_callback(f"  Total PDFs checked:     {results['total']}")
    log_callback(f"  Has OCR (OK):           {results['has_ocr']}")
    log_callback(f"  No OCR (renamed):       {results['no_ocr_renamed']}")
    log_callback(f"  Has OCR (tagged):       {results['has_ocr_renamed']}")
    log_callback(f"  Already tagged:         {results['already_tagged']}")
    log_callback(f"  Timed out (>{PER_FILE_TIMEOUT:.0f}s):       {results['timed_out']}")
    log_callback(f"  Errors:                 {results['errors']}")

    # Update persistent statistics
    cumulative, history = load_stats()
    cumulative["total"] += results["total"]
    cumulative["has_ocr"] += results["has_ocr"]
    cumulative["no_ocr_renamed"] += results["no_ocr_renamed"]
    cumulative["has_ocr_renamed"] += results.get("has_ocr_renamed", 0)
    cumulative["already_tagged"] += results["already_tagged"]
    cumulative["errors"] += results["errors"]
    cumulative["sessions"] += 1

    # Append a session entry to history
    history.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files_checked": results["total"],
        "no_ocr_renamed": results["no_ocr_renamed"],
        "has_ocr_renamed": results["has_ocr_renamed"],
        "errors": results["errors"]
    })

    save_stats(cumulative, history)

    # Show cumulative stats
    log_callback("")
    log_callback(f"--- All-Time Statistics (across {cumulative['sessions']} sessions) ---")
    log_callback(f"  Total PDFs checked:     {cumulative['total']}")
    log_callback(f"  Has OCR (OK):           {cumulative['has_ocr']}")
    log_callback(f"  No OCR (renamed):       {cumulative['no_ocr_renamed']}")
    log_callback(f"  Has OCR (tagged):       {cumulative['has_ocr_renamed']}")
    log_callback(f"  Already tagged:         {cumulative['already_tagged']}")
    log_callback(f"  Errors:                 {cumulative['errors']}")

    done_callback()


# --------------- Theme Colors ---------------

THEMES = {
    "dark": {
        "bg":           "#1e1e2e",
        "drop_bg":      "#313244",
        "drop_border":  "#585b70",
        "drop_fg":      "#a6adc8",
        "drop_hover":   "#89b4fa",
        "log_bg":       "#181825",
        "log_fg":       "#cdd6f4",
        "log_select":   "#45475a",
        "title_fg":     "#89b4fa",
        "label_fg":     "#cdd6f4",
        "ok":           "#a6e3a1",
        "renamed":      "#fab387",
        "tagged":       "#94e2d5",
        "skip":         "#6c7086",
        "error":        "#f38ba8",
        "info":         "#89b4fa",
        "btn_bg":       "#313244",
        "btn_fg":       "#cdd6f4",
    },
    "light": {
        "bg":           "#eff1f5",
        "drop_bg":      "#ccd0da",
        "drop_border":  "#9ca0b0",
        "drop_fg":      "#5c5f77",
        "drop_hover":   "#1e66f5",
        "log_bg":       "#e6e9ef",
        "log_fg":       "#4c4f69",
        "log_select":   "#bcc0cc",
        "title_fg":     "#1e66f5",
        "label_fg":     "#4c4f69",
        "ok":           "#40a02b",
        "renamed":      "#fe640b",
        "tagged":       "#179299",
        "skip":         "#9ca0b0",
        "error":        "#d20f39",
        "info":         "#1e66f5",
        "btn_bg":       "#ccd0da",
        "btn_fg":       "#4c4f69",
    },
}


# --------------- GUI ---------------

class App:
    def __init__(self):
        # Load persisted settings
        self.config = load_config()

        # Create the main window (with or without drag-and-drop support)
        if HAS_DND:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title("PDF OCR Checker")
        self.root.geometry("750x600")
        self.root.minsize(550, 450)

        self.processing = False
        self.abort_event = threading.Event()
        self._build_ui()
        self._apply_theme()

    # ---- Theme application ----

    def _get_theme(self):
        """Return the current theme color dictionary based on dark_mode setting."""
        return THEMES["dark"] if self.config["dark_mode"] else THEMES["light"]

    def _apply_fonts(self):
        """Apply font sizes based on the font_size config value."""
        base = self.config.get("font_size", 10)
        self.style.configure("TButton", font=("Segoe UI", max(base - 1, 7)))
        self.style.configure("TLabel", font=("Segoe UI", base))
        self.style.configure("Title.TLabel", font=("Segoe UI", base + 4, "bold"))
        self.drop_label.config(font=("Segoe UI", base + 1))
        self.log_area.config(font=("Consolas", max(base - 1, 7)))
        self.status.config(font=("Segoe UI", base))

        # Update font size menu checkmarks
        if hasattr(self, "font_size_menu"):
            for i, size in enumerate(self._font_sizes):
                self.font_size_menu.entryconfig(
                    i, label=f"{'> ' if size == base else '   '}{size}")

    def _apply_theme(self):
        """Apply the current theme colors to every widget in the window."""
        t = self._get_theme()

        self.root.configure(bg=t["bg"])

        # Ttk styles
        self.style.configure("TLabel", background=t["bg"], foreground=t["label_fg"])
        self.style.configure("Title.TLabel", background=t["bg"], foreground=t["title_fg"])
        self.style.configure("TButton", background=t["btn_bg"], foreground=t["btn_fg"])

        # Drop zone
        self.drop_frame.config(bg=t["drop_bg"], highlightbackground=t["drop_border"])
        self.drop_label.config(bg=t["drop_bg"], fg=t["drop_fg"])

        # Log area
        self.log_area.config(bg=t["log_bg"], fg=t["log_fg"],
                             insertbackground=t["log_fg"], selectbackground=t["log_select"])
        self.log_area.tag_configure("ok", foreground=t["ok"])
        self.log_area.tag_configure("renamed", foreground=t["renamed"])
        self.log_area.tag_configure("tagged", foreground=t["tagged"])
        self.log_area.tag_configure("skip", foreground=t["skip"])
        self.log_area.tag_configure("error", foreground=t["error"])
        self.log_area.tag_configure("info", foreground=t["info"])

        # Button bar frame
        self.btn_frame.config(bg=t["bg"])

        # Menu bar colors (limited support on Windows but we try)
        self.menubar.config(bg=t["bg"], fg=t["label_fg"],
                            activebackground=t["drop_bg"], activeforeground=t["title_fg"])
        for menu in (self.options_menu, self.view_menu):
            menu.config(bg=t["bg"], fg=t["label_fg"],
                        activebackground=t["drop_bg"], activeforeground=t["title_fg"])
        if hasattr(self, "font_size_menu"):
            self.font_size_menu.config(bg=t["bg"], fg=t["label_fg"],
                                       activebackground=t["drop_bg"],
                                       activeforeground=t["title_fg"])

        self._apply_fonts()

    # ---- UI Construction ----

    def _build_ui(self):
        # -- Style setup --
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TButton", padding=6, font=("Segoe UI", 9))
        self.style.configure("TLabel", font=("Segoe UI", 10))
        self.style.configure("Title.TLabel", font=("Segoe UI", 14, "bold"))

        # -- Menu bar --
        self.menubar = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=self.menubar)

        # "Options" menu
        self.options_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Options", menu=self.options_menu)
        self.options_menu.add_command(label="Suffix Settings...", command=self._open_suffix_settings)
        self.options_menu.add_separator()
        self.options_menu.add_command(label="Reset Settings to Defaults...", command=self._reset_config)
        self.options_menu.add_command(label="Reset All-Time Statistics...", command=self._reset_stats)
        self.options_menu.add_command(label="Reset Error Log...", command=self._reset_error_log)

        # "View" menu
        self.view_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="View", menu=self.view_menu)
        self.view_menu.add_command(
            label="Switch to Light Mode" if self.config["dark_mode"] else "Switch to Dark Mode",
            command=self._toggle_theme
        )

        # Font size submenu
        self._font_sizes = [8, 9, 10, 11, 12, 14]
        self.font_size_menu = tk.Menu(self.view_menu, tearoff=0)
        self.view_menu.add_cascade(label="Font Size", menu=self.font_size_menu)
        current = self.config.get("font_size", 10)
        for size in self._font_sizes:
            prefix = "> " if size == current else "   "
            self.font_size_menu.add_command(
                label=f"{prefix}{size}",
                command=lambda s=size: self._set_font_size(s)
            )

        # -- Title --
        ttk.Label(self.root, text="PDF OCR Checker", style="Title.TLabel").pack(pady=(14, 4))
        self.subtitle = ttk.Label(self.root, text=self._subtitle_text())
        self.subtitle.pack()

        # -- Drop zone --
        self.drop_frame = tk.Frame(self.root, highlightthickness=2, cursor="hand2")
        self.drop_frame.pack(padx=20, pady=12, fill="x", ipady=18)

        self.drop_label = tk.Label(
            self.drop_frame, text="Drag & Drop PDF files here\nor click to browse",
            font=("Segoe UI", 11), justify="center")
        self.drop_label.pack(expand=True)

        if HAS_DND:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            self.drop_frame.dnd_bind("<<DragEnter>>", self._on_drag_enter)
            self.drop_frame.dnd_bind("<<DragLeave>>", self._on_drag_leave)
        else:
            self.drop_label.config(
                text="Click to browse for PDF files\n(install tkinterdnd2 for drag & drop)")

        self.drop_frame.bind("<Button-1>", self._on_browse)
        self.drop_label.bind("<Button-1>", self._on_browse)

        # -- Button bar --
        self.btn_frame = tk.Frame(self.root)
        self.btn_frame.pack(padx=20, fill="x")

        ttk.Button(self.btn_frame, text="Browse Files...", command=self._on_browse).pack(
            side="left", padx=(0, 6))
        ttk.Button(self.btn_frame, text="Show All-Time Stats", command=self._show_cumulative).pack(
            side="left", padx=(0, 6))
        self.abort_btn = ttk.Button(self.btn_frame, text="Abort", command=self._on_abort,
                                    state="disabled")
        self.abort_btn.pack(side="left", padx=(0, 6))

        # -- Log area --
        self.log_area = scrolledtext.ScrolledText(
            self.root, height=14, font=("Consolas", 9),
            relief="flat", borderwidth=0, state="disabled")
        self.log_area.pack(padx=20, pady=(8, 8), fill="both", expand=True)

        # -- Status bar --
        self.status = ttk.Label(self.root, text="Ready")
        self.status.pack(pady=(0, 8))

    def _subtitle_text(self):
        """Build the subtitle string from current config."""
        if self.config.get("remove_suffix_mode", False):
            suffixes = []
            if self.config["no_ocr_suffix"]:
                suffixes.append(f'"{self.config["no_ocr_suffix"]}"')
            if self.config["has_ocr_suffix"]:
                suffixes.append(f'"{self.config["has_ocr_suffix"]}"')
            if suffixes:
                return "Remove mode:  stripping " + ", ".join(suffixes) + " from files"
            return "Remove mode active but no suffixes configured"
        parts = []
        if self.config["rename_no_ocr"] and self.config["no_ocr_suffix"]:
            parts.append(f'No OCR -> "{self.config["no_ocr_suffix"]}"')
        if self.config["rename_has_ocr"] and self.config["has_ocr_suffix"]:
            parts.append(f'Has OCR -> "{self.config["has_ocr_suffix"]}"')
        if parts:
            return "Active rules:  " + "   |   ".join(parts)
        return "No renaming rules active (configure in Options > Suffix Settings)"

    # ---- Theme Toggle ----

    def _toggle_theme(self):
        """Switch between dark and light mode and save the preference."""
        self.config["dark_mode"] = not self.config["dark_mode"]
        save_config(self.config)
        self._apply_theme()
        # Update the menu label
        self.view_menu.entryconfig(0,
            label="Switch to Light Mode" if self.config["dark_mode"] else "Switch to Dark Mode")

    def _set_font_size(self, size):
        """Change the font size and save the preference."""
        self.config["font_size"] = size
        save_config(self.config)
        self._apply_fonts()

    # ---- Options: Suffix Settings Dialog ----

    def _open_suffix_settings(self):
        """Open a dialog window where the user can change suffix settings."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Suffix Settings")
        dlg.geometry("420x370")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        t = self._get_theme()
        dlg.configure(bg=t["bg"])

        row = 0
        pad = {"padx": 16, "pady": (10, 2), "sticky": "w"}

        # -- No OCR section --
        tk.Label(dlg, text="Files WITHOUT OCR (no searchable text):",
                 bg=t["bg"], fg=t["title_fg"], font=("Segoe UI", 10, "bold")).grid(
            row=row, column=0, columnspan=2, **pad); row += 1

        no_ocr_var = tk.BooleanVar(value=self.config["rename_no_ocr"])
        tk.Checkbutton(dlg, text="Rename these files", variable=no_ocr_var,
                       bg=t["bg"], fg=t["label_fg"], selectcolor=t["drop_bg"],
                       activebackground=t["bg"], activeforeground=t["label_fg"]).grid(
            row=row, column=0, columnspan=2, padx=16, pady=2, sticky="w"); row += 1

        tk.Label(dlg, text="Suffix:", bg=t["bg"], fg=t["label_fg"]).grid(
            row=row, column=0, padx=(16, 4), pady=2, sticky="w")
        no_ocr_entry = tk.Entry(dlg, width=25)
        no_ocr_entry.insert(0, self.config["no_ocr_suffix"])
        no_ocr_entry.grid(row=row, column=1, padx=(0, 16), pady=2, sticky="w"); row += 1

        # -- Spacer --
        tk.Frame(dlg, height=10, bg=t["bg"]).grid(row=row, column=0, columnspan=2); row += 1

        # -- Has OCR section --
        tk.Label(dlg, text="Files WITH OCR (has searchable text):",
                 bg=t["bg"], fg=t["title_fg"], font=("Segoe UI", 10, "bold")).grid(
            row=row, column=0, columnspan=2, **pad); row += 1

        has_ocr_var = tk.BooleanVar(value=self.config["rename_has_ocr"])
        tk.Checkbutton(dlg, text="Rename these files", variable=has_ocr_var,
                       bg=t["bg"], fg=t["label_fg"], selectcolor=t["drop_bg"],
                       activebackground=t["bg"], activeforeground=t["label_fg"]).grid(
            row=row, column=0, columnspan=2, padx=16, pady=2, sticky="w"); row += 1

        tk.Label(dlg, text="Suffix:", bg=t["bg"], fg=t["label_fg"]).grid(
            row=row, column=0, padx=(16, 4), pady=2, sticky="w")
        has_ocr_entry = tk.Entry(dlg, width=25)
        has_ocr_entry.insert(0, self.config["has_ocr_suffix"])
        has_ocr_entry.grid(row=row, column=1, padx=(0, 16), pady=2, sticky="w"); row += 1

        # -- Spacer --
        tk.Frame(dlg, height=10, bg=t["bg"]).grid(row=row, column=0, columnspan=2); row += 1

        # -- Remove mode section --
        tk.Label(dlg, text="Remove mode:",
                 bg=t["bg"], fg=t["title_fg"], font=("Segoe UI", 10, "bold")).grid(
            row=row, column=0, columnspan=2, **pad); row += 1

        remove_var = tk.BooleanVar(value=self.config.get("remove_suffix_mode", False))
        tk.Checkbutton(dlg, text="Remove suffixes instead of adding them",
                       variable=remove_var,
                       bg=t["bg"], fg=t["label_fg"], selectcolor=t["drop_bg"],
                       activebackground=t["bg"], activeforeground=t["label_fg"]).grid(
            row=row, column=0, columnspan=2, padx=16, pady=2, sticky="w"); row += 1

        # -- Spacer --
        tk.Frame(dlg, height=16, bg=t["bg"]).grid(row=row, column=0, columnspan=2); row += 1

        # -- Buttons --
        btn_frame = tk.Frame(dlg, bg=t["bg"])
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(4, 16))

        def on_save():
            self.config["rename_no_ocr"] = no_ocr_var.get()
            self.config["no_ocr_suffix"] = no_ocr_entry.get().strip()
            self.config["rename_has_ocr"] = has_ocr_var.get()
            self.config["has_ocr_suffix"] = has_ocr_entry.get().strip()
            self.config["remove_suffix_mode"] = remove_var.get()
            save_config(self.config)
            self.subtitle.config(text=self._subtitle_text())
            dlg.destroy()

        ttk.Button(btn_frame, text="Save", command=on_save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side="left", padx=6)

    # ---- Remove Suffixes (runs instead of process_files when remove mode is on) ----

    def _process_remove_suffixes(self, filepaths, config, done_callback, abort_event=None):
        """Remove configured suffixes from the given PDF files."""
        suffixes = []
        if config["no_ocr_suffix"]:
            suffixes.append(config["no_ocr_suffix"])
        if config["has_ocr_suffix"]:
            suffixes.append(config["has_ocr_suffix"])

        self._log(f"  Active suffixes: {', '.join(suffixes)}\n")

        removed = 0
        skipped = 0
        errors = 0
        for filepath in filepaths:
            if abort_event is not None and abort_event.is_set():
                self._log("")
                self._log("--- Aborted by user ---")
                break

            filepath = filepath.strip().strip('"').strip("'")
            if not filepath.lower().endswith(".pdf"):
                self._log(f"  SKIP     {os.path.basename(filepath)} (not a PDF)")
                continue
            basename = os.path.basename(filepath)
            try:
                new_path, matched = remove_suffix_from_file(filepath, suffixes)
                if matched:
                    new_name = os.path.basename(new_path)
                    self._log(f"  REMOVED  {basename} -> {new_name}")
                    removed += 1
                else:
                    self._log(f"  SKIP     {basename} (no matching suffix)")
                    skipped += 1
            except Exception as e:
                error_msg = f"{basename}: {e}"
                self._log(f"  ERROR    {error_msg}")
                log_error(error_msg)
                errors += 1

        self._log("")
        self._log(f"--- Remove Suffixes Results ---")
        self._log(f"  Suffixes removed:       {removed}")
        self._log(f"  Skipped (no suffix):    {skipped}")
        self._log(f"  Errors:                 {errors}")

        done_callback()

    # ---- Statistics ----

    def _show_cumulative(self):
        """Display all-time cumulative statistics in the log area."""
        cumulative, history = load_stats()
        self._log(f"")
        self._log(f"--- All-Time Statistics (across {cumulative.get('sessions', 0)} sessions) ---")
        self._log(f"  Total PDFs checked:     {cumulative.get('total', 0)}")
        self._log(f"  Has OCR (OK):           {cumulative.get('has_ocr', 0)}")
        self._log(f"  No OCR (renamed):       {cumulative.get('no_ocr_renamed', 0)}")
        self._log(f"  Has OCR (tagged):       {cumulative.get('has_ocr_renamed', 0)}")
        self._log(f"  Already tagged:         {cumulative.get('already_tagged', 0)}")
        self._log(f"  Errors:                 {cumulative.get('errors', 0)}")

    def _reset_stats(self):
        """Ask the user for confirmation, then clear all persistent statistics."""
        if messagebox.askyesno("Reset Statistics",
                               "This will permanently delete all recorded statistics.\n\nContinue?"):
            reset_stats()
            self._log("")
            self._log("--- All-time statistics have been reset ---")

    def _reset_config(self):
        """Ask the user for confirmation, then reset all settings to defaults."""
        if messagebox.askyesno("Reset Settings",
                               "This will reset all settings to their default values.\n\nContinue?"):
            self.config = dict(DEFAULT_CONFIG)
            save_config(self.config)
            self.subtitle.config(text=self._subtitle_text())
            self.view_menu.entryconfig(0,
                label="Switch to Light Mode" if self.config["dark_mode"] else "Switch to Dark Mode")
            self._apply_theme()
            self._log("")
            self._log("--- All settings have been reset to defaults ---")

    def _reset_error_log(self):
        """Ask the user for confirmation, then clear the error log file."""
        if messagebox.askyesno("Reset Error Log",
                               "This will permanently delete all recorded errors.\n\nContinue?"):
            clear_error_log()
            self._log("")
            self._log("--- Error log has been cleared ---")

    # ---- Logging ----

    def _log(self, message):
        """Write a message to the on-screen log area with color coding."""
        tag = None
        if message.startswith("  OK"):
            tag = "ok"
        elif message.startswith("  RENAMED"):
            tag = "renamed"
        elif message.startswith("  REMOVED"):
            tag = "ok"
        elif message.startswith("  TAGGED"):
            tag = "tagged"
        elif message.startswith("  SKIP"):
            tag = "skip"
        elif message.startswith("  NO-OCR"):
            tag = "renamed"
        elif message.startswith("  ERROR"):
            tag = "error"
        elif message.startswith("---") or message.startswith("  Total") or \
             message.startswith("  Has") or message.startswith("  No") or \
             message.startswith("  Already") or message.startswith("  Errors") or \
             message.startswith("  Active"):
            tag = "info"

        def _append():
            self.log_area.config(state="normal")
            if tag:
                self.log_area.insert("end", message + "\n", tag)
            else:
                self.log_area.insert("end", message + "\n")
            self.log_area.see("end")
            self.log_area.config(state="disabled")

        self.root.after(0, _append)

    # ---- Processing ----

    def _done(self):
        """Called when file processing is complete. Re-enables the drop zone."""
        def _finish():
            self.processing = False
            aborted = self.abort_event.is_set()
            self.status.config(text="Aborted" if aborted else "Done")
            self.drop_label.config(text="Drag & Drop PDF files here\nor click to browse")
            self.abort_btn.config(state="disabled")
        self.root.after(0, _finish)

    def _on_abort(self):
        """Signal the worker thread to stop after the current file."""
        if not self.processing:
            return
        self.abort_event.set()
        self.status.config(text="Aborting...")
        self.abort_btn.config(state="disabled")

    def _start_processing(self, filepaths):
        """Begin processing a list of PDF file paths in a background thread."""
        if self.processing:
            return
        if not filepaths:
            return

        self.processing = True
        self.abort_event.clear()
        self.abort_btn.config(state="normal")
        self.status.config(text=f"Processing {len(filepaths)} file(s)...")
        self.drop_label.config(text="Processing...")

        # Clear previous log output
        self.log_area.config(state="normal")
        self.log_area.delete("1.0", "end")
        self.log_area.config(state="disabled")

        # Take a snapshot of config so changes during processing don't cause issues
        config_snapshot = dict(self.config)

        if config_snapshot.get("remove_suffix_mode", False):
            self._log(f"Removing suffixes from {len(filepaths)} file(s)...\n")
            thread = threading.Thread(
                target=self._process_remove_suffixes,
                args=(filepaths, config_snapshot, self._done, self.abort_event),
                daemon=True)
        else:
            self._log(f"Checking {len(filepaths)} file(s)...\n")
            thread = threading.Thread(
                target=process_files,
                args=(filepaths, config_snapshot, self._log, self._done,
                      self.abort_event),
                daemon=True)
        thread.start()

    # ---- Drag and Drop Handling ----

    def _parse_drop_data(self, data):
        """Parse tkdnd drop data which can contain space-separated paths
        with curly braces around paths that contain spaces."""
        files = []
        i = 0
        while i < len(data):
            if data[i] == '{':
                try:
                    end = data.index('}', i)
                except ValueError:
                    break
                files.append(data[i + 1:end])
                i = end + 2
            elif data[i] == ' ':
                i += 1
            else:
                end = data.find(' ', i)
                if end == -1:
                    end = len(data)
                files.append(data[i:end])
                i = end + 1
        return files

    def _on_drop(self, event):
        files = self._parse_drop_data(event.data)
        pdf_files = [f for f in files if f.lower().endswith(".pdf")]
        self._start_processing(pdf_files)

    def _on_drag_enter(self, event):
        t = self._get_theme()
        self.drop_frame.config(highlightbackground=t["drop_hover"])
        self.drop_label.config(fg=t["drop_hover"])

    def _on_drag_leave(self, event):
        t = self._get_theme()
        self.drop_frame.config(highlightbackground=t["drop_border"])
        self.drop_label.config(fg=t["drop_fg"])

    def _on_browse(self, event=None):
        if self.processing:
            return
        files = filedialog.askopenfilenames(
            title="Select PDF files",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")])
        if files:
            self._start_processing(list(files))

    def run(self):
        self.root.mainloop()


# --------------- CLI mode (drag onto .py / .bat) ---------------

def cli_mode(filepaths):
    """Run without GUI when files are passed as command-line arguments."""
    config = load_config()
    print(f"PDF OCR Checker — Checking {len(filepaths)} file(s)...\n")

    def log(msg):
        print(msg)

    done = [False]
    def on_done():
        done[0] = True

    process_files(filepaths, config, log, on_done)
    print("\nPress Enter to exit...")
    input()


# --------------- Entry point ---------------

if __name__ == "__main__":
    cli_args = [a for a in sys.argv[1:] if a.lower().endswith(".pdf")]

    # When running as a compiled exe (PyInstaller), always use GUI mode.
    # Files dragged onto the exe are auto-processed in the GUI window.
    if cli_args and not getattr(sys, "frozen", False):
        cli_mode(cli_args)
    else:
        app = App()
        if cli_args:
            app.root.after(500, lambda: app._start_processing(cli_args))
        app.run()
