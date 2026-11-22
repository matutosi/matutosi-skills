#!/usr/bin/env python3
"""九州の作業の気づきから足した道具のテスト (shift_check.py・crop.py の --label の警告と列の位置の表示・
check.py の以下略と数え方・sparse.py のコメント行・to_csv.py の調査区数を超える出現地点数).

    python tests/test_tools_kyushu.py

numpy・scipy が無いときは shift_check.py の試験を，Pillow が無いときは画像の試験を飛ばす．
"""

import contextlib
import csv
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import check as chk  # noqa: E402
import sparse  # noqa: E402
import to_csv  # noqa: E402

try:
    from PIL import Image, ImageDraw
except ImportError:                                   # pragma: no cover
    Image = None
try:
    import numpy  # noqa: F401
    import scipy  # noqa: F401
    HAVE_SCIPY = True
except ImportError:                                   # pragma: no cover
    HAVE_SCIPY = False


def run(fn, argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = fn(argv)
    return rc, out.getvalue()


def write_tsv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        for r in rows:
            f.write("\t".join(r) + "\n")


class SparseCommentTest(unittest.TestCase):
    def test_comment_lines_are_skipped(self):
        """#table 以外の # で始まる行はコメントとして読み飛ばす (九州 Tab.137)"""
        d = tempfile.mkdtemp()
        src = os.path.join(d, "a.sp")
        with open(src, "w", encoding="utf-8") as f:
            f.write("#table Tab.7 3\n# 帯 1 (y 2000-3000)\nA b|ア|K|1:+ 3:1・2\n  # 字下げしたコメント\n"
                    "||S|2:+\n")
        sparse.main([src, d])
        with open(os.path.join(d, "transcripts", "Tab.007", "body.tsv"), encoding="utf-8") as f:
            rows = [l.rstrip("\n").split("\t") for l in f]
        self.assertEqual(len(rows), 3)                  # 見出し + 2 行 (コメントは行にならない)
        self.assertEqual(rows[1][3:9], ["A b", "ア", "K", "+", "・", "1・2"])
        self.assertEqual(rows[2][5:9], ["S", "・", "+", "・"])

    def body(self, text, n=5):
        d = tempfile.mkdtemp()
        src = os.path.join(d, "a.sp")
        with open(src, "w", encoding="utf-8") as f:
            f.write(f"#table Tab.8 {n}\n{text}\n")
        sparse.main([src, d])
        with open(os.path.join(d, "transcripts", "Tab.008", "body.tsv"), encoding="utf-8") as f:
            return [l.rstrip("\n").split("\t") for l in f][1]

    def test_quoted_value_with_space(self):
        """値に空白を含められる (引用符)．`+ 2` を次の地点の値と読んで消さない (中国 Tab.010)"""
        r = self.body('A b|ア|K|2:"+ 2" 4:1・2 5:\'1 2\'')
        self.assertEqual(r[6:11], ["・", "+ 2", "・", "1・2", "1 2"])
        r = self.body('A b|ア|K|*+ "+ 2" ・ 1・2 ・')
        self.assertEqual(r[6:11], ["+", "+ 2", "・", "1・2", "・"])
        self.assertEqual(self.body("A b|ア|K|1:+ 3:1・2 5:")[6:11], ["+", "・", "1・2", "・", ""])

    def test_unquoted_space_stops_instead_of_dropping(self):
        """引用符なしの `2:+ 2` は番号の無い値 `2` になり，黙って消さずに止まる"""
        with self.assertRaises(SystemExit) as cm:
            self.body("A b|ア|K|2:+ 2 4:1")
        self.assertIn("番号の無い値", str(cm.exception.code))
        with self.assertRaises(SystemExit) as cm:
            self.body("A b|ア|K|1:+ 1:2")
        self.assertIn("2 回", str(cm.exception.code))
        with self.assertRaises(SystemExit) as cm:
            self.body("A b|ア|K|6:+")
        self.assertIn("範囲", str(cm.exception.code))
        with self.assertRaises(SystemExit):
            self.body('A b|ア|K|*+ "+ 2" ・')              # 値の数が地点の数と合わない


class OverPlotsTest(unittest.TestCase):
    def test_parse_value_over(self):
        """常在度の列で出現地点数が調査区数を超える: 「調査区数を超える」の check (九州 Tab.005)"""
        cov, soc, const, st, note = to_csv.parse_value("4", 2)
        self.assertEqual((cov, soc, const, st), ("", "", "4", "check"))
        self.assertIn("調査区数 2 を超える", note)
        self.assertNotIn("自信なし", note)
        self.assertEqual(to_csv.parse_value("3(+-1)", 2)[:4], ("+-1", "", "3", "check"))
        self.assertEqual(to_csv.parse_value("2", 2)[:4], ("", "", "2", "ok"))    # 超えない数は今までどおり
        self.assertEqual(to_csv.parse_value("4", 0)[:4], ("4", "1", "", "ok"))   # 調査区の列の 4 は被度

    def test_build_keeps_column_kind_note_apart(self):
        d = tempfile.mkdtemp()
        t = os.path.join(d, "transcripts", "Tab.005")
        write_tsv(os.path.join(t, "meta.tsv"), [["key", "value"], ["file", "kyushu_004"], ["table", "Tab.5"]])
        write_tsv(os.path.join(t, "header.tsv"), [["item_ja", "item_de", "unit", "1", "2"],
                                                   ["調査区数", "Zahl d. Aufn.", "", "", "2"]])
        write_tsv(os.path.join(t, "body.tsv"), [
            ["kind", "group_ja", "group_de", "s_name", "j_name", "layer", "1", "2", "note"],
            ["sp", "", "", "Illicium anisatum", "シキミ", "S", "+", "4", ""],
            ["sp", "", "", "Eurya japonica", "ヒサカキ", "S", "1・1", "2", ""],
            ["sp", "", "", "Ilex crenata", "イヌツゲ", "S", "・", "1", ""]])
        sites, comp = to_csv.build(t)
        cell = [c for c in comp if c["plot"] == "2" and c["j_name"] == "シキミ"][0]
        self.assertEqual((cell["constancy"], cell["status"]), ("4", "check"))
        self.assertIn("調査区数 2 を超える", cell["note"])
        self.assertNotIn("列の種類", cell["note"])
        kind = [s for s in sites if s["item_ja"] == "列の種類" and s["plot"] == "2"][0]
        self.assertEqual(kind["value"], "常在度")


def write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in cols})


