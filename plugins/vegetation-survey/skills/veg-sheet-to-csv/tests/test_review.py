#!/usr/bin/env python3
"""review.py の自己テスト (外部ライブラリ不要).

    python3 tests/test_review.py
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import review as R  # noqa: E402

SHEET = {"site": {"調査年月日": "20240501", "群落名": "スダジイ群落", "出現種数": 3,
                  "要確認": {"標高": "字が潰れている"}},
         "species": [{"階層": "T1", "種名": "スダジイ", "学名": "Castanopsis sieboldii", "被度・群度": "4,4"},
                     {"階層": "H1", "種名": "ベニシダ", "学名": "Dryopteris erythrosora", "被度・群度": "+",
                      "要確認": "被度が + か 1 か"},
                     {"階層": "H1", "種名": "ナナメノキ", "被度・群度": "1,1"}]}
NAMES = "状態\t入力\t標準和名\t学名\t科名\t候補\t備考\nalias\tナナメノキ\tナナミノキ\tIlex chinensis\tモチノキ科\t\t\nok\tスダジイ\tスダジイ\t\t\t\t\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.data = os.path.join(self.dir, "data.json")
        with open(self.data, "w", encoding="utf-8") as fh:
            json.dump(SHEET, fh, ensure_ascii=False)
        self.img = os.path.join(self.dir, "sheet.png")
        with open(self.img, "wb") as fh:
            fh.write(PNG)
        self.names = os.path.join(self.dir, "names.tsv")
        with open(self.names, "w", encoding="utf-8") as fh:
            fh.write(NAMES)
        self.store = R.Store(self.data, [self.img], self.names)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def read(self, suffix=""):
        with open(self.data + suffix, encoding="utf-8") as fh:
            return json.load(fh)


class TestStore(Base):
    def test_payload(self):
        p = self.store.payload()
        self.assertEqual(len(p["sheets"]), 1)
        self.assertEqual(p["sheets"][0]["image"], 0)
        self.assertEqual(p["names"]["ナナメノキ"]["hub"], "ナナミノキ")
        self.assertIn("階層", p["species_cols"])
        self.assertTrue(any("学名が空" in w for w in p["sheets"][0]["warnings"]))

    def test_save_keeps_single_shape_and_bak(self):
        site = dict(SHEET["site"], 標高="", 斜面方位="S")          # 空にした欄は消える
        species = SHEET["species"][:2] + [{"階層": "H1", "種名": "ナナミノキ", "学名": "Ilex chinensis",
                                           "被度・群度": "1,1"}, {"階層": "", "種名": ""}]   # 全部空の行は捨てる
        species[1] = dict(species[1], 要確認="")                   # 印を外す
        w = self.store.save(0, site, species)
        d = self.read()
        self.assertNotIn("sheets", d)                              # 1 枚の形のまま
        self.assertNotIn("標高", d["site"])
        self.assertEqual(d["site"]["斜面方位"], "S")
        self.assertEqual(len(d["species"]), 3)
        self.assertNotIn("要確認", d["species"][1])
        self.assertTrue(os.path.exists(self.data + ".bak"))
        self.assertEqual(self.read(".bak")["species"][2]["種名"], "ナナメノキ")
        self.assertFalse(any("学名が空" in x for x in w))

    def test_bak_is_kept_from_first_save(self):
        self.store.save(0, SHEET["site"], SHEET["species"][:1])
        self.store.save(0, SHEET["site"], SHEET["species"][:2])
        bak = self.read(".bak")
        self.assertEqual(len(bak["species"]), 3)                   # 2 回目で上書きしない

    def test_sheets_shape_and_range(self):
        with open(self.data, "w", encoding="utf-8") as fh:
            json.dump({"sheets": [SHEET, SHEET]}, fh, ensure_ascii=False)
        self.store.save(1, {"群落名": "x"}, [{"階層": "T1", "種名": "a"}])
        d = self.read()
        self.assertEqual(d["sheets"][1]["site"], {"群落名": "x"})
        self.assertEqual(d["sheets"][0]["site"]["群落名"], "スダジイ群落")
        with self.assertRaises(ValueError):
            self.store.save(5, {}, [])

    def test_flag_keys_do_not_warn_in_build(self):
        w = R.sheet_warnings(1, SHEET)
        self.assertFalse(any("要確認" in x for x in w))


class TestServer(Base):
    def setUp(self):
        super().setUp()
        self.server = R.ThreadingHTTPServer(("127.0.0.1", 0), R.make_handler(self.store))
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def post(self, data, origin=None):
        req = urllib.request.Request(self.url + "/api/save", data=json.dumps(data).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        if origin:
            req.add_header("Origin", origin)
        return json.load(urllib.request.urlopen(req))

    def test_page_data_image(self):
        self.assertIn(b"<title>", urllib.request.urlopen(self.url + "/").read())
        d = json.load(urllib.request.urlopen(self.url + "/api/data"))
        self.assertEqual(d["file"], "data.json")
        self.assertEqual(urllib.request.urlopen(self.url + "/img?i=0").read(), PNG)
        with self.assertRaises(urllib.error.HTTPError):            # 渡していない画像は見せない
            urllib.request.urlopen(self.url + "/img?i=1")

    def test_save_and_origin(self):
        r = self.post({"sheet": 0, "site": {"群落名": "y"}, "species": [{"階層": "T1", "種名": "z"}]})
        self.assertTrue(r["ok"])
        self.assertEqual(r["bak"], "data.json.bak")
        self.assertEqual(self.read()["site"], {"群落名": "y"})
        for body, origin, code in (({"sheet": 0, "site": {}, "species": []}, "http://evil.example", 403),
                                   ({"sheet": 0, "site": [], "species": []}, None, 400)):
            with self.assertRaises(urllib.error.HTTPError) as cm:
                self.post(body, origin)
            self.assertEqual(cm.exception.code, code)
            cm.exception.close()


if __name__ == "__main__":
    unittest.main()
