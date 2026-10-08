#!/usr/bin/env python3
"""日本語 Markdown 原稿を「1文ごとに改行」「引用は1文ごとに > 」「段落間は空行1つ」の
書式に整形するスクリプト(1文1行の改行ルールを機械的に適用する)。

対象外(そのまま素通し):
  - フェンス付きコードブロック(``` ... ```)
  - 見出し行(# ...)
  - リスト行(-, *, +, 数字. で始まる行)
  - テーブル行(| で始まる行)
  - 生 HTML 行(< で始まる行)

対象:
  - 通常の地の文の段落 → 文末(．。！？ + 続く閉じ括弧・引用符・**太字閉じ記号**)ごとに改行
  - 「> 」で始まる引用段落 → 文末ごとに改行し、各行の先頭に「> 」を付け直す
  - 段落と段落の間は空行を1つだけに揃える

インライン code span(`...`)内の句読点は分割対象にしない。

使い方:
    python sentence_per_line.py file1.md [file2.md ...]   # 直接上書き
    python sentence_per_line.py -                          # 標準入力→標準出力
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

CODE_FENCE_RE = re.compile(r"^\s*```")
COMMENT_OPEN_RE = re.compile(r"^\s*<!--")
SENTENCE_END_CHARS = "．。！？"
CLOSING_CHARS = "」』）】》'\"’"
LIST_RE = re.compile(r"^([-*+]|\d+\.)\s")
CAPTION_RE = re.compile(r"^(図．|表．|図：|表：)")
# 「図．」「表．」の "．" は図表の参照記法であって文末ではない
# (本文中の "(図．fig_xxx)" や行頭の "表．…" を誤分割しないための保護)
CAPTION_MARK_CHARS = "図表"
# 引用行から "> " をちょうど1つだけ外す(残りの空白・入れ子はそのまま保つ)
QUOTE_MARK_RE = re.compile(r"^(\s*>)( ?)(.*)$")


def _restore(text: str, spans: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: spans[int(m.group(1))], text)


def split_sentences(text: str) -> list[str]:
    """インライン code span を保護したうえで、文末ごとに分割する。

    **太字** の開閉状態を先頭からトラッキングし、文末記号の直後の "**" が
    「開いている太字を閉じる」場合のみ現在の文に含める(単に次の文の
    太字が始まっているだけの "**" を誤って前の文に食わせない)。
    """
    spans: list[str] = []

    def stash(m: re.Match) -> str:
        spans.append(m.group(0))
        return f"\x00{len(spans) - 1}\x00"

    protected = re.sub(r"`[^`]*`", stash, text)

    parts: list[str] = []
    start = 0
    bold_open = False
    i = 0
    n = len(protected)
    while i < n:
        if protected[i:i + 2] == "**":
            bold_open = not bold_open
            i += 2
            continue
        if protected[i] in SENTENCE_END_CHARS:
            # 「図．」「表．」は図表の参照記法なので文末として扱わない
            if protected[i] == "．" and i > 0 and protected[i - 1] in CAPTION_MARK_CHARS:
                i += 1
                continue
            j = i
            while j < n and protected[j] in SENTENCE_END_CHARS:
                j += 1
            while j < n and protected[j] in CLOSING_CHARS:
                j += 1
            if bold_open and protected[j:j + 2] == "**":
                j += 2
                bold_open = False
            seg = protected[start:j].strip()
            if seg:
                parts.append(seg)
            start = j
            i = j
            continue
        i += 1
    tail = protected[start:].strip()
    if tail:
        parts.append(tail)

    return [_restore(p, spans) for p in parts]


def is_special_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    # 字下げされた行は箇条書きの継続などなので、字下げごとそのまま残す
    # (行頭の空白を落として前の行と連結すると階層が壊れる)
    if line[:1].isspace():
        return True
    if s.startswith("#") or s.startswith("```") or s.startswith("|") or s.startswith("<"):
        return True
    # フェンス div(::: figpair)と画像リンク(![...]) は 1 行として扱う
    # (隣り合う行と連結して "::: figpair![...]" のように壊すのを防ぐ)
    if s.startswith(":::") or s.startswith("!["):
        return True
    # 図題・表題は 1 行として扱う("図．05_01_R：…" の "．" で切らない)
    if CAPTION_RE.match(s):
        return True
    if LIST_RE.match(s):
        return True
    return False


def process(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]

        if CODE_FENCE_RE.match(line):
            out.append(line)
            i += 1
            while i < n and not CODE_FENCE_RE.match(lines[i]):
                out.append(lines[i])
                i += 1
            if i < n:
                out.append(lines[i])
                i += 1
            continue

        # HTML コメントブロックはコメント記号が閉じるまで素通しする
        # (中の URL やメモを地の文と見なして連結すると "…jp/xxx-->" のように壊れる)
        if COMMENT_OPEN_RE.match(line) and "-->" not in line:
            out.append(line)
            i += 1
            while i < n and "-->" not in lines[i]:
                out.append(lines[i])
                i += 1
            if i < n:
                out.append(lines[i])
                i += 1
            continue

        if not line.strip():
            if out and out[-1] != "":
                out.append("")
            i += 1
            while i < n and not lines[i].strip():
                i += 1
            continue

        if line.lstrip().startswith(">"):
            # 引用ブロックは行の種類を見ながら処理する。
            # 文ごとに割り直すのは「> 」直後がプレーンな地の文の行だけに限る。
            # 入れ子の引用(>>)、字下げされた行、箇条書き、<br> を含む行は
            # 書き手が意図した構造なので、元の行をそのまま残す
            # (潰すと出力例やプロンプトのインデントが壊れる)。
            # 引用では行をまたいで連結しない。
            # 記載例やプロンプトの改行位置は書き手が決めたものなので、
            # 1 行の中に複数の文があるときだけ、その行を割る。
            while i < n and lines[i].lstrip().startswith(">"):
                raw = lines[i]
                m = QUOTE_MARK_RE.match(raw)
                rest = m.group(3) if m else ""
                if (
                    not rest.strip()              # 引用内の空行
                    or rest.startswith(">")       # 入れ子の引用(>> 出力例など)
                    or rest[:1].isspace()         # 字下げされた行(箇条書きの子要素など)
                    or "<br>" in rest             # 明示的な改行指定
                    or is_special_line(rest)      # 箇条書き・表・見出し・HTML・図表題
                ):
                    out.append(raw)
                else:
                    for s in split_sentences(rest.strip()):
                        out.append(f"> {s}")
                i += 1
            continue

        if is_special_line(line):
            out.append(line)
            i += 1
            continue

        buf = [line.strip()]
        i += 1
        while i < n and lines[i].strip() and not is_special_line(lines[i]) and not lines[i].lstrip().startswith(">"):
            buf.append(lines[i].strip())
            i += 1
        out.extend(split_sentences("".join(buf)))

    result = "\n".join(out)
    return result.strip("\n") + "\n"


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit("使い方: python sentence_per_line.py file1.md [file2.md ...] | -")

    if args == ["-"]:
        sys.stdout.write(process(sys.stdin.read()))
        return

    for arg in args:
        path = Path(arg)
        if not path.is_file():
            print(f"エラー: ファイルが見つかりません: {path}", file=sys.stderr)
            continue
        # BOM と改行コードは元のまま保つ(無用な差分を出さないため)
        raw = path.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        original = raw.decode("utf-8-sig" if bom else "utf-8")
        newline = "\r\n" if "\r\n" in original else "\n"

        formatted = process(original.replace("\r\n", "\n"))

        if formatted.replace("\n", newline) != original:
            data = formatted.replace("\n", newline).encode("utf-8")
            path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
            print(f"Formatted: {path}")
        else:
            print(f"No change: {path}")


if __name__ == "__main__":
    main()
