#!/usr/bin/env python3
"""marks_grid.py の自己テスト (九州の大新で出た型: 端の行・点の大きさ・折り目と枠の破線・点のそばのよごれ・
帯の画像の端の列・学名での --merge-rows)．

    python tests/test_marks_grid_kyushu.py

numpy・scipy・Pillow が無いときは飛ばす．画像は小さな合成画像．
"""

import contextlib
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

try:
    import marks_grid as mg                      # numpy・scipy が無いと sys.exit で止まる
    from PIL import Image, ImageDraw
except (ImportError, SystemExit):                # pragma: no cover
    mg = None


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = mg.main(argv)
    return rc, out.getvalue()


def cross(draw, x, y, r=7, t=1):
    draw.rectangle((x - r, y - t, x + r, y + t), fill=0)
    draw.rectangle((x - t, y - r, x + t, y + r), fill=0)


def dot(draw, x, y, d=8):
    draw.ellipse((x - d / 2, y - d / 2, x + d / 2, y + d / 2), fill=0)


def make_table(n_rows, xs, value=(), y0=60, pitch=30, dot_d=8, size=None, skip=(), extra=None, names=None, cross_r=7, cross_t=1):
    """点と + の格子の画像と body.tsv を作る．value は値のセル (行, 列)，skip は印の無いセル．
    extra(draw) で折り目・枠などを描き足す．戻り: (置き場, 画像のパス)"""
    d = tempfile.mkdtemp()
    w = size[0] if size else xs[-1] + 80
    h = size[1] if size else y0 + pitch * n_rows + 60
    im = Image.new("L", (w, h), "white")
    draw = ImageDraw.Draw(im)
    for r in range(n_rows):
        for c, x in enumerate(xs):
            y = y0 + r * pitch
            if (r, c) in skip:
                continue
            if (r, c) in value:
                cross(draw, x, y, cross_r, cross_t)
            else:
                dot(draw, x, y, dot_d)
    if extra:
        extra(draw)
    src = os.path.join(d, "t.png")
    im.save(src)
    body = os.path.join(d, "transcripts", "Tab.001")
    os.makedirs(body)
    with open(os.path.join(body, "body.tsv"), "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(["kind", "group_ja", "group_de", "s_name", "j_name", "layer"]
                          + [str(i) for i in range(1, len(xs) + 1)] + ["note"]) + "\n")
        for r in range(n_rows):
            cells = ["+" if (r, c) in value else "・" for c in range(len(xs))]
            s, j = names[r] if names else ("A b%d" % r, "ナ%d" % r)
            f.write("\t".join(["sp", "", "", s, j, "K"] + cells + [""]) + "\n")
    return d, src


@unittest.skipIf(mg is None, "numpy・scipy・Pillow が無い")
class EdgeTest(unittest.TestCase):
    def test_edge_warnings_unit(self):
        """上端が 1 行目の印に近い・列ごとの 1 行目の y がそろわないときに警告する (九州 Tab.011)"""
        marks = [[(60 + 30 * r, "d", 0, 0, 56 + 30 * r, 64 + 30 * r) for r in range(10)] for _ in range(8)]
        for c in (3, 4, 5):
            marks[c] = marks[c][1:]                                  # 1 行目を落とした列
        msgs = mg.edge_warnings(marks, 50, 400, 30)
        self.assertTrue(any("上端 y=50" in m for m in msgs), msgs)
        self.assertTrue(any("1 行目の印の y がそろわない: 列 4-6" in m for m in msgs), msgs)
        self.assertEqual(mg.edge_warnings(marks[:3], 20, 400, 30), [])   # 余白が十分でそろっていれば何も出ない

    def test_edge_warning_in_run(self):
        """1 行目の印にかかる --box で回すと [注意] が出る．余白を取れば出ない"""
        xs = [60 + 40 * c for c in range(8)]
        d, src = make_table(12, xs)
        _, out = run([src, d, "Tab.1", "--box", "30", "58", str(xs[-1] + 30), "420"])
        self.assertIn("[注意] --box の上端 y=58", out)
        _, out = run([src, d, "Tab.1", "--box", "30", "20", str(xs[-1] + 30), "450"])
        self.assertNotIn("[注意]", out)
        self.assertIn("食い違い 0 セル", out)


