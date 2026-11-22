"""veg-table-to-csv2 のテスト (標準ライブラリだけで動く)

    python tests/test_csv2.py
"""
import contextlib
import csv
import io
import json
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
        self.assertEqual(len(ids), len(set(ids)))
        keys = [(r.stage, r.order) for r in rules.RULES]
        self.assertEqual(keys, sorted(keys))                    # 段の順 → 段の中の順に並ぶ
        st = {r.id: r.stage for r in rules.RULES}
        self.assertLess(ids.index("D26"), ids.index("D11"))     # D26 は段 6 の中で D11 の前
        self.assertLess(ids.index("D13"), ids.index("D03"))     # 字の乱れ (段 1) は書式 (段 2) の前
        self.assertLess(ids.index("D13"), ids.index("D12"))
        for later in ("D16", "D11", "D26"):                     # 名前を直す (段 3) の後に，学名で引く・種を数える
            self.assertGreater(st[later], st["D10"])
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
        from rules import s4_header as site
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
        from rules import s3_names as names
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
        from rules import s3_names as names
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


class OnceAndFixesTest(unittest.TestCase):
    HEAD = ["item_ja", "item_de", "unit", "1", "2", "3", "4", "note"]
    BODY = ["kind", "group_ja", "group_de", "s_name", "j_name", "layer", "1", "2", "3", "4", "note"]

    def _table(self, counts, once):
        body = [self.BODY] + [["sp", "", "", f"Aa a{i}", f"エー{i}", "K", "+", "+", "+", "+", ""] for i in range(3)]
        return make([self.HEAD, ["出現種数", "Artenzahl", ""] + counts + [""]], body, once=once)

    def test_heading_shift(self):
        """D11: 1 地点ずらすと関わる地点の出現種数がすべて印字と合うときだけ，1 回出現の行を移す"""
        once = [["3", "Bb b1", "ビー1", "K", "+", ""], ["3", "Bb b2", "ビー2", "K", "+", ""]]
        d = self._table(["3", "5", "3", "3"], once)            # in 3 の 2 種を地点 2 へ移すと 2・3 とも合う
        run(freeze.main, [d])
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 0, out)
        got = {r["j_name"]: (r["plot"], r["note_judge"]) for r in rows(os.path.join(d, "composition.csv")) if r["source"] == "once"}
        self.assertEqual(got, {"ビー1": ("2", "D11"), "ビー2": ("2", "D11")})
        # 1 つ飛んだ先 (2026-11-17 ユーザ決定 3a): in 1 の後ろの 1 行を地点 3 へ．地点 2 はもう合っていて，地点 3 に見出しが無い
        d = self._table(["4", "3", "4", "3"], [["1", "Cc c1", "シー1", "K", "+", ""], ["1", "Cc c2", "シー2", "K", "+", ""]])
        run(freeze.main, [d])
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 0, out)
        got = {r["j_name"]: (r["plot"], r["note_judge"]) for r in rows(os.path.join(d, "composition.csv")) if r["source"] == "once"}
        self.assertEqual(got, {"シー1": ("1", ""), "シー2": ("3", "D11")})
        d = self._table(["3", "5", "5", "3"], once)            # 地点 3 の種数は印字と合っている: 移さない
        run(freeze.main, [d])
        run(decide.main, [d])
        got = {r["j_name"]: r["plot"] for r in rows(os.path.join(d, "composition.csv")) if r["source"] == "once"}
        self.assertEqual(got, {"ビー1": "3", "ビー2": "3"})
        d = self._table(["3", "5", "3", "5"], once)            # 前へも後ろへも合う: 決められないので移さない
        run(freeze.main, [d])
        run(decide.main, [d])
        got = {r["j_name"]: r["plot"] for r in rows(os.path.join(d, "composition.csv")) if r["source"] == "once"}
        self.assertEqual(got, {"ビー1": "3", "ビー2": "3"})

    def test_name_fixes(self):
        """D08・D09: 誤植の訂正の表 (name_fixes.tsv) で和名・学名を直す．表が無ければ何もしない"""
        from rules import s3_names as names
        body = [BODY3, ["sp", "", "", "Cyrtominum falcatum", "オニヤブソテツ", "K", "+", "・", "・", ""],
                ["sp", "", "", "Elaeagnus macrophylla", "オオナワシロクミ", "S", "+", "・", "・", ""]]
        d = make([HEAD3], body)
        run(freeze.main, [d])
        names._FIXES.clear()
        keep = names.lookup
        names.lookup = lambda j: ("none", "")                  # 和名優先 (D10) はここでは当てない
        try:
            run(decide.main, [d])
            self.assertEqual([r["note_judge"] for r in rows(os.path.join(d, "composition.csv"))], ["", ""])
            write(os.path.join(d, "name_fixes.tsv"), [["field", "raw", "fixed", "rule", "first_cell"],
                                                     ["s_name", "Cyrtominum falcatum", "Cyrtomium falcatum", "X22", ""],
                                                     ["j_name", "オオナワシロクミ", "オオナワシログミ", "X20", ""]])
            names._FIXES.clear()
            run(decide.main, [d])
        finally:
            names.lookup = keep
            names._FIXES.clear()
        got = [(r["s_name"], r["j_name"], r["note_judge"]) for r in rows(os.path.join(d, "composition.csv"))]
        self.assertEqual(got, [("Cyrtomium falcatum", "オニヤブソテツ", "D09"), ("Elaeagnus macrophylla", "オオナワシログミ", "D08")])

    def test_restore_writes_fixes_and_separates_user(self):
        """restore.py: 誤植 (X20・X22) は name_fixes.tsv に，前回のユーザ確認は old_user_judgments.tsv に分ける"""
        import restore
        d = make([HEAD3, ["海抜高度", "Höhe", "m", "400", "300", "-", "1: 印字は 40．ユーザ確認 2026-11-16: 400 に直す"]],
                 [BODY3, ["sp", "", "", "Cyrtomium falcatum", "オニヤブソテツ", "K", "+", "・", "・",
                          "学名の印字は Cyrtominum falcatum．誤植なので Cyrtomium falcatum に直した (規則 X22)"]],
                 once=[["2", "A a", "エー", "K", "+", "印字は in 1．ユーザ確認 2026-11-16: 地点 2 へ移す"]])
        out = os.path.join(d, "restored")
        rc, log = run(restore.main, [d, "--out", out])
        self.assertEqual(rc, 0, log)
        fixes = rows_tsv(os.path.join(out, "name_fixes.tsv"))
        self.assertEqual([(r["field"], r["raw"], r["fixed"]) for r in fixes], [("s_name", "Cyrtominum falcatum", "Cyrtomium falcatum")])
        self.assertEqual([r["id"] for r in rows_tsv(os.path.join(out, "judgments.tsv"))], ["L:X22"])
        user = rows_tsv(os.path.join(out, "old_user_judgments.tsv"))
        self.assertEqual([(r["cell_id"], r["value"]) for r in user], [("Tab.001/o1/@plot", "2")])
        t = common.Table(os.path.join(out, "transcripts", "Tab.001"))
        self.assertEqual(t.get("once", 1, "@plot"), "1")                  # 印字に戻っている
        self.assertEqual(t.get("header", 1, "1"), "400")                 # 自由な書き方のユーザ確認は機械で戻さない (控えから)


