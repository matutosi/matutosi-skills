#!/usr/bin/env python3
"""配置の JSON (layout.json) からグラフィカルアブストラクトを組み，点検する.

    python compose.py layout.json --out ga            # ga.png・ga.pdf を書き，点検する
    python compose.py layout.json --out ga --formats png,pdf,svg
    python compose.py layout.json --check-only        # 書き出さずに点検だけ

座標はすべて mm で，原点は左上．文字の大きさは pt (実寸)．
イラストは外部ツールで作った画像 (PNG など) を `image` 要素の `src` に置く．
画像がまだ無ければ，点線の枠と「画像待ち」の字を代わりに描く．

点検すること (結果は JSON で標準出力に出し，問題があれば終了コード 1):
  - text_overflow   文字が親の枠 (parent) か用紙の外にはみ出している
  - text_overlap    文字どうしが重なっている
  - text_on_image   文字が画像・グラフの上に載っている (要素に "over": true があれば許す)
  - font_too_small  文字が最小の大きさ (canvas.min_font_pt) より小さい
  - image_missing   イラストの画像がまだ無い
  - approx_values   グラフの値が概略 (原図からの読み取り) で，注記が無い

要るもの: matplotlib (と numpy)．画像の読み込みに Pillow があれば JPEG なども使える．
"""

import argparse
import json
import math
import os
import sys
import warnings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MM_PER_INCH = 25.4
PT_PER_MM = 72.0 / MM_PER_INCH

# 日本語の字が出る書体を，この順に探す
JP_FONTS = [
    "BIZ UDPGothic", "BIZ UDGothic", "Yu Gothic", "YuGothic", "Meiryo",
    "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans CJK JP",
    "Noto Sans JP", "IPAexGothic", "IPAGothic", "TakaoPGothic",
]

DEFAULT_CANVAS = {
    "width_mm": 330.0,
    "height_mm": 132.0,
    "dpi": 300,
    "background": "#ffffff",
    "font": "auto",
    "min_font_pt": 7.0,
    "text_color": "#333333",
}

ELEMENT_TYPES = ("panel", "box", "text", "image", "arrow", "chart", "line")


class LayoutError(ValueError):
    """配置の JSON の誤り."""


# ---------------------------------------------------------------- 読み込み

def load_layout(path):
    with open(path, encoding="utf-8") as f:
        layout = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    return normalize(layout, base)


def normalize(layout, base="."):
    """既定値を埋め，誤りを調べる．誤りは LayoutError で返す."""
    if not isinstance(layout, dict):
        raise LayoutError("配置は JSON のオブジェクトにする")
    canvas = dict(DEFAULT_CANVAS)
    canvas.update(layout.get("canvas", {}))
    for key in ("width_mm", "height_mm", "dpi", "min_font_pt"):
        try:
            canvas[key] = float(canvas[key])
        except (TypeError, ValueError):
            raise LayoutError("canvas.%s は数にする" % key)
        if canvas[key] <= 0:
            raise LayoutError("canvas.%s は正の数にする" % key)
    palette = layout.get("palette", {})
    elements = layout.get("elements")
    if not isinstance(elements, list) or not elements:
        raise LayoutError("elements (要素の並び) が空")
    ids = set()
    out = []
    for i, el in enumerate(elements):
        if not isinstance(el, dict):
            raise LayoutError("elements[%d] はオブジェクトにする" % i)
        el = dict(el)
        t = el.get("type")
        if t not in ELEMENT_TYPES:
            raise LayoutError("elements[%d] の type %r は %s のどれかにする" % (i, t, "/".join(ELEMENT_TYPES)))
        el.setdefault("id", "%s%d" % (t, i + 1))
        if el["id"] in ids:
            raise LayoutError("id %r が重なっている" % el["id"])
        ids.add(el["id"])
        if t in ("panel", "box", "image", "chart"):
            for key in ("x", "y", "w", "h"):
                if not isinstance(el.get(key), (int, float)):
                    raise LayoutError("%s の %s (mm) が無い" % (el["id"], key))
            if el["w"] <= 0 or el["h"] <= 0:
                raise LayoutError("%s の w・h は正の数にする" % el["id"])
        if t == "text":
            for key in ("x", "y"):
                if not isinstance(el.get(key), (int, float)):
                    raise LayoutError("%s の %s (mm) が無い" % (el["id"], key))
            if not isinstance(el.get("text"), str):
                raise LayoutError("%s の text が無い" % el["id"])
        if t in ("arrow", "line"):
            for key in ("from", "to"):
                v = el.get(key)
                if not (isinstance(v, list) and len(v) == 2):
                    raise LayoutError("%s の %s は [x, y] (mm) にする" % (el["id"], key))
        if t == "image" and el.get("src"):
            el["src_given"] = el["src"]   # 報告には JSON に書いたとおりの形を出す
            if not os.path.isabs(el["src"]):
                el["src"] = os.path.normpath(os.path.join(base, el["src"]))
        if t == "chart":
            if el.get("kind") not in ("scatter", "bar", "line"):
                raise LayoutError("%s の kind は scatter/bar/line のどれかにする" % el["id"])
            data = el.get("data")
            if not isinstance(data, dict) or "y" not in data:
                raise LayoutError("%s の data に y が無い" % el["id"])
        out.append(el)
    for el in out:
        p = el.get("parent")
        if p is not None and p not in ids:
            raise LayoutError("%s の parent %r が見つからない" % (el["id"], p))
    return {"canvas": canvas, "palette": palette, "elements": out,
            "style": layout.get("style", {}), "title": layout.get("title", "")}


