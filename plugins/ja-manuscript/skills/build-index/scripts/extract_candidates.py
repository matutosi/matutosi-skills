#!/usr/bin/env python3
"""原稿 md から索引の見出し語候補を抽出する．

コードブロック・図リンク・図題は対象外．
見出し・太字・定義文の語を優先度 高，カタカナ語・漢字熟語を優先度 低として出す．
出力は _index_work/candidates_<章>.md と _index_work/candidates_all.md．
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# 索引の見出しにしない汎用語 (本によって合わなければ，ここを直す)
STOPWORDS = {
    "こと", "もの", "ため", "とき", "場合", "ここ", "そこ", "これ", "それ", "など",
    "本書", "本章", "本節", "以下", "上記", "次章", "前章", "一つ", "二つ", "自分",
    "読者", "読み手", "著者", "内容", "説明", "意味", "必要", "可能", "使用", "利用",
    "作成", "実行", "確認", "注意", "参照", "以上", "以外", "同様", "全体", "部分",
    "方法", "結果", "問題", "理由", "関係", "状態", "今回", "最初", "最後", "実際",
    "基本", "重要", "普通", "自体", "程度", "多く", "様々", "一般", "特定", "具体",
    "コード", "ファイル", "パターン", "ケース", "ポイント", "レベル", "タイプ",
}

RE_FENCE = re.compile(r"^\s*(```|~~~)")
RE_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*(\{#[^}]*\})?\s*$")
RE_HEAD_NUM = re.compile(r"^(?:第?\d+(?:\.\d+)*\s*章?[\s:：.]*)")
RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
RE_DEFINE = re.compile(r"([^\s，．（）()「」]{2,20}?)(?:とは|と呼びます|といいます|と言います|を指します)")
RE_CODE_INLINE = re.compile(r"`([A-Za-z][A-Za-z0-9_.:]{1,39})`")
RE_KATAKANA = re.compile(r"[ァ-ヴー]{3,}")
RE_KANJI = re.compile(r"[一-龥]{2,8}")
RE_FIGLINK = re.compile(r"^\s*!\[|^\s*図[．.]|^\s*表[．.:：]|^\s*:::")
# 索引の見出しにしない定型の節見出し
RE_SKIP_HEAD = re.compile(r"練習問題|解答|まとめ|使い分け|コラム|参考文献|考察")
RE_PAREN = re.compile(r"[(（][^)）]*[)）]?")


def clean(word: str) -> str:
    w = word.strip()
    w = re.sub(r"^[「『（(\[\s]+", "", w)
    w = re.sub(r"[」』）)\]\s，．,、。:：]+$", "", w)
    return w.strip()


def strip_markup(line: str) -> str:
    """行から索引に不要なマークアップを落とす(太字の中身は残す)．"""
    line = re.sub(r"`[^`]*`", " ", line)
    line = re.sub(r"\\@ref\([^)]*\)", " ", line)
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)
    line = line.replace("**", "")
    return line


def scan(path: Path, skip_head=None):
    """1章を走査して {語: 情報} を返す．"""
    info = defaultdict(lambda: {"count": 0, "kinds": set(), "first": None})

    def add(word: str, kind: str, lineno: int, n: int = 1):
        w = clean(word)
        if not w or w in STOPWORDS or len(w) < 2 or len(w) > 30:
            return
        if w.isdigit():
            return
        # 定義文・太字から拾った語は，文の途中を切り取った断片を落とす
        if kind in ("定義", "太字"):
            if len(w) > 16 or re.search(r"[ぁ-ゖ]$", w):
                return
        rec = info[w]
        rec["count"] += n
        rec["kinds"].add(kind)
        if rec["first"] is None:
            rec["first"] = lineno

    lines = path.read_text(encoding="utf-8").splitlines()
    in_fence = False
    body_lines = 0
    for i, raw in enumerate(lines, 1):
        if RE_FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence or RE_FIGLINK.match(raw):
            continue
        body_lines += 1

        m = RE_HEADING.match(raw)
        if m:
            title = RE_HEAD_NUM.sub("", m.group(2))
            if (skip_head or RE_SKIP_HEAD).search(title):
                continue
            title = RE_PAREN.sub(" ", title)
            for part in re.split(r"[—・:：/，,]", title):
                part = clean(part)
                if len(part) <= 16:
                    add(part, "見出し", i, 3)
            continue

        for b in RE_BOLD.findall(raw):
            add(RE_PAREN.sub(" ", re.sub(r"[，．]", "", b)).strip(), "太字", i, 2)
        for c in RE_CODE_INLINE.findall(raw):
            add(c, "コード", i)

        text = strip_markup(raw)
        for d in RE_DEFINE.findall(text):
            add(d, "定義", i, 3)
        for k in RE_KATAKANA.findall(text):
            add(k, "カタカナ", i)
        for k in RE_KANJI.findall(text):
            add(k, "漢字", i)

    return info, body_lines


PRIORITY = ("見出し", "定義", "太字")


def main() -> int:
    ap = argparse.ArgumentParser(description="索引の見出し語候補を抽出する")
    ap.add_argument("files", nargs="+", help="原稿 md (chapter_*.md)")
    ap.add_argument("-o", "--out-dir", default="_index_work", help="出力先(既定 _index_work)")
    ap.add_argument("--min-count", type=int, default=2, help="カタカナ・漢字語の最小出現回数(既定 2)")
    ap.add_argument("--skip-heading", help="索引にしない節見出しの正規表現 (既定: 練習問題|解答|まとめ|使い分け|コラム|参考文献|考察)")
    args = ap.parse_args()
    skip_head = re.compile(args.skip_heading) if args.skip_heading else None

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    merged = defaultdict(lambda: {"count": 0, "kinds": set(), "chapters": []})
    total_lines = 0

    for f in sorted({Path(p) for p in args.files}):
        if not f.exists():
            print(f"見つかりません: {f}", file=sys.stderr)
            continue
        info, body_lines = scan(f, skip_head)
        total_lines += body_lines

        hi, lo = [], []
        for w, rec in info.items():
            kinds = rec["kinds"]
            row = (w, "・".join(sorted(kinds)), rec["count"], rec["first"])
            if kinds & set(PRIORITY) or "コード" in kinds:
                hi.append(row)
            elif rec["count"] >= args.min_count:
                lo.append(row)

        hi.sort(key=lambda r: -r[2])
        lo.sort(key=lambda r: -r[2])

        buf = [f"# 索引候補: {f.name}", "",
               f"本文 {body_lines} 行 / 候補 {len(hi) + len(lo)} 語"
               f"(優先度 高 {len(hi)}・低 {len(lo)})", "",
               "採用する語の `採` 欄に `o` を書く．", "",
               "## 優先度 高(見出し・定義・太字・コード)", "",
               "| 採 | 候補語 | 種別 | 回数 | 初出行 |",
               "| -- | ------ | ---- | ---- | ------ |"]
        for w, k, c, ln in hi:
            buf.append(f"|  | {w} | {k} | {c} | {ln} |")
        buf += ["", f"## 優先度 低(カタカナ・漢字熟語，{args.min_count} 回以上)", "",
                "| 採 | 候補語 | 種別 | 回数 | 初出行 |",
                "| -- | ------ | ---- | ---- | ------ |"]
        for w, k, c, ln in lo:
            buf.append(f"|  | {w} | {k} | {c} | {ln} |")

        dest = out_dir / f"candidates_{f.stem}.md"
        dest.write_text("\n".join(buf) + "\n", encoding="utf-8")
        print(f"{dest}: 候補 {len(hi) + len(lo)} 語")

        for w, rec in info.items():
            m = merged[w]
            m["count"] += rec["count"]
            m["kinds"] |= rec["kinds"]
            m["chapters"].append(f.stem.replace("chapter_", ""))

    rows = sorted(merged.items(), key=lambda kv: (-len(kv[1]["chapters"]), -kv[1]["count"]))
    buf = ["# 索引候補(全章)", "",
           f"本文 {total_lines} 行 / 異なり語 {len(rows)}", "",
           "複数の章に出る語ほど主見出しに向く．", "",
           "| 候補語 | 出現章 | 章数 | 総回数 | 種別 |",
           "| ------ | ------ | ---- | ------ | ---- |"]
    for w, rec in rows:
        if len(rec["chapters"]) < 2 and rec["count"] < args.min_count:
            continue
        chs = ", ".join(rec["chapters"])
        buf.append(f"| {w} | {chs} | {len(rec['chapters'])} | {rec['count']} | "
                   f"{'・'.join(sorted(rec['kinds']))} |")
    dest = out_dir / "candidates_all.md"
    dest.write_text("\n".join(buf) + "\n", encoding="utf-8")
    print(f"{dest}: 異なり語 {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
