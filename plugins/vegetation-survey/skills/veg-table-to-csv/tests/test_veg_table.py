#!/usr/bin/env python3
"""veg-table-to-csv のスクリプトの自己テスト.

    python tests/test_veg_table.py

Pillow・PyMuPDF が無いときは，画像を使う試験だけを飛ばす．
"""

import contextlib
import csv
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import check as chk  # noqa: E402
import improve  # noqa: E402
import tables  # noqa: E402
import to_csv  # noqa: E402

EXAMPLE = os.path.join(HERE, "..", "..", "..", "examples", "table")


def run(fn, argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = fn(argv)
    return rc, out.getvalue()


def workdir():
    d = tempfile.mkdtemp()
    shutil.copytree(os.path.join(EXAMPLE, "transcripts"), os.path.join(d, "transcripts"))
    return d


def rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class ParseValueTest(unittest.TestCase):
    def test_values(self):
        for raw, cov, soc, const, st in [
            ("+・2", "+", "2", "", "ok"), ("+", "+", "1", "", "ok"), ("r", "r", "1", "", "ok"),
            ("4・2", "4", "2", "", "ok"), ("3.4", "3", "4", "", "ok"), ("＋・１", "", "", "", "check"),
            ("IV(+-3)", "+-3", "", "IV", "ok"), ("V", "", "", "V", "ok"),
            ("2(3-4)", "2", "3-4", "", "ok"), ("+・2?", "+", "2", "", "check"),
            ("+(+)", "+", "", "+", "ok"), ("+(1)", "1", "", "+", "ok"), ("r(+-1)", "+-1", "", "r", "ok"),
        ]:
            self.assertEqual(to_csv.parse_value(raw)[:4], (cov, soc, const, st), raw)

    def test_count_of_plots(self):
        for raw, cov, const in [("2(3-4)", "3-4", "2"), ("1(+)", "+", "1"), ("3(+-2)", "+-2", "3"),
                                ("2", "", "2"), ("V(+-2)", "+-2", "V")]:
            self.assertEqual(to_csv.parse_value(raw, 3)[:3], (cov, "", const), raw)
        self.assertEqual(to_csv.parse_value("5(1)", 3)[3], "check")      # 調査区数より多い
        self.assertEqual(to_csv.parse_value("+", 12)[:3], ("", "", "+"))   # 常在度の列の + だけは常在度
        self.assertEqual(to_csv.parse_value("r", 6)[:3], ("", "", "r"))
        self.assertEqual(to_csv.parse_value("v", 0)[:4], ("v", "", "", "ok"))   # 規則 X16: 小文字の v は極めて微小
        self.assertEqual(to_csv.parse_value("v", 12)[:4], ("v", "", "", "ok"))  # 常在度の列にも当てる
        self.assertEqual(to_csv.parse_value("+(4-5)", 5)[:3], ("4-5", "", "+"))   # 常在度の列では常在度
        self.assertEqual(to_csv.parse_value("+(4-5)")[:3], ("+", "4-5", ""))      # 地点の列では群度の範囲
        self.assertEqual(to_csv.parse_value("+")[:3], ("+", "1", ""))      # 地点の列は被度
        self.assertEqual(to_csv.parse_value("2(3-4)")[:3], ("2", "3-4", ""))    # 調査区数が無ければ今までどおり

    def test_column_kind_constancy_with_plus_and_once(self):
        """常在度の列の + だけのセルは常在度とし，1 回出現のセルは列の種類に数えない (混在にしない)"""
        def cell(plot, cover, soc, const, raw, source="body"):
            return dict(plot=plot, cover=cover, sociability=soc, constancy=const, value_raw=raw, source=source, note="")
        comp = [cell("1", "", "", "V", "V"), cell("1", "", "", "IV", "IV"), cell("1", "+", "1", "", "+"),
                cell("2", "", "", "V", "V"), cell("2", "", "", "II", "II"), cell("2", "+", "2", "", "+・2", "once")]
        sites = []
        to_csv.add_column_kind("f", "Tab.1", ["1", "2"], {}, comp, sites)
        kinds = {s["plot"]: (s["value"], s["status"]) for s in sites}
        self.assertEqual(kinds["1"], ("常在度", "ok"))      # + は常在度の低い印
        self.assertEqual(kinds["2"], ("常在度", "ok"))      # 1 回出現の +・2 は数えない
        self.assertEqual((comp[2]["constancy"], comp[2]["cover"]), ("+", ""))
        self.assertEqual(comp[5]["cover"], "+")            # 1 回出現のセルは変えない

    def test_column_kind_majority(self):
        """種類の違うセルが少ない列は，多数決で列の種類を決め，少ないほうのセルに印を付ける (0.5.9)"""
        def cell(plot, cover, const, raw, note="", status="ok"):
            return dict(plot=plot, cover=cover, sociability="", constancy=const, value_raw=raw,
                        source="body", note=note, status=status)
        comp = [cell("1", "", "V", "V"), cell("1", "", "III", "III"), cell("1", "2", "", "2・3"),
                cell("2", "", "IV", "IV"), cell("2", "", "II", "II"), cell("2", "1", "", "1・2", "ユーザ確認: 今の転記でよい"),
                cell("3", "1", "", "1・1"), cell("3", "+", "", "+"), cell("3", "", "I", "I"),
                cell("4", "1", "", "1・1"), cell("4", "", "I", "I")]
        sites = []
        to_csv.add_column_kind("f", "Tab.1", ["1", "2", "3", "4"], {}, comp, sites)
        kinds = {s["plot"]: (s["value"], s["status"]) for s in sites}
        self.assertEqual(kinds["1"], ("常在度", "ok"))
        self.assertEqual(comp[2]["status"], "check")       # 少ないほうのセルは check
        self.assertIn("列の種類 (常在度) と違う形のセル", comp[2]["note"])
        self.assertEqual(comp[5]["status"], "ok")          # 回答済みのセルは ok のまま
        self.assertEqual(kinds["3"], ("調査区", "ok"))
        self.assertEqual(comp[8]["status"], "check")
        self.assertEqual(kinds["4"], ("混在", "check"))    # 同数は混在のまま

    def test_plots_per_column(self):
        self.assertEqual(to_csv.plots_per_column([{"item_ja": "調査区数", "item_de": "", "1": "3", "2": "12", "note": ""}]),
                         {"1": 3, "2": 12})
        self.assertEqual(to_csv.plots_per_column([{"item_ja": "調査番号;調査区数", "item_de": "", "1": "6"}]), {})
        # 調査区数の印字が無い 5 未満の列 (値が全部 算用数字) は <5 と書き，上限 4 として読む
        n = to_csv.plots_per_column([{"item_ja": "調査区数", "item_de": "", "1": "<5", "2": "-", "3": "7"}])
        self.assertEqual(n, {"1": 4, "3": 7})
        self.assertEqual(to_csv.parse_value("3(2-3)", n["1"])[:3], ("2-3", "", "3"))
        self.assertEqual(to_csv.parse_value("5(1)", n["1"])[3], "check")       # 5 未満の列で 5 は超える

    def test_partial_date(self):
        """月や日が - の日付・月の範囲 (0.5.10)"""
        f = lambda raw: to_csv.norm_site("調査年月日", "Datum d. Aufn.", raw)[:2]
        self.assertEqual(f("- - -"), ("-", "ok"))
        self.assertEqual(f("'80 - -"), ("1980", "ok"))
        self.assertEqual(f("'80 6 -"), ("1980-06", "ok"))
        self.assertEqual(f("'80 6-11"), ("1980", "ok"))           # 6〜11 月の範囲 (日付ではない)
        self.assertIn("月の範囲 6-11", to_csv.norm_site("調査年月日", "", "'80 6-11")[2])
        self.assertEqual(f("'83 8 3"), ("1983-08-03", "ok"))      # ふつうの日付は今までどおり
        g = to_csv.norm_site("調査年月日", "Datum d. Aufn. (1982)", "7 -", "1982")
        self.assertEqual(g[:2], ("1982-07", "ok"))                 # 日が - で年は項目名にある
        self.assertIn("年は項目名", g[2])
        self.assertEqual(to_csv.norm_site("調査年月日", "", "7 -")[1], "check")   # 年が無ければ読めない

    def test_arabic_in_roman_column(self):
        """調査区数 5 以上の列 (ローマ数字の列) の算用数字 1(+-2) はローマ数字の誤植 (規則 X8)"""
        v = to_csv.parse_value("1(+-2)", 12)
        self.assertEqual(v[:4], ("+-2", "", "I", "ok"))
        self.assertIn("規則 X8", v[4])
        self.assertEqual(to_csv.parse_value("3(+)", 4)[:3], ("+", "", "3"))      # 5 未満の列は出現地点数のまま
        self.assertEqual(to_csv.parse_value("2", 12)[:3], ("", "", "2"))          # 括弧の無い数字は今までどおり

    def test_layer_from_below_keeps_check_and_skips_constancy_only(self):
        """階層の欠け以外の check は消さない．値が常在度の列だけの行には下の階層を当てない (0.5.10)"""
        def row(s, layer, note, c1="", c2=""):
            return dict(kind="sp", s_name=s, j_name="", layer=layer, note=note, **{"1": c1, "2": c2})
        body = [row("A a", "", "check 種名に線．階層の印字は無い", "+", ""),
                row("B b", "S", "", "1", "III"),
                row("C c", "", "階層の印字なし", "・", "II"),
                row("D d", "K", "", "+", "IV")]
        out = to_csv.layer_from_below(body, {"2": 5})
        self.assertIn("check 種名に線．階層の印字は無い", out[0]["note"])   # 理由のある check は残す
        self.assertEqual(out[0]["layer"], "S")                              # 地点の列に値があるので下の階層
        self.assertEqual(out[2]["layer"], "")                               # 常在度の列だけ → 当てない
        self.assertIn(to_csv.NO_LAYER_NOTE, out[2]["note"])
        out = to_csv.layer_from_below([row("A a", "", "check 階層の印字が無い", "+"), row("B b", "S", "", "1")], {})
        self.assertNotIn("check", out[0]["note"])                           # 階層の欠けだけの check は外す

    def test_layer_from_below_run_and_partial_date_dash(self):
        """階層の無い行が続く最後の行に下の階層を当てない．`'82 6-7 -` は月の範囲 (0.5.14)"""
        def row(s, layer, note):
            return dict(kind="sp", s_name=s, j_name="", layer=layer, note=note, **{"1": "+"})
        body = [row("A a", "", "階層の印字なし"), row("B b", "", "階層の印字なし"), row("C c", "K", "")]
        out = to_csv.layer_from_below(body, {})
        self.assertEqual([r["layer"] for r in out], ["", "", "K"])
        body = [row("A a", "", "階層の欄は空欄 (…)"), row("B b", "", "階層の印字なし"), row("C c", "K", "")]
        self.assertEqual(to_csv.layer_from_below(body, {})[1]["layer"], "")
        body = [row("A a", "S", ""), row("B b", "", "階層の印字なし"), row("C c", "K", "")]
        self.assertEqual(to_csv.layer_from_below(body, {})[1]["layer"], "K")   # 1 行だけなら今までどおり
        f = lambda raw: to_csv.norm_site("調査年月日", "Datum d. Aufn.", raw)
        self.assertEqual(f("'82 6-7 -")[:2], ("1982", "ok"))
        self.assertIn("月の範囲 6-7", f("'82 6-7 -")[2])

    def test_presence_mark(self):
        self.assertEqual(to_csv.parse_value("O")[:4], ("O", "", "", "ok"))
        self.assertEqual(to_csv.parse_value("○")[:4], ("O", "", "", "ok"))

    def test_absent(self):
        for raw in ("", "・", "-", "."):
            self.assertIsNone(to_csv.parse_value(raw))

    def test_unreadable(self):
        self.assertEqual(to_csv.parse_value("?")[3], "check")
        self.assertEqual(to_csv.parse_value("・?")[4], "非出現か自信なし")

    def test_soc_default_cover(self):
        old = to_csv.SOC_DEFAULT
        try:
            to_csv.SOC_DEFAULT = "cover"
            for raw, soc in (("3", "3"), ("4", "4"), ("2", "2"), ("1", "1"), ("+", "1"), ("r", "1"),
                             ("3・2", "2"), ("+・2", "2")):
                self.assertEqual(to_csv.parse_value(raw)[1], soc, raw)
            to_csv.SOC_DEFAULT = "one"
            self.assertEqual(to_csv.parse_value("3")[1], "1")
        finally:
            to_csv.SOC_DEFAULT = old

    def test_bracket(self):
        self.assertIn("括弧付き", to_csv.parse_value("(+)")[4])


class PreferJaNameTest(unittest.TestCase):
    def test_targets_species_mismatch(self):
        """属は同じで種が合わない行も和名を優先して直す (0.5.13)．--genus-only で属だけ"""
        import prefer_ja_name as pj
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "names.tsv"), "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t", lineterminator="\n")
            w.writerow(["status", "j_name", "s_name", "count", "hub", "latin", "family", "same_genus", "candidates", "note"])
            w.writerow(["ok", "ヒメジョオン", "Erigeron canadensis", "1", "", "Erigeron annuus", "", "1", "", ""])
            w.writerow(["ok", "ヤマハギ", "Lespedeza bicolor var. japonica", "1", "", "Lespedeza bicolor", "", "1", "", ""])
            w.writerow(["ok", "ヤブマメ", "Edgeworthia trisperma", "1", "", "Amphicarpaea edgeworthii", "", "0", "", ""])
        t = pj.targets(d, {"ok"}, set())
        self.assertEqual(t[("Erigeron canadensis", "ヒメジョオン")], "Erigeron annuus")   # 種が合わない
        self.assertNotIn(("Lespedeza bicolor var. japonica", "ヤマハギ"), t)              # 下の階級だけの違いは直さない
        self.assertIn(("Edgeworthia trisperma", "ヤブマメ"), t)                             # 属が合わない
        t = pj.targets(d, {"ok"}, set(), genus_only=True)
        self.assertNotIn(("Erigeron canadensis", "ヒメジョオン"), t)


