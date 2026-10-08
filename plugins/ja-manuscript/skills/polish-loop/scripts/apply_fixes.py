#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""置換リスト (before/after) を、一意に一致するものだけ機械的に当てる。

polish-loop (推敲の before/after) と apply-proof-marks (朱書きの置換リスト) の共通の本体。
apply-proof-marks/scripts/apply_fixes.py はこれを呼ぶだけの入口。

使い方:
  python apply_fixes.py fixes.json                # 確認だけ(既定。何も書かない)
  python apply_fixes.py fixes.json --apply        # 実際に書き換える
  python apply_fixes.py fixes.json --apply --partial   # 一致しないものは飛ばし、残りを当てる
  python apply_fixes.py fixes.json --apply --post      # 適用後に整形 (1文1行・表) を走らせる
  python apply_fixes.py fixes.tsv  --apply        # TSV(file<TAB>before<TAB>after)でもよい

fixes.json の形 (キー名は before/after でも old/new でもよい。混ざっていてもよい):
  [{"file": "chapter_04.md", "before": "…", "after": "…"},
   {"file": "chapter_05.md", "old": "この行は消す．\\n", "new": ""}]

決めごと:
  - `before` が原稿に**ちょうど1回**現れるものだけ当てる。
    1件でも 0回・複数回・ファイルが無い があれば、**何も書かずに止まる** (--partial なら飛ばして残りを当てる)。
    部分適用にならないよう、全件を検査してから書き込む。
  - 改行コード (CRLF) と BOM は元のファイルに合わせる。before/after の改行は \\n で書けばよい。
  - 巻き込みを見つけるため、次を警告する (--strict なら警告でも止まる)。
      * 語の途中で切れている before (前後と同じ字種で続く) と、3文字以下の短い before
      * 置換のあと、after の出現数が「1つ増える」にならない・before がまたできた
      * 設定した禁止文字や、見出しの節番号のあとの空白落ちが新たに増えた
  - 当てる箇所ごとに、前後の文脈を置換前・置換後で並べて出す (--quiet で省く)。

設定 (任意): --config で渡すか、カレントの _polish/config.json。
  {"forbidden": {"全角(": "（", "読点、": "、"},   # 増えたら警告する文字 (名前: 文字)
   "check_heading_number": true}                   # 「## 1.6 練習問題」の番号のあとの空白落ちを見る
  設定が無ければ、禁止文字と見出しの点検はしない (表記の規則は原稿ごとに違うため)。
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 整形のスキルは同じ置き場 (プラグインなら同じプラグイン) の兄弟にある
SKILLS = Path(__file__).resolve().parents[2]
SPL = SKILLS / "sentence-per-line" / "scripts" / "sentence_per_line.py"
PAD = SKILLS / "markdown-table-pad" / "scripts" / "pad_tables.py"

BOM = b"\xef\xbb\xbf"
HEAD_RE = re.compile(r"^(#+)[ \t]+(\d+(?:\.\d+)*)([^\n]).*$", re.M)
SHORT = 3       # これ以下の長さの before は警告する
HIRA_SHORT = 6  # ひらがなの途中で切れるときは、この長さ以下なら警告する


# ---------------------------------------------------------------- 読み込み

def pick(row, new_key, old_key, n):
    """before/old (after/new) のどちらかを取る。両方あって違えば誤り。"""
    has_new, has_old = new_key in row, old_key in row
    if has_new and has_old and row[new_key] != row[old_key]:
        raise ValueError("#%d: %s と %s の両方があり、中身が違う" % (n, new_key, old_key))
    if not (has_new or has_old):
        raise ValueError("#%d: %s (または %s) が無い" % (n, new_key, old_key))
    return row[new_key] if has_new else row[old_key]


