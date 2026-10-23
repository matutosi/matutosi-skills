#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""decisions.py と split_commits.py の自己テスト (標準ライブラリと git だけ).

    python tests/test_decisions.py

一時ディレクトリに git init した小さなリポジトリを作って試す。
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
FIXES = os.path.join(HERE, "..", "scripts", "apply_fixes.py")


def run(script, args, cwd):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + list(args),
                       cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")


def git(cwd, *args):
    r = subprocess.run(["git"] + list(args), cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace"))
    return r.stdout.decode("utf-8")


def write(path, data):
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        git(self.d, "init", "-q")
        git(self.d, "config", "user.email", "t@example.com")
        git(self.d, "config", "user.name", "tester")
        git(self.d, "config", "core.autocrlf", "false")
        self.dec = os.path.join(self.d, "decisions.json")

    def tearDown(self):
        self._tmp.cleanup()

    def p(self, *names):
        return os.path.join(self.d, *names)

    def commit_all(self, msg="init"):
        git(self.d, "add", "-A")
        git(self.d, "commit", "-q", "-m", msg)

    def add(self, did, label, old, new, status="approved", file="a.md", extra=()):
        items = json.dumps([{"file": file, "old": old, "new": new}], ensure_ascii=False)
        code, out, err = run("decisions.py", ["--file", self.dec, "add", "--id", did, "--tag", "t",
                                              "--label", label, "--items-json", items,
                                              "--status", status] + list(extra), self.d)
        self.assertEqual(code, 0, err)

    def log(self):
        return git(self.d, "log", "--format=%s").splitlines()


class TestDecisions(Base):
    def test_add_overwrite_list_status(self):
        self.add("K1", "一つ目", "あ", "い", status="pending")
        self.add("K1", "一つ目 (改)", "あ", "う", status="pending")
        self.add("K2", "二つ目", "か", "き")
        data = json.loads(read(self.dec).decode("utf-8"))
        self.assertEqual([x["id"] for x in data["decisions"]], ["K1", "K2"])
        self.assertEqual(data["decisions"][0]["label"], "一つ目 (改)")
        code, out, err = run("decisions.py", ["--file", self.dec, "status", "K1", "approved"], self.d)
        self.assertEqual(code, 0, err)
        code, out, err = run("decisions.py", ["--file", self.dec, "list", "--status", "approved"], self.d)
        self.assertIn("K1", out)
        self.assertIn("(2 件)", out)

    def test_to_fixes_excludes_and_applies(self):
        write(self.p("a.md"), "フローの図です．\nここは直さない部分です．\n別の語も使う．\n")
        self.add("K18", "流れにする", "フローの", "流れの")
        self.add("K19", "直さない", "直さない", "直す", status="rejected")
        self.add("K20", "待ち", "別の語", "他の語", status="pending")
        out_path = self.p("fixes.json")
        code, out, err = run("decisions.py", ["--file", self.dec, "to-fixes", "--ids", "K18,K19,K20",
                                              "--out", out_path], self.d)
        self.assertEqual(code, 0, err)
        rows = json.loads(read(out_path).decode("utf-8"))
        self.assertEqual(rows, [{"file": "a.md", "old": "フローの", "new": "流れの"}])
        r = subprocess.run([sys.executable, FIXES, "fixes.json", "--apply"], cwd=self.d,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.assertIn("流れの図です", read(self.p("a.md")).decode("utf-8"))
        code, out, err = run("decisions.py", ["--file", self.dec, "mark-applied", "--ids", "K18"], self.d)
        self.assertEqual(code, 0, err)
        data = json.loads(read(self.dec).decode("utf-8"))
        self.assertEqual(data["decisions"][0]["status"], "applied")


class TestSplitCommits(Base):
    BASE = ("第1行はそのままです．\n"
            "フローの図を見ます．\n"
            "第3行もそのままです．\n"
            "第4行もそのままです．\n"
            "第5行もそのままです．\n"
            "ここで平均を使います．\n"
            "第7行もそのままです．\n"
            "第8行もそのままです．\n"
            "第9行もそのままです．\n"
            "ここに誤字がある．\n")

    def setup_repo(self, bom=False, crlf=False):
        text = self.BASE.replace("\n", "\r\n") if crlf else self.BASE
        data = text.encode("utf-8")
        if bom:
            data = b"\xef\xbb\xbf" + data
        self.bom, self.crlf = bom, crlf
        write(self.p("a.md"), data)
        write(self.p("fig.png"), b"\x89PNG\x00old")
        write(self.p("b.md"), "別の章です．\n")
        self.commit_all()
        nl = "\r\n" if crlf else "\n"
        new = (text.replace("フローの", "流れの")
                   .replace("平均を", "中央値を")
                   .replace("誤字がある", "誤りがある"))
        data2 = new.encode("utf-8")
        if bom:
            data2 = b"\xef\xbb\xbf" + data2
        write(self.p("a.md"), data2)
        write(self.p("b.md"), "別の章です．" + nl + "追記です．" + nl)
        write(self.p("fig.png"), b"\x89PNG\x00new")
        self.add("K1", "「フロー」を「流れ」にする", "フローの", "流れの", extra=["--files", "fig.png"])
        self.add("K2", "「平均」を「中央値」にする", "平均を", "中央値を")

    def split(self, *extra):
        return run("split_commits.py", ["--file", self.dec] + list(extra), self.d)

    def test_split_two_decisions_and_other(self):
        self.setup_repo()
        code, out, err = self.split()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.log(), ["その他の変更", "「平均」を「中央値」にする",
                                      "「フロー」を「流れ」にする", "init"])
        # K1: 流れだけ (a.md と fig.png)
        show1 = git(self.d, "show", "--format=", "HEAD~2", "--stat")
        self.assertIn("fig.png", show1)
        diff_k2 = git(self.d, "show", "--format=", "HEAD~1")
        self.assertIn("+ここで中央値を使います．", diff_k2)
        self.assertNotIn("流れの", diff_k2)
        self.assertNotIn("誤りがある", diff_k2)
        diff_k1 = git(self.d, "show", "--format=", "HEAD~2")
        self.assertIn("流れの", diff_k1)
        self.assertNotIn("中央値", diff_k1)
        # other: 決定に関係ない誤字の直しと b.md が1つに入る
        diff_o = git(self.d, "show", "--format=", "HEAD")
        self.assertIn("誤りがある", diff_o)
        self.assertIn("b.md", diff_o)
        self.assertNotIn("中央値", diff_o)
        # 未コミットが無い (decisions.json 以外)
        status = [l for l in git(self.d, "status", "--porcelain").splitlines() if "decisions.json" not in l]
        self.assertEqual(status, [])
        self.assertIn("a.md", git(self.d, "show", "--format=", "--name-only", "HEAD"))

    def test_skip_other_leaves_other_uncommitted(self):
        self.setup_repo()
        code, out, err = self.split("--skip-other")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.log(), ["「平均」を「中央値」にする", "「フロー」を「流れ」にする", "init"])
        status = git(self.d, "status", "--porcelain")
        self.assertIn("b.md", status)
        self.assertIn("a.md", status)  # 誤字の直しのハンクが残る
        self.assertIn("誤りがある", git(self.d, "diff", "a.md"))

    def test_skip_other_dry_run_still_lists_other(self):
        self.setup_repo()
        before = git(self.d, "rev-parse", "HEAD")
        code, out, err = self.split("--skip-other", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(git(self.d, "rev-parse", "HEAD"), before)
        self.assertIn("other", out)

    def test_dry_run_commits_nothing(self):
        self.setup_repo()
        before = git(self.d, "rev-parse", "HEAD")
        code, out, err = self.split("--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(git(self.d, "rev-parse", "HEAD"), before)
        self.assertIn("K1", out)
        self.assertIn("K2", out)
        self.assertIn("other", out)
        self.assertIn("a.md", git(self.d, "status", "--porcelain"))

    def test_rejected_goes_to_other(self):
        self.setup_repo()
        run("decisions.py", ["--file", self.dec, "status", "K2", "rejected"], self.d)
        code, out, err = self.split()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.log(), ["その他の変更", "「フロー」を「流れ」にする", "init"])
        self.assertIn("中央値", git(self.d, "show", "--format=", "HEAD"))

    def test_trailer(self):
        self.setup_repo()
        write(self.p("trailer.txt"), "Co-Authored-By: Someone <s@example.com>\n")
        code, out, err = self.split("--trailer-file", self.p("trailer.txt"))
        self.assertEqual(code, 0, out + err)
        msg = git(self.d, "log", "-1", "--format=%B", "HEAD~1")
        self.assertIn("Co-Authored-By: Someone", msg)

    def test_bom_and_crlf_preserved(self):
        self.setup_repo(bom=True, crlf=True)
        expected = read(self.p("a.md"))
        code, out, err = self.split()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(read(self.p("a.md")), expected)
        self.assertEqual(len(self.log()), 4)
        # コミットされた中身も BOM・CRLF のまま
        blob = subprocess.run(["git", "show", "HEAD:a.md"], cwd=self.d, stdout=subprocess.PIPE).stdout
        self.assertEqual(blob, expected)
        self.assertTrue(blob.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", blob)
        diff_k2 = git(self.d, "show", "--format=", "HEAD~1")
        self.assertIn("中央値を使います", diff_k2)
        self.assertNotIn("流れの", diff_k2)

    def test_same_hunk_two_decisions_warns(self):
        write(self.p("a.md"), "フローの平均を見る．\n")
        self.commit_all()
        write(self.p("a.md"), "流れの中央値を見る．\n")
        self.add("K1", "流れ", "フローの", "流れの")
        self.add("K2", "中央値", "平均を", "中央値を")
        code, out, err = self.split()
        self.assertEqual(code, 0, out + err)
        self.assertIn("警告", err)
        self.assertEqual(self.log(), ["流れ", "init"])


class TestGroupByTag(Base):
    def setup_repo(self):
        write(self.p("a.md"), "あ1\nい\nい\nい\nう2\nい\nい\nい\nえ3\nい\nい\nい\nお4\n")
        self.commit_all()
        write(self.p("a.md"), "あ一\nい\nい\nい\nう二\nい\nい\nい\nえ三\nい\nい\nい\nお四\n")
        self.add("T1", "一にする", "あ1", "あ一", extra=["--tag", "x"])
        self.add("T2", "二にする", "う2", "う二", extra=["--tag", "x"])
        self.add("T3", "三にする", "え3", "え三", extra=["--tag", "x"])
        self.add("U1", "四にする", "お4", "お四", extra=["--tag", "y"])

    def split(self, *extra):
        return run("split_commits.py", ["--file", self.dec] + list(extra), self.d)

    def test_group_by_tag(self):
        self.setup_repo()
        code, out, err = self.split("--group-by-tag")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.log(), ["四にする", "一にする", "init"])
        dx = git(self.d, "show", "--format=", "HEAD~1")
        for s in ("あ一", "う二", "え三"):
            self.assertIn(s, dx)
        self.assertNotIn("お四", dx)
        dy = git(self.d, "show", "--format=", "HEAD")
        self.assertIn("お四", dy)
        self.assertNotIn("あ一", dy)

    def test_skip_other_with_group_by_tag(self):
        self.setup_repo()
        write(self.p("b.md"), "決定に関係ない新しい章です．" + chr(10))
        code, out, err = self.split("--group-by-tag", "--skip-other")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.log(), ["四にする", "一にする", "init"])
        self.assertIn("b.md", git(self.d, "status", "--porcelain"))

    def test_tag_label(self):
        self.setup_repo()
        code, out, err = self.split("--group-by-tag", "--tag-label", "x=まとめて数字にする")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.log(), ["四にする", "まとめて数字にする", "init"])

    def test_tag_label_needs_group_by_tag(self):
        self.setup_repo()
        code, out, err = self.split("--tag-label", "x=メッセージ")
        self.assertNotEqual(code, 0)
        self.assertIn("--group-by-tag", err)
        self.assertEqual(len(self.log()), 1)

    def test_default_is_per_decision(self):
        self.setup_repo()
        code, out, err = self.split()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.log(), ["四にする", "三にする", "二にする", "一にする", "init"])

    def test_dry_run_commits_nothing(self):
        self.setup_repo()
        before = git(self.d, "rev-parse", "HEAD")
        code, out, err = self.split("--group-by-tag", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(git(self.d, "rev-parse", "HEAD"), before)
        self.assertIn("tag:x", out)
        self.assertIn("tag:y", out)
        self.assertIn("要約: 決定 4 件", out)
        self.assertIn("ハンク 4 件", out)

    def test_trailer_on_group_commit(self):
        self.setup_repo()
        write(self.p("trailer.txt"), "Co-Authored-By: Someone <s@example.com>\n")
        code, out, err = self.split("--group-by-tag", "--trailer-file", self.p("trailer.txt"))
        self.assertEqual(code, 0, out + err)
        self.assertIn("Co-Authored-By: Someone", git(self.d, "log", "-1", "--format=%B", "HEAD~1"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