class DateTest(unittest.TestCase):
    def test_forms(self):
        self.assertEqual(to_csv.norm_date("6. Juli 1983"), "1983-07-06")
        self.assertEqual(to_csv.norm_date("'83 8 3"), "1983-08-03")
        self.assertEqual(to_csv.norm_date("8 3", "1983"), "1983-08-03")
        self.assertEqual(to_csv.norm_date("1983年8月3日"), "1983-08-03")
        self.assertIsNone(to_csv.norm_date("不明"))


class ReviewHtmlTest(unittest.TestCase):
    def test_from_tsv(self):
        """user_review.tsv から赤枠つきの画像を埋め込んだ HTML ができる"""
        import review_html
        from PIL import Image
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "work"))
        Image.new("RGB", (800, 600), "white").save(os.path.join(d, "work", "p001.png"))
        with open(os.path.join(d, "user_review.tsv"), "w", encoding="utf-8") as f:
            f.write("table\tplot\tj_name\tkind\twhat\tpage\tx0\ty0\tx1\ty1\n")
            f.write("Tab.1\t3\tヨシ\t値\t下の値はどちらの種か\tp001\t300\t200\t400\t260\n")
        out = os.path.join(d, "r.html")
        run(review_html.main, [os.path.join(d, "user_review.tsv"), out])
        s = open(out, encoding="utf-8").read()
        self.assertIn("U01", s)
        self.assertIn("data:image/png;base64,", s)
        self.assertIn("下の値はどちらの種か", s)

    def test_answers_file_name(self):
        """回答 JSON の保存名に地方名が付く (--region か，出力 HTML の名前から)．読み込みはファイル名を見ない (2026-11-05)"""
        import review_html
        from PIL import Image
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "work"))
        Image.new("RGB", (800, 600), "white").save(os.path.join(d, "work", "p001.png"))
        tsv = os.path.join(d, "user_review.tsv")
        with open(tsv, "w", encoding="utf-8") as f:
            f.write("table\tplot\tj_name\tkind\twhat\tpage\tx0\ty0\tx1\ty1\n")
            f.write("Tab.1\t3\tヨシ\t読めない値\tかすれ\tp001\t300\t200\t400\t260\n")

        def read(p):
            with open(p, encoding="utf-8") as fh:
                return fh.read()

        def page(*argv):
            run(review_html.main, [tsv, *argv])
            return read(argv[0])
        s = page(os.path.join(d, "x.html"), "--region", "kanto", "--title", "組成表の確認 (関東)")
        self.assertIn('const FNAME="kanto_review_answers.json"', s)
        self.assertIn("<title>組成表の確認 (関東)</title>", s)     # --title があれば題は変えない
        self.assertIn("<title>確認 (kanto)</title>", page(os.path.join(d, "y.html"), "--region", "kanto"))
        self.assertIn('const FNAME="okinawa_review_answers.json"', page(os.path.join(d, "okinawa.html")))
        self.assertIn('const FNAME="review_answers.json"', page(os.path.join(d, "z.html"), "--region", ""))
        self.assertNotIn("review_answers.json'", review_html.JS)      # 保存名を JS に固定で書かない
        self.assertNotIn(".name", review_html.JS)                     # 読み込みはファイル名で選ばない
        self.assertEqual(review_html.answers_name("to hoku/x"), "to_hoku_x_review_answers.json")
        run(review_html.main, [tsv, os.path.join(d, "ui"), "--split", "--region", "kinki"])
        self.assertIn('const FNAME="kinki_A_review_answers.json"', read(os.path.join(d, "ui", "review_A.html")))

    def test_split_by_group(self):
        """--split で区分ごとの HTML に分ける．A の項目には値の入力欄が付く"""
        import review_html
        from PIL import Image
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "work"))
        Image.new("RGB", (800, 600), "white").save(os.path.join(d, "work", "p001.png"))
        with open(os.path.join(d, "user_review.tsv"), "w", encoding="utf-8") as f:
            f.write("table\tplot\tj_name\tkind\twhat\tpage\tx0\ty0\tx1\ty1\n")
            f.write("Tab.1\t3\tヨシ\t読めない値\tかすれ\tp001\t300\t200\t400\t260\n")
            f.write("Tab.1\t4\tヨシ\tB. 下線の対応\t下線\tp001\t300\t200\t400\t260\n")
            f.write("Tab.1\t5\t\t表頭の値\t入れ替わり\tp001\t300\t200\t400\t260\n")
        out = os.path.join(d, "ui")
        run(review_html.main, [os.path.join(d, "user_review.tsv"), out, "--split"])
        self.assertEqual(sorted(os.listdir(out)), ["review_A.html", "review_B.html", "review_D.html"])
        self.assertIn('data-opt="val"', open(os.path.join(out, "review_A.html"), encoding="utf-8").read())

    def test_plot_labels_and_head_rows(self):
        """地点の文字列を番号にする．等間隔の列は測って番号を振る．head_rows.tsv があれば通し番号の行を貼る (0.5.16)"""
        import review_html
        from PIL import Image, ImageDraw
        self.assertEqual(review_html.parse_plots("6,9-11,14"), [6, 9, 10, 11, 14])
        self.assertEqual(review_html.parse_plots("8?,17"), [8, 17])
        self.assertEqual(review_html.parse_plots("a,3"), [])
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "work"))
        im = Image.new("RGB", (1000, 600), "white")
        dr = ImageDraw.Draw(im)
        for k in range(8):                       # 列 1〜8 (x = 100, 200, …)．各列に点を 5 行
            for y in range(250, 450, 40):
                dr.ellipse((100 + 100 * k - 4, y - 4, 100 + 100 * k + 4, y + 4), fill="black")
        im.save(os.path.join(d, "work", "p001.png"))
        cols, ok = review_html.plot_cols(d, "work/p001.png", [250, 300, 650, 340], [100, 150, 800, 490], "3,6")
        self.assertTrue(ok)
        self.assertEqual([t for _, t in cols], ["3", "4", "5", "6"])
        self.assertTrue(all(abs(x - (100 + 100 * (int(t) - 1))) <= 6 for x, t in cols))
        cols, ok = review_html.plot_cols(d, "work/p001.png", [250, 300, 650, 340], [100, 150, 800, 490], "3")
        self.assertFalse(ok)
        self.assertEqual(cols, [[450, "地点 3"]])
        tsv = os.path.join(d, "user_review.tsv")
        with open(tsv, "w", encoding="utf-8") as f:
            f.write("table\tplot\tj_name\tkind\twhat\tpage\tx0\ty0\tx1\ty1\n")
            f.write("Tab.1\t3,6\tヨシ\t読めない値\tかすれ\tp001\t250\t500\t650\t540\n")
        hr = os.path.join(d, "head_rows.tsv")
        with open(hr, "w", encoding="utf-8") as f:
            f.write("region\ttable\tpage\ty0\ty1\tnote\nx\tTab.1\tp001\t40\t80\t\ny\tTab.1\tp001\t\t\t無い\n")
        self.assertEqual(review_html.load_head_rows(hr, "x"), {("Tab.1", "p001"): [40, 80]})
        self.assertEqual(review_html.load_head_rows(hr, "y"), {})
        it = review_html.from_tsv(tsv, review_html.load_head_rows(hr, "x"))[0]
        self.assertEqual(it["images"][0]["head_y"], [40, 80])
        self.assertIn("通し番号", it["images"][0]["caption"])
        self.assertNotIn("head_y", review_html.from_tsv(tsv)[0]["images"][0])

    def test_plot_x_map_and_narrow(self):
        """通し番号の行のかたまりから地点の列の x を測り，確かめる地点の前後だけに切り出す (0.5.20)"""
        import review_html as R
        from PIL import Image, ImageDraw
        im = Image.new("L", (2000, 800), 255)
        dr = ImageDraw.Draw(im)
        for k in range(12):                      # 通し番号の行 (y 100-130)．先頭のかたまり (x 200) は地点ではない
            x = 200 + 100 * k
            dr.rectangle((x - 8, 100, x + 8, 130), fill=0)
            if k:                                # 地点の列 (x 300〜1300) には本体に点が並ぶ
                for y in range(300, 600, 40):
                    dr.ellipse((x - 4, y - 4, x + 4, y + 4), fill=0)
        xmap = R.plot_x_map(im, [95, 135], 11, [280, 620])
        self.assertEqual(xmap[1], 300)
        self.assertEqual(xmap[11], 1300)
        crop = R.narrow_crop([150, 250, 1450, 650], xmap, [9])
        self.assertEqual(crop[1:4:2], [250, 650])
        self.assertTrue(crop[0] < 1000 - 50 and crop[0] > 900 - 100)       # 地点 7 (x 900) の少し左から
        self.assertTrue(crop[2] > 1300 and crop[2] < 1400)                 # 地点 11 (x 1300) の少し右まで
        self.assertEqual(R.narrow_crop([150, 250, 1450, 650], None, [9]), [150, 250, 1450, 650])
        # 赤枠が段落や行を囲んで狭めた範囲からはみ出すときは狭めない (中国 U86)
        self.assertEqual(R.narrow_crop([150, 250, 1450, 650], xmap, [9], box=[250, 300, 1350, 340]), [150, 250, 1450, 650])
        self.assertEqual(R.parse_plots("30,32"), [30, 32])

    def test_plot_x_map_table_range(self):
        """同じ高さに 2 つの表が並ぶとき，xr (その表の左右) の中だけで通し番号を探す"""
        import review_html as R
        from PIL import Image, ImageDraw
        im = Image.new("L", (3000, 800), 255)
        dr = ImageDraw.Draw(im)
        for left in (100, 1700):                  # 左の表 (x 100〜1000) と右の表 (x 1700〜2600)．どちらも 10 地点
            for k in range(10):
                x = left + 100 * k
                dr.rectangle((x - 8, 100, x + 8, 130), fill=0)
                for y in range(300, 600, 40):
                    dr.ellipse((x - 4, y - 4, x + 4, y + 4), fill=0)
        right = R.plot_x_map(im, [95, 135], 10, [280, 620], xr=[1600, 2700])
        self.assertEqual(right[1], 1700)
        self.assertEqual(right[10], 2600)
        left = R.plot_x_map(im, [95, 135], 10, [280, 620], xr=[0, 1100])
        self.assertEqual(left[1], 100)
        d = tempfile.mkdtemp()
        hr = os.path.join(d, "head_rows.tsv")
        with open(hr, "w", encoding="utf-8") as f:
            f.write("region\ttable\tpage\ty0\ty1\tnote\tx0\tx1\nx\tTab.1\tp001\t40\t80\t\t1600\t2700\n")
        self.assertEqual(R.load_head_rows(hr, "x"), {("Tab.1", "p001"): [40, 80, 1600, 2700]})

    def test_col_x_and_box_check(self):
        """marks_grid.py が書く col_x.tsv を読み，赤枠が地点の列から外れていれば知らせる (0.5.21)"""
        import review_html as R
        d = tempfile.mkdtemp()
        p = os.path.join(d, "col_x.tsv")
        try:                                     # marks_grid.py は読み込みに numpy と scipy が要る (CI には無い)
            import marks_grid as M
        except (ImportError, SystemExit):        # 無いと marks_grid.py は sys.exit で止まる
            M = None
        if M:
            M.save_col_x(p, "Tab.9", "p001", [100.0, 200.0, 300.0])
            M.save_col_x(p, "Tab.10", "p001", [150.0, 250.0])
            M.save_col_x(p, "Tab.9", "p001", [110.0, 210.0, 310.0])     # 同じ表・ページは置き換える
        else:                                    # save_col_x と同じ形を手で書いて，review_html の読みだけ確かめる
            with open(p, "w", encoding="utf-8") as f:
                f.write("table\tpage\tplot\tx\n")
                f.write("Tab.10\tp001\t1\t150\nTab.10\tp001\t2\t250\n")
                f.write("Tab.9\tp001\t1\t110\nTab.9\tp001\t2\t210\nTab.9\tp001\t3\t310\n")
        R._COLX.clear()
        cx = R.load_col_x(d)
        self.assertEqual(cx[("Tab.9", "p001")], {1: 110, 2: 210, 3: 310})
        self.assertEqual(cx[("Tab.10", "p001")], {1: 150, 2: 250})
        self.assertEqual(R.table_key("Tab.009"), "Tab.9")
        self.assertIsNone(R.box_off_column(cx[("Tab.9", "p001")], [2], [180, 0, 240, 10]))
        warn = R.box_off_column(cx[("Tab.9", "p001")], [3], [180, 0, 240, 10])     # 地点 3 の列は x 310
        self.assertIn("地点 2", warn)

    def test_options_from_what(self):
        """what に文で書いた選択肢をラジオボタンの選択肢に取り出す (2026-11-08．四国 U02)"""
        import review_html as R
        note, labs = R.options_from_what("地点 10 に + がある．選択肢: 今の転記 (B2 に +．印字どおり) でよい / "
                                         "地点 10 の + を S に移す (下の層とみる) / B1 に移す．赤枠は地点 10")
        self.assertEqual(labs, ["今の転記 (B2 に +．印字どおり) でよい", "地点 10 の + を S に移す (下の層とみる)", "B1 に移す"])
        self.assertEqual(note, "地点 10 に + がある．赤枠は地点 10．")
        _, labs = R.options_from_what("点の上に + が重なる．今の転記 (+?) でよい / 出現なし (・) とする (点とみる)")
        self.assertEqual(labs, ["今の転記 (+?) でよい", "出現なし (・) とする (点とみる)"])
        _, labs = R.options_from_what("印字は 1・21．選択肢: 1・2 とする (余分な字とみる)・2・1 とする・今の転記 (1・2?) でよい")
        self.assertEqual(labs, ["1・2 とする (余分な字とみる)", "2・1 とする", "今の転記 (1・2?) でよい"])
        self.assertEqual(R.options_from_what("選択肢の無い説明．"), ("選択肢の無い説明．", []))
        opts = R.options_of("A", ["今の転記 (+?) でよい", "出現なしとする"], "+?")
        self.assertEqual([o["value"] for o in opts], ["a", "b", "val"])     # A には入力欄を足す
        opts = R.options_of("B", ["S に移す", "B1 に移す"], "B2 +")
        self.assertEqual(opts[-1]["label"], "今の転記 (B2 +) でよい")      # 今の転記の選択肢が無ければ足す

    def test_row_col_labels(self):
        """rows・cols を書くと，種名と地点番号の余白が付いて画像が大きくなる"""
        import review_html
        from PIL import Image
        d = tempfile.mkdtemp()
        Image.new("RGB", (800, 600), "white").save(os.path.join(d, "p.png"))
        sp = {"page": "p.png", "crop": [300, 200, 500, 300]}
        plain = review_html.make_image(d, sp)
        sp2 = dict(sp, rows=[[250, "ナナカマド K"]], cols=[[400, "46"]])
        self.assertGreater(len(review_html.make_image(d, sp2)), len(plain))
        self.assertGreater(review_html.add_labels(Image.new("RGB", (100, 50)), [[10, "ヨシ"]], [[20, "1"]], 0, 0).width, 100)

    def test_layer_strip(self):
        """layer_x (階層の列) が切り出しの外なら左に貼って画像が広がる．切り出しの中なら貼らない (2026-11-05)"""
        import base64
        import review_html
        from PIL import Image
        d = tempfile.mkdtemp()
        Image.new("RGB", (800, 600), "white").save(os.path.join(d, "p.png"))

        def width(sp):
            return Image.open(io.BytesIO(base64.b64decode(review_html.make_image(d, sp)))).width
        sp = {"page": "p.png", "crop": [500, 200, 700, 300]}
        self.assertEqual(width(dict(sp, layer_x=[300, 360])), width(sp) + 60 + 8)   # 8 は境の余白
        self.assertEqual(width(dict(sp, layer_x=[520, 560])), width(sp))
        # 種名の列と続けて貼る (重なるぶんは除く)
        self.assertEqual(width(dict(sp, names_x=[100, 330], layer_x=[300, 360])), width(sp) + 230 + 30 + 8)
        # user_review.tsv の任意の列 layer_x0・layer_x1
        os.makedirs(os.path.join(d, "work"))
        Image.new("RGB", (800, 600), "white").save(os.path.join(d, "work", "p001.png"))
        with open(os.path.join(d, "user_review.tsv"), "w", encoding="utf-8") as f:
            f.write("table\tplot\tj_name\tkind\twhat\tpage\tx0\ty0\tx1\ty1\tlayer_x0\tlayer_x1\n")
            f.write("Tab.1\t27\tサカキ\tB. 下線の対応\t下線か折り目か\tp001\t600\t200\t650\t230\t300\t360\n")
            f.write("Tab.1\t28\tクリ\tB. 下線の対応\t下線か\tp001\t600\t250\t650\t280\t\t\n")
        it = review_html.from_tsv(os.path.join(d, "user_review.tsv"))
        self.assertEqual(it[0]["images"][0]["layer_x"], [300, 360])
        self.assertIn("階層の列", it[0]["images"][0]["caption"])
        self.assertNotIn("layer_x", it[1]["images"][0])

    def test_option_marks_and_column_box(self):
        """選択肢の頭の記号 (a: など) は外す．1 地点だけを見るのに赤枠が横に長いときは，その列にも縦の赤枠を付ける (2026-11-09)"""
        import review_html as R
        from PIL import Image
        _, labs = R.options_from_what("+ か点か．選択肢: a: 点 (出現なし．出現種数が印字と一致) / b: + (出現種数が印字より 1 多い)")
        self.assertEqual(labs, ["点 (出現なし．出現種数が印字と一致)", "+ (出現種数が印字より 1 多い)"])
        _, labs = R.options_from_what("説明．選択肢: 1) 今の転記でよい / 2) 別の地点にも + がある")
        self.assertEqual(labs, ["今の転記でよい", "別の地点にも + がある"])
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "work"))
        Image.new("RGB", (1200, 600), "white").save(os.path.join(d, "work", "p001.png"))
        with open(os.path.join(d, "col_x.tsv"), "w", encoding="utf-8") as f:
            f.write("table\tpage\tplot\tx\n" + "".join(f"Tab.1\tp001\t{k}\t{100 + 50 * k}\n" for k in range(1, 15)))
        with open(os.path.join(d, "user_review.tsv"), "w", encoding="utf-8") as f:
            f.write("table\tplot\tj_name\tkind\twhat\tpage\tx0\ty0\tx1\ty1\n")
            f.write("Tab.1\t4\tウバメガシ\tA. 読めない値\t1 桁だけ\tp001\t120\t200\t800\t260\n")   # 行を横に長く囲んだ
            f.write("Tab.1\t5\tトベラ\tA. 読めない値\tかすれ\tp001\t330\t200\t370\t230\n")      # そのセルだけ
        it = R.from_tsv(os.path.join(d, "user_review.tsv"))
        marks = it[0]["images"][0]["marks"]
        self.assertEqual(len(marks), 2)
        self.assertEqual((marks[1]["box"][0] + marks[1]["box"][2]) // 2, 300)        # 地点 4 の列 (x 300)
        self.assertIn("縦の赤枠は地点 4", it[0]["images"][0]["caption"])
        self.assertEqual(len(it[1]["images"][0]["marks"]), 1)

    def test_export_png(self):
        """--export-png で各項目の画像を PNG に書き出す (赤枠が説明の場所と合うかを確かめる．2026-11-09)"""
        import review_html as R
        from PIL import Image
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "work"))
        Image.new("RGB", (800, 600), "white").save(os.path.join(d, "work", "p001.png"))
        tsv = os.path.join(d, "user_review.tsv")
        with open(tsv, "w", encoding="utf-8") as f:
            f.write("table\tplot\tj_name\tkind\twhat\tpage\tx0\ty0\tx1\ty1\n")
            f.write("Tab.1\t3\tヨシ\tA. 読めない値\tかすれ．選択肢: 今の転記 (+) でよい / 点とする\tp001\t250\t300\t300\t330\n")
        png = os.path.join(d, "png")
        run(R.main, [tsv, os.path.join(d, "r.html"), "--export-png", png])
        self.assertTrue(os.path.exists(os.path.join(png, "U01_0.png")))

    def test_option_problems(self):
        """判断の根拠と結果の無い選択肢を知らせる (2026-11-09 ユーザ指示．中国 U29)"""
        import review_html as R
        self.assertIn("選択肢が無い", R.option_problems([], ""))
        self.assertIn("中身が無い", R.option_problems(["今の転記でよい", "K とする"], ""))
        self.assertEqual(R.option_problems(["今の転記でよい", "K とする"], "B1;K +"), "")      # current 列で中身が付く
        self.assertEqual(R.option_problems(["今の転記 (下線なしのため K 層) でよい", "B1 とする"], ""), "")


