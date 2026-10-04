# Files Comparison

A WinMerge-style file and folder comparison tool for macOS/Linux/Windows,
with a modern Qt (PySide6) interface.

## Setup

```
pip3 install -r requirements.txt   # PySide6
```

Start it either way:

```
python3 app.py      # foreground (blocks the terminal)
./start.command     # background, detached — or double-click it in Finder
```

`start.command` launches the app with `nohup` and returns immediately; it
also refuses to start a second copy if one is already running. Output is
appended to `files_comparison.log`.

## Usage

1. Fill the **LEFT** and **RIGHT** panels — either two files or two folders —
   using the **File…** or **Folder…** buttons (you can also type or paste a
   path). The comparison runs automatically as soon as both sides are filled,
   or press **Compare** to re-run it.
2. Press **Compare**.
   - Two files → side-by-side diff with changed (amber), added (green),
     and removed (red) lines. Line numbers shown in gray gutters; both
     panes scroll together.
   - Two folders → a tree listing every item as *Identical*, *Different*,
     *Left only*, *Right only*, or *Binary differ*.
     Files with near-identical names on opposite sides (e.g. `doc copy`
     vs `doc cop`) are paired automatically and shown as `nameA ↔ nameB`.
     Double-click any file row to open its side-by-side diff.

## Options

- **Ignore whitespace** — leading/trailing and repeated internal whitespace
  don't count as differences.
- **Ignore case** — `ABC` and `abc` count as equal.
- **Ignore blank lines** — extra blank lines are shown in gray instead of
  red/green and don't count as differences.
- **Include subfolders** — compare folders recursively (on by default).

**Office documents** (`.docx`, `.pptx`, `.xlsx`, `.odt`, `.ods`, `.odp`) are
ZIP archives, so instead of a useless "binary" result the app extracts their
text — one line per paragraph, slide, or sheet row — and diffs that. The
status bar notes when text was extracted.

Other binary files are detected (NUL byte in the first 8 KB) and reported as
identical/different without a line diff. Text files over 10 MB are skipped.
`.DS_Store`, `__pycache__`, and VCS directories are ignored in folder scans.

## Troubleshooting

The app writes a detailed log to `files_comparison.log` in this folder —
every drop event, parsed path, and comparison result is recorded there.

## Tests

```
python3 -m unittest discover -s tests -v
```

## Files

- `diff_engine.py` — comparison logic, no GUI dependencies
- `app.py` — tkinter GUI
- `tests/test_diff_engine.py` — engine unit tests
