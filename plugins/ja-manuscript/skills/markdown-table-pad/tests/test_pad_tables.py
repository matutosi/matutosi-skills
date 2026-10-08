#!/usr/bin/env python3
"""pad_tables.py の自己テスト (外部ライブラリ不要).

    python tests/test_pad_tables.py
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "pad_tables.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from pad_tables import pad_tables, str_width  # noqa: E402


class TestWidth(unittest.TestCase):
    def test_width(self):
        self.assertEqual(str_width("abc"), 3)
        self.assertEqual(str_width("全角"), 4)
        self.assertEqual(str_width("ｶﾅ"), 2)  # 半角カナは1


class TestPad(unittest.TestCase):
    def test_ascii(self):
        src = "| a | bbb |\n|---|---|\n| cc | d |\n"
        # 列の幅は区切り行の --- に合わせて最小 3
        self.assertEqual(pad_tables(src), "| a   | bbb |\n| --- | --- |\n| cc  | d   |\n")

    def test_fullwidth(self):
        src = "| a | 長い列 |\n|---|---|\n| 全角あ | b |\n"
        self.assertEqual(pad_tables(src),
                         "| a      | 長い列 |\n| ------ | ------ |\n| 全角あ | b      |\n")

    def test_alignment_colons_kept(self):
        out = pad_tables("| a | b | c |\n|:--|:-:|--:|\n| 1 | 2 | 3 |\n")
        sep = out.splitlines()[1]
        cells = [c.strip() for c in sep.strip("|").split("|")]
        self.assertTrue(cells[0].startswith(":") and not cells[0].endswith(":"))
        self.assertTrue(cells[1].startswith(":") and cells[1].endswith(":"))
        self.assertTrue(cells[2].endswith(":") and not cells[2].startswith(":"))

    def test_text_outside_tables_untouched(self):
        src = "本文 | 縦棒を含む行．\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n後の本文．\n"
        out = pad_tables(src)
        self.assertTrue(out.startswith("本文 | 縦棒を含む行．\n\n"))
        self.assertTrue(out.endswith("\n\n後の本文．\n"))

    def test_idempotent(self):
        once = pad_tables("| a | 長い列 |\n|---|---|\n| 全角あ | b |\n")
        self.assertEqual(pad_tables(once), once)


class TestCli(unittest.TestCase):
    def run_cli(self, args, stdin=None):
        return subprocess.run([sys.executable, SCRIPT] + args, input=stdin, capture_output=True)

    def test_stdin(self):
        r = self.run_cli(["-"], "| a | 長い列 |\n|---|---|\n| 全角あ | b |\n".encode("utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.assertEqual(r.stdout.decode("utf-8").replace("\r\n", "\n").splitlines()[2],
                         "| 全角あ | b      |")

    def test_file_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("| a | bbb |\n|---|---|\n| cc | d |\n")
            r = self.run_cli([p])
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
            with open(p, encoding="utf-8") as fh:
                self.assertEqual(fh.read().splitlines()[2], "| cc  | d   |")


if __name__ == "__main__":
    unittest.main()