class ConvertTest(unittest.TestCase):
    def test_golden(self):
        """見本の転記表から，examples の正解と1バイトも違わない CSV ができる."""
        d = workdir()
        run(to_csv.main, [d])
        for name in ("sites.csv", "composition.csv"):
            with open(os.path.join(d, name), "rb") as f, open(os.path.join(EXAMPLE, "expected_" + name), "rb") as g:
                self.assertEqual(f.read().split(), g.read().split(), name)   # checkout で CRLF になる環境がある

    def test_no_transcripts(self):
        with self.assertRaises(SystemExit):
            run(to_csv.main, [tempfile.mkdtemp()])

    def test_multi_layer(self):
        d = workdir()
        body = os.path.join(d, "transcripts", "Tab.1", "body.tsv")
        with open(body, "a", encoding="utf-8") as f:
            f.write("sp\t\t\tSasa sp.\tササ属の1種\tS;K\t+\t・\t・\t\n")
        run(to_csv.main, [d])
        hit = [r for r in rows(os.path.join(d, "composition.csv")) if r["layer"] == "S;K"]
        self.assertEqual(hit[0]["status"], "multi")

    def test_note_for_one_plot(self):
        d = workdir()
        body = os.path.join(d, "transcripts", "Tab.1", "body.tsv")
        with open(body, "a", encoding="utf-8") as f:
            f.write("sp\t\t\tPinus thunbergii\tクロマツ\t\t+\t1・1\t・\t2: 下線\n")
        run(to_csv.main, [d])
        hit = {r["plot"]: r["note"] for r in rows(os.path.join(d, "composition.csv")) if r["j_name"] == "クロマツ"}
        self.assertEqual(hit, {"1": "", "2": "下線"})

    def test_cell_layer_by_underline_kind(self):
        """3 つ書きの階層で一重・二重の下線を使い分ける行は，セルの「N: 二重下線」「N: 一重下線」で階層を決める (0.5.32)"""
        to_csv.PLOTS_SEEN.clear()
        to_csv.PLOTS_SEEN.update(["1", "2", "3", "4"])
        row = {"layer": "B1;S;K", "1": "1・1", "2": "+", "3": "2・2", "4": "+",
               "note": "印字は B1,S,K (B1 に二重下線・K に一重下線); 1: 二重下線; 3: 一重下線; 4: 下線"}
        self.assertEqual(to_csv.cell_layer(row, "1"), "B1")
        self.assertEqual(to_csv.cell_layer(row, "3"), "K")
        self.assertEqual(to_csv.cell_layer(row, "2"), "S")          # 印の無い値は残りの階層
        self.assertEqual(to_csv.cell_layer(row, "4"), "B1;S;K")     # 種類の分からない下線は決めない
        wavy = {"layer": "B2;S;K", "2": "+", "note": "印字は B2,S,K (B2 に二重下線・S に波線); 2: 波線"}
        self.assertEqual(to_csv.cell_layer(wavy, "2"), "S")
        mixed = {"layer": "B1;B2;S", "1": "1・1", "2": "+",
                 "note": "印字は B1,B2,S (B1 に下線，B2 に二重下線); 1: 下線"}   # 種類を書かない下線と二重下線
        self.assertEqual(to_csv.cell_layer(mixed, "1"), "B1")
        self.assertEqual(to_csv.cell_layer(mixed, "2"), "S")
        to_csv.PLOTS_SEEN.clear()

    def test_cell_layer_by_layer_underline(self):
        """階層の字の下線が note に分かれば，下線の値はその階層，下線の無い値は残りの階層に決まる (multi を外す)"""
        row = {"layer": "B2;S", "note": "印字は B2,S (S に下線．B2 の 2 は白抜きの字)"}
        self.assertEqual(to_csv.cell_layer(row, "1"), "B2")
        self.assertEqual(to_csv.cell_layer(dict(row, **{"1": "±+"}), "1"), "S")
        three = {"layer": "B1;B2;S", "note": "印字は B1,B2,S (B2 と S に下線)"}
        self.assertEqual(to_csv.cell_layer(three, "1"), "B1")
        # 決まらないときは複数のまま
        self.assertEqual(to_csv.cell_layer({"layer": "B2;S", "note": "印字は B2,S (両方に下線)"}, "1"), "B2;S")
        self.assertEqual(to_csv.cell_layer({"layer": "B2;S", "note": "印字は B2,S (下線の有無が読めない)"}, "1"), "B2;S")
        self.assertEqual(to_csv.cell_layer({"layer": "B2;S;K", "note": "印字は B2,S,K (S に下線)"}, "1"), "B2;K")
        # どの階層の字にも下線が無いときは後ろの階層を下線つきとみる
        none = {"layer": "B2;S", "note": "印字は B2,S (階層の字に下線なし)"}
        self.assertEqual(to_csv.cell_layer(none, "1"), "B2")
        self.assertEqual(to_csv.cell_layer(dict(none, **{"1": "±+"}), "1"), "S")

    def test_herb_layer(self):
        """階層が複数のままの草本 (着生植物でない) は K 層にする．K が候補に無い・木本・着生植物は変えない"""
        self.assertEqual(to_csv.herb_layer("Miscanthus sinensis", "S;K"), "K")
        self.assertEqual(to_csv.herb_layer("Sasa palmata", "B2;S;K"), "K")
        self.assertEqual(to_csv.herb_layer("Miscanthus sinensis", "B2;S"), "B2;S")
        self.assertEqual(to_csv.herb_layer("Kalopanax pictus", "S;K"), "S;K")
        self.assertEqual(to_csv.herb_layer("Haplopteris flexuosa", "B2;K"), "B2;K")
        self.assertEqual(to_csv.herb_layer("Miscanthus sinensis", "K"), "K")

    def test_layer_from_below(self):
        """階層の印字が無い行は，すぐ下の行の階層にする (層の位置の誤り)．階層の無い行が続くとき・下が見出しのときは
        空欄のまま，check を外して note を簡潔にする"""
        body = [
            {"kind": "sp", "s_name": "A", "layer": "", "note": "check 階層の印字が無い (常在度の列の値)"},
            {"kind": "sp", "s_name": "B", "layer": "S", "note": ""},
            {"kind": "sp", "s_name": "C", "layer": "", "note": "階層の印字は無い"},
            {"kind": "sp", "s_name": "D", "layer": "", "note": "check 階層の印字が無い"},
            {"kind": "sp", "s_name": "E", "layer": "B2;S", "note": ""},
            {"kind": "group", "s_name": "", "layer": "", "note": ""},
            {"kind": "sp", "s_name": "F", "layer": "", "note": "階層の印字なし"},
            {"kind": "group", "s_name": "", "layer": "", "note": ""},
        ]
        got = to_csv.layer_from_below(body)
        self.assertEqual([r["layer"] for r in got], ["S", "S", "", "", "B2;S", "", "", ""])
        self.assertNotIn("check", got[0]["note"])
        self.assertIn("下の行の階層 S", got[0]["note"])
        for i in (2, 3, 6):
            self.assertEqual(got[i]["note"], to_csv.NO_LAYER_NOTE)
        # 階層の欄に「-」と明記された行は，下の行の階層にせず，check も付けない
        dash = [
            {"kind": "sp", "s_name": "G", "layer": "", "note": "check 階層の印字は − (常在度の列だけに値)"},
            {"kind": "sp", "s_name": "H", "layer": "S", "note": ""},
        ]
        got = to_csv.layer_from_below(dash)
        self.assertEqual(got[0]["layer"], "")
        self.assertNotIn("check", got[0]["note"])
        self.assertIn("階層の印字は", got[0]["note"])

    def test_level_L(self):
        """方位・傾斜の L (レベル) は方位なし (-)・傾斜 0 にする．value_raw は L のまま．ほかの値は変わらない"""
        d = workdir()
        head = os.path.join(d, "transcripts", "Tab.1", "header.tsv")
        with open(head, "a", encoding="utf-8") as f:
            f.write("方位\tExposition\t\tL\tSW\t-\n")
            f.write("傾斜\tNeigung\t°\tL\t20\tL\n")
        run(to_csv.main, [d])
        got = {(r["item_ja"], r["plot"]): r for r in rows(os.path.join(d, "sites.csv"))}
        self.assertEqual(got[("方位", "1")]["value"], "-")
        self.assertEqual(got[("方位", "1")]["value_raw"], "L")
        self.assertEqual(got[("方位", "2")]["value"], "SW")
        self.assertEqual(got[("方位", "3")]["value"], "-")
        self.assertEqual(got[("傾斜", "1")]["value"], "0")
        self.assertEqual(got[("傾斜", "1")]["unit"], "°")
        self.assertEqual(got[("傾斜", "3")]["value_raw"], "L")
        self.assertEqual(got[("傾斜", "2")]["value"], "20")
        self.assertEqual(got[("傾斜", "1")]["status"], "ok")
        self.assertIn("自動変換", got[("傾斜", "1")]["note"])
        self.assertEqual(got[("傾斜", "2")]["note"], "")
        self.assertEqual(to_csv.norm_site("海抜", "Höhe", "L")[0], "L")   # 方位・傾斜のほかは変えない

    def test_check_after_other_note(self):
        """check が備考の途中 (`2: 下線; 2: check …`) にあっても status=check になる"""
        d = workdir()
        body = os.path.join(d, "transcripts", "Tab.1", "body.tsv")
        with open(body, "a", encoding="utf-8") as f:
            f.write("sp\t\t\tPinus thunbergii\tクロマツ\t\t+\t1・1\t・\t2: 下線; 2: check 下線か筋か\n")
        run(to_csv.main, [d])
        hit = {r["plot"]: r["status"] for r in rows(os.path.join(d, "composition.csv")) if r["j_name"] == "クロマツ"}
        self.assertEqual(hit, {"1": "ok", "2": "check"})


