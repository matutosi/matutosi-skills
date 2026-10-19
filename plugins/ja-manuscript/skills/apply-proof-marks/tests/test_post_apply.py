#!/usr/bin/env python3
"""post_apply.py の自己テスト.  python tests/test_post_apply.py"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "post_apply.py")
PY = sys.executable.replace("\\", "/")


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def write(repo, rel, text):
    p = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read(repo, rel):
    with open(os.path.join(repo, rel), encoding="utf-8") as fh:
        return fh.read()


def pycmd(code):
    """シェルを通せる python -c のコマンド."""
    return '"%s" -c "%s"' % (PY, code.replace('"', '\\"'))


class PostApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = self.tmp.name
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "core.autocrlf", "false")
        write(self.repo, "chapter_01.md", "a\n")
        for n in ("fig_a", "fig_b", "fig_c"):
            write(self.repo, "figures/%s.pdf" % n, "orig\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        write(self.repo, "chapter_01.md", "b\n")  # 原稿を変更 (未コミット)

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, steps, check=None):
        cfg = {"steps": steps, "restore_globs": ["figures/*"]}
        if check:
            cfg["check"] = check
        # 設定ファイルは作業ツリーの外に置く (変更ファイルに数えない)
        path = os.path.join(self.tmp.name + "_cfg.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        self.addCleanup(os.remove, path)
        return path

    def run_pa(self, *args):
        r = subprocess.run([sys.executable, SCRIPT, "--repo", self.repo, *args],
                           capture_output=True)
        return r.returncode, r.stdout.decode("utf-8", "replace")

    def exists(self, rel):
        return os.path.exists(os.path.join(self.repo, rel))

    def test_a_skip_when_not_matched(self):
        cfg = self.config([
            {"name": "対象外", "cmd": pycmd("open('ran.txt','w').write('x')"),
             "when_changed": ["other_*.md"]},
            {"name": "対象", "cmd": pycmd("open('ran2.txt','w').write('x')"),
             "when_changed": ["chapter_*.md"]},
        ])
        code, out = self.run_pa("--config", cfg)
        self.assertEqual(code, 0, out)
        self.assertFalse(self.exists("ran.txt"))
        self.assertTrue(self.exists("ran2.txt"))
        self.assertIn("対象外: 飛ばした", out)

    def test_b_restore_unintended(self):
        write(self.repo, "figures/fig_c.pdf", "mine\n")  # ステップの前から未コミット
        body = ("import pathlib;"
                "[pathlib.Path('figures/%s.pdf'%n).write_text('new\\n') "
                "for n in ('fig_a','fig_b','fig_c')]")
        cfg = self.config([{"name": "再生成", "cmd": pycmd(body),
                            "when_changed": ["chapter_*.md"]}])
        code, out = self.run_pa("--config", cfg, "--intended", "figures/fig_a.pdf")
        self.assertEqual(code, 0, out)
        self.assertEqual(read(self.repo, "figures/fig_a.pdf"), "new\n")
        self.assertEqual(read(self.repo, "figures/fig_b.pdf"), "orig\n")
        self.assertEqual(read(self.repo, "figures/fig_c.pdf"), "new\n")  # 戻さない
        self.assertIn("figures/fig_b.pdf", out)

    def test_c_failure_continues(self):
        cfg = self.config(
            [{"name": "失敗", "cmd": pycmd("import sys;sys.exit(3)")},
             {"name": "次", "cmd": pycmd("open('next.txt','w').write('x')")}],
            check={"name": "点検",
                   "cmd": pycmd("open('chk.txt','w').write('x');print('CHECK-OK')")})
        code, out = self.run_pa("--config", cfg)
        self.assertEqual(code, 1)
        self.assertTrue(self.exists("next.txt"))
        self.assertTrue(self.exists("chk.txt"))
        self.assertIn("失敗: 失敗", out)
        self.assertIn("CHECK-OK", out)

    def test_d_dry_run(self):
        cfg = self.config(
            [{"name": "S", "cmd": pycmd("open('ran.txt','w').write('x')")}],
            check={"name": "点検", "cmd": pycmd("open('chk.txt','w').write('x')")})
        code, out = self.run_pa("--config", cfg, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertFalse(self.exists("ran.txt"))
        self.assertFalse(self.exists("chk.txt"))
        self.assertIn("dry-run", out)


if __name__ == "__main__":
    unittest.main()
