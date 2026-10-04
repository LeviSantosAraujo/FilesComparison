"""Core file/folder comparison logic. No GUI dependencies."""

from __future__ import annotations

import difflib
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# Line kinds
EQUAL = "equal"
CHANGED = "changed"
ADDED = "added"
REMOVED = "removed"
BLANK = "blank"  # add/remove of blank lines only, ignored under ignore_blank_lines

# Folder entry statuses
IDENTICAL = "identical"
DIFFERENT = "different"
LEFT_ONLY = "left_only"
RIGHT_ONLY = "right_only"
TYPE_MISMATCH = "type_mismatch"
BINARY = "binary"
ERROR = "error"

MAX_DIFF_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_BINARY_CHUNK = 8192

# Names skipped during folder scans (noise on every platform)
IGNORED_NAMES = frozenset({".DS_Store", "__pycache__", ".git", ".hg", ".svn"})


def _is_ignored(name: str) -> bool:
    # ~$* are Office lock/owner temp files; ._* are macOS AppleDouble files
    return (name in IGNORED_NAMES
            or name.startswith("~$")
            or name.startswith("._"))


@dataclass
class DiffOptions:
    ignore_whitespace: bool = False
    ignore_case: bool = False
    ignore_blank_lines: bool = False
    recursive: bool = True


@dataclass
class SideLine:
    lineno: int  # 1-based
    text: str    # original text, line ending stripped
    kind: str    # equal/changed/added/removed/blank


@dataclass
class DiffRow:
    left: SideLine | None   # None = blank pad cell
    right: SideLine | None


@dataclass
class FileResult:
    left_path: Path
    right_path: Path
    rows: list[DiffRow] = field(default_factory=list)
    is_binary: bool = False
    identical: bool = False
    summary: dict = field(default_factory=dict)  # kind -> count of lines
    error: str | None = None
    note: str | None = None  # e.g. "text extracted from .docx"


@dataclass
class DirEntry:
    relpath: str
    status: str
    is_dir: bool
    left_path: Path | None
    right_path: Path | None


def is_binary(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(_BINARY_CHUNK)
    except OSError:
        return False
    return b"\x00" in chunk


def read_lines(path: Path) -> list[str]:
    return path.read_bytes().decode("utf-8", errors="replace").splitlines()


# --- Office document text extraction (docx/pptx/xlsx/odf are ZIPs of XML) ---

_OFFICE_EXTS = {".docx", ".docm", ".pptx", ".pptm", ".xlsx", ".xlsm",
                ".odt", ".ods", ".odp"}
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_OT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def _is_zip(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"PK\x03\x04"
    except OSError:
        return False


def _docx_lines(zf: zipfile.ZipFile) -> list[str]:
    names = [n for n in zf.namelist() if n == "word/document.xml"]
    names += sorted(n for n in zf.namelist()
                    if re.fullmatch(r"word/(header|footer)\d*\.xml", n))
    lines = []
    for name in names:
        root = ET.fromstring(zf.read(name))
        for p in root.iter(_W + "p"):
            parts = []
            for node in p.iter():
                if node.tag == _W + "t":
                    parts.append(node.text or "")
                elif node.tag == _W + "tab":
                    parts.append("\t")
            lines.append("".join(parts))
    return lines


def _pptx_lines(zf: zipfile.ZipFile) -> list[str]:
    slides = sorted(
        (n for n in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
        key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[-1]).group()))
    lines = []
    for i, name in enumerate(slides, 1):
        if len(slides) > 1:
            lines.append(f"── slide {i} ──")
        root = ET.fromstring(zf.read(name))
        for p in root.iter(_A + "p"):
            lines.append("".join(t.text or "" for t in p.iter(_A + "t")))
    return lines


def _xlsx_lines(zf: zipfile.ZipFile) -> list[str]:
    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.iter(_X + "si"):
            shared.append("".join(t.text or "" for t in si.iter(_X + "t")))
    sheets = sorted(
        (n for n in zf.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
        key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[-1]).group()))
    lines = []
    for i, name in enumerate(sheets, 1):
        if len(sheets) > 1:
            lines.append(f"── sheet {i} ──")
        root = ET.fromstring(zf.read(name))
        for row in root.iter(_X + "row"):
            cells = []
            for c in row.iter(_X + "c"):
                v = c.find(_X + "v")
                txt = v.text if v is not None and v.text is not None else ""
                if c.get("t") == "s" and txt.isdigit() and int(txt) < len(shared):
                    txt = shared[int(txt)]
                cells.append(txt)
            lines.append("\t".join(cells))
    return lines


