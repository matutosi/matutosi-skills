#!/usr/bin/env python3
"""graphical-abstract のスクリプトの自己テスト.

    python tests/test_graphical_abstract.py

compose.py の描画と点検は matplotlib，pdf_pages.py は pymupdf が要る．無ければその部分を飛ばす．
"""

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import compose  # noqa: E402
import make_prompts  # noqa: E402

try:
    import matplotlib  # noqa: F401
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    import pymupdf  # noqa: F401
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

EXAMPLES = os.path.join(HERE, "..", "..", "..", "examples")

BASE = {
    "canvas": {"width_mm": 120, "height_mm": 60, "dpi": 100, "min_font_pt": 7},
    "elements": [
        {"type": "panel", "id": "p1", "x": 5, "y": 5, "w": 50, "h": 50, "title": "A"},
        {"type": "text", "id": "t1", "parent": "p1", "x": 10, "y": 20, "text": "hello", "size": 10},
    ],
}


def layout(extra=None, **canvas):
    d = copy.deepcopy(BASE)
    d["canvas"].update(canvas)
    if extra:
        d["elements"].extend(extra)
    return compose.normalize(d)


class TestNormalize(unittest.TestCase):
    def test_defaults(self):
        lay = layout()
        self.assertEqual(lay["canvas"]["background"], "#ffffff")
        self.assertEqual(lay["elements"][0]["id"], "p1")

    def test_auto_id(self):
        d = copy.deepcopy(BASE)
        d["elements"].append({"type": "arrow", "from": [1, 1], "to": [5, 5]})
        lay = compose.normalize(d)
        self.assertEqual(lay["elements"][-1]["id"], "arrow3")

    def test_errors(self):
        bad = [
            {"elements": []},
            {"elements": [{"type": "circle"}]},
            {"elements": [{"type": "panel", "x": 0, "y": 0, "w": 0, "h": 5}]},
            {"elements": [{"type": "text", "x": 0, "y": 0}]},
            {"elements": [{"type": "arrow", "from": [0], "to": [1, 1]}]},
            {"elements": [{"type": "chart", "kind": "pie", "x": 0, "y": 0, "w": 5, "h": 5, "data": {"y": [1]}}]},
            {"elements": [{"type": "text", "x": 0, "y": 0, "text": "a", "parent": "nope"}]},
            {"elements": [{"type": "text", "id": "a", "x": 0, "y": 0, "text": "a"},
                          {"type": "text", "id": "a", "x": 0, "y": 0, "text": "b"}]},
            {"canvas": {"width_mm": -1}, "elements": [{"type": "text", "x": 0, "y": 0, "text": "a"}]},
        ]
        for d in bad:
            with self.assertRaises(compose.LayoutError, msg=json.dumps(d, ensure_ascii=False)):
                compose.normalize(d)

    def test_relative_src(self):
        d = copy.deepcopy(BASE)
        d["elements"].append({"type": "image", "id": "i", "x": 0, "y": 0, "w": 5, "h": 5, "src": "illust/a.png"})
        lay = compose.normalize(d, base=tempfile.gettempdir())
        el = lay["elements"][-1]
        self.assertEqual(el["src_given"], "illust/a.png")
        self.assertTrue(os.path.isabs(el["src"]))


class TestGeometry(unittest.TestCase):
    def test_overlap(self):
        self.assertEqual(compose._overlap((0, 0, 10, 10), (20, 0, 5, 5)), 0)
        self.assertAlmostEqual(compose._overlap((0, 0, 10, 10), (8, 2, 10, 3)), 2)

    def test_outside(self):
        self.assertEqual(compose._outside((1, 1, 5, 5), (0, 0, 10, 10)), 0)
        self.assertAlmostEqual(compose._outside((8, 1, 5, 5), (0, 0, 10, 10)), 3)

    def test_wrap_japanese(self):
        # 1字 = 1 mm として，幅 5 mm で折り返す
        s = compose.wrap_text("あいうえおかきくけこ", 5, 10, len)
        self.assertEqual(s.split("\n"), ["あいうえお", "かきくけこ"])

    def test_wrap_keeps_words_and_punctuation(self):
        s = compose.wrap_text("あいうえ，おか", 4, 10, len)
        self.assertTrue(s.split("\n")[0].endswith("，"))   # 読点は行頭に送らない
        s = compose.wrap_text("abc defgh", 5, 10, len)
        self.assertIn("defgh", s.split("\n"))               # 欧文の語は切らない


