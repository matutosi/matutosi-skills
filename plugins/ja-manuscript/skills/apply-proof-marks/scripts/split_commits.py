#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作業ツリーの未コミットの変更を、decisions.json の決定ごとにコミットへ分ける。

使い方:
  python split_commits.py [--file decisions.json] [--repo .] [--dry-run] [--trailer-file FILE]

  --dry-run        どの変更がどの決定に振り分けられるかを表で出すだけ (何もコミットしない)
  --trailer-file   各コミットメッセージの末尾に足す文面 (共著の行など)

振り分け:
  - テキストファイルごとに git diff -U0 を取り、ハンクに分ける。
  - ハンクの追加行に決定の項目の new が現れる (または削除行に old が現れる) 決定へ振り分ける。
    複数に当たれば先に載っている決定へ振り分け、警告を出す。
  - どれにも当たらないハンクは other (その他の変更)。
  - 決定の files に挙げたファイル (図など) は、その決定へ。
  - rejected の決定は対象外。決定の並び順にコミットし、最後に other を1コミットにまとめる。
  - git apply が失敗したら、そこで止めて、ステージ済みのものと残りを報告する。
改行コード (CRLF) と BOM は、バイナリのまま扱うので変わらない。
決定の記録そのもの (decisions.json) は、リポジトリの中にあっても振り分けの対象にしない。
標準ライブラリと git だけで動く。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BOM = "﻿"
OTHER = "other"
OTHER_LABEL = "その他の変更"
HUNK_RE = re.compile(rb"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")


class GitError(Exception):
    pass


def git(repo, *args, input_=None, check=True):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=repo,
                       input=input_, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and r.returncode != 0:
        raise GitError("git %s: %s" % (" ".join(args), r.stderr.decode("utf-8", "replace").strip()))
    return r


def norm(b):
    """バイト列を文字列にし、BOM と CRLF を取り除く。"""
    s = b.decode("utf-8", "replace").replace("\r\n", "\n")
    return s[1:] if s.startswith(BOM) else s


def zlist(b):
    return [x.decode("utf-8", "replace") for x in b.split(b"\0") if x]


def changed_files(repo):
    """(追跡済みで変更のあるファイル, 未追跡のファイル)"""
    tracked = zlist(git(repo, "diff", "--name-only", "-z", "--no-renames").stdout)
    untracked = zlist(git(repo, "ls-files", "-o", "--exclude-standard", "-z").stdout)
    return tracked, untracked


def binary_files(repo):
    out = git(repo, "diff", "--numstat", "-z", "--no-renames").stdout
    bins = set()
    for ent in zlist(out):
        parts = ent.split("\t", 2)
        if len(parts) == 3 and parts[0] == "-" and parts[1] == "-":
            bins.add(parts[2])
    return bins


def parse_diff(raw):
    """(ヘッダのバイト列, [ハンクのバイト列のリスト]) を返す。"""
    head, hunks, cur = [], [], None
    for ln in raw.splitlines(keepends=True):
        if HUNK_RE.match(ln):
            if cur is not None:
                hunks.append(cur)
            cur = [ln]
        elif cur is None:
            head.append(ln)
        else:
            cur.append(ln)
    if cur is not None:
        hunks.append(cur)
    return b"".join(head), [b"".join(h) for h in hunks]


def hunk_text(h):
    """ハンクの (追加行の本文, 削除行の本文) を返す。改行は \\n にそろえる。"""
    added, removed = [], []
    for ln in h.splitlines(keepends=True)[1:]:
        if ln.startswith(b"+"):
            added.append(ln[1:])
        elif ln.startswith(b"-"):
            removed.append(ln[1:])
    return norm(b"".join(added)), norm(b"".join(removed))


def item_hits(it, added, removed):
    new, old = it.get("new", ""), it.get("old", "")
    return (bool(new) and new in added) or (bool(old) and old in removed)


def match_decisions(path, h, decs):
    """ハンクに当たる決定の id のリスト (並び順)。"""
    added, removed = hunk_text(h)
    hits = []
    for d in decs:
        for it in d.get("items", []):
            if it.get("file", "").replace("\\", "/") == path and item_hits(it, added, removed):
                hits.append(d["id"])
                break
    return hits


def build_plan(repo, decs, skip_path):
    """変更を決定ごとに振り分ける。

    戻り値: (hunk_map, whole_map, warnings)
      hunk_map: id -> [(path, header, hunk)]
      whole_map: id -> [path] (ファイル丸ごと。バイナリ・未追跡・決定の files)
    """
    active = [d for d in decs if d.get("status") != "rejected"]
    file_owner = {}
    for d in active:
        for f in d.get("files", []):
            file_owner.setdefault(f.replace("\\", "/"), d["id"])
    tracked, untracked = changed_files(repo)
    bins = binary_files(repo)
    hunk_map, whole_map, warns = {}, {}, []
    for path in tracked + untracked:
        if skip_path and path == skip_path:
            continue
        if path in file_owner:
            whole_map.setdefault(file_owner[path], []).append(path)
            continue
        if path in untracked or path in bins:
            whole_map.setdefault(OTHER, []).append(path)
            continue
        raw = git(repo, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-renames",
                  "--", path).stdout
        header, hunks = parse_diff(raw)
        for h in hunks:
            hits = match_decisions(path, h, active)
            if len(hits) > 1:
                warns.append("%s: 複数の決定に当たる (%s)。%s へ振り分ける" % (path, ",".join(hits), hits[0]))
            hunk_map.setdefault(hits[0] if hits else OTHER, []).append((path, header, h))
    return hunk_map, whole_map, warns


