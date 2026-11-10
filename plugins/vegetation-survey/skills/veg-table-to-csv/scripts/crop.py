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
  列の位置は `・` の並びから測る．測れないときは警告を出し，`--box` を地点の数で等分する (左右には `--pad` を足さない)．
  群の境で間隔が広がる表など，測れない・等分では合わない表は，`--centers` で全列の中心の x を，
  等間隔なら `--first-x` と `--pitch` を渡す．最後の列が切り出しの右端からはみ出せば警告する．
  列の位置をどう決めたか (`列の位置: 測った`・`等分`・`引数`) を必ず表示する．
  `--label` の左端が字に掛かる (名前の頭がはみ出す) ときは警告し，広げる先の x を出す．
- `--tiles` は「行数x列数」(`3x2` は縦 3 枚・横 2 枚)．`--raw` は `--tiles` を使わず 1 枚で切る．

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


def estimate_shear(im, limit=80, step=4, center=0):
    """行の濃淡がいちばん鋭くなる傾き (dy) を探す．値の列だけの画像を渡す

    1 行分ずれた傾きでも行がそろって見えるので，帯ごとに測るときは center の近くだけを探す"""
    g = im.convert('L')
    best, best_var = center, -1.0
    for dy in range(center - limit, center + limit + 1, step):
        var = ImageStat.Stat(shear(g, dy).resize((1, g.height), Image.BOX)).var[0]
        if var > best_var:
            best, best_var = dy, var
    return best


def shear_bands(im, dy, bands=8, near=16):
    """傾きを帯ごとに dy の近くで測って直した画像を返す．傾きは表の中で一様でない"""
    out = Image.new(im.mode, im.size, 'white')
    h = im.height / bands
    for i in range(bands):
        top, bottom = int(i * h), int((i + 1) * h)
        band = im.crop((0, top, im.width, bottom))
        out.paste(shear(band, estimate_shear(band, near, 4, dy)), (0, top))
    return out


def _profile(im):
    """列ごとの字の量 (0〜1)"""
    bw = im.convert('L').point(lambda v: 255 if v < 128 else 0)
    return [v / 255 for v in bw.resize((bw.width, 1), Image.BOX).tobytes()]


def _comb(prof, plots, pitch, start):
    return sum(prof[min(len(prof) - 1, round(start + i * pitch))] for i in range(plots))