@unittest.skipIf(mg is None, "numpy・scipy・Pillow が無い")
class DotSizeTest(unittest.TestCase):
    def test_measure_and_auto(self):
        """点の大きさを測って --dot-max を決める (九州 Tab.038．点 14〜16 px で既定 16 だと点を値と取り違えた)"""
        xs = [60 + 50 * c for c in range(10)]
        value = {(3, 2), (7, 5), (10, 8)}
        d, src = make_table(14, xs, value, pitch=40, dot_d=17, cross_r=10, cross_t=2)
        box = ["--box", "25", "20", str(xs[-1] + 35), "620"]
        _, out = run([src, d, "Tab.1"] + box)
        self.assertRegex(out, r"点の大きさ: 1[78] px .*--dot-max 2[0-9] \(自動\)")
        self.assertIn("食い違い 0 セル", out)
        _, out = run([src, d, "Tab.1"] + box + ["--dot-max", "14", "--centers"] + [str(x) for x in xs])   # 明示した値はそのまま使う
        self.assertIn("--dot-max 14 (引数)", out)
        self.assertIn("[画像に点の形]", out)                            # 点が値に見えるときは別に出す
        self.assertNotIn("食い違い 0 セル", out)

    def test_small_dots_keep_floor(self):
        """点の小さい表 (中国・四国) は既定 16 のまま"""
        self.assertEqual(mg.auto_dot_max(8), 16)
        self.assertEqual(mg.auto_dot_max(None), 16)
        self.assertEqual(mg.auto_dot_max(16), 20)


