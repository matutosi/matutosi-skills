#!/usr/bin/env python3
"""polish-loop のスクリプトの自己テスト (外部ライブラリ不要).

    python tests/test_polish_loop.py

どのスクリプトもカレントディレクトリの原稿と _polish/ を相手にするので，
一時ディレクトリを作ってそこで動かす．
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
    out = r.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
    err = r.stderr.decode("utf-8", "replace")
    return r.returncode, out, err


def write(path, text, newline="\n"):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)


def read(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def p(self, *names):
        return os.path.join(self.d, *names)


class TestApplyFixes(Base):
    def setUp(self):
        super().setUp()
        write(self.p("chapter_01.md"), "これは誤時です．\n表記を統一します．\n")

    def fixes(self, rows, name="fixes.json"):
        write(self.p(name), json.dumps(rows, ensure_ascii=False))
        return name

    def test_check_only_does_not_write(self):
        f = self.fixes([{"file": "chapter_01.md", "before": "誤時", "after": "誤字"}])
        code, out, err = run("apply_fixes.py", [f], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("誤時", read(self.p("chapter_01.md")))

    def test_apply(self):
        f = self.fixes([{"file": "chapter_01.md", "before": "誤時", "after": "誤字"}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.p("chapter_01.md")), "これは誤字です．\n表記を統一します．\n")

    def test_not_unique_is_not_applied(self):
        # 「す．」は2回現れるので当てない．一意な方だけ当たる
        f = self.fixes([{"file": "chapter_01.md", "before": "す．", "after": "す。"},
                        {"file": "chapter_01.md", "before": "誤時", "after": "誤字"}])
        run("apply_fixes.py", [f, "--apply"], self.d)
        text = read(self.p("chapter_01.md"))
        self.assertNotIn("す。", text)

    def test_crlf_kept(self):
        write(self.p("chapter_02.md"), "一行目です．\n二行目です．\n", newline="\r\n")
        f = self.fixes([{"file": "chapter_02.md", "before": "一行目", "after": "1行目"}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.p("chapter_02.md")), "1行目です．\r\n二行目です．\r\n")

    def test_tsv(self):
        write(self.p("fixes.tsv"), "chapter_01.md\t誤時\t誤字\n")
        code, out, err = run("apply_fixes.py", ["fixes.tsv", "--apply"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("誤字", read(self.p("chapter_01.md")))

    def test_mismatch_stops_unless_partial(self):
        rows = [{"file": "chapter_01.md", "before": "す．", "after": "す。"},
                {"file": "chapter_01.md", "before": "誤時", "after": "誤字"}]
        code, out, err = run("apply_fixes.py", [self.fixes(rows), "--apply"], self.d)
        self.assertEqual(code, 1)
        self.assertIn("誤時", read(self.p("chapter_01.md")))
        code, out, err = run("apply_fixes.py", [self.fixes(rows), "--apply", "--partial"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("誤字", read(self.p("chapter_01.md")))

    def test_old_new_keys_and_mixed(self):
        f = self.fixes([{"file": "chapter_01.md", "old": "誤時", "new": "誤字"},
                        {"file": "chapter_01.md", "before": "統一します", "after": "そろえます"}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.p("chapter_01.md")), "これは誤字です．\n表記をそろえます．\n")

    def test_conflicting_keys_stop(self):
        f = self.fixes([{"file": "chapter_01.md", "before": "誤時", "old": "これ", "after": "誤字"}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 1)
        self.assertIn("中身が違う", out)
        self.assertIn("誤時", read(self.p("chapter_01.md")))

    def test_bom_kept(self):
        with open(self.p("chapter_03.md"), "wb") as fh:
            fh.write(b"\xef\xbb\xbf" + "一行目です．\r\n".encode("utf-8"))
        f = self.fixes([{"file": "chapter_03.md", "before": "一行目", "after": "1行目"}])
        run("apply_fixes.py", [f, "--apply"], self.d)
        with open(self.p("chapter_03.md"), "rb") as fh:
            self.assertEqual(fh.read(), b"\xef\xbb\xbf" + "1行目です．\r\n".encode("utf-8"))

    def test_context_shown(self):
        f = self.fixes([{"file": "chapter_01.md", "before": "誤時", "after": "誤字"}])
        code, out, err = run("apply_fixes.py", [f], self.d)
        self.assertIn("前: これは【誤時】です", out)
        self.assertIn("後: これは【誤字】です", out)

    def test_split_word_warning(self):
        # 「にわか雨」の「わか」だけを置き換える巻き込み．1回しか現れないので一意の検査は通る
        write(self.p("chapter_04.md"), "午後はにわか雨でした．\n")
        f = self.fixes([{"file": "chapter_04.md", "before": "わか", "after": "分か"}])
        code, out, err = run("apply_fixes.py", [f], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("短い", out)
        self.assertIn("ひらがなの途中で切れている", out)
        code, out, err = run("apply_fixes.py", [f, "--apply", "--strict"], self.d)
        self.assertEqual(code, 1)
        self.assertIn("にわか雨", read(self.p("chapter_04.md")))

    def test_no_warning_at_word_boundary(self):
        f = self.fixes([{"file": "chapter_01.md", "before": "これは誤時です", "after": "これは誤字です"}])
        code, out, err = run("apply_fixes.py", [f], self.d)
        self.assertIn("警告 0 件", out)

    def test_count_warning(self):
        # 「aabb」の「ab」を「a」にすると，前の「a」とつながって「ab」がまたできる
        write(self.p("chapter_04.md"), "x aabb y\n")
        f = self.fixes([{"file": "chapter_04.md", "before": "ab", "after": "a"}])
        code, out, err = run("apply_fixes.py", [f], self.d)
        self.assertIn("before がまだ 1 回ある", out)

    def test_style_check_needs_config(self):
        f = self.fixes([{"file": "chapter_01.md", "before": "誤時です．", "after": "誤字です、"}])
        code, out, err = run("apply_fixes.py", [f], self.d)
        self.assertNotIn("禁止文字", out)
        write(self.p("_polish", "config.json"), json.dumps({"forbidden": {"読点、": "、"}}, ensure_ascii=False))
        code, out, err = run("apply_fixes.py", [f], self.d)
        self.assertIn("禁止文字 読点、 が 1 個増えた", out)

    def test_heading_check_with_config(self):
        write(self.p("chapter_05.md"), "## 1.6 練習問題\n\n## 2. まとめ\n")
        write(self.p("cfg.json"), json.dumps({"check_heading_number": True}))
        f = self.fixes([{"file": "chapter_05.md", "before": "1.6 練習", "after": "1.6練習"}])
        code, out, err = run("apply_fixes.py", [f, "--config", "cfg.json"], self.d)
        self.assertIn("見出しの番号のあとに空白が無い: ## 1.6練習問題", out)
        self.assertNotIn("2. まとめ", out)


class TestRoundReport(Base):
    def test_add_and_table(self):
        for args in (["--add", "1", "5", "10", "3"], ["--add", "2", "1", "4", "2"]):
            code, out, err = run("round_report.py", args, self.d)
            self.assertEqual(code, 0, err)
        code, out, err = run("round_report.py", [], self.d)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(self.p("_polish", "rounds.tsv")))
        self.assertIn("5", out)
        self.assertIn("1", out)

    def test_type_count(self):
        run("round_report.py", ["--type", "terms"], self.d)
        code, out, err = run("round_report.py", ["--type", "terms"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("2", out)
        self.assertIn("scan_recurring.py", out)  # 2回目は原稿全体を洗うよう促す


class TestScanRecurring(Base):
    def test_list(self):
        code, out, err = run("scan_recurring.py", ["--list"], self.d)
        self.assertEqual(code, 0, err)
        for key in ("terms", "forbidden", "heading"):
            self.assertIn(key, out)

    def test_no_manuscript(self):
        code, out, err = run("scan_recurring.py", [], self.d)
        self.assertEqual(code, 1)

    def test_forbidden(self):
        write(self.p("chapter_01.md"), "読点は、使わない．（全角括弧）も使わない．\n")
        code, out, err = run("scan_recurring.py", ["--type", "forbidden"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("ch01.md:1", out)  # 表示では chapter_ を ch に縮める
        self.assertIn("全角括弧", out)
        self.assertIn("読点、", out)

    def test_terms_from_config(self):
        write(self.p("chapter_01.md"), "樹形図を描く．デンドログラムを読む．\n")
        write(self.p("_polish", "config.json"),
              json.dumps({"terms": [["デンドログラム", "樹形図"]]}, ensure_ascii=False))
        code, out, err = run("scan_recurring.py", ["--type", "terms"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("「樹形図」1 件", out)

    def test_no_terms_without_config(self):
        # 用語の組は config で渡す．既定では何も検出しない
        write(self.p("chapter_01.md"), "樹形図を描く．デンドログラムを読む．\n")
        code, out, err = run("scan_recurring.py", ["--type", "terms"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("0 件", out)

    def test_fig_leaf_needs_config(self):
        # 図の生成元を config に書かなければ，この型は何も数えない
        write(self.p("chapter_01.md"), "本文です．\n")
        code, out, err = run("scan_recurring.py", ["--type", "fig-leaf"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("0 件", out)

    def test_fig_leaf_with_config(self):
        write(self.p("chapter_01.md"), "ヒストグラムを使います．\n")
        write(self.p("make_fig.R"), 'paths <- list(\n  c("見せたいのは", "ヒストグラム"),\n  c("見せたいのは", "バイオリン図"),\n)\n')
        write(self.p("_polish", "config.json"), json.dumps({"figure_sources": ["make_fig.R"]}))
        code, out, err = run("scan_recurring.py", ["--type", "fig-leaf"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("バイオリン図", out)
        self.assertNotIn("「ヒストグラム」", out)

    def test_glob(self):
        write(self.p("body", "a.md"), "読点は、使わない．\n")
        code, out, err = run("scan_recurring.py", ["--type", "forbidden", "--glob", "body/*.md"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("a.md:1", out)


class TestCalibrate(Base):
    def test_hit_miss_false_alarm(self):
        write(self.p("chapter_01.md"), "これは誤時です．冗長な表現をすることができます．最後の文です．\n")
        ai = [{"file": "chapter_01.md", "before": "誤時", "after": "誤字"},
              {"file": "chapter_01.md", "before": "最後の文", "after": "最後の一文"}]
        human = [{"file": "chapter_01.md", "old": "誤時です", "new": "誤字です"},
                 {"file": "chapter_01.md", "old": "することができます", "new": "できます"}]
        write(self.p("ai.json"), json.dumps(ai, ensure_ascii=False))
        write(self.p("human.json"), json.dumps(human, ensure_ascii=False))
        code, out, err = run("calibrate.py", ["--ai", "ai.json", "--human", "human.json"], self.d)
        self.assertEqual(code, 0, err)
        rows = read(self.p("_polish", "calibration.tsv")).splitlines()[1:]
        kinds = sorted(r.split("\t")[0] for r in rows)
        self.assertEqual(kinds, ["拾えた", "空振り", "見逃し"])


if __name__ == "__main__":
    unittest.main()