class CheckAbridgedTest(unittest.TestCase):
    def make(self, abridged_note=True):
        d = tempfile.mkdtemp()
        sites, comp = [], []

        def count(table, plot, n):
            sites.append(dict(table=table, plot=plot, item_ja="出現種数", item_de="Artenzahl", value=str(n),
                              source="header", status="ok"))

        def sp(table, plot, name, source="body"):
            comp.append(dict(table=table, plot=plot, s_name=name, j_name="", layer="K", cover="+",
                             sociability="1", value_raw="+", source=source, status="ok"))
        # Tab.15: 以下略の表 (印字の種数が読んだ種より多い)
        for p, n in (("1", 5), ("2", 6)):
            count("Tab.15", p, n)
            for k in range(3):
                sp("Tab.15", p, f"A s{k}")
        if abridged_note:
            sites.append(dict(table="Tab.15", plot="1", item_ja="本体の省略", item_de="Bemerkung", value="以下略",
                              value_raw="u. a. 以下略", source="note", status="ok"))
        # Tab.38: 地点 1 は本体 + 1 回出現で合う・地点 2 は本体だけで合う・地点 3 はどちらとも合わない
        for p in ("1", "2", "3"):
            for k in range(4):
                sp("Tab.38", p, f"B s{k}")
            sp("Tab.38", p, "C once", "once")
        count("Tab.38", "1", 5)
        count("Tab.38", "2", 4)
        count("Tab.38", "3", 9)
        write_csv(os.path.join(d, "sites.csv"), chk.SITE_COLS, sites)
        write_csv(os.path.join(d, "composition.csv"), chk.COMP_COLS, comp)
        return d

    def test_auto_abridged(self):
        d = self.make()
        rc, out = run(chk.main, [d])
        self.assertNotIn("[種数] Tab.15", out)
        self.assertIn("[以下略] Tab.15 地点 1", out)
        self.assertIn("以下略の表 1: Tab.15 (自動: Tab.15)", out)
        self.assertIn("[種数] Tab.38 地点 2", out)       # 以下略でない表は今までどおり問題
        self.assertIn("本体だけと合う", out)

    def test_option_abridged(self):
        d = self.make(abridged_note=False)
        _, out = run(chk.main, [d])
        self.assertIn("[種数] Tab.15 地点 1", out)
        _, out = run(chk.main, [d, "--abridged", "Tab.015"])  # 0 を詰めた名前でも同じ表
        self.assertNotIn("[種数] Tab.15", out)
        self.assertIn("[以下略] Tab.15 地点 2", out)
        d = self.make()
        _, out = run(chk.main, [d, "--no-abridged-auto"])
        self.assertIn("[種数] Tab.15 地点 1", out)

    def test_counting_per_plot(self):
        d = self.make()
        _, out = run(chk.main, [d])
        self.assertIn("[数え方] Tab.38: 本体 + 1 回出現で合う 1 地点 (1)・本体だけで合う 1 地点 (2)・"
                      "どちらとも合わない 1 地点 (3)", out)


