"""転記の値の有無を画像のセルと突き合わせ，隣の地点へ取り違えた値の候補を出す．報告だけで，転記は書き換えない．

    python scripts/check_cells.py <画像> <出力> <表> --box X0 Y0 X1 Y1 --layer X0 X1

- `--box` は値の列を囲む範囲，`--layer` は階層の列の範囲 (x だけ)．`crop.py --dense` と同じ画像の座標を使う．
- 行は階層の字の並び，列は `・` の並び (`crop.measure_columns`) から測る．列を測れなければ `--box` を等分する．
  階層の字で行を測れなければ，値の列の字の並びで測る．
- **地点の間に常在度の列が混ざる表は，列が等間隔でないので使えない**．
- セルの字の幅が `・` より広ければ「値あり」とする．**`+` と `1` の読み違いは見つけられない**．
- 候補は画像に戻って確かめる．下線・点線の枠・ごみを値と見ることがある．
- 境の幅は既定で，字のあるセルの幅の中央値の 1.5 倍．`・` と値の幅が近い表は `--wmin` で変えて，結果が動くかを見る．
"""
import argparse
import csv
import os
import re
import sys

from PIL import Image, ImageDraw

import crop

Image.MAX_IMAGE_PIXELS = None


def table_dir(table):
    return re.sub(r'\d+', lambda m: '%03d' % int(m.group()), table)


def read_body(path):
    with open(path, encoding='utf-8', newline='') as f:
        rows = list(csv.reader(f, delimiter='\t'))
    head = rows[0]
    first = head.index('1')
    n = sum(1 for c in head if c.isdigit())
    return [(r[4], r[5], [v != '・' for v in r[first:first + n]])
            for r in rows[1:] if r and r[0] == 'sp'], n


def runs(flags):
    """真が続く範囲 (始まり, 終わり) の並び"""
    out, start = [], None
    for i, v in enumerate(list(flags) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i))
            start = None
    return out


def find_rows(im):
    """階層の字の並びから行を拾う．縦の罫線は除く．(行の上下の並び, 行の間隔) を返す"""
    w, h = im.size
    bw = im.convert('L').point(lambda v: 255 if v < 128 else 0)
    draw = ImageDraw.Draw(bw)
    for x, v in enumerate(bw.resize((w, 1), Image.BOX).tobytes()):
        if v > 127:                                   # 高さの半分以上が黒い列は罫線
            draw.line([(x, 0), (x, h)], fill=0)
    return pick_rows(v > 0 for v in bw.resize((1, h), Image.BOX).tobytes())


def find_rows_by_values(bw, centers, half):
    """値の列の字の並びから行を拾う．傾いた罫線があっても，列の中心の近くだけを見るので掛からない"""
    h = bw.height
    count = [0] * h
    for cx in centers:
        strip = bw.crop((int(cx - half), 0, int(cx + half), h)).resize((1, h), Image.BOX).tobytes()
        for y, v in enumerate(strip):
            count[y] += v > 0
    return pick_rows(c >= len(centers) / 3 for c in count)