def color(value, palette, default=None):
    if value is None:
        return default
    return palette.get(value, value)


# ---------------------------------------------------------------- 書体

def pick_font(requested="auto"):
    """使える書体の名前を返す．日本語の書体が無ければ None と警告."""
    from matplotlib import font_manager
    names = {f.name for f in font_manager.fontManager.ttflist}
    if requested and requested != "auto":
        if requested in names:
            return requested
        print("警告: 書体 %r が見つからない．ほかの日本語の書体を探す" % requested, file=sys.stderr)
    for name in JP_FONTS:
        if name in names:
            return name
    print("警告: 日本語の書体が見つからない．日本語の字は豆腐 (□) になる", file=sys.stderr)
    return None


# ---------------------------------------------------------------- 折り返し

def wrap_text(text, width_mm, size_pt, measure):
    """幅 width_mm に収まるよう1字ずつ折り返す (和文向け．欧文の語は切らない).

    measure(s) は文字列 s の幅 (mm) を返す関数．
    行頭に来てはいけない記号 (，．、。)」』) は前の行に残す．
    """
    no_head = set("，．、。)）」』】〉》!?！？・ー")
    lines = []
    for para in text.split("\n"):
        tokens = _tokens(para)
        line = ""
        for tok in tokens:
            trial = line + tok
            if line and measure(trial) > width_mm and tok[0] not in no_head:
                lines.append(line.rstrip())
                line = tok.lstrip()
            else:
                line = trial
        lines.append(line)
    return "\n".join(lines)


def _tokens(s):
    """欧文の語と数はひとまとまり，和文は1字ずつに分ける."""
    out = []
    buf = ""
    for ch in s:
        if ch.isascii() and not ch.isspace():
            buf += ch
            continue
        if buf:
            out.append(buf)
            buf = ""
        out.append(ch)
    if buf:
        out.append(buf)
    return out


# ---------------------------------------------------------------- 描画

