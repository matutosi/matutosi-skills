#!/usr/bin/env python3
"""terms.yaml の「よみ」が無い見出しに，よみの候補を出す (任意の補助).

    python suggest_yomi.py terms.yaml

- 候補は pykakasi で作る．pykakasi が無ければ，導入方法を出して終了コード 0 で終わる．
- **ファイルには何も書き込まない**．候補は「要確認」として画面に出すだけで，
  確定は人が行う (人名・専門用語・数字を含む語は誤りやすい)．
- 英字だけの見出しは，原綴のまま書く規則なので，候補を出さない．
- `--all` を付けると，よみのある見出しも調べ，候補と食い違うものを「要確認」で示す．
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

INSTALL_HINT = "pykakasi が入っていません．よみの候補が要るときは: pip install pykakasi"


def to_hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if 0x30A1 <= ord(c) <= 0x30F6 else c for c in s)


def is_latin(name: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9\s.\-_/+]+", name))


def make_converter():
    """pykakasi の変換器を返す．無ければ None．"""
    try:
        import pykakasi
    except ImportError:
        return None
    return pykakasi.kakasi()


def candidate(kks, name: str) -> str:
    """見出しのよみの候補 (ひらがな)．"""
    parts = kks.convert(name)
    return "".join(to_hira(p.get("hira") or p.get("orig", "")) for p in parts)


def suggest(entries: list[dict], kks, show_all: bool = False) -> list[tuple[str, str, str, str]]:
    """(階層の表示名，見出し，いまのよみ，候補) の並びを返す．"""
    rows = []

    def one(label: str, e: dict):
        name = e.get("見出し", "")
        if not name or is_latin(name):
            return
        have = e.get("よみ") or ""
        if have and not show_all:
            return
        cand = candidate(kks, name)
        if have and to_hira(have) == cand:
            return
        rows.append((label, name, have, cand))

    for e in entries:
        one(e["見出し"], e)
        for s in e.get("副", []) or []:
            one(f"{e['見出し']} > {s.get('見出し', '')}", s)
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="terms.yaml のよみの候補を出す (書き込まない)")
    ap.add_argument("terms", help="terms.yaml")
    ap.add_argument("--all", action="store_true", help="よみのある見出しも調べ，食い違いを示す")
    args = ap.parse_args(argv)

    kks = make_converter()
    if kks is None:
        print(INSTALL_HINT)
        return 0
    try:
        import yaml
    except ImportError:
        print("PyYAML が要ります: pip install pyyaml", file=sys.stderr)
        return 2

    data = yaml.safe_load(Path(args.terms).read_text(encoding="utf-8")) or {}
    rows = suggest(data.get("entries", []) or [], kks, args.all)
    if not rows:
        print("よみの候補を出す見出しは，ありませんでした．")
        return 0
    print("よみの候補 (要確認．自動では書き込みません．確かめて terms.yaml に自分で書いてください)")
    print()
    for label, name, have, cand in rows:
        if have:
            print(f"- {label}: いまのよみ「{have}」と候補「{cand}」が違います (要確認)")
        else:
            print(f"- {label}: よみ: {cand}   (要確認)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