class TestPrompts(unittest.TestCase):
    def test_ratio(self):
        self.assertEqual(make_prompts.nearest_ratio(160, 90), "16:9")
        self.assertEqual(make_prompts.nearest_ratio(50, 50), "1:1")
        self.assertEqual(make_prompts.nearest_ratio(30, 40), "3:4")

    def test_prompt_has_constraints(self):
        pos, neg = make_prompts.build_prompt("a frog on a leaf.", {"palette": ["#112233"]})
        self.assertIn("a frog on a leaf", pos)
        self.assertIn("no text", pos)
        self.assertIn("#112233", pos)
        self.assertIn("letters", neg)

    def test_collect_and_render(self):
        lay = layout([
            {"type": "image", "id": "i1", "x": 60, "y": 5, "w": 40, "h": 30, "src": "illust/i1.png", "prompt": "a tree"},
            {"type": "image", "id": "i2", "x": 60, "y": 40, "w": 10, "h": 10, "src": "photo.jpg"},
        ])
        slots = make_prompts.collect(lay)
        self.assertEqual([s["id"] for s in slots], ["i1", "i2"])
        self.assertFalse(slots[0]["skip"])
        self.assertTrue(slots[1]["skip"])
        self.assertEqual(slots[0]["src"], "illust/i1.png")
        md = make_prompts.render_markdown(slots, "t")
        self.assertIn("--ar 4:3", md)
        self.assertIn("illust/i1.png", md)

    def test_examples_parse(self):
        for name in ("paper", "book"):
            lay = compose.load_layout(os.path.join(EXAMPLES, name, "layout.json"))
            slots = make_prompts.collect(lay)
            self.assertTrue(any(not s["skip"] for s in slots), name)


