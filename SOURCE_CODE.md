# PDF-OCR-checker — Full Source Code with Explanations

Below is the complete source code of every file in the project, with detailed comments explaining what each part does. Written for someone with zero coding experience.

---

### pdf_ocr_checker.py

This is the main program file. It is broken into sections below.

#### Section 1: Description and Imports (Lines 1-22)

```python
"""
PDF OCR Checker - Drag & Drop Tool
Checks PDFs for text content (OCR). Renames files based on their OCR status
using configurable suffixes. Supports light/dark mode, persistent statistics,
and an options menu to customize suffix behavior.
"""
```
This is a **docstring** -- a description of what the program does. It has no effect on the program itself; it is just a note for anyone reading the code.

```python
import os
```
Loads the `os` module, which lets the program interact with the **operating system** -- things like reading file paths, renaming files, and checking if files exist.

```python
import sys
```
Loads the `sys` module, which gives access to **system-level information** -- in this case, it is used to read command-line arguments (the file paths you pass when dragging files onto the .bat file).

```python
import json
```
Loads the `json` module, which lets the program read and write **JSON files**. JSON is a simple text format for storing structured data (like settings and statistics). It looks like `{"key": "value"}`.

```python
import fitz  # PyMuPDF
```
Loads **PyMuPDF** (imported as `fitz`), which is a powerful library for reading and analyzing PDF files. This is the core tool that opens each PDF and extracts text from its pages.

```python
import threading
```
Loads the `threading` module, which allows the program to do **two things at once**. This is used so that the window (GUI) stays responsive and doesn't freeze while PDFs are being processed in the background.

```python
from datetime import datetime
```
Loads `datetime`, which provides the current date and time. Used to timestamp each session in the log file.

```python
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
```
Loads **tkinter**, which is Python's built-in library for creating graphical windows, buttons, labels, and other visual elements. The sub-modules provide:
- `ttk`: Modern-looking styled widgets (buttons, labels, etc.)
- `filedialog`: The standard "Open File" dialog window
- `scrolledtext`: A text box with a built-in scrollbar (used for the log area)
- `messagebox`: Pop-up confirmation dialogs (used for the "Reset Statistics" confirmation)

```python
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
```
This **tries** to load the `tkinterdnd2` package, which adds drag-and-drop support to the window. If it is installed, `HAS_DND` is set to `True`. If it is not installed (perhaps the user skipped `install.bat`), the program doesn't crash -- it just sets `HAS_DND` to `False` and falls back to the file browser button instead.

---

#### Section 2: File Paths (Lines 25-28)

```python
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
```
Figures out the **folder where this script is located** on disk. `__file__` is a special variable that contains the script's own file path. `os.path.abspath` makes sure it's a full path (not relative), and `os.path.dirname` extracts just the folder. This ensures all data files are stored next to the script, no matter where you launch it from.

```python
LOG_FILE = os.path.join(SCRIPT_DIR, "ocr_checker_log.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "ocr_checker_config.json")
ERROR_LOG_FILE = os.path.join(SCRIPT_DIR, "ocr_checker_errors.log")
```
Defines the full paths for three data files:
- `LOG_FILE`: Where cumulative statistics are stored (how many files checked, renamed, etc., across all sessions).
- `CONFIG_FILE`: Where settings are stored (your chosen suffixes, dark/light mode preference, etc.).
- `ERROR_LOG_FILE`: Where error messages are logged to a plain text file for later review.

All files are placed in the same folder as the script.

---

#### Section 3: Configuration / Settings Persistence (Lines 32-60)

```python
DEFAULT_CONFIG = {
    "no_ocr_suffix": "_OCR-me",
    "has_ocr_suffix": "_OCR-ok",
    "rename_no_ocr": True,
    "rename_has_ocr": False,
    "remove_suffix_mode": False,
    "dark_mode": True,
    "font_size": 10,
}
```
Defines the **default settings** that are used the very first time the program runs (before any config file exists). These are:
- `no_ocr_suffix`: The text added to file names that have no OCR. Default is `_OCR-me`.
- `has_ocr_suffix`: The text added to file names that have OCR. Default is `_OCR-ok`.
- `rename_no_ocr`: Whether to actually rename files without OCR. Default is `True` (yes, rename them).
- `rename_has_ocr`: Whether to rename files with OCR. Default is `False` (no, leave them alone).
- `remove_suffix_mode`: Whether to remove suffixes instead of adding them. Default is `False`.
- `dark_mode`: Whether the app starts in dark mode. Default is `True`.
- `font_size`: The base font size for the UI. Default is `10`.