def load_fixes(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    rows = []
    if path.endswith(".json"):
        for n, r in enumerate(json.loads(text), 1):
            if "file" not in r:
                raise ValueError("#%d: file が無い" % n)
            rows.append((n, r["file"], pick(r, "before", "old", n), pick(r, "after", "new", n)))
    else:
        n = 0
        for ln in text.split("\n"):
            if not ln.strip() or ln.startswith("#"):
                continue
            n += 1
            cells = ln.rstrip("\r").split("\t")
            if len(cells) != 3:
                raise ValueError("TSV の %d 行目の列数が3でない: %s" % (n, ln[:50]))
            rows.append((n, cells[0], cells[1], cells[2]))
    return [(n, f, b.replace("\r\n", "\n"), a.replace("\r\n", "\n")) for n, f, b, a in rows]


def load_config(path):
    if path is None:
        cand = Path("_polish") / "config.json"
        if not cand.exists():
            return {}
        path = cand
    cfg = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    forb = cfg.get("forbidden", {})
    if isinstance(forb, list):  # ["（", "、"] の形も受ける
        forb = {ch: ch for ch in forb}
    return {"forbidden": forb, "check_heading_number": bool(cfg.get("check_heading_number"))}


def read_doc(path):
    """(本文 (改行は \\n), BOM の有無, CRLF か) を返す。"""
    raw = Path(path).read_bytes()
    bom = raw.startswith(BOM)
    text = raw[len(BOM):].decode("utf-8") if bom else raw.decode("utf-8")
    crlf = "\r\n" in text and text.count("\r\n") == text.count("\n")
    return (text.replace("\r\n", "\n") if crlf else text), bom, crlf


def write_doc(path, text, bom, crlf):
    if crlf:
        text = text.replace("\n", "\r\n")
    Path(path).write_bytes((BOM if bom else b"") + text.encode("utf-8"))


# ---------------------------------------------------------------- 巻き込みの警告

def kind(ch):
    o = ord(ch)
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or ch in "々〆":
        return "漢字"
    if 0x3041 <= o <= 0x309F:
        return "ひらがな"
    if 0x30A1 <= o <= 0x30FF or 0xFF66 <= o <= 0xFF9F:
        return "カタカナ"
    if ch.isascii() and ch.isalnum() or 0xFF10 <= o <= 0xFF19 or 0xFF21 <= o <= 0xFF3A or 0xFF41 <= o <= 0xFF5A:
        return "英数字"
    return None


def split_warnings(text, pos, before):
    """before が語の途中で切れているか、短すぎるかを見る。"""
    out = []
    core = before.strip()
    if 0 < len(core) <= SHORT:
        out.append("before が %d 文字と短い (別の語の一部に当たっていないか)" % len(core))
    edges = []
    if pos > 0 and before:
        edges.append(("前", text[pos - 1], before[0]))
    end = pos + len(before)
    if end < len(text) and before:
        edges.append(("後", text[end], before[-1]))
    for side, outer, inner in edges:
        k = kind(outer)
        if k is None or k != kind(inner):
            continue
        if k == "ひらがな" and len(before) > HIRA_SHORT:
            continue  # ひらがなは続くのが普通なので、長い before なら気にしない
        out.append("before の%sが%sの途中で切れている (「%s|%s」)" % (
            side, k, *((outer, inner) if side == "前" else (inner, outer))))
    return out


def count_warnings(old, new, before, after):
    """置換の前後で数が合うか (前後とつながって別の語ができていないか) を見る。"""
    out = []
    left = new.count(before) - after.count(before)
    if before and left > 0:
        out.append("置換のあとに before がまだ %d 回ある (前後とつながってできた)" % left)
    if after:
        delta = new.count(after) - old.count(after)
        expect = 1 - before.count(after)
        if delta != expect:
            out.append("after の出現数が %+d になった (%+d のはず。前後とつながっていないか)" % (delta, expect))
    return out


def context(text, pos, length, n):
    a, b = max(0, pos - n), min(len(text), pos + length + n)
    s = ("…" if a > 0 else "") + text[a:pos] + "【" + text[pos:pos + length] + "】" + \
        text[pos + length:b] + ("…" if b < len(text) else "")
    return s.replace("\n", "⏎")


def style_issues(text, cfg):
    """禁止文字の数と、番号のあとに空白の無い見出しの集合。"""
    counts = {label: text.count(ch) for label, ch in cfg.get("forbidden", {}).items()}
    heads = set()
    if cfg.get("check_heading_number"):
        for m in HEAD_RE.finditer(text):
            if m.group(3) not in " \t.．":  # 「## 1. はじめに」の点は空白落ちではない
                heads.add(m.group(0).strip()[:40])
    return counts, heads


def style_warnings(old, new, cfg):
    c0, h0 = style_issues(old, cfg)
    c1, h1 = style_issues(new, cfg)
    out = ["禁止文字 %s が %d 個増えた" % (k, c1[k] - c0[k]) for k in c1 if c1[k] > c0[k]]
    out += ["見出しの番号のあとに空白が無い: %s" % h for h in sorted(h1 - h0)]
    return out


# ---------------------------------------------------------------- 本体

def main():
    ap = argparse.ArgumentParser(description="置換リストを、一意に一致するものだけ当てる")
    ap.add_argument("fixes", help="fixes.json または fixes.tsv")
    ap.add_argument("--apply", action="store_true", help="実際に書き換える(既定は確認だけ)")
    ap.add_argument("--partial", action="store_true", help="一致しないものは飛ばし、残りを当てる")
    ap.add_argument("--strict", action="store_true", help="警告があっても止まる")
    ap.add_argument("--config", help="設定の JSON (既定は _polish/config.json があればそれ)")
    ap.add_argument("--context", type=int, default=10, help="前後に見せる文字数 (既定 10)")
    ap.add_argument("--post", action="store_true", help="適用後に 1文1行・表の整形と check_manuscript.py を走らせる")
    ap.add_argument("--quiet", action="store_true", help="1件ごとの文脈を出さない")
    args = ap.parse_args()

    try:
        rows = load_fixes(args.fixes)
        cfg = load_config(args.config)
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print("置換リストか設定が読めない: %s" % e)
        return 1

    by_file = {}
    for n, f, b, a in rows:
        by_file.setdefault(f, []).append((n, b, a))

    ng, warns, shown, staged = [], [], [], {}
    for f, items in by_file.items():
        if not os.path.exists(f):
            ng.append("%s が無い (%d 件)" % (f, len(items)))
            continue
        orig, bom, crlf = read_doc(f)
        s, applied = orig, 0
        for n, b, a in items:
            c = s.count(b) if b else 0
            if c != 1:
                ng.append("#%d %s: %d 件ヒット — %s" % (n, f, c, b[:40].replace("\n", "⏎")))
                continue
            pos = s.index(b)
            line = s.count("\n", 0, pos) + 1
            new = s[:pos] + a + s[pos + len(b):]
            w = split_warnings(s, pos, b) + count_warnings(s, new, b, a)
            warns += ["#%d %s:%d %s" % (n, f, line, x) for x in w]
            shown.append(("#%d %s:%d" % (n, f, line), context(s, pos, len(b), args.context),
                          context(new, pos, len(a), args.context)))
            s, applied = new, applied + 1
        if applied:
            warns += ["%s %s" % (f, x) for x in style_warnings(orig, s, cfg)]
            staged[f] = (s, bom, crlf, applied)

    total = sum(v[3] for v in staged.values())
    print("当てられる %d 件 / 当てられない %d 件 / 警告 %d 件" % (total, len(ng), len(warns)))
    if not args.quiet:
        for label, before, after in shown:
            print("  %s\n    前: %s\n    後: %s" % (label, before, after))
    if ng:
        print("当てられない:")
        for x in ng:
            print("  - " + x)
    if warns:
        print("★ 警告 (巻き込みを疑う。文脈を見て確かめる):")
        for x in warns:
            print("  - " + x)

    if ng and not args.partial:
        print("止めました (何も書いていない)。直して再実行するか、--partial で残りだけ当てる。")
        return 1
    if warns and args.strict:
        print("止めました (--strict のため警告でも書かない)。")
        return 1
    if not args.apply:
        print("(確認のみ。書き換えるには --apply を付ける)")
        return 0

    for f, (s, bom, crlf, _n) in staged.items():
        write_doc(f, s, bom, crlf)
        print("  書き換え: %s" % f)

    if args.post and staged:
        files = sorted(staged)
        for script in (SPL, PAD):
            if script.exists():
                subprocess.run([sys.executable, str(script)] + files)
        if Path("check_manuscript.py").exists():
            subprocess.run([sys.executable, "check_manuscript.py"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