def _odf_lines(zf: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(zf.read("content.xml"))
    return ["".join(el.itertext())
            for el in root.iter() if el.tag in (_OT + "p", _OT + "h")]


def extract_document_lines(path: Path) -> tuple[list[str], str] | None:
    """Return (lines, description) for ZIP-based Office docs, else None."""
    ext = path.suffix.lower()
    if ext not in _OFFICE_EXTS or not _is_zip(path):
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "word/document.xml" in names:
                lines = _docx_lines(zf)
            elif any(re.fullmatch(r"ppt/slides/slide\d+\.xml", n) for n in names):
                lines = _pptx_lines(zf)
            elif any(re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n) for n in names):
                lines = _xlsx_lines(zf)
            elif "content.xml" in names:
                lines = _odf_lines(zf)
            else:
                return None
        return lines, f"text extracted from {ext} — one line per paragraph/cell"
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return None


def _normalize(line: str, options: DiffOptions) -> str:
    if options.ignore_whitespace:
        line = " ".join(line.split())
    if options.ignore_case:
        line = line.casefold()
    return line


def _row_is_diff(row: DiffRow) -> bool:
    kinds = {s.kind for s in (row.left, row.right) if s is not None}
    return bool(kinds - {EQUAL, BLANK})


# --- line alignment -------------------------------------------------------
# A "pair" op couples left line i with right line j; _emit turns it into an
# EQUAL or CHANGED row depending on normalized equality.
#
# Two strategies:
#  * _global_align — Needleman-Wunsch over the whole file: finds the best
#    pairing overall, so related lines pair as changed even when difflib's
#    LCS would split them into separate delete/insert regions (the common
#    case for heavily revised documents).
#  * _difflib_align — fast LCS fallback for very large files.
_ALIGN_GAP = 0.3        # penalty for an unpaired (add/remove) line
_ALIGN_MIN_SIM = 0.61   # > 2*gap, so an accepted pair always beats two gaps
_EQUAL_BONUS = 2.0
_MAX_GLOBAL_CELLS = 80_000  # n*m cap for the global aligner
_MAX_FUZZY_PAIRS = 20000    # per-hunk n*m cap in the difflib fallback


def _lenient(line: str) -> str:
    # lenient normalization for similarity only — pairing is about
    # relatedness, not equality, so case/whitespace shouldn't block a pair
    return " ".join(line.split()).casefold()


def _global_align(left_lines, right_lines, norm_left, norm_right):
    n, m = len(left_lines), len(right_lines)
    matcher = difflib.SequenceMatcher(autojunk=False)
    sim = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            if norm_left[i] == norm_right[j]:
                sim[i][j] = _EQUAL_BONUS
                continue
            a, b = _lenient(left_lines[i]), _lenient(right_lines[j])
            if not a or not b:
                continue
            matcher.set_seqs(a, b)
            if matcher.real_quick_ratio() >= _ALIGN_MIN_SIM:
                r = matcher.ratio()
                if r >= _ALIGN_MIN_SIM:
                    sim[i][j] = r

    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] - _ALIGN_GAP
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] - _ALIGN_GAP
    for i in range(1, n + 1):
        prev, cur, srow = dp[i - 1], dp[i], sim[i - 1]
        for j in range(1, m + 1):
            best = prev[j] - _ALIGN_GAP
            down = cur[j - 1] - _ALIGN_GAP
            if down > best:
                best = down
            if srow[j - 1] > 0:
                diag = prev[j - 1] + srow[j - 1]
                if diag > best:
                    best = diag
            cur[j] = best

    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if (i > 0 and j > 0 and sim[i - 1][j - 1] > 0
                and dp[i][j] == dp[i - 1][j - 1] + sim[i - 1][j - 1]):
            ops.append(("pair", i - 1, j - 1))
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j] == dp[i][j - 1] - _ALIGN_GAP):
            ops.append(("add", None, j - 1))
            j -= 1
        else:
            ops.append(("del", i - 1, None))
            i -= 1
    ops.reverse()
    return ops


