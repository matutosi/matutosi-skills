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

紙をスキャンした PDF (注釈が無く、ページが画像だけ) を渡したときも、
各ページを元の解像度で描画して、画像と同じく色で探す (自動で切り替わる)。

スマホの写真は、横倒しなら本文の行の向きを見て縦に直し (上下は見分けられないので、
逆さなら --rotate 270)、EXIF の 72dpi は用紙 (A4) の
長辺から見積もり直し、彩度の下限の既定を 0.30 に下げる (写真の赤ペンはスキャンより薄い)。

`--ref もとの原稿.pdf` を付けると、色ではなく**もとの原稿との差**で探す (OpenCV が要る)。
    python extract_marks.py scan.pdf --ref manuscript.pdf
    python extract_marks.py p07.jpg p29.jpg --ref manuscript.pdf --ref-pages 7,29
図の同じ色を拾わず、赤以外のペンも拾い、参照の画像が `_clean` になる。
印刷したときと同じ版の PDF が要る。位置が合わないページは色の方法に戻る。
写真は台形にゆがむので合わないことが多い (スキャン向け)。
"""
import argparse
import os
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

# パスワード付き PDF 用．main() が --password か環境変数 PDF_PASSWORD から決める
PASSWORD = None


def _need_password(wrong):
    sys.exit("PDF のパスワードが違います: --password か環境変数 PDF_PASSWORD を確かめる" if wrong else
             "パスワード付きの PDF です: --password か環境変数 PDF_PASSWORD で渡す "
             "(履歴に残したくなければ環境変数のほうがよい)")


def open_reader(pdf):
    """pypdf で開く。パスワード付きなら復号する (無い・違うときは分かるメッセージで止める)。"""
    r = pypdf.PdfReader(str(pdf))
    if r.is_encrypted and not r.decrypt(PASSWORD or ""):
        _need_password(bool(PASSWORD))
    return r


def open_pdfium(path):
    """pypdfium2 で開く。パスワード付きなら PASSWORD で復号する。"""
    try:
        return pdfium.PdfDocument(str(path), password=PASSWORD)
    except pdfium.PdfiumError as e:
        if "assword" in str(e):
            _need_password(bool(PASSWORD))
        raise


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
    out = [list(r) for r in sorted(rects, key=lambda r: (-r[3], r[0]))]

    def near(a, b):
        return not (a[2] < b[0] - gap_x or a[0] > b[2] + gap_x
                    or a[3] < b[1] - gap_y or a[1] > b[3] + gap_y)

    # 3つ目が離れた2つをつなぐことがあるので，これ以上まとまらなくなるまで繰り返す
    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                if near(out[i], out[j]):
                    a, b = out[i], out[j]
                    out[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    del out[j]
                    merged = True
                    break
            if merged:
                break
    return sorted(out, key=lambda c: -c[3])


# ---------------------------------------------------------------- 描画
def render(pdf, page_no, dpi, strip_annots=False):
    """1ページを描画して Image を返す。

    strip_annots=True で注釈を描かない(朱書きを消した版)。PDF は書き換えない。
    """
    doc = open_pdfium(pdf)
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


def tight(img, margin=12):
    """白地の画像から，筆跡のある範囲だけを残して切り詰める (余白は margin 画素)．"""
    a = np.asarray(img.convert("L"))
    ys, xs = np.where(a < 250)
    if not len(xs):
        return img
    return img.crop((max(0, int(xs.min()) - margin), max(0, int(ys.min()) - margin),
                     min(img.width, int(xs.max()) + 1 + margin), min(img.height, int(ys.max()) + 1 + margin)))


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
    """画像の解像度 (dpi)。72dpi 以下 (写真の既定値) は用紙 (A4) の長辺から見積もる。"""
    d = img.info.get("dpi")
    try:
        v = float(d[0]) if d else 0
    except (TypeError, ValueError):
        v = 0
    if v > 72:
        return v
    if max(img.size) >= 1500:                       # A4 の長辺 (11.69in) に写っているとみなす
        return max(img.size) / 11.69
    return v if v >= 50 else fallback


def is_photo(img):
    """カメラで撮った画像か (EXIF に機種名がある)。"""
    try:
        ex = img.getexif()
    except Exception:
        return False
    return bool(ex.get(271) or ex.get(272))         # Make / Model


def stripe(profile, k=15):
    """濃さのプロファイルの細かい揺れ (行の縞) だけを測る。照明のむらのような緩い変化は除く。"""
    smooth = np.convolve(profile, np.ones(k) / k, mode="same")
    return float(np.std(profile - smooth))


def lines_are_vertical(img):
    """本文の行が縦に走っているか (横倒しの写真)。

    局所の背景より暗い画素を字とみなし (机の影・照明のむらに強い)、中央だけで
    行方向と列方向の縞の強さを比べる。横書きの行は横縞を作る。
    """
    from PIL import ImageFilter
    small = img.convert("L")
    small.thumbnail((1000, 1000))
    g = np.asarray(small).astype(float)
    bg = np.asarray(small.filter(ImageFilter.BoxBlur(15))).astype(float)
    h, w = g.shape
    m = (g < bg - 25)[int(h * .15):int(h * .85), int(w * .15):int(w * .85)]
    return stripe(m.mean(axis=0)) > stripe(m.mean(axis=1)) * 1.2


def upright(img, rotate="auto"):
    """横倒しの画像を、本文の行が横になる向きに直す。(画像, 回した角度) を返す。

    auto は行が縦に走っていれば反時計回りに 90° 回す。上下 (90° か 270° か) は
    見分けられないので、逆さになったら --rotate 270 のように角度を指定する。
    """
    from PIL import ImageOps
    img = ImageOps.exif_transpose(img).convert("RGB")
    if rotate == "auto":
        angle = 90 if lines_are_vertical(img) else 0
    else:
        angle = int(rotate)
    if angle:
        img = img.rotate(angle, expand=True)
    return img, angle


# ---------------------------------------------------------------- 参照 PDF との差
def load_cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        sys.exit("--ref には OpenCV が要ります: pip install opencv-python")


def text_mask(img):
    """彩度の低い濃い画素 (本文の黒) だけ。色の朱書きは入らない。"""
    hsv = np.asarray(img.convert("HSV")).astype(int)
    return (hsv[..., 2] < 110) & (hsv[..., 1] < 90)


def align_ref(img, ref_pdf, ref_no):
    """参照 PDF のページを、スキャンに重なるように描画する。(画像, 本文の重なり) を返す。

    ORB の特徴点 + RANSAC で相似変換を求め、ECC (アフィン) で詰める。
    """
    cv2 = load_cv2()
    doc = open_pdfium(ref_pdf)
    try:
        if not 1 <= ref_no <= len(doc):
            return None, 0.0
        page = doc[ref_no - 1]
        scale = img.width / page.get_width()          # 用紙の幅に合わせて刷ったとみなす
        ref = page.render(scale=scale).to_pil().convert("RGB")
    finally:
        doc.close()
    g1 = np.where(text_mask(img), 0, 255).astype(np.uint8)
    g2 = np.where(text_mask(ref), 0, 255).astype(np.uint8)
    orb = cv2.ORB_create(8000)
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, None)
    if d1 is None or d2 is None:
        return None, 0.0
    mt = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d2, d1)
    if len(mt) < 10:
        return None, 0.0
    src = np.float32([k2[m.queryIdx].pt for m in mt])
    dst = np.float32([k1[m.trainIdx].pt for m in mt])
    M, _ = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3)
    if M is None:
        return None, 0.0
    # ECC の行列は スキャン(template) 座標 → 参照(input) 座標 の向き
    W = cv2.invertAffineTransform(M).astype(np.float32)
    b1 = cv2.GaussianBlur(255 - g1, (0, 0), 2).astype(np.float32)
    b2 = cv2.GaussianBlur(255 - g2, (0, 0), 2).astype(np.float32)
    try:
        _, W = cv2.findTransformECC(b1, b2, W, cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6),
                                    None, 5)
    except cv2.error:
        pass
    warped = cv2.warpAffine(np.asarray(ref), W, img.size,
                            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                            borderValue=(255, 255, 255))
    warped = Image.fromarray(warped)
    rm = cv2.dilate(text_mask(warped).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    sm = text_mask(img)
    return warped, float((sm & rm).sum()) / max(1, int(sm.sum()))


def diff_mask(img, refimg, px):
    """スキャンにあって参照に無いもの。参照の何かがある所 (1pt 膨らませる) と紙の端は外す。"""
    cv2 = load_cv2()
    a = np.asarray(img).astype(int)
    hsv = np.asarray(img.convert("HSV")).astype(int)
    ink = (a.min(2) < 170) | ((hsv[..., 1] > 70) & (hsv[..., 2] > 60))
    r = max(1, int(round(px)))
    refm = (np.asarray(refimg).min(2) < 235).astype(np.uint8)
    refm = cv2.dilate(refm, np.ones((2 * r + 1, 2 * r + 1), np.uint8)) > 0
    m = ink & ~refm
    e = int(12 * px)                                    # 紙の端 12pt (スキャナの影)
    m[:e] = False; m[-e:] = False; m[:, :e] = False; m[:, -e:] = False
    return m


def run_images(files, args):
    """画像ファイルから探す。"""
    pages = []
    from PIL import ImageSequence
    for f in files:
        raw = Image.open(f)
        photo = is_photo(raw)
        dpi = image_dpi(raw, args.dpi)
        # 複数ページの TIFF は，全ページを <名前>_p1, _p2 … として読む
        frames = [fr.copy() for fr in ImageSequence.Iterator(raw)]
        for n, fr in enumerate(frames, start=1):
            stem = Path(f).stem if len(frames) == 1 else "%s_p%d" % (Path(f).stem, n)
            img, angle = upright(fr, args.rotate)
            if angle and args.rotate == "auto":
                print("%s: 横倒しなので反時計回りに 90° 回して読む (逆さなら --rotate 270)" % stem)
            pages.append((stem, img, dpi, photo))
    src = ",".join(Path(f).name for f in files)
    outdir = prepare_outdir(Path(files[0]).resolve().parent / "marks", src, args)
    run_pages(pages, outdir, args, "画像")


def ref_page_numbers(args, n, default):
    """画像・ページの順に対応する参照 PDF のページ番号。"""
    if not args.ref_pages:
        return default
    nums = parse_page_list(args.ref_pages)   # 画像・ページの順に対応させるので，書いた順を保つ
    if len(nums) != n:
        sys.exit("--ref-pages の数 (%d) が画像・ページの数 (%d) と合わない" % (len(nums), n))
    return nums


def write_manifest(path, header, rows):
    """帯の一覧 (manifest.tsv) を書く．header はタブ区切りの見出しの 1 行 (改行なし)．"""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(header + "\n")
        for r in rows:
            fh.write("\t".join(str(x) for x in r) + "\n")


def prepare_outdir(default, source, args):
    """出力先 (--out か，ソースのあるフォルダの marks/) を作って返す．

    marks/ が別の PDF・画像の出力のときは，上書きすると知らせる (--out で分けられる)．
    ソースの名前は出力先の .source に控える．
    """
    outdir = Path(args.out).resolve() if getattr(args, "out", None) else default
    outdir.mkdir(parents=True, exist_ok=True)
    tag = outdir / ".source"
    if tag.exists():
        before = tag.read_text(encoding="utf-8").strip()
        if before and before != source:
            print("注意: %s は別のソース (%s) の出力です．%s の分で上書きします (--out で別の場所に出せます)"
                  % (outdir, before, source))
    tag.write_text(source + "\n", encoding="utf-8")
    return outdir


def run_pages(pages, outdir, args, unit, ref_nums=None):
    """(名前, 画像, dpi, 写真か) の並びから朱書きを探して帯を切り出す。

    既定は色で探す。--ref があれば参照 PDF との差で探す。
    """
    if np is None:
        sys.exit("画像から探すには numpy が要ります: pip install numpy")
    hue = parse_hue(args.color)
    outdir.mkdir(parents=True, exist_ok=True)
    if args.ref:
        load_cv2()
        ref_nums = ref_page_numbers(args, len(pages),
                                    ref_nums or list(range(1, len(pages) + 1)))
    elif args.clean == "always":
        print("注意: 画像では朱書きの下の字を戻せないので、_clean は作らない (--ref なら作れる)")
    rows = []
    by_color = by_ref = 0
    for idx, (stem, img, dpi, photo) in enumerate(pages):
        px = dpi / 72                                   # 1pt あたりの画素
        refimg = None
        if args.ref:
            refimg, ov = align_ref(img, args.ref, ref_nums[idx])
            if refimg is None or ov < 0.8:
                print("注意: %s は参照 PDF の p.%d と位置が合わない (本文の重なり %.0f%%)。色で探す"
                      % (stem, ref_nums[idx], 100 * ov))
                refimg = None
        if refimg is not None:
            mask = diff_mask(img, refimg, px)
            by_ref += 1
        else:
            min_sat = args.min_sat if args.min_sat is not None else (0.30 if photo else 0.40)
            mask = color_mask(img, hue, args.hue_tol, min_sat)
            by_color += 1
        bands = mask_bands(mask, pad=int(args.pad * px), gap=int(args.pad * px),
                           min_pixels=args.min_pixels)
        for k, (top, bot, n) in enumerate(bands, start=1):
            name = "%s_b%d" % (stem, k)
            rows.append((stem, k, top, bot, n, name, ""))
            if args.list:
                continue
            band = img.crop((0, top, img.width, bot))
            if args.ink_only:   # 画像・スキャン: 本文を除き，色 (または参照との差) の画素だけを白地に置く
                m = mask[top:bot]
                a = np.asarray(band)
                only = np.full_like(a, 255)
                only[m] = a[m]
                tight(Image.fromarray(only)).save(outdir / (name + "_ink.png"))
                continue
            band.save(outdir / (name + ".png"))
            if refimg is not None and args.clean != "never":
                refimg.crop((0, top, img.width, bot)).save(outdir / (name + "_clean.png"))
            if args.ink == "always" or (refimg is not None and args.ink == "auto"):
                m = mask[top:bot]
                a = np.asarray(band)
                only = np.full_like(a, 255)
                only[m] = a[m]
                Image.fromarray(only).save(outdir / (name + "_ink.png"))
        if args.zoom and not args.list and bands and not args.ink_only:   # 画像の拡大は本文も写るので，--ink-only では出さない
            sub = np.zeros_like(mask)
            for top, bot, _ in bands:
                sub[top:bot] = mask[top:bot]
            for j, c in enumerate(mask_clusters(sub, cell=max(4, int(4 * px)),
                                                gap=25 * px), start=1):
                l = max(0, int(c[0] - 90 * px)); t = max(0, int(c[1] - 16 * px))
                r = min(img.width, int(c[2] + 90 * px)); b = min(img.height, int(c[3] + 16 * px))
                img.crop((l, t, r, b)).save(outdir / ("%s_z%d.png" % (stem, j)))

    man = outdir / "manifest.tsv"
    write_manifest(man, "image\tband\ttop\tbot\tpixels\tname\toverlap", rows)

    names = [p[0] for p in pages]
    hit = [n for n in names if any(r[0] == n for r in rows)]
    print("朱書きのある%s: %d / %d" % (unit, len(hit), len(names)))
    print("帯: %d 本" % len(rows))
    blank = [n for n in names if n not in hit]
    print("朱書き無し: %s" % (",".join(blank) if blank else "なし"))
    if by_ref:
        print("参照 PDF との差で探した: %d / %d" % (by_ref, len(names)))
    if by_color:
        print("注意: 色で探したので、図の中の同じ色も帯になる。帯を見て外す")
    print("manifest: %s" % man)


# ---------------------------------------------------------------- スキャンした PDF
def is_scanned(page):
    """注釈が無く、文字も無く、画像があるページ (紙をスキャンしたもの) か。"""
    if ink_rects(page):
        return False
    try:
        if (page.extract_text() or "").strip():
            return False
    except Exception:
        return False
    try:
        return len(page.images) > 0
    except Exception:
        return False


def scan_dpi(page, fallback):
    """ページに貼られた一番大きな画像の解像度 (dpi)。取れなければ fallback。"""
    try:
        w = max(im.image.width for im in page.images)
    except Exception:
        return fallback
    pw = float(page.mediabox.width)
    return w / pw * 72 if pw > 0 and w > 0 else fallback


def run_scanned_pdf(pdf, reader, want, args):
    """スキャンした PDF の各ページを元の解像度で描画し、画像と同じく色で探す。"""
    pages, nums = [], []
    for i, page in enumerate(reader.pages, start=1):
        if want and i not in want:
            continue
        dpi = scan_dpi(page, args.dpi)
        pages.append(("p%03d" % i, render(pdf, i, dpi), dpi, False))
        nums.append(i)
    outdir = prepare_outdir(pdf.parent / "marks", pdf.name, args)
    run_pages(pages, outdir, args, "ページ", nums)


# ---------------------------------------------------------------- 本体
def parse_page_list(spec):
    """`12,11` や `3-5,1` を，書いた順のページ番号の並びにする (範囲は昇順に展開)．"""
    if not spec:
        return None
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = (int(x) for x in part.split("-"))
            if b < a:
                sys.exit("ページの範囲 %s が逆です (小さい方から書く)" % part)
            out.extend(range(a, b + 1))
        else:
            out.append(int(part))
    return out


def parse_pages(spec):
    pages = parse_page_list(spec)
    return set(pages) if pages is not None else None


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
    ap.add_argument("--password", help="パスワード付き PDF のパスワード (参照 PDF にも使う)。"
                    "履歴に残したくなければ環境変数 PDF_PASSWORD にする")
    ap.add_argument("--ink-only", action="store_true",
                    help="朱書きだけを白地に置いた画像 (pNNN_bK_ink.png) だけを出す．本文の写った画像は作らない．"
                         "文字起こしや，本文を見せたくないとき用")
    ap.add_argument("--zoom", action="store_true",
                    help="筆跡のかたまりごとに拡大画像も出す(手書きが読めないとき)")
    ap.add_argument("--zoom-dpi", type=int, default=300)
    ap.add_argument("--out", help="出力先のフォルダ (既定: 入力のあるフォルダの marks/)．"
                    "別の PDF の出力を上書きしたくないときに分ける")
    ap.add_argument("--color", default="red",
                    help="画像のみ: 朱書きの色。red/orange/green/blue か #rrggbb")
    ap.add_argument("--hue-tol", type=float, default=25.0,
                    help="画像のみ: 色相の許容幅(度)")
    ap.add_argument("--min-sat", type=float, default=None,
                    help="画像のみ: 彩度の下限(0-1)。既定はスキャン 0.40・写真 0.30。"
                         "薄い色の図を外したいときは上げる")
    ap.add_argument("--min-pixels", type=int, default=30,
                    help="画像のみ: これより画素の少ない帯は捨てる(にじみ・ごみ)")
    ap.add_argument("--rotate", choices=["auto", "0", "90", "180", "270"], default="auto",
                    help="画像のみ: 反時計回りに回す角度。auto は横倒しなら 90")
    ap.add_argument("--ref", type=Path,
                    help="画像・スキャンのみ: もとの原稿の PDF。色ではなく差で探す (OpenCV が要る)")
    ap.add_argument("--ref-pages",
                    help="--ref の対応ページ (画像・ページの順)。既定はスキャンと同じ番号、画像は 1 から")
    args = ap.parse_args()
    global PASSWORD
    PASSWORD = args.password if args.password is not None else os.environ.get("PDF_PASSWORD")

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
    want = parse_pages(args.pages)
    need_clean = args.clean != "never" or args.ink != "never" or args.ink_only

    reader = open_reader(pdf)
    targets = [p for i, p in enumerate(reader.pages, start=1) if not want or i in want]
    if targets and not any(ink_rects(p) for p in targets):
        if all(is_scanned(p) for p in targets):
            how = ("参照 PDF との差で探す" if args.ref
                   else "色で探す (--color %s)" % args.color)
            print("注釈が無く、ページが画像だけなので、スキャンとみなして%s" % how)
            return run_scanned_pdf(pdf, reader, want, args)
        print("注意: Ink 注釈がありません。紙のスキャンなら、ページを画像にして渡す")
    outdir = prepare_outdir(pdf.parent / "marks", pdf.name, args)
    rows = []
    for i, page in enumerate(reader.pages, start=1):
        if want and i not in want:
            continue
        rects = ink_rects(page)
        if not rects:
            continue
        # 描画されるのは CropBox (無ければ MediaBox)．注釈の座標はその左下が原点とは限らない
        box = page.cropbox
        left, bottom = float(box.left), float(box.bottom)
        H = float(box.top) - bottom
        if left or bottom:
            rects = [(r[0] - left, r[1] - bottom, r[2] - left, r[3] - bottom) for r in rects]
        bands = to_bands(rects, args.pad)
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
            if args.ink_only:   # 本文は出さない．朱書きだけを白地に置いた画像を，筆跡の範囲に切り詰めて保存する
                only = ink_only(band, clean.crop((0, top, clean.width, bot)))
                if only is not None:
                    tight(only).save(outdir / (name + "_ink.png"))
                rows.append((i, k, round(y0, 1), round(y1, 1), n, name, ""))
                continue
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
            if args.ink_only:   # 拡大も，本文を除いた朱書きだけの版にする
                big = ink_only(big, render(pdf, i, args.zoom_dpi, True)) or big
            zy = big.height / H
            for j, c in enumerate(to_clusters(rects), start=1):
                t = max(0, int((H - c[3] - 16) * zy)); b = min(big.height, int((H - c[1] + 16) * zy))
                l = max(0, int((c[0] - 90) * zy)); rr = min(big.width, int((c[2] + 90) * zy))
                big.crop((l, t, rr, b)).save(outdir / ("p%03d_z%d%s.png" % (i, j, "_ink" if args.ink_only else "")))

    man = outdir / "manifest.tsv"
    write_manifest(man, "page\tband\ty0\ty1\tstrokes\tname\toverlap", rows)

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
