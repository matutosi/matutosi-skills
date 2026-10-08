# -*- coding: utf-8 -*-
"""apply-proof-marks を試すための朱書き PDF を作る.

    python make_proof_pdf.py            # chapter_01_proof.pdf を作り直す

../chapter_01.md を簡単に組んで PDF にし，手書きの注釈 (Ink) で朱書きを入れる．
手書きの文字は，フォントの字形の輪郭を少し揺らした筆跡で描く (輪郭だけの字になる)．
朱書きの中身と，反映後の正解は expected_fixes.json にある．

PyMuPDF と fontTools が要る (pip install pymupdf fonttools)．
日本語の字形は PyMuPDF に組み込みのフォントを使うので，フォントの導入は要らない．
"""
import io
import math
import random
import re
import sys
from pathlib import Path

try:
    import pymupdf
    from fontTools.pens.basePen import BasePen
    from fontTools.ttLib import TTFont
except ImportError:
    sys.exit("PyMuPDF と fontTools が要ります: pip install pymupdf fonttools")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "chapter_01.md"
OUT = HERE / "chapter_01_proof.pdf"

PAGE_W, PAGE_H = 595, 842      # A4
MARGIN_X, TOP = 80, 90
BODY, LEAD = 10.5, 26          # 本文の文字サイズと行送り (校正用に行間を広くとる)
HAND = 10                      # 手書きの文字の大きさ
RED = (0.85, 0.1, 0.1)

FONT = pymupdf.Font("japan")
TT = TTFont(io.BytesIO(FONT.buffer))
GLYPHS = TT.getGlyphSet()
CMAP = TT.getBestCmap()
UPM = TT["head"].unitsPerEm
rng = random.Random(7)         # 揺れを毎回同じにする


# ---------------------------------------------------------------- 組版
def blocks(md):
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
            out.append((f"h{level}", re.sub(r"\s*\{#.*\}$", "", s.lstrip("# "))))
        elif s.startswith("- "):
            flush()
            out.append(("li", "・" + s[2:]))
        elif s.startswith("|"):
            flush()
            if not re.fullmatch(r"\|[-|: ]+\|", s):
                out.append(("tr", [c.strip() for c in s.strip("|").split("|")]))
        else:
            para.append(s)
    flush()
    return out


# 朱書きを入れる語．行をまたぐと位置を探せないので，途中で折り返さない
KEEP = ["誤時", "状況は", "すことができます", "調査区の番号の重複", "樹形図"]


def wrap(text, size, width):
    lines, cur = [], ""
    for ch in text:
        # 句読点と閉じ括弧は行頭に置かず，前の行にぶら下げる
        if FONT.text_length(cur + ch, size) > width and ch not in "，．、。）」":
            cut = len(cur)
            for w in KEEP:
                pos = text.find(w)
                start = len("".join(lines))
                # 折り返す位置が語の途中なら，語の前で折り返す
                if pos >= 0 and pos < start + cut < pos + len(w):
                    cut = pos - start
            lines.append(cur[:cut])
            cur = cur[cut:] + ch
        else:
            cur += ch
    return lines + [cur] if cur else lines


def typeset(doc):
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    width = PAGE_W - 2 * MARGIN_X
    y = TOP
    md = SRC.read_text(encoding="utf-8").replace(r"\@ref(ch-read)", "2")
    for kind, val in blocks(md):
        if kind == "h1":
            y += 6
            page.insert_text((MARGIN_X, y), val, fontname="japan", fontsize=16)
            y += 34
        elif kind == "h2":
            y += 12
            page.insert_text((MARGIN_X, y), val, fontname="japan", fontsize=12.5)
            y += 24
        elif kind == "tr":
            for i, cell in enumerate(val):
                page.insert_text((MARGIN_X + 20 + i * 90, y), cell,
                                 fontname="japan", fontsize=BODY)
            y += LEAD
        else:
            indent = 10 if kind == "li" else 0
            first = True
            for ln in wrap(val, BODY, width - indent - (0 if kind == "li" else BODY)):
                x = MARGIN_X + indent + (BODY if kind == "p" and first else 0)
                page.insert_text((x, y), ln, fontname="japan", fontsize=BODY)
                y += LEAD
                first = False
            y += 4
    page.insert_text((PAGE_W / 2 - 4, PAGE_H - 40), "1", fontname="helv", fontsize=9)
    return page


# ---------------------------------------------------------------- 手書きの筆跡
class StrokePen(BasePen):
    """字形の輪郭を折れ線の並びにする (曲線は細かく刻む)．"""

    def __init__(self, gs):
        super().__init__(gs)
        self.strokes, self.cur = [], []

    def _moveTo(self, p):
        self.cur = [p]

    def _lineTo(self, p):
        self.cur.append(p)

    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        for i in range(1, 7):
            t = i / 6
            u = 1 - t
            self.cur.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                             u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))

    def _qCurveToOne(self, p1, p2):
        p0 = self.cur[-1]
        for i in range(1, 5):
            t = i / 4
            u = 1 - t
            self.cur.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                             u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))

    def _closePath(self):
        if self.cur:
            self.cur.append(self.cur[0])
            self.strokes.append(self.cur)
        self.cur = []

    _endPath = _closePath