class UnderlineTest(unittest.TestCase):
    def layers(self, line):
        d = workdir()
        with open(os.path.join(d, "transcripts", "Tab.1", "body.tsv"), "a", encoding="utf-8") as f:
            f.write(line)
        run(to_csv.main, [d])
        return {r["plot"]: (r["layer"], r["cover"], r["status"])
                for r in rows(os.path.join(d, "composition.csv")) if r["j_name"] == "シュロ"}

    def test_note_marks_layer(self):
        got = self.layers("sp\t\t\tTrachycarpus fortunei\tシュロ\tS;K\t1・2\t+\t・\t2: 下線; 印字は S,K (K に下線)\n")
        self.assertEqual(got, {"1": ("S", "1", "ok"), "2": ("K", "+", "ok")})

    def test_plus_minus(self):
        got = self.layers("sp\t\t\tTrachycarpus fortunei\tシュロ\tS;K\t+\t±\t・\t印字は S,K (S に下線)\n")
        self.assertEqual(got, {"1": ("K", "+", "ok"), "2": ("S", "+", "ok")})

    def test_no_mark_stays_multi(self):
        got = self.layers("sp\t\t\tTrachycarpus fortunei\tシュロ\tS;K\t+\t・\t・\t\n")
        self.assertEqual(got["1"][2], "multi")

    def test_three_layers(self):
        got = self.layers("sp\t\t\tTrachycarpus fortunei\tシュロ\tB2;S;K\t+\t±\t・\t印字は B2,S,K (K に下線)\n")
        self.assertEqual((got["1"][0], got["1"][2], got["2"][0]), ("B2;S", "multi", "K"))


