# Files Comparison

A WinMerge-style file and folder comparison tool for macOS/Linux/Windows,
with a modern Qt (PySide6) interface.

![icon](icon.png)

## Requirements

- Python 3.10+
- PySide6 (`pip3 install -r requirements.txt`)

## Running

```
python3 app.py      # foreground (blocks the terminal)
./start.command     # background, detached — or double-click it in Finder
./stop.command      # kill the detached instance
```

`start.command` launches the app with `nohup` and returns immediately; it
refuses to start a second copy if one is already running. Output is
appended to `files_comparison.log`. Closing the main window shuts the
whole app down — no process is left behind.

## Usage

1. Fill the **LEFT** and **RIGHT** panels — either two files or two
   folders — using the **File…** or **Folder…** buttons (you can also type
   or paste a path). The comparison runs automatically as soon as both
   sides are filled; press **Compare** to re-run it.
2. Two files → side-by-side diff with changed (amber), added (green),
   and removed (red) rows. Line numbers in gray gutters; both panes
   scroll together. Related lines are aligned globally, so a revised
   paragraph on the left sits next to its counterpart on the right.
3. Two folders → a tree listing every item as *Identical*, *Different*,
   *Left only*, *Right only*, *Type mismatch*, or *Binary differ*.
   - Files with near-identical names on opposite sides (e.g. `doc copy`
     vs `doc cop`) are paired automatically and shown as `nameA ↔ nameB`.
   - Double-click any file row to open its side-by-side diff — including
     files that exist on only one side (shown on their side).

## Options

- **Ignore whitespace** — leading/trailing and repeated internal
  whitespace doesn't count as a difference.
- **Ignore case** — `ABC` and `abc` count as equal.
- **Ignore blank lines** — extra blank lines show in gray instead of
  red/green and don't count as differences.
- **Include subfolders** — compare folders recursively (on by default).

## Supported formats

- **Text files** — any UTF-8 text is compared line by line (up to 10 MB).
- **Office/OpenDocument** — `.docx`, `.pptx`, `.xlsx`, `.odt`, `.ods`,
  `.odp`: text is extracted (one line per paragraph, slide paragraph, or
  sheet row) and diffed instead of reporting a useless "binary" result.
- **Binary files** — detected via NUL byte in the first 8 KB and reported
  as identical/different without a line diff.

Folder scans skip noise: `.DS_Store`, `__pycache__`, `.git`/`.hg`/`.svn`,
Office lock files (`~$*`), and macOS AppleDouble files (`._*`).

## Troubleshooting

The app writes a detailed log to `files_comparison.log` in this folder —
picker results, comparison decisions, and double-click events are all
recorded there.

## Tests

```
python3 -m unittest discover -s tests -v
```

## Project layout

- `app.py` — PySide6 GUI (windows, diff table, folder tree, styling)
- `diff_engine.py` — comparison logic, no GUI dependencies
- `start.command` / `stop.command` — detached launch/kill scripts
- `tools/make_icon.py` — regenerates `icon.png` (pure stdlib, no Pillow)
- `tests/test_diff_engine.py` — engine unit tests