def measure_columns(im, plots, rough=None):
    """値の列の中心の x を，`・` の縦の並びから測る．(中心の列, 理由) を返す．測れなければ (None, 理由)

    罫線を除き，等間隔の櫛がいちばん多く字に当たる位置を探す．
    列の数が合わない・峰がはっきりしないときは測れないことにする．"""
    raw = _profile(im)
    n = len(raw)
    left, right = 0, n
    for x, v in enumerate(raw):                       # 値の両側の縦の罫線の内側だけを見る
        if v > .5 and x < n / 3:
            left = x + 1
        if v > .5 and x > n * 2 / 3:
            right = min(right, x)
    if rough:
        left, right = max(left, rough[0]), min(right, rough[1])
    width = right - left
    if plots < 2 or width < plots * 4:
        return None, '範囲が狭い'
    cap = sorted(raw[left:right])[int(width * .9)]
    capped = [min(v, cap) for v in raw[left:right]]
    prof = [sum(capped[max(0, x - 2):x + 3]) / 5 for x in range(width)]
    pmax = width / (plots - 1)
    best = (-1.0, 0.0, 0)

    def search(pitches, starts_of):
        nonlocal best
        for pitch in pitches:
            for start in starts_of(pitch):
                s = _comb(prof, plots, pitch, start)
                if s > best[0]:
                    best = (s, pitch, start)

    search([pmax * (.5 + .5 * i / 100) for i in range(101)],
           lambda p: range(0, max(1, int(width - p * (plots - 1))), 2))
    _, pitch0, start0 = best
    search([pitch0 + .02 * i for i in range(-25, 26)],
           lambda p: [s for s in range(max(0, start0 - 3), start0 + 4) if s + p * (plots - 1) < width])
    _, pitch, start = best

    def runs(x):                                      # 縦に並ぶ字の数．値の列は行の数だけあり，罫線は少ない
        if not 0 <= x < width:
            return 0
        x = round(left + x)
        strip = gray.crop((max(0, x - 4), 0, x + 5, gray.height)).resize((1, gray.height), Image.BOX).tobytes()
        return sum(1 for u, v in zip(strip, strip[1:]) if u >= 225 > v)

    gray = im.convert('L')
    count = [runs(start + i * pitch) for i in range(plots)]
    typical = sorted(count)[plots // 2]
    if count[-1] < typical / 2 and runs(start - pitch) >= typical / 2:     # 櫛の端が罫線に乗った
        start -= pitch
    elif count[0] < typical / 2 and runs(start + plots * pitch) >= typical / 2:
        start += pitch
    count = [runs(start + i * pitch) for i in range(plots)]
    typical = sorted(count)[plots // 2]
    if not typical or min(count) < typical / 2:
        return None, '字の無い列がある'
    if max(runs(start - pitch), runs(start + plots * pitch)) >= typical / 2:
        return None, '範囲の外にも列がある'
    return [left + start + i * pitch for i in range(plots)], ''


def label_cut(im, x, y0, y1, look=300, near=12):
    """--label の左端 x に字が掛かる (左の字から続いている) 所を探す．(掛かる所の y の並び, 左へ広げる先の x か None)

    左端の 3 px と，そのすぐ左 near px の両方に字のある行が続く所を数える．
    左端に沿って長く続く縦の線 (罫線) は字ではないので数えない"""
    x0 = max(0, x - look)
    if x - x0 < near + 2 or y1 <= y0:
        return [], None
    g = im.crop((x0, y0, x + 2, y1)).convert('L')
    w, h = g.size
    px = g.tobytes()
    dark = [[px[y * w + i] < 128 for i in range(w)] for y in range(h)]
    edge = x - x0                                     # 左端の列の添字
    on = [any(r[edge - 1:edge + 2]) for r in dark]
    left = [any(r[edge - 1 - near:edge - 1]) for r in dark]
    hits, y = [], 0
    while y < h:
        if on[y]:
            z = y
            while z < h and on[z]:
                z += 1
            if z - y <= 80 and sum(left[y:z]) >= 3:     # 80 px を超えて続くのは縦の罫線
                hits.append((y, z))
            y = z
        else:
            y += 1
    if not hits:
        return [], None
    merged = [list(hits[0])]                          # 1 字の画の切れ目で分かれた所を 1 か所にまとめる
    for a, b in hits[1:]:
        if a - merged[-1][1] <= 10:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    hits = merged
    to = None
    run = 0
    for i in range(edge - 1, -1, -1):                 # 掛かる所の 9 割以上で字の無い縦の隙間 (12 px．字の間より広い) を左へ探す
        busy = sum(any(dark[yy][i] for yy in range(max(0, a - 4), min(h, b + 4))) for a, b in hits)
        clear = busy <= .1 * len(hits)
        run = run + 1 if clear else 0
        if run >= 12:
            to = x0 + i + 6                           # 字の頭から 6 px 左
            break
    return [y0 + (a + b) // 2 for a, b in hits], to


def dense_tile(im, edges, label, first, last, y_range, grid_top=26, lines=False):
    """1 枚分: 左に種名・階層，右に first〜last 地点の値．edges は地点の境 (地点の数 + 1 個) の x

    境に掛かる値が欠けないよう，隣の組と接する側は列の幅の 2 割だけ広く切る．
    列の線は `+` を隠したり偽の `+` を作ったりするので，札の高さだけに引く (lines で全体に引く)"""
    top, bottom = y_range
    margin = round((edges[1] - edges[0]) * .2)
    left = int(edges[first - 1]) - (margin if first > 1 else 0)
    right = int(edges[last]) + 1 + (margin if last < len(edges) - 1 else 0)
    names = im.crop((label[0], top, label[1], bottom))
    vals = im.crop((left, top, right, bottom))
    out = Image.new('RGB', (names.width + 12 + vals.width, vals.height + grid_top), 'white')
    out.paste(names, (0, grid_top))
    out.paste(vals, (names.width + 12, grid_top))
    d = ImageDraw.Draw(out)
    f = _font(20)
    for i in range(first, last + 1):
        cx = names.width + 12 + round(edges[i - 1] - left)
        d.line([(cx, 0), (cx, out.height if lines else grid_top)], fill=(170, 210, 255))
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
    ap.add_argument('--centers', type=float, nargs='+',
                    help='密な表: 全列の中心の x (原寸．群の境で間隔が広がる表など，列を測れない・等分では合わない表)')
    ap.add_argument('--first-x', type=float, help='密な表: 第 1 列の中心の x (原寸．--pitch と組で等間隔の列を渡す)')
    ap.add_argument('--pitch', type=float, help='密な表: 列の間隔 (px．--first-x と組で)')
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
        origin = a.label[1]                           # 値の側の探す範囲の左端 (--pad で広げた範囲より左へは行かない)
        given = None
        if a.centers:
            if len(a.centers) != a.plots:
                sys.exit(f'--centers は {len(a.centers)} 個．--plots は {a.plots}')
            given = sorted(a.centers)
        elif a.first_x is not None or a.pitch is not None:
            if a.first_x is None or a.pitch is None:
                sys.exit('--first-x と --pitch は組で渡す')
            given = [a.first_x + a.pitch * k for k in range(a.plots)]
        if given:                                     # 渡された列の中心から境を作る (間隔の不ぞろいな表にも合う)
            g = [x - a.label[0] for x in given]
            gaps = [b - c for c, b in zip(g, g[1:])] or [50.0]
            edges = ([g[0] - gaps[0] / 2] + [(c + b) / 2 for c, b in zip(g, g[1:])] + [g[-1] + gaps[-1] / 2])
            centers, why = None, ''
            print(f'列は引数のとおり: 第 1 列の中心 x={given[0]:.0f}・最後 x={given[-1]:.0f}・間隔 {min(gaps):.0f}-{max(gaps):.0f} px')
            print('列の位置: 引数 (' + ('--centers' if a.centers else '--first-x・--pitch') + ')')
            search = None
        else:
            search = whole.crop((max(x0, origin) - a.label[0], 0, x1 - a.label[0], y1 - y0))
            centers, why = measure_columns(search, a.plots)
        if given:
            pass
        elif centers:
            w = (centers[-1] - centers[0]) / (a.plots - 1)
            base = max(x0, origin) - a.label[0]
            edges = [base + c - w / 2 for c in centers] + [base + centers[-1] + w / 2]
            print(f'列を測った: 第 1 列の中心 x={round(base + centers[0] + a.label[0])}，間隔 {w:.1f} px')
            weq = (a.box[2] - a.box[0]) / a.plots
            print(f'列の位置: 測った (点の並びから)．--box を等分した場合の第 1 列の中心は x={a.box[0] + weq / 2:.0f}・'
                  f'間隔 {weq:.1f} px')
        else:
            w = (a.box[2] - a.box[0]) / a.plots       # 等分は --pad を足す前の --box で行う
            edges = [a.box[0] - a.label[0] + i * w for i in range(a.plots + 1)]
            print(f'列の位置: 等分 (測れなかった)．第 1 列の中心 x={a.box[0] + w / 2:.0f}・間隔 {w:.1f} px')
            print(f'警告: 列を測れなかった ({why})．--box を {a.plots} 等分した．--box の左右を第 1 列と最後の列の外側に'
                  '合わせ，1 枚目で札と値の列が合っているかを確かめる．間隔が不ぞろいなら --centers か --first-x・--pitch で渡す')
        if edges[-1] > whole.width - 2:               # 最後の列が切り出しの右端からはみ出す (右端の列の値が切れる)
            print(f'警告: 最後の列の右の境 x={edges[-1] + a.label[0]:.0f} が切り出しの右端 x={x1} を越える．'
                  '右端の列の値が切れるので，--box の右端を広げる')
        label_w = min(a.label[1] - a.label[0], int(edges[0]))   # 第 1 列を種名の側に写さない
        if label_w < a.label[1] - a.label[0]:
            print(f'--label の右端が第 1 列に掛かるので，x={a.label[0] + label_w} で止めた')
        cut, to = label_cut(im, a.label[0], y0, y1)
        if cut:                                       # 名前の頭がはみ出す (左端が字のかたまりに掛かる)
            ys = ' '.join(str(v) for v in cut[:8]) + (' …' if len(cut) > 8 else '')
            more = f'左端を x={to} まで広げる' if to is not None else '左端を字の無い所まで広げる'
            if len(cut) >= 5:
                print(f'警告: --label の左端 x={a.label[0]} が字に掛かる ({len(cut)} 行．y={ys})．名前の頭が切れる．{more}')
            else:
                print(f'注意: --label の左端 x={a.label[0]} に字が掛かる ({len(cut)} 行．y={ys})．'
                      f'長い学名の末尾なら問題ない．名前の頭なら{more}')
        rows = int(a.tiles.lower().split('x')[0])
        h = (y1 - y0) / rows
        print(f'行の傾き {dy} px を直した')
        for r in range(rows):
            top, bottom = max(0, int(r * h - a.overlap)), min(y1 - y0, int((r + 1) * h + a.overlap))
            band = im.crop((a.label[0], y0 + top, x1, y0 + bottom))   # 傾きは表の中で一様でないので，帯ごとに測る
            dy_r = dy if a.shear is not None or rows == 1 else estimate_shear(
                band.crop((x0 - a.label[0], 0, band.width, band.height)), 16, 4, dy)
            band = shear(band, dy_r * (x1 - a.label[0]) / (x1 - x0))
            if rows > 1:
                print(f'帯 {r + 1}: 行の傾き {dy_r} px')
            for first in range(1, a.plots + 1, a.dense):
                last = min(a.plots, first + a.dense - 1)
                tile = dense_tile(band, edges, (0, label_w), first, last, (0, bottom - top), lines=a.grid)
                out, scale = ruled(tile, (0, 0, tile.width, tile.height), a.max, a.grid, a.zoom, y0 + top - 26)
                path = os.path.join(a.out, f'{stem}_r{r + 1}_p{first:02d}-{last:02d}.png')
                out.save(path)
                warn = '  ← 0.6 未満．--dense を小さくする' if scale < 0.6 else ''
                print(f'{path}: 縮小率 {scale:.3f}{warn}')
        return

    if a.raw:
        if a.tiles.lower() not in ('1x1', '1'):
            print(f'警告: --raw は --tiles ({a.tiles}) を使わず 1 枚で切る．分けるなら --raw を外す')
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