class SparseTest(unittest.TestCase):
    def test_expand(self):
        import sparse
        d = tempfile.mkdtemp()
        src = os.path.join(d, "s.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("#table Tab.7 3\ng|随伴種|Begleiter\nAaa bbb|アア|K|2:+\n||S|*+ ・ 1・2\n")
        sparse.main([src, d])
        with open(os.path.join(d, "transcripts", "Tab.007", "body.tsv"), encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[2].split("\t")[5:9], ["K", "・", "+", "・"])
        self.assertEqual(lines[3].split("\t")[5:9], ["S", "+", "・", "1・2"])

    def test_output_to_transcripts(self):
        import sparse
        d = tempfile.mkdtemp()
        src = os.path.join(d, "s.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("#table Tab.7 1\nAaa bbb|アア|K|1:+\n")
        sparse.main([src, os.path.join(d, "transcripts")])       # 置き場でなく transcripts を渡しても同じ所へ
        self.assertTrue(os.path.exists(os.path.join(d, "transcripts", "Tab.007", "body.tsv")))

    def test_plot_list(self):
        self.assertEqual(to_csv.plot_list("1,7-9"), ["1", "7", "8", "9"])
        self.assertEqual(to_csv.plot_list("in 1"), ["in 1"])


class SpeciesKeyTest(unittest.TestCase):
    def test_subsp_and_var(self):
        """subsp./ssp.・v./var.・空白の違いは同じ種として数える"""
        k = lambda s: chk.spkey({"s_name": s, "j_name": ""})
        self.assertEqual(k("Rubus rosaefolius subsp. x"), k("Rubus rosaefolius ssp. x"))
        self.assertEqual(k("Parnassia foliosa var.nummularia"), k("Parnassia foliosa v. nummularia"))
        self.assertNotEqual(k("Eurya japonica"), k("Eurya emarginata"))

    def test_japanese_spaces(self):
        """学名の無い行は和名の全角空白を除いて数える"""
        self.assertEqual(chk.spkey({"s_name": "", "j_name": "ツ　ゲ"}), "ツゲ")


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.d = workdir()
        run(to_csv.main, [self.d])

    def test_clean(self):
        rc, out = run(chk.main, [self.d])
        self.assertEqual(rc, 0, out)
        self.assertIn("一致 3・不一致 0", out)
        self.assertNotIn("出現種数の無い表", out)

    def test_count_mismatch(self):
        p = os.path.join(self.d, "transcripts", "Tab.1", "once.tsv")
        with open(p, encoding="utf-8") as f:
            text = f.read()
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(text.split("\n")[:2]) + "\n")     # 地点 3 の 1 回出現の種を落とす
        run(to_csv.main, [self.d])
        rc, out = run(chk.main, [self.d])
        self.assertEqual(rc, 1)
        self.assertIn("出現種数 3 に対し読んだ種 2", out)

    def test_heading_shifts(self):
        """1 回出現の見出しが続けて 1 つずつずれた型 (九州 Tab.085) を種数で見つける (規則 X35)"""
        body = {p: {f"b{p}_{i}" for i in range(5)} for p in range(1, 7)}
        true_once = {1: {"a"}, 2: {"b", "c"}, 3: {"d"}, 4: {"e", "f", "g"}, 5: {"h"}, 6: {"i", "j"}}
        want = {p: len(body[p] | true_once[p]) for p in body}
        printed = {p + 1 if p >= 3 else p: v for p, v in true_once.items()}   # in 3〜6 が 1 つ後ろへ (7 は表に無い)
        got = chk.heading_shifts(body, printed, want)
        self.assertEqual(got, [(4, 7, -1, [3, 4, 5, 6])])
        self.assertEqual(chk.heading_shifts(body, true_once, want), [])

    def test_once_group_and_nameless(self):
        """once.tsv の group 列は group_ja へ．名前の無い値は種に含めず nameless.tsv へ (X53)"""
        p = os.path.join(self.d, "transcripts", "Tab.1", "once.tsv")
        with open(p, encoding="utf-8") as f:
            lines = f.read().rstrip("\n").split("\n")
        head = lines[0].split("\t")
        rows = [dict(zip(head, l.split("\t"))) for l in lines[1:]]
        rows[0]["group"] = "出現 2 回の種"
        rows.append(dict(plot=rows[0]["plot"], s_name="", j_name="", layer="B2", value="1・2", note="印字は B2-1・2"))
        cols = head + ["group"]
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(["\t".join(cols)] + ["\t".join(r.get(c, "") for c in cols) for r in rows]) + "\n")
        _, out = run(to_csv.main, [self.d])
        self.assertIn("名前の無い値 1 件", out)
        with open(os.path.join(self.d, "nameless.tsv"), encoding="utf-8") as f:
            self.assertIn("1・2", f.read())
        comp = list(csv.DictReader(open(os.path.join(self.d, "composition.csv"), encoding="utf-8-sig")))
        self.assertIn("出現 2 回の種", {r["group_ja"] for r in comp if r["source"] == "once"})
        self.assertFalse([r for r in comp if not r["s_name"] and not r["j_name"]])

    def test_no_count_table(self):
        p = os.path.join(self.d, "transcripts", "Tab.1", "header.tsv")
        with open(p, encoding="utf-8") as f:
            lines = [x for x in f if "出現種数" not in x]
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(lines)
        run(to_csv.main, [self.d])
        self.assertIn("出現種数の無い表 1: Tab.1", run(chk.main, [self.d])[1])

    def test_count_without_moss(self):
        """出現種数が「蘚苔類を除く」表は，蘚苔類 (1 回出現の note「蘚苔・地衣類の段落」) を数えない"""
        p = os.path.join(self.d, "transcripts", "Tab.1", "once.tsv")
        with open(p, encoding="utf-8") as f:
            text = f.read().rstrip("\n")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text + "\n3\tBryum argenteum\tギンゴケ\t\t+\t蘚苔・地衣類の段落 (Moose u. Flechten)\n")
        run(to_csv.main, [self.d])
        self.assertIn("出現種数 3 に対し読んだ種 4", run(chk.main, [self.d])[1])     # 印字が蘚苔を数えるか分からない
        self.assertIn("一致 3・不一致 0", run(chk.main, [self.d, "--no-moss"])[1])
        h = os.path.join(self.d, "transcripts", "Tab.1", "header.tsv")
        with open(h, encoding="utf-8") as f:
            ht = f.read()
        with open(h, "w", encoding="utf-8") as f:
            f.write(ht.replace("出現種数\tArtenzahl\t", "出現種数\tArtenzahl (Ohne Moosarten)\t"))
        run(to_csv.main, [self.d])
        out = run(chk.main, [self.d])[1]
        self.assertIn("一致 3・不一致 0", out)                                  # 項目名で見分ける
        self.assertIn("種数から外した表 1: Tab.1", out)

    def _edit_csv(self, name, change):
        p = os.path.join(self.d, name)
        data = rows(p)
        change(data)
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(data)

    def test_clues(self):
        comp = [{"source": "once", "table": "T", "plot": p} for p in ("1", "2", "1")]
        out = chk.clues(comp, {"T": {5: (20, 10), 6: (10, 20), 8: (8, 14), 9: (10, 5)}})
        self.assertIn("in 1 が 1 回出現の段落の 2 か所", out[0])
        self.assertTrue(any("地点 5 と 6 の印字の種数を入れ替える" in x for x in out))
        self.assertFalse(chk.clues([], {"T": {5: (11, 10)}}))
        out = chk.clues([], {"T": {3: (12, 8), 4: (5, 9)}})
        self.assertTrue(any("見出しの欠け" in x for x in out) or any("入れ替える" in x for x in out))

    def test_presence_mark_is_valid(self):
        def mark(data):
            data[0].update(cover="O", sociability="")
        self._edit_csv("composition.csv", mark)
        self.assertNotIn("被度", run(chk.main, [self.d])[1])

    def test_plot_outside_header(self):
        def add(data):
            data.append(dict(data[-1], plot="99", source="note"))
        self._edit_csv("sites.csv", add)
        rc, out = run(chk.main, [self.d])
        self.assertEqual(rc, 1)
        self.assertIn("地点 99 は表頭に無い", out)

    def test_two_count_rows_are_summed(self):
        def split(data):
            for r in [x for x in data if "出現種数" in x["item_ja"]]:
                n = int(r["value"])
                r["value"] = str(n - 1)
                data.append(dict(r, item_ja="出現種数 (コケ植物)", value="1"))
        self._edit_csv("sites.csv", split)
        rc, out = run(chk.main, [self.d])
        self.assertEqual(rc, 0, out)
        self.assertIn("一致 3・不一致 0", out)

    def test_constancy_column_is_not_counted(self):
        def mark(data):
            for r in data:
                if r["plot"] == "1":
                    r["cover"], r["sociability"], r["constancy"] = "", "", "V"
        self._edit_csv("composition.csv", mark)
        rc, out = run(chk.main, [self.d])
        self.assertIn("常在度の列 1 列", out)
        self.assertNotIn("地点 1:", out)


class TablesTest(unittest.TestCase):
    def index(self):
        p = os.path.join(tempfile.mkdtemp(), "index.tsv")
        with open(p, "w", encoding="utf-8") as f:
            f.write("file\ttab_numbers\ttitles\tstatus\n")
            f.write("kinki_001.pdf\t4;6\t4:表題A;6:表題;B\tkeep\n")
            f.write("kinki_002.pdf\t6;8\t8:表題C\tkeep\n")
            f.write("old.pdf\t9\t9:外す\told\n")
            f.write("tohoku_001.pdf\t1\t1:別の地方\tkeep\n")
        return p

    def test_from_index(self):
        r = tables.from_index(self.index(), "kinki")
        self.assertEqual([x["table"] for x in r], ["Tab.4", "Tab.6", "Tab.8"])
        self.assertEqual(r[1]["title"], "表題;B")              # 表題の中の ; で切らない
        self.assertEqual(r[1]["page"], "kinki_001")            # 同じ番号は最初のページ

    def test_resume(self):
        d = tempfile.mkdtemp()
        run(tables.main, ["init", d, "--index", self.index(), "--prefix", "kinki"])
        run(tables.main, ["set", d, "Tab.4", "done"])
        run(tables.main, ["set", d, "Tab.8", "reading"])
        self.assertTrue(run(tables.main, ["next", d])[1].startswith("Tab.8"))   # 途中の表が先
        out = run(tables.main, ["show", d])[1]
        self.assertIn("done 1", out)
        self.assertIn("番号の抜け: 5 7", out)

    def test_init_keeps_record(self):
        d = tempfile.mkdtemp()
        run(tables.main, ["init", d, "--index", self.index(), "--prefix", "kinki"])
        with self.assertRaises(SystemExit):
            run(tables.main, ["init", d, "--index", self.index()])

    def test_add_and_unknown(self):
        d = tempfile.mkdtemp()
        run(tables.main, ["add", d, "Tab.1", "--kind", "small"])
        self.assertEqual(tables.load(d)[0]["kind"], "small")
        with self.assertRaises(SystemExit):
            run(tables.main, ["set", d, "Tab.2", "done"])

    def test_set_title_and_titles_from_meta(self):
        """一覧の表題を set --title と titles (meta.tsv の title_ja) で書き換える (0.5.11)"""
        d = tempfile.mkdtemp()
        run(tables.main, ["add", d, "Tab.21", "--title", "マサキートベラ群州"])
        run(tables.main, ["add", d, "Tab.22", "--note", "続き: s01114_p46"])
        self.assertEqual(tables.load(d)[1]["note"], "続き: s01114_p46")
        run(tables.main, ["set", d, "Tab.22", "done", "--title", "ムクノキ―エノキ群集"])
        self.assertEqual(tables.load(d)[1]["title"], "ムクノキ―エノキ群集")
        os.makedirs(os.path.join(d, "transcripts", "Tab.021"))
        with open(os.path.join(d, "transcripts", "Tab.021", "meta.tsv"), "w", encoding="utf-8") as f:
            f.write("key\tvalue\ntitle_ja\tマサキ―トベラ群集\n")
        run(tables.main, ["titles", d])
        self.assertEqual(tables.load(d)[0]["title"], "マサキ―トベラ群集")


