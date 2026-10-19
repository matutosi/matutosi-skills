#!/usr/bin/env python3
"""check_applied.py と impact.py の自己テスト (標準ライブラリだけ).

    python tests/test_proof_check.py
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")


def run(script, args, cwd):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args,
                       cwd=cwd, capture_output=True)
    return (r.returncode, r.stdout.decode("utf-8", "replace").replace("\r\n", "\n"),
            r.stderr.decode("utf-8", "replace"))


def write(path, text, crlf=False):
    if crlf:
        text = text.replace("\n", "\r\n")
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8"))


class CheckApplied(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        write(os.path.join(self.d, "a.md"),
              "吾輩は猫である．\n名前はまだ無い．\n新しい文がここにある．\n"
              "古い　文と\n新しい文の両方．\n改行をまた\nぐ文章．\n", crlf=True)

    def tearDown(self):
        self.tmp.cleanup()

    def judge(self, items, extra=()):
        p = os.path.join(self.d, "items.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False)
        code, out, err = run("check_applied.py", [p, "--root", self.d, "--json"] + list(extra), self.d)
        self.assertEqual(code, 0, err)
        return {r["id"]: r["judgement"] for r in json.loads(out)["results"]}

    def test_four_judgements_and_delete(self):
        items = [
            {"id": "1", "file": "a.md", "old": "ほげ", "new": "新しい文がここにある"},
            {"id": "2", "file": "a.md", "old": "吾輩は猫である", "new": "我輩は犬である"},
            {"id": "3", "file": "a.md", "old": "古い 文", "new": "新しい文の両方"},
            {"id": "4", "file": "a.md", "old": "存在しない", "new": "どこにもない"},
            {"id": "5", "file": "a.md", "old": "消えた語", "new": ""},
            {"id": "6", "file": "a.md", "old": "名前はまだ無い", "new": ""},
        ]
        r = self.judge(items)
        self.assertEqual(r, {"1": "applied", "2": "pending", "3": "both",
                             "4": "moot", "5": "applied", "6": "pending"})

    def test_whitespace_ignored(self):
        r = self.judge([{"id": "x", "file": "a.md", "old": "改行を また ぐ文章", "new": "なし"},
                        {"id": "y", "file": "a.md", "old": "古い　文", "new": "zzz"}])
        self.assertEqual(r["x"], "pending")
        self.assertEqual(r["y"], "pending")

    def test_decisions_format(self):
        data = {"decisions": [{"id": "d1", "items": [
            {"file": "a.md", "old": "吾輩は猫", "new": "x"}]}]}
        p = os.path.join(self.d, "d.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        code, out, _ = run("check_applied.py", [p, "--root", self.d], self.d)
        self.assertEqual(code, 0)
        self.assertIn("pending", out)
        self.assertIn("合計: 1", out)


MD1 = """# 第1章 {#sec-a}

本文．\\@ref(sec-b) を見よ．図 01_01 は重要．

![説明](figures/01_01_R.png)

図．01_01_R：最初の図

```r
# code_01_01_R
x <- 1  # ここに foo
```

## 節B {#sec-b}

次の図 01_02 と code_01_02_R を参照．

![説明](figures/01_02_R.png)

図．01_02_R：次の図

```r
# code_01_02_R
y <- 2
```
"""

MD2 = """# 第2章

\\@ref(sec-b) と図 01_02 を参照．`foo` の話．foo はインライン外にもある．

# 練習問題

図 01_01 を見て答えよ．
"""


class Impact(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        write(os.path.join(self.d, "chapter_01.md"), MD1)
        write(os.path.join(self.d, "chapter_02.md"), MD2, crlf=True)

    def tearDown(self):
        self.tmp.cleanup()

    def j(self, args):
        code, out, err = run("impact.py", ["--root", self.d, "--json"] + args, self.d)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_label(self):
        r = self.j(["label", "sec-b"])
        defs, refs = r["sections"][0]["hits"], r["sections"][1]["hits"]
        self.assertEqual([(h["file"], h["line"]) for h in defs], [("chapter_01.md", 14)])
        self.assertEqual(sorted((h["file"], h["line"]) for h in refs),
                         [("chapter_01.md", 3), ("chapter_02.md", 3)])

    def test_range_broken_and_shift(self):
        # 14-26 行 = 節B (ラベル sec-b，図 01_02，code_01_02_R)
        r = self.j(["range", "chapter_01.md:14-26"])
        self.assertEqual(r["found"]["labels"], ["sec-b"])
        self.assertEqual(r["found"]["figures"], ["01_02"])
        self.assertEqual(r["found"]["codes"], ["code_01_02_R"])
        files = {(h["file"], h["line"]) for h in r["sections"][0]["hits"]}
        self.assertIn(("chapter_01.md", 3), files)      # \@ref(sec-b)
        self.assertIn(("chapter_02.md", 3), files)      # 図 01_02 と \@ref
        self.assertEqual(r["counts"]["shift_figures"], 0)
        # 3-12 行 (図 01_01 とコード) を動かすと，後ろの図・コードが 1 件ずつ繰り上がる
        r2 = self.j(["range", "chapter_01.md:5-12"])
        self.assertEqual(r2["counts"]["shift_figures"], 1)
        self.assertEqual(r2["counts"]["shift_codes"], 1)
        self.assertGreaterEqual(r2["counts"]["broken"], 2)   # 本文・練習問題の「図 01_01」

    def test_text_prose_excludes_code(self):
        all_ = self.j(["text", "foo"])["sections"][0]["hits"]
        prose = self.j(["text", "foo", "--prose"])["sections"][0]["hits"]
        self.assertTrue(any(h["file"] == "chapter_01.md" for h in all_))
        self.assertFalse(any(h["file"] == "chapter_01.md" for h in prose))
        self.assertEqual(sum(h["count"] for h in prose), 1)  # chapter_02 のインライン外の 1 件

    def test_figure(self):
        hits = self.j(["figure", "01_01"])["sections"][0]["hits"]
        kinds = sorted(h["kind"] for h in hits)
        self.assertEqual(kinds, sorted(["図題", "本文", "画像リンク", "練習問題"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
