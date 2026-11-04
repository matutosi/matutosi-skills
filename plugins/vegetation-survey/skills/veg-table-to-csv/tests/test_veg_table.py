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
        self.assertEqual(to_csv.parse_value("+(4-5)", 5)[:3], ("4-5", "", "+"))   # 常在度の列では常在度
        self.assertEqual(to_csv.parse_value("+(4-5)")[:3], ("+", "4-5", ""))      # 地点の列では群度の範囲
        self.assertEqual(to_csv.parse_value("+")[:3], ("+", "1", ""))      # 地点の列は被度
        self.assertEqual(to_csv.parse_value("2(3-4)")[:3], ("2", "3-4", ""))    # 調査区数が無ければ今までどおり

    def test_plots_per_column(self):
        self.assertEqual(to_csv.plots_per_column([{"item_ja": "調査区数", "item_de": "", "1": "3", "2": "12", "note": ""}]),
                         {"1": 3, "2": 12})
        self.assertEqual(to_csv.plots_per_column([{"item_ja": "調査番号;調査区数", "item_de": "", "1": "6"}]), {})

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

    def test_no_count_table(self):
        p = os.path.join(self.d, "transcripts", "Tab.1", "header.tsv")
        with open(p, encoding="utf-8") as f:
            lines = [x for x in f if "出現種数" not in x]
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(lines)
        run(to_csv.main, [self.d])
        self.assertIn("出現種数の無い表 1: Tab.1", run(chk.main, [self.d])[1])

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
