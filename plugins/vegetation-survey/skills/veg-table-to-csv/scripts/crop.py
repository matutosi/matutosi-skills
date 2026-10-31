"""ページ画像の一部を切り出し，原寸の座標の目盛りを付けて保存する．

    # 読むための画像 (目盛り付き．縦 2 x 横 1 のタイルに分ける)
    python scripts/crop.py <ページ.png> --box X0 Y0 X1 Y1 --tiles 2x1 --out <置き場>

    # 表を 1 枚の画像として切り出す (折り込みの切り分け．目盛りなし・原寸)
    python scripts/crop.py <ページ.png> --box X0 Y0 X1 Y1 --raw --name tab12 --out <置き場>
    python scripts/crop.py <ページ.png> --raw --rotate 90 --name tab12 --out <置き場>   # 横倒しを起こす

- 座標はすべて**原寸の px** (見渡し画像や目盛りに書いてある数字)．`--box` を省くと全体．
  見渡しから目で読んだ座標はずれるので，`--box` は既定で上下左右に 80 px 広げて切る (`--pad`)．
- 目盛り付きの画像は，上下左右の余白に原寸の x・y を書く．**別のタイルの同じ行は，
  y の目盛りで対応を取る** (横に分けたタイルで，種名と値を結ぶのに使う)．
- `--max` は保存する画像の長辺 (既定 1800 px)．読み手はこれより大きい画像を縮めるので，
  大きくしても字は大きくならない．字を大きくしたいときは `--box` を小さくするか，タイルを増やす．
- 表示の縮小率 (保存した画像の px / 原寸の px) を必ず表示する．**0.6 を下回ったら，
  `・` と `+`，`1` と `I` の見分けが怪しくなる**ので，もっと細かく切る．
- `--zoom` は拡大の倍率 (既定 1．ページ内の小さい表を読むときに 2〜3)．`--max` を超えない範囲で拡大する．
- `--rotate` は反時計回りの角度 (90・180・270)．`--raw` と組み合わせて使う．
- **密な表** (地点が多く横に収まらない表) は `--dense N` を使う．`--box` は値の列だけを囲む．
  行の傾きを直し，`--label X0 X1` の範囲 (種名・階層) を各画像の左に貼り，地点を N 列ずつの画像に分ける．
  列の上に地点の番号を書くので，**種名と値が 1 枚に入り，番号で列を取り違えない**．縦の分割は `--tiles 6x1`．

    python scripts/crop.py <表.png> --box 5180 1730 7260 7200 --dense 10 --plots 20 --label 3950 5170 --tiles 6x1 --out <置き場>
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageStat

Image.MAX_IMAGE_PIXELS = None

MARGIN_X, MARGIN_Y = 64, 28


def _font(size):
    for name in ('arial.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                 # Pillow 10.1 より前
        return ImageFont.load_default()


def _step(scale):
    """表示で 40 px 以上あく，きりのよい原寸の刻み"""
    for s in (10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000):
        if s * scale >= 40:
            return s
    return 5000


def ruled(im, box, maxside=1800, grid=False, zoom=1.0, y_origin=0):
    """box を切り出して縮め (zoom > 1 なら拡大し)，余白に原寸の目盛りを書いた画像と縮小率を返す"""
    x0, y0, x1, y1 = box
    shift = y_origin - y0 if y_origin else 0          # 目盛りの y を元の画像の座標にする
    part = im.crop(box).convert('RGB')
    scale = min(zoom, (maxside - 2 * MARGIN_X) / max(part.width, part.height))
    w, h = max(1, round(part.width * scale)), max(1, round(part.height * scale))
    part = part.resize((w, h), Image.LANCZOS)
    out = Image.new('RGB', (w + 2 * MARGIN_X, h + 2 * MARGIN_Y), 'white')
    out.paste(part, (MARGIN_X, MARGIN_Y))
    d = ImageDraw.Draw(out)
    f = _font(15)
    step = _step(scale)
    col = (200, 0, 0)
    for y in range(((y0 + shift) // step + 1) * step, y1 + shift, step):
        yy = MARGIN_Y + round((y - y0 - shift) * scale)
        d.line([(MARGIN_X - 8, yy), (MARGIN_X - 1, yy)], fill=col)
        d.line([(MARGIN_X + w, yy), (MARGIN_X + w + 7, yy)], fill=col)
        d.text((2, yy - 8), str(y), fill=col, font=f)
        d.text((MARGIN_X + w + 9, yy - 8), str(y), fill=col, font=f)
        if grid:
            d.line([(MARGIN_X, yy), (MARGIN_X + w, yy)], fill=(170, 210, 255))
    for x in range((x0 // step + 1) * step, x1, step):
        xx = MARGIN_X + round((x - x0) * scale)
        d.line([(xx, MARGIN_Y - 8), (xx, MARGIN_Y - 1)], fill=col)
        d.line([(xx, MARGIN_Y + h), (xx, MARGIN_Y + h + 7)], fill=col)
        d.text((xx - 14, 2), str(x), fill=col, font=f)
        d.text((xx - 14, MARGIN_Y + h + 9), str(x), fill=col, font=f)
        if grid:
            d.line([(xx, MARGIN_Y), (xx, MARGIN_Y + h)], fill=(170, 210, 255))
    return out, scale


def shear(im, dy):
    """右端が左端より dy px 下がった行を水平にする"""
    return im.transform(im.size, Image.AFFINE, (1, 0, 0, dy / im.width, 1, 0), Image.BICUBIC,
                        fillcolor='white')


def estimate_shear(im, limit=60, step=4):
    """行の濃淡がいちばん鋭くなる傾き (dy) を探す．値の列だけの画像を渡す"""
    g = im.convert('L')
    best, best_var = 0, -1.0
    for dy in range(-limit, limit + 1, step):
        var = ImageStat.Stat(shear(g, dy).resize((1, g.height), Image.BOX)).var[0]
        if var > best_var:
            best, best_var = dy, var
    return best


def dense_tile(im, box, label, plots, first, last, y_range, grid_top=26):
    """1 枚分: 左に種名・階層，右に first〜last 地点の値．(画像, 値の左端からの幅) を返す"""
    x0, _, x1, _ = box
    w = (x1 - x0) / plots
    top, bottom = y_range
    left = int(x0 + (first - 1) * w)
    right = min(x1, int(x0 + last * w) + 1)
    names = im.crop((label[0], top, label[1], bottom))
    vals = im.crop((left, top, right, bottom))
    out = Image.new('RGB', (names.width + 12 + vals.width, vals.height + grid_top), 'white')
    out.paste(names, (0, grid_top))
    out.paste(vals, (names.width + 12, grid_top))
    d = ImageDraw.Draw(out)
    f = _font(20)
    for i in range(first, last + 1):
        cx = names.width + 12 + round((i - first) * w)
        d.line([(cx, 0), (cx, out.height)], fill=(170, 210, 255))
        d.text((cx + 6, 1), str(i), fill=(200, 0, 0), font=f)
    return out


def tiles(box, rows, cols, overlap):
    x0, y0, x1, y1 = box
    tw, th = (x1 - x0) / cols, (y1 - y0) / rows
    for r in range(rows):
        for c in range(cols):
            yield (r + 1, c + 1,
                   (max(x0, int(x0 + c * tw - overlap)), max(y0, int(y0 + r * th - overlap)),
                    min(x1, int(x0 + (c + 1) * tw + overlap)),
                    min(y1, int(y0 + (r + 1) * th + overlap))))


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('image')
    ap.add_argument('--box', type=int, nargs=4, metavar=('X0', 'Y0', 'X1', 'Y1'))
    ap.add_argument('--tiles', default='1x1', help='縦 x 横 の枚数 (例: 3x2)')
    ap.add_argument('--overlap', type=int, default=60,
                    help='タイルを上下左右に広げる幅 (原寸 px．隣のタイルとは 2 倍重なる)')
    ap.add_argument('--pad', type=int, default=80,
                    help='--box を上下左右に広げる幅 (原寸 px．見渡しから目で読んだ範囲の誤差を吸収する)')
    ap.add_argument('--max', type=int, default=1800, help='保存する画像の長辺 (px)')
    ap.add_argument('--zoom', type=float, default=1.0, help='拡大の倍率 (小さい表は 2〜3)')
    ap.add_argument('--grid', action='store_true', help='目盛りの線を画像の上にも薄く引く')
    ap.add_argument('--dense', type=int, help='密な表: 1 枚に入れる地点の数 (--box は値の列だけ)')
    ap.add_argument('--plots', type=int, help='密な表: 表の地点の数')
    ap.add_argument('--label', type=int, nargs=2, metavar=('X0', 'X1'), help='密な表: 種名と階層の列の範囲')
    ap.add_argument('--shear', type=int, help='密な表: 行の傾き (右端の下がり px．省くと自動で測る)')
    ap.add_argument('--raw', action='store_true', help='目盛りを付けず原寸で切り出す')
    ap.add_argument('--rotate', type=int, default=0, choices=(0, 90, 180, 270))
    ap.add_argument('--name', help='出力の名前 (既定: 入力名と座標)')
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)

    im = Image.open(a.image)
    if a.box:
        x0, y0, x1, y1 = a.box
        box = (max(0, x0 - a.pad), max(0, y0 - a.pad),
               min(im.width, x1 + a.pad), min(im.height, y1 + a.pad))
    else:
        box = (0, 0, im.width, im.height)
    os.makedirs(a.out, exist_ok=True)
    stem = a.name or '%s_%d_%d_%d_%d' % ((os.path.splitext(os.path.basename(a.image))[0],) + box)

    if a.dense:
        if not (a.plots and a.label and a.box):
            sys.exit('--dense には --box・--plots・--label が要る')
        x0, y0, x1, y1 = box
        dy = a.shear if a.shear is not None else estimate_shear(im.crop(box))
        whole = shear(im.crop((a.label[0], y0, x1, y1)), dy * (x1 - a.label[0]) / (x1 - x0))
        shifted = (x0 - a.label[0], 0, x1 - a.label[0], y1 - y0)
        rows = int(a.tiles.lower().split('x')[0])
        h = (y1 - y0) / rows
        print(f'行の傾き {dy} px を直した')
        for r in range(rows):
            top, bottom = max(0, int(r * h - a.overlap)), min(y1 - y0, int((r + 1) * h + a.overlap))
            for first in range(1, a.plots + 1, a.dense):
                last = min(a.plots, first + a.dense - 1)
                tile = dense_tile(whole, shifted, (0, a.label[1] - a.label[0]), a.plots, first, last, (top, bottom))
                out, scale = ruled(tile, (0, 0, tile.width, tile.height), a.max, True, a.zoom, y0 + top - 26)
                path = os.path.join(a.out, f'{stem}_r{r + 1}_p{first:02d}-{last:02d}.png')
                out.save(path)
                warn = '  ← 0.6 未満．--dense を小さくする' if scale < 0.6 else ''
                print(f'{path}: 縮小率 {scale:.3f}{warn}')
        return

    if a.raw:
        part = im.crop(box)
        if a.rotate:
            part = part.rotate(a.rotate, expand=True)
        path = os.path.join(a.out, stem + '.png')
        part.save(path)
        with open(os.path.join(a.out, stem + '.box.txt'), 'w', encoding='utf-8') as f:
            f.write(f'box={box} rotate={a.rotate} source={a.image}\n')
        print(f'{path}: {part.width} x {part.height} px (原寸)．元の画像の box={box} '
              f'(--pad {a.pad} を含む) rotate={a.rotate}')
        return

    rows, cols = (int(v) for v in a.tiles.lower().split('x'))
    for r, c, tb in tiles(box, rows, cols, a.overlap):
        out, scale = ruled(im, tb, a.max, a.grid, a.zoom)
        suffix = f'_r{r}c{c}' if rows * cols > 1 else ''
        path = os.path.join(a.out, stem + suffix + '.png')
        out.save(path)
        warn = '  ← 0.6 未満．もっと細かく切る' if scale < 0.6 else ''
        print(f'{path}: box={tb} 縮小率 {scale:.3f}{warn}')


if __name__ == '__main__':
    main()