def jitter(pts, amp=0.25):
    return [(x + rng.uniform(-amp, amp), y + rng.uniform(-amp, amp)) for x, y in pts]


def hand_text(text, x, y, size=HAND, vertical=False):
    """手書きの文字の筆跡．(x, y) は1字目の左上．ページ座標 (上が 0)．"""
    strokes = []
    for ch in text:
        gs = GLYPHS[CMAP[ord(ch)]]
        pen = StrokePen(GLYPHS)
        gs.draw(pen)
        k = size / UPM
        tilt = rng.uniform(-0.04, 0.04)
        for st in pen.strokes:
            pts = [(x + gx * k + gy * k * tilt, y + size * 0.88 - gy * k) for gx, gy in st]
            strokes.append(jitter(pts))
        if vertical:
            y += size * 1.05
        else:
            x += gs.width * k * 1.02
    return strokes


def line(p, q, n=8, amp=0.4):
    return jitter([(p[0] + (q[0] - p[0]) * i / n, p[1] + (q[1] - p[1]) * i / n)
                   for i in range(n + 1)], amp)


def find(page, text, nth=0):
    hits = page.search_for(text)
    if len(hits) <= nth:
        sys.exit(f"組んだ PDF に「{text}」が見つからない")
    return hits[nth]


def ink(page, strokes):
    a = page.add_ink_annot(strokes)
    a.set_colors(stroke=RED)
    a.set_border(width=0.9)
    a.update()


def strike(r):
    """取り消し線 (少し右上がり)．"""
    mid = (r.y0 + r.y1) / 2
    return line((r.x0 - 1, mid + 1), (r.x1 + 1, mid - 1))


def lead_line(r, to):
    """取り消した語から，書き込みまでの引き出し線．"""
    return line(((r.x0 + r.x1) / 2, r.y0), to, n=6)


# ---------------------------------------------------------------- 朱書き
def above(r, dx=0):
    """行間 (語の上) に書き込むときの左上の位置．"""
    return r.x0 + dx, r.y0 - HAND - 3


def mark(page):
    # 1. 「誤時」→「誤字」: 「時」を消して上に「字」
    r = find(page, "誤時")
    t = pymupdf.Rect((r.x0 + r.x1) / 2, r.y0, r.x1, r.y1)
    x, y = above(t, 4)
    ink(page, [strike(t), lead_line(t, (x, y + HAND))] + hand_text("字", x, y))

    # 2. 2つ目の「状況は」を削除 (取り消し線と，削除の印「トル」)
    t = find(page, "状況は", nth=1)
    x, y = above(t, 16)
    ink(page, [strike(t), lead_line(t, (x, y + HAND))] + hand_text("トル", x, y))

    # 3. 「洗い出すことができます」→「洗い出します」
    r = find(page, "すことができます")
    x, y = above(r, 20)
    ink(page, [strike(r), lead_line(r, (x, y + HAND))] + hand_text("します", x, y))

    # 4. 「調査区の番号の重複」の後に「と欠番」を挿入 (くの字の挿入記号)
    r = find(page, "調査区の番号の重複")
    x, yb = r.x1 + 1, r.y1 + 1
    caret = line((x - 4, yb + 6), (x, yb), 3) + line((x, yb), (x + 4, yb + 6), 3)[1:]
    ink(page, [caret, line((x, yb), (x + 12, r.y0 + 2), 4)] + hand_text("と欠番", x + 14, r.y0 - 4))

    # 5. 全角の括弧を半角に (両方の括弧を丸で囲み，右に「半角」と書く)
    strokes = []
    for ch in "（）":
        c = find(page, ch)
        cx, cy, rad = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2, 7
        strokes.append(jitter([(cx + rad * math.cos(a / 12 * 2 * math.pi + 0.3),
                                cy + rad * math.sin(a / 12 * 2 * math.pi + 0.3)) for a in range(14)], 0.5))
    c = find(page, "）")
    cy = (c.y0 + c.y1) / 2
    ink(page, strokes + [line((c.x1 + 2, cy), (c.x1 + 16, cy), 4)]
        + hand_text("半角", c.x1 + 18, cy - HAND / 2))

    # 6. 「樹形図」→「デンドログラム」(用語をそろえる)
    r = find(page, "樹形図")
    x, y = above(r, -2)
    ink(page, [strike(r), lead_line(r, (r.x0 + 10, y + HAND))] + hand_text("デンドログラム", x, y))

    # 7. 要判断: 表の右の余白に「縦長の例も?」(勝手に決めない書き込み)
    r = find(page, "オミナエシ")
    x = PAGE_W - 62
    ink(page, [line((r.x1 + 60, r.y0 - 20), (x - 6, r.y0 - 20), 6)]
        + hand_text("縦長の例も？", x, r.y0 - 60, vertical=True))


def main():
    doc = pymupdf.open()
    page = typeset(doc)
    mark(page)
    doc.set_metadata({"title": "apply-proof-marks の練習用 (第1章の朱書き)"})
    doc.save(OUT, garbage=3, deflate=True)
    print(f"{OUT.name}: 朱書き {len(list(page.annots()))} 個")


if __name__ == "__main__":
    main()
