# -*- coding: utf-8 -*-
"""紙の校正 PDF から朱書き(Ink 注釈)を取り出し、その周辺だけを画像に切り出す。

ページ全体を読むかわりに、朱書きのある帯だけを読めるようにする。
Ink 注釈の座標を使うので、図の中の緑色を朱書きと取り違えることがない。

1つの帯について、最大3枚を出す。

| ファイル            | 中身                     | いつ要るか                       |
| ------------------- | ------------------------ | -------------------------------- |
| `pNNN_bK.png`       | 朱書き入り(そのまま)     | いつも。どの字に何をしたかが分かる |
| `pNNN_bK_clean.png` | 朱書きを消した版         | 朱書きが本文に重なって読めないとき |
| `pNNN_bK_ink.png`   | 朱書きだけを白地に置いた版 | 手書き文字そのものが読みにくいとき |

clean は画像から緑を消したのではなく、**PDF から `/Annots` を外して描画し直したもの**。
ink はその2枚の差分なので、どちらも下の文字と混ざらない。

使い方:
    python extract_marks.py _review/foo.pdf --list            # 一覧だけ
    python extract_marks.py _review/foo.pdf --pages 56-71     # 範囲を切り出す
    python extract_marks.py _review/foo.pdf --pages 7 --clean always --ink always
    python extract_marks.py _review/foo.pdf --pages 7 --zoom  # 筆跡ごとに拡大も出す

画像 (スキャン・写真の jpg/png/tif) を渡すと、朱書きを**色で**探す。
    python extract_marks.py _review/scan/*.jpg --color red    # 紙に赤ペン(既定)
    python extract_marks.py _review/scan/page01.png --color green
画像では Ink 注釈の座標が無いので、図の中の同じ色も拾う(帯を見て外す)。
朱書きの下の字は戻せないので `_clean` は作らない。`_ink` は色の画素だけを白地に置いた版。
"""
import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

try:
    import pypdf
except ImportError:
    sys.exit("pypdf が要ります: pip install pypdf")
try:
    from PIL import Image  # noqa: F401  (pypdfium2 の to_pil が使う)
except ImportError:
    sys.exit("Pillow が要ります: pip install pillow")
try:
    import pypdfium2 as pdfium
except ImportError:
    sys.exit("pypdfium2 が要ります: pip install pypdfium2")
try:
    import numpy as np
except ImportError:
    np = None


# ---------------------------------------------------------------- 注釈の取り出し
def ink_rects(page):
    """1ページの Ink 注釈の矩形(PDF 座標)を返す。"""
    annots = page.get("/Annots")
    if not annots:
        return []
    try:
        annots = annots.get_object()
    except Exception:
        pass
    out = []
    for ref in annots:
        obj = ref.get_object()
        if str(obj.get("/Subtype")) != "/Ink":
            continue
        r = obj.get("/Rect")
        out.append([float(r[0]), float(r[1]), float(r[2]), float(r[3])])
    return out


def to_bands(rects, pad):
    """矩形を縦方向に統合して帯(y0, y1, 本数)にする。"""
    spans = sorted((r[1] - pad, r[3] + pad) for r in rects)
    if not spans:
        return []
    bands = [[spans[0][0], spans[0][1], 1]]
    for y0, y1 in spans[1:]:
        if y0 <= bands[-1][1]:
            bands[-1][1] = max(bands[-1][1], y1)
            bands[-1][2] += 1
        else:
            bands.append([y0, y1, 1])
    return bands


def to_clusters(rects, gap_x=25.0, gap_y=12.0):
    """近い筆跡どうしをまとめて、書き込み1つぶんの矩形にする。"""
    out = []
    for r in sorted(rects, key=lambda r: (-r[3], r[0])):
        for c in out:
            if not (r[2] < c[0] - gap_x or r[0] > c[2] + gap_x
                    or r[3] < c[1] - gap_y or r[1] > c[3] + gap_y):
                c[0] = min(c[0], r[0]); c[1] = min(c[1], r[1])
                c[2] = max(c[2], r[2]); c[3] = max(c[3], r[3])
                break
        else:
            out.append(list(r))
    return sorted(out, key=lambda c: -c[3])


# ---------------------------------------------------------------- 描画
def render(pdf, page_no, dpi, strip_annots=False):
    """1ページを描画して Image を返す。

    strip_annots=True で注釈を描かない(朱書きを消した版)。PDF は書き換えない。
    """
    doc = pdfium.PdfDocument(str(pdf))
    try:
        page = doc[page_no - 1]
        img = page.render(scale=dpi / 72, draw_annots=not strip_annots).to_pil()
        return img.convert("RGB")
    finally:
        doc.close()