class SmallRulesTest(unittest.TestCase):
    def _comp(self, d):
        run(freeze.main, [d])
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 0, out)
        return {(r["j_name"], r["plot"]): r for r in rows(os.path.join(d, "composition.csv"))}

    def test_constancy_formats(self):
        """D12 (算用数字の列のローマ数字)・D13 (括弧・- の欠け)・D14 (出現地点数 > 調査区数)"""
        body = [BODY3] + [["sp", "", "", f"Aa a{i}", f"エー{i}", "", v1, v2, "・", ""] for i, (v1, v2) in enumerate(
            [("1(+)", "II(+)"), ("2(1)", "I(+"), ("3(+)", "III(+ 1)"), ("I(+)", "IV"), ("5(+)", "V(+-2)"), ("2", "I")])]
        got = self._comp(make([HEAD3, ["調査区数", "Zahl d. Aufn.", "", "3", "8", "-", ""]], body))
        self.assertEqual((got[("エー3", "1")]["constancy"], got[("エー3", "1")]["note_judge"]), ("1", "D12"))
        self.assertEqual((got[("エー4", "1")]["constancy"], got[("エー4", "1")]["note_judge"]), ("3", "D14"))
        self.assertEqual(got[("エー0", "1")]["note_judge"], "")
        self.assertEqual((got[("エー1", "2")]["value_decided"], got[("エー1", "2")]["note_judge"]), ("I(+)", "D13"))
        self.assertEqual((got[("エー2", "2")]["value_decided"], got[("エー2", "2")]["note_judge"]), ("III(+-1)", "D13"))
        self.assertEqual(got[("エー4", "2")]["note_judge"], "")

    def test_once_herb_layer(self):
        """D16: 1 回出現で階層の無い草本は K．階層を書かない表 (半分以上の行に階層が無い) では当てない"""
        herb = sorted(common.to_csv.HERBS)[0]
        once = [["1", herb, "ソウホン", "", "+", ""], ["1", "Bb b", "ビー", "K", "+", ""], ["2", "Cc c", "シー", "S", "+", ""]]
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            got = self._comp(make([HEAD3], [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "・", ""]], once=once))
            self.assertEqual((got[("ソウホン", "1")]["layer"], got[("ソウホン", "1")]["note_judge"]), ("K", "D16"))
            once2 = [["1", herb, "ソウホン", "", "+", ""], ["1", "Bb b", "ビー", "", "+", ""], ["2", "Cc c", "シー", "S", "+", ""]]
            got = self._comp(make([HEAD3], [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "・", ""]], once=once2))
            self.assertEqual(got[("ソウホン", "1")]["note_judge"], "")
        finally:
            names.lookup = keep

    def test_header_rules(self):
        """D17 (同左)・D18 (横棒の重なり．日付と調査番号は除く)・D19 (小数点の落ち)"""
        d = make([HEAD3,
                  ["調査地", "Ort", "", "阿蘇", "同左", "左同", ""],
                  ["調査番号", "Feld-Nr.", "", "- -", "A 1", "- -", ""],
                  ["調査年月日", "Datum", "", "- - -", "'80 5 1", "- -", ""],
                  ["海抜高度", "Höhe ü. Meer", "m", "- -", "300", "-", ""],
                  ["高木層の高さ", "Höhe d. Baumschicht", "m", "8", "6", "-", ""],
                  ["低木層の高さ", "Höhe d. Strauchschicht", "m", "15", "3", "25", ""],
                  ["草本層の高さ", "Höhe d. Krautschicht", "m", "0.5", "30", "0.3", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""]])
        run(freeze.main, [d])
        run(decide.main, [d])
        s = {(r["item_ja"], r["plot"]): (r["value_raw"], r["note_judge"]) for r in rows(os.path.join(d, "sites.csv"))}
        v = {(r["item_ja"], r["plot"]): r["value"] for r in rows(os.path.join(d, "sites.csv"))}
        self.assertEqual((v[("調査地", "2")], v[("調査地", "3")]), ("阿蘇", "阿蘇"))
        self.assertEqual(s[("調査地", "3")], ("左同", "D17"))
        self.assertEqual((v[("海抜高度", "1")], s[("海抜高度", "1")][1]), ("-", "D18"))
        self.assertEqual(s[("調査番号", "1")][1], "")                       # 調査番号・日付の - - は直さない
        self.assertEqual(s[("調査年月日", "1")][1], "")
        self.assertEqual((v[("低木層の高さ", "1")], s[("低木層の高さ", "1")][1]), ("1.5", "D19"))
        self.assertEqual(s[("低木層の高さ", "3")][1], "")                    # 上の層の値が無い地点は直さない
        self.assertEqual((v[("草本層の高さ", "2")], s[("草本層の高さ", "2")][1]), ("3.0", "D19"))


class ConflictsAndAskTest(unittest.TestCase):
    def _place(self):
        d = make([HEAD3, ["出現種数", "Artenzahl", "", "2", "1", "1", ""],
                  ["方位", "Exposition", "", "ES", "N", "S", ""],
                  ["調査年月日", "Datum d. Aufn.", "", "'80 5 1", "??", "'80 5 2", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "S;K", "+", "+?", "・", ""],
                  ["sp", "", "", "Bb b", "ビー", "K", "・", "・", "+", ""]])
        write(os.path.join(d, "judgments.tsv"), [["cell_id", "value", "id", "date", "note"],
                                                ["Tab.001/h2/2", "NE", "L:X1", "", "今の規則で直した"],
                                                ["Tab.001/h2/1", "SE", "L:X31", "", "規則と同じ結果"]])
        write(os.path.join(d, "old_user_judgments.tsv"), [["cell_id", "value", "id", "date", "note"],
                                                         ["Tab.001/b2/3", "1・1", "U:ユーザ確認", "", "前回の答え"]])
        run(freeze.main, [d])
        return d

    def test_conflicts(self):
        """矛盾の区分 N (種数)・V (値)・L (階層)・S (表頭)・J (引き継ぎの判断)・U (前回のユーザ確認) を洗い出し，CSV に入れる"""
        import conflicts
        d = self._place()
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 0, out)
        conf = rows_tsv(os.path.join(d, "conflicts.tsv"))
        kinds = {(r["cell_id"], r["kind"]) for r in conf}
        self.assertIn(("Tab.001/h1/1", "N"), kinds)                   # 地点 1: 印字 2・読んだ種 1
        self.assertNotIn(("Tab.001/h1/3", "N"), kinds)                # 地点 3 は合っている
        self.assertIn(("Tab.001/b1/2", "V"), kinds)                   # +? (自信なし)
        self.assertIn(("Tab.001/b1/1", "L"), kinds)                   # S;K で下線の手がかりなし
        self.assertIn(("Tab.001/h3/2", "S"), kinds)                   # 日付として読めない
        self.assertIn(("Tab.001/h2/2", "J"), kinds)                   # 規則になっていない引き継ぎの判断
        self.assertNotIn(("Tab.001/h2/1", "J"), kinds)                # 規則 (D06) と同じ結果の判断は矛盾に数えない
        self.assertIn(("Tab.001/b2/3", "U"), kinds)
        comp = {(r["j_name"], r["plot"]): r["note_conflict"] for r in rows(os.path.join(d, "composition.csv"))}
        self.assertEqual(comp[("エー", "1")], "L")
        self.assertEqual(comp[("ビー", "3")], "U")
        self.assertEqual(rows(os.path.join(d, "composition.csv"))[-1]["value_raw"], "+")     # 前回の答えは当てていない
        sites = {(r["item_ja"], r["plot"]): r["note_conflict"] for r in rows(os.path.join(d, "sites.csv"))}
        self.assertEqual((sites[("出現種数", "1")], sites[("方位", "2")]), ("N", "J"))
        rc, out = run(conflicts.main, [d])
        self.assertEqual(rc, 0)
        self.assertIn("N 出現種数が印字と合わない", out)

    def test_ask_rules_and_apply(self):
        """規則ごとの件数と例の HTML を作り，回答を rule_settings.tsv・judgments.tsv に当てる"""
        import ask_rules
        d = self._place()
        run(decide.main, [d])
        page = os.path.join(d, "rules.html")
        rc, out = run(ask_rules.main, [d, page])
        self.assertEqual(rc, 0, out)
        with open(page, encoding="utf-8") as f:
            text = f.read()
        for want in ('data-id="D06"', 'data-id="L:X1"', 'data-id="U"', "方位", "<td>ES</td><td>SE</td>", "rule_answers.json"):
            self.assertIn(want, text)
        ans = os.path.join(d, "rule_answers.json")
        with open(ans, "w", encoding="utf-8") as f:
            f.write('{"D06": {"choice": "b", "memo": ""}, "D01": {"choice": "c", "memo": "記号表のある地方だけ"},'
                    ' "L:X1": {"choice": "b", "memo": ""}, "U": {"choice": "b", "memo": ""}}')
        rc, out = run(ask_rules.main, [d, "--apply", ans])
        self.assertEqual(rc, 0, out)
        use = {r["rule"]: r["use"] for r in rows_tsv(os.path.join(d, "rule_settings.tsv"))}
        self.assertEqual((use["D06"], use["D01"], use["D03"]), ("no", "yes", "yes"))
        ids = [r["id"] for r in rows_tsv(os.path.join(d, "judgments.tsv"))]
        self.assertEqual(sorted(ids), ["L:X31", "U:ユーザ確認"])       # L:X1 は外れ，前回のユーザ確認が足された
        todo = rows_tsv(os.path.join(d, "rule_answers_todo.tsv"))
        self.assertEqual([(r["id"], r["what"]) for r in todo], [("D01", "条件を変える")])
        run(decide.main, [d])                                          # 作り直すと，採らない規則は当たらず，引き継ぐ判断が効く
        sites = {(r["item_ja"], r["plot"]): (r["value"], r["note_judge"]) for r in rows(os.path.join(d, "sites.csv"))}
        self.assertEqual(sites[("方位", "1")], ("SE", "L:X31"))        # D06 を外したので，引き継ぎの判断が効く
        self.assertEqual(sites[("方位", "2")], ("N", ""))
        comp = {(r["j_name"], r["plot"]): (r["value_decided"], r["note_judge"]) for r in rows(os.path.join(d, "composition.csv"))}
        self.assertEqual(comp[("ビー", "3")], ("1・1", "U:ユーザ確認"))