class ImproveTest(unittest.TestCase):
    def test_add_list_set(self):
        d = tempfile.mkdtemp()
        run(improve.main, ["add", d, "--kind", "pattern", "--text", "新しい型"])
        run(improve.main, ["add", d, "--kind", "pattern", "--text", "新しい型"])    # 同じ案は増やさない
        self.assertEqual(len(improve.load(d)), 1)
        self.assertIn("1. [pattern] 新しい型", run(improve.main, ["list", d])[1])
        run(improve.main, ["set", d, "1", "applied"])
        self.assertIn("0 件", run(improve.main, ["list", d])[1])

    def test_scan_hides_real_data(self):
        d = workdir()
        with open(os.path.join(d, "transcripts", "Tab.1", "once.tsv"), "a", encoding="utf-8") as f:
            f.write("1\tAaa bbb\tアア\t\t7x\n2\tCcc ddd\tイイ\t\t8y\n3\tEee fff\tウウ\t\t9z\n")
        run(to_csv.main, [d])
        run(improve.main, ["scan", d])
        text = improve.load(d)[0]["text"]
        self.assertIn("9a", text)                             # 値は型にする
        self.assertNotIn("7x", text)
        self.assertEqual(str(improve.load(d)[0]["count"]), "3")

    def test_scan_ignores_single(self):
        d = workdir()
        with open(os.path.join(d, "transcripts", "Tab.1", "once.tsv"), "a", encoding="utf-8") as f:
            f.write("1\tAaa bbb\tアア\t\t7x\n")
        run(to_csv.main, [d])
        self.assertEqual(improve.scan(d), [])


class SpeciesTest(unittest.TestCase):
    def test_check(self):
        import check_species as cs
        idx = {"v": 1, "hub": {"アキグミ": {"family": "", "family_jp": "グミ", "status": ""}},
               "alias": {"アキグミ": ["アキグミ"]}, "latin": {"アキグミ": {"GL": "Elaeagnus umbellata"}}}
        got = cs.check([{"j_name": "アキグミ", "s_name": "Elaeagnus umbellata"},
                        {"j_name": "アキグミ", "s_name": "Elaeagnus umbellata"},
                        {"j_name": "アキグミ", "s_name": "Vitex rotundifolia"},
                        {"j_name": "ゼンゼンチガウ", "s_name": ""}], idx)
        self.assertEqual(got[0]["status"], "none")             # 怪しい行が先
        ok = {r["s_name"]: r for r in got if r["status"] == "ok"}
        self.assertEqual(ok["Elaeagnus umbellata"]["count"], 2)
        self.assertEqual(ok["Elaeagnus umbellata"]["same_genus"], "1")
        self.assertEqual(ok["Vitex rotundifolia"]["same_genus"], "0")


