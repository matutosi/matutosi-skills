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

    def test_same_file_written_two_ways_keeps_every_fix(self):
        # "chapter_01.md" と "./chapter_01.md" は同じファイル．別扱いにして先の置換が消えてはいけない
        f = self.fixes([{"file": "chapter_01.md", "before": "誤時", "after": "誤字"},
                        {"file": "./chapter_01.md", "before": "統一", "after": "統合"}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 0, err)
        text = read(self.p("chapter_01.md"))
        self.assertIn("誤字", text)
        self.assertIn("統合", text)

    def test_overlapping_before_stops_and_writes_nothing(self):
        # 2 件目の before が，1 件目で書き換わった所にかかるときは，当てられないものとして止める
        write(self.p("chapter_02.md"), "AAA BBB CCC\n")
        f = self.fixes([{"file": "chapter_02.md", "before": "AAA BBB", "after": "X"},
                        {"file": "chapter_02.md", "before": "BBB CCC", "after": "Y"}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 1)
        self.assertIn("当てられない", out)
        self.assertEqual(read(self.p("chapter_02.md")), "AAA BBB CCC\n")

    def test_mixed_line_endings_are_kept_byte_for_byte(self):
        with open(self.p("chapter_03.md"), "wb") as fh:
            fh.write("一行目です．\r\n二行目です．\n三行目です．\r\n".encode("utf-8"))
        f = self.fixes([{"file": "chapter_03.md", "before": "二行目です", "after": "二行目でした"}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 0, err)
        with open(self.p("chapter_03.md"), "rb") as fh:
            self.assertEqual(fh.read(),
                             "一行目です．\r\n二行目でした．\n三行目です．\r\n".encode("utf-8"))

    def test_kind_classifies_characters(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("apply_fixes", os.path.join(SCRIPTS, "apply_fixes.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.kind("語"), "漢字")
        self.assertEqual(mod.kind("々"), "漢字")
        self.assertEqual(mod.kind("あ"), "ひらがな")
        self.assertEqual(mod.kind("ア"), "カタカナ")
        self.assertEqual(mod.kind("ｱ"), "カタカナ")        # 半角カナ
        self.assertEqual(mod.kind("a"), "英数字")
        self.assertEqual(mod.kind("Ａ"), "英数字")          # 全角英数
        self.assertEqual(mod.kind("７"), "英数字")
        self.assertIsNone(mod.kind("，"))

    def test_quiet_and_context_zero(self):
        f = self.fixes([{"file": "chapter_01.md", "before": "誤時", "after": "誤字"}])
        code, out, err = run("apply_fixes.py", [f, "--quiet"], self.d)
        self.assertEqual(code, 0, err)
        self.assertNotIn("前:", out)
        code, out, err = run("apply_fixes.py", [f, "--context", "0"], self.d)
        self.assertEqual(code, 0, err)

    def test_post_runs_the_check_command_from_config(self):
        f = self.fixes([{"file": "chapter_01.md", "before": "誤時", "after": "誤字"}])
        write(self.p("_polish", "config.json"), json.dumps(
            {"check": "python -c \"open('checked.txt','w').write('x')\""}))
        code, out, err = run("apply_fixes.py", [f, "--apply", "--post"], self.d)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.exists(self.p("checked.txt")))

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

    def test_count_replaces_all_when_number_matches(self):
        # 全体置換: count を付ければ，ちょうどその数のときだけ全部を置き換える
        f = self.fixes([{"file": "chapter_01.md", "before": "す．", "after": "す。", "count": 2}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.p("chapter_01.md")), "これは誤時です。\n表記を統一します。\n")
        self.assertIn("(1/2)", out)

    def test_count_mismatch_stops(self):
        # count が実際の数と違えば，何も書かずに止まる (想定外の箇所を見つける)
        f = self.fixes([{"file": "chapter_01.md", "before": "す．", "after": "す。", "count": 3}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 1)
        self.assertIn("2 件ヒット (3 件のはず)", out)
        self.assertNotIn("す。", read(self.p("chapter_01.md")))

    def test_count_all_occurrences_with_different_lengths(self):
        write(self.p("chapter_03.md"), "A 図です．B 図です．C 図です．\n")
        f = self.fixes([{"file": "chapter_03.md", "before": "図です", "after": "グラフです", "count": 3}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.p("chapter_03.md")), "A グラフです．B グラフです．C グラフです．\n")

    def test_count_in_tsv(self):
        write(self.p("fixes.tsv"), "chapter_01.md\tす．\tす。\t2\n")
        code, out, err = run("apply_fixes.py", ["fixes.tsv", "--apply"], self.d)
        self.assertEqual(code, 0, err)
        self.assertEqual(read(self.p("chapter_01.md")).count("す。"), 2)

    def test_bad_count_is_rejected(self):
        f = self.fixes([{"file": "chapter_01.md", "before": "誤時", "after": "誤字", "count": 0}])
        code, out, err = run("apply_fixes.py", [f, "--apply"], self.d)
        self.assertEqual(code, 1)
        self.assertIn("count", out)

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
        # 禁止文字は config の forbidden に書いたものだけを見る (SKILL.md の約束)
        write(self.p("chapter_01.md"), "読点は、使わない．（全角括弧）も使わない．\n")
        write(self.p("_polish", "config.json"),
              json.dumps({"forbidden": {"全角括弧": "（", "読点、": "、"}}, ensure_ascii=False))
        code, out, err = run("scan_recurring.py", ["--type", "forbidden"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("ch01.md:1", out)  # 表示では chapter_ を ch に縮める
        self.assertIn("全角括弧", out)
        self.assertIn("読点、", out)

    def test_forbidden_needs_config(self):
        write(self.p("chapter_01.md"), "読点は、使わない．（全角括弧）も使わない．\n")
        code, out, err = run("scan_recurring.py", ["--type", "forbidden"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("0 件", out)

    def test_forbidden_skips_code_blocks(self):
        write(self.p("chapter_01.md"), "本文です．\n\n```r\nx <- c(1、2)\n```\n")
        write(self.p("_polish", "config.json"),
              json.dumps({"forbidden": {"読点、": "、"}}, ensure_ascii=False))
        code, out, err = run("scan_recurring.py", ["--type", "forbidden"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("0 件", out)

    def test_config_with_bom(self):
        write(self.p("chapter_01.md"), "読点は、使わない．\n")
        write(self.p("_polish", "config.json"),
              "﻿" + json.dumps({"forbidden": {"読点、": "、"}}, ensure_ascii=False))
        code, out, err = run("scan_recurring.py", ["--type", "forbidden"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("読点、", out)

    def test_unknown_type_is_an_error(self):
        write(self.p("chapter_01.md"), "本文です．\n")
        code, out, err = run("scan_recurring.py", ["--type", "no-such-type"], self.d)
        self.assertNotEqual(code, 0)
        self.assertIn("no-such-type", out + err)

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
        write(self.p("_polish", "config.json"),
              json.dumps({"forbidden": {"読点、": "、"}}, ensure_ascii=False))
        code, out, err = run("scan_recurring.py", ["--type", "forbidden", "--glob", "body/*.md"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("a.md:1", out)


class TestScanTypes(Base):
    """scan_recurring.py の型ごとの照合 (検出するものと，しないもの)．"""

    def scan(self, key, text, config=None, name="chapter_01.md"):
        write(self.p(name), text)
        if config is not None:
            write(self.p("_polish", "config.json"), json.dumps(config, ensure_ascii=False))
        code, out, err = run("scan_recurring.py", ["--type", key], self.d)
        self.assertEqual(code, 0, err)
        return out

    def test_next(self):
        out = self.scan("next", "次の3つを示す．\n次の図を見る．\n")
        self.assertIn("ch01.md:1", out)
        self.assertNotIn("ch01.md:2", out)

    def test_plain_style(self):
        out = self.scan("plain", "これは結果である．\nこれは結果です．\n- 箇条書きである．\n")
        self.assertIn("ch01.md:1", out)
        self.assertNotIn("ch01.md:2", out)
        self.assertNotIn("ch01.md:3", out)      # 箇条書きの行は見ない

    def test_becomes(self):
        out = self.scan("becomes", "結果になります．\n便利になります．\n")
        self.assertIn("ch01.md:1", out)
        self.assertNotIn("ch01.md:2", out)

    def test_donoun(self):
        out = self.scan("donoun", "検討を行う．\n確認します．\n")
        self.assertIn("ch01.md:1", out)
        self.assertNotIn("ch01.md:2", out)

    def test_terms_do_not_match_a_longer_word(self):
        # 「目盛」を誤とするとき，正の「目盛り」の中の「目盛」は数えない
        out = self.scan("terms", "目盛りを付ける．目盛を付ける．\n",
                        config={"terms": [["目盛り", "目盛"]]})
        self.assertIn("「目盛」1 件", out)

    def test_heading_number_space(self):
        out = self.scan("heading", "## 1.2見出し\n## 1.2 見出し\n## 4組は\n")
        self.assertIn("ch01.md:1", out)
        self.assertNotIn("ch01.md:2", out)
        self.assertNotIn("ch01.md:3", out)      # 「4組」は節番号ではない

    def test_selfref(self):
        text = "# 第1章 はじめに {#ch-intro}\n本文は \\@ref(ch-intro) を指す．\n他は \\@ref(ch-other) を指す．\n"
        out = self.scan("selfref", text)
        self.assertIn("ch01.md:2", out)
        self.assertNotIn("ch01.md:3", out)

    def test_exercises_count_mismatch(self):
        text = ("## 1.5 練習問題 {#ex}\n\n1. 問1\n2. 問2\n\n"
                "## 1.6 練習問題の解答例 {#ans}\n\n### 解答 1\n答え\n")
        out = self.scan("exercises", text)
        self.assertIn("問 2 / 解答 1", out)

    def test_axis_internal_name(self):
        text = "本文\n\n```r\nggplot(d) + labs(x = reorder(Var1, n))\nggplot(d) + labs(x = \"密度\")\n```\n"
        out = self.scan("axis", text)
        self.assertIn("ch01.md:4", out)
        self.assertNotIn("ch01.md:5", out)

    def test_lablang_mismatch(self):
        text = ("```r\n# code_01_01_R\nggplot(d) + labs(x = \"密度\")\n```\n\n"
                "```python\n# code_01_01_py\nax.set_xlabel(\"density\")\n```\n")
        out = self.scan("lablang", text)
        self.assertIn("code_01_01", out)

    def test_clean_manuscript_has_no_hits(self):
        text = "# 第1章 はじめに {#ch-intro}\n\nこれは結果です．次に進みます．\n"
        out = self.scan("next", text)
        self.assertIn("0 件", out)


class TestCalibrate(Base):
    def test_target_with_newline_keeps_one_row_per_item(self):
        # 対象に改行を含む指摘でも，明細 (TSV) の行が割れない
        write(self.p("chapter_01.md"), "1行目です．\n2行目です．\n3行目です．\n")
        ai = [{"file": "chapter_01.md", "before": "1行目です．\n2行目", "after": "x"}]   # 空振りになる
        human = [{"file": "chapter_01.md", "old": "3行目です", "new": "y"}]            # 見逃しになる
        write(self.p("ai.json"), json.dumps(ai, ensure_ascii=False))
        write(self.p("human.json"), json.dumps(human, ensure_ascii=False))
        code, out, err = run("calibrate.py", ["--ai", "ai.json", "--human", "human.json"], self.d)
        self.assertEqual(code, 0, err)
        rows = read(self.p("_polish", "calibration.tsv")).splitlines()
        self.assertEqual(len(rows), 1 + 2)         # 見出し + 「見逃し」1 件 + 「空振り」1 件
        self.assertTrue(all(r.count("\t") == 4 for r in rows), rows)

    def test_unlocatable_target_is_reported(self):
        write(self.p("chapter_01.md"), "これは本文です．\n")
        ai = [{"file": "chapter_01.md", "before": "ない文字列", "after": "x"}]
        human = [{"file": "chapter_01.md", "old": "本文", "new": "y"}]
        write(self.p("ai.json"), json.dumps(ai, ensure_ascii=False))
        write(self.p("human.json"), json.dumps(human, ensure_ascii=False))
        code, out, err = run("calibrate.py", ["--ai", "ai.json", "--human", "human.json"], self.d)
        self.assertEqual(code, 0, err)
        self.assertIn("不能 1", out)
        self.assertIn("baseline に 0 回", out)

    def test_slack_matches_neighbours(self):
        write(self.p("chapter_01.md"), "AAAAABBBBB\n")
        ai = [{"file": "chapter_01.md", "before": "AAAAA", "after": "x"}]
        human = [{"file": "chapter_01.md", "old": "BBBBB", "new": "y"}]
        write(self.p("ai.json"), json.dumps(ai))
        write(self.p("human.json"), json.dumps(human))
        code, out, err = run("calibrate.py", ["--ai", "ai.json", "--human", "human.json"], self.d)
        self.assertIn("拾えた   : 0", out)           # 隣り合うだけでは重ならない
        code, out, err = run("calibrate.py", ["--ai", "ai.json", "--human", "human.json",
                                              "--slack", "1"], self.d)
        self.assertIn("拾えた   : 1", out)

    def test_fixes_with_bom(self):
        write(self.p("chapter_01.md"), "これは誤時です．\n")
        ai = [{"file": "chapter_01.md", "before": "誤時", "after": "誤字"}]
        human = [{"file": "chapter_01.md", "old": "誤時です", "new": "誤字です"}]
        write(self.p("ai.json"), "﻿" + json.dumps(ai, ensure_ascii=False))
        write(self.p("human.json"), "﻿" + json.dumps(human, ensure_ascii=False))
        code, out, err = run("calibrate.py", ["--ai", "ai.json", "--human", "human.json"], self.d)
        self.assertEqual(code, 0, err)

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
