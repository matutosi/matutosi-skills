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


if __name__ == "__main__":
    unittest.main(verbosity=1)
