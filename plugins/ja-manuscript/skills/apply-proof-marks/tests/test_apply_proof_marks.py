#!/usr/bin/env python3
"""apply-proof-marks のスクリプトの自己テスト.

    python tests/test_apply_proof_marks.py

apply_fixes.py は標準ライブラリだけで試せる．
extract_marks.py は pypdf と Pillow が要る (無ければ飛ばす)．
画像の切り出しまで試すには pypdfium2 も要る (無ければその試験だけ飛ばす)．
テスト用の朱書き PDF は，pypdf で手書きの注釈 (Ink) を入れて作る．
"""

import json
import os
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
try:
    import pypdfium2  # noqa: F401
    HAVE_PDFIUM = True
except ImportError:
    HAVE_PDFIUM = False


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

    @unittest.skipUnless(HAVE_PDF and HAVE_PDFIUM, "pypdfium2 が要る")
    def test_crop_images(self):
        code, out, err = run("extract_marks.py", ["proof.pdf", "--pages", "1"], self.d)
        self.assertEqual(code, 0, err)
        pngs = sorted(f for f in os.listdir(self.p("marks")) if f.endswith(".png"))
        self.assertTrue(any(f.startswith("p001_b1") for f in pngs), pngs)
        self.assertTrue(any(f.startswith("p001_b2") for f in pngs), pngs)


try:
    import numpy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False


