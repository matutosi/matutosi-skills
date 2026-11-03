#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""proof_review.py の自己テスト (標準ライブラリだけ).

    python tests/test_proof_review.py

一時ディレクトリに原稿・項目 JSON・画像を作り，判定・決定の保存・サーバ・apply を試す。
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import proof_review as P  # noqa: E402

MS = "# 第1章\n\n庭の木に小さな鳥がとまった．\n朝の市場で野菜を買い出します．\n"
ITEMS = {"title": "第1章", "items": [
    {"id": "s1", "kind": "simple", "page": 3, "band": "p003_b1", "label": "「朝」を「夕方」に",
     "images": ["p003_b1.png"],
     "options": [{"key": "a", "label": "朱書きどおり", "recommended": True,
                  "items": [{"file": "ch01.md", "old": "朝の市場", "new": "夕方の市場"}]}]},
    {"id": "j1", "kind": "judge", "page": 3, "band": "p003_b2", "label": "言い方",
     "images": ["p003_b2.png"],
     "options": [{"key": "a", "label": "案 a", "recommended": True,
                  "items": [{"file": "ch01.md", "old": "小さな鳥が", "new": "ちいさな鳥が"}]},
                 {"key": "b", "label": "案 b",
                  "items": [{"file": "ch01.md", "old": "小さな鳥が", "new": "小鳥が"}]}]},
    {"id": "u1", "kind": "unreadable", "page": 4, "band": "p004_b1", "label": "判読不能", "images": [], "options": []},
]}


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        write(os.path.join(self.dir, "ch01.md"), MS)
        os.mkdir(os.path.join(self.dir, "marks"))
        self.items = os.path.join(self.dir, "marks", "items_p003.json")
        write(self.items, json.dumps(ITEMS, ensure_ascii=False))
        for name in ("p003_b1.png", "p003_b2.png"):
            with open(os.path.join(self.dir, "marks", name), "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n")
        self.dec = os.path.join(self.dir, "marks", "decisions.json")
        self.store = P.Store([self.items], self.dec, self.dir)

    def tearDown(self):
        self.tmp.cleanup()


class TestStore(Base):
    def test_load(self):
        self.assertEqual([it["id"] for it in self.store.items], ["s1", "j1", "u1"])
        self.assertTrue(os.path.isabs(self.store.items[0]["images"][0]))

    def test_duplicate_id(self):
        other = os.path.join(self.dir, "marks", "items_dup.json")
        write(other, json.dumps({"items": [ITEMS["items"][0]]}, ensure_ascii=False))
        with self.assertRaises(ValueError):
            P.Store([self.items, other], self.dec, self.dir)

    def test_where(self):
        sub = ITEMS["items"][0]["options"][0]["items"][0]
        self.assertEqual(self.store.where(sub), ("pending", 4))
        write(os.path.join(self.dir, "ch01.md"), MS.replace("朝の市場", "夕方の市場"))
        self.assertEqual(self.store.where(sub)[0], "applied")
        self.assertEqual(self.store.where({"file": "ch01.md", "old": "無い文", "new": "別の文"})[0], "moot")
        self.assertEqual(self.store.where({"file": "none.md", "old": "a", "new": "b"})[0], "nofile")

    def test_diff_html(self):
        a, b = P.diff_html("朝の市で", "夕の市で")
        self.assertIn("<del>朝</del>", a)
        self.assertIn("<ins>夕</ins>", b)

    def test_decide_option_and_edit(self):
        self.store.decide({"id": "j1", "status": "approved", "choice": "b"})
        d = self.store.decisions()["j1"]
        self.assertEqual(d["items"][0]["new"], "小鳥が")
        self.assertIn("案 b", d["label"])
        self.store.decide({"id": "j1", "status": "approved", "choice": "a", "edited": True,
                           "items": [{"file": "ch01.md", "old": "小さな鳥が", "new": "小さい鳥が"}]})
        d = self.store.decisions()["j1"]
        self.assertEqual(d["items"][0]["new"], "小さい鳥が")
        self.assertTrue(d.get("edited"))
        self.assertEqual(len(self.store.decisions()), 1)

    def test_decide_own_hold_undo(self):
        self.store.decide({"id": "u1", "status": "approved", "choice": "own",
                           "items": [{"file": "ch01.md", "old": "買い出します", "new": "買い出しましょう"}]})
        self.store.decide({"id": "s1", "status": "pending", "choice": "a", "memo": "あとで"})
        c = self.store.counts()
        self.assertEqual((c["approved"], c["pending"], c["undecided"]), (1, 1, 1))
        self.store.decide({"id": "s1", "status": "undecided"})
        self.assertNotIn("s1", self.store.decisions())
        with self.assertRaises(LookupError):
            self.store.decide({"id": "zz", "status": "approved"})
        with self.assertRaises(ValueError):
            self.store.decide({"id": "s1", "status": "done"})

    def test_keeps_other_decisions(self):
        write(self.dec, json.dumps({"decisions": [{"id": "K1", "tag": "x", "label": "既存", "status": "applied",
                                                   "files": [], "items": []}]}, ensure_ascii=False))
        self.store.decide({"id": "s1", "status": "approved", "choice": "a"})
        self.assertEqual(set(self.store.decisions()), {"K1", "s1"})


