#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""推敲の before/after を、一意に一致するものだけ機械的に当てる。

使い方:
  python apply_fixes.py fixes.json            # 確認だけ(既定)
  python apply_fixes.py fixes.json --apply    # 実際に書き換える
  python apply_fixes.py fixes.tsv  --apply    # TSV(file<TAB>before<TAB>after)でもよい

fixes.json の形:
  [{"file": "chapter_04.md", "before": "…", "after": "…"}, ...]

決めごと:
  - `before` が原稿に**ちょうど1回**現れるものだけ当てる(0回・複数回は当てずに報告)。
    部分適用にならないよう、全件を検査してから書き込む。
  - 改行コード(CRLF)は保つ。
  - 適用後に禁止文字と見出しの空白を点検する(一括置換の巻き添えを早期に見つけるため)。
"""
import argparse
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 本書で使わない文字。適用後に混入していないか見る
FORBIDDEN = {
    "全角(": "（", "全角)": "）", "読点、": "、", "句点。": "。",
    "en ダッシュ": "–", "≈": "≈",
}
# 「## 1.6 練習問題」のように、節番号の直後の空白が落ちていないか
HEAD_RE = re.compile(r"^(#+)\s+(\d+(?:\.\d+)*)(.)")


def load(path):
    text = io.open(path, encoding="utf-8").read()
    if path.endswith(".json"):
        rows = json.loads(text)
        return [(r["file"], r["before"], r["after"]) for r in rows]
    out = []
    for ln in text.split("\n"):
        if not ln.strip() or ln.startswith("#"):
            continue
        cells = ln.rstrip("\r").split("\t")
        if len(cells) != 3:
            print("  TSV の列数が3でない行を飛ばす: %s" % ln[:50])
            continue
        out.append(tuple(cells))
    return out


def check_file(path):
    """禁止文字と見出しの空白落ちを見る。問題の一覧を返す。"""
    bad = []
    for i, ln in enumerate(io.open(path, encoding="utf-8"), 1):
        for label, ch in FORBIDDEN.items():
            if ch in ln:
                bad.append("%s:%d 禁止文字 %s" % (path, i, label))
        m = HEAD_RE.match(ln)
        if m and m.group(3) != " ":
            bad.append("%s:%d 見出しの節番号のあとに空白が無い: %s" % (path, i, ln.strip()[:40]))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fixes", help="fixes.json または fixes.tsv")
    ap.add_argument("--apply", action="store_true", help="実際に書き換える(既定は確認だけ)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    rows = load(args.fixes)
    by_file = {}
    for f, b, a in rows:
        by_file.setdefault(f, []).append((b, a))

    plans, skips = {}, []
    for f, pairs in by_file.items():
        if not os.path.exists(f):
            skips.append("SKIP %s (ファイルが無い)" % f)
            continue
        s = io.open(f, encoding="utf-8", newline="").read()
        applied = 0
        for b, a in pairs:
            n = s.count(b)
            if n != 1:
                skips.append("SKIP %s (一致 %d 件) %s" % (f, n, b[:44].replace("\r\n", "⏎")))
                continue
            s = s.replace(b, a)
            applied += 1
        if applied:
            plans[f] = (s, applied)

    total = sum(v[1] for v in plans.values())
    print("当てられる %d 件 / 見送り %d 件" % (total, len(skips)))
    for sk in skips:
        print("  " + sk)

    if not args.apply:
        print("(確認のみ。書き換えるには --apply を付ける)")
        return 0

    for f, (s, _n) in plans.items():
        io.open(f, "w", encoding="utf-8", newline="").write(s)
    print("%d ファイルを書き換えた" % len(plans))

    bad = []
    for f in plans:
        bad.extend(check_file(f))
    if bad:
        print("★ 適用後の点検で問題あり(一括置換の巻き添えを疑う)")
        for b in bad:
            print("   " + b)
        return 1
    if not args.quiet:
        print("適用後の点検: 禁止文字・見出しの空白とも問題なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