class ReviewTest(unittest.TestCase):
    def setUp(self):
        try:
            import review
        except ImportError:
            self.skipTest("Pillow が無い")
        self.review = review
        self.d = tempfile.mkdtemp()
        tdir = os.path.join(self.d, "transcripts", "Tab.007")
        os.makedirs(tdir)
        with open(os.path.join(tdir, "body.tsv"), "w", encoding="utf-8", newline="") as f:
            f.write("kind\tgroup_ja\tgroup_de\ts_name\tj_name\tlayer\t1\tnote\n")
            f.write("sp\t\t\tAaa bbb\tアイウ\tK\t+\t\nsp\t\t\tCcc ddd\tアイウエ\tK\t+\t\n")
        with open(os.path.join(tdir, "once.tsv"), "w", encoding="utf-8", newline="") as f:
            f.write("plot\ts_name\tj_name\tlayer\tvalue\tnote\n1\tAaa bbb\tアイウ\tK\t+\t\n")
        with open(os.path.join(tdir, "sparse.txt"), "w", encoding="utf-8", newline="") as f:
            f.write("#table Tab.7 1\ng|アイウ|x\nAaa bbb|アイウ|K|1:+\n")
        self.src = os.path.join(self.d, "in.tsv")
        with open(self.src, "w", encoding="utf-8", newline="") as f:
            f.write("table\tfield\tcurrent\tcandidates\tpage\tx0\ty0\tx1\ty1\tnote\n")
            f.write("Tab.7\tj_name\tアイウ\tアイオ;アイカ\tp.png\t0\t0\t100\t50\t濁点\n")
            f.write("Tab.7\tj_name\tアイウ\t\tp.png\t0\t0\t100\t50\t\n")      # 同じ項目は足さない
            f.write("Tab.7\tlayer\tK\t\tp.png\t0\t0\t100\t50\t\n")

    def test_import_and_save(self):
        self.assertEqual(self.review.import_rows(self.d, self.src), (2, 2))
        self.assertEqual(self.review.import_rows(self.d, self.src), (0, 2))
        self.review.save_row(self.d, {"id": 1, "answer": " アイオ\t", "memo": "", "state": "fix"})
        row = self.review.read_queue(self.d)[0]
        self.assertEqual((row["answer"], row["state"], row["candidates"]), ("アイオ", "fix", "アイオ;アイカ"))
        with self.assertRaises(ValueError):
            self.review.save_row(self.d, {"id": 1, "state": "wrong"})
        with self.assertRaises(LookupError):
            self.review.save_row(self.d, {"id": 9, "state": "ok"})

    def test_apply_only_exact_names(self):
        self.review.import_rows(self.d, self.src)
        self.review.save_row(self.d, {"id": 1, "answer": "アイオ", "state": "fix"})
        self.review.save_row(self.d, {"id": 2, "answer": "S", "state": "fix"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.review.apply_rows(self.d), (1, 0, 1))
        self.assertIn("[手で直す]", out.getvalue())
        tdir = os.path.join(self.d, "transcripts", "Tab.007")
        with open(os.path.join(tdir, "body.tsv"), encoding="utf-8") as f:
            body = f.read()
        self.assertIn("Aaa bbb\tアイオ\t", body)
        self.assertIn("Ccc ddd\tアイウエ\t", body)                  # 語の一部は直さない
        with open(os.path.join(tdir, "once.tsv"), encoding="utf-8") as f:
            self.assertIn("アイオ", f.read())
        with open(os.path.join(tdir, "sparse.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Aaa bbb|アイオ|K|1:+", text)
        self.assertIn("g|アイウ|x", text)                           # 見出しは直さない
        self.assertEqual(self.review.read_queue(self.d)[0]["state"], "applied")

    def test_render_and_move(self):
        from PIL import Image
        Image.new("L", (400, 400), "white").save(os.path.join(self.d, "p.png"))
        self.review.import_rows(self.d, self.src)
        row = self.review.read_queue(self.d)[0]
        pages = self.review.Pages(self.d)
        self.assertTrue(self.review.render(pages, row).startswith(b"\x89PNG"))
        self.assertTrue(self.review.render(pages, row, dy=100).startswith(b"\x89PNG"))


class ImageTest(unittest.TestCase):
    def setUp(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow が無い")
        self.Image = Image

    def test_zoom(self):
        import crop
        im = self.Image.new("RGB", (1000, 1000), "white")
        self.assertEqual(crop.ruled(im, (0, 0, 200, 100))[1], 1.0)
        out, scale = crop.ruled(im, (0, 0, 200, 100), zoom=2)
        self.assertEqual(scale, 2)
        self.assertEqual(out.width, 400 + 2 * crop.MARGIN_X)
        self.assertLess(crop.ruled(im, (0, 0, 1000, 1000), maxside=900, zoom=3)[1], 1)   # --max は超えない

    def test_shear_estimate(self):
        import crop
        from PIL import ImageDraw
        im = self.Image.new("L", (800, 400), "white")
        d = ImageDraw.Draw(im)
        for y in range(40, 360, 40):                           # 右へ 24 px 下がる行
            for x in range(0, 800, 10):
                d.rectangle((x, y + x * 24 // 800, x + 4, y + x * 24 // 800 + 4), fill="black")
        self.assertLessEqual(abs(crop.estimate_shear(im) - 24), 4)
        self.assertLessEqual(abs(crop.estimate_shear(im, 16, 4, 28) - 24), 4)      # 帯ごとは近くだけを探す
        self.assertLessEqual(abs(crop.estimate_shear(im, 8, 4, -40) + 40), 8)      # 範囲の外へは出ない

    def test_dense(self):
        import crop
        d = tempfile.mkdtemp()
        src = os.path.join(d, "t.png")
        self.Image.new("RGB", (1000, 600), "white").save(src)
        run(crop.main, [src, "--box", "400", "0", "1000", "600", "--pad", "0", "--dense", "10", "--plots", "20",
                        "--label", "0", "390", "--tiles", "2x1", "--shear", "0", "--out", d, "--name", "x"])
        self.assertTrue(os.path.exists(os.path.join(d, "x_r2_p11-20.png")))

    def test_dense_label_stops_at_first_column(self):
        import crop
        d = tempfile.mkdtemp()
        src = os.path.join(d, "t.png")
        self.Image.new("RGB", (1000, 600), "white").save(src)       # 字が無いので等分に戻る
        _, out = run(crop.main, [src, "--box", "400", "0", "1000", "600", "--pad", "0", "--dense", "10", "--plots", "10",
                                 "--label", "0", "450", "--shear", "0", "--out", d, "--name", "x"])
        self.assertIn("x=400 で止めた", out)

    def test_dense_tile_keeps_value_heads(self):
        import crop
        im = self.Image.new("RGB", (1000, 100), "white")
        edges = [100 + i * 50 for i in range(21)]
        whole = crop.dense_tile(im, edges, (0, 90), 11, 20, (0, 100)).width
        self.assertEqual(whole, 90 + 12 + 10 * 50 + 1 + 10)         # 左だけ 2 割広い
        first = crop.dense_tile(im, edges, (0, 90), 1, 10, (0, 100)).width
        self.assertEqual(first, 90 + 12 + 10 * 50 + 1 + 10)         # 右だけ 2 割広い

    def _dots(self, pitch=60, n=10, left=100):
        from PIL import ImageDraw
        im = self.Image.new("L", (800, 600), "white")
        d = ImageDraw.Draw(im)
        d.line([(40, 0), (40, 600)], fill=0, width=2)          # 階層の右の罫線
        d.line([(left + n * pitch, 0), (left + n * pitch, 600)], fill=0, width=2)
        for y in range(20, 590, 30):
            for i in range(n):
                x = left + i * pitch
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=0)
        return im

    def test_measure_columns(self):
        import crop
        centers, _ = crop.measure_columns(self._dots(), 10)
        self.assertLessEqual(abs(centers[0] - 100), 3)
        self.assertLessEqual(abs(centers[-1] - 640), 3)

    def test_measure_columns_wrong_count(self):
        import crop
        self.assertIsNone(crop.measure_columns(self._dots(), 9)[0])          # 地点の数が違えば測らない
        self.assertIsNone(crop.measure_columns(self.Image.new("L", (800, 600), "white"), 10)[0])

    def test_dense_given_columns_and_warnings(self):
        """--centers・--first-x/--pitch で列を渡す．右端の列のはみ出しと --raw の --tiles を警告する (0.5.34)"""
        import crop
        d = tempfile.mkdtemp()
        src = os.path.join(d, "t.png")
        self.Image.new("RGB", (1000, 600), "white").save(src)
        cs = ["430", "470", "510", "590", "630", "670"]                 # 群の境で間隔が広がる
        _, out = run(crop.main, [src, "--box", "400", "0", "700", "600", "--pad", "0", "--dense", "6", "--plots", "6",
                                 "--label", "0", "390", "--shear", "0", "--centers", *cs, "--out", d, "--name", "c"])
        self.assertIn("列は引数のとおり: 第 1 列の中心 x=430", out)
        self.assertNotIn("列を測れなかった", out)
        self.assertNotIn("最後の列の右の境", out)
        _, out = run(crop.main, [src, "--box", "400", "0", "700", "600", "--pad", "0", "--dense", "6", "--plots", "6",
                                 "--label", "0", "390", "--shear", "0", "--first-x", "450", "--pitch", "50",
                                 "--out", d, "--name", "p"])
        self.assertIn("最後の列の右の境", out)                         # 最後の列 (x 700) の右が切り出しの外
        _, out = run(crop.main, [src, "--box", "0", "0", "100", "100", "--raw", "--tiles", "3x1", "--out", d, "--name", "r"])
        self.assertIn("--raw は --tiles", out)

    def test_dense_ignores_pad_when_dividing(self):
        import crop, contextlib, io
        d = tempfile.mkdtemp()
        src = os.path.join(d, "t.png")
        self.Image.new("RGB", (1000, 600), "white").save(src)       # 字が無いので等分に戻る
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            crop.main([src, "--box", "400", "100", "900", "500", "--dense", "10", "--plots", "10",
                       "--label", "0", "390", "--shear", "0", "--out", d, "--name", "x"])
        self.assertIn("列を測れなかった", out.getvalue())
        tile = self.Image.open(os.path.join(d, "x_r1_p01-10.png"))
        self.assertLess(tile.width, 1040 + 2 * crop.MARGIN_X)       # --pad を足すと 660 px になる

    def _cells(self, d, wrong):
        """点の表 (3 行 x 10 地点) と，地点 3 の値を地点 wrong に書いた転記を作る"""
        from PIL import ImageDraw
        im = self.Image.new("L", (800, 300), "white")
        draw = ImageDraw.Draw(im)
        draw.line([(40, 0), (40, 300)], fill=0, width=2)
        for r, y in enumerate((60, 120, 180)):
            draw.rectangle((10, y - 8, 25, y + 8), fill=0)                 # 階層の字
            for i in range(10):
                x = 100 + i * 60
                if r == 1 and i == 2:
                    draw.rectangle((x - 12, y - 3, x + 12, y + 3), fill=0)  # 値
                    draw.rectangle((x - 3, y - 12, x + 3, y + 12), fill=0)
                else:
                    draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=0)
        src = os.path.join(d, "t.png")
        im.save(src)
        body = os.path.join(d, "transcripts", "Tab.001")
        os.makedirs(body)
        plots = [str(i) for i in range(1, 11)]
        with open(os.path.join(body, "body.tsv"), "w", encoding="utf-8", newline="") as f:
            f.write("\t".join(["kind", "group_ja", "group_de", "s_name", "j_name", "layer"] + plots + ["note"]) + "\n")
            for r in range(3):
                cells = ["・"] * 10
                if r == 1:
                    cells[wrong - 1] = "+"
                f.write("\t".join(["sp", "", "", "A b", "ナ%d" % r, "K"] + cells + [""]) + "\n")
        return src

    def _check_cells(self, wrong, *extra):
        import check_cells, contextlib, io
        d = tempfile.mkdtemp()
        src = self._cells(d, wrong)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            check_cells.main([src, d, "Tab.1", "--box", "50", "30", "790", "210", "--layer", "5", "30",
                              "--shear", "0", "--wmin", "13", *extra])
        return out.getvalue()

    def test_check_cells_lists_image_only(self):
        self.assertIn("[画像だけ] ナ1 K: 地点 3 (x=220 y=120)", self._check_cells(4, "--extra"))
        self.assertNotIn("[画像だけ]", self._check_cells(3, "--extra"))

    def test_check_cells_finds_neighbour(self):
        self.assertIn("地点 4 の値は地点 3", self._check_cells(4))

    def test_check_cells_clean(self):
        self.assertIn("候補 0 件", self._check_cells(3))

    def _grid(self):
        try:
            import check_grid
        except (ImportError, SystemExit):
            self.skipTest("numpy と scipy が無い")
        return check_grid

    def test_grid_match_rows_skips_extra_row(self):
        check_grid = self._grid()
        typed = [["d", "v"], ["v", "d"]]
        image = [["d", "x", "v"], ["v", "x", "d"]]                  # [列][行]．真ん中の行は転記に無い
        self.assertEqual(check_grid.match_rows(typed, image), [(0, 0), (1, 2)])

    def test_grid_cell_type(self):
        check_grid = self._grid()
        dot = (0, 0, 8, 8, 40)
        is_dot = lambda q: q[2] <= 12 and q[3] <= 9
        self.assertEqual(check_grid.cell_type([], is_dot, 26), "x")
        self.assertEqual(check_grid.cell_type([dot], is_dot, 26), "d")
        self.assertEqual(check_grid.cell_type([(0, 0, 20, 20, 90)], is_dot, 26), "v")
        self.assertEqual(check_grid.cell_type([(0, 0, 12, 20, 60), (24, 0, 12, 20, 60)], is_dot, 26), "c")

    def test_grid_finds_wrong_column(self):
        check_grid = self._grid()
        from PIL import ImageDraw
        d = tempfile.mkdtemp()
        im = self.Image.new("L", (500, 900), "white")
        draw = ImageDraw.Draw(im)
        for r in range(40):
            y = 40 + r * 20
            for c in range(8):
                x = 60 + c * 50
                if r == 10 and c == 2:
                    draw.rectangle((x - 9, y - 1, x + 9, y + 1), fill=0)   # 値
                    draw.rectangle((x - 1, y - 8, x + 1, y + 8), fill=0)
                else:
                    draw.ellipse((x - 4, y - 3, x + 4, y + 3), fill=0)
        src = os.path.join(d, "t.png")
        im.save(src)
        body = os.path.join(d, "transcripts", "Tab.001")
        os.makedirs(body)
        with open(os.path.join(body, "body.tsv"), "w", encoding="utf-8", newline="") as f:
            f.write("\t".join(["kind", "group_ja", "group_de", "s_name", "j_name", "layer"]
                              + [str(i) for i in range(1, 9)] + ["note"]) + "\n")
            for r in range(40):
                cells = ["・"] * 8
                if r == 10:
                    cells[3] = "+"                                  # 隣の地点に書いた
                f.write("\t".join(["sp", "", "", "A b", "ナ%d" % r, "K"] + cells + [""]) + "\n")
        _, out = run(check_grid.main, [src, d, "Tab.1", "--box", "30", "20", "480", "840"])
        self.assertIn("対応した行 40", out)
        self.assertIn("ナ10 K: 地点 3 転記 d・画像 v", out)
        self.assertIn("ナ10 K: 地点 4 転記 v・画像 d", out)

    def _mg(self):
        try:
            import marks_grid
        except (ImportError, SystemExit):
            self.skipTest("numpy と scipy が無い")
        return marks_grid

    def test_marks_link_skips_dirt_and_gap(self):
        mg = self._mg()
        ref = [100 + 20 * k for k in range(10)]
        ms = [y + 3 for y in ref]
        ms.insert(5, ref[4] + 12)                                   # 行の間のよごれ
        del ms[8]                                                   # 印の無いセル (ref の 7 行目)
        asg, extra = mg.link(ms, ref, 20)
        self.assertEqual(extra, [5])
        self.assertEqual(asg[7], -1)
        self.assertEqual(asg[:5], [0, 1, 2, 3, 4])

    def test_marks_regular_columns_ignore_frame(self):
        """点線の枠の破線が列の間に山を作っても，等間隔の当てはめで列を取る (0.5.14．近畿 Tab.061)"""
        mg = self._mg()
        import numpy as np
        cols = [1318 + 79 * c for c in range(11)]
        xs = [x for c, x in enumerate(cols) for _ in range(2 if c == 9 else 15)]   # 列 10 は点が少ない
        xs += [1594] * 30                                                         # 枠の破線
        base, how = mg.pick_columns(np.array(xs, float), 11, 1270, 2160)
        self.assertIn("等間隔", how)
        self.assertTrue(all(abs(b - c) <= 2 for b, c in zip(base, cols)), base)

    def test_marks_split_groups(self):
        """1 つの印字の行を階層ごとに分けた転記を見つけ，1 行にまとめる (0.5.33)"""
        mg = self._mg()
        layers = ["K", "B1", "S", "K", "S", "S", "K"]
        notes = ["", "印字は B1,S,K (B1 に二重下線・K に一重下線)", "\x00", "\x00印字は B1,S,K", "", "印字は S,K", "\x00"]
        groups = mg.split_groups(layers, notes)
        self.assertEqual(groups, [[1, 2, 3], [5, 6]])
        self.assertEqual(mg.split_groups(layers, notes, [[0, 1]])[0], [0, 1])       # 手で渡す組は先に取る
        names = ["a K", "b B1", "b S", "b K", "c S", "d S", "d K"]
        vals = [["+", "・"], ["1・1", "・"], ["・", "+"], ["・", "・"], ["+", "+"], ["・", "・"], ["・", "2・2"]]
        n2, v2, src = mg.merge_split(names, vals, groups)
        self.assertEqual(len(v2), 4)
        self.assertEqual(v2[1], ["1・1", "+"])
        self.assertEqual(src[1], [1, 2, 3])
        self.assertIn("+2 行", n2[1])
        self.assertEqual(v2[3], ["・", "2・2"])

    def test_marks_grid_shear(self):
        """--shear で右下がりの行の傾きを補正して格子を作る (0.5.33)"""
        mg = self._mg()
        from PIL import ImageDraw
        d = tempfile.mkdtemp()
        xs = [60 + 40 * c for c in range(14)]
        im = self.Image.new("L", (700, 700), "white")
        draw = ImageDraw.Draw(im)
        value = {(3, 2), (7, 12), (15, 13)}
        for r in range(25):
            for c, x in enumerate(xs):
                y = 50 + r * 22 + 2.2 * c                                   # 右端で約 29 px 下がる (行の間隔 22)
                if (r, c) in value:
                    draw.rectangle((x - 6, y - 1, x + 6, y + 1), fill=0)
                    draw.rectangle((x - 1, y - 6, x + 1, y + 6), fill=0)
                else:
                    draw.ellipse((x - 4, y - 3, x + 4, y + 3), fill=0)
        src = os.path.join(d, "t.png")
        im.save(src)
        body = os.path.join(d, "transcripts", "Tab.001")
        os.makedirs(body)
        with open(os.path.join(body, "body.tsv"), "w", encoding="utf-8", newline="") as f:
            f.write("\t".join(["kind", "group_ja", "group_de", "s_name", "j_name", "layer"]
                              + [str(i) for i in range(1, 15)] + ["note"]) + "\n")
            for r in range(25):
                cells = ["+" if (r, c) in value else "・" for c in range(14)]
                f.write("\t".join(["sp", "", "", "A b", "ナ%d" % r, "K"] + cells + [""]) + "\n")
        _, out = run(mg.main, [src, d, "Tab.1", "--box", "35", "30", "640", "640", "--shear", "28.6"])
        self.assertIn("行の傾きを補正した", out)
        self.assertIn("画像の行 25", out)
        self.assertIn("食い違い 0 セル", out)

    def test_marks_const_columns(self):
        mg = self._mg()
        vals = [["+", "V(1-2)", "・"], ["・", "+(+)", "1・2"], ["2・2", "・", "・"]]
        self.assertEqual(mg.const_columns(vals), {1})

    def test_marks_grid_uneven_shifted_ruled(self):
        mg = self._mg()
        from PIL import ImageDraw
        d = tempfile.mkdtemp()
        xs = [60, 100, 160, 200, 240, 300, 380, 420, 460, 520, 560, 600]   # 不等間隔．列 6 は常在度
        im = self.Image.new("L", (680, 960), "white")
        draw = ImageDraw.Draw(im)
        draw.rectangle((30, 20, 650, 900), outline=0, width=3)             # 枠
        draw.line([(338, 20), (338, 900)], fill=0, width=2)                # 列の間の罫線
        draw.line([(30, 38), (650, 38)], fill=0, width=2)                  # 横の罫線
        for x in range(30, 650, 14):
            draw.line([(x, 880), (x + 7, 880)], fill=0, width=2)           # 横の破線

        def cross(x, y):
            draw.rectangle((x - 6, y - 1, x + 6, y + 1), fill=0)
            draw.rectangle((x - 1, y - 6, x + 1, y + 6), fill=0)

        value = {(10, 2), (12, 5), (20, 7), (25, 0)}
        for r in range(40):
            for c, x in enumerate(xs):
                y = 50 + r * 20 + c + c * r / 40                            # 右ほど・下ほど行が下がる (最大 22 px)
                if (r, c) == (30, 8):
                    continue                                                # 印の無いセル
                if (r, c) in value:
                    cross(x, y)
                elif c == 5 and r % 3 == 0:
                    cross(x, y)
                    draw.rectangle((x + 12, y - 6, x + 19, y + 6), fill=0)  # 常在度の値は右へ伸びる
                    draw.rectangle((x + 24, y - 6, x + 31, y + 6), fill=0)
                else:
                    draw.ellipse((x - 4, y - 3, x + 4, y + 3), fill=0)
        draw.ellipse((216, 50 + 15 * 20 + 13, 224, 50 + 15 * 20 + 19), fill=0)  # 列 5 の行の間のよごれ
        src = os.path.join(d, "t.png")
        im.save(src)
        body = os.path.join(d, "transcripts", "Tab.001")
        os.makedirs(body)
        with open(os.path.join(body, "body.tsv"), "w", encoding="utf-8", newline="") as f:
            f.write("\t".join(["kind", "group_ja", "group_de", "s_name", "j_name", "layer"]
                              + [str(i) for i in range(1, 13)] + ["note"]) + "\n")
            for r in range(40):
                cells = ["・"] * 12
                for (rr, c) in value:
                    if rr == r:
                        cells[c] = "+"
                if r % 3 == 0:
                    cells[5] = "II(+-1)"
                if r == 10:
                    cells[2] = "・"                                         # 読み落とし
                if r == 20:
                    cells[7] = "・"                                         # 値を 1 行下に書いた
                if r == 21:
                    cells[7] = "+"
                f.write("\t".join(["sp", "", "", "A b", "ナ%d" % r, "K"] + cells + [""]) + "\n")
        png = os.path.join(d, "diff.png")
        band = os.path.join(d, "band.png")
        _, out = run(mg.main, [src, d, "Tab.1", "--box", "35", "25", "645", "895", "--diff-png", png,
                               "--band", "1", "10", "--band-png", band])
        self.assertIn("常在度の列: 6", out)
        self.assertIn("画像の行 40", out)
        self.assertIn("対応した行 40", out)
        self.assertIn("[画像に値] ナ10 K: 地点 3", out)
        self.assertIn("[画像に値] ナ20 K: 地点 8", out)
        self.assertIn("[転記に値] ナ21 K: 地点 8 転記 +・画像は点", out)
        self.assertIn("食い違い 3 セル", out)
        self.assertTrue(os.path.exists(png))
        self.assertTrue(os.path.exists(band))
        with open(os.path.join(body, "body.tsv"), "w", encoding="utf-8", newline="") as f:   # 読む前 (見出しだけ)
            f.write("\t".join(["kind", "group_ja", "group_de", "s_name", "j_name", "layer"]
                              + [str(i) for i in range(1, 13)] + ["note"]) + "\n")
        os.remove(band)
        _, out = run(mg.main, [src, d, "Tab.1", "--box", "35", "25", "645", "895", "--band", "1", "10", "--band-png", band])
        self.assertIn("画像の行 40", out)
        self.assertTrue(os.path.exists(band))

    def test_dense_has_no_full_lines(self):
        import crop
        im = self.Image.new("RGB", (1000, 100), "white")
        edges = [100 + i * 50 for i in range(11)]
        tile = crop.dense_tile(im, edges, (0, 90), 1, 10, (0, 100))
        self.assertEqual(tile.getpixel((102, 80)), (255, 255, 255))         # 値の高さに線を引かない
        full = crop.dense_tile(im, edges, (0, 90), 1, 10, (0, 100), lines=True)
        self.assertNotEqual(full.getpixel((102, 80)), (255, 255, 255))

    def test_find_rows_ignores_rule(self):
        import check_cells
        from PIL import ImageDraw
        im = self.Image.new("L", (60, 300), "white")
        draw = ImageDraw.Draw(im)
        draw.line([(40, 0), (40, 300)], fill=0, width=2)            # 階層の範囲に掛かる罫線
        for y in (60, 120, 180):
            draw.rectangle((10, y - 8, 25, y + 8), fill=0)
        self.assertEqual(len(check_cells.find_rows(im)[0]), 3)

    def test_find_rows_by_values(self):
        import check_cells
        bw = self._dots().point(lambda v: 255 if v < 128 else 0)    # 19 行 x 10 地点 (両端に罫線)
        centers = [100 + i * 60 for i in range(10)]
        self.assertEqual(len(check_cells.find_rows_by_values(bw, centers, 18)[0]), 19)

    def test_find_rows_fills_gap(self):
        import check_cells
        from PIL import ImageDraw
        bw = self._dots().point(lambda v: 255 if v < 128 else 0)
        ImageDraw.Draw(bw).rectangle((50, 134, 700, 146), fill=0)   # 1 行分の字が消えた
        centers = [100 + i * 60 for i in range(10)]
        self.assertEqual(len(check_cells.find_rows_by_values(bw, centers, 18)[0]), 19)

    def test_row_shifts(self):
        import check_cells
        typed = [[False] * 10 for _ in range(3)]
        seen = [[False] * 10 for _ in range(3)]
        typed[1][2] = typed[1][3] = True
        seen[0][2] = seen[0][3] = True                              # 画像では 1 行上にある
        self.assertEqual(check_cells.row_shifts(typed, seen), [(1, 0, -1)])
        seen = [row[:] for row in typed]
        self.assertEqual(check_cells.row_shifts(typed, seen), [])

    def test_shear_bands_keeps_size(self):
        import crop
        im = self.Image.new("L", (300, 240), "white")
        self.assertEqual(crop.shear_bands(im, 8, bands=4).size, im.size)

    def test_parse_pages(self):
        import pages
        self.assertEqual(pages.parse_pages("2-4,7"), {2, 3, 4, 7})
        self.assertIsNone(pages.parse_pages(""))

    def test_contact(self):
        import pages
        d = tempfile.mkdtemp()
        for i in range(13):
            self.Image.new("RGB", (300, 400), "white").save(os.path.join(d, "p%02d.png" % i))
        src = [os.path.join(d, "p%02d.png" % i) for i in range(13)]
        out = os.path.join(d, "work")
        run(pages.main, src + ["--out", out])
        self.assertTrue(os.path.exists(os.path.join(out, "contact_02.png")))    # 12 コマで次の 1 枚へ
        self.assertFalse(os.path.exists(os.path.join(out, "contact_03.png")))

    def test_pdf_rotation(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("PyMuPDF が無い")
        import pages
        d = tempfile.mkdtemp()
        png = os.path.join(d, "a.png")
        self.Image.new("RGB", (200, 100), "white").save(png)
        doc = pymupdf.open()
        p = doc.new_page(width=200, height=100)
        p.insert_image(p.rect, filename=png)
        p.set_rotation(90)
        doc.new_page(width=100, height=100).insert_text((10, 50), "text page")
        doc.save(os.path.join(d, "b.pdf"))
        got = list(pages.pdf_pages(os.path.join(d, "b.pdf"), {1}))
        self.assertEqual((got[0][0], got[0][1]), (1, 2))
        self.assertEqual(got[0][2].size, (100, 200))           # ページの回転を画像にも当てる


class MergeTablesTest(unittest.TestCase):
    """並行して読んだ表の作業場所 scratch/tNNN/ を共有のファイルへ取り込む (merge_tables.py)"""

    def test_merge_one(self):
        import merge_tables as MT
        out = tempfile.mkdtemp()
        w = os.path.join(out, "scratch", "t005")
        os.makedirs(os.path.join(w, "out", "transcripts", "Tab.005"))
        with open(os.path.join(w, "out", "transcripts", "Tab.005", "meta.tsv"), "w", encoding="utf-8") as f:
            f.write("key\tvalue\n")
        with open(os.path.join(w, "status.tsv"), "w", encoding="utf-8") as f:
            f.write("Tab.005\tdone\t印字の表題\t結果の要約\n")
        with open(os.path.join(w, "log.md"), "w", encoding="utf-8") as f:
            f.write("## Tab.005 印字の表題\n- 読んだ\n")
        with open(os.path.join(w, "user_review.tsv"), "w", encoding="utf-8") as f:
            f.write("table\tplot\tj_name\tkind\twhat\tpage\tx0\ty0\tx1\ty1\tnames_x0\tnames_x1\textra\n")
            f.write("Tab.5\t3\tヨシ\tA. 読めない値\tかすれ\tp001\t1\t2\t3\t4\t10\t20\tx\n")
        with open(os.path.join(out, "user_review.tsv"), "w", encoding="utf-8") as f:
            f.write("table\tplot\tj_name\tkind\twhat\tpage\tx0\ty0\tx1\ty1\n")
            f.write("Tab.2\t1\tススキ\tA. 読めない値\t前の項目\tp001\t5\t6\t7\t8\n")
        with contextlib.redirect_stdout(io.StringIO()):
            got = MT.merge_one(out, "Tab.005", run_tables=False)
            again = MT.merge_one(out, "Tab.005", run_tables=False)
        self.assertEqual(got, ("done", 1))
        self.assertIsNone(again)                                   # 二度は取り込まない
        self.assertTrue(os.path.exists(os.path.join(out, "transcripts", "Tab.005", "meta.tsv")))
        with open(os.path.join(out, "user_review.tsv"), encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        self.assertEqual([r["table"] for r in rows], ["Tab.2", "Tab.5"])
        self.assertEqual(rows[1]["names_x0"], "10")                # 列は名前で合わせる
        self.assertNotIn("extra", rows[1])
        with open(os.path.join(out, "reading_log.md"), encoding="utf-8") as f:
            self.assertIn("## Tab.005", f.read())


class ReferenceInfoTest(unittest.TestCase):
    def test_reference_info(self):
        import review_html as R
        d = tempfile.mkdtemp()
        t = os.path.join(d, "transcripts", "Tab.007")
        os.makedirs(t)
        files = {
            "meta.tsv": ["key\tvalue", "title_ja\tスギ植林"],
            "header.tsv": ["item_ja\titem_de\tunit\t1\t2\t3\t4", "高木第1層植被率\t\t%\t90\t15\t80\t85"],
            "notes.tsv": ["plot\titem_ja\titem_de\tvalue\tunit\tvalue_raw\tstatus\tnote", "1-3\t調査地\t\tA村\t\t\tok\t"],
            "body.tsv": ["kind\tgroup_ja\tgroup_de\ts_name\tj_name\tlayer\t1\t2\t3\t4\tnote",
                         "sp\t\t\tC\tスギ\tB1\t5・5\t4・4\t+\t・\t",
                         "sp\t\t\tD\tヒノキ\tB1\t1・1\t・\t3・3\t・\t",
                         "sp\t\t\tE\tツタ\tS;K\t5・5\t5・5\t5・5\t5・5\t"],
        }
        for k, v in files.items():
            with open(os.path.join(t, k), "w", encoding="utf-8") as f:
                f.write("\n".join(v) + "\n")
        r = R.reference_info(d, "Tab.7", [2])
        self.assertEqual(r["title"], "スギ植林")
        self.assertEqual(r["cols"], [1, 2, 3])                     # 前後 1 地点ずつ
        rows = {x[0]: x[1:] for x in r["rows"]}
        self.assertEqual(rows["高木第1層植被率"], ["90", "15", "80"])
        self.assertEqual(rows["調査地"], ["A村", "A村", "A村"])
        self.assertEqual(rows["優占 (B1)"], ["スギ 5・5", "スギ 4・4", "ヒノキ 3・3"])
        self.assertNotIn("優占 (S;K)", rows)                      # 2 階層の行は数えない
        self.assertIsNone(R.reference_info(d, "Tab.8", [2]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
