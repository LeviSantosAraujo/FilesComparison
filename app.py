"""Files Comparison — PySide6 GUI.

Run: python3 app.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget)

import diff_engine as de

LOG_PATH = Path(__file__).resolve().parent / "files_comparison.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"),
              logging.StreamHandler()])
log = logging.getLogger("files_comparison")
log.info("=== app module loaded, log file: %s ===", LOG_PATH)

# --- visual theme ---------------------------------------------------------
BG = "#eef0f4"
CARD = "#ffffff"
BORDER = "#d9dde3"
TEXT = "#1f2328"
MUTED = "#65707e"
ACCENT = "#2f6df6"
ACCENT_DK = "#1f56d8"

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
    de.IDENTICAL: None,
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

ICON_PATH = Path(__file__).resolve().parent / "icon.png"

QSS = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 13px;
}}
QLabel#brand {{ font-size: 18px; font-weight: bold; }}
QLabel#tagline {{ color: {MUTED}; font-size: 12px; }}
QLabel#status {{ color: {MUTED}; font-size: 11px; padding: 2px; }}
QLabel#panelTitle {{ color: {MUTED}; font-size: 10px; font-weight: bold; }}
#card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLineEdit {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #b9d2fb;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{ background: #f0f2f6; }}
QPushButton:pressed {{ background: #e4e8ee; }}
QPushButton:disabled {{ color: {MUTED}; }}
QPushButton#accent {{
    background: {ACCENT};
    color: white;
    border: none;
    font-weight: bold;
}}
QPushButton#accent:hover {{ background: {ACCENT_DK}; }}
QPushButton#accent:pressed {{ background: {ACCENT_DK}; }}
QPushButton#accent:disabled {{ background: #9db8f5; }}
QCheckBox {{ spacing: 6px; }}
QTableWidget, QTreeWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: #dbe7fd;
    selection-color: {TEXT};
}}
QTableWidget::item {{ padding: 0px 6px; }}
QTreeWidget::item {{ padding: 4px 2px; }}
QHeaderView::section {{
    background: {GUTTER_BG};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    font-weight: bold;
}}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: #c4cad3; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #a8b0bc; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: #c4cad3; border-radius: 5px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: #a8b0bc; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""


def mono_font() -> QFont:
    f = QFont("Menlo")
    f.setStyleHint(QFont.StyleHint.TypeWriter)
    f.setPointSize(12)
    return f


class CompareThread(QThread):
    """Runs the engine off the UI thread."""
    done = Signal(str, object)  # kind ("file"|"dirs"|"error"), result

    def __init__(self, left: Path, right: Path, options: de.DiffOptions):
        super().__init__()
        self.left, self.right, self.options = left, right, options

    def run(self):
        try:
            if self.left.is_dir():
                self.done.emit("dirs", de.compare_dirs(self.left, self.right,
                                                       self.options))
            else:
                self.done.emit("file", de.compare_files(self.left, self.right,
                                                        self.options))
        except Exception:
            log.exception("compare worker failed")
            self.done.emit("error", None)


class DiffTable(QTableWidget):
    """Side-by-side diff: [# | left text | # | right text] in one table."""

    def __init__(self):
        super().__init__()
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["", "Left", "", "Right"])
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(22)
        h = self.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setShowGrid(False)
        self.setFont(mono_font())

    def show_result(self, result: de.FileResult):
        self.setRowCount(0)
        self.setRowCount(len(result.rows))
        for i, row in enumerate(result.rows):
            for num_col, txt_col, cell in ((0, 1, row.left), (2, 3, row.right)):
                num = QTableWidgetItem("" if cell is None else str(cell.lineno))
                num.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                     | Qt.AlignmentFlag.AlignVCenter)
                num.setForeground(QColor(GUTTER_FG))
                num.setBackground(QColor(GUTTER_BG))
                txt = QTableWidgetItem("" if cell is None else cell.text)
                bg = PAD_BG if cell is None else ROW_COLORS.get(cell.kind)
                if bg:
                    num.setBackground(QColor(bg))
                    txt.setBackground(QColor(bg))
                else:
                    txt.setBackground(QColor(CARD))
                self.setItem(i, num_col, num)
                self.setItem(i, txt_col, txt)
        self.scrollToTop()