```python
def load_config():
```
A function that **reads the settings file** from disk and returns the settings as a dictionary.

```python
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
```
Tries to open and read the config file. `json.load` converts the JSON text back into a Python dictionary.

```python
        merged = {**DEFAULT_CONFIG, **cfg}
        return merged
```
**Merges** the saved settings with the defaults. This is important because if a future version adds a new setting, older config files won't have it -- the default fills in the gap. The `{**dict1, **dict2}` syntax combines two dictionaries, with `dict2` values overriding `dict1`.

```python
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)
```
If the config file doesn't exist yet or is corrupted, just return the defaults. The program doesn't crash.

```python
def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
```
**Writes the settings** to the config file as formatted JSON. `indent=2` makes the file human-readable with nice indentation.

---

#### Section 4: Log File / Persistent Statistics (Lines 64-92)

```python
def load_stats():
```
Reads the **cumulative statistics** from the log file. Returns two things: the cumulative totals and the session history (a list of past sessions).

```python
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("cumulative", { ... }), data.get("history", [])
```
Opens and reads the log file. `data.get("cumulative", {...})` means "get the `cumulative` key from the data, but if it doesn't exist, use the fallback dictionary with all zeroes."

```python
    except (FileNotFoundError, json.JSONDecodeError):
        return { ... zeroed stats ... }, []
```
If the log file doesn't exist or is corrupted, returns all zeroes and an empty history.

```python
def save_stats(cumulative, history):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump({"cumulative": cumulative, "history": history}, f, indent=2)
```
Writes the statistics back to the log file.

```python
def reset_stats():
    save_stats({ ... all zeroes ... }, [])
```
Resets all statistics by overwriting the log file with zeroed-out data and an empty history list.

---

#### Section 4b: Error Log (Lines 96-108)

```python
def log_error(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
```
**Appends** an error message to the error log file. Each line is prefixed with a timestamp so you can see when each error occurred. The `"a"` mode means "append" -- new entries are added to the end without erasing previous ones.

```python
def clear_error_log():
    with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")
```
Clears the error log by overwriting the file with an empty string. The `"w"` mode means "write" -- it replaces all existing content.

---

#### Section 5: PDF Text Detection (Lines 113-127)

```python
def pdf_has_text(filepath, min_chars=10):
```
Defines a function called `pdf_has_text`. It takes two inputs:
- `filepath`: The location of the PDF file on your computer
- `min_chars=10`: The minimum number of text characters required to consider the PDF as "having OCR." Defaults to 10 to avoid false positives from stray characters or metadata.

```python
    try:
        doc = fitz.open(filepath)
```
Opens the PDF file using PyMuPDF. The `try:` block means "attempt this, and if something goes wrong, handle the error gracefully instead of crashing."

```python
        total_text = 0
```
Creates a counter starting at zero to track how many characters of text have been found across all pages.

```python
        for page in doc:
```
Starts a **loop** that goes through every page in the PDF, one by one.

```python
            text = page.get_text().strip()
```
Extracts all text from the current page. `.strip()` removes leading/trailing blank spaces and line breaks.

```python
            total_text += len(text)
```
Adds the number of characters found on this page to the running total.

```python
            if total_text >= min_chars:
                doc.close()
                return True
```
**Early exit optimization:** If enough text is found (10+ characters), stop checking further pages. Close the PDF and report `True`.

```python
        doc.close()
        return total_text >= min_chars
```
After all pages, close the PDF and return the final verdict.

```python
    except Exception as e:
        raise RuntimeError(f"Could not read PDF: {e}")
```
If anything went wrong (corrupted file, permission denied, etc.), raises a clear error message.

---

#### Section 5b: Suffix Sanitization (Lines 132-135)