def ink_only(band, clean_band):
    """朱書き入りと朱書きなしの差分から、朱書きだけを白地に置いた画像を作る。"""
    if np is None:
        return None
    a = np.asarray(band.convert("RGB")).astype(int)
    c = np.asarray(clean_band.convert("RGB")).astype(int)
    if a.shape != c.shape:
        return None
    diff = np.abs(a - c).max(2) > 40
    out = np.full_like(a, 255)
    out[diff] = a[diff]
    return Image.fromarray(out.astype("uint8"))


def stroke_overlap(img, clean, rects, H, sy):
    """朱書きが本文の字にどれだけ重なっているかを、筆跡ごとに測って最大値を返す。

    帯全体で測ると、5行の中で3文字に線を引いただけでは比率が小さくなり見逃す。
    筆跡の矩形の中だけで測ることで、局所的な重なりを拾える。
    """
    if np is None:
        return 0.0
    best = 0.0
    for x0, y0, x1, y1 in rects:
        top = max(0, int((H - y1) * sy)); bot = min(img.height, int((H - y0) * sy))
        left = max(0, int(x0 * sy)); right = min(img.width, int(x1 * sy))
        if bot - top < 4 or right - left < 4:
            continue
        a = np.asarray(img.crop((left, top, right, bot)).convert("RGB")).astype(int)
        c = np.asarray(clean.crop((left, top, right, bot)).convert("RGB")).astype(int)
        text = c.max(2) < 128
        if text.sum() < 50:            # 下に字がほとんど無い(余白への書き込み)
            continue
        changed = np.abs(a - c).max(2) > 40
        best = max(best, float((text & changed).sum()) / float(text.sum()))
    return best


# ---------------------------------------------------------------- 画像からの取り出し
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
COLOR_HUE = {"red": 0.0, "orange": 25.0, "green": 135.0, "blue": 220.0}


