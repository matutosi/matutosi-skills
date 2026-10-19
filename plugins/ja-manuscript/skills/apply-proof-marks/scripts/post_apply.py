#!/usr/bin/env python3
"""校正の反映のあとの後始末を自動で行う (抽出ファイルの作り直し・図の再生成・点検).

図の再生成は意図しない図のバイト列まで書き換えるので，restore_globs に当たるファイルで
「ステップの実行で新たに変更され，--intended に挙がっていないもの」を git checkout で戻す．

設定ファイル (既定 _review/marks/post_apply.json):
    {
      "steps": [
        {"name": "抽出ファイルの作り直し", "cmd": "python tools/extract_code.py {changed}",
         "when_changed": ["chapter_*.md"]},
        {"name": "図の再生成", "cmd": "python tools/render.py {changed}",
         "when_changed": ["chapter_*.md"], "slow": true}
      ],
      "check": {"name": "原稿の点検", "cmd": "python tools/check.py"},
      "restore_globs": ["figures/*"]
    }

Usage:
    python post_apply.py [--config FILE] [--repo .] [--intended FILE ...]
                         [--only-step 名前] [--dry-run]
    例: python post_apply.py --intended figures/fig_03.pdf
"""

import argparse
import fnmatch
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_CONFIG = "_review/marks/post_apply.json"


def git(repo, *args):
    r = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=repo,
                       capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def norm(p):
    return os.path.normpath(p).replace("\\", "/")


def changed_files(repo):
    """未コミットの変更ファイル (リポジトリからの相対パス)."""
    code, out, err = git(repo, "status", "--porcelain", "-z", "--untracked-files=all")
    if code != 0:
        raise RuntimeError("git status に失敗: " + err.strip())
    items = out.split("\0")
    files, i = [], 0
    while i < len(items):
        e = items[i]
        i += 1
        if len(e) < 4:
            continue
        files.append(e[3:])
        if e[0] in "RC":  # 改名・複製は元のパスが続く
            i += 1
    return files


def match_any(path, globs):
    return any(fnmatch.fnmatch(path, g) for g in globs)


def quote(paths):
    if os.name == "nt":
        return subprocess.list2cmdline(paths)
    return " ".join(shlex.quote(p) for p in paths)


def snapshot(repo, globs):
    """restore_globs に当たるファイルの内容ハッシュ."""
    code, out, _ = git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    snap = {}
    for p in out.split("\0"):
        if p and match_any(p, globs):
            fp = os.path.join(repo, p)
            if os.path.isfile(fp):
                with open(fp, "rb") as fh:
                    snap[p] = hashlib.sha1(fh.read()).hexdigest()
    return snap


def run_cmd(cmd, repo):
    t0 = time.time()
    r = subprocess.run(cmd, shell=True, cwd=repo, capture_output=True)
    out = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    return r.returncode, out, time.time() - t0


def tail(text, n=15):
    lines = text.strip().splitlines()
    return "\n".join(lines[-n:])


def run_step(step, repo, restore_globs, intended):
    """ステップを実行して結果と戻したファイルを返す."""
    before_changed = set(changed_files(repo))
    before = snapshot(repo, restore_globs)
    code, out, sec = run_cmd(step["cmd"], repo)
    after = snapshot(repo, restore_globs)
    restored = []
    for p, h in after.items():
        if p not in before or before[p] == h:
            continue  # 新規ファイル (戻せない) か変化なし
        if p in intended or p in before_changed:
            continue  # 意図した変更か，ステップの前からあった変更
        c, _, _ = git(repo, "checkout", "--", p)
        if c == 0:
            restored.append(p)
    return {"name": step["name"], "code": code, "sec": sec, "out": out,
            "restored": restored, "skipped": False}


def main(argv=None):
    ap = argparse.ArgumentParser(description="校正の反映のあとの後始末")
    ap.add_argument("--config", default=None, help="設定ファイル (既定 %s)" % DEFAULT_CONFIG)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--intended", nargs="*", default=[],
                    help="意図して変更した (戻さない) ファイル")
    ap.add_argument("--only-step", default=None, help="この名前のステップだけ走らせる")
    ap.add_argument("--dry-run", action="store_true", help="実行せず，走らせるものだけ出す")
    a = ap.parse_args(argv)

    repo = os.path.abspath(a.repo)
    cfg_path = a.config or os.path.join(repo, DEFAULT_CONFIG)
    try:
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as e:
        print("設定ファイルを読めません: %s (%s)" % (cfg_path, e))
        return 2

    steps = cfg.get("steps", [])
    check = cfg.get("check")
    restore_globs = cfg.get("restore_globs", [])
    intended = {norm(p) for p in a.intended}
    if a.only_step:
        steps = [s for s in steps if s.get("name") == a.only_step]
        if not steps:
            print("ステップが見つかりません: " + a.only_step)
            return 2

    try:
        changed = changed_files(repo)
    except RuntimeError as e:
        print(e)
        return 2

    results = []
    for step in steps:
        globs = step.get("when_changed")
        hit = [f for f in changed if match_any(f, globs)] if globs else list(changed)
        if globs and not hit:
            results.append({"name": step["name"], "skipped": True, "code": None,
                            "sec": 0, "restored": [], "out": ""})
            continue
        step = dict(step, cmd=step["cmd"].replace("{changed}", quote(hit)))
        if a.dry_run:
            print("[dry-run] %s: %s" % (step["name"], step["cmd"]))
            continue
        print("実行中: %s%s" % (step["name"], " (時間がかかります)" if step.get("slow") else ""),
              flush=True)
        results.append(run_step(step, repo, restore_globs, intended))

    check_res = None
    if check:
        if a.dry_run:
            print("[dry-run] %s: %s" % (check.get("name", "点検"), check["cmd"]))
        else:
            code, out, sec = run_cmd(check["cmd"], repo)
            check_res = {"code": code, "sec": sec, "out": out}

    if a.dry_run:
        print("dry-run のため何も実行していません．")
        return 0

    print("\n=== 後始末の報告 ===")
    failed = 0
    for r in results:
        if r["skipped"]:
            print("- %s: 飛ばした (対象の変更ファイルなし)" % r["name"])
        elif r["code"] == 0:
            print("- %s: 成功 (%.1f 秒)" % (r["name"], r["sec"]))
        else:
            failed += 1
            print("- %s: 失敗 (終了コード %s, %.1f 秒)\n%s" % (
                r["name"], r["code"], r["sec"], tail(r["out"])))
    restored = [p for r in results for p in r["restored"]]
    print("元に戻したファイル: %s" % (", ".join(restored) if restored else "なし"))
    if check_res is not None:
        ok = check_res["code"] == 0
        if not ok:
            failed += 1
        print("%s: %s (終了コード %s)\n%s" % (
            check.get("name", "点検"), "問題なし" if ok else "問題あり",
            check_res["code"], tail(check_res["out"])))
    print("失敗: %d 件" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
