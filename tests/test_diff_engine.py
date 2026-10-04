import tempfile
import unittest
import zipfile
from pathlib import Path

import diff_engine as de

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(path: Path, paragraphs: list[str]):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    doc = (f'<?xml version="1.0"?>'
           f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "")
        z.writestr("word/document.xml", doc)


def kinds(rows):
    """Return list of (left_kind, right_kind) per row; None for pad cells."""
    return [(r.left.kind if r.left else None,
             r.right.kind if r.right else None) for r in rows]


class TestDiffLines(unittest.TestCase):
    def test_identical(self):
        rows = de.diff_lines(["a", "b", "c"], ["a", "b", "c"])
        self.assertTrue(all(r.left and r.left.kind == de.EQUAL for r in rows))
        self.assertEqual(len(rows), 3)

    def test_changed(self):
        # similar lines pair as changed
        rows = de.diff_lines(["a", "the quick fox", "c"], ["a", "the quick foxes", "c"])
        self.assertEqual(kinds(rows),
                         [(de.EQUAL, de.EQUAL),
                          (de.CHANGED, de.CHANGED),
                          (de.EQUAL, de.EQUAL)])
        self.assertEqual(rows[1].left.text, "the quick fox")
        self.assertEqual(rows[1].right.text, "the quick foxes")

    def test_dissimilar_single_line(self):
        # genuinely unrelated lines show as remove+add, not a forced pair
        rows = de.diff_lines(["a", "b", "c"], ["a", "x", "c"])
        self.assertEqual(kinds(rows),
                         [(de.EQUAL, de.EQUAL),
                          (de.REMOVED, None),
                          (None, de.ADDED),
                          (de.EQUAL, de.EQUAL)])

    def test_added(self):
        rows = de.diff_lines(["a", "c"], ["a", "b", "c"])
        self.assertIn((None, de.ADDED), kinds(rows))
        self.assertIsNone(rows[1].left)
        self.assertEqual(rows[1].right.lineno, 2)

    def test_removed(self):
        rows = de.diff_lines(["a", "b", "c"], ["a", "c"])
        self.assertIn((de.REMOVED, None), kinds(rows))

    def test_replace_pairing(self):
        # dissimilar lines don't get forced into "changed" pairs
        rows = de.diff_lines(["p", "q"], ["x", "y", "z"])
        self.assertEqual(kinds(rows),
                         [(de.REMOVED, None),
                          (de.REMOVED, None),
                          (None, de.ADDED),
                          (None, de.ADDED),
                          (None, de.ADDED)])

    def test_fuzzy_pairing(self):
        # similar lines pair as changed even when not index-aligned
        rows = de.diff_lines(
            ["unique left", "the quick brown fox jumps over"],
            ["zzzz", "extra line here", "the quick brown fox leaps over stuff"])
        pair = [r for r in rows if r.left and r.left.kind == de.CHANGED]
        self.assertEqual(len(pair), 1)
        self.assertEqual(pair[0].left.text, "the quick brown fox jumps over")
        self.assertEqual(pair[0].right.text, "the quick brown fox leaps over stuff")
        self.assertIn((de.REMOVED, None), kinds(rows))
        self.assertEqual(kinds(rows).count((None, de.ADDED)), 2)

    def test_ignore_whitespace(self):
        opts = de.DiffOptions(ignore_whitespace=True)
        rows = de.diff_lines(["  hello   world"], ["hello world"], opts)
        self.assertEqual(kinds(rows), [(de.EQUAL, de.EQUAL)])
        self.assertEqual(rows[0].left.text, "  hello   world")  # original kept

    def test_ignore_case(self):
        opts = de.DiffOptions(ignore_case=True)
        rows = de.diff_lines(["HELLO"], ["hello"], opts)
        self.assertEqual(kinds(rows), [(de.EQUAL, de.EQUAL)])

    def test_ignore_blank_lines(self):
        opts = de.DiffOptions(ignore_blank_lines=True)
        rows = de.diff_lines(["a", "", "b"], ["a", "b"], opts)
        self.assertEqual(kinds(rows)[1], (de.BLANK, None))

    def test_without_ignore_blank_lines(self):
        rows = de.diff_lines(["a", "", "b"], ["a", "b"])
        self.assertEqual(kinds(rows)[1], (de.REMOVED, None))

    def test_empty_files(self):
        self.assertEqual(de.diff_lines([], []), [])


class TestCompareFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, content, binary=False):
        p = self.dir / name
        if binary:
            p.write_bytes(content)
        else:
            p.write_text(content)
        return p

    def test_identical_files(self):
        a = self._write("a.txt", "same\n")
        b = self._write("b.txt", "same\n")
        r = de.compare_files(a, b)
        self.assertTrue(r.identical)
        self.assertFalse(r.is_binary)
        self.assertIsNone(r.error)

    def test_different_files_summary(self):
        a = self._write("a.txt", "one\ntwo\nthree\n")
        b = self._write("b.txt", "one\nTWO\nthree\nfour\n")
        r = de.compare_files(a, b)
        self.assertFalse(r.identical)
        self.assertEqual(r.summary[de.CHANGED], 1)
        self.assertEqual(r.summary[de.ADDED], 1)

    def test_binary_detection(self):
        a = self._write("a.bin", b"\x00\x01\x02", binary=True)
        b = self._write("b.bin", b"\x00\x01\x03", binary=True)
        r = de.compare_files(a, b)
        self.assertTrue(r.is_binary)
        self.assertFalse(r.identical)

    def test_binary_identical(self):
        a = self._write("a.bin", b"\x00\xff", binary=True)
        b = self._write("b.bin", b"\x00\xff", binary=True)
        r = de.compare_files(a, b)
        self.assertTrue(r.is_binary)
        self.assertTrue(r.identical)

    def test_docx_text_diff(self):
        a = self.dir / "a.docx"
        b = self.dir / "b.docx"
        make_docx(a, ["Intro", "Old conclusion"])
        make_docx(b, ["Intro", "New conclusion", "Appendix"])
        r = de.compare_files(a, b)
        self.assertFalse(r.is_binary)
        self.assertFalse(r.identical)
        self.assertEqual(r.summary.get(de.CHANGED), 1)
        self.assertEqual(r.summary.get(de.ADDED), 1)
        self.assertIn("docx", r.note)
        # original paragraph text is preserved in the rows
        changed = [row for row in r.rows if row.left and row.left.kind == de.CHANGED]
        self.assertEqual(changed[0].left.text, "Old conclusion")

    def test_docx_identical(self):
        a = self.dir / "a.docx"
        b = self.dir / "b.docx"
        make_docx(a, ["Same", "Content"])
        make_docx(b, ["Same", "Content"])
        self.assertTrue(de.compare_files(a, b).identical)

    def test_extract_document_lines(self):
        a = self.dir / "a.docx"
        make_docx(a, ["Hello", "World"])
        lines, note = de.extract_document_lines(a)
        self.assertEqual(lines, ["Hello", "World"])
        self.assertIsNone(de.extract_document_lines(self._write("t.txt", "x")))

    def test_ignore_options_make_identical(self):
        a = self._write("a.txt", "Hello   World\n")
        b = self._write("b.txt", "hello world\n")
        self.assertFalse(de.compare_files(a, b).identical)
        opts = de.DiffOptions(ignore_whitespace=True, ignore_case=True)
        self.assertTrue(de.compare_files(a, b, opts).identical)


class TestCompareDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.left = Path(self.tmp.name) / "left"
        self.right = Path(self.tmp.name) / "right"
        (self.left / "sub").mkdir(parents=True)
        (self.right / "sub").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _statuses(self, entries):
        return {e.relpath: e.status for e in entries}

    def test_folder_compare(self):
        (self.left / "same.txt").write_text("x\n")
        (self.right / "same.txt").write_text("x\n")
        (self.left / "diff.txt").write_text("a\n")
        (self.right / "diff.txt").write_text("b\n")
        (self.left / "gone.txt").write_text("only left\n")
        (self.right / "new.txt").write_text("only right\n")
        (self.left / "sub" / "nested.txt").write_text("deep\n")

        statuses = self._statuses(de.compare_dirs(self.left, self.right))
        self.assertEqual(statuses["same.txt"], de.IDENTICAL)
        self.assertEqual(statuses["diff.txt"], de.DIFFERENT)
        self.assertEqual(statuses["gone.txt"], de.LEFT_ONLY)
        self.assertEqual(statuses["new.txt"], de.RIGHT_ONLY)
        self.assertEqual(statuses["sub"], de.IDENTICAL)
        self.assertEqual(statuses["sub/nested.txt"], de.LEFT_ONLY)

    def test_non_recursive(self):
        (self.left / "sub" / "nested.txt").write_text("deep\n")
        opts = de.DiffOptions(recursive=False)
        statuses = self._statuses(de.compare_dirs(self.left, self.right, opts))
        self.assertNotIn("sub/nested.txt", statuses)
        self.assertEqual(statuses["sub"], de.IDENTICAL)

    def test_type_mismatch(self):
        (self.right / "sub").rmdir()
        (self.right / "sub").write_text("file not dir\n")
        statuses = self._statuses(de.compare_dirs(self.left, self.right))
        self.assertEqual(statuses["sub"], de.TYPE_MISMATCH)

    def test_binary_files(self):
        (self.left / "a.bin").write_bytes(b"\x00\x01")
        (self.right / "a.bin").write_bytes(b"\x00\x02")
        statuses = self._statuses(de.compare_dirs(self.left, self.right))
        self.assertEqual(statuses["a.bin"], de.BINARY)


if __name__ == "__main__":
    unittest.main()