class AskRulesProposalsTest(unittest.TestCase):
    def test_groups_and_proposals(self):
        """引き継ぎの判断を型ごとに分け，規則にしやすさと考えられる条件を選択肢に出す．--carry で答え済みを外す"""
        import ask_rules
        d = make([HEAD3, ["草本層の高さ", "Höhe d. Krautschicht", "m", "0:2", "0.5", "0.3", ""],
                  ["調査地 (県名)", "Ort (Signal d. Präf.)", "", "Ka", "Y*", "M", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "÷・2", "+", "・", ""]],
                 once=[["2", "Bb b", "ビー", "", "+", ""], ["2", "Cc c", "シー", "K", "+", ""], ["3", "Dd d", "ディー", "K", "+", ""]])
        write(os.path.join(d, "judgments.tsv"), [["cell_id", "value", "id", "date", "note"],
                                                ["Tab.001/h1/1", "0.2", "L:-", "", ""], ["Tab.001/h2/2", "Y", "L:-", "", ""],
                                                ["Tab.001/b1/1", "+・2", "L:-", "", ""], ["Tab.001/h2/1", "K", "L:X1", "", ""],
                                                ["Tab.001/o1/@layer", "K", "L:X51", "", ""]])
        # これらの型はのちに規則 (D16・D21-D23) になった．群分けを確かめるため，ここでは不採用にして判断を残す
        write(os.path.join(d, "rule_settings.tsv"), [["rule", "use", "param", "note"]] + [[r, "no", "", ""] for r in
                                                                                         ("D16", "D20", "D21", "D22", "D23")])
        run(freeze.main, [d])
        run(decide.main, [d])
        by = {"L:-": [("a", "0:2", "", ""), ("b", "Y*", "", ""), ("c", "÷・2", "", ""), ("d", "1 2", "", ""),
                      ("e", "同左 北西部", "", ""), ("f", "なぞ", "", "")], "L:X1": [("g", "Ka", "", "")]}
        self.assertEqual(list(ask_rules.legacy_groups(by)),
                         ["L:-/小数点の乱れ", "L:-/脚注の印", "L:-/値の字の乱れ", "L:-/中黒の落ち", "L:-/同左つきの地名", "L:-/そのほか", "L:X1"])
        page = os.path.join(d, "rules.html")
        rc, out = run(ask_rules.main, [d, page])
        self.assertEqual(rc, 0, out)
        with open(page, encoding="utf-8") as f:
            text = f.read()
        for want in ('data-id="L:-/小数点の乱れ"', 'data-id="L:-/脚注の印"', 'data-id="L:-/値の字の乱れ"', 'data-id="L:X51"',
                     "規則にしやすさ: 高", "規則にしやすさ: 低-中", 'value="r1"', "草本の一覧に足す", "不採用"):
            self.assertIn(want, text)
        self.assertLess(text.index('data-id="L:X51"'), text.index('data-id="L:X1"'))     # 規則にしやすい群が先
        ans = os.path.join(d, "rule_answers.json")
        with open(ans, "w", encoding="utf-8") as f:
            json.dump({"L:X51": {"choice": "r1", "memo": ""}, "L:-/脚注の印": {"choice": "b", "memo": ""},
                       "L:-/小数点の乱れ": {"choice": "r2", "memo": "植生高も"}, "L:X1": {"choice": "a", "memo": ""}}, f, ensure_ascii=False)
        rc, out = run(ask_rules.main, [d, "--apply", ans])
        self.assertEqual(rc, 0, out)
        left = [r["cell_id"] for r in rows_tsv(os.path.join(d, "judgments.tsv"))]
        self.assertNotIn("Tab.001/h2/2", left)                          # 脚注の印の群だけ外れる (同じ L:- のほかの型は残る)
        self.assertIn("Tab.001/h1/1", left)
        self.assertIn("Tab.001/b1/1", left)
        todo = {r["id"]: (r["what"], r["memo"]) for r in rows_tsv(os.path.join(d, "rule_answers_todo.tsv"))}
        self.assertEqual(todo["L:X51"][0], "規則にする")
        self.assertIn("草本の一覧に足す", todo["L:X51"][1])
        self.assertIn("メモ: 植生高も", todo["L:-/小数点の乱れ"][1])
        rc, out = run(ask_rules.main, [d, page, "--carry", ans])
        with open(page, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn('data-id="L:X51"', text)                       # 答え済みは外れる
        self.assertIn('data-id="L:-/値の字の乱れ"', text)


class AnsweredRulesTest(unittest.TestCase):
    """2026-11-16 のユーザの回答 (規則の確認 2) から足した規則 D20-D26 と，D11・D16・D17 の拡張"""
    HEAD4 = ["item_ja", "item_de", "unit", "1", "2", "3", "4", "note"]
    BODY4 = ["kind", "group_ja", "group_de", "s_name", "j_name", "layer", "1", "2", "3", "4", "note"]

    def _run(self, d):
        from rules import _lib as header, s5_layer as layer, s3_names as names
        header._TABLES.clear()
        layer._WOODY.clear()
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        sites = {(r["item_ja"], r["plot"]): r for r in rows(os.path.join(d, "sites.csv"))}
        comp = {(r["j_name"], r["plot"], r["source"]): r for r in rows(os.path.join(d, "composition.csv"))}
        return sites, comp

    def test_values_and_header_marks(self):
        """D20 (中黒の落ち)・D21 (÷)・D22 (高さの行の 0:2)・D23 (末尾の *)・D17 (同左 X)"""
        d = make([self.HEAD4,
                  ["調査区数", "Zahl d. Aufn.", "", "-", "-", "-", "6", ""],
                  ["草本層の高さ", "Höhe d. Krautschicht", "m", "0:2", "1:5", "0.3", "-", ""],
                  ["調査面積", "Größe d. Probefläche", "m2", "1:5", "25", "25*", "-", ""],
                  ["調査地", "Ort", "", "阿蘇外輪山東部", "阿蘇外輪山南部", "同左 北西部", "同左 宮地", ""],
                  ["海抜高度", "Höhe ü. Meer", "m", "300", "同左 付近", "-", "-", ""]],
                 [self.BODY4, ["sp", "", "", "Aa a", "エー", "K", "1 2", "÷・2", "+", "2 3", ""]])
        sites, comp = self._run(d)
        self.assertEqual((comp[("エー", "1", "body")]["value_decided"], comp[("エー", "1", "body")]["note_judge"]), ("1・2", "D20"))
        self.assertEqual((comp[("エー", "2", "body")]["value_decided"], comp[("エー", "2", "body")]["note_judge"]), ("+・2", "D21"))
        self.assertEqual(comp[("エー", "4", "body")]["note_judge"], "")                 # 常在度の列の「2 3」は直さない
        self.assertEqual((sites[("草本層の高さ", "1")]["value"], sites[("草本層の高さ", "1")]["note_judge"]), ("0.2", "D22"))
        self.assertEqual(sites[("調査面積", "1")]["note_judge"], "")                    # 高さの行だけ
        self.assertEqual((sites[("調査面積", "3")]["value"], sites[("調査面積", "3")]["note_judge"]), ("25", "D23"))
        self.assertEqual((sites[("調査地", "3")]["value"], sites[("調査地", "4")]["value"]), ("阿蘇外輪山北西部", "阿蘇外輪山宮地"))
        self.assertEqual(sites[("調査地", "4")]["note_judge"], "D17")
        self.assertEqual(sites[("海抜高度", "2")]["note_judge"], "")                    # 左の値が 1 つだけのときは直さない

    def test_year_and_pref(self):
        """D24 (年を出典に: 後で 1 字違い．翌年 1-3 月は除く)・D25 (県名を注記の県か地名の表で．記号が 2 つのセルは除く)"""
        d = make([self.HEAD4,
                  ["調査年月日", "Datum d. Aufn.", "", "'79 7 24", "'79 2 10", "'76 5 1", "'78 7 1", ""],
                  ["調査地 (県名)", "Ort (Signal d. Präf.)", "", "Ka", "O", "N/F", "M", ""]],
                 [self.BODY4, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", "+", ""]],
                 notes=[["1,2,4", "出典", "Nachweis", "熊本県 1978", "", "Präf. Kumamoto 1978", "ok", ""],
                        ["3", "出典", "Nachweis", "長崎県 1969", "", "1969", "ok", ""],
                        ["1", "調査地", "Lage", "天草", "", "Amakusa 天草", "ok", ""],
                        ["2", "調査地", "Lage", "宮崎県椎葉村", "", "Shiiba-mura 宮崎県椎葉村", "ok", ""],
                        ["3", "調査地", "Lage", "阿蘇", "", "Aso 阿蘇", "ok", ""],
                        ["4", "調査地", "Lage", "どこか", "", "irgendwo", "ok", ""]])
        write(os.path.join(d, "pref_symbols.tsv"), [["symbol", "pref"], ["K", "熊本県"], ["Ka", "鹿児島県"], ["M", "宮崎県"], ["O", "大分県"]])
        write(os.path.join(d, "place_pref.tsv"), [["place", "pref"], ["天草", "熊本県"], ["阿蘇", "熊本県"]])
        sites, _ = self._run(d)
        date = {p: (sites[("調査年月日", p)]["value"], sites[("調査年月日", p)]["note_judge"]) for p in "1234"}
        self.assertEqual(date["1"], ("1978-07-24", "D24"))            # 出典 1978 の翌年 7 月
        self.assertEqual(date["2"], ("1979-02-10", ""))               # 翌年の 1-3 月は年度の報告書とみて直さない
        self.assertEqual(date["3"], ("1976-05-01", ""))               # 1976 と 1969 は 2 字違い
        self.assertEqual(date["4"], ("1978-07-01", ""))
        pref = {p: (sites[("調査地 (県名)", p)]["value"], sites[("調査地 (県名)", p)]["note_judge"]) for p in "1234"}
        self.assertEqual(pref["1"], ("K", "D25"))                     # 地名の表 (天草 → 熊本県)
        self.assertEqual(pref["2"], ("M", "D25"))                     # 注記に県名が書いてある
        self.assertEqual(pref["3"], ("N/F", ""))                      # 記号が 2 つのセルは直さない
        self.assertEqual(pref["4"], ("M", ""))                        # 県が決まらない地名は直さない

    def test_once_layer_and_moves(self):
        """D16 (木本以外は K)・D11 (段落の先頭の何行かを前の地点へ)・D26 (表頭に無い階層の段落を隣へ．種数が合うときだけ)"""
        body = [self.BODY4, ["sp", "", "", "Quercus glauca", "アラカシ", "B", "+", "+", "+", "+", ""],
                ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", "+", ""]]
        d = make([self.HEAD4, ["出現種数", "Artenzahl", "", "3", "3", "2", "4", ""]], body,
                 once=[["2", "Bb b", "ビー", "K", "+", ""], ["2", "Cc c", "シー", "K", "+", ""],      # 先頭の 1 行は地点 1 の種
                       ["4", "Quercus glauca", "アラカシ", "", "+", ""], ["4", "Dd d", "ディー", "", "+", ""],
                       ["4", "Ff f", "エフ", "K", "+", ""]])
        sites, comp = self._run(d)
        self.assertEqual((comp[("ビー", "1", "once")]["note_judge"], comp[("シー", "2", "once")]["note_judge"]), ("D11", ""))
        self.assertEqual((comp[("ディー", "4", "once")]["layer"], comp[("ディー", "4", "once")]["note_judge"]), ("K", "D16"))
        self.assertEqual(comp[("アラカシ", "4", "once")]["layer"], "")                 # 木本と分かる種は階層を補わない
        # D26: in 2 の段落は，前へも後ろへも種数が合う (D11 は決められない)．地点 2 の表頭に高木層が無いのに B の値があり，
        # 高木層があるのは地点 3 だけなので，地点 3 へ移す
        d = make([HEAD3, ["出現種数", "Artenzahl", "", "4", "2", "4", ""],
                  ["高木層の高さ", "Höhe d. Baumschicht", "m", "-", "-", "7", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""], ["sp", "", "", "Bb b", "ビー", "K", "+", "+", "+", ""]],
                 once=[["2", "Ee e", "イー", "B", "+", ""], ["2", "Ff f", "エフ", "K", "+", ""]])
        sites, comp = self._run(d)
        self.assertEqual((comp[("イー", "3", "once")]["note_judge"], comp[("エフ", "3", "once")]["note_judge"]), ("D26", "D26"))
        # 階層の手がかりが無ければ (どの地点にも高木層がある)，決められないので移さない
        d = make([HEAD3, ["出現種数", "Artenzahl", "", "4", "2", "4", ""],
                  ["高木層の高さ", "Höhe d. Baumschicht", "m", "8", "6", "7", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""], ["sp", "", "", "Bb b", "ビー", "K", "+", "+", "+", ""]],
                 once=[["2", "Ee e", "イー", "B", "+", ""], ["2", "Ff f", "エフ", "K", "+", ""]])
        sites, comp = self._run(d)
        self.assertEqual(comp[("イー", "2", "once")]["note_judge"], "")


class LeftSevenTest(unittest.TestCase):
    """九州の残る引き継ぎの判断 7 セルから直した所 (2026-11-16 ユーザ決定 1a・4a)"""

    def _comp(self, d):
        from rules import s5_layer as layer, s3_names as names
        layer._WOODY.clear()
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        return {(r["j_name"], r["source"]): r for r in rows(os.path.join(d, "composition.csv"))}

    def test_separate_shifts(self):
        """離れた 2 つのずれ: 前後どちらでも合うずれ (地点 7) は見送り，別の所のずれ (地点 2・3) は移す (1a)"""
        head = ["item_ja", "item_de", "unit"] + [str(i) for i in range(1, 10)] + ["note"]
        body = ["kind", "group_ja", "group_de", "s_name", "j_name", "layer"] + [str(i) for i in range(1, 10)] + ["note"]
        d = make([head, ["出現種数", "Artenzahl", ""] + ["2", "2", "1", "1", "1", "2", "1", "2", "1"] + [""]],
                 [body, ["sp", "", "", "Aa a", "エー", "K"] + ["+"] * 9 + [""]],
                 once=[["2", "Bb b", "ビー", "K", "+", ""], ["3", "Cc c", "シー", "K", "+", ""], ["7", "Dd d", "ディー", "K", "+", ""]])
        comp = self._comp(d)
        self.assertEqual((comp[("ビー", "once")]["plot"], comp[("ビー", "once")]["note_judge"]), ("1", "D11"))
        self.assertEqual((comp[("シー", "once")]["plot"], comp[("シー", "once")]["note_judge"]), ("2", "D11"))
        self.assertEqual((comp[("ディー", "once")]["plot"], comp[("ディー", "once")]["note_judge"]), ("7", ""))

    def test_woody_from_decided_cells(self):
        """木本の判定: S;K の行は，下線の規則で S に決まる値があるときだけ木本の手がかりにする (4a)"""
        body = [BODY3,
                ["sp", "", "", "Aa a", "シュボク", "S;K", "+", "・", "・", "印字は S,K (S に下線); 1: 下線"],
                ["sp", "", "", "Bb b", "ツルクサ", "S;K", "+", "+", "・", "印字は S,K"],
                ["sp", "", "", "Cc c", "ソウホン", "K", "+", "・", "・", ""]]
        once = [["2", "Aa a", "シュボク", "", "+", ""], ["2", "Bb b", "ツルクサ", "", "+", ""], ["3", "Dd d", "ディー", "K", "+", ""],
                ["3", "Ee e", "イー", "K", "+", ""]]
        comp = self._comp(make([HEAD3], body, once=once))
        self.assertEqual(comp[("シュボク", "once")]["layer"], "")              # S に決まる値がある: 木本
        self.assertEqual((comp[("ツルクサ", "once")]["layer"], comp[("ツルクサ", "once")]["note_judge"]), ("K", "D16"))


class LaterThanSourceTest(unittest.TestCase):
    def test_conflict_y(self):
        """調査年が出典の年より後: 転記は直さず，矛盾 Y・status=check にする．翌年の 1-3 月は出さない (2026-11-16 ユーザ決定)"""
        head = ["item_ja", "item_de", "unit", "1", "2", "3", "4", "note"]
        body = ["kind", "group_ja", "group_de", "s_name", "j_name", "layer", "1", "2", "3", "4", "note"]
        d = make([head, ["調査年月日", "Datum d. Aufn.", "", "'79 7 24", "'79 2 10", "'76 5 1", "'70 8 -", ""]],
                 [body, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", "+", ""]],
                 notes=[["1-4", "出典", "Nachweis", "熊本県 1978", "", "Präf. Kumamoto 1978", "ok", ""]])
        write(os.path.join(d, "rule_settings.tsv"), [["rule", "use", "param", "note"], ["D24", "no", "", "不採用"]])
        run(freeze.main, [d])
        rc, out = run(decide.main, [d])
        self.assertEqual(rc, 0, out)
        s = {r["plot"]: r for r in rows(os.path.join(d, "sites.csv")) if r["item_ja"] == "調査年月日"}
        self.assertEqual((s["1"]["value"], s["1"]["status"], s["1"]["note_conflict"], s["1"]["note_judge"]), ("1979-07-24", "check", "Y", ""))
        self.assertEqual((s["2"]["status"], s["2"]["note_conflict"]), ("ok", ""))     # 翌年の 2 月: 年度の報告書
        self.assertEqual((s["3"]["status"], s["3"]["note_conflict"]), ("ok", ""))     # 出典より前
        self.assertEqual((s["4"]["value"], s["4"]["note_conflict"]), ("1970-08", ""))
        kinds = [r["kind"] for r in rows_tsv(os.path.join(d, "conflicts.tsv"))]
        self.assertEqual(kinds.count("Y"), 1)


class StageOrderTest(unittest.TestCase):
    def test_open_paren_then_arabic(self):
        """段 1 (D13) が段 2 (D12) より先: 算用数字の列の I(+ は I(+) を経て 1(+) になる (2026-11-17 ユーザ決定 1a)"""
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make([HEAD3, ["調査区数", "Zahl d. Aufn.", "", "3", "-", "-", ""]],
                     [BODY3, ["sp", "", "", "Aa a", "エー", "S", "I(+", "+", "・", ""],
                             ["sp", "", "", "Bb b", "ビー", "S", "1(+)", "+", "・", ""],
                             ["sp", "", "", "Cc c", "シー", "S", "2(+)", "・", "+", ""],
                             ["sp", "", "", "Dd d", "ディー", "S", "3(1)", "・", "+", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        r = {(x["j_name"], x["plot"]): x for x in rows(os.path.join(d, "composition.csv"))}[("エー", "1")]
        self.assertEqual((r["value_decided"], r["note_judge"]), ("1(+)", "D13;D12"))


class InternalRulesTest(unittest.TestCase):
    def test_t_numbers(self):
        """to_csv.py の中の決まり (T 規則) の番号が note_judge に出る (2026-11-17 ユーザ決定 5a)"""
        from common import to_csv
        from rules import s3_names as names
        herb = next(iter(sorted(to_csv.HERBS)))
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make([HEAD3, ["方位", "Exposition", "", "L", "S", "N", ""],
                      ["調査年月日", "Datum d. Aufn.", "", "'79 8 -", "'79 8 2", "'79 8 3", ""]],
                     [BODY3, ["sp", "", "", "Aa a", "エー", "S;K", "2", "1", "・", "印字は S,K (S に下線); 1: 下線"],
                      ["sp", "", "", herb, "ソウホン", "S;K", "+", "・", "・", "印字は S,K"],
                      ["sp", "", "", "Cc c", "シー", "", "・", "v", "・", "階層の印字なし"],
                      ["sp", "", "", "Dd d", "ディー", "K", "・", "・", "○", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        comp = {(r["j_name"], r["plot"]): r for r in rows(os.path.join(d, "composition.csv"))}
        sites = {(r["item_ja"], r["plot"]): r for r in rows(os.path.join(d, "sites.csv"))}
        self.assertIn("T01", comp[("エー", "1")]["note_judge"].split(";"))      # 下線で S
        self.assertIn("T05", comp[("エー", "1")]["note_judge"].split(";"))      # 群度の補い
        self.assertIn("T02", comp[("ソウホン", "1")]["note_judge"].split(";"))  # 草本は K
        self.assertIn("T06", comp[("シー", "2")]["note_judge"].split(";"))
        self.assertIn("T07", comp[("ディー", "3")]["note_judge"].split(";"))
        self.assertEqual(sites[("方位", "1")]["note_judge"], "T08")
        self.assertEqual(sites[("調査年月日", "1")]["note_judge"], "T09")
        self.assertEqual(sites[("調査年月日", "2")]["note_judge"], "")       # ふつうの日付は書式の変換だけ
        self.assertEqual(sites[("列の種類", "1")]["note_judge"], "T11")

    def test_rule_list_is_current(self):
        """references/rules.md が規則の登録と合っている (古ければ python scripts/rule_list.py で作り直す)"""
        import rule_list
        self.assertEqual(run(rule_list.main, ["--check"])[0], 0)


class MovedRulesTest(unittest.TestCase):
    """今のスキルから移した規則 D27-D30 と矛盾の区分 R・H・D・G・P (2026-11-17 ユーザ決定 4a)"""

    def _run(self, d):
        from rules import s3_names as names, s5_layer as layer
        layer._WOODY.clear()
        names._FIXES.clear()
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        return rows(os.path.join(d, "composition.csv")), rows(os.path.join(d, "sites.csv"))

    def test_layer_letters(self):
        """D27: k → K．s は表頭に低木層があるので S．D28: F → K，BB2 → B2，草本層が 1 つの表の K2 → K"""
        d = make([HEAD3, ["高木第2層の高さ", "", "m", "8", "8", "8", ""], ["低木層の高さ", "", "m", "3", "3", "3", ""],
                  ["草本層の高さ", "", "m", "0.5", "0.5", "0.5", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "k", "+", "・", "・", ""],
                  ["sp", "", "", "Bb b", "ビー", "s", "+", "・", "・", ""],
                  ["sp", "", "", "Cc c", "シー", "F", "+", "・", "・", ""],
                  ["sp", "", "", "Dd d", "ディー", "BB2", "+", "・", "・", ""],
                  ["sp", "", "", "Ee e", "イー", "K2", "+", "・", "・", ""]])
        comp, _ = self._run(d)
        got = {r["j_name"]: (r["layer"], r["note_judge"].split(";")[0]) for r in comp}
        self.assertEqual(got["エー"], ("K", "D27"))
        self.assertEqual(got["ビー"], ("S", "D27"))
        self.assertEqual(got["シー"], ("K", "D28"))
        self.assertEqual(got["ディー"], ("B2", "D38"))         # BB2 は字の重なり (D38) が先に当たる
        self.assertEqual(got["イー"], ("K", "D28"))

    def test_dash_absent(self):
        """D29: 横棒だけを + と読んだセルは，出現なしとみると種数が合い + では合わないときだけ出現なし"""
        d = make([HEAD3, ["出現種数", "Artenzahl", "", "1", "2", "1", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""],
                  ["sp", "", "", "Bb b", "ビー", "K", "+", "+", "・", "1: 印字は横棒だけ (-)．+ とした (規則 X26); 2: 印字は横棒だけ (-)．+ とした (規則 X26)"]])
        comp, _ = self._run(d)
        got = {(r["j_name"], r["plot"]): r for r in comp}
        self.assertNotIn(("ビー", "1"), got)                       # 地点 1 は出現なしで合う
        self.assertEqual(got[("ビー", "2")]["note_judge"], "")    # 地点 2 は + のままで合う

    def test_fix_place(self):
        """D30: 訂正の表の field=place で注記の調査地を直す"""
        d = make([HEAD3], [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""]],
                 notes=[["1-3", "調査地", "Fundort", "浦江町沖黒島", "", "Kamae-cho 浦江町沖黒島", "ok", ""]])
        write(os.path.join(d, "name_fixes.tsv"), [["field", "raw", "fixed", "rule", "first_cell"], ["place", "浦江町", "蒲江町", "X2", ""]])
        _, sites = self._run(d)
        r = next(x for x in sites if x["item_ja"] == "調査地" and x["plot"] == "1")
        self.assertEqual((r["value"], r["note_judge"]), ("蒲江町沖黒島", "D30"))

    def test_conflicts_r_h_d_p(self):
        """R: 植被率 > 100・傾斜 > 90．H: 下の層が上の層より高い．D: 存在しない日付．P: 注記に調査地の無い地点"""
        d = make([HEAD3, ["低木層の高さ", "", "m", "3", "1", "2", ""], ["草本層の高さ", "", "m", "0.5", "1.5", "0.4", ""],
                  ["草本層植被率", "", "%", "120", "80", "90", ""], ["傾斜", "Neigung", "°", "95", "10", "20", ""],
                  ["調査年月日", "Datum d. Aufn.", "", "'79 2 30", "'79 8 2", "'79 8 3", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""]],
                 notes=[["1,2", "調査地", "Fundort", "木城町", "", "Kijo-cho 木城町", "ok", ""]])
        _, sites = self._run(d)
        s = {(r["item_ja"], r["plot"]): r for r in sites}
        self.assertEqual((s[("草本層の植被率", "1")]["status"], s[("草本層の植被率", "1")]["note_conflict"]), ("check", "R"))
        self.assertEqual(s[("傾斜", "1")]["note_conflict"], "R")
        self.assertEqual((s[("草本層の高さ", "2")]["status"], s[("草本層の高さ", "2")]["note_conflict"]), ("check", "H"))
        self.assertEqual(s[("草本層の高さ", "1")]["note_conflict"], "")
        self.assertEqual(s[("調査年月日", "1")]["note_conflict"], "D")
        conf = {(r["cell_id"], r["kind"]) for r in rows_tsv(os.path.join(d, "conflicts.tsv"))}
        self.assertIn(("Tab.001/d/調査地/3", "P"), conf)
        self.assertNotIn(("Tab.001/d/調査地/1", "P"), conf)

    def test_conflict_g(self):
        """G: 県名の記号の県と注記の調査地の県が違い，D25 でも直せない (その地方の記号に無い県)"""
        d = make([HEAD3, ["調査地 (県名)", "Präf.", "", "M", "M", "M", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""]],
                 notes=[["1", "調査地", "Fundort", "熊本県阿蘇", "", "", "ok", ""],
                        ["2", "調査地", "Fundort", "宮崎県木城町", "", "", "ok", ""]])
        write(os.path.join(d, "pref_symbols.tsv"), [["symbol", "pref"], ["M", "宮崎県"]])
        _, sites = self._run(d)
        s = {(r["item_ja"], r["plot"]): r for r in sites}
        self.assertEqual((s[("調査地 (県名)", "1")]["status"], s[("調査地 (県名)", "1")]["note_conflict"]), ("check", "G"))
        self.assertEqual(s[("調査地 (県名)", "2")]["note_conflict"], "")


class KyushuAnswersTest(unittest.TestCase):
    """九州の読み直しへのユーザ決定 (2026-11-17「1a 2a 3a」) から足した規則"""

    def _run(self, d):
        from rules import s3_names as names, s5_layer as layer
        layer._WOODY.clear()
        names._FIXES.clear()
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        return rows(os.path.join(d, "composition.csv")), rows(os.path.join(d, "sites.csv"))

    def test_dot_paren_layers(self):
        """D20: 空白の無い 12・+2．D31: 和名の括弧書き．D33: 階層の -．D34: B-1"""
        d = make([HEAD3],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "12", "+2", "・", ""],
                  ["sp", "", "", "Bb b", "ビー (シー)", "K", "+", "・", "・", ""],
                  ["sp", "", "", "Cc c", "ディー", "-", "+", "・", "・", ""],
                  ["sp", "", "", "Ee e", "イー", "B-1", "+", "・", "・", ""]])
        comp, _ = self._run(d)
        got = {(r["j_name"], r["plot"]): r for r in comp}
        self.assertEqual((got[("エー", "1")]["cover"], got[("エー", "1")]["sociability"], got[("エー", "1")]["note_judge"]), ("1", "2", "D20"))
        self.assertEqual((got[("エー", "2")]["cover"], got[("エー", "2")]["sociability"]), ("+", "2"))
        self.assertIn("D31", got[("ビー", "1")]["note_judge"].split(";"))
        self.assertEqual((got[("ディー", "1")]["layer"], got[("ディー", "1")]["note_judge"].split(";")[0]), ("", "D33"))
        self.assertEqual((got[("イー", "1")]["layer"], got[("イー", "1")]["note_judge"].split(";")[0]), ("B1", "D34"))

    def test_item_names(self):
        """D32: 書き方の揺れ (高木第 1 層植被率) と対応表の別名 (既発表資料名 → 出典)．決まった名の行がすでにある表では別名を直さない"""
        d = make([HEAD3, ["高木第 1 層植被率", "Deckung d. Baumschicht-1", "%", "40", "50", "60", ""],
                  ["群落記号", "Spalte", "", "a", "a", "b", ""], ["群落区分", "Spalte", "", "A", "A", "A", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""]],
                 notes=[["1-3", "既発表資料名", "Nachweis", "Miyawaki 1981", "", "", "ok", ""]])
        write(os.path.join(os.path.dirname(d.rstrip(os.sep)), "item_names.tsv") if False else os.path.join(d, "item_names.tsv"),
              [["alias", "name", "note"], ["既発表資料名", "出典", ""], ["群落記号", "群落区分", ""]])
        _, sites = self._run(d)
        items = {r["item_ja"] for r in sites}
        self.assertIn("高木第1層の植被率", items)
        self.assertIn("出典", items)
        self.assertIn("群落記号", items)                      # 群落区分の行がもうあるので直さない
        self.assertNotIn("既発表資料名", items)

    def test_tail_shift(self):
        """D11 の広げた形: 段落の後ろの k 行を次の地点へ移すと両方の地点が合う (見出し in 3: の欠け)"""
        head = ["item_ja", "item_de", "unit", "1", "2", "3", "note"]
        d = make([head, ["出現種数", "Artenzahl", "", "1", "2", "3", ""]],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""]],
                 once=[["2", "Bb b", "ビー", "K", "+", ""], ["2", "Cc c", "シー", "K", "+", ""], ["2", "Dd d", "ディー", "K", "+", ""]])
        comp, _ = self._run(d)
        got = {r["j_name"]: (r["plot"], r["note_judge"]) for r in comp if r["source"] == "once"}
        self.assertEqual(got["ビー"], ("2", ""))
        self.assertEqual(got["シー"], ("3", "D11"))
        self.assertEqual(got["ディー"], ("3", "D11"))


class FernLayerTest(unittest.TestCase):
    def test_fern_k(self):
        """D35: 階層の印字の無いシダは K．着生シダ (Lepisorus) と種で除くもの (Asplenium antiquum) は空欄のまま (X14・X42)"""
        from rules import s3_names as names, s5_layer as layer
        layer._WOODY.clear()
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make([HEAD3],
                     [BODY3, ["sp", "", "", "Gleichenia japonica", "ウラジロ", "", "+", "・", "・", ""],
                      ["sp", "", "", "Dicranopteris pedata", "コシダ", "", "+", "・", "・", ""],
                      ["sp", "", "", "Lepisorus thunbergianus", "ノキシノブ", "", "+", "・", "・", ""],
                      ["sp", "", "", "Asplenium antiquum", "オオタニワタリ", "", "+", "・", "・", ""],
                      ["sp", "", "", "Equisetum arvense", "スギナ", "", "+", "・", "・", ""],
                      ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        got = {r["j_name"]: (r["layer"], r["note_judge"]) for r in rows(os.path.join(d, "composition.csv")) if r["plot"] == "1"}
        self.assertEqual(got["コシダ"], ("K", "D35"))
        self.assertEqual(got["スギナ"], ("K", "D35"))
        self.assertEqual(got["ノキシノブ"][0], "")
        self.assertEqual(got["オオタニワタリ"][0], "")


class PlotConstancyTest(unittest.TestCase):
    """2026-11-17 ユーザ決定 4a・6a: D20 の +-2，D36 (X13) 地点の列の常在度の書き方"""

    def _run(self, d):
        from rules import s3_names as names, s5_layer as layer
        layer._WOODY.clear()
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        return {(r["j_name"], r["plot"]): r for r in rows(os.path.join(d, "composition.csv"))}

    def test_plot_column(self):
        """地点の列の I(+)・r(1) は括弧の中の被度．+-2 は +・2"""
        d = make([HEAD3],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "I(+)", "+-2", "+", ""],
                  ["sp", "", "", "Bb b", "ビー", "K", "+", "+", "・", ""],
                  ["sp", "", "", "Cc c", "シー", "K", "1", "+", "・", ""]],
                 once=[["3", "Dd d", "ディー", "K", "r(1)", ""]])
        got = self._run(d)
        self.assertEqual((got[("エー", "1")]["cover"], got[("エー", "1")]["constancy"], got[("エー", "1")]["note_judge"].split(";")[0]), ("+", "", "D36"))
        self.assertEqual((got[("エー", "2")]["cover"], got[("エー", "2")]["sociability"], got[("エー", "2")]["note_judge"].split(";")[0]), ("+", "2", "D20"))
        self.assertEqual((got[("ディー", "3")]["cover"], got[("ディー", "3")]["note_judge"].split(";")[0]), ("1", "D36"))

    def test_constancy_table_kept(self):
        """調査区数の行が無い総合常在度表 (ローマ数字が多数の列) には当てない"""
        d = make([HEAD3],
                 [BODY3, ["sp", "", "", "Aa a", "エー", "K", "I(+)", "II(+)", "V(1-2)", ""],
                  ["sp", "", "", "Bb b", "ビー", "K", "III(+)", "I(+)", "II(+)", ""],
                  ["sp", "", "", "Cc c", "シー", "K", "II(1)", "IV(+)", "I(+)", ""]])
        got = self._run(d)
        self.assertEqual((got[("エー", "1")]["constancy"], got[("エー", "1")]["note_judge"]), ("I", ""))


class DayOnlyDateTest(unittest.TestCase):
    def test_item_year_month(self):
        """D37: 値が日だけで，年月が項目名の括弧にある調査日に年月を補う (2026-11-17 ユーザ決定 1a)"""
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make([HEAD3, ["調査日", "Datum d. Aufnahme(1988. 3)", "", "19", "24?", "-", ""]],
                     [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        s = {r["plot"]: r for r in rows(os.path.join(d, "sites.csv")) if r["item_ja"] == "調査日"}
        self.assertEqual((s["1"]["value"], s["1"]["note_judge"]), ("1988-03-19", "D37"))
        self.assertEqual((s["2"]["value"], s["2"]["status"]), ("1988-03-24", "check"))
        self.assertEqual(s["3"]["value"], "-")


class UpperVConstancyTest(unittest.TestCase):
    def test_no_plot_count_row(self):
        """D40 は，調査区数の行が無い常在度の列 (総合常在度表．中国 Tab.072) の V を直さない"""
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make([HEAD3, ["出現種数", "Artenzahl", "", "1", "2", "-", ""]],
                     [BODY3, ["sp", "", "", "Aa a", "エー", "K", "V", "II", "II", ""],
                      ["sp", "", "", "Bb b", "ビー", "K", "III", "V", "V(+-1)", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        comp = {(r["j_name"], r["plot"]): r for r in rows(os.path.join(d, "composition.csv"))}
        for key in (("エー", "1"), ("ビー", "2")):
            self.assertNotIn("D40", comp[key]["note_judge"])


class ColumnKindTest(unittest.TestCase):
    """段 0 (D41・D42): 調査区数の印字の無い常在度の列と，調査区数 1 の地点の列 (2026-11-20 ユーザ決定 a)"""

    def _decide(self, header, body):
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make(header, body)
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        return d, {(r["j_name"], r["plot"]): r for r in rows(os.path.join(d, "composition.csv"))}

    def test_missing_count_paren_species(self):
        """D41: 出現種数が括弧つきの列 (中部 Tab.021) の 3(2-3) は常在度 3．転記は印字のまま"""
        d, comp = self._decide(
            [HEAD3, ["出現種数", "Artenzahl", "", "13", "(25)", "16", ""]],
            [BODY3, ["sp", "", "", "Aa a", "エー", "K", "2・3", "3(2-3)", "+", ""],
             ["sp", "", "", "Bb b", "ビー", "K", "+", "1(+)", "・", ""]])
        a2 = comp[("エー", "2")]
        self.assertEqual((a2["constancy"], a2["cover"], a2["sociability"]), ("3", "2-3", ""))
        self.assertEqual(a2["value_raw"], "3(2-3)")
        self.assertIn("D41", a2["note_judge"])
        self.assertIn("調査区数", a2["note_modify"])
        a1 = comp[("エー", "1")]                               # 地点の列はそのまま
        self.assertEqual((a1["cover"], a1["sociability"], a1["constancy"]), ("2", "3", ""))
        self.assertNotIn("D41", a1["note_judge"])
        with open(os.path.join(d, "transcripts", "Tab.001", "header.tsv"), encoding="utf-8") as f:
            self.assertNotIn("調査区数", f.read())                 # 転記に行を足さない
        log = rows_tsv(os.path.join(d, "decisions.tsv"))
        self.assertIn(("Tab.001/d/調査区数/2", "<5", "D41"), {(r["cell_id"], r["decided"], r["judge"]) for r in log})

    def test_missing_count_mean_row(self):
        """D41: 平均出現種数の行に値がある列 (関東 Tab.085)．算用数字で最大が 5 以上の列には当てない．
        ローマ数字が半分以上の列は調査区数 5 以上とみる (+ だけのセルも常在度)"""
        d, comp = self._decide(
            [HEAD3, ["平均出現種数", "Mittlere Artenzahl", "", "22", "18", "20", ""]],
            [BODY3, ["sp", "", "", "Aa a", "エー", "K", "2(+-2)", "6(1)", "V(+)", ""],
             ["sp", "", "", "Bb b", "ビー", "K", "1(2)", "2(+)", "III", ""],
             ["sp", "", "", "Cc c", "シー", "K", "・", "・", "+", ""]])
        self.assertEqual(comp[("エー", "1")]["constancy"], "2")
        self.assertIn("D41", comp[("エー", "1")]["note_judge"])
        self.assertNotIn("D41", comp[("エー", "2")]["note_judge"])   # 6 > 4: 調査区数が決まらない
        self.assertIn("D41", comp[("エー", "3")]["note_judge"])      # ローマ数字の列 (調査区数 5 以上)
        self.assertIn("5 以上", comp[("エー", "3")]["note_modify"])
        self.assertEqual(comp[("エー", "3")]["constancy"], "V")
        self.assertEqual((comp[("シー", "3")]["constancy"], comp[("シー", "3")]["cover"]), ("+", ""))
        log = rows_tsv(os.path.join(d, "decisions.tsv"))
        self.assertIn(("Tab.001/d/調査区数/3", "5+", "D41"), {(r["cell_id"], r["decided"], r["judge"]) for r in log})

    def test_missing_count_star(self):
        """D41 (a): 表頭の 3*・7* と「* は調査区数」の注 (九州ページ内 Tab.030)．注の無い表には当てない"""
        head = [HEAD3, ["植生高", "Höhe d. Vegetation", "cm", "5", "3*", "7*", "2-3: * は表下の注 (*調査区数)"],
                ["出現種数", "Artenzahl", "", "3", "4", "5", ""]]
        body = [BODY3, ["sp", "", "", "Aa a", "エー", "K", "3・3", "3(2-3)", "V(+-4)", ""],
                ["sp", "", "", "Bb b", "ビー", "K", "+", "1(+)", "II(+)", ""]]
        d, comp = self._decide(head, body)
        a2, a3 = comp[("エー", "2")], comp[("エー", "3")]
        self.assertEqual((a2["constancy"], a2["cover"]), ("3", "2-3"))
        self.assertIn("D41", a2["note_judge"])
        self.assertIn("3*", a2["note_modify"])
        self.assertIn("D41", a3["note_judge"])
        log = {(r["cell_id"], r["decided"]) for r in rows_tsv(os.path.join(d, "decisions.tsv"))}
        self.assertIn(("Tab.001/d/調査区数/2", "3"), log)
        self.assertIn(("Tab.001/d/調査区数/3", "7"), log)
        kinds = {r["plot"]: r for r in rows(os.path.join(d, "sites.csv")) if r["item_ja"] == "列の種類"}
        self.assertEqual(kinds["2"]["value"], "常在度")
        self.assertIn("D41", kinds["2"]["note_judge"])
        height = {r["plot"]: r for r in rows(os.path.join(d, "sites.csv")) if r["item_ja"] == "植生高"}
        self.assertEqual((height["1"]["value"], height["2"]["value"]), ("5", "-"))     # 3* は植生高の値ではない
        self.assertIn("D23", height["2"]["note_judge"])
        head[1][-1] = ""                                       # 注が無ければ * は調査区数とみない
        _, comp = self._decide(head, body)
        self.assertNotIn("D41", comp[("エー", "2")]["note_judge"])

    def test_count_one_is_plot(self):
        """D42: 調査区数 1 の列 (中部 Tab.058・関東 Tab.070) は地点の列．常在度の形の値がある列は除く．
        当てたことは組成のセルと，表頭の調査区数・列の種類の行の note_judge・note_modify に残る"""
        d, comp = self._decide(
            [HEAD3, ["調査区数", "Zahl d. Aufnahmen", "", "1", "1", "5", ""]],
            [BODY3, ["sp", "", "", "Aa a", "エー", "K", "2・3", "1(+)", "IV(+-1)", ""],
             ["sp", "", "", "Bb b", "ビー", "K", "+", "・", "II", ""]])
        a1 = comp[("エー", "1")]
        self.assertEqual((a1["cover"], a1["sociability"], a1["constancy"]), ("2", "3", ""))
        self.assertIn("D42", a1["note_judge"])
        self.assertIn("地点の列", a1["note_modify"])
        sites = [r for r in rows(os.path.join(d, "sites.csv")) if r["plot"] == "1"]
        for item in ("調査区数", "列の種類"):
            r = next(x for x in sites if x["item_ja"] == item)
            self.assertIn("D42", r["note_judge"], item)
            self.assertIn("地点の列", r["note_modify"], item)
        self.assertEqual(comp[("ビー", "1")]["cover"], "+")
        self.assertNotIn("D42", comp[("エー", "2")]["note_judge"])   # 1(+) は常在度の形
        self.assertEqual(comp[("エー", "2")]["constancy"], "1")


class SubscriptSociabilityTest(unittest.TestCase):
    def test_count_one_column_with_subscript(self):
        """D42・D45: 調査区数 1 の列の 3(5) (群度が右下の小さい字 3₅) は被度・群度．出現地点数が調査区数を超える check を出さない．
        2(…)〜5(…) の無い列の 1(+) は常在度のまま"""
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make([HEAD3, ["調査区数", "Zahl d. Aufnahmen", "", "1", "1", "5", ""]],
                     [BODY3, ["sp", "", "", "Aa a", "エー", "K", "3(5)", "1(+)", "IV(+-1)", ""],
                      ["sp", "", "", "Bb b", "ビー", "K", "1(2)", "1(1)", "II", ""],
                      ["sp", "", "", "Cc c", "シー", "K", "+", "・", "I", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        comp = {(r["j_name"], r["plot"]): r for r in rows(os.path.join(d, "composition.csv"))}
        a1, b1 = comp[("エー", "1")], comp[("ビー", "1")]
        self.assertEqual((a1["cover"], a1["sociability"], a1["constancy"], a1["status"]), ("3", "5", "", "ok"))
        self.assertEqual((b1["cover"], b1["sociability"], b1["constancy"]), ("1", "2", ""))
        self.assertIn("D45", a1["note_judge"])
        self.assertIn("右下", a1["note_modify"])
        self.assertNotIn("超える", a1["note_read"])
        self.assertEqual(comp[("エー", "2")]["constancy"], "1")       # 3(5) の形の無い列は常在度のまま


class ShikokuDecisionsTest(unittest.TestCase):
    def test_double_glyph_doubt_dot_and_late_dot(self):
        """D38 (字の重なり KK・vv)・D39 (・? は出現なし)・D20 の 12・ (2026-11-17 四国のあとのユーザ決定 5・6・8)"""
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make([HEAD3, ["調査区数", "Zahl d. Aufn.", "", "-", "-", "4", ""]],
                     [BODY3, ["sp", "", "", "Aa a", "エー", "KK", "12・", "・?", "II", ""],
                      ["sp", "", "", "Bb b", "ビー", "K", "vv", "+", "・", ""],
                      ["sp", "", "", "Cc c", "シー", "K", "+", "V", "V", ""],
                      ["sp", "", "", "Dd d", "ディー", "K", "・12", "4,3", "+(+1)", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        comp = {(r["j_name"], r["plot"]): r for r in rows(os.path.join(d, "composition.csv"))}
        self.assertEqual((comp[("エー", "1")]["layer"], comp[("エー", "1")]["value_decided"]), ("K", "1・2"))
        self.assertNotIn(("エー", "2"), comp)                       # ・? は出現なし
        self.assertEqual(comp[("エー", "3")]["constancy"], "II")      # 常在度のローマ数字は重なりとみない
        self.assertEqual(comp[("ビー", "1")]["value_decided"], "v")
        self.assertEqual((comp[("シー", "2")]["value_decided"], comp[("シー", "2")]["note_judge"].split(";")[0]), ("v", "D40"))   # 地点の列の V
        self.assertEqual(comp[("シー", "3")]["constancy"], "V")       # 常在度の列の V はそのまま
        self.assertEqual(comp[("ディー", "1")]["value_decided"], "1・2")   # 中黒が前にずれた ・12
        self.assertEqual(comp[("ディー", "2")]["value_decided"], "4・3")   # カンマの区切り
        self.assertEqual((comp[("ディー", "3")]["value_decided"], comp[("ディー", "3")]["note_judge"].split(";")[0]),
                         ("+(+-1)", "D13"))                            # 範囲の - の欠け (空白なし)


class TwoDigitYearTest(unittest.TestCase):
    """2 桁の年 (項目名の ('78)・セルの 1. Mai '78) と日の範囲の書き方 (D37・D43・to_csv.norm_date)"""

    def test_two_digit_years_and_ranges(self):
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        head = ["item_ja", "item_de", "unit", "1", "2", "3", "4", "5", "6", "note"]
        try:
            d = make([head,
                      ["調査年月日('78)", "Datum d. Aufn.", "", "8 2", "8/4", "8 2", "8 2", "8 2", "8 2", ""],
                      ["調査年月日", "Datum d. Aufn.", "", "1. Mai '78", "28. Apr. '80", "'60", "'77 10",
                       "19.-23. Okt. '78", "19.-23. Okt. '78, u. 16. Dez. '78", ""]],
                     [["kind", "group_ja", "group_de", "s_name", "j_name", "layer", "1", "2", "3", "4", "5", "6", "note"],
                      ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", "+", "+", "+", ""]],
                     notes=[["1", "調査年月日", "Datum", "1976-12-24～26", "", "24.-26. Dez. 1976", "ok", ""],
                            ["2", "調査年月日", "Datum", "2. Aug. 1977", "", "", "ok", ""],
                            ["3", "調査年月日", "Datum", "1979-10-19/1979-10-23", "", "", "ok", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        s = {}
        for r in rows(os.path.join(d, "sites.csv")):
            s.setdefault((r["cell_id"].split("/")[1], r["plot"]), r)
        self.assertEqual(s[("h1", "1")]["value"], "1978-08-02")
        self.assertIn("D37", s[("h1", "1")]["note_judge"])
        self.assertEqual(s[("h1", "2")]["value"], "1978-08-04")
        got = {p: (s[("h2", p)]["value"], s[("h2", p)]["status"]) for p in "123456"}
        self.assertEqual(got["1"], ("1978-05-01", "ok"))
        self.assertEqual(got["2"], ("1980-04-28", "ok"))
        self.assertEqual(got["3"], ("1960", "ok"))
        self.assertEqual(got["4"], ("1977-10", "ok"))
        self.assertEqual(got["5"], ("1978-10-19/1978-10-23", "ok"))
        self.assertEqual(got["6"][1], "check")                     # 日付が 2 つある印字は決めない
        self.assertEqual((s[("n1", "1")]["value"], s[("n1", "1")]["note_judge"]), ("1976-12-24/1976-12-26", "D43"))
        self.assertEqual(s[("n2", "2")]["value"], "1977-08-02")
        self.assertNotIn("D43", s[("n3", "3")]["note_judge"])       # もうそろっている


class FeldNumberTest(unittest.TestCase):
    def test_once_and_notes_by_feld_number(self):
        """D44: 1 回出現の in OK-2・注記の OK: / MM,MK: を表頭の調査番号から地点に引く (関東 Tab.068)"""
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make([HEAD3, ["調査番号", "Feld-Nr.", "", "OK 1", "OK 11", "MM 8", ""],
                      ["出現種数", "Artenzahl", "", "1", "2", "1", ""]],
                     [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+", "+", "+", ""]],
                     once=[["OK-11", "Bb b", "ビー", "K", "+", "見出しの印字は in OK-11"],
                           ["OK-99", "Cc c", "シー", "K", "+", ""]],
                     notes=[["OK", "調査地", "Lage", "大島", "", "OK: Insel Oshima 大島", "ok", ""],
                            ["MM,MK", "調査地", "Lage", "三宅島", "", "MM,MK: Insel Miyakejima 三宅島", "ok", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        comp = {(r["j_name"], r["plot"]): r for r in rows(os.path.join(d, "composition.csv"))}
        self.assertIn(("ビー", "2"), comp)
        self.assertIn("D44", comp[("ビー", "2")]["note_judge"])
        self.assertIn(("シー", "OK-99"), comp)                        # 表頭に無い調査番号は印字のまま
        place = {r["plot"]: r for r in rows(os.path.join(d, "sites.csv")) if r["item_ja"] == "調査地"}
        self.assertEqual((place["1"]["value"], place["2"]["value"], place["3"]["value"]), ("大島", "大島", "三宅島"))
        self.assertIn("D44", place["3"]["note_judge"])
        conf = rows_tsv(os.path.join(d, "conflicts.tsv"))
        self.assertFalse([r for r in conf if r["kind"] == "N" and r["cell_id"].endswith("/2")])   # 地点 2 の種数が合う


class RingAndBareRangeTest(unittest.TestCase):
    def test_ring_mark_and_bare_range(self):
        """D46 (値の右上の小さな丸 +°・3・4° を外す．四国 Tab.086)・D47 (常在度の列の V+-5・I+・I1 を括弧に入れる．四国 Tab.062)．
        地点の列の I1 は D47 で触らない"""
        from rules import s3_names as names
        keep = names.lookup
        names.lookup = lambda j: ("none", "")
        try:
            d = make([HEAD3, ["調査区数", "Zahl d. Aufn.", "", "-", "-", "8", ""]],
                     [BODY3, ["sp", "", "", "Aa a", "エー", "K", "+°", "3・4°", "V+-5", ""],
                      ["sp", "", "", "Bb b", "ビー", "K", "1・1", "・", "I+", ""],
                      ["sp", "", "", "Cc c", "シー", "K", "I1", "+", "I1", ""]],
                     once=[["2", "Dd d", "ディー", "K", "+°", ""]])
            run(freeze.main, [d])
            rc, out = run(decide.main, [d])
        finally:
            names.lookup = keep
        self.assertEqual(rc, 0, out)
        comp = {(r["j_name"], r["plot"]): r for r in rows(os.path.join(d, "composition.csv"))}
        a1, a2, a3 = comp[("エー", "1")], comp[("エー", "2")], comp[("エー", "3")]
        self.assertEqual((a1["cover"], a1["status"]), ("+", "ok"))
        self.assertEqual((a2["cover"], a2["sociability"], a2["status"]), ("3", "4", "ok"))
        self.assertIn("D46", a1["note_judge"])
        self.assertIn("丸", a2["note_modify"])
        self.assertEqual((a3["cover"], a3["constancy"], a3["status"]), ("+-5", "V", "ok"))
        self.assertIn("D47", a3["note_judge"])
        b3, c3 = comp[("ビー", "3")], comp[("シー", "3")]
        self.assertEqual((b3["cover"], b3["constancy"]), ("+", "I"))
        self.assertEqual((c3["cover"], c3["constancy"]), ("1", "I"))
        self.assertNotIn("D47", comp[("シー", "1")]["note_judge"])     # 地点の列は触らない
        self.assertEqual(comp[("ディー", "2")]["cover"], "+")
        self.assertIn("D46", comp[("ディー", "2")]["note_judge"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
