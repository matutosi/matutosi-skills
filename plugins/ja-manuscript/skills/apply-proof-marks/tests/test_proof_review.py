#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""proof_review.py の自己テスト (標準ライブラリだけ).

    python tests/test_proof_review.py

一時ディレクトリに原稿・項目 JSON・画像を作り，判定・決定の保存・静的な HTML・apply を試す。
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

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


def page_data(page):
    """HTML に埋め込んだ DATA を取り出す"""
    start = page.index("const DATA = ") + len("const DATA = ")
    end = page.index(";\nconst KEY", start)
    return json.loads(page[start:end])


class TestHtml(Base):
    def test_page_embeds_items_and_images(self):
        out = os.path.join(self.dir, "out", "review_ch01.html")
        page = P.build_page(self.store, out)
        self.assertIn("<title>第1章</title>", page)
        self.assertNotIn("/api/", page)                     # サーバに問い合わせない
        d = page_data(page)
        self.assertEqual([it["id"] for it in d["items"]], ["s1", "j1", "u1"])
        self.assertTrue(d["items"][0]["images"][0]["src"].startswith("data:image/png;base64,"))
        self.assertEqual(d["items"][2]["images"], [])
        self.assertEqual(d["answers_name"], "review_ch01_decisions.json")
        self.assertEqual(d["items"][0]["options"][0]["items"][0]["state"], "pending")
        self.assertEqual(d["reading_label"], "朱書き")
        self.assertNotIn(self.dir, page)                    # 手元のパスを入れない

    def test_text_only_items(self):
        """画像の無い修正案 (原稿だけから作ったもの) は 1 段組・見出しは「読み取り」"""
        rows = [dict(it, images=[]) for it in ITEMS["items"]]
        path = os.path.join(self.dir, "marks", "items_text.json")
        write(path, json.dumps({"items": rows}, ensure_ascii=False))
        page = P.build_page(P.Store([path], self.dec, self.dir), os.path.join(self.dir, "t.html"))
        d = page_data(page)
        self.assertEqual(d["title"], "修正案の採否")
        self.assertEqual(d["reading_label"], "読み取り")
        self.assertIn(".card.noimg", page)
        self.assertIn('hasImg?"":" noimg"', page)

    def test_initial_decisions_and_cli(self):
        self.store.decide({"id": "s1", "status": "approved", "choice": "a"})
        out = os.path.join(self.dir, "r.html")
        rc = subprocess.run([sys.executable, os.path.join(SCRIPTS, "proof_review.py"), "html", self.items,
                             "--out", out, "--base", self.dir], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=dict(os.environ, PYTHONIOENCODING="utf-8")).returncode
        self.assertEqual(rc, 0)
        d = page_data(open(out, encoding="utf-8").read())
        self.assertEqual(d["items"][0]["decision"]["status"], "approved")

    def test_missing_image(self):
        os.remove(os.path.join(self.dir, "marks", "p003_b1.png"))
        with self.assertRaises(ValueError):
            P.build_page(self.store, os.path.join(self.dir, "r.html"))

    def test_script_has_no_closing_tag_in_data(self):
        rows = [dict(ITEMS["items"][0], note="</script><b>x</b>")]
        path = os.path.join(self.dir, "marks", "items_x.json")
        write(path, json.dumps({"items": rows}, ensure_ascii=False))
        page = P.build_page(P.Store([path], self.dec, self.dir), os.path.join(self.dir, "x.html"))
        self.assertEqual(page.count("</script>"), 1)
        self.assertEqual(page_data(page)["items"][0]["note"], "</script><b>x</b>")


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

    def test_apply_downloaded_answers(self):
        """HTML で保存した回答 (decisions.json と同じ形．置き場は別) を --decisions で当てる"""
        ans = os.path.join(self.dir, "review_decisions.json")
        write(ans, json.dumps({"decisions": [
            {"id": "j1", "tag": "proof", "label": "言い方 (自分で書いた直し)", "status": "approved", "files": [],
             "items": [{"file": "ch01.md", "old": "小さな鳥が", "new": "小鳥が", "count": 1}],
             "choice": "own", "memo": "", "page": 3, "band": "p003_b2"}]}, ensure_ascii=False))
        rc, out = self.run_cli("apply", self.items, "--decisions", ans, "--apply")
        self.assertEqual(rc, 0, out)
        self.assertIn("小鳥が", open(os.path.join(self.dir, "ch01.md"), encoding="utf-8").read())
        rc, out = self.run_cli("status", self.items, "--decisions", ans)
        self.assertIn("反映済み 1", out)

    def test_apply_text_and_docx(self):
        # テキストと Word の原稿が混ざっても，1 回の apply で両方に当て，Word は変更履歴にする
        sys.path.insert(0, HERE)
        import test_apply_docx as TD
        TD.make_docx(os.path.join(self.dir, "ms.docx"))
        self.store.decide({"id": "s1", "status": "approved", "choice": "a"})
        self.store.decide({"id": "j1", "status": "approved", "choice": "own",
                           "items": [{"file": "ms.docx", "old": "庭の木に", "new": "庭の松に"}]})
        rc, out = self.run_cli("apply", self.items, "--apply", "--author", "校正者")
        self.assertEqual(rc, 0, out)
        with open(os.path.join(self.dir, "ch01.md"), encoding="utf-8") as fh:
            self.assertIn("夕方の市場で", fh.read())
        with zipfile.ZipFile(os.path.join(self.dir, "ms.docx")) as z:
            x = z.read("word/document.xml").decode("utf-8")
        self.assertRegex(x, r'<w:ins [^>]*w:author="校正者"')
        self.assertEqual(self.store.decisions()["j1"]["status"], "applied")
        sub = {"file": "ms.docx", "old": "庭の木に", "new": "庭の松に"}
        self.assertEqual(self.store.where(sub)[0], "applied")      # 原稿での状態も docx の本文で判定する

    def test_apply_docx_failure_blocks_text(self):
        # Word 側が当たらなければ，テキスト側も書かない
        sys.path.insert(0, HERE)
        import test_apply_docx as TD
        TD.make_docx(os.path.join(self.dir, "ms.docx"))
        self.store.decide({"id": "s1", "status": "approved", "choice": "a"})
        self.store.decide({"id": "j1", "status": "approved", "choice": "own",
                           "items": [{"file": "ms.docx", "old": "無い文字列", "new": "x"}]})
        with open(os.path.join(self.dir, "ch01.md"), encoding="utf-8") as fh:
            before = fh.read()
        rc, out = self.run_cli("apply", self.items, "--apply")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("Word の原稿", out)
        with open(os.path.join(self.dir, "ch01.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

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