@unittest.skipIf(mg is None, "numpy・scipy・Pillow が無い")
class LineTest(unittest.TestCase):
    def test_fold_line_through_column(self):
        """折り目の細い線が列の中心を縦に通っても，点を値と取らず，線に触れた + を落とさない (九州 Tab.015)"""
        xs = [60 + 50 * c for c in range(8)]
        value = {(2, 3), (6, 3), (9, 1)}

        def fold(draw):
            for y in range(20, 470, 2):                             # 少し波打つ細い線 (幅 2)
                x = xs[3] - 3 + (1 if (y // 40) % 2 else 0)
                draw.rectangle((x, y, x + 1, y + 1), fill=0)
            for y in range(30, 460, 23):                            # 切れ切れの短い線が別の列の点に重なる
                draw.line([(xs[6] + 1, y), (xs[6] + 1, y + 14)], fill=0, width=2)

        d, src = make_table(14, xs, value, pitch=30, dot_d=10, extra=fold)
        _, out = run([src, d, "Tab.1", "--box", "25", "20", str(xs[-1] + 35), "480"])
        self.assertIn("画像の行 14", out)
        self.assertIn("食い違い 0 セル", out)

    def test_dashed_frame(self):
        """区分種の破線の枠 (縦の破線・角) を値や行と取り違えない (九州 Tab.050)"""
        xs = [60 + 60 * c for c in range(6)]

        def frame(draw):
            x0, x1, y0, y1 = xs[2] - 22, xs[3] + 22, 60 + 30 * 3 - 18, 60 + 30 * 7 + 18
            for y in range(y0 + 12, y1 - 8, 14):                    # 縦の破線 (列の中心から 22 px)
                for x in (x0, x1):
                    draw.rectangle((x, y, x + 2, y + 7), fill=0)
            for x in range(x0 + 12, x1 - 8, 14):                    # 横の破線
                for y in (y0, y1):
                    draw.rectangle((x, y, x + 7, y + 2), fill=0)
            for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
                hx = sorted((cx, cx + 12 * sx)); hy = sorted((cy, cy + 2 * sy))
                draw.rectangle((hx[0], hy[0], hx[1], hy[1]), fill=0)  # 角の横の腕
                vx = sorted((cx, cx + 2 * sx)); vy = sorted((cy, cy + 12 * sy))
                draw.rectangle((vx[0], vy[0], vx[1], vy[1]), fill=0)  # 角の縦の腕

        d, src = make_table(12, xs, {(4, 2), (5, 3)}, pitch=30, dot_d=10, extra=frame)
        _, out = run([src, d, "Tab.1", "--box", "25", "20", str(xs[-1] + 35), "450"])
        self.assertIn("枠の破線とみて除いた線", out)
        self.assertIn("画像の行 12", out)
        self.assertIn("食い違い 0 セル", out)

    def test_dashes_unit(self):
        """等間隔の短い線は破線，行ごとに 1 つの縦棒 (I・1) は破線とみない"""
        import numpy as np

        class A:
            dash = 8

        def comp(x, y, w, h):
            return [x, y, w, h, w * h, 1.0, x - w / 2, x + w / 2, y - h / 2, y + h / 2]

        dashes = [comp(100, 50 + 14 * k, 3, 8) for k in range(5)]
        stems = [comp(200, 50 + 40 * k, 3, 22) for k in range(5)]    # 行の間隔 40 の縦棒
        got = mg.dashed_frames(np.array(dashes + stems, float), 50, 40, A())
        self.assertEqual(got.tolist(), [True] * 5 + [False] * 5)

    def test_rule_keeps_dot(self):
        """長い罫線を消しても，線に重なった点は残す"""
        import numpy as np
        bw = np.zeros((200, 60), bool)
        bw[:, 30:32] = True                                         # 縦の罫線
        yy, xx = np.mgrid[:200, :60]
        bw |= (yy - 100) ** 2 + (xx - 31) ** 2 <= 36                 # 線の上の点 (直径 12)
        old = mg.remove_rules(bw, 60)
        new = mg.remove_rules(bw, 60, core=4, keep_max=45)
        self.assertLess(old[94:107, 25:38].sum(), 100)               # 前は点が削れて割れた
        self.assertGreater(new[94:107, 25:38].sum(), 100)
        self.assertFalse(new[:80, 30:32].any())                      # 線は消える


@unittest.skipIf(mg is None, "numpy・scipy・Pillow が無い")
class SmallTest(unittest.TestCase):
    def test_speck_next_to_dot(self):
        """点のすぐそばの小さなよごれは点とみる (九州 Tab.029)．--dot-speck 0 なら前のとおり値に出る"""
        xs = [60 + 50 * c for c in range(8)]

        def speck(draw):
            draw.rectangle((xs[4] + 10, 60 + 30 * 5 - 3, xs[4] + 21, 60 + 30 * 5 + 2), fill=0)   # 12x6．点の約 5 割

        d, src = make_table(10, xs, {(2, 1)}, pitch=30, dot_d=12, extra=speck)
        box = ["--box", "25", "20", str(xs[-1] + 35), "380"]
        _, out = run([src, d, "Tab.1"] + box)
        self.assertIn("食い違い 0 セル", out)
        _, out = run([src, d, "Tab.1"] + box + ["--dot-speck", "0"])
        self.assertIn("ナ5 K: 地点 5", out)

    def test_band_cols_edges(self):
        """--band-cols の両端の列を切らない．紙面の外は白 (九州 Tab.008)"""
        xs = [12 + 40 * c for c in range(6)]                        # 第 1 列が紙面の左端に近い
        d, src = make_table(8, xs, {(1, 0), (3, 5)}, pitch=30, dot_d=8)
        band = os.path.join(d, "band.png")
        _, out = run([src, d, "Tab.1", "--box", "0", "20", str(xs[-1] + 30), "300",
                      "--band", "1", "8", "--band-cols", "1", "6", "--band-png", band])
        self.assertIn("帯の画像", out)
        im = Image.open(band).convert("L")
        p = 40
        self.assertEqual(im.width, 50 + 6 * p + p // 4 * 2 + 50)    # 両端の列に P/4 ずつ足す
        top = im.crop((50, 26, 50 + p // 4, im.height - 1))
        self.assertGreater(top.getextrema()[0], 128)                 # 紙面の外は黒でなく白

    def test_merge_rows_by_name(self):
        """--merge-rows を学名・和名で渡す (九州 Tab.015．行番号の取り違えを防ぐ)"""
        names = [("Aa bb", "アア"), ("Cc dd", "シイ"), ("Cc dd var. ee", "シイモドキ"), ("", ""),
                 ("Ff gg", "フウ"), ("Ff gg", "フウ")]
        rows = [(s, j, "K" if i != 5 else "S") for i, (s, j) in enumerate(names)]
        self.assertEqual(mg.parse_merge_rows(["シイ:Cc dd var. ee"], rows), [[1, 2]])
        self.assertEqual(mg.parse_merge_rows(["Cc dd var. ee"], rows), [[2, 3]])   # 名前の無い続きの行まで
        self.assertEqual(mg.parse_merge_rows(["2-3", "5"], rows), [[1, 2], [4]])
        self.assertEqual(mg.parse_merge_rows(["フウ@S:アア"], rows), [[0, 1, 2, 3, 4, 5]])
        with self.assertRaises(ValueError):
            mg.parse_merge_rows(["フウ:アア"], rows)                  # 同じ名前が 2 行
        with self.assertRaises(ValueError):
            mg.parse_merge_rows(["ナイ"], rows)
        xs = [60 + 50 * c for c in range(6)]
        d, src = make_table(6, xs, {(1, 2)}, pitch=30, dot_d=10, names=names)
        _, out = run([src, d, "Tab.1", "--box", "25", "20", str(xs[-1] + 35), "260", "--merge-rows", "シイ:シイモドキ"])
        self.assertIn("分けた行をまとめた: 1 組 2-3", out)


def dotted_box(draw, x0, y0, x1, y1, d=9, step=18):
    """点線の枠 (直径 d の点が step px おき．四国のページ内の表の a・b の枠)"""
    for x in range(x0, x1 + 1, step):
        for y in (y0, y1):
            draw.rectangle((x, y, x + d - 1, y + d - 1), fill=0)
    for y in range(y0 + step, y1, step):
        for x in (x0, x1):
            draw.rectangle((x, y, x + d - 1, y + d - 1), fill=0)


def dashed_box(draw, x0, y0, x1, y1, t=7, ln=16, step=24):
    """破線の枠 (太さ t・長さ ln の線が step px おき．長さが太さの 2.5 倍に満たない．四国 Tab.124)"""
    for x in range(x0, x1 - ln + 1, step):
        for y in (y0, y1):
            draw.rectangle((x, y, x + ln - 1, y + t - 1), fill=0)
    for y in range(y0 + step, y1 - ln + 1, step):
        for x in (x0, x1):
            draw.rectangle((x, y, x + t - 1, y + ln - 1), fill=0)


@unittest.skipIf(mg is None, "numpy・scipy・Pillow が無い")
class PageTableTest(unittest.TestCase):
    """ページ内の表 (行の間隔 110 px・点 17 px・字の高さ 60 px) の型 (四国のページ内の表 94 表で出たもの)"""

    XS = [80 + 190 * c for c in range(6)]
    PITCH = 110

    def page_table(self, value, extra=None):
        return make_table(8, self.XS, value, y0=80, pitch=self.PITCH, dot_d=17, extra=extra, cross_r=30, cross_t=4)

    def box(self):
        return ["--box", "20", "20", str(self.XS[-1] + 70), str(80 + self.PITCH * 8 - 40)]

    def test_dotted_lines_unit(self):
        """点線・破線の枠は並びとみて，行ごと・列ごとに 1 つの点や値は並びとみない"""
        import numpy as np

        def comp(x, y, w, h):
            return [x, y, w, h, w * h, 1.0, x - w / 2, x + w / 2, y - h / 2, y + h / 2]

        frame_dots = [comp(100, 50 + 16 * k, 9, 9) for k in range(6)]      # 点線 (縦)
        frame_dash = [comp(50 + 24 * k, 300, 16, 7) for k in range(6)]     # 破線 (横．長さが太さの 2.3 倍)
        data_dots = [comp(400, 50 + 110 * k, 10, 10) for k in range(6)]    # 点の列 (行の間隔 110)
        row_dots = [comp(500 + 40 * k, 700, 10, 10) for k in range(6)]     # 点の行 (列の間隔 40．周期が長さの 2.5 倍を超える)
        got = mg.dotted_lines(np.array(frame_dots + frame_dash + data_dots + row_dots, float), 8, 60, 110)
        self.assertEqual(got.tolist(), [True] * 12 + [False] * 12)

    def test_dotted_frame_default(self):
        """点線の枠 (9 px の点) と破線の枠があっても，既定の引数で行の間隔・点の大きさを測り違えない (3a．四国 Tab.044・124・149)"""
        xs, p = self.XS, self.PITCH

        def frames(draw):
            dotted_box(draw, xs[0] - 60, 80 + p - 50, xs[2] + 60, 80 + 3 * p + 45)
            dashed_box(draw, xs[3] - 60, 80 + 4 * p - 50, xs[5] + 60, 80 + 6 * p + 45)

        d, src = self.page_table({(1, 0), (2, 1), (5, 4)}, extra=frames)
        _, out = run([src, d, "Tab.1"] + self.box())
        self.assertIn("点線・破線の枠とみて除いたかたまり", out)
        self.assertRegex(out, r"点の大きさ: 1[78] px")                    # 枠の 9 px の点ではなく紙面の点
        self.assertIn("画像の行 8", out)
        self.assertIn("食い違い 0 セル", out)

    def test_auto_max_h(self):
        """--max-h を省くと，行の間隔の見込みが 80 px 以上の表 (ページ内の表) では 1.1 倍にし，
        折り込みの表 (40-55 px) は 45 のまま (3b)"""
        self.assertEqual(mg.auto_max_h(110), 121)
        self.assertEqual(mg.auto_max_h(55), 45)
        self.assertEqual(mg.auto_max_h(0), 45)
        xs = self.XS
        d, src = self.page_table({(1, 0), (2, 1), (3, 2), (6, 5)})        # 値は高さ 61 px
        _, out = run([src, d, "Tab.1"] + self.box())
        self.assertIn("--max-h", out)
        self.assertIn("食い違い 0 セル", out)
        _, out = run([src, d, "Tab.1"] + self.box() + ["--max-h", "45", "--glyph-h", "45"])
        self.assertNotIn("食い違い 0 セル", out)                          # 前の既定では値を落とした

    def test_summary_thin_roman(self):
        """総合常在度表の細い 1 画の I (縦の線 62 px) を罫線とみて消さない (3c．四国ページ内 Tab.078)"""
        xs, p = self.XS, self.PITCH
        romans = {(0, 0), (2, 3), (4, 1), (6, 5)}
        fives = {(1, 2), (5, 4)}

        def glyphs(draw):
            for r, c in romans:                                     # I: 太さ 6 の縦の線 + 上下のセリフ
                x, y = xs[c], 80 + r * p
                draw.rectangle((x - 3, y - 31, x + 2, y + 31), fill=0)
                draw.rectangle((x - 12, y - 33, x + 11, y - 29), fill=0)
                draw.rectangle((x - 12, y + 29, x + 11, y + 33), fill=0)
            for r, c in fives:                                      # V
                x, y = xs[c], 80 + r * p
                draw.line([(x - 18, y - 30), (x, y + 30), (x + 18, y - 30)], fill=0, width=6)

        d, src = make_table(8, xs, (), y0=80, pitch=p, dot_d=17, skip=romans | fives, extra=glyphs)
        body = os.path.join(d, "transcripts", "Tab.001", "body.tsv")
        with open(body, encoding="utf-8") as f:
            lines = f.read().splitlines()
        rows = [lines[0]]
        for r, line in enumerate(lines[1:]):
            cells = line.split("\t")
            for c in range(len(xs)):
                cells[6 + c] = "I" if (r, c) in romans else "V" if (r, c) in fives else "・"
            rows.append("\t".join(cells))
        with open(body, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(rows) + "\n")
        _, out = run([src, d, "Tab.1"] + self.box())
        self.assertIn("総合常在度表", out)
        self.assertIn("食い違い 0 セル", out)
        _, out = run([src, d, "Tab.1"] + self.box() + ["--rule", "60"])
        self.assertIn("転記 I・画像は", out)                              # 前の既定 (罫線 60 px) では I を落とした


if __name__ == "__main__":
    unittest.main()
