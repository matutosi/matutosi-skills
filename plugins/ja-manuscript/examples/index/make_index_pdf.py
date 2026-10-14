# -*- coding: utf-8 -*-
"""build-index を試すための小さな本の PDF を作る.

    python make_index_pdf.py                 # sample_book.pdf を作り直す
    python make_index_pdf.py --font <ttf>    # 日本語フォントを指定する

chapter_01.md〜chapter_03.md を簡単に組んで PDF にする．
- 1ページ目は目次で，ノンブルは付けない (本文は2ページ目から 1 になる)．
- 章の見出しをしおりに入れる (build_index.py は，しおりの `第N章` で章の範囲を決める)．
- 日本語フォントは埋め込む (使った字だけの部分集合にする)．

PyMuPDF と fontTools が要る (pip install pymupdf fonttools)．
日本語フォントは，見つかった順に BIZ UDゴシック・游ゴシック・メイリオ・Noto Sans CJK を使う．
見つからないときは --font で指定する．
"""
import argparse
import re
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:
    sys.exit("PyMuPDF が要ります: pip install pymupdf fonttools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
OUT = HERE / "sample_book.pdf"

PAGE_W, PAGE_H = 300, 420       # A6
MARGIN_X, TOP, BOTTOM = 34, 56, 56
BODY, LEAD = 11, 22

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\BIZ-UDGothicR.ttc",
    r"C:\Windows\Fonts\YuGothR.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
]


def find_font(arg):
    if arg:
        return arg
    for c in FONT_CANDIDATES:
        if Path(c).exists():
            return c
    sys.exit("日本語フォントが見つかりません．--font で指定してください")


def parse(md):
    """Markdown を (種類, 文字列) の並びにする．段落は行をつなぐ．"""
    out, para = [], []

    def flush():
        if para:
            out.append(("p", "".join(para)))
            para.clear()

    for line in md.splitlines():
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("#"):
            flush()
            level = len(s) - len(s.lstrip("#"))
            out.append((f"h{level}", re.sub(r"\s*\{#.*\}$", "", s.lstrip("# ")).strip()))
        elif s.startswith("- "):
            flush()
            out.append(("li", "・" + s[2:]))
        else:
            para.append(s.replace("**", ""))
    flush()
    return out


class Typesetter:
    def __init__(self, doc, fontfile):
        self.doc = doc
        self.fontfile = fontfile
        self.font = pymupdf.Font(fontfile=fontfile)
        self.page = None
        self.y = 0
        self.nombre = 0          # いまのページのノンブル (0 は付けない)
        self.toc = []

    def new_page(self, nombre=True):
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.page.insert_font(fontname="jp", fontfile=self.fontfile)
        self.y = TOP
        if nombre:
            self.nombre += 1
            self.text((PAGE_W / 2 - 3, PAGE_H - 36), str(self.nombre), 9)

    def text(self, xy, s, size):
        self.page.insert_text(xy, s, fontname="jp", fontsize=size)

    def wrap(self, s, size, width):
        lines, cur = [], ""
        for ch in s:
            if self.font.text_length(cur + ch, size) > width and ch not in "，．、。）」":
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        return lines + [cur] if cur else lines

    def ensure(self, need):
        if self.y + need > PAGE_H - BOTTOM:
            self.new_page()

    def add(self, kind, val):
        width = PAGE_W - 2 * MARGIN_X
        if kind == "h1":
            self.new_page()      # 章は新しいページから
            self.toc.append([1, val, self.doc.page_count])
            self.y += 6
            self.text((MARGIN_X, self.y), val, 16)
            self.y += 34
        elif kind == "h2":
            self.ensure(60)
            self.y += 10
            self.text((MARGIN_X, self.y), val, 12)
            self.toc.append([2, val, self.doc.page_count])
            self.y += 22
        else:
            indent = 10 if kind == "li" else 0
            lines = self.wrap(val, BODY, width - indent - (0 if kind == "li" else BODY))
            for i, ln in enumerate(lines):
                self.ensure(LEAD)
                x = MARGIN_X + indent + (BODY if kind == "p" and i == 0 else 0)
                self.text((x, self.y), ln, BODY)
                self.y += LEAD
            self.y += 4


def main():
    ap = argparse.ArgumentParser(description="build-index の例の PDF を作る")
    ap.add_argument("--font", help="日本語フォント (ttf/ttc)")
    args = ap.parse_args()
    fontfile = find_font(args.font)

    doc = pymupdf.open()
    ts = Typesetter(doc, fontfile)

    # 1ページ目: 目次 (ノンブルなし．しおりには入れない)
    chapters = sorted(HERE.glob("chapter_*.md"))
    titles = []
    for p in chapters:
        first = p.read_text(encoding="utf-8").splitlines()[0]
        titles.append(re.sub(r"\s*\{#.*\}$", "", first.lstrip("# ")).strip())
    ts.new_page(nombre=False)
    ts.text((MARGIN_X, TOP + 20), "植生解析入門", 20)
    ts.text((MARGIN_X, TOP + 60), "目次", 13)
    for i, t in enumerate(titles):
        ts.text((MARGIN_X + 10, TOP + 90 + i * 24), t, BODY)

    for p in chapters:
        for kind, val in parse(p.read_text(encoding="utf-8")):
            ts.add(kind, val)

    doc.set_toc(ts.toc)
    doc.set_metadata({"title": "植生解析入門 (build-index の例)"})
    try:
        doc.subset_fonts()
    except Exception as e:  # fontTools が無いときは全部入りになる
        print("警告: フォントの部分集合化に失敗:", e)
    doc.save(OUT, garbage=4, deflate=True)
    print(f"{OUT.name}: {doc.page_count} ページ / {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