```python
def _sanitize_suffix(suffix):
    """Remove any characters from a suffix that could cause path traversal or
    invalid file names. Only allows alphanumeric, hyphen, underscore, and dot."""
    return "".join(c for c in suffix if c.isalnum() or c in "-_.")
```
A **security function** that cleans suffix strings before they are used in file operations. It filters out any characters that are not alphanumeric, hyphens, underscores, or dots. This prevents malicious or accidental suffixes (e.g., `/../evil`) from causing **path traversal** -- where a crafted file name could write to a different directory than intended. The suffix settings come from a JSON config file, so this function acts as a safety net.

---

#### Section 6: File Renaming (Lines 138-166)

```python
def rename_file(filepath, suffix):
```
A **generic** rename function. Unlike the previous version which had a hardcoded suffix, this one accepts any suffix as a parameter. This is what allows the user to customize the suffix in the Options menu.

```python
    suffix = _sanitize_suffix(suffix)
    if not suffix:
        return filepath, False
```
**Security step:** Sanitizes the suffix before using it. If the suffix becomes empty after sanitization (e.g., it was all invalid characters), the function returns without renaming.

```python
    directory = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    name, ext = os.path.splitext(basename)
```
Breaks the file path into its parts:
- `directory`: The folder (e.g., `C:\Documents`)
- `basename`: The file name (e.g., `report.pdf`)
- `name`: The name without extension (e.g., `report`)
- `ext`: The extension (e.g., `.pdf`)

```python
    if name.endswith(suffix):
        return filepath, False
```
**Safety check:** If the file already has this suffix, don't add it again.

```python
    new_name = f"{name}{suffix}{ext}"
    new_path = os.path.join(directory, new_name)
```
Builds the new file name. Example with suffix `_OCR-me`: `report` + `_OCR-me` + `.pdf` = `report_OCR-me.pdf`.

```python
    counter = 1
    while os.path.exists(new_path):
        new_name = f"{name}{suffix}_{counter}{ext}"
        new_path = os.path.join(directory, new_name)
        counter += 1
```
**Collision handling:** If a file with the new name already exists, appends a number (`_1`, `_2`, etc.) until a unique name is found.

```python
    os.rename(filepath, new_path)
    return new_path, True
```
Renames the file on disk and returns the new path with `True` (meaning the rename happened).

---

#### Section 6b: Remove Suffix from File (Lines 169-196)

```python
def remove_suffix_from_file(filepath, suffixes):
```
The **reverse** of `rename_file` -- this function removes a previously added suffix from a file name. It takes a list of suffixes to check against, so it can remove either the "no OCR" or "has OCR" suffix.

```python
    directory = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    name, ext = os.path.splitext(basename)
```
Breaks the file path into its components (same as `rename_file`).

```python
    for suffix in suffixes:
        suffix = _sanitize_suffix(suffix)
        if suffix and name.endswith(suffix):
            new_name = name[:-len(suffix)] + ext
            new_path = os.path.join(directory, new_name)
```
Loops through each configured suffix. For each one, sanitizes it and checks if the file name ends with that suffix. If it does, builds a new name by removing the suffix. `name[:-len(suffix)]` means "everything except the last N characters" where N is the length of the suffix.