class DiffWindow(QMainWindow):
    """Standalone window showing one file comparison."""

    def __init__(self, title: str):
        super().__init__()
        self.setWindowTitle(title)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(12, 12, 12, 8)
        self.table = DiffTable()
        lay.addWidget(self.table, stretch=1)
        self.status = QLabel()
        self.status.setObjectName("status")
        lay.addWidget(self.status)
        self.setCentralWidget(central)


class FolderTree(QTreeWidget):
    """Treeview of compare_dirs results; double-click a file to open a diff."""

    file_activated = Signal(object)  # de.DirEntry

    def __init__(self):
        super().__init__()
        self.setColumnCount(3)
        self.setHeaderLabels(["Name", "Status", "Type"])
        self.setColumnWidth(0, 560)
        self.setColumnWidth(1, 140)
        self.setIndentation(16)
        self.itemDoubleClicked.connect(self._emit_entry)

    def show_entries(self, entries: list[de.DirEntry]):
        self.clear()
        nodes: dict[str, QTreeWidgetItem] = {}
        counts: dict[str, int] = {}

        # entries are sorted by relpath, so parents always precede children
        for entry in entries:
            counts[entry.status] = counts.get(entry.status, 0) + 1
            parts = entry.relpath.split("/")
            name = (f"{parts[-1]} ↔ {entry.pair.rsplit('/', 1)[-1]}"
                    if entry.pair else parts[-1])
            item = QTreeWidgetItem([name,
                                    STATUS_LABELS.get(entry.status, entry.status),
                                    "Folder" if entry.is_dir else "File"])
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            color = STATUS_COLORS.get(entry.status)
            if color:
                for c in range(3):
                    item.setBackground(c, QColor(color))
            parent_path = entry.relpath.rsplit("/", 1)[0] if "/" in entry.relpath else ""
            if parent_path and parent_path in nodes:
                nodes[parent_path].addChild(item)
            else:
                self.addTopLevelItem(item)
            nodes[entry.relpath] = item
        self.expandAll()

        parts_ = [f"{counts[k]} {STATUS_LABELS.get(k, k).lower()}"
                  for k in (de.DIFFERENT, de.LEFT_ONLY, de.RIGHT_ONLY,
                            de.BINARY, de.TYPE_MISMATCH, de.ERROR)
                  if counts.get(k)]
        return f"{len(entries)} items — " + (
            ", ".join(parts_) if parts_ else "all identical")

    def _emit_entry(self, item: QTreeWidgetItem, _col):
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        log.info("tree double-click: %r", entry)
        if (entry and not entry.is_dir
                and (entry.left_path or entry.right_path)):
            self.file_activated.emit(entry)


