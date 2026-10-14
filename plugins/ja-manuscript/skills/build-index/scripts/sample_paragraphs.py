#!/usr/bin/env python3
"""索引の点検用に，本文から段落を無作為に抜き出す．

各段落に対し，terms.yaml の見出し語のうち段落中に現れるものを並べる．
「この段落の内容を索引から引けるか」を人が判断するための材料を作る．
"""
from __future__ import annotations

import argparse
import random
import re
import sys
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

RE_FENCE = re.compile(r"^\s*(```|~~~)")
RE_SKIP = re.compile(r"^\s*(#|!\[|\||>|-|\d+\.|:::|図[．.]|表[．.])")


def norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def paragraphs(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    in_fence, buf, start = False, [], 0
    for i, raw in enumerate(lines, 1):
        if RE_FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not raw.strip() or RE_SKIP.match(raw):
            if buf:
                yield start, " ".join(buf)
                buf = []
            continue
        if not buf:
            start = i
        buf.append(raw.strip())
    if buf:
        yield start, " ".join(buf)


def load_headings(path: Path | None):
    if not path or not path.exists():
        return []
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    heads = []
    for e in data.get("entries", []) or []:
        words = e.get("検索") or [e["見出し"]]
        heads.append((e["見出し"], [norm(w) for w in words]))
        for s in e.get("副", []) or []:
            sw = s.get("検索") or [s["見出し"]]
            heads.append((f"{e['見出し']} > {s['見出し']}", [norm(w) for w in sw]))
    return heads


def main() -> int:
    ap = argparse.ArgumentParser(description="索引の点検用に本文の段落を抜き出す")
    ap.add_argument("files", nargs="+", help="原稿 md")
    ap.add_argument("-n", "--num", type=int, default=8, help="抜き出す段落数(既定 8)")
    ap.add_argument("-t", "--terms", help="terms.yaml(あれば該当する見出し語を表示)")
    ap.add_argument("--min-chars", type=int, default=60, help="対象とする段落の最小文字数")
    ap.add_argument("--seed", type=int, default=0, help="乱数の種")
    args = ap.parse_args()

    pool = []
    for f in sorted({Path(p) for p in args.files}):
        if f.exists():
            pool += [(f.name, ln, t) for ln, t in paragraphs(f) if len(t) >= args.min_chars]
    if not pool:
        print("段落が見つかりません", file=sys.stderr)
        return 1

    random.seed(args.seed)
    heads = load_headings(Path(args.terms) if args.terms else None)
    for name, ln, text in random.sample(pool, min(args.num, len(pool))):
        body = norm(text)
        hit = [h for h, ws in heads if any(w and w in body for w in ws)]
        print(f"\n--- {name}:{ln}")
        print(text[:300])
        if heads:
            print(f"  索引で引ける見出し: {'，'.join(hit) if hit else '(無し)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