class Composer:
    def __init__(self, layout):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        matplotlib.rcParams["pdf.fonttype"] = 42   # PDF に書体を埋め込む (文字のまま)
        matplotlib.rcParams["ps.fonttype"] = 42
        matplotlib.rcParams["svg.fonttype"] = "none"
        matplotlib.rcParams["axes.unicode_minus"] = False
        self.plt = plt
        self.layout = layout
        self.cv = layout["canvas"]
        self.pal = layout["palette"]
        self.font = pick_font(self.cv.get("font", "auto"))
        if self.font:
            matplotlib.rcParams["font.family"] = [self.font, "DejaVu Sans"]
        W, H = self.cv["width_mm"], self.cv["height_mm"]
        self.fig = plt.figure(figsize=(W / MM_PER_INCH, H / MM_PER_INCH), dpi=self.cv["dpi"])
        self.fig.patch.set_facecolor(self.cv["background"])
        ax = self.fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, W)
        ax.set_ylim(H, 0)          # 上が 0 (左上原点)
        ax.axis("off")
        self.ax = ax
        self.texts = []            # (要素 id, Text, 親の矩形, over を許すか, 属するグラフ id)
        self.rects = {}            # 要素 id -> (x, y, w, h)
        self.blocks = []           # 画像・グラフの描画域: (id, 矩形)
        self.chart_axes = []       # (グラフ id, Axes, グラフの枠)
        self.issues = []

    # --- 共通
    def rect_of(self, el):
        return (el["x"], el["y"], el["w"], el["h"])

    def parent_rect(self, el):
        p = el.get("parent")
        return self.rects.get(p) if p else None

    def add_issue(self, kind, el_id, message, **extra):
        d = {"kind": kind, "id": el_id, "message": message}
        d.update(extra)
        self.issues.append(d)

    def measure_mm(self, s, size, weight):
        from matplotlib.textpath import TextPath
        from matplotlib.font_manager import FontProperties
        fp = FontProperties(family=self.plt.rcParams["font.family"], size=size, weight=weight)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            bb = TextPath((0, 0), s or " ", prop=fp).get_extents()
        return bb.width / PT_PER_MM

    # --- 要素
    def draw(self):
        for el in self.layout["elements"]:
            if el["type"] in ("panel", "box", "image", "chart"):
                self.rects[el["id"]] = self.rect_of(el)
        for el in self.layout["elements"]:
            getattr(self, "draw_" + el["type"])(el)
        return self

    def draw_panel(self, el):
        from matplotlib.patches import FancyBboxPatch
        x, y, w, h = self.rect_of(el)
        r = float(el.get("radius", 2.0))
        patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=%g" % r,
                               facecolor=color(el.get("fill"), self.pal, "#f5f5f2"),
                               edgecolor=color(el.get("edge"), self.pal, "#999999"),
                               linewidth=float(el.get("linewidth", 0.8)), zorder=1)
        self.ax.add_patch(patch)
        if el.get("title"):
            pad = float(el.get("title_pad", 3.0))
            size = float(el.get("title_size", 12))
            t = self.ax.text(x + pad, y + pad, el["title"], ha="left", va="top",
                             fontsize=size, fontweight="bold",
                             color=color(el.get("title_color"), self.pal, self.cv["text_color"]),
                             zorder=5)
            self.texts.append((el["id"] + ".title", t, (x, y, w, h), False, None))

    def draw_box(self, el):
        from matplotlib.patches import FancyBboxPatch
        x, y, w, h = self.rect_of(el)
        r = float(el.get("radius", 1.5))
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=%g" % r,
                                         facecolor=color(el.get("fill"), self.pal, "#dddddd"),
                                         edgecolor=color(el.get("edge"), self.pal, "none"),
                                         linewidth=float(el.get("linewidth", 0.8)), zorder=2))
        if el.get("text"):
            size = float(el.get("size", 10))
            weight = el.get("weight", "normal")
            s = el["text"]
            # 手で改行を入れた文字は折り返さない (はみ出せば点検で知らせる)
            if el.get("wrap", "\n" not in s):
                s = wrap_text(s, w - 2 * float(el.get("pad", 1.5)), size,
                              lambda q: self.measure_mm(q, size, weight))
            t = self.ax.text(x + w / 2, y + h / 2, s, ha="center", va="center",
                             fontsize=size, fontweight=weight, linespacing=float(el.get("linespacing", 1.3)),
                             color=color(el.get("color"), self.pal, "#ffffff"), zorder=6)
            self.texts.append((el["id"], t, (x, y, w, h), False, None))

    def draw_text(self, el):
        size = float(el.get("size", 10))
        weight = el.get("weight", "normal")
        s = el["text"]
        if el.get("wrap_mm"):
            s = wrap_text(s, float(el["wrap_mm"]), size, lambda q: self.measure_mm(q, size, weight))
        t = self.ax.text(el["x"], el["y"], s,
                         ha=el.get("ha", "left"), va=el.get("va", "top"),
                         fontsize=size, fontweight=weight, fontstyle=el.get("style", "normal"),
                         linespacing=float(el.get("linespacing", 1.3)),
                         color=color(el.get("color"), self.pal, self.cv["text_color"]),
                         rotation=float(el.get("rotation", 0)), zorder=7)
        self.texts.append((el["id"], t, self.parent_rect(el), bool(el.get("over")), None))

    def draw_image(self, el):
        from matplotlib.patches import Rectangle
        x, y, w, h = self.rect_of(el)
        src = el.get("src")
        if src and os.path.exists(src):
            img = self._read_image(src)
            # 生成した絵の背景はわずかに灰色がかることが多く，枠の地色との境目が四角く見える．
            # 白に近い画素を透明にして，枠の地色になじませる (knockout_white: false で止める)
            ko = el.get("knockout_white", True)
            if ko:
                img = knockout_white(img, 245 if ko is True else int(ko))
            # 生成した絵は周りの余白が広い．余白を切り落として枠いっぱいに使う (trim_white: false で止める)
            if el.get("trim_white", True):
                img = trim_white(img)
            ih, iw = img.shape[0], img.shape[1]
            # 枠に収まるよう縦横比を保って縮め，halign・valign (既定は中央) に寄せる
            scale = min(w / iw, h / ih)
            dw, dh = iw * scale, ih * scale
            ha, va = el.get("halign", "center"), el.get("valign", "center")
            x0 = x if ha == "left" else (x + w - dw if ha == "right" else x + (w - dw) / 2)
            y0 = y if va == "top" else (y + h - dh if va == "bottom" else y + (h - dh) / 2)
            self.ax.imshow(img, extent=(x0, x0 + dw, y0 + dh, y0), zorder=3, interpolation="antialiased")
            self.ax.set_xlim(0, self.cv["width_mm"])
            self.ax.set_ylim(self.cv["height_mm"], 0)
            self.blocks.append((el["id"], (x0, y0, dw, dh)))
        else:
            self.ax.add_patch(Rectangle((x, y), w, h, facecolor="none", edgecolor="#aaaaaa",
                                        linestyle=(0, (3, 2)), linewidth=0.8, zorder=3))
            self.ax.text(x + w / 2, y + h / 2, "画像待ち\n%s" % el["id"], ha="center", va="center",
                         fontsize=8, color="#aaaaaa", zorder=3)
            self.blocks.append((el["id"], (x, y, w, h)))
            given = el.get("src_given", src)
            self.add_issue("image_missing", el["id"],
                           "イラストの画像がまだ無い (%s)" % (given or "src の指定なし"),
                           src=given or "")

    def _read_image(self, path):
        try:
            from PIL import Image
            import numpy as np
            with Image.open(path) as im:
                return np.asarray(im.convert("RGBA"))
        except ImportError:
            return self.plt.imread(path)

    def draw_arrow(self, el):
        from matplotlib.patches import FancyArrowPatch
        lw = float(el.get("linewidth", 2.0))
        style = "-|>,head_length=%g,head_width=%g" % (float(el.get("head_length", 0.6)) * lw,
                                                      float(el.get("head_width", 0.35)) * lw)
        self.ax.add_patch(FancyArrowPatch(tuple(el["from"]), tuple(el["to"]), arrowstyle=style,
                                          mutation_scale=4, linewidth=lw,
                                          color=color(el.get("color"), self.pal, "#555555"),
                                          shrinkA=0, shrinkB=0, zorder=4))

    def draw_line(self, el):
        (x1, y1), (x2, y2) = el["from"], el["to"]
        self.ax.plot([x1, x2], [y1, y2], color=color(el.get("color"), self.pal, "#999999"),
                     linewidth=float(el.get("linewidth", 0.8)),
                     linestyle=el.get("linestyle", "-"), zorder=2)

    def draw_chart(self, el):
        x, y, w, h = self.rect_of(el)
        W, H = self.cv["width_mm"], self.cv["height_mm"]
        # 軸の目盛と軸名のための余白 (mm)．グラフの枠 (x, y, w, h) の内側に取る
        ml, mr, mt, mb = [float(v) for v in el.get("margins_mm", [12, 3, 3, 10])]
        ax = self.fig.add_axes([(x + ml) / W, 1 - (y + h - mb) / H, (w - ml - mr) / W, (h - mt - mb) / H])
        ax.patch.set_alpha(0)
        size = float(el.get("size", 8))
        data = el["data"]
        ys = data["y"]
        xs = data.get("x", list(range(len(ys))))
        groups = data.get("group")
        colors = el.get("colors", {})
        default_c = color(el.get("color"), self.pal, "#4477aa")
        if el["kind"] == "bar":
            cs = [color(colors.get(str(g)), self.pal, default_c) for g in (groups or xs)]
            pos = list(range(len(ys)))
            ax.bar(pos, ys, color=cs, width=float(el.get("bar_width", 0.6)))
            ax.set_xticks(pos)
            ax.set_xticklabels([str(v) for v in xs])
            if el.get("bar_labels", True):
                for p, v in zip(pos, ys):
                    t = ax.text(p, v, " %s" % _fmt(v), ha="center", va="bottom", fontsize=size)
                    self.texts.append((el["id"] + ".label", t, (x, y, w, h), True, el["id"]))
        else:
            if groups:
                order = []
                for g in groups:
                    if g not in order:
                        order.append(g)
                for g in order:
                    gx = [a for a, b in zip(xs, groups) if b == g]
                    gy = [a for a, b in zip(ys, groups) if b == g]
                    c = color(colors.get(str(g)), self.pal, default_c)
                    self._series(ax, el["kind"], gx, gy, c, str(g))
                if el.get("legend"):
                    leg = ax.legend(fontsize=size, frameon=False, loc=el.get("legend_loc", "best"))
                    for t in leg.get_texts():
                        self.texts.append((el["id"] + ".legend", t, (x, y, w, h), True, el["id"]))
            else:
                self._series(ax, el["kind"], xs, ys, default_c, None)
        if el.get("xlim"):
            ax.set_xlim(*el["xlim"])
        if el.get("ylim"):
            ax.set_ylim(*el["ylim"])
        if el.get("xticks") is not None:
            ax.set_xticks(el["xticks"])
        if el.get("yticks") is not None:
            ax.set_yticks(el["yticks"])
        ax.set_xlabel(el.get("xlabel", ""), fontsize=size + 1)
        ax.set_ylabel(el.get("ylabel", ""), fontsize=size + 1)
        ax.tick_params(labelsize=size)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        self.chart_axes.append((el["id"], ax, (x, y, w, h)))   # 目盛は点検のときに見えるものだけ拾う
        for t in (ax.xaxis.label, ax.yaxis.label):
            if t.get_text():
                self.texts.append((el["id"] + ".axislabel", t, (x, y, w, h), True, el["id"]))
        self.blocks.append((el["id"], (x + ml, y + mt, w - ml - mr, h - mt - mb)))
        if el.get("approx") and not el.get("approx_note"):
            self.add_issue("approx_values", el["id"],
                           "グラフの値は概略だが，図の中に注記 (approx_note) が無い")
        if el.get("approx_note"):
            # 右上 (描画域の上の余白) に置く．軸名とは重ならない
            t = self.ax.text(x + w - mr, y + 0.5, el["approx_note"], ha="right", va="top",
                             fontsize=float(el.get("note_size", max(size - 1, self.cv["min_font_pt"]))),
                             color="#888888", zorder=7)
            self.texts.append((el["id"] + ".note", t, self.parent_rect(el) or (x, y, w, h), True, el["id"]))

    def _series(self, ax, kind, xs, ys, c, label):
        if kind == "scatter":
            ax.scatter(xs, ys, color=c, s=14, label=label, zorder=3)
        else:
            ax.plot(xs, ys, color=c, marker="o", markersize=3, label=label)

    # ------------------------------------------------------------ 点検
    def check(self):
        self.fig.canvas.draw()
        renderer = self.fig.canvas.get_renderer()
        W, H = self.cv["width_mm"], self.cv["height_mm"]
        px_per_mm = self.cv["dpi"] / MM_PER_INCH
        for cid, cax, crect in self.chart_axes:
            for axis, lim in ((cax.xaxis, cax.get_xlim()), (cax.yaxis, cax.get_ylim())):
                lo, hi = min(lim), max(lim)
                span = (hi - lo) or 1.0
                for tick in axis.get_major_ticks():
                    loc = tick.get_loc()
                    if loc is None or not (lo - 1e-9 * span <= loc <= hi + 1e-9 * span):
                        continue   # 軸の外の目盛は描かれない
                    if tick.label1.get_visible() and tick.label1.get_text():
                        self.texts.append((cid + ".tick", tick.label1, crect, True, cid))
        boxes = []
        for el_id, t, prect, over, chart in self.texts:
            if not t.get_text().strip() or not t.get_visible():
                continue
            bb = t.get_window_extent(renderer=renderer)
            # 表示座標 (左下原点・px) -> mm (左上原点)
            r = (bb.x0 / px_per_mm, H - bb.y1 / px_per_mm, bb.width / px_per_mm, bb.height / px_per_mm)
            boxes.append((el_id, t, r, over, chart))
            size = t.get_fontsize()
            if size < self.cv["min_font_pt"] - 1e-6:
                self.add_issue("font_too_small", el_id, "文字が %.1f pt で，最小 %.1f pt より小さい"
                               % (size, self.cv["min_font_pt"]), text=t.get_text(), size_pt=round(size, 2))
            area = prect or (0, 0, W, H)
            out = _outside(r, area)
            if out > 0.3:
                where = "親の枠" if prect else "用紙"
                self.add_issue("text_overflow", el_id, "文字が%sから %.1f mm はみ出している" % (where, out),
                               text=t.get_text(), bbox_mm=_round(r))
            elif prect and _outside(r, (0, 0, W, H)) > 0.3:
                self.add_issue("text_overflow", el_id, "文字が用紙からはみ出している",
                               text=t.get_text(), bbox_mm=_round(r))
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a[4] and a[4] == b[4] and a[0].endswith(".tick") and b[0].endswith(".tick"):
                    continue   # 同じグラフの目盛どうし (matplotlib が間引く)
                ov = _overlap(a[2], b[2])
                if ov > 0.3:
                    self.add_issue("text_overlap", a[0], "文字が %s と重なっている (%.1f mm)" % (b[0], ov),
                                   text=a[1].get_text(), other=b[1].get_text())
        for el_id, t, r, over, chart in boxes:
            if over:
                continue
            for bid, br in self.blocks:
                if bid == chart:
                    continue
                ov = _overlap(r, br)
                if ov > 0.3:
                    self.add_issue("text_on_image", el_id, "文字が %s の上に載っている (%.1f mm)．意図したなら \"over\": true" % (bid, ov),
                                   text=t.get_text())
        return self.issues

    def save(self, base, formats):
        written = []
        for fmt in formats:
            path = "%s.%s" % (base, fmt)
            kw = {"dpi": self.cv["dpi"]} if fmt in ("png", "jpg", "tif", "tiff") else {}
            self.fig.savefig(path, facecolor=self.fig.get_facecolor(), **kw)
            written.append(path)
        return written