def parse_hue(spec):
    """`red` などの名前か `#rrggbb` から色相(度)を返す。"""
    spec = spec.strip().lower()
    if spec in COLOR_HUE:
        return COLOR_HUE[spec]
    s = spec.lstrip("#")
    if len(s) != 6:
        sys.exit("--color は %s か #rrggbb で指定する" % "/".join(COLOR_HUE))
    import colorsys
    r, g, b = (int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hsv(r, g, b)[0] * 360


def color_mask(img, hue, hue_tol=25.0, min_sat=0.40, min_val=0.30):
    """指定の色相に近く、彩度と明度が一定以上の画素を True にする。

    黒い本文・灰色の網掛け・白地は彩度が低いので外れる。図の同じ色は外れない。
    """
    hsv = np.asarray(img.convert("HSV")).astype(float)
    h = hsv[..., 0] * 360 / 255
    d = np.abs(h - hue)
    d = np.minimum(d, 360 - d)
    return (d <= hue_tol) & (hsv[..., 1] >= min_sat * 255) & (hsv[..., 2] >= min_val * 255)


def mask_bands(mask, pad, gap, min_pixels):
    """色の画素のある行を縦にまとめて帯(top, bot, 画素数)にする(画像の座標)。"""
    counts = mask.sum(axis=1)
    rows = np.where(counts >= 2)[0]
    if len(rows) == 0:
        return []
    spans, s, p = [], rows[0], rows[0]
    for y in rows[1:]:
        if y - p > gap:
            spans.append((s, p))
            s = y
        p = y
    spans.append((s, p))
    h = mask.shape[0]
    out = []
    for s, e in spans:
        n = int(counts[s:e + 1].sum())
        if n < min_pixels:             # JPEG のにじみ・ごみ
            continue
        top, bot = max(0, s - pad), min(h, e + 1 + pad)
        if out and top <= out[-1][1]:
            out[-1][1] = bot
            out[-1][2] += n
        else:
            out.append([top, bot, n])
    return out


def mask_clusters(mask, cell, gap):
    """色の画素をセル単位でまとめ、近いものどうしを書き込み1つぶんの矩形にする。"""
    h, w = mask.shape
    gh, gw = (h + cell - 1) // cell, (w + cell - 1) // cell
    pad = np.zeros((gh * cell, gw * cell), bool)
    pad[:h, :w] = mask
    occ = pad.reshape(gh, cell, gw, cell).sum(axis=(1, 3)) >= 2
    rects = [[x * cell, y * cell, (x + 1) * cell, (y + 1) * cell]
             for y, x in zip(*np.nonzero(occ))]
    # 縦の向きは問わないので to_clusters を流用し、重なりが無くなるまで繰り返す
    while True:
        merged = to_clusters(rects, gap_x=gap, gap_y=gap)
        if len(merged) == len(rects):
            return sorted(merged, key=lambda c: (c[1], c[0]))
        rects = merged


def image_dpi(img, fallback):
    d = img.info.get("dpi")
    try:
        v = float(d[0]) if d else 0
    except (TypeError, ValueError):
        v = 0
    return v if v >= 50 else fallback


def run_images(files, args):
    if np is None:
        sys.exit("画像から探すには numpy が要ります: pip install numpy")
    hue = parse_hue(args.color)
    outdir = Path(files[0]).resolve().parent / "marks"
    outdir.mkdir(exist_ok=True)
    if args.clean == "always":
        print("注意: 画像では朱書きの下の字を戻せないので、_clean は作らない")
    rows = []
    for f in files:
        img = Image.open(f).convert("RGB")
        dpi = image_dpi(img, args.dpi)
        px = dpi / 72                                   # 1pt あたりの画素
        mask = color_mask(img, hue, args.hue_tol, args.min_sat)
        bands = mask_bands(mask, pad=int(args.pad * px), gap=int(args.pad * px),
                           min_pixels=args.min_pixels)
        stem = Path(f).stem
        for k, (top, bot, n) in enumerate(bands, start=1):
            name = "%s_b%d" % (stem, k)
            rows.append((stem, k, top, bot, n, name, ""))
            if args.list:
                continue
            band = img.crop((0, top, img.width, bot))
            band.save(outdir / (name + ".png"))
            if args.ink == "always":
                m = mask[top:bot]
                a = np.asarray(band)
                only = np.full_like(a, 255)
                only[m] = a[m]
                Image.fromarray(only).save(outdir / (name + "_ink.png"))
        if args.zoom and not args.list and bands:
            sub = np.zeros_like(mask)
            for top, bot, _ in bands:
                sub[top:bot] = mask[top:bot]
            for j, c in enumerate(mask_clusters(sub, cell=max(4, int(4 * px)),
                                                gap=25 * px), start=1):
                l = max(0, int(c[0] - 90 * px)); t = max(0, int(c[1] - 16 * px))
                r = min(img.width, int(c[2] + 90 * px)); b = min(img.height, int(c[3] + 16 * px))
                img.crop((l, t, r, b)).save(outdir / ("%s_z%d.png" % (stem, j)))

    man = outdir / "manifest.tsv"
    with open(man, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("image\tband\ttop\tbot\tpixels\tname\toverlap\n")
        for r in rows:
            fh.write("\t".join(str(x) for x in r) + "\n")

    hit = [Path(f).stem for f in files if any(r[0] == Path(f).stem for r in rows)]
    print("朱書きのある画像: %d / %d" % (len(hit), len(files)))
    print("帯: %d 本" % len(rows))
    blank = [Path(f).stem for f in files if Path(f).stem not in hit]
    print("朱書き無し: %s" % (",".join(blank) if blank else "なし"))
    print("注意: 色で探したので、図の中の同じ色も帯になる。帯を見て外す")
    print("manifest: %s" % man)


# ---------------------------------------------------------------- 本体
def parse_pages(spec):
    if not spec:
        return None
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="+", help="校正 PDF (1つ) か、画像 (jpg/png/tif。複数可)")
    ap.add_argument("--pages", help="56-71 や 88,90 の形で指定 (PDF のみ)")
    ap.add_argument("--dpi", type=int, default=170)
    ap.add_argument("--pad", type=float, default=18.0,
                    help="帯の上下に足す文脈(pt)。本文1行 ≒ 14pt")
    ap.add_argument("--list", action="store_true", help="画像は作らず一覧だけ出す")
    ap.add_argument("--clean", choices=["auto", "always", "never"], default="auto",
                    help="朱書きを消した版。auto は字に重なった帯だけ")
    ap.add_argument("--ink", choices=["auto", "always", "never"], default="auto",
                    help="朱書きだけの版。auto は字に重なった帯だけ")
    ap.add_argument("--overlap", type=float, default=0.10,
                    help="auto の閾値。筆跡の下の字がどれだけ覆われたか(筆跡ごとの最大)")
    ap.add_argument("--zoom", action="store_true",
                    help="筆跡のかたまりごとに拡大画像も出す(手書きが読めないとき)")
    ap.add_argument("--zoom-dpi", type=int, default=300)
    ap.add_argument("--color", default="red",
                    help="画像のみ: 朱書きの色。red/orange/green/blue か #rrggbb")
    ap.add_argument("--hue-tol", type=float, default=25.0,
                    help="画像のみ: 色相の許容幅(度)")
    ap.add_argument("--min-sat", type=float, default=0.40,
                    help="画像のみ: 彩度の下限(0-1)。薄い色の図を外したいときは上げる")
    ap.add_argument("--min-pixels", type=int, default=30,
                    help="画像のみ: これより画素の少ない帯は捨てる(にじみ・ごみ)")
    args = ap.parse_args()

    images = [s for s in args.src if Path(s).suffix.lower() in IMAGE_EXT]
    if images:
        if len(images) != len(args.src):
            sys.exit("PDF と画像を混ぜて渡さない")
        if args.pages:
            print("注意: --pages は PDF のときだけ効く (画像は渡したものをすべて見る)")
        return run_images(images, args)
    if len(args.src) != 1:
        sys.exit("PDF は1つだけ渡す")

    pdf = Path(args.src[0]).resolve()
    outdir = pdf.parent / "marks"
    outdir.mkdir(exist_ok=True)
    want = parse_pages(args.pages)
    need_clean = args.clean != "never" or args.ink != "never"

    reader = pypdf.PdfReader(str(pdf))
    rows = []
    for i, page in enumerate(reader.pages, start=1):
        if want and i not in want:
            continue
        rects = ink_rects(page)
        if not rects:
            continue
        bands = to_bands(rects, args.pad)
        H = float(page.mediabox[3])
        if args.list:
            for k, (y0, y1, n) in enumerate(bands, start=1):
                rows.append((i, k, round(y0, 1), round(y1, 1), n, "p%03d_b%d" % (i, k), ""))
            continue

        img = render(pdf, i, args.dpi)
        clean = render(pdf, i, args.dpi, True) if need_clean else None
        sy = img.height / H
        for k, (y0, y1, n) in enumerate(bands, start=1):
            name = "p%03d_b%d" % (i, k)
            top = max(0, int((H - y1) * sy))
            bot = min(img.height, int((H - y0) * sy))
            band = img.crop((0, top, img.width, bot))
            band.save(outdir / (name + ".png"))
            ratio = ""
            if clean is not None:
                cband = clean.crop((0, top, clean.width, bot))
                inb = [r for r in rects if r[1] >= y0 - args.pad and r[3] <= y1 + args.pad]
                r = stroke_overlap(img, clean, inb, H, sy)
                ratio = "%.2f" % r
                hit = r >= args.overlap
                if args.clean == "always" or (args.clean == "auto" and hit):
                    cband.save(outdir / (name + "_clean.png"))
                if args.ink == "always" or (args.ink == "auto" and hit):
                    only = ink_only(band, cband)
                    if only is not None:
                        only.save(outdir / (name + "_ink.png"))
            rows.append((i, k, round(y0, 1), round(y1, 1), n, name, ratio))

        if args.zoom:
            big = render(pdf, i, args.zoom_dpi)
            zy = big.height / H
            for j, c in enumerate(to_clusters(rects), start=1):
                t = max(0, int((H - c[3] - 16) * zy)); b = min(big.height, int((H - c[1] + 16) * zy))
                l = max(0, int((c[0] - 90) * zy)); rr = min(big.width, int((c[2] + 90) * zy))
                big.crop((l, t, rr, b)).save(outdir / ("p%03d_z%d.png" % (i, j)))

    man = outdir / "manifest.tsv"
    with open(man, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("page\tband\ty0\ty1\tstrokes\tname\toverlap\n")
        for r in rows:
            fh.write("\t".join(str(x) for x in r) + "\n")

    pages = sorted({r[0] for r in rows})
    print("朱書きのあるページ: %d" % len(pages))
    print(pages)
    print("帯: %d 本 (1ページあたり %.1f)" % (len(rows), len(rows) / max(1, len(pages))))

    # 範囲を指定したときは、朱書きの無いページを明示する。
    # そうしないと呼び出し側が「見落としたのか、元から無いのか」を区別できない。
    if want:
        last = len(reader.pages)
        asked = sorted(p for p in want if p <= last)
        blank = [p for p in asked if p not in set(pages)]
        if blank:
            print("朱書き無し: %s (指定 %d ページ中 %d)"
                  % (",".join(str(p) for p in blank), len(asked), len(blank)))
        else:
            print("朱書き無し: なし (指定 %d ページすべてに朱書きがある)" % len(asked))
        if len(asked) < len(want):
            print("範囲外(全 %d ページ): %s"
                  % (last, ",".join(str(p) for p in sorted(want) if p > last)))

    print("manifest: %s" % man)


if __name__ == "__main__":
    main()