class TestServer(Base):
    def setUp(self):
        super().setUp()
        self.server = P.ThreadingHTTPServer(("127.0.0.1", 0), P.make_handler(self.store))
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def post(self, data, origin=None):
        req = urllib.request.Request(self.url + "/api/decide", data=json.dumps(data).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        if origin:
            req.add_header("Origin", origin)
        return json.load(urllib.request.urlopen(req))

    def test_page_items_image(self):
        self.assertIn(b"<title>", urllib.request.urlopen(self.url + "/").read())
        v = json.load(urllib.request.urlopen(self.url + "/api/items"))
        self.assertEqual(len(v["items"]), 3)
        key = v["items"][0]["images"][0]["key"]
        self.assertTrue(urllib.request.urlopen(self.url + "/img?k=" + urllib.parse.quote(key)).read().startswith(b"\x89PNG"))
        with self.assertRaises(urllib.error.HTTPError):    # 項目に無いファイルは見せない
            urllib.request.urlopen(self.url + "/img?k=" + urllib.parse.quote(os.path.join(self.dir, "ch01.md")))

    def test_decide_and_origin(self):
        self.assertTrue(self.post({"id": "s1", "status": "approved", "choice": "a"})["ok"])
        self.assertEqual(self.store.decisions()["s1"]["status"], "approved")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post({"id": "s1", "status": "rejected"}, origin="http://evil.example")
        self.assertEqual(cm.exception.code, 403)


class TestApply(Base):
    def run_cli(self, *args):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "proof_review.py")] + list(args),
                           cwd=self.dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return r.returncode, r.stdout.decode("utf-8") + r.stderr.decode("utf-8")

    def test_apply(self):
        self.store.decide({"id": "s1", "status": "approved", "choice": "a"})
        self.store.decide({"id": "j1", "status": "rejected", "choice": "a"})
        rc, out = self.run_cli("apply", self.items)
        self.assertEqual(rc, 0, out)
        self.assertIn("朝の市場", open(os.path.join(self.dir, "ch01.md"), encoding="utf-8").read())
        rc, out = self.run_cli("apply", self.items, "--apply")
        self.assertEqual(rc, 0, out)
        body = open(os.path.join(self.dir, "ch01.md"), encoding="utf-8").read()
        self.assertIn("夕方の市場で", body)
        self.assertIn("小さな鳥が", body)             # 不採用は当てない
        self.assertEqual(self.store.decisions()["s1"]["status"], "applied")
        rc, out = self.run_cli("status", self.items)
        self.assertIn("反映済み 1", out)

    def test_apply_failure_names_items(self):
        # 修正前が原稿に無い置換は止まり，#番号と項目の id，--partial が無いことを案内する
        self.store.decide({"id": "s1", "status": "approved", "choice": "own",
                           "items": [{"file": "ch01.md", "old": "原稿に無い文字列", "new": "x"}]})
        before = open(os.path.join(self.dir, "ch01.md"), encoding="utf-8").read()
        rc, out = self.run_cli("apply", self.items, "--apply")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("#1 s1", out)
        self.assertIn("--partial は無い", out)
        self.assertEqual(open(os.path.join(self.dir, "ch01.md"), encoding="utf-8").read(), before)
        self.assertEqual(self.store.decisions()["s1"]["status"], "approved")   # 反映済みにしない


if __name__ == "__main__":
    unittest.main()