@unittest.skipUnless(HAS_MPL, "matplotlib が無い")
class TestCompose(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kinds(self, lay):
        return [i["kind"] for i in compose.run(lay, check_only=True)["issues"]]

    def test_clean(self):
        self.assertEqual(self.kinds(layout()), [])

    def test_writes_files(self):
        out = os.path.join(self.tmp, "ga")
        r = compose.run(layout(), out, ["png", "pdf", "svg"])
        for ext in ("png", "pdf", "svg"):
            self.assertTrue(os.path.getsize(out + "." + ext) > 0, ext)
        self.assertEqual(r["size_px"], [472, 236])

    def test_overflow(self):
        lay = layout([{"type": "text", "id": "long", "parent": "p1", "x": 10, "y": 30,
                       "text": "a very long line that cannot fit", "size": 12}])
        self.assertIn("text_overflow", self.kinds(lay))

    def test_overflow_canvas(self):
        lay = layout([{"type": "text", "id": "edge", "x": 115, "y": 2, "text": "outside", "size": 12}])
        self.assertIn("text_overflow", self.kinds(lay))

    def test_overlap(self):
        lay = layout([{"type": "text", "id": "t2", "parent": "p1", "x": 11, "y": 21, "text": "world", "size": 10}])
        self.assertIn("text_overlap", self.kinds(lay))

    def test_small_font(self):
        lay = layout([{"type": "text", "id": "tiny", "parent": "p1", "x": 10, "y": 40, "text": "tiny", "size": 5}])
        self.assertIn("font_too_small", self.kinds(lay))

    def test_missing_image_and_text_on_image(self):
        lay = layout([
            {"type": "image", "id": "img", "x": 60, "y": 5, "w": 50, "h": 40, "src": os.path.join(self.tmp, "none.png")},
            {"type": "text", "id": "cap", "x": 70, "y": 20, "text": "on top", "size": 10},
        ])
        k = self.kinds(lay)
        self.assertIn("image_missing", k)
        self.assertIn("text_on_image", k)
        lay["elements"][-1]["over"] = True
        self.assertNotIn("text_on_image", self.kinds(lay))

    def test_real_image(self):
        import numpy as np
        import matplotlib.pyplot as plt
        path = os.path.join(self.tmp, "a.png")
        plt.imsave(path, np.zeros((20, 40, 3)) + 0.5)
        lay = layout([{"type": "image", "id": "img", "x": 60, "y": 5, "w": 50, "h": 40, "src": path}])
        self.assertNotIn("image_missing", self.kinds(lay))

    def test_knockout_white(self):
        import numpy as np
        img = np.array([[[250, 250, 250], [10, 200, 10]]], dtype=np.uint8)
        out = compose.knockout_white(img)
        self.assertEqual(out.shape, (1, 2, 4))
        self.assertEqual(out[0, 0, 3], 0)      # 白に近い画素は透明
        self.assertEqual(out[0, 1, 3], 255)    # 色のある画素は残る
        out = compose.knockout_white(img.astype(float) / 255, threshold=251)
        self.assertEqual(out[0, 0, 3], 255)

    def test_knockout_border_color(self):
        import numpy as np
        img = np.full((20, 20, 3), 238, dtype=np.uint8)   # うすい灰色の背景
        img[8:12, 8:12] = [30, 60, 90]
        out = compose.knockout_white(img)
        self.assertEqual(out[0, 0, 3], 0)
        self.assertEqual(out[10, 10, 3], 255)

    def test_trim_white(self):
        import numpy as np
        img = np.full((500, 1000, 4), 255, dtype=np.uint8)
        img[200:300, 250:750, :3] = 0       # 絵の本体
        img[5:7, 5:7, :3] = 0               # 隅の小さな点 (無視する)
        out = compose.trim_white(img, pad=0)
        self.assertEqual(out.shape[:2], (100, 500))

    def test_valign_bottom(self):
        import numpy as np
        import matplotlib.pyplot as plt
        path = os.path.join(self.tmp, "wide.png")
        plt.imsave(path, np.zeros((10, 40, 3)) + 0.3)
        lay = layout([{"type": "image", "id": "img", "x": 60, "y": 5, "w": 40, "h": 40,
                       "src": path, "valign": "bottom"}])
        c = compose.Composer(lay).draw()
        bid, (x0, y0, dw, dh) = c.blocks[0]
        c.plt.close(c.fig)
        self.assertAlmostEqual(y0 + dh, 45, places=3)   # 下端が枠の下端にそろう

    def test_prompt_ref(self):
        lay = layout([{"type": "image", "id": "i", "x": 60, "y": 5, "w": 30, "h": 30, "src": "b.png",
                       "ref": "a.png", "prompt": "the same scene"}])
        md = make_prompts.render_markdown(make_prompts.collect(lay))
        self.assertIn("参照画像: `a.png`", md)
        self.assertIn("reference_image: \"a.png\"", md)
        self.assertIn("academic_style: false", md)

    def test_chart_ticks_and_approx(self):
        chart = {"type": "chart", "id": "c", "kind": "scatter", "x": 60, "y": 5, "w": 55, "h": 50,
                 "data": {"x": [0, 1, 2], "y": [3, 2, 1]}, "xlabel": "x", "ylabel": "y", "approx": True}
        k = self.kinds(layout([chart]))
        self.assertIn("approx_values", k)
        self.assertNotIn("text_overflow", k)   # 軸の外の目盛を数えない
        chart["approx_note"] = "(approx.)"
        self.assertNotIn("approx_values", self.kinds(layout([chart])))

    def test_bar_chart(self):
        chart = {"type": "chart", "id": "c", "kind": "bar", "x": 60, "y": 5, "w": 55, "h": 50,
                 "data": {"x": ["a", "b"], "y": [28, 1]}, "colors": {"a": "#00ff00"}}
        self.assertEqual(self.kinds(layout([chart])), [])

    def test_box_wrap(self):
        lay = layout([{"type": "box", "id": "b", "x": 60, "y": 5, "w": 20, "h": 30, "size": 9,
                       "text": "a b c d e f g h i j k l m n o p"}])
        self.assertNotIn("text_overflow", self.kinds(lay))

    def test_cli(self):
        path = os.path.join(self.tmp, "layout.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(BASE, f)
        self.assertEqual(compose.main([path, "--check-only"]), 0)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"elements": []}, f)
        self.assertEqual(compose.main([path]), 2)

    def test_examples_compose(self):
        for name in ("paper", "book"):
            lay = compose.load_layout(os.path.join(EXAMPLES, name, "layout.json"))
            kinds = {i["kind"] for i in compose.run(lay, check_only=True)["issues"]}
            # 見本は絵が無いので image_missing だけが出る (書体が無い環境でも)
            kinds.discard("image_missing")
            if compose.pick_font() is None:
                continue   # 日本語の書体が無いと字の幅が変わるので，はみ出しは見ない
            self.assertEqual(kinds, set(), name)