@unittest.skipIf(Image is None, "Pillow が無い")
class CropLabelTest(unittest.TestCase):
    def page(self):
        im = Image.new("L", (900, 700), "white")
        dr = ImageDraw.Draw(im)
        for r in range(12):
            y = 60 + r * 45
            for x in (60, 85, 110, 135):                 # 名前の字 (x 60〜149)
                dr.rectangle((x, y, x + 18, y + 24), outline=0, width=3)
            for c in range(6):                           # 値の列の点 (x 500〜)
                cx = 520 + c * 60
                dr.ellipse((cx - 4, y + 8, cx + 4, y + 16), fill=0)
        return im

    def test_label_cut(self):
        import crop
        im = self.page()
        hits, to = crop.label_cut(im, 120, 40, 620)
        self.assertGreaterEqual(len(hits), 5)
        self.assertIsNotNone(to)
        self.assertLess(to, 60)
        self.assertEqual(crop.label_cut(im, 40, 40, 620), ([], None))

    def test_dense_messages(self):
        import crop
        d = tempfile.mkdtemp()
        src = os.path.join(d, "p.png")
        self.page().save(src)
        _, out = run(crop.main, [src, "--box", "490", "50", "850", "600", "--dense", "6", "--plots", "6",
                                 "--label", "120", "480", "--out", os.path.join(d, "o")])
        self.assertIn("警告: --label の左端 x=120 が字に掛かる", out)
        self.assertIn("列の位置: ", out)
        _, out = run(crop.main, [src, "--box", "490", "50", "850", "600", "--dense", "6", "--plots", "6",
                                 "--label", "40", "480", "--first-x", "520", "--pitch", "60", "--out", os.path.join(d, "o")])
        self.assertNotIn("--label の左端", out)
        self.assertIn("列の位置: 引数 (--first-x・--pitch)", out)


@unittest.skipIf(Image is None, "Pillow が無い")
class CropDeskewTest(unittest.TestCase):
    W, H, C, R = 460, 560, 6, 11

    def slanted(self, slope, lean):
        """行が右へ slope (px あたり) 下がり，列が下ほど右へ lean px 寄る点の表"""
        im = Image.new("L", (self.W, self.H), "white")
        dr = ImageDraw.Draw(im)
        self.truth = []
        for r in range(self.R):
            for c in range(self.C):
                x, y = 60 + c * 60, 40 + r * 46
                X, Y = x + lean * y / self.H, y + slope * x
                dr.ellipse((X - 5, Y - 5, X + 5, Y + 5), fill=0)
                self.truth.append((x, y))
        return im

    def test_deskew_region_straightens_rows_and_columns(self):
        import crop
        slope, lean = 0.06, 24
        im = self.slanted(slope, lean)
        out = crop.deskew_region(im, [self.H / 2], [slope * self.W], self.W, lean)
        px = out.load()
        for x, y in self.truth:
            self.assertLess(px[x, y], 128, (x, y))             # 点が元の位置 (上端・左端の位置) に戻る
        flat = crop.deskew_region(self.slanted(0, 0), [self.H / 2], [0], self.W, 0)
        self.assertEqual(flat.tobytes(), self.slanted(0, 0).convert("L").tobytes())   # 傾きなしは変えない

    def test_estimate_lean(self):
        import crop
        im = self.slanted(0, 24).crop((30, 0, self.W, self.H))
        lean, why = crop.estimate_lean(im, self.C)
        self.assertIsNotNone(lean, why)
        self.assertAlmostEqual(lean, 24, delta=6)
        self.assertIsNone(crop.estimate_lean(Image.new("L", (300, 300), "white"), self.C)[0])

    def test_deskew_option_makes_copy(self):
        import crop
        d = tempfile.mkdtemp()
        src = os.path.join(d, "p.png")
        self.slanted(0, 0).save(src)
        o = os.path.join(d, "o")
        _, out = run(crop.main, [src, "--box", "30", "20", "440", "540", "--dense", "6", "--plots", "6", "--label", "5", "20",
                                 "--shear", "0", "--lean", "0", "--deskew", "--name", "t", "--out", o])
        self.assertIn("傾きを直した写し", out)
        self.assertTrue(os.path.exists(os.path.join(o, "t_deskew.png")))
        self.assertIn("行の傾き 0 px を直した", out)
        self.assertTrue([f for f in os.listdir(o) if f.startswith("t_r1_p01-06")])