class SidePanel(QWidget):
    """Half-width card: title, path field, File…/Folder… buttons."""

    def __init__(self, title: str, edit: QLineEdit,
                 on_file, on_folder):
        super().__init__()
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.edit = edit
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("panelTitle")
        lay.addWidget(title_lbl)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(edit, stretch=1)
        file_btn = QPushButton("File…")
        file_btn.clicked.connect(on_file)
        folder_btn = QPushButton("Folder…")
        folder_btn.clicked.connect(on_folder)
        row.addWidget(file_btn)
        row.addWidget(folder_btn)
        lay.addLayout(row)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Files Comparison")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self._worker: CompareThread | None = None
        self._diff_windows: list[DiffWindow] = []

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(8)

        brand_row = QHBoxLayout()
        brand = QLabel("Files Comparison")
        brand.setObjectName("brand")
        tagline = QLabel("side-by-side diff for files & folders")
        tagline.setObjectName("tagline")
        brand_row.addWidget(brand)
        brand_row.addWidget(tagline)
        brand_row.addStretch()
        root.addLayout(brand_row)

        self.left_edit = QLineEdit()
        self.right_edit = QLineEdit()
        self.left_edit.setPlaceholderText("Path to left file or folder")
        self.right_edit.setPlaceholderText("Path to right file or folder")
        panels = QHBoxLayout()
        panels.setSpacing(8)
        panels.addWidget(SidePanel("LEFT", self.left_edit,
                                   lambda: self._pick(self.left_edit, False),
                                   lambda: self._pick(self.left_edit, True)))
        panels.addWidget(SidePanel("RIGHT", self.right_edit,
                                   lambda: self._pick(self.right_edit, False),
                                   lambda: self._pick(self.right_edit, True)))
        root.addLayout(panels)

        opts = QHBoxLayout()
        opts.setSpacing(14)
        self.opt_ws = QCheckBox("Ignore whitespace")
        self.opt_case = QCheckBox("Ignore case")
        self.opt_blank = QCheckBox("Ignore blank lines")
        self.opt_recursive = QCheckBox("Include subfolders")
        self.opt_recursive.setChecked(True)
        for cb in (self.opt_ws, self.opt_case, self.opt_blank, self.opt_recursive):
            opts.addWidget(cb)
        opts.addStretch()
        self.compare_btn = QPushButton("Compare")
        self.compare_btn.setObjectName("accent")
        self.compare_btn.clicked.connect(self.compare)
        opts.addWidget(self.compare_btn)
        root.addLayout(opts)

        self.stack = QStackedWidget()
        hint = QLabel("Pick a file or folder on each side above — "
                      "the comparison runs automatically.")
        hint.setObjectName("tagline")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(hint)                                   # 0
        self.diff_table = DiffTable()
        self.stack.addWidget(self.diff_table)                        # 1
        folder_page = QWidget()
        fp_lay = QVBoxLayout(folder_page)
        fp_lay.setContentsMargins(0, 0, 0, 0)
        fp_lay.setSpacing(4)
        self.folder_tree = FolderTree()
        self.folder_tree.file_activated.connect(self._open_file_diff)
        self.folder_status = QLabel()
        self.folder_status.setObjectName("status")
        fp_lay.addWidget(self.folder_tree, stretch=1)
        fp_lay.addWidget(self.folder_status)
        self.stack.addWidget(folder_page)                            # 2
        self.binary_lbl = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.binary_lbl.setObjectName("tagline")
        self.stack.addWidget(self.binary_lbl)                        # 3
        root.addWidget(self.stack, stretch=1)

        self.status = QLabel()
        self.status.setObjectName("status")
        root.addWidget(self.status)

        self.setCentralWidget(central)
        log.info("app init: PySide6 %s", __import__("PySide6").__version__)

    # -- actions -----------------------------------------------------------

    def _options(self) -> de.DiffOptions:
        return de.DiffOptions(
            ignore_whitespace=self.opt_ws.isChecked(),
            ignore_case=self.opt_case.isChecked(),
            ignore_blank_lines=self.opt_blank.isChecked(),
            recursive=self.opt_recursive.isChecked())

    def _pick(self, edit: QLineEdit, is_dir: bool):
        side = "left" if edit is self.left_edit else "right"
        log.info("browse clicked: %s %s", side, "folder" if is_dir else "file")
        if is_dir:
            path = QFileDialog.getExistingDirectory(self, "Pick folder")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Pick file")
        log.info("picker returned: %r", path)
        if path:
            edit.setText(path)
            self._compare_if_ready()

    def _compare_if_ready(self):
        if self.left_edit.text() and self.right_edit.text():
            self.compare()

    def compare(self):
        left = Path(self.left_edit.text().strip())
        right = Path(self.right_edit.text().strip())
        log.info("compare: left=%s right=%s", left, right)
        if not left.exists() or not right.exists():
            log.warning("compare aborted: left.exists()=%s right.exists()=%s",
                        left.exists(), right.exists())
            QMessageBox.critical(self, "Files Comparison",
                                 "Both paths must exist.")
            return
        if left.is_file() != right.is_file():
            QMessageBox.critical(self, "Files Comparison",
                                 "Pick two files or two folders — not one of each.")
            return

        self.compare_btn.setEnabled(False)
        self.compare_btn.setText("Comparing…")
        self.status.setText("")
        self._worker = CompareThread(left, right, self._options())
        self._worker.done.connect(self._on_result)
        self._worker.start()

    def _on_result(self, kind: str, result):
        self.compare_btn.setEnabled(True)
        self.compare_btn.setText("Compare")
        log.info("compare finished: kind=%s", kind)

        if kind == "error":
            QMessageBox.critical(self, "Files Comparison",
                                 "Comparison failed — see files_comparison.log")
            return
        if kind == "dirs":
            summary = self.folder_tree.show_entries(result)
            self.folder_status.setText(summary)
            self.status.setText("Double-click a file to view its diff")
            self.stack.setCurrentIndex(2)
            return

        if result.error:
            QMessageBox.critical(self, "Files Comparison", result.error)
            return
        if result.is_binary:
            msg = ("Binary files are identical" if result.identical
                   else "Binary files differ")
            self.status.setText(msg)
            self.binary_lbl.setText(msg)
            self.stack.setCurrentIndex(3)
            return

        prefix = (result.note + " — ") if result.note else ""
        if result.identical:
            self.status.setText(prefix + "Files are identical")
        else:
            s = result.summary
            parts = [f"{s.get(k, 0)} {k}" for k in
                     (de.CHANGED, de.ADDED, de.REMOVED) if s.get(k)]
            if s.get(de.BLANK):
                parts.append(f"{s[de.BLANK]} blank (ignored)")
            self.status.setText(prefix + "Differences: " + ", ".join(parts))
        self.diff_table.show_result(result)
        self.stack.setCurrentIndex(1)

    def _single_side_result(self, entry: de.DirEntry) -> de.FileResult:
        """Pseudo FileResult for a file that exists on only one side."""
        p = entry.left_path or entry.right_path
        result = de.FileResult(p, p)
        doc = de.extract_document_lines(p)
        if doc is not None:
            lines, _ = doc
            result.note = "only in " + ("left" if entry.left_path else "right")
        elif de.is_binary(p):
            result.is_binary = True
            return result
        else:
            try:
                lines = de.read_lines(p)
            except OSError as e:
                result.error = str(e)
                return result
            result.note = "only in " + ("left" if entry.left_path else "right")
        result.rows = [
            de.DiffRow(de.SideLine(i + 1, l, de.EQUAL), None)
            if entry.left_path else
            de.DiffRow(None, de.SideLine(i + 1, l, de.EQUAL))
            for i, l in enumerate(lines)]
        return result

    def _open_file_diff(self, entry: de.DirEntry):
        side = entry.left_path or entry.right_path
        other = entry.right_path if entry.left_path else entry.left_path
        title = side.name if other is None else f"{entry.left_path.name} ↔ {entry.right_path.name}"
        win = DiffWindow(title)
        win.resize(1200, 800)
        win.show()
        self._diff_windows.append(win)  # keep a reference alive

        if entry.left_path is None or entry.right_path is None:
            result = self._single_side_result(entry)
            if result.is_binary:
                win.status.setText("Binary file — exists on one side only")
            elif result.error:
                win.status.setText(result.error)
            else:
                win.table.show_result(result)
                win.status.setText(
                    result.note + " — " + f"{len(result.rows)} lines")
            return

        thread = CompareThread(entry.left_path, entry.right_path, self._options())
        thread.setParent(win)
        thread.finished.connect(thread.deleteLater)

        def on_done(kind, result, w=win):
            if kind == "file" and not result.error and not result.is_binary:
                w.table.show_result(result)
                s = result.summary
                parts = [f"{s.get(k, 0)} {k}" for k in
                         (de.CHANGED, de.ADDED, de.REMOVED) if s.get(k)]
                w.status.setText(
                    "Files are identical" if result.identical
                    else "Differences: " + ", ".join(parts))
            elif kind == "file" and result.is_binary:
                w.status.setText("Binary files are identical" if result.identical
                                 else "Binary files differ")
            else:
                w.status.setText(getattr(result, "error", None) or "Error")

        thread.done.connect(on_done)
        thread.start()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Files Comparison")
    app.setStyleSheet(QSS)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