def make_patch(items):
    """同じファイルのハンクを、ファイルごとのヘッダの下にまとめる。"""
    order, by = [], {}
    for path, header, h in items:
        if path not in by:
            by[path] = [header, []]
            order.append(path)
        by[path][1].append(h)
    return b"".join(by[p][0] + b"".join(by[p][1]) for p in order)


def commit(repo, message, trailer):
    msg = message
    if trailer:
        msg = message.rstrip("\n") + "\n\n" + trailer.strip("\n") + "\n"
    with tempfile.NamedTemporaryFile("wb", suffix=".txt", delete=False) as fh:
        fh.write(msg.encode("utf-8"))
        name = fh.name
    try:
        git(repo, "commit", "-q", "-F", name)
    finally:
        os.unlink(name)


def report_state(repo, done):
    print("--- 途中で止まった ---", file=sys.stderr)
    print("コミット済み: %s" % (", ".join(done) or "なし"), file=sys.stderr)
    st = git(repo, "diff", "--cached", "--stat", check=False).stdout.decode("utf-8", "replace")
    print("ステージ済み:\n%s" % (st.strip() or "(なし)"), file=sys.stderr)
    rest = git(repo, "status", "--short", check=False).stdout.decode("utf-8", "replace")
    print("残っている変更:\n%s" % (rest.strip() or "(なし)"), file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="未コミットの変更を決定ごとにコミットへ分ける")
    ap.add_argument("--file", default="_review/marks/decisions.json")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--trailer-file")
    a = ap.parse_args(argv)
    repo = str(Path(a.repo).resolve())
    dfile = Path(a.file)
    if not dfile.is_absolute() and not dfile.exists():
        dfile = Path(repo) / a.file
    if not dfile.exists():
        sys.exit("決定の記録が無い: %s" % a.file)
    data = json.loads(dfile.read_bytes().decode("utf-8-sig"))
    decs = data.get("decisions", [])
    trailer = Path(a.trailer_file).read_bytes().decode("utf-8-sig") if a.trailer_file else ""
    skip = None
    try:
        skip = dfile.resolve().relative_to(Path(repo).resolve()).as_posix()
    except ValueError:
        pass

    try:
        if git(repo, "diff", "--cached", "--name-only").stdout.strip():
            sys.exit("ステージ済みの変更がある。先にコミットするか戻してから実行する")
        hunk_map, whole_map, warns = build_plan(repo, decs, skip)
    except GitError as e:
        sys.exit("エラー: %s" % e)
    for w in warns:
        print("警告: %s" % w, file=sys.stderr)

    labels = {d["id"]: d.get("label", d["id"]) for d in decs}
    labels[OTHER] = OTHER_LABEL
    order = [d["id"] for d in decs if d.get("status") != "rejected"] + [OTHER]

    print("決定 | ファイル | 種別 | 変更")
    count = 0
    for did in order:
        for path, _, h in hunk_map.get(did, []):
            print("%s | %s | ハンク | %s" % (did, path, h.splitlines()[0].decode("utf-8", "replace")))
            count += 1
        for path in whole_map.get(did, []):
            print("%s | %s | ファイル丸ごと | -" % (did, path))
            count += 1
    if a.dry_run:
        print("(--dry-run: 何もコミットしない)")
        return 0
    if not count:
        print("未コミットの変更は無い")
        return 0

    done = []
    for did in order:
        if done:  # 前のコミットで行番号がずれるので、毎回作り直す
            try:
                hunk_map, whole_map, _ = build_plan(repo, decs, skip)
            except GitError as e:
                print("エラー: %s" % e, file=sys.stderr)
                report_state(repo, done)
                return 1
        items, whole = hunk_map.get(did, []), whole_map.get(did, [])
        if not items and not whole:
            continue
        try:
            for path in whole:
                git(repo, "add", "-A", "--", path)
            if items:
                git(repo, "apply", "--cached", "--unidiff-zero", "--whitespace=nowarn", "-",
                    input_=make_patch(items))
            commit(repo, labels[did], trailer)
        except GitError as e:
            print("エラー: %s" % e, file=sys.stderr)
            report_state(repo, done)
            return 1
        done.append(did)
        print("コミット: %s (%s)" % (did, labels[did]))

    status = git(repo, "status", "--porcelain").stdout.decode("utf-8", "replace").splitlines()
    left = [l for l in status if not (skip and l[3:].strip('"') == skip)]
    if left:
        print("未コミットが残っている:\n%s" % "\n".join(left), file=sys.stderr)
        return 1
    print("未コミットは残っていない (%d コミット)" % len(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