@unittest.skipIf(Image is None or not HAVE_SCIPY, "Pillow・numpy・scipy が無い")
class UlSheetTest(unittest.TestCase):
    def setUp(self):
        try:
            import ul_sheet
        except (ImportError, SystemExit):
            self.skipTest("numpy と scipy が無い")
        self.ul = ul_sheet

    def make(self):
        d = tempfile.mkdtemp()
        im = Image.new("L", (400, 300), "white")
        im.save(os.path.join(d, "p.png"))
        head = ["kind", "group_ja", "group_de", "s_name", "j_name", "layer", "1", "2", "3", "note"]
        rows = [head,
                ["sp", "", "", "A a", "ア", "S;K", "+", "・", "1", "3: 下線; 印字は S,K (K に下線)"],
                ["sp", "", "", "B b", "イ", "K", "・", "2", "・", ""],
                ["sp", "", "", "C c", "ウ", "S;K", "・", "+", "+", "2: 二重下線; 3: 下線なし"]]
        write_tsv(os.path.join(d, "transcripts", "Tab.003", "body.tsv"), rows)
        grid = os.path.join(d, "grid.tsv")
        with open(grid, "w", encoding="utf-8", newline="") as f:
            f.write("row\tspecies\t1\t2\t3\ty_first\ty_last\n")
            for k, (a, b) in enumerate([(60, 66), (120, 126), (180, 186)]):
                f.write(f"{k + 1}\tx\t_\t_\t_\t{a}\t{b}\n")
        return d, os.path.join(d, "p.png"), grid

    def test_underlined_plots(self):
        self.assertEqual(self.ul.underlined_plots("3: 下線; 印字は S,K (K に下線)"), {3})
        self.assertEqual(self.ul.underlined_plots("2: 二重下線; 3: 下線なし; 1: 波線"), {1, 2})
        self.assertEqual(self.ul.underlined_plots(""), set())

    def test_sheet_modes(self):
        d, src, grid = self.make()
        base = [src, d, "Tab.3", "--grid", grid, "--first-x", "100", "--pitch", "100"]
        rc, out = run(self.ul.main, base)                              # 下線の付いたセル: 1 行の地点 3・3 行の地点 2
        self.assertEqual(rc, 0, out)
        self.assertIn("2 セル", out)
        path = os.path.join(d, "ul_Tab.003_01.png")
        self.assertTrue(os.path.exists(path))
        w, h = Image.open(path).size
        self.assertGreater(w, 2 * 100 * 3 * .9)                        # 原寸の 3 倍 (幅 100 px) のセルが 2 枚横に並ぶ
        rc, out = run(self.ul.main, base + ["--mode", "multi"])        # 階層が 2 つ以上の行の値: 1 行 (+・1) と 3 行 (+・+)
        self.assertIn("4 セル", out)
        rc, out = run(self.ul.main, base + ["--rows", "2"])            # 行 2 の値のあるセルだけ
        self.assertIn("1 セル", out)
        rc, out = run(self.ul.main, base + ["--rows", "1-3", "--max-tiles", "3"])
        self.assertIn("5 セル", out)
        self.assertTrue(os.path.exists(os.path.join(d, "ul_Tab.003_02.png")))

    def test_row_count_mismatch_stops(self):
        d, src, grid = self.make()
        with open(grid, "a", encoding="utf-8") as f:
            f.write("4\tx\t_\t_\t_\t240\t240\n")
        with self.assertRaises(SystemExit) as cm:
            run(self.ul.main, [src, d, "Tab.3", "--grid", grid, "--first-x", "100", "--pitch", "100"])
        self.assertIn("grid.tsv", str(cm.exception.code))