def knockout_white(img, threshold=245):
    """RGB の3つとも threshold 以上の画素を透明にした RGBA の配列を返す (0-255 か 0-1 の配列)."""
    import numpy as np
    a = np.asarray(img)
    if a.dtype != np.uint8:
        a = (np.clip(a, 0, 1) * 255).astype(np.uint8)
    if a.ndim == 2:
        a = np.stack([a] * 3, axis=-1)
    if a.shape[2] == 3:
        a = np.concatenate([a, np.full(a.shape[:2] + (1,), 255, np.uint8)], axis=2)
    a = a.copy()
    rgb = a[:, :, :3].astype(int)
    white = (rgb >= threshold).all(axis=2)
    # 背景がうすい灰色・うすい青などのこともある．縁の色 (中央値) が明るければ，それに近い色も背景とみなす
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    if bg.min() >= 225:
        white |= (np.abs(rgb - bg) <= 10).all(axis=2)
    a[white, 3] = 0
    return a


def trim_white(img, threshold=225, pad=0.02):
    """透明か白に近い画素だけの縁を切り落とす．pad は残す余白 (長い辺に対する割合).

    生成した絵の縁には，うすい灰色のざらつき (RGB で 220-245) が散らばることがある．
    切る範囲を決めるときは threshold を低め (225) にし，画素が 1% に満たない行・列は無視する．
    """
    import numpy as np
    a = np.asarray(img)
    if a.dtype != np.uint8:
        a = (np.clip(a, 0, 1) * 255).astype(np.uint8)
    rgb = a[:, :, :3] if a.ndim == 3 else np.stack([a] * 3, axis=-1)
    ink = ~((rgb >= threshold).all(axis=2))
    if a.ndim == 3 and a.shape[2] == 4:
        ink &= a[:, :, 3] > 0
    # 隅に残る小さな点 (生成 AI の印など) で切り損ねないよう，ごく少ない画素の行・列は無視する
    min_r = max(1, int(a.shape[1] * 0.01))
    min_c = max(1, int(a.shape[0] * 0.01))
    rows = np.where(ink.sum(axis=1) >= min_r)[0]
    cols = np.where(ink.sum(axis=0) >= min_c)[0]
    if rows.size == 0 or cols.size == 0:
        return a
    p = int(round(max(a.shape[:2]) * pad))
    r0, r1 = max(rows[0] - p, 0), min(rows[-1] + p + 1, a.shape[0])
    c0, c1 = max(cols[0] - p, 0), min(cols[-1] + p + 1, a.shape[1])
    return a[r0:r1, c0:c1]