def _align_hunk(dels, adds, left_lines, right_lines):
    """Order-preserving fuzzy pairing inside one difflib change hunk.
    Returns ops ("pair"|"del"|"add", i, j) with i/j indexing dels/adds."""
    n, m = len(dels), len(adds)
    if n == m or n * m > _MAX_FUZZY_PAIRS:
        # same-size hunk (or too big for fuzzy): pair positionally
        ops = [("pair", t, t) for t in range(min(n, m))]
        ops += [("del", t, None) for t in range(min(n, m), n)]
        ops += [("add", None, t) for t in range(min(n, m), m)]
        return ops

    sim = [[0.0] * m for _ in range(n)]
    for i, di in enumerate(dels):
        for j, aj in enumerate(adds):
            r = difflib.SequenceMatcher(
                None, _lenient(left_lines[di]), _lenient(right_lines[aj])).ratio()
            if r >= _ALIGN_MIN_SIM:
                sim[i][j] = r

    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        prev, cur, srow = dp[i - 1], dp[i], sim[i - 1]
        for j in range(1, m + 1):
            best = prev[j] if prev[j] >= cur[j - 1] else cur[j - 1]
            diag = prev[j - 1] + srow[j - 1]
            cur[j] = diag if diag > best else best

    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if (i > 0 and j > 0 and sim[i - 1][j - 1] > 0
                and dp[i][j] == dp[i - 1][j - 1] + sim[i - 1][j - 1]):
            ops.append(("pair", i - 1, j - 1))
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j] == dp[i][j - 1]):
            ops.append(("add", None, j - 1))
            j -= 1
        else:
            ops.append(("del", i - 1, None))
            i -= 1
    ops.reverse()
    return ops


def _difflib_align(left_lines, right_lines, norm_left, norm_right):
    """Fallback for large files: LCS anchors + fuzzy pairing inside hunks."""
    sm = difflib.SequenceMatcher(a=norm_left, b=norm_right, autojunk=False)
    opcodes = sm.get_opcodes()
    ops = []
    k = 0
    while k < len(opcodes):
        tag, i1, i2, j1, j2 = opcodes[k]
        if tag == "equal":
            for t in range(i2 - i1):
                ops.append(("pair", i1 + t, j1 + t))
            k += 1
            continue
        dels, adds = [], []
        while k < len(opcodes) and opcodes[k][0] != "equal":
            t, a1, a2, b1, b2 = opcodes[k]
            if t in ("delete", "replace"):
                dels.extend(range(a1, a2))
            if t in ("insert", "replace"):
                adds.extend(range(b1, b2))
            k += 1
        for op, i, j in _align_hunk(dels, adds, left_lines, right_lines):
            ops.append((op,
                        dels[i] if i is not None else None,
                        adds[j] if j is not None else None))
    return ops


def diff_lines(left_lines: list[str], right_lines: list[str],
               options: DiffOptions | None = None) -> list[DiffRow]:
    """Align two lists of lines into side-by-side rows using normalized matching."""
    options = options or DiffOptions()
    norm_left = [_normalize(l, options) for l in left_lines]
    norm_right = [_normalize(l, options) for l in right_lines]

    if len(left_lines) * len(right_lines) <= _MAX_GLOBAL_CELLS:
        ops = _global_align(left_lines, right_lines, norm_left, norm_right)
    else:
        ops = _difflib_align(left_lines, right_lines, norm_left, norm_right)

    rows: list[DiffRow] = []
    for op, i, j in ops:
        if op == "pair":
            kind = EQUAL if norm_left[i] == norm_right[j] else CHANGED
            rows.append(DiffRow(
                SideLine(i + 1, left_lines[i], kind),
                SideLine(j + 1, right_lines[j], kind)))
        elif op == "del":
            rows.append(DiffRow(
                SideLine(i + 1, left_lines[i], REMOVED), None))
        else:
            rows.append(DiffRow(None,
                SideLine(j + 1, right_lines[j], ADDED)))

    if options.ignore_blank_lines:
        for row in rows:
            for side in (row.left, row.right):
                if side and side.kind in (ADDED, REMOVED) and not side.text.strip():
                    side.kind = BLANK
    return rows