def body_rows(n_cols, rows, groups_at=()):
    """rows: [(名前, [値 …])]．groups_at: 見出しを入れる種の行の添字"""
    out = [["kind", "group_ja", "group_de", "s_name", "j_name", "layer"] + [str(i) for i in range(1, n_cols + 1)] + ["note"]]
    for i, (name, vals) in enumerate(rows):
        if i in groups_at:
            out.append(["group", "見出し", "Gruppe"] + [""] * (n_cols + 4))
        out.append(["sp", "", "", "Aa " + name, "ア" + name, "K"] + vals + [""])
    return out


@unittest.skipIf(Image is None, "Pillow が無い")
class ShiftCheckTest(unittest.TestCase):
    R, C = 30, 8

    def setUp(self):
        try:
            import shift_check
        except (ImportError, SystemExit):
            self.skipTest("numpy と scipy が無い")
        self.sc = shift_check

    def value(self, r, c):
        return (r * 3 + c * 5) % 4 == 0

    def draw(self, path, rowy, drift=lambda r, c: 0.0, heading=None, merged=()):
        """rowy: 物理の行の y．heading: 見出しの行の y (名前だけで印なし)．merged: 名前を書かない行 (前の行と同じ印字)"""
        im = Image.new("L", (520, int(rowy[-1]) + 80), "white")
        dr = ImageDraw.Draw(im)
        for r, y in enumerate(rowy):
            if r not in merged:
                for x in (40, 62):                       # 階層・和名の字
                    dr.rectangle((x, y - 10, x + 14, y + 10), outline=0, width=3)
            for c in range(self.C):
                cx, yy = 140 + c * 40, y + drift(r, c)
                if self.value(r, c):
                    dr.rectangle((cx - 7, yy - 1, cx + 7, yy + 1), fill=0)
                    dr.rectangle((cx - 1, yy - 7, cx + 1, yy + 7), fill=0)
                else:
                    dr.ellipse((cx - 3, yy - 3, cx + 3, yy + 3), fill=0)
        if heading is not None:
            for x in (40, 62, 84):
                dr.rectangle((x, heading - 10, x + 14, heading + 10), outline=0, width=3)
        im.save(path)

    def transcript(self, d, shift_col=(), part=None, groups_at=()):
        rows = []
        for r in range(self.R):
            vals = []
            for c in range(self.C):
                src = r
                if c in shift_col or (part and c == part[0] and r >= part[1]):
                    src = r + 1                          # 転記の値が 1 行上 (帯の 1 行目を落とした型)
                vals.append("+" if src < self.R and self.value(src, c) else "・")
            rows.append((str(r), vals))
        write_tsv(os.path.join(d, "transcripts", "Tab.011", "body.tsv"), body_rows(self.C, rows, groups_at))

    def test_finds_whole_and_partial_shift(self):
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r + (30 if r >= 10 else 0) for r in range(self.R)]   # 行 10 の上に見出しの行
        src = os.path.join(d, "p.png")
        self.draw(src, rowy, heading=60 + 30 * 10)
        self.transcript(d, shift_col={2}, part=(5, 15), groups_at=(10,))
        rc, out = run(self.sc.main, [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1]), "--ref", "35", "80"])
        self.assertEqual(rc, 0, out)
        self.assertIn("群の見出し 1 行も数えた", out)
        self.assertIn("列 3: 列全体で d=+1", out)
        self.assertRegex(out, r"列 6: 行 1[4-7]-30 .* で d=\+1")
        flagged = [l for l in out.split("---")[1].splitlines() if l.startswith("  列 ")]
        self.assertEqual({l.split(":")[0].strip() for l in flagged}, {"列 3", "列 6"})

    def test_no_false_alarm_and_edge_rows(self):
        """--box の上下端が端の行に掛かっても，印は上下に広げて拾うので落とさない"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        self.draw(src, rowy)
        self.transcript(d)
        rc, out = run(self.sc.main, [src, d, "Tab.11", "--box", "120", "62", "450", str(rowy[-1] - 2), "--ref", "35", "80",
                                     "--edge", "15"])
        self.assertEqual(rc, 0, out)
        self.assertIn("1 行ずれの疑いのある列は無い", out)
        self.assertNotIn("[多い]", out)

    def test_merge_rows(self):
        """1 印字行を 2 行に分けた転記 (括弧書きの種．Tab.016) は --merge-rows でまとめる"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        self.draw(src, rowy)
        rows = []
        for r in range(self.R):
            vals = ["+" if self.value(r, c) else "・" for c in range(self.C)]
            if r == 8:                                   # 物理の行 8 の値を 2 行に分けた
                first = [v if c < 4 else "・" for c, v in enumerate(vals)]
                second = [v if c >= 4 else "・" for c, v in enumerate(vals)]
                rows += [("8a", first), ("8b", second)]
            else:
                rows.append((str(r), vals))
        write_tsv(os.path.join(d, "transcripts", "Tab.016", "body.tsv"), body_rows(self.C, rows))
        args = [src, d, "Tab.16", "--box", "120", "60", "450", str(rowy[-1]), "--ref", "35", "80"]
        rc, out = run(self.sc.main, args)
        self.assertEqual(rc, 1)
        self.assertIn("行の数が合わない", out)
        rc, out = run(self.sc.main, args + ["--merge-rows", "9-10"])
        self.assertEqual(rc, 0, out)
        self.assertIn("分けた行をまとめた: 1 組 9-10", out)
        self.assertIn("1 行ずれの疑いのある列は無い", out)

    def test_track_up_for_fold(self):
        """折り目で右上ほど行が下がる表は --track up (下から追う) で偽の指摘を出さない (Tab.010)"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        drift = lambda r, c: 28.0 * (c / (self.C - 1)) * (1 - r / (self.R - 1))   # 右上で行の間隔の 0.9 倍下がる
        self.draw(src, rowy, drift=drift)
        self.transcript(d)
        args = [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1]), "--ref", "35", "80"]
        rc, out = run(self.sc.main, args + ["--track", "up"])
        self.assertEqual(rc, 0, out)
        self.assertIn("1 行ずれの疑いのある列は無い", out)
        self.assertNotIn("[多い]", out)
        self.assertEqual(out.count("印の無い行 0．"), self.C)   # どの列も全部の行に印が当たる
        self.transcript(d, shift_col={6})                    # 傾いた列でもずれは見つける
        _, out = run(self.sc.main, args + ["--track", "up"])
        self.assertIn("列 7: 列全体で d=+1", out)

    def test_track_chain_for_curved_rows(self):
        """傾きが直線でない (中ほどだけ下がる) 表は --track chain で偽の指摘を出さず，ずれは見つける (Tab.084)"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        drift = lambda r, c: 26.0 * (1 - abs(c - 3.5) / 3.5) * (r / (self.R - 1))   # 中の列の下ほど下がる
        self.draw(src, rowy, drift=drift)
        self.transcript(d)
        args = [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1] + 30), "--ref", "35", "80", "--track", "chain"]
        rc, out = run(self.sc.main, args)
        self.assertEqual(rc, 0, out)
        self.assertIn("1 行ずれの疑いのある列は無い", out)
        self.assertNotIn("[多い]", out)
        self.transcript(d, shift_col={3})
        _, out = run(self.sc.main, args)
        self.assertIn("列 4: 列全体で d=+1", out)

    def test_fold_column_is_excluded(self):
        """--fold の x が通る列は [ずれ]・[多い] の判定から外す (Tab.021)"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        self.draw(src, rowy)
        self.transcript(d, shift_col={4})
        args = [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1]), "--ref", "35", "80"]
        _, out = run(self.sc.main, args)
        self.assertIn("列 5: 列全体で d=+1", out)
        rc, out = run(self.sc.main, args + ["--fold", "300"])
        self.assertEqual(rc, 0, out)
        self.assertIn("折り目の線が通る列 (ずれ・多いの判定から外す): 5", out)
        self.assertIn("1 行ずれの疑いのある列は無い", out)
        self.assertIn("折り目の列で食い違い: 5", out)

    def test_words_and_rings(self):
        """横に続く字は 1 つの印．+ は値，中に穴のある丸 (白抜きの点) は点"""
        import numpy as np
        from types import SimpleNamespace
        a = SimpleNamespace(dot_fill=.5)
        im = Image.new("L", (200, 60), "white")
        dr = ImageDraw.Draw(im)
        dr.ellipse((10, 20, 22, 32), outline=0, width=2)           # 白抜きの点
        dr.rectangle((50, 25, 62, 27), fill=0)                     # +
        dr.rectangle((55, 20, 57, 32), fill=0)
        for x in (100, 112, 124):                                  # 1・1 (3 つのかたまり)
            dr.rectangle((x, 20, x + 4, 32), fill=0)
        path = os.path.join(tempfile.mkdtemp(), "w.png")
        im.save(path)
        comps = self.sc.components(Image.open(path).convert("L"), (0, 0, 200, 60), rule=0)
        isdot = np.array([self.sc.is_dot(q, 16, a) for q in comps])
        words = self.sc.make_words(comps, 30, 10)
        kinds = sorted((round(float(comps[g[0], 0])), self.sc.word_kind(g, comps, isdot, 16, 40)) for g in words)
        self.assertEqual(kinds, [(16, "r"), (56, "v"), (102, "v")])

    def write_grid(self, path, rowy):
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\t".join(["row", "species"] + [str(c + 1) for c in range(self.C)] + ["y_first", "y_last"]) + "\n")
            for k, y in enumerate(rowy):
                f.write("\t".join([str(k + 1), "x"] + ["_"] * self.C + [str(round(y)), str(round(y))]) + "\n")

    def test_track_default_is_chain(self):
        """--track の既定は chain．none で前の動きに戻せる"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        self.draw(src, rowy)
        self.transcript(d)
        args = [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1]), "--ref", "35", "80"]
        rc, out = run(self.sc.main, args)
        self.assertEqual(rc, 0, out)
        rc, out_none = run(self.sc.main, args + ["--track", "none"])
        self.assertEqual(rc, 0, out_none)
        # 既定の結果は --track chain と同じ
        _, out_chain = run(self.sc.main, args + ["--track", "chain"])
        self.assertEqual(out, out_chain)

    def test_grid_rows_without_ref(self):
        """階層・和名の印字の無い行があって --ref が行を測り違える表は，--grid (marks_grid の y) で通る (Tab.115 型)"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        self.draw(src, rowy, merged={4, 5, 17})            # 名前を書かない行 (階層の印字の無い行)
        self.transcript(d, shift_col={2})
        grid = os.path.join(d, "grid.tsv")
        self.write_grid(grid, rowy)
        base = [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1])]
        rc, out = run(self.sc.main, base + ["--ref", "35", "80"])
        self.assertEqual(rc, 1)                            # --ref だけでは行の数が合わない
        self.assertIn("--grid", out)
        rc, out = run(self.sc.main, base + ["--grid", grid])
        self.assertEqual(rc, 0, out)
        self.assertIn("行の y: --grid (first) (30 行)", out)
        self.assertIn("列 3: 列全体で d=+1", out)
        flagged = [l for l in out.split("---")[1].splitlines() if l.startswith("  列 ")]
        self.assertEqual({l.split(":")[0].strip() for l in flagged}, {"列 3"})

    def test_grid_accepts_row_y(self):
        """marks_grid.py が書く row_y.tsv を --grid にそのまま渡せる (この表・このページの行．無い行は前後から補う)"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        self.draw(src, rowy)
        self.transcript(d, shift_col={2})
        path = os.path.join(d, "row_y.tsv")
        lines = ["table\tpage\trow\tname\ty", "Tab.9\tp\t1\tx\t999"]                  # 別の表の行は読まない
        lines += [f"Tab.11\tp\t{r + 1}\tsp{r}\t{y}" for r, y in enumerate(rowy) if r != 7]   # 行 8 は対応しなかった
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        rc, out = run(self.sc.main, [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1]), "--grid", path])
        self.assertEqual(rc, 0, out)
        self.assertIn("row_y.tsv に無い行 [8]", out)
        self.assertIn("列 3: 列全体で d=+1", out)

    def test_small_table_is_out_of_scope(self):
        """種の行が --min-rows より少ない表は「対象外」と知らせて止まる (九州ページ内 Tab.069 は 3 行)"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        self.draw(src, rowy)
        self.transcript(d)
        rc, out = run(self.sc.main, [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1]), "--ref", "35", "80",
                                     "--min-rows", "31"])
        self.assertEqual(rc, 0, out)
        self.assertIn("対象外", out)

    def test_grid_count_mismatch_stops(self):
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        self.draw(src, rowy)
        self.transcript(d)
        grid = os.path.join(d, "grid.tsv")
        self.write_grid(grid, rowy[:-2])
        with self.assertRaises(SystemExit) as cm:
            run(self.sc.main, [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1]), "--grid", grid])
        self.assertIn("--grid", str(cm.exception.code))

    def test_fix_rows_continues_and_reports(self):
        """--fix-rows: 行の数が合わなくても止まらず，補った所を示して続ける．付けなければ前のとおり止まる"""
        d = tempfile.mkdtemp()
        rowy = [60 + 30 * r for r in range(self.R)]
        src = os.path.join(d, "p.png")
        self.draw(src, rowy, merged={10})                  # 行 11 の名前が無く，--ref は 29 行しか測れない
        self.transcript(d)
        args = [src, d, "Tab.11", "--box", "120", "60", "450", str(rowy[-1]), "--ref", "35", "80"]
        rc, out = run(self.sc.main, args)
        self.assertEqual(rc, 1)
        rc, out = run(self.sc.main, args + ["--fix-rows"])
        self.assertEqual(rc, 0, out)
        self.assertIn("[行の補正]", out)
        self.assertIn("足りない行を補った: y=360", out)
        self.assertIn("行: 30 行", out)
        self.assertIn("1 行ずれの疑いのある列は無い", out)

    def test_fix_row_count_and_phys_kinds(self):
        import numpy as np
        ys, notes = self.sc.fix_row_count([10, 40, 100, 130], 5)           # 間隔 60 の所に 1 行足りない
        self.assertEqual(list(ys), [10, 40, 70, 100, 130])
        self.assertTrue(notes[0].startswith("足りない行を補った"))
        ys, notes = self.sc.fix_row_count([10, 40, 70, 100], 5)           # 広い所が無ければ下へ延ばす
        self.assertEqual(list(ys), [10, 40, 70, 100, 130])
        ys, notes = self.sc.fix_row_count([10, 40, 55, 70, 100], 4, cnt=[5, 5, 0, 5, 5])   # 印の無い行を除く
        self.assertEqual(list(ys), [10, 40, 70, 100])
        # まとめた行 (1-2 を 1 行) があっても，見出しの位置を合わせる
        kinds = ["sp", "sp", "group", "sp", "sp"]
        self.assertEqual(self.sc.phys_kinds(kinds, [[0, 1], [2], [3]]), ["sp", "group", "sp", "sp"])
        self.assertEqual(self.sc.phys_kinds(kinds, [[0], [1], [2], [3]]), ["sp", "sp", "group", "sp", "sp"])

    def test_best_segment(self):
        import numpy as np
        e0 = np.array([0, 1, 1, 1, 0, 0, 1, 0])
        ed = np.array([0, 0, 0, 0, 1, 0, 0, 1])
        self.assertEqual(self.sc.best_segment(e0, ed, 2), (3, 1, 3))
        self.assertIsNone(self.sc.best_segment(e0, ed, 4))


class OnceLinesTest(unittest.TestCase):
    def test_slanted_lines(self):
        """右ほど下がる 4 行の段落を左右で測って 1 行ずつ切り，幅ごとに分けて貼る"""
        try:
            import once_lines
        except (ImportError, SystemExit):
            self.skipTest("numpy と scipy が無い")
        from PIL import Image, ImageDraw
        d = tempfile.mkdtemp()
        im = Image.new("L", (3000, 400), "white")
        dr = ImageDraw.Draw(im)
        for i in range(4):
            for x in range(20, 2980, 40):
                y = 60 + 70 * i + 20 * x / 3000            # 右端で 20 px 下がる
                dr.rectangle((x, y - 10, x + 24, y + 10), fill=0)
        src = os.path.join(d, "p.png")
        im.save(src)
        rc, out = run(once_lines.main, [src, d, "--box", "0", "20", "3000", "380", "--width", "1200", "--overlap", "100"])
        self.assertEqual(rc, 0, out)
        self.assertIn("行: 4 行 (左右で測った)", out)
        self.assertIn("(12 切れ)", out)                   # 4 行 × 3 切れ (0・1100・2200)
        self.assertTrue(os.path.exists(os.path.join(d, "once_lines_01.png")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