@unittest.skipUnless(HAVE_PDF and HAVE_NUMPY, "Pillow と numpy が要る")
class TestExtractMarksImage(Base):
    """画像 (スキャン・写真) から朱書きを色で探す．"""

    def setUp(self):
        super().setUp()
        from PIL import Image, ImageDraw
        # 黒い本文の行・赤ペンの線2本 (離れた位置)・薄い赤 (網掛け) の帯
        im = Image.new("RGB", (600, 800), "white")
        dr = ImageDraw.Draw(im)
        for y in range(80, 700, 40):
            dr.rectangle((60, y, 540, y + 12), fill=(20, 20, 20))
        dr.line((100, 126, 260, 126), fill=(220, 30, 40), width=4)
        dr.line((300, 606, 420, 600), fill=(220, 30, 40), width=4)
        dr.rectangle((60, 400, 540, 430), fill=(250, 225, 225))  # 彩度が低いので拾わない
        im.save(self.p("p001.png"), dpi=(72, 72))
        Image.new("RGB", (600, 800), "white").save(self.p("p002.jpg"))

    def rows(self):
        return [r.split("\t") for r in read(self.p("marks", "manifest.tsv")).splitlines()[1:]]

    def test_list(self):
        code, out, err = run("extract_marks.py", ["p001.png", "p002.jpg", "--list"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual([r[5] for r in self.rows()], ["p001_b1", "p001_b2"])
        self.assertIn("朱書き無し: p002", out)
        self.assertFalse([f for f in os.listdir(self.p("marks")) if f.endswith(".png")])

    def test_crop_ink_zoom(self):
        code, out, err = run("extract_marks.py",
                             ["p001.png", "--ink", "always", "--zoom"], self.d)
        self.assertEqual(code, 0, err)
        pngs = set(os.listdir(self.p("marks")))
        for f in ["p001_b1.png", "p001_b1_ink.png", "p001_b2.png", "p001_z1.png", "p001_z2.png"]:
            self.assertIn(f, pngs)
        self.assertNotIn("p001_b1_clean.png", pngs)  # 画像では作らない

    def test_other_color(self):
        # 緑を指定すると赤の線は拾わない
        code, out, err = run("extract_marks.py", ["p001.png", "--color", "green", "--list"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.rows(), [])

    @unittest.skipUnless(HAVE_PDFIUM, "pypdfium2 が要る")
    def test_scanned_pdf_falls_back_to_color(self):
        # 注釈が無く、ページが画像だけの PDF (紙のスキャン) は、自動で色で探す
        from PIL import Image
        Image.open(self.p("p001.png")).save(self.p("scan.pdf"), resolution=72)
        code, out, err = run("extract_marks.py", ["scan.pdf", "--list"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("スキャンとみなして", out)
        self.assertEqual([r[5] for r in self.rows()], ["p001_b1", "p001_b2"])

    def test_text_pdf_without_ink_warns(self):
        # 注釈の無い普通の PDF は、切り替えずに注意だけ出す
        make_marked_pdf(self.p("proof.pdf"), [[]])
        code, out, err = run("extract_marks.py", ["proof.pdf", "--list"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("Ink 注釈がありません", out)

    def test_sideways_photo_is_rotated(self):
        # 横倒しの写真 (行が縦に走る) は 90° 回して読む．EXIF の 72dpi は大きさから見積もり直す
        from PIL import Image
        Image.open(self.p("p001.png")).resize((1500, 2000)).rotate(-90, expand=True).save(
            self.p("side.jpg"), dpi=(72, 72), quality=95)
        code, out, err = run("extract_marks.py", ["side.jpg", "--list"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("90° 回して", out)
        self.assertEqual([r[5] for r in self.rows()], ["side_b1", "side_b2"])

    def test_rotate_zero_keeps_orientation(self):
        from PIL import Image
        Image.open(self.p("p001.png")).resize((1500, 2000)).rotate(-90, expand=True).save(
            self.p("side.jpg"), dpi=(72, 72), quality=95)
        code, out, err = run("extract_marks.py", ["side.jpg", "--list", "--rotate", "0"], self.d)
        self.assertEqual(code, 0, err)
        self.assertNotIn("回して", out)

    def test_mixed_input_is_rejected(self):
        make_marked_pdf(self.p("proof.pdf"), [[(100, 700, 160, 715)]])
        code, out, err = run("extract_marks.py", ["proof.pdf", "p001.png"], self.d)
        self.assertNotEqual(code, 0)


try:
    import cv2  # noqa: F401
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False


@unittest.skipUnless(HAVE_PDF and HAVE_NUMPY and HAVE_PDFIUM and HAVE_CV2,
                     "Pillow・numpy・pypdfium2・OpenCV が要る")
class TestExtractMarksRef(Base):
    """もとの原稿 (参照 PDF) との差で探す．"""

    def setUp(self):
        super().setUp()
        import random
        from PIL import Image, ImageDraw
        rnd = random.Random(1)
        # 参照: 長さのそろわない「字」のかたまりを並べた本文 (特徴点が取れるように)
        ref = Image.new("RGB", (1000, 1400), "white")
        dr = ImageDraw.Draw(ref)
        for y in range(120, 1250, 45):
            x = 100
            while x < 880:
                w = rnd.randint(8, 30)
                dr.rectangle((x, y + rnd.randint(0, 6), x + w, y + 22 - rnd.randint(0, 6)),
                             fill=(20, 20, 20))
                x += w + rnd.randint(6, 14)
        dr.rectangle((600, 700, 800, 800), fill=(60, 180, 120))   # 図の緑 (朱書きではない)
        ref.save(self.p("ref.pdf"), resolution=120)
        # スキャン: 少しずらして赤と青の書き込みを足す
        scan = Image.new("RGB", (1000, 1400), "white")
        scan.paste(ref.rotate(0.4, fillcolor="white").crop((0, 0, 992, 1394)), (8, 6))
        dr = ImageDraw.Draw(scan)
        dr.line((150, 300, 400, 300), fill=(220, 30, 40), width=4)
        dr.line((200, 1000, 450, 990), fill=(30, 60, 220), width=4)
        scan.save(self.p("scan.png"), dpi=(120, 120))

    def rows(self):
        return [r.split("\t") for r in read(self.p("marks", "manifest.tsv")).splitlines()[1:]]

    def test_ref_finds_any_color_and_makes_clean(self):
        code, out, err = run("extract_marks.py", ["scan.png", "--ref", "ref.pdf"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("参照 PDF との差で探した: 1 / 1", out)
        rows = self.rows()
        self.assertEqual(len(rows), 2, rows)                 # 赤と青．図の緑は拾わない
        self.assertTrue(int(rows[0][2]) < 300 < int(rows[0][3]))
        self.assertTrue(int(rows[1][2]) < 995 < int(rows[1][3]))
        self.assertTrue(os.path.exists(self.p("marks", "scan_b1_clean.png")))

    def test_color_finds_figure_green(self):
        # 比べるため: 色で緑を探すと図を拾う
        code, out, err = run("extract_marks.py", ["scan.png", "--color", "green", "--list"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.rows()), 1)


if __name__ == "__main__":
    unittest.main()