def compare_files(left_path, right_path,
                  options: DiffOptions | None = None) -> FileResult:
    options = options or DiffOptions()
    left_path, right_path = Path(left_path), Path(right_path)
    result = FileResult(left_path, right_path)

    # Office docs (docx/pptx/xlsx/odf) are ZIPs — diff their extracted text
    left_doc = extract_document_lines(left_path)
    right_doc = extract_document_lines(right_path)
    if left_doc is not None and right_doc is not None:
        lines_l, result.note = left_doc
        lines_r, _ = right_doc
        result.rows = diff_lines(lines_l, lines_r, options)
        for row in result.rows:
            for kind in {s.kind for s in (row.left, row.right) if s and s.kind != EQUAL}:
                result.summary[kind] = result.summary.get(kind, 0) + 1
        result.identical = not any(_row_is_diff(r) for r in result.rows)
        return result

    if is_binary(left_path) or is_binary(right_path):
        result.is_binary = True
        try:
            result.identical = left_path.read_bytes() == right_path.read_bytes()
        except OSError as e:
            result.error = str(e)
        return result

    try:
        for p in (left_path, right_path):
            if p.stat().st_size > MAX_DIFF_FILE_SIZE:
                result.error = f"{p.name} exceeds the {MAX_DIFF_FILE_SIZE // (1 << 20)} MB diff limit"
                return result
        rows = diff_lines(read_lines(left_path), read_lines(right_path), options)
    except OSError as e:
        result.error = str(e)
        return result

    result.rows = rows
    for row in rows:
        for kind in {s.kind for s in (row.left, row.right) if s and s.kind != EQUAL}:
            result.summary[kind] = result.summary.get(kind, 0) + 1
    result.identical = not any(_row_is_diff(r) for r in rows)
    return result


def _scan(root: Path, recursive: bool) -> dict[str, Path]:
    result: dict[str, Path] = {}
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not _is_ignored(d)]
            for name in dirnames + filenames:
                if _is_ignored(name):
                    continue
                p = Path(dirpath) / name
                result[p.relative_to(root).as_posix()] = p
    else:
        for p in root.iterdir():
            if not _is_ignored(p.name):
                result[p.name] = p
    return result


def compare_dirs(left_dir, right_dir,
                 options: DiffOptions | None = None) -> list[DirEntry]:
    options = options or DiffOptions()
    left_dir, right_dir = Path(left_dir), Path(right_dir)
    left_map = _scan(left_dir, options.recursive)
    right_map = _scan(right_dir, options.recursive)

    entries: list[DirEntry] = []
    for rel in sorted(set(left_map) | set(right_map)):
        lp, rp = left_map.get(rel), right_map.get(rel)
        if lp is None:
            entries.append(DirEntry(rel, RIGHT_ONLY, rp.is_dir(), None, rp))
        elif rp is None:
            entries.append(DirEntry(rel, LEFT_ONLY, lp.is_dir(), lp, None))
        elif lp.is_dir() or rp.is_dir():
            status = IDENTICAL if lp.is_dir() == rp.is_dir() else TYPE_MISMATCH
            entries.append(DirEntry(rel, status, lp.is_dir(), lp, rp))
        else:
            try:
                office = (extract_document_lines(lp) is not None
                          and extract_document_lines(rp) is not None)
                if office:
                    status = IDENTICAL if compare_files(lp, rp, options).identical else DIFFERENT
                elif is_binary(lp) or is_binary(rp):
                    status = IDENTICAL if lp.read_bytes() == rp.read_bytes() else BINARY
                else:
                    status = IDENTICAL if compare_files(lp, rp, options).identical else DIFFERENT
            except OSError:
                status = ERROR
            entries.append(DirEntry(rel, status, False, lp, rp))
    return entries
