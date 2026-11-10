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

    def test_best_segment(self):
        import numpy as np
        e0 = np.array([0, 1, 1, 1, 0, 0, 1, 0])
        ed = np.array([0, 0, 0, 0, 1, 0, 0, 1])
        self.assertEqual(self.sc.best_segment(e0, ed, 2), (3, 1, 3))
        self.assertIsNone(self.sc.best_segment(e0, ed, 4))


if __name__ == "__main__":
    unittest.main(verbosity=1)