```python
            if os.path.exists(new_path):
                counter = 1
                base = name[:-len(suffix)]
                while os.path.exists(new_path):
                    new_name = f"{base}_{counter}{ext}"
                    new_path = os.path.join(directory, new_name)
                    counter += 1
```
**Collision handling:** If a file with the original name already exists (e.g., you already have `report.pdf` and you're trying to rename `report_OCR-me.pdf` back), it appends a number to avoid overwriting.

```python
            os.rename(filepath, new_path)
            return new_path, suffix
    return filepath, None
```
Renames the file and returns the new path along with which suffix was removed. If no matching suffix was found, returns the original path and `None`.

---

#### Section 7: Processing Multiple Files (Lines 142-218)

```python
def process_files(filepaths, config, log_callback, done_callback):
```
The main processing function. Now takes a `config` dictionary so it knows which suffixes to use and which renaming rules are active.

```python
    no_ocr_suffix = config["no_ocr_suffix"]
    has_ocr_suffix = config["has_ocr_suffix"]
    do_rename_no_ocr = config["rename_no_ocr"]
    do_rename_has_ocr = config["rename_has_ocr"]
```
Extracts the current settings into local variables for easy access.

```python
    active_suffixes = []
    if do_rename_no_ocr and no_ocr_suffix:
        active_suffixes.append(no_ocr_suffix)
    if do_rename_has_ocr and has_ocr_suffix:
        active_suffixes.append(has_ocr_suffix)
```
Builds a list of all suffixes that are currently in use. This is checked later to detect files that were already tagged in a previous run.

```python
    results = {
        "total": 0, "has_ocr": 0, "no_ocr_renamed": 0,
        "has_ocr_renamed": 0, "already_tagged": 0, "errors": 0
    }
```
Creates counters for tracking session statistics. Now includes `has_ocr_renamed` for files with OCR that get tagged.

The **main loop** (`for filepath in filepaths:`) works the same as before but with two key differences:

**Already-tagged detection** now checks against all active suffixes:
```python
        for sfx in active_suffixes:
            if name_no_ext.endswith(sfx):
                log_callback(f"  SKIP     {basename} (already tagged {sfx})")
```

**The decision logic** now handles four scenarios:
```python
        if has_text:
            if do_rename_has_ocr and has_ocr_suffix:
                # Rename files WITH OCR (if enabled)
                ...
            else:
                # Just report OK (don't rename)
                ...
        else:
            if do_rename_no_ocr and no_ocr_suffix:
                # Rename files WITHOUT OCR (if enabled)
                ...
            else:
                # Just report as no-OCR (don't rename)
                ...
```

When an error occurs (file not found, corrupted PDF, permission denied, etc.), the error message is both displayed in the UI via `log_callback` and written to the error log file via `log_error`. This means every error shown on screen is also persisted to `ocr_checker_errors.log` for later review.

After all files are processed, the function:

1. **Prints a session summary** (results from this batch only).
2. **Loads the existing cumulative stats** from the log file.
3. **Adds this session's numbers** to the cumulative totals.
4. **Appends a session entry** to the history list with a timestamp.
5. **Saves everything** back to the log file.
6. **Prints the all-time summary** below the session summary.
7. **Calls `done_callback()`** to signal that processing is finished.

---

#### Section 8: Theme Colors (Lines 222-268)

```python
THEMES = {
    "dark": { ... },
    "light": { ... },
}
```
Defines two complete **color palettes** -- one for dark mode and one for light mode. Each palette is a dictionary that maps a purpose (like `"bg"` for background, `"ok"` for success messages) to a hex color code.

**Dark mode** uses colors from the Catppuccin Mocha palette (dark blues, soft pastels).
**Light mode** uses colors from the Catppuccin Latte palette (light grays, vivid accents).

Each theme defines colors for:
- `bg`: Main window background
- `drop_bg`, `drop_border`, `drop_fg`, `drop_hover`: Drop zone colors
- `log_bg`, `log_fg`, `log_select`: Log area colors
- `title_fg`, `label_fg`: Text colors
- `ok`, `renamed`, `tagged`, `skip`, `error`, `info`: Log message colors
- `btn_bg`, `btn_fg`: Button colors

---

#### Section 9: The App Class -- Initialization (Lines 273-293)

```python
class App:
    def __init__(self):
```
The `App` class contains the entire graphical application. `__init__` is the constructor that runs when the app starts.

```python
        self.config = load_config()
```
**Loads the saved settings** (suffixes, dark/light mode) from the config file. If no config file exists, uses the defaults.

```python
        if HAS_DND:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()
```
Creates the main window, using drag-and-drop support if available.

```python
        self.root.title("PDF OCR Checker")
        self.root.geometry("750x600")
        self.root.minsize(550, 450)
```
Sets the window title and size (slightly larger than before to fit the new features).

```python
        self.processing = False
        self._build_ui()
        self._apply_theme()
```
Sets the processing flag, builds all visual elements, then applies the correct color theme.

---

#### Section 10: Theme & Font Application (Lines 297-340)

```python
    def _apply_fonts(self):
```
Applies font sizes to all UI elements based on the `font_size` config value. The base size scales all fonts proportionally:
- Title: base + 4
- Drop zone label: base + 1
- Labels / status: base
- Buttons / log area: base - 1

Also updates the font size menu checkmarks to indicate the current selection.

```python
    def _get_theme(self):
        return THEMES["dark"] if self.config["dark_mode"] else THEMES["light"]
```
Returns the correct color palette based on the current setting.

```python
    def _apply_theme(self):
        t = self._get_theme()
        self.root.configure(bg=t["bg"])
        ...
```
Goes through **every widget** in the window and updates its colors to match the current theme. This includes:
- The main window background
- All ttk styles (labels, buttons)
- The drop zone (background, border, text)
- The log area (background, text, selection, and all color tags)
- The button bar
- The menu bar and all sub-menus

Calls `_apply_fonts()` at the end to ensure font sizes are also applied. This function is called once at startup and again every time the user toggles the theme.

---

#### Section 11: Building the UI (Lines 343-410)

```python
    def _build_ui(self):
```
Creates all the visual elements of the window.

**Menu bar:**
```python
        self.menubar = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=self.menubar)
```
Creates a **menu bar** at the top of the window (the horizontal bar with "Options" and "View"). `tearoff=0` prevents the menu from being "torn off" into a floating window (an old tkinter behavior).

```python
        self.options_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Options", menu=self.options_menu)
        self.options_menu.add_command(label="Suffix Settings...", command=self._open_suffix_settings)
        self.options_menu.add_separator()
        self.options_menu.add_command(label="Reset Settings to Defaults...", command=self._reset_config)
        self.options_menu.add_command(label="Reset All-Time Statistics...", command=self._reset_stats)
        self.options_menu.add_command(label="Reset Error Log...", command=self._reset_error_log)
```
Creates the **Options** menu with four items:
- **Suffix Settings...**: Opens the dialog to configure suffixes (including a "remove mode" checkbox)
- **Reset Settings to Defaults...**: Resets all settings (suffixes, theme, font size) back to their default values
- **Reset All-Time Statistics...**: Clears the statistics log file
- **Reset Error Log...**: Clears the error log file

```python
        self.view_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="View", menu=self.view_menu)
        self.view_menu.add_command(
            label="Switch to Light Mode" if self.config["dark_mode"] else "Switch to Dark Mode",
            command=self._toggle_theme)
```
Creates the **View** menu with items for toggling between dark and light mode, and a **Font Size** submenu with preset sizes (8, 9, 10, 11, 12, 14). The current size is indicated with a `>` prefix.

**Subtitle label:**
```python
        self.subtitle = ttk.Label(self.root, text=self._subtitle_text())
```
Shows the currently active renaming rules below the title. This updates whenever settings are changed.

**Button bar:**
```python
        self.btn_frame = tk.Frame(self.root)
        ...
        ttk.Button(self.btn_frame, text="Browse Files...", command=self._on_browse)
        ttk.Button(self.btn_frame, text="Show All-Time Stats", command=self._show_cumulative)
```
Adds a row of buttons below the drop zone:
- **Browse Files...**: Opens the file picker (same as clicking the drop zone)
- **Show All-Time Stats**: Displays cumulative statistics in the log area

All other UI elements (drop zone, log area, status bar) work the same as before.

```python
    def _subtitle_text(self):
```
Builds the subtitle string dynamically from the current settings. Shows which renaming rules are active, e.g., `Active rules: No OCR -> "_OCR-me" | Has OCR -> "_OCR-ok"`.

---

#### Section 12: Theme Toggle & Font Size (Lines 413-425)

```python
    def _toggle_theme(self):
        self.config["dark_mode"] = not self.config["dark_mode"]
        save_config(self.config)
        self._apply_theme()
        self.view_menu.entryconfig(0,
            label="Switch to Light Mode" if self.config["dark_mode"] else "Switch to Dark Mode")
```
Flips the `dark_mode` setting, saves it to the config file, repaints all widgets with the new colors, and updates the menu label to show the opposite option.

```python
    def _set_font_size(self, size):
        self.config["font_size"] = size
        save_config(self.config)
        self._apply_fonts()
```
Sets the font size to the chosen value, saves to config, and immediately applies the new size to all UI elements.

---

#### Section 13: Suffix Settings Dialog (Lines 428-490)

```python
    def _open_suffix_settings(self):
        dlg = tk.Toplevel(self.root)
```
Opens a **new dialog window** (`Toplevel`) on top of the main window. This is the settings popup.

```python
        dlg.transient(self.root)
        dlg.grab_set()
```
- `transient`: Makes the dialog visually linked to the main window (it moves with it, appears on top).
- `grab_set`: Prevents the user from clicking on the main window while the dialog is open (they must close it first).

The dialog contains:

**For files WITHOUT OCR:**
```python
        no_ocr_var = tk.BooleanVar(value=self.config["rename_no_ocr"])
        tk.Checkbutton(dlg, text="Rename these files", variable=no_ocr_var, ...)
```
A **checkbox** that enables or disables renaming for files without OCR. `BooleanVar` is a special variable that tkinter checkboxes can read and write.

```python
        no_ocr_entry = tk.Entry(dlg, width=25)
        no_ocr_entry.insert(0, self.config["no_ocr_suffix"])
```
A **text input field** pre-filled with the current suffix. The user can type any suffix they want.

**For files WITH OCR:** Same pattern -- a checkbox and a text input.

**Save button:**
```python
        def on_save():
            self.config["rename_no_ocr"] = no_ocr_var.get()
            self.config["no_ocr_suffix"] = no_ocr_entry.get().strip()
            self.config["rename_has_ocr"] = has_ocr_var.get()
            self.config["has_ocr_suffix"] = has_ocr_entry.get().strip()
            save_config(self.config)
            self.subtitle.config(text=self._subtitle_text())
            dlg.destroy()
```
When "Save" is clicked:
1. Reads the current values from all checkboxes and text fields.
2. Updates the config dictionary.
3. Saves to disk.
4. Updates the subtitle in the main window to reflect the new rules.
5. Closes the dialog.

---

#### Section 13b: Remove Suffixes Mode

The Suffix Settings dialog includes a **"Remove suffixes instead of adding them"** checkbox. When enabled, the `remove_suffix_mode` config value is set to `True`.

```python
        remove_var = tk.BooleanVar(value=self.config.get("remove_suffix_mode", False))
        tk.Checkbutton(dlg, text="Remove suffixes instead of adding them",
                       variable=remove_var, ...)
```

When remove mode is active, dropping files into the app (or browsing) triggers `_process_remove_suffixes` instead of `process_files`. This method:

1. Collects both configured suffixes (no-OCR and has-OCR) into a list
2. Loops through each dropped file, calling `remove_suffix_from_file()` for each
3. Logs the result with `REMOVED` (green), `SKIP` (gray), or `ERROR` (red)
4. Shows a summary of how many files were modified, skipped, or had errors

The subtitle bar updates to show **"Remove mode: stripping ..."** so the user always knows which mode is active. The setting is saved to config and persists between sessions.

---

#### Section 14: Statistics Display & Reset Methods (Lines 493-530)

```python
    def _show_cumulative(self):
        cumulative, history = load_stats()
        self._log(f"--- All-Time Statistics (across {cumulative.get('sessions', 0)} sessions) ---")
        ...
```
Loads the stats from the log file and displays them in the log area.

```python
    def _reset_stats(self):
        if messagebox.askyesno("Reset Statistics",
                               "This will permanently delete all recorded statistics.\n\nContinue?"):
            reset_stats()
            self._log("--- All-time statistics have been reset ---")
```
Shows a **confirmation dialog** ("Yes" / "No"). Only if the user clicks "Yes" does it actually clear the statistics log file.

```python
    def _reset_config(self):
        if messagebox.askyesno("Reset Settings",
                               "This will reset all settings to their default values.\n\nContinue?"):
            self.config = dict(DEFAULT_CONFIG)
            save_config(self.config)
            ...
```
Resets all settings (suffixes, dark/light mode, font size) back to the values defined in `DEFAULT_CONFIG`. After saving, it immediately updates the UI: refreshes the subtitle text, updates the theme toggle menu label, reapplies the theme and font sizes, and logs a confirmation message.

```python
    def _reset_error_log(self):
        if messagebox.askyesno("Reset Error Log",
                               "This will permanently delete all recorded errors.\n\nContinue?"):
            clear_error_log()
            self._log("--- Error log has been cleared ---")
```
Clears the error log file (`ocr_checker_errors.log`) after a confirmation dialog. This removes all previously recorded error entries.

---

#### Section 15: Logging (Lines 511-536)

```python
    def _log(self, message):
```
Writes a color-coded message to the log area. Each log line starts with a fixed-width label (padded to 7 characters) so that the file names and descriptions align neatly in a column. The label determines the color tag:
- `"OK"` (green): Files with OCR, left unchanged.
- `"RENAMED"` (orange): Files without OCR, renamed.
- `"REMOVED"` (green): Files that had a suffix removed via the Remove Suffixes feature.
- `"TAGGED"` (teal): Files with OCR that get renamed with the has-OCR suffix.
- `"NO-OCR"` (orange): Files without OCR when renaming is disabled.
- `"SKIP"` (gray): Files already tagged or not PDFs.
- `"ERROR"` (red): Files that couldn't be read.
- `"info"` (blue): Summary statistics lines.

---

#### Section 16: Processing (Lines 539-573)

```python
    def _start_processing(self, filepaths):
```
Same structure as before, with two important additions:

```python
        config_snapshot = dict(self.config)
```
Takes a **snapshot** (copy) of the current settings before starting the background thread. This prevents issues if the user changes settings mid-processing -- the processing thread uses the settings as they were when it started.

```python
        if config_snapshot.get("remove_suffix_mode", False):
            ...
            thread = threading.Thread(
                target=self._process_remove_suffixes,
                args=(filepaths, config_snapshot, self._done),
                daemon=True)
        else:
            ...
            thread = threading.Thread(
                target=process_files,
                args=(filepaths, config_snapshot, self._log, self._done),
                daemon=True)
```
**Branches based on remove mode:** If remove mode is enabled in the config, it runs `_process_remove_suffixes` (which strips suffixes from file names) instead of `process_files` (which checks for OCR and adds suffixes). Both run in a background thread.

---

#### Section 17: Drag-and-Drop & Event Handlers (Lines 834-880)

```python
    def _parse_drop_data(self, data):
```
Parses the raw string that tkdnd provides when files are dropped onto the window. The format is tricky: file paths are space-separated, but paths containing spaces are wrapped in curly braces (e.g., `{C:\My Documents\file.pdf}`). This function handles both formats.

```python
            if data[i] == '{':
                try:
                    end = data.index('}', i)
                except ValueError:
                    break
```
**Security fix:** When looking for the closing brace `}`, the code wraps the search in a `try/except ValueError`. If the drop data contains a malformed entry with an opening brace but no closing brace, the parser stops cleanly instead of crashing.

```python
    def _on_drag_enter(self, event):
        t = self._get_theme()
        self.drop_frame.config(highlightbackground=t["drop_hover"])
        self.drop_label.config(fg=t["drop_hover"])
```
The drag hover colors come from the current theme instead of being hardcoded, so they look correct in both light and dark mode.

---

#### Section 18: CLI Mode (Lines 626-640)

```python
def cli_mode(filepaths):
    config = load_config()
    ...
    process_files(filepaths, config, log, on_done)
```
The command-line mode now also loads the config file, so your suffix settings apply even when dragging files onto the .bat file.

---

#### Section 19: Entry Point (Lines 643-656)

```python
if __name__ == "__main__":
    cli_args = [a for a in sys.argv[1:] if a.lower().endswith(".pdf")]

    if cli_args and not getattr(sys, "frozen", False):
        cli_mode(cli_args)
    else:
        app = App()
        if cli_args:
            app.root.after(500, lambda: app._start_processing(cli_args))
        app.run()
```
Decides how to start the application:
- `sys.frozen` is a special attribute set by **PyInstaller** when running as a compiled exe. `getattr(sys, "frozen", False)` checks for it safely.
- **Running as a Python script with PDF arguments**: uses CLI mode (prints to the console).
- **Running as a compiled exe with PDF arguments** (e.g., files dragged onto the exe): opens the GUI and automatically starts processing the files after a short delay (500ms to let the window finish loading).
- **Running without arguments**: opens the GUI normally.

---

### PDF OCR Checker.bat

```batch
@echo off
cd /d "%~dp0"
python app\pdf_ocr_checker.py %*
```

Line-by-line:

- `@echo off` -- Tells Windows not to display each command as it runs. Without this, you'd see the commands themselves printed in the window, which looks messy.
- `cd /d "%~dp0"` -- Changes the current directory to **wherever this .bat file is located**. `%~dp0` is a special Windows variable that means "the drive and folder path of the batch file being run." This ensures the program can find `pdf_ocr_checker.py` even if you run the .bat file from a different location.
- `python app\pdf_ocr_checker.py %*` -- Runs the Python script from the `app` subfolder. `%*` passes along **all arguments** -- meaning if you dragged files onto this .bat file, those file paths are forwarded to the Python script.

---

### install.bat

```batch
@echo off
echo ========================================
echo   PDF-OCR-checker - Setup
echo ========================================
echo.
echo Installing required Python packages...
pip install PyMuPDF tkinterdnd2
echo.
echo ----------------------------------------
echo   Setup complete!
echo   You can now:
echo     1. Double-click "PDF OCR Checker.bat" to open the GUI
echo     2. Drag PDF files onto "PDF OCR Checker.bat"
echo ----------------------------------------
pause
```

Line-by-line:

- `@echo off` -- Hides the command text (same as above).
- `echo ...` lines -- Print messages to the screen so you know what's happening.
- `echo.` -- Prints a blank line (for visual spacing).
- `pip install PyMuPDF tkinterdnd2` -- **This is the key line.** `pip` is Python's package installer. This command downloads and installs:
  - **PyMuPDF**: The library that reads PDF files and extracts text
  - **tkinterdnd2**: The library that enables drag-and-drop in the window
- `pause` -- Keeps the window open after installation so you can read the messages. Press any key to close it.

---

### requirements.txt

```
PyMuPDF>=1.23.0
tkinterdnd2>=0.3.0
```

This file lists the **required Python packages** and their minimum versions:
- `PyMuPDF>=1.23.0` means "PyMuPDF version 1.23.0 or newer"
- `tkinterdnd2>=0.3.0` means "tkinterdnd2 version 0.3.0 or newer"

This file is a standard convention in Python projects. It allows anyone to install all dependencies at once by running `pip install -r requirements.txt`. In this project, the `install.bat` file does the same thing in a more user-friendly way.

---

### build.bat

```batch
@echo off
echo ========================================
echo   PDF-OCR-checker - Build Standalone EXE
echo ========================================
echo.
echo Requires: Python, PyInstaller, PyMuPDF, tkinterdnd2
echo.
echo Installing/updating build dependencies...
pip install pyinstaller PyMuPDF tkinterdnd2
echo.
echo Building standalone executable...
cd /d "%~dp0"
python -m PyInstaller --onefile --windowed --name "PDF OCR Checker v1" --collect-all tkinterdnd2 --distpath "..\standalone" --specpath "build_temp" --workpath "build_temp\work" pdf_ocr_checker.py
echo.
echo Cleaning up build files...
rmdir /s /q build_temp 2>nul
echo.
echo ----------------------------------------
echo   Build complete!
echo   The standalone exe is in: ..\standalone\PDF OCR Checker v1.exe
echo ----------------------------------------
pause
```

This script compiles the Python application into a **standalone Windows executable** using PyInstaller:

- `pip install pyinstaller PyMuPDF tkinterdnd2` -- Ensures all build dependencies are installed.
- `python -m PyInstaller` -- Runs PyInstaller as a Python module.
  - `--onefile`: Bundles everything into a single `.exe` file.
  - `--windowed`: Hides the console window (the app has its own GUI).
  - `--name "PDF OCR Checker v1"`: Sets the output file name.
  - `--collect-all tkinterdnd2`: Ensures the drag-and-drop library and its native files are included.
  - `--distpath "..\standalone"`: Places the finished exe in the `standalone` folder (one level up from `app`).
  - `--specpath` / `--workpath`: Temporary build files, cleaned up afterwards.
- `rmdir /s /q build_temp` -- Deletes the temporary build files after the exe is created.
