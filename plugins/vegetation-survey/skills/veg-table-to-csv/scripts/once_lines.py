"""1 回出現の段落 (幅の広い・傾いた複数行の段落) を 1 行ずつ切り出し，傾きを直して縦に貼る．
行をまたぐ語 (行末の「コ」と次の行頭の「ベニバナボロギク」) を 1 枚の上で続けて読めるようにする．

    python scripts/once_lines.py <画像> <出力の置き場> --box X0 Y0 X1 Y1 [--width 2400] [--overlap 200]

- 行は字の横の投影で測る．左の 1/4 と右の 1/4 で別々に測り，数が合えば行ごとに左右の y を直線でつなぐ
  (右ほど下がる段落)．合わなければ左だけで測り，傾きは `--shear` (右端で下がる px) で渡す．
- 各行を `--width` px ごとに切り (隣と `--overlap` px 重ねる)，左上に `L<行>-<切れ>` と原寸の x を書いて縦に貼る．
  1 枚の高さが `--max-height` を超えたら次の画像に分ける．出力は <置き場>/once_lines_01.png …
- 切り出しの位置 (行の y) は once_lines.tsv に書く．読み終えたら，続きの語は 1 つの種として once.tsv に書く．
"""
import argparse
import os
import sys

try:
    import numpy as np
    from scipy import ndimage as ndi
except ImportError:                                     # pragma: no cover
    sys.exit('numpy と scipy が要る (pip install numpy scipy)')
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None


def font(size=22):
    for name in ('arial.ttf', 'DejaVuSans.ttf', 'msgothic.ttc', 'meiryo.ttc'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def line_centers(bw, min_gap=None):
    """2 値画像の行 (字のある y の帯) の中心と高さ．戻り: [(中心, 高さ)]"""
    prof = bw.sum(axis=1).astype(float)
    if not prof.any():
        return []
    on = prof > max(1.0, .03 * prof.max())
    on = ndi.binary_closing(on, structure=np.ones(5, bool))
    lab, n = ndi.label(on)
    out = []
    for sl in ndi.find_objects(lab):
        a, b = sl[0].start, sl[0].stop
        if b - a >= 5:
            out.append(((a + b) / 2, b - a))
    if not out:
        return []
    med = float(np.median([h for _, h in out]))
    return [(c, h) for c, h in out if h >= .4 * med]     # 下線・点の切れ端の帯は行とみない


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('image')
    ap.add_argument('out')
    ap.add_argument('--box', type=int, nargs=4, required=True, metavar=('X0', 'Y0', 'X1', 'Y1'),
                    help='段落の範囲 (原寸)')
    ap.add_argument('--width', type=int, default=2400, help='1 切れの幅 (px)')
    ap.add_argument('--overlap', type=int, default=200, help='隣の切れと重ねる幅 (px)')
    ap.add_argument('--shear', type=float, help='右端で行が下がる px (左右で行の数が合わないとき)')
    ap.add_argument('--pad', type=float, default=.35, help='行の上下に足す幅 (行の間隔に対する割合)')
    ap.add_argument('--scale', type=float, default=1.0, help='貼る画像の縮小率')
    ap.add_argument('--max-height', type=int, default=3200, help='1 枚の高さの上限 (px．縮小後)')
    ap.add_argument('--threshold', type=int, default=128)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)

    im = Image.open(a.image).convert('L')
    X0, Y0, X1, Y1 = a.box
    W = X1 - X0
    bw = np.asarray(im.crop((X0, Y0, X1, Y1))) < a.threshold
    q = max(50, W // 4)
    left = line_centers(bw[:, :q])
    right = line_centers(bw[:, W - q:])
    if not left:
        sys.exit('--box の中に字の行が無い')
    if a.shear is not None:
        lines = [(c, c + a.shear, h) for c, h in left]
        how = f'左で測り，--shear {a.shear:+.0f}'
    elif len(right) == len(left):
        lines = [(cl, cr, max(hl, hr)) for (cl, hl), (cr, hr) in zip(left, right)]
        how = '左右で測った'
    else:
        lines = [(c, c, h) for c, h in left]
        how = f'左だけで測った (右は {len(right)} 行で数が合わない．傾くなら --shear)'
    pitch = float(np.median(np.diff([c for c, _, _ in lines]))) if len(lines) > 1 else 2.0 * lines[0][2]
    half = .5 * pitch + a.pad * pitch
    xl, xr = q / 2, W - q / 2
    print(f'行: {len(lines)} 行 ({how})．行の間隔 {pitch:.0f} px')

    def y_at(line, x):
        cl, cr, _ = line
        return cl + (cr - cl) * (x - xl) / (xr - xl)

    # 行ごとに，x を 100 px ずつ切って行の y に合わせて貼り，まっすぐな行の画像にする
    straight = []
    hh = int(round(2 * half))
    for ln in lines:
        row = Image.new('L', (W, hh), 255)
        for x in range(0, W, 100):
            w = min(100, W - x)
            yc = Y0 + y_at(ln, x + w / 2)
            row.paste(im.crop((X0 + x, int(round(yc - half)), X0 + x + w, int(round(yc - half)) + hh)), (x, 0))
        straight.append(row)

    # 行を --width ごとに切って縦に貼る
    pieces = []
    step = max(1, a.width - a.overlap)
    for i, row in enumerate(straight, 1):
        for k, x in enumerate(range(0, W, step), 1):
            pieces.append((f'L{i}-{k} x={X0 + x}', row.crop((x, 0, min(W, x + a.width), hh))))
            if x + a.width >= W:
                break
    f = font(max(14, int(22 * a.scale)))
    label_h = int(30 * a.scale) + 4
    pages, cur, used = [], [], 0
    for name, p in pieces:
        if a.scale != 1.0:
            p = p.resize((max(1, int(p.width * a.scale)), max(1, int(p.height * a.scale))))
        need = p.height + label_h
        if cur and used + need > a.max_height:
            pages.append(cur)
            cur, used = [], 0
        cur.append((name, p))
        used += need
    if cur:
        pages.append(cur)
    width = max(p.width for _, p in pieces) if a.scale == 1.0 else int(a.width * a.scale)
    for n, page in enumerate(pages, 1):
        H = sum(p.height + label_h for _, p in page)
        out = Image.new('RGB', (width, H), 'white')
        d = ImageDraw.Draw(out)
        y = 0
        for name, p in page:
            d.text((4, y + 2), name, fill=(200, 0, 0), font=f)
            out.paste(p.convert('RGB'), (0, y + label_h))
            y += p.height + label_h
            d.line((0, y - 1, width, y - 1), fill=(160, 160, 255))
        path = os.path.join(a.out, f'once_lines_{n:02d}.png')
        out.save(path)
        print(f'画像: {path} ({len(page)} 切れ)')
    with open(os.path.join(a.out, 'once_lines.tsv'), 'w', encoding='utf-8') as fo:
        fo.write('line\ty_left\ty_right\n')
        for i, (cl, cr, _) in enumerate(lines, 1):
            fo.write(f'{i}\t{Y0 + cl:.0f}\t{Y0 + cr:.0f}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