def _fmt(v):
    return ("%d" % v) if float(v).is_integer() else ("%g" % v)


def _round(r):
    return [round(v, 1) for v in r]


def _outside(r, area):
    """矩形 r が area からはみ出す最大の長さ (mm)."""
    x, y, w, h = r
    ax, ay, aw, ah = area
    return max(0.0, ax - x, ay - y, (x + w) - (ax + aw), (y + h) - (ay + ah))


def _overlap(a, b):
    """2つの矩形の重なりの短い辺の長さ (mm)．重ならなければ 0."""
    dx = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    dy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if dx <= 0 or dy <= 0:
        return 0.0
    return min(dx, dy)


def run(layout, out=None, formats=("png", "pdf"), check_only=False):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*Glyph.*missing.*")
        warnings.filterwarnings("ignore", message=".*findfont.*")
        c = Composer(layout).draw()
        issues = c.check()
        written = [] if (check_only or not out) else c.save(out, formats)
        c.plt.close(c.fig)
    return {"font": c.font, "size_mm": [layout["canvas"]["width_mm"], layout["canvas"]["height_mm"]],
            "size_px": [int(round(layout["canvas"]["width_mm"] / MM_PER_INCH * layout["canvas"]["dpi"])),
                        int(round(layout["canvas"]["height_mm"] / MM_PER_INCH * layout["canvas"]["dpi"]))],
            "written": written, "issue_count": len(issues), "issues": issues}


def main(argv=None):
    ap = argparse.ArgumentParser(description="配置の JSON からグラフィカルアブストラクトを組み，点検する")
    ap.add_argument("layout", help="配置の JSON (layout.json)")
    ap.add_argument("--out", help="書き出す名前 (拡張子なし)．例: ga → ga.png・ga.pdf")
    ap.add_argument("--formats", default="png,pdf", help="書き出す形式 (既定 png,pdf．svg・tif も可)")
    ap.add_argument("--check-only", action="store_true", help="書き出さずに点検だけ")
    ap.add_argument("--allow-missing-images", action="store_true",
                    help="画像待ち (image_missing) だけなら終了コードを 0 にする")
    args = ap.parse_args(argv)
    try:
        layout = load_layout(args.layout)
    except (LayoutError, json.JSONDecodeError) as e:
        print("配置の誤り: %s" % e, file=sys.stderr)
        return 2
    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    result = run(layout, args.out, formats, args.check_only or not args.out)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    kinds = {i["kind"] for i in result["issues"]}
    if args.allow_missing_images:
        kinds.discard("image_missing")
    return 1 if kinds else 0


if __name__ == "__main__":
    sys.exit(main())
