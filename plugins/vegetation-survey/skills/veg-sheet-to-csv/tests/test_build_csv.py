#!/usr/bin/env python3
"""build_csv.py の自己テスト (外部ライブラリ不要).

    python3 tests/test_build_csv.py
"""

import csv
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import build_csv as b  # noqa: E402

SAMPLE = os.path.join(HERE, "..", "..", "..", "examples", "sample.json")


def load():
    with open(SAMPLE, encoding="utf-8") as f:
        return json.load(f)


def read(path, enc="cp932"):
    with open(path, encoding=enc, newline="") as f:
        return list(csv.reader(f))


class KanaTest(unittest.TestCase):
    def test_half(self):
        self.assertEqual(b.to_half("ガギプヴァ"), "ｶﾞｷﾞﾌﾟｳﾞｧ")
        self.assertEqual(b.to_half("ベニシダ"), "ﾍﾞﾆｼﾀﾞ")
        self.assertEqual(b.to_half("ススキ・ヨシ"), "ｽｽｷ･ﾖｼ")
        self.assertEqual(b.to_half("オオバﾔｼｬﾌﾞｼ"), "ｵｵﾊﾞﾔｼｬﾌﾞｼ")
        self.assertEqual(b.to_half("ひらがな"), "ﾋﾗｶﾞﾅ")
        self.assertEqual(b.to_half("ナキリスゲ属"), "ﾅｷﾘｽｹﾞ属")
        self.assertEqual(b.to_half("ｾﾝﾀﾞﾝｰ"), "ｾﾝﾀﾞﾝｰ")

    def test_full(self):
        self.assertEqual(b.to_full("ﾍﾞﾆｼﾀﾞ"), "ベニシダ")
        self.assertEqual(b.to_full("ｵｵﾊﾞﾔｼｬﾌﾞｼ"), "オオバヤシャブシ")
        self.assertEqual(b.to_full("ﾘｮｳﾌﾞ"), "リョウブ")

    def test_roundtrip(self):
        s = "ヤブニッケイ"
        self.assertEqual(b.to_full(b.to_half(s)), s)


class CoverTest(unittest.TestCase):
    def test_split(self):
        for src, c, g in [("3,4", "3", "4"), ("3・4", "3", "4"), ("+", "+", None), ("2.3", "2", "3")]:
            sp = {"被度・群度": src}
            b.split_cover(sp)
            self.assertEqual(sp["被度階級値"], c)
            self.assertEqual(sp.get("群度"), g)


class BuildTest(unittest.TestCase):
    def run_cli(self, *args):
        out = os.path.join(tempfile.mkdtemp(), "x")
        self.assertEqual(b.main([SAMPLE, "-o", out] + list(args)), 0)
        return out

    def test_single_default(self):
        rows = read(self.run_cli() + ".csv")
        self.assertEqual(rows[0], b.ALL_COLS)
        self.assertEqual(len(rows) - 1, 4)
        self.assertEqual({len(r) for r in rows}, {47})
        r = dict(zip(rows[0], rows[1]))
        self.assertEqual(r["種名"], "ｺｼﾞｲ")
        self.assertEqual(r["群度"], "4")
        self.assertEqual(r["面積測定方法"], "0")
        self.assertEqual(r["緯度"], "")
        last = dict(zip(rows[0], rows[4]))
        self.assertEqual((last["被度階級値"], last["群度"]), ("+", ""))

    def test_full_na(self):
        out = self.run_cli("--kana", "full", "--missing", "na", "--unknown-code", "blank")
        r = dict(zip(*read(out + ".csv")[:2]))
        self.assertEqual(r["種名"], "コジイ")
        self.assertEqual(r["緯度"], "NA")
        self.assertEqual(r["面積測定方法"], "NA")
        self.assertEqual(r["絶滅危惧種フラグ"], "0")

    def test_two_files(self):
        out = self.run_cli("--layout", "two", "--encoding", "utf-8-sig", "--eol", "lf")
        site = read(out + "_地点.csv", "utf-8-sig")
        comp = read(out + "_組成.csv", "utf-8-sig")
        self.assertEqual(site[0][0], "調査ID")
        self.assertEqual(len(site) - 1, 1)
        self.assertEqual(len(comp) - 1, 4)
        self.assertEqual({r[0] for r in comp[1:]}, {site[1][0]})
        self.assertEqual(site[0][1:], b.SITE_COLS)
        self.assertEqual(comp[0][1:], b.SPECIES_COLS)

    def test_two_sheets_keys(self):
        d = load()
        _, site_rows, spec_rows, _ = b.build({"sheets": [d, d]}, layout="two")
        self.assertEqual([r[0] for r in site_rows], ["S001", "S002"])
        self.assertEqual(len({r[0] for r in spec_rows}), 2)

    def test_warnings(self):
        d = load()
        d["site"]["出現種数"] = "9"
        d["species"].append({"階層": "X9", "種名": "コジイ", "学名": "", "被度階級値": ""})
        text = "\n".join(b.build(d)[0])
        for key in ["出現種数 9", "X9", "学名が空", "被度階級値が空"]:
            self.assertIn(key, text)
        d2 = load()
        d2["species"].append(dict(d2["species"][0]))
        self.assertIn("2回", "\n".join(b.build(d2)[0]))

    def test_unknown_keys(self):
        d = load()
        d["site"]["標高m"] = "1"
        d["species"][0]["被度"] = "3"
        text = "\n".join(b.build(d)[0])
        self.assertIn("'標高m'", text)
        self.assertIn("'被度'", text)

    def test_input_not_modified(self):
        d = load()
        before = json.dumps(d, ensure_ascii=False)
        b.build(d)
        self.assertEqual(json.dumps(d, ensure_ascii=False), before)

    def test_na_applies_to_species_columns(self):
        _, _, _, rows = b.build(load(), missing="na")
        r = dict(zip(b.ALL_COLS, rows[0]))
        self.assertEqual((r["科名"], r["被度百分率"], r["行番号"]), ("NA", "NA", "NA"))

    def test_public_name_follows_kana(self):
        _, _, _, rows = b.build(load(), kana="full")
        r = dict(zip(b.ALL_COLS, rows[0]))
        self.assertEqual(r["種名（公開用）"], "コジイ")

    def test_multi_sheet_single_layout(self):
        d = load()
        _, _, _, rows = b.build({"sheets": [d, d]})
        self.assertEqual(len(rows), 8)

    def test_unencodable_char(self):
        d = load()
        d["site"]["備考"] = "\U0001F600"  # 絵文字は cp932 で書けない
        path = os.path.join(tempfile.mkdtemp(), "in.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        out = os.path.join(tempfile.mkdtemp(), "x")
        rc = b.main([path, "-o", out, "--encoding", "cp932"])
        self.assertEqual(rc, 1)  # 例外を出さずに終了コード 1
        rc = b.main([path, "-o", out, "--encoding", "utf-8-sig"])
        self.assertEqual(rc, 0)

    def test_clean(self):
        self.assertEqual(b.build(load())[0], [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
