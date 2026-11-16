"""veg-table-to-csv2 のテスト (標準ライブラリだけで動く)

    python tests/test_csv2.py
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

import common  # noqa: E402
import decide  # noqa: E402
import freeze  # noqa: E402
import rules  # noqa: E402

EXAMPLE = os.path.join(HERE, "..", "..", "..", "examples", "table", "transcripts")


def run(fn, argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = fn(argv)
    return rc, out.getvalue()


def rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path, lines):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join("\t".join(l) for l in lines) + "\n")


def make(header, body, once=(), notes=(), name="Tab.001"):
    """置き場を作って返す．header・body は見出しの行を含む行のリスト"""
    d = tempfile.mkdtemp()
    t = os.path.join(d, "transcripts", name)
    os.makedirs(t)
    write(os.path.join(t, "meta.tsv"), [["key", "value"], ["file", "x_001"], ["table", "Tab.1"]])
    write(os.path.join(t, "header.tsv"), header)
    write(os.path.join(t, "body.tsv"), body)
    write(os.path.join(t, "once.tsv"), [["plot", "s_name", "j_name", "layer", "value", "note"]] + list(once))
    write(os.path.join(t, "notes.tsv"),
          [["plot", "item_ja", "item_de", "value", "unit", "value_raw", "status", "note"]] + list(notes))
    return d


HEAD3 = ["item_ja", "item_de", "unit", "1", "2", "3", "note"]
BODY3 = ["kind", "group_ja", "group_de", "s_name", "j_name", "layer", "1", "2", "3", "note"]


class FreezeTest(unittest.TestCase):
    def test_freeze_and_check(self):
        d = tempfile.mkdtemp()
        shutil.copytree(EXAMPLE, os.path.join(d, "transcripts"))
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 2)                               # 固定していないと作らない
        self.assertIn("固定していない表", out)
        self.assertEqual(run(freeze.main, [d])[0], 0)
        self.assertEqual(run(freeze.main, [d, "--check"])[0], 0)
        self.assertEqual(run(decide.main, [d])[0], 0)
        body = os.path.join(d, "transcripts", "Tab.1", "body.tsv")
        with open(body, "a", encoding="utf-8") as f:
            f.write("\t".join(["sp", "", "", "Pinus thunbergii", "クロマツ", "", "+", "・", "・", ""]) + "\n")
        rc, out = run(freeze.main, [d, "--check"])
        self.assertEqual(rc, 2)                               # 固定後の書き換えを見つける
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 2)
        self.assertIn("固定後に書き換えられた表", out)
        with self.assertRaises(SystemExit):
            run(freeze.main, [d, "--refreeze", "Tab.1"])      # 理由が要る
        self.assertEqual(run(freeze.main, [d, "--refreeze", "Tab.1", "--why", "読み落としを足した"])[0], 0)
        self.assertEqual(run(decide.main, [d])[0], 0)

    def test_hash_ignores_newline_style(self):
        d = tempfile.mkdtemp()
        shutil.copytree(EXAMPLE, os.path.join(d, "transcripts"))
        t = os.path.join(d, "transcripts", "Tab.1")
        h1 = freeze.table_hash(t)
        p = os.path.join(t, "body.tsv")
        with open(p, "rb") as f:
            raw = f.read().replace(b"\r\n", b"\n")
        with open(p, "wb") as f:
            f.write(raw.replace(b"\n", b"\r\n"))
        self.assertEqual(freeze.table_hash(t), h1)


class DecideTest(unittest.TestCase):
    def test_same_as_to_csv_and_cell_ids(self):
        """規則が何も当たらない表では，今の to_csv.py と同じ値になる．行はセルの ID で転記に結び付く"""
        d = tempfile.mkdtemp()
        shutil.copytree(EXAMPLE, os.path.join(d, "transcripts"))
        run(freeze.main, [d])
        out = os.path.join(d, "new")
        self.assertEqual(run(decide.main, [d, "--out", out])[0], 0)
        run(common.to_csv.main, [d])
        old_c, new_c = rows(os.path.join(d, "composition.csv")), rows(os.path.join(out, "composition.csv"))
        self.assertEqual(len(old_c), len(new_c))
        for a, b in zip(old_c, new_c):
            for k in ("table", "plot", "s_name", "j_name", "layer", "cover", "sociability", "constancy", "status"):
                self.assertEqual(a[k], b[k], k)
            self.assertEqual(a["note"], b["note_read"])
            self.assertEqual(b["value_raw"], b["value_decided"])
            self.assertEqual(b["source_read"], "ai")
        t = common.Table(os.path.join(d, "transcripts", "Tab.1"))
        for b in new_c:                                       # ID から転記のセルを引ける
            self.assertEqual(t.get_id(b["cell_id"]), b["value_raw"])
        old_s, new_s = rows(os.path.join(d, "sites.csv")), rows(os.path.join(out, "sites.csv"))
        self.assertEqual([r["value"] for r in old_s], [r["value"] for r in new_s])
        ids = [r["cell_id"] for r in new_s]
        self.assertTrue(any("/h" in i for i in ids) and any("/n" in i for i in ids) and any("/d/" in i for i in ids))
        self.assertEqual(len(ids), len(set(ids)))             # ID は重ならない

    def test_rules_and_settings(self):
        """D03 (算用数字 → ローマ数字)・D02 (範囲の逆順)・D01 (県名の 0)．転記は変わらず，決定だけが変わる"""
        d = make([HEAD3, ["調査区数", "Zahl d. Aufn.", "", "-", "7", "-", ""],
                  ["調査地 (県名)", "Ort (Signal d. Präf.)", "", "0", "O", "Ka", ""]],
                 [BODY3, ["sp", "", "", "A a", "エー", "S", "+", "2(+)", "・", ""],
                  ["sp", "", "", "B b", "ビー", "S", "・", "III(+-r)", "・", ""],
                  ["sp", "", "", "C c", "シー", "S", "・", "IV(+)", "1・2", ""]],
                 once=[["2", "D d", "ディー", "K", "1(+)", ""]])
        run(freeze.main, [d])
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 0, out)
        comp = {r["j_name"]: r for r in rows(os.path.join(d, "composition.csv")) if r["plot"] == "2"}
        self.assertEqual((comp["ディー"]["constancy"], comp["ディー"]["note_judge"]), ("I", "D03"))   # 1 回出現も同じ条件
        self.assertEqual((comp["エー"]["constancy"], comp["エー"]["value_raw"], comp["エー"]["value_decided"]),
                         ("II", "2(+)", "II(+)"))
        self.assertEqual(comp["エー"]["note_judge"], "D03")
        self.assertIn("2(+) → II(+)", comp["エー"]["note_modify"])
        self.assertEqual((comp["ビー"]["cover"], comp["ビー"]["note_judge"]), ("r-+", "D02"))
        self.assertEqual(comp["シー"]["note_judge"], "")
        pref = [r for r in rows(os.path.join(d, "sites.csv")) if r["item_ja"].startswith("調査地") and r["plot"] == "1"][0]
        self.assertEqual((pref["value"], pref["value_raw"], pref["note_judge"]), ("O", "0", "D01"))
        log = rows_tsv(os.path.join(d, "decisions.tsv"))
        self.assertEqual(sorted(r["judge"] for r in log), ["D01", "D02", "D03", "D03"])   # D03 は本体と 1 回出現
        # 転記は書き換わっていない
        self.assertEqual(run(freeze.main, [d, "--check"])[0], 0)
        # 規則を外すと，印字のままの決定になる (読み直しは要らない)
        write(os.path.join(d, "rule_settings.tsv"), [["rule", "use", "param", "note"], ["D03", "no", "", ""]])
        run(decide.main, [d])
        comp = {r["j_name"]: r for r in rows(os.path.join(d, "composition.csv")) if r["plot"] == "2"}
        self.assertEqual((comp["エー"]["constancy"], comp["エー"]["note_judge"]), ("2", ""))
        self.assertEqual(comp["ビー"]["note_judge"], "D02")

    def test_ten_classes(self):
        """D04: VI-X が 2 つ以上ある列は 10 階級とみて 5 階級に直す．1 つだけなら直さない"""
        d = make([HEAD3, ["調査区数", "Zahl d. Aufn.", "", "12", "9", "-", ""]],
                 [BODY3, ["sp", "", "", "A a", "エー", "", "VIII(+)", "VII", "・", ""],
                  ["sp", "", "", "B b", "ビー", "", "X", "II", "・", ""],
                  ["sp", "", "", "C c", "シー", "", "III", "IV", "・", ""]])
        run(freeze.main, [d])
        run(decide.main, [d])
        got = {(r["j_name"], r["plot"]): (r["constancy"], r["note_judge"]) for r in rows(os.path.join(d, "composition.csv"))}
        self.assertEqual(got[("エー", "1")], ("IV", "D04"))
        self.assertEqual(got[("ビー", "1")], ("V", "D04"))
        self.assertEqual(got[("シー", "1")], ("II", "D04"))
        self.assertEqual(got[("ビー", "2")], ("II", ""))        # 列 2 は VII が 1 つだけ

    def test_readings_and_judgments(self):
        """読み (readings.tsv) と個別の判断 (judgments.tsv) は転記を変えずに決定へ効く"""
        d = make([HEAD3, ["海抜高度", "Höhe ü. Meer", "m", "40", "300", "320", ""]],
                 [BODY3, ["sp", "", "", "A a", "エー", "S;K", "+?", "1・1", "・", ""]],
                 once=[["2", "D d", "ディー", "D", "+", ""]])
        run(freeze.main, [d])
        write(os.path.join(d, "readings.tsv"), [["cell_id", "value", "reader", "date", "note"],
                                               ["Tab.001/b1/1", "+・2", "user", "2026-11-16", ""]])
        write(os.path.join(d, "judgments.tsv"), [["cell_id", "value", "id", "date", "note"],
                                                ["Tab.001/h1/1", "400", "J001", "2026-11-16", "0 の落ちとみる"],
                                                ["Tab.001/o1/@layer", "K", "J002", "2026-11-16", "D は K の誤植"],
                                                ["Tab.001/b1/@layer", "S", "J003", "2026-11-16", ""]])
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 0, out)
        comp = rows(os.path.join(d, "composition.csv"))
        a1 = [r for r in comp if r["j_name"] == "エー" and r["plot"] == "1"][0]
        self.assertEqual((a1["source_read"], a1["value_raw"], a1["cover"], a1["sociability"], a1["status"]),
                         ("user", "+・2", "+", "2", "ok"))
        self.assertIn("AI の読み: +?", a1["note_read"])
        self.assertEqual((a1["layer"], a1["note_judge"]), ("S", "J003"))     # 行の項目の判断は行の全セルに付く
        once = [r for r in comp if r["j_name"] == "ディー"][0]
        self.assertEqual((once["layer"], once["note_judge"], once["cell_id"]), ("K", "J002", "Tab.001/o1/@value"))
        alt = [r for r in rows(os.path.join(d, "sites.csv")) if r["item_ja"] == "海抜高度" and r["plot"] == "1"][0]
        self.assertEqual((alt["value"], alt["value_raw"], alt["note_judge"]), ("400", "40", "J001"))
        self.assertIn("40 → 400．0 の落ちとみる", alt["note_modify"])
        # 2 回作っても同じ (作り直せる)
        first = rows(os.path.join(d, "composition.csv"))
        run(decide.main, [d])
        self.assertEqual(first, rows(os.path.join(d, "composition.csv")))
        # 転記に無いセルの ID は誤りにして，何も書かない
        write(os.path.join(d, "judgments.tsv"), [["cell_id", "value", "id", "date", "note"],
                                                ["Tab.001/b9/1", "+", "J009", "", ""], ["Tab.777/b1/1", "+", "J010", "", ""]])
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 2)
        self.assertIn("Tab.777", out)

    def test_rule_registry(self):
        ids = [r.id for r in rules.load_all()]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))
        for r in rules.RULES:
            self.assertTrue(r.title and r.group)


def rows_tsv(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


class RestoreTest(unittest.TestCase):
    def test_classify_and_apply(self):
        """note の「印字は X」から，決定の決まりで直したセルだけを印字に戻す．読み方の決まり・対象外は戻さない"""
        import restore
        d = make([HEAD3, ["調査年月日", "Datum", "", "'78 8 1", "'79 5 2", "-", "1: 年の印字は '70．出典の年に合わせて 1978 とした (規則 X34)"],
                  ["調査地 (県名)", "Ort (Signal d. Präf.)", "", "K", "O", "Ka",
                   "1: 県名の印字は Ka．調査地は熊本県なので K に直した (規則 X1); 2: 県名の印字は 0．O とした (規則 X44)"]],
                 [BODY3,
                  ["sp", "", "", "Laurocerasus zippeliana", "バクチノキ", "B", "II", "1(+)", "+",
                   "学名の印字は「Prunus zippeliana」．和名を優先し，チェックリストの学名に修正した; "
                   "1: 印字は III．10 階級の常在度を 5 階級に直して II とした (規則 X57); "
                   "2: 印字は I(+)．算用数字の列に混じるローマ数字なので 1(+) とした (規則 X8 (i)); "
                   "3: 印字は +． (+ のあとに点)．+ とした (規則 X48)"],
                  ["sp", "", "", "Quercus glauca", "アラカシ", "B", "+", "・", "・",
                   "階層の印字は B2 だが表頭の高木層は 1 つ (B) だけなので B に直した (規則 X24)"]],
                 once=[["5", "A a", "エー", "K", "+", "印字は in 4．見出しのずれとみて地点 4 から 5 へ移した (規則 X35)"],
                       ["2", "B b", "ビー", "K", "+", "階層の印字なし (+ だけ)．草本なので K とした (規則 X51)"]],
                 notes=[["1", "調査地", "Lage", "蒲江町", "", "Kamae-cho 浦江町", "ok",
                         "和文の印字は 浦江町．ローマ字に合わせて蒲江町に直した (規則 X2)"],
                        ["2", "出現種数の印字", "Artenzahl", "", "", "18", "check", "印字ミスか? 読み直しても読んだ種は 14 (差 -4)"]])
        found = restore.scan(d)
        got = {(f.kind, f.row, f.col): (f.status, f.raw) for _, f in found}
        self.assertEqual(got[("body", 1, "@s_name")], ("戻せる", "Prunus zippeliana"))
        self.assertEqual(got[("body", 1, "1")], ("戻せる", "III"))
        self.assertEqual(got[("body", 1, "2")], ("戻せる", "I(+)"))           # 括弧を含む値を途中で切らない
        self.assertEqual(got[("body", 1, "3")][0], "読み方")                  # X48 は読み方の決まり (戻さない)
        self.assertEqual(got[("body", 2, "@layer")], ("戻せる", "B2"))
        self.assertEqual(got[("header", 1, "1")], ("戻せる", "'70 8 1"))      # 年だけを戻す
        self.assertEqual(got[("header", 2, "1")], ("戻せる", "Ka"))
        self.assertEqual(got[("header", 2, "2")], ("戻せる", "0"))
        self.assertEqual(got[("once", 1, "@plot")], ("戻せる", "4"))
        self.assertEqual(got[("once", 2, "@layer")], ("戻せる", ""))
        self.assertEqual(got[("notes", 1, "@value")][0], "個別に見る")         # 地名の一部の直しは機械で戻さない
        self.assertNotIn(("notes", 2, "@value"), got)                         # 出現種数の食い違いは直しではない
        out = os.path.join(d, "restored")
        rc, log = run(restore.main, [d, "--out", out])
        self.assertEqual(rc, 0, log)
        t = common.Table(os.path.join(out, "transcripts", "Tab.001"))
        self.assertEqual((t.get("body", 1, "@s_name"), t.get("body", 1, "1"), t.get("body", 1, "2"), t.get("body", 1, "3")),
                         ("Prunus zippeliana", "III", "I(+)", "+"))
        self.assertEqual((t.get("header", 2, "1"), t.get("header", 2, "2"), t.get("once", 1, "@plot")), ("Ka", "0", "4"))
        src = common.Table(os.path.join(d, "transcripts", "Tab.001"))
        self.assertEqual(src.get("body", 1, "1"), "II")                       # 元の置き場は触らない
        self.assertEqual(len(rows_tsv(os.path.join(out, "restore_log.tsv"))), 9)


class MoreRulesTest(unittest.TestCase):
    def test_single_tree_layer(self):
        """D05: 表頭の高木層が 1 つの表の B2 → B．高木層が 2 つの表・高木層の行が無い表では当てない"""
        body = [BODY3, ["sp", "", "", "A a", "エー", "B2", "+", "・", "・", ""],
                ["sp", "", "", "B b", "ビー", "B2;S", "1・1", "+", "・", "印字は B2,S (B2 に下線); 1: 下線"]]
        one = make([HEAD3, ["高木層の高さ", "Höhe d. Baumschicht", "m", "8", "6", "-", ""]], body)
        two = make([HEAD3, ["高木第1層の高さ", "Höhe d. Baumschicht-1", "m", "18", "16", "-", ""],
                    ["高木第2層の高さ", "Höhe d. Baumschicht-2", "m", "8", "6", "-", ""]], body)
        none = make([HEAD3, ["海抜高度", "Höhe ü. Meer", "m", "8", "6", "-", ""]], body)
        got = {}
        for name, d in (("one", one), ("two", two), ("none", none)):
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
            self.assertEqual(rc, 0, out)
            got[name] = {(r["j_name"], r["plot"]): (r["layer"], r["note_judge"]) for r in rows(os.path.join(d, "composition.csv"))}
        self.assertEqual(got["one"][("エー", "1")], ("B", "D05"))
        self.assertEqual(got["one"][("ビー", "1")][0], "B")              # 下線の値は B
        self.assertEqual(got["one"][("ビー", "2")][0], "S")              # 下線の無い値は S
        self.assertEqual(got["two"][("エー", "1")], ("B2", ""))
        self.assertEqual(got["none"][("エー", "1")], ("B2", ""))

    def test_aspect(self):
        """D06: 方位の字の重なり・逆順・3 字の順・逆向き・F"""
        from rules import site
        for raw, want in (("SSS", "S"), ("SWSW", "SW"), ("NN", "N"), ("EN", "NE"), ("ES", "SE"), ("NWN", "NNW"),
                          ("NEE", "ENE"), ("SN", "-"), ("WE", "-"), ("F", "E"), ("SF", "SE")):
            self.assertEqual(site.fix_aspect(raw)[0], want, raw)
        for raw in ("N", "SSW", "-", "L", "", "NSE", "5", "EEN"):
            self.assertIsNone(site.fix_aspect(raw), raw)
        d = make([HEAD3, ["方位", "Exposition", "", "ES", "NW", "L", ""]],
                 [BODY3, ["sp", "", "", "A a", "エー", "", "+", "・", "・", ""]])
        run(freeze.main, [d])
        run(decide.main, [d])
        asp = {r["plot"]: (r["value"], r["value_raw"], r["note_judge"]) for r in rows(os.path.join(d, "sites.csv")) if r["item_ja"] == "方位"}
        self.assertEqual(asp["1"], ("SE", "ES", "D06"))
        self.assertEqual(asp["2"], ("NW", "NW", ""))

    def test_redundant_judgments_and_prune(self):
        """規則と同じ結果の引き継ぎの判断 (L:) は数えて外せる．ユーザの判断 (U:) は外さない"""
        d = make([HEAD3, ["方位", "Exposition", "", "ES", "NW", "WS", ""]],
                 [BODY3, ["sp", "", "", "A a", "エー", "", "+", "・", "・", ""]])
        run(freeze.main, [d])
        write(os.path.join(d, "judgments.tsv"), [["cell_id", "value", "id", "date", "note"],
                                                ["Tab.001/h1/1", "SE", "L:X31", "", ""],
                                                ["Tab.001/h1/3", "SW", "U:ユーザ確認", "", ""],
                                                ["Tab.001/h1/2", "N", "L:X1", "", "規則に無い直し"]])
        rc, out = run(decide.main, [d, "--prune-judgments"])
        self.assertEqual(rc, 0, out)
        self.assertIn("判断のうち規則と同じ結果 (消せる): 2", out)
        left = [r["cell_id"] for r in rows_tsv(os.path.join(d, "judgments.tsv"))]
        self.assertEqual(left, ["Tab.001/h1/3", "Tab.001/h1/2"])           # L:X31 だけが外れる
        asp = {r["plot"]: (r["value"], r["note_judge"]) for r in rows(os.path.join(d, "sites.csv")) if r["item_ja"] == "方位"}
        self.assertEqual(asp, {"1": ("SE", "D06"), "2": ("N", "L:X1"), "3": ("SW", "D06")})


class NameRulesTest(unittest.TestCase):
    def test_prefer_ja_name(self):
        """D10: 属が合わない行だけ，和名を優先してチェックリストの学名にする．似た名・あいまいな名は直さない"""
        from rules import names
        table = {"バクチノキ": ("ok", "Laurocerasus zippeliana"), "ヒメジョオン": ("ok", "Erigeron annuus"),
                 "ナゾノキ": ("similar", "Aaa bbb"), "アオキ": ("alias", "Aucuba japonica")}
        keep = names.lookup
        names.lookup = lambda j: table.get(j, ("none", ""))
        try:
            d = make([HEAD3], [BODY3,
                               ["sp", "", "", "Prunus zippeliana", "バクチノキ", "B", "+", "・", "・", ""],
                               ["sp", "", "", "Erigeron canadensis", "ヒメジョオン", "K", "+", "・", "・", ""],
                               ["sp", "", "", "Xxx yyy", "ナゾノキ", "K", "+", "・", "・", ""],
                               ["sp", "", "", "Aucuba japonica", "アオキ", "S", "+", "・", "・", ""]],
                     once=[["2", "Cerasus zippeliana", "バクチノキ", "S", "+", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
            self.assertEqual(rc, 0, out)
            got = {(r["j_name"], r["source"]): (r["s_name"], r["note_judge"]) for r in rows(os.path.join(d, "composition.csv"))}
            self.assertEqual(got[("バクチノキ", "body")], ("Laurocerasus zippeliana", "D10"))
            self.assertEqual(got[("バクチノキ", "once")], ("Laurocerasus zippeliana", "D10"))
            self.assertEqual(got[("ヒメジョオン", "body")], ("Erigeron canadensis", ""))      # 属は同じ: 既定では直さない
            self.assertEqual(got[("ナゾノキ", "body")], ("Xxx yyy", ""))                      # 似た名は直さない
            self.assertEqual(got[("アオキ", "body")], ("Aucuba japonica", ""))
            write(os.path.join(d, "rule_settings.tsv"), [["rule", "use", "param", "note"], ["D10", "yes", "species", ""]])
            run(decide.main, [d])
            got = {(r["j_name"], r["source"]): r["s_name"] for r in rows(os.path.join(d, "composition.csv"))}
            self.assertEqual(got[("ヒメジョオン", "body")], "Erigeron annuus")               # param=species で種の違いも直す
        finally:
            names.lookup = keep

    def test_missing_checklist_is_reported(self):
        """チェックリストが使えないときは D10 を当てず，その旨を知らせる (止めない)"""
        from rules import names
        keep_state, keep_missing = dict(names._STATE), list(names.MISSING)
        names._STATE.update(idx=None, tried=True, why="無い")
        names.MISSING[:] = ["D10 (和名優先) は当てていない: チェックリストが無い"]
        try:
            d = make([HEAD3], [BODY3, ["sp", "", "", "Prunus zippeliana", "バクチノキ", "B", "+", "・", "・", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
            self.assertEqual(rc, 0, out)
            self.assertIn("D10 (和名優先) は当てていない", out)
            self.assertEqual(rows(os.path.join(d, "composition.csv"))[0]["s_name"], "Prunus zippeliana")
        finally:
            names._STATE.clear()
            names._STATE.update(keep_state)
            names.MISSING[:] = keep_missing


if __name__ == "__main__":
    unittest.main(verbosity=1)
