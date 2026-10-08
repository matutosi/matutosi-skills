#!/usr/bin/env python3
"""apply-proof-marks のスクリプトの自己テスト.

    python tests/test_apply_proof_marks.py

apply_fixes.py は標準ライブラリだけで試せる．
extract_marks.py は pypdf と Pillow が要る (無ければ飛ばす)．
画像の切り出しまで試すには poppler (pdftoppm) も要る (無ければその試験だけ飛ばす)．
テスト用の朱書き PDF は，pypdf で手書きの注釈 (Ink) を入れて作る．
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")

try:
    import pypdf
    from pypdf.generic import (ArrayObject, DictionaryObject, FloatObject,
                               NameObject)
    import PIL  # noqa: F401
    HAVE_PDF = True
except ImportError:
    HAVE_PDF = False
HAVE_POPPLER = shutil.which("pdftoppm") is not None


def run(script, args, cwd):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args,
                       cwd=cwd, capture_output=True)
    return (r.returncode, r.stdout.decode("utf-8", "replace").replace("\r\n", "\n"),
            r.stderr.decode("utf-8", "replace"))


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def make_marked_pdf(path, strokes_per_page):
    """A4 のページに，手書きの注釈 (Ink) を入れた PDF を作る．

    strokes_per_page: ページごとの筆跡の矩形 [x0, y0, x1, y1] のリスト．
    """
    w = pypdf.PdfWriter()
    for strokes in strokes_per_page:
        page = w.add_blank_page(595, 842)
        annots = ArrayObject()
        for x0, y0, x1, y1 in strokes:
            ink = DictionaryObject({
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Ink"),
                NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (x0, y0, x1, y1)]),
                NameObject("/InkList"): ArrayObject([ArrayObject(
                    [FloatObject(v) for v in (x0, y0, x1, y1)])]),
                NameObject("/C"): ArrayObject([FloatObject(1), FloatObject(0), FloatObject(0)]),
            })
            annots.append(w._add_object(ink))
        page[NameObject("/Annots")] = annots
    with open(path, "wb") as fh:
        w.write(fh)


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def p(self, *names):
        return os.path.join(self.d, *names)


class TestApplyFixes(Base):
    def setUp(self):
        super().setUp()
        write(self.p("chapter_05.md"), "よく使うグラフほど，正しく描きます．\nこの行はまるごと消す．\n最後の行です．\n")

    def fixes(self, rows):
        write(self.p("fixes.json"), json.dumps(rows, ensure_ascii=False))
        return "fixes.json"

    def test_check_only(self):
        f = self.fixes([{"file": "chapter_05.md", "old": "ほど，正しく", "new": "ほど正しく"}])
        code, out, err = run("apply_fixes.py", [f], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("ほど，正しく", read(self.p("chapter_05.md")))

    def test_apply_and_delete_line(self):
        f = self.fixes([{"file": "chapter_05.md", "old": "ほど，正しく", "new": "ほど正しく"},
                        {"file": "chapter_05.md", "old": "この行はまるごと消す．\n", "new": ""}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.p("chapter_05.md")), "よく使うグラフほど正しく描きます．\n最後の行です．\n")

    def test_mismatch_stops_everything(self):
        # 1件でも「ちょうど1回」でなければ，何も書かずに止まる (部分適用にしない)
        f = self.fixes([{"file": "chapter_05.md", "old": "ほど，正しく", "new": "ほど正しく"},
                        {"file": "chapter_05.md", "old": "す．", "new": "す。"}])  # 3回現れる
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 1)
        self.assertIn("ほど，正しく", read(self.p("chapter_05.md")))

    def test_missing_file(self):
        f = self.fixes([{"file": "nothing.md", "old": "a", "new": "b"}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 1)

    def test_post_uses_sibling_skills(self):
        # --post は同じ置き場にある sentence-per-line と markdown-table-pad を呼ぶ
        write(self.p("chapter_06.md"), "一文目です．二文目です．\n\n| a | 長い列 |\n|---|---|\n| 全角あ | b |\n")
        f = self.fixes([{"file": "chapter_06.md", "old": "一文目", "new": "1文目"}])
        code, out, err = run("apply_fixes.py", [f, "--apply", "--post"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.p("chapter_06.md")),
                         "1文目です．\n二文目です．\n\n| a      | 長い列 |\n| ------ | ------ |\n| 全角あ | b      |\n")


@unittest.skipUnless(HAVE_PDF, "pypdf と Pillow が要る")
class TestExtractMarks(Base):
    def setUp(self):
        super().setUp()
        # 1ページ目: 離れた2か所に朱書き．2ページ目: 朱書きなし．3ページ目: 1か所
        make_marked_pdf(self.p("proof.pdf"), [
            [(100, 700, 160, 715), (300, 300, 380, 320)],
            [],
            [(120, 500, 200, 512)],
        ])

    def names(self):
        rows = read(self.p("marks", "manifest.tsv")).splitlines()[1:]
        return [r.split("	")[5] for r in rows]

    def test_list(self):
        code, out, err = run("extract_marks.py", ["proof.pdf", "--list"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("[1, 3]", out)  # 朱書きのあるページ
        self.assertEqual(self.names(), ["p001_b1", "p001_b2", "p003_b1"])
        self.assertFalse([f for f in os.listdir(self.p("marks")) if f.endswith(".png")])

    def test_list_pages(self):
        code, out, err = run("extract_marks.py", ["proof.pdf", "--list", "--pages", "3"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.names(), ["p003_b1"])

    @unittest.skipUnless(HAVE_POPPLER, "poppler (pdftoppm) が要る")
    def test_crop_images(self):
        code, out, err = run("extract_marks.py", ["proof.pdf", "--pages", "1"], self.d)
        self.assertEqual(code, 0, err)
        pngs = sorted(f for f in os.listdir(self.p("marks")) if f.endswith(".png"))
        self.assertTrue(any(f.startswith("p001_b1") for f in pngs), pngs)
        self.assertTrue(any(f.startswith("p001_b2") for f in pngs), pngs)


if __name__ == "__main__":
    unittest.main()