def pick_rows(flags):
    """字のある高さの並びから行の上下を決める．(行の上下の並び, 行の間隔) を返す"""
    rows = runs(flags)
    if len(rows) < 2:
        return [], 0
    height = sorted(b - t for t, b in rows)[len(rows) // 2]
    tops = [t for t, _ in rows]
    pitch = sorted(b - a for a, b in zip(tops, tops[1:]))[(len(tops) - 1) // 2]
    out = []
    for t, b in rows:
        if b - t < height * .6:                       # ごみ
            continue
        k = max(1, round((b - t) / pitch))            # 行がつながった塊は等分する
        out += [(t + (b - t) * i // k, t + (b - t) * (i + 1) // k) for i in range(k)]
    return out, pitch


def cell_widths(bw, rows, pitch, centers, half):
    """行 x 地点ごとの，字の左右の幅"""
    w = bw.width
    data = bw.tobytes()
    out = []
    for t, b in rows:
        c = (t + b) // 2
        top, bottom = max(0, c - pitch // 2 + 2), min(bw.height, c + pitch // 2 - 2)
        cols = [any(data[y * w + x] for y in range(top, bottom)) for x in range(w)]
        row = []
        for cx in centers:
            xs = [x for x in range(max(0, int(cx - half)), min(w, int(cx + half))) if cols[x]]
            row.append(xs[-1] - xs[0] + 1 if xs else 0)
        out.append(row)
    return out


def align(typed, seen):
    """転記の行を測った行へ順に対応させる．全部 `・` の行は転記に無いことがあるので，測った側だけ飛ばせる"""
    ni, nj = len(typed), len(seen)
    if nj < ni:
        return None
    n = len(typed[0]) if typed else 0
    gap = [sum(row) for row in seen]
    score = [[0.0] * (nj + 1)] + [[-1e9] * (nj + 1) for _ in range(ni)]
    take = [[False] * (nj + 1) for _ in range(ni + 1)]
    for i in range(1, ni + 1):
        for j in range(1, nj + 1):
            same = sum(a == b for a, b in zip(typed[i - 1], seen[j - 1])) / n
            a, b = score[i - 1][j - 1] + same - .9, score[i][j - 1] - .02 * gap[j - 1]
            score[i][j], take[i][j] = (a, True) if a >= b else (b, False)
    i, j = ni, max(range(nj + 1), key=lambda k: score[ni][k])
    match = [0] * ni
    while i:
        if take[i][j]:
            match[i - 1] = j - 1
            i -= 1
        j -= 1
    return match


def candidates(typed, seen):
    """転記に値があって画像に無いセルと，隣の画像にだけ値があるセルの組"""
    out = []
    for r, (t, m) in enumerate(zip(typed, seen)):
        used = set()
        for p, v in enumerate(t):
            if v and not m[p]:
                for q in (p - 1, p + 1):
                    if 0 <= q < len(t) and m[q] and not t[q] and q not in used:
                        used.add(q)
                        out.append((r, p, q))
                        break
    return out


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('image')
    ap.add_argument('out')
    ap.add_argument('table', help='表の名前 (Tab.9 など)')
    ap.add_argument('--box', type=int, nargs=4, required=True, metavar=('X0', 'Y0', 'X1', 'Y1'))
    ap.add_argument('--layer', type=int, nargs=2, required=True, metavar=('X0', 'X1'), help='階層の列の範囲')
    ap.add_argument('--wmin', type=int, help='これ以上の幅を「値あり」とする (既定は自動)')
    ap.add_argument('--shear', type=int, help='行の傾き (省くと自動で測る)')
    a = ap.parse_args(argv)

    body, plots = read_body(os.path.join(a.out, 'transcripts', table_dir(a.table), 'body.tsv'))
    im = Image.open(a.image).convert('L')
    x0, y0, x1, y1 = a.box
    part = im.crop(tuple(a.box))
    dy = a.shear if a.shear is not None else crop.estimate_shear(part)
    part = crop.shear(part, dy)
    centers, why = crop.measure_columns(part, plots)
    if centers:
        pitch_x = (centers[-1] - centers[0]) / (plots - 1)
        print(f'列を測った: 第 1 列の中心 x={round(x0 + centers[0])}，間隔 {pitch_x:.1f} px')
    else:
        pitch_x = (x1 - x0) / plots
        centers = [(i + .5) * pitch_x for i in range(plots)]
        print(f'警告: 列を測れなかった ({why})．--box を {plots} 等分した')
    bw = part.point(lambda v: 255 if v < 128 else 0)
    rows, pitch = find_rows(im.crop((a.layer[0], y0, a.layer[1], y1)))
    if len(rows) < len(body):                         # 傾いた罫線が階層の範囲に掛かると，行がつながる
        rows, pitch = find_rows_by_values(bw, centers, pitch_x * .3)
        print('階層の字では行を測れないので，値の列の字の並びで測った')
    print(f'行: 測った {len(rows)}・転記 {len(body)}．地点 {plots}')
    if len(rows) < len(body):
        sys.exit('測った行が転記より少ない．--box を値の列だけに合わせる')
    width = cell_widths(bw, rows, pitch, centers, pitch_x * .3)
    filled = sorted(v for row in width for v in row if v)
    wmin = a.wmin or round(filled[len(filled) // 2] * 1.5)
    seen = [[v >= wmin for v in row] for row in width]
    typed = [t for _, _, t in body]
    match = align(typed, seen)
    seen = [seen[j] for j in match]
    only_t = sum(t and not m for r, s in zip(typed, seen) for t, m in zip(r, s))
    only_m = sum(m and not t for r, s in zip(typed, seen) for t, m in zip(r, s))
    print(f'境の幅 {wmin} px．転記だけの値 {only_t}・画像だけの値 {only_m}')
    found = candidates(typed, seen)
    name = ''
    names = []
    for j_name, _, _ in body:
        name = j_name or name
        names.append(name)
    for r, p, q in found:
        print(f'[候補] {names[r]} {body[r][1]}: 地点 {p + 1} の値は地点 {q + 1} かもしれない')
    print(f'候補 {len(found)} 件 (画像で確かめる．転記は書き換えていない)')


if __name__ == '__main__':
    main()
