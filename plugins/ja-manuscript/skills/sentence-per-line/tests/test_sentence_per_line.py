#!/usr/bin/env python3
"""sentence_per_line.py の自己テスト (外部ライブラリ不要).

    python tests/test_sentence_per_line.py
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "sentence_per_line.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from sentence_per_line import process  # noqa: E402


class TestProcess(unittest.TestCase):
    def test_split_sentences(self):
        self.assertEqual(process("一文目です．二文目です．\n"), "一文目です．\n二文目です．\n")

    def test_maru_and_marks(self):
        self.assertEqual(process("はい。本当？そうです！\n"), "はい。\n本当？\nそうです！\n")

    def test_closing_bracket_stays(self):
        # 文末に続く閉じ括弧・引用符は前の文に付き，その後ろで割る
        # (括弧の中に句点を打つと「」と言った」の前でも割れる．括弧内には句点を打たない書き方を前提にしている)
        self.assertEqual(process("「そうです．」次です．\n"),
                         "「そうです．」\n次です．\n")
        self.assertEqual(process("（注意．）次です．\n"), "（注意．）\n次です．\n")

    def test_wrapped_lines_are_joined(self):
        self.assertEqual(process("途中で折り返された\n文です．次の文です．\n"),
                         "途中で折り返された文です．\n次の文です．\n")

    def test_blank_lines_collapsed(self):
        self.assertEqual(process("段落1です．\n\n\n\n段落2です．\n"), "段落1です．\n\n段落2です．\n")

    def test_code_block_untouched(self):
        src = "前です．\n\n```r\nx <- 1. y <- 2.\n# コメント．もう1つ．\n```\n\n後です．\n"
        self.assertEqual(process(src), src)

    def test_quote_split_only_within_line(self):
        src = "> 一文目．二文目．\n> 三文目．\n"
        self.assertEqual(process(src), "> 一文目．\n> 二文目．\n> 三文目．\n")

    def test_heading_untouched(self):
        src = "# 見出し．です\n\n本文です．\n"
        self.assertEqual(process(src), src)

    def test_idempotent(self):
        src = "一文目です．二文目です．\n\n> 引用．引用2．\n"
        once = process(src)
        self.assertEqual(process(once), once)


class TestCli(unittest.TestCase):
    def run_cli(self, args, stdin=None):
        return subprocess.run([sys.executable, SCRIPT] + args, input=stdin,
                              capture_output=True)

    def test_stdin(self):
        r = self.run_cli(["-"], "あ．い．\n".encode("utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.assertEqual(r.stdout.decode("utf-8").replace("\r\n", "\n"), "あ．\nい．\n")

    def test_file_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("あ．い．\n")
            r = self.run_cli([p])
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            with open(p, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "あ．\nい．\n")


if __name__ == "__main__":
    unittest.main()