@unittest.skipUnless(HAS_FITZ, "pymupdf が無い")
class TestPdfPages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_pdf(self, name, text=True, **save):
        import pymupdf
        doc = pymupdf.open()
        doc.new_page()   # 表紙 (文字なし)
        for i in range(2):
            page = doc.new_page()
            if text:
                page.insert_text((72, 72), "Results page %d " % (i + 1) * 10)
        path = os.path.join(self.tmp, name)
        doc.save(path, **save)
        return path

    def run_main(self, args):
        import io
        import contextlib
        import pdf_pages
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = pdf_pages.main(args)
        return code, json.loads(buf.getvalue())

    def test_text_pdf(self):
        path = self.make_pdf("a.pdf")
        out = os.path.join(self.tmp, "pages")
        code, info = self.run_main([path, "--out", out, "--pages", "2-3", "--dpi", "50"])
        self.assertEqual(code, 0)
        self.assertFalse(info["scanned"])          # 表紙が 0 字でもスキャンとしない
        self.assertEqual(info["pages"], 3)
        self.assertEqual(len(info["images"]), 2)
        self.assertTrue(os.path.exists(os.path.join(out, "p02.png")))
        with open(info["text"], encoding="utf-8") as f:
            self.assertIn("=== p03 ===", f.read())

    def test_scanned(self):
        path = self.make_pdf("b.pdf", text=False)
        code, info = self.run_main([path, "--info"])
        self.assertEqual(code, 0)
        self.assertTrue(info["scanned"])

    def test_user_password(self):
        import pymupdf
        path = self.make_pdf("c.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256,
                             user_pw="u", owner_pw="o")
        code, info = self.run_main([path, "--info"])
        self.assertEqual(code, 3)
        self.assertTrue(info["needs_password"])

    def test_owner_password_only(self):
        import pymupdf
        path = self.make_pdf("d.pdf", encryption=pymupdf.PDF_ENCRYPT_AES_256,
                             owner_pw="o", permissions=0)
        code, info = self.run_main([path, "--info"])
        self.assertEqual(code, 0)
        self.assertFalse(info["needs_password"])
        self.assertTrue(info["owner_restricted"])

    def test_parse_pages(self):
        import pdf_pages
        self.assertEqual(pdf_pages.parse_pages(None, 3), [0, 1, 2])
        self.assertEqual(pdf_pages.parse_pages("2-,1", 3), [1, 2, 0])
        self.assertEqual(pdf_pages.parse_pages("5", 3), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
