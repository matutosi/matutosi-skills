"""画像の値のセルと転記のセルを，行と列の格子で突き合わせる．報告だけで，転記は書き換えない．

    python scripts/check_grid.py <画像> <出力> <表> --box X0 Y0 X1 Y1
    python scripts/check_grid.py <画像> <出力> <表> --box X0 Y0 X1 Y1 --first 1433 --pitch 70.9

- `--box` は値の列だけを囲む (左の罫線・右の外を含めない)．check_cells.py が測れない表で使う．
- 字のかたまりを取り，`・` の位置から列の中心を y の 2 次式で追う (紙面の傾きと曲がりを吸収する)．
  全部の列の字の y から行の格子を作り，転記の行と全体が最も合うように対応づける．
- セルは `d` (点)・`v` (単独の値)・`c` (`1・2` のような値)・`x` (字が無い) に分ける．
  点と値が違うセルを `[違い]` に出す．枠の線・染み・小さい点の誤判定も混じるので，画像で確かめる．
- 列が見つからないときは `--first` (第 1 列の中心)・`--pitch` (間隔) を渡す．
  点が小さい表は `--dot-w`・`--dot-h` と `--min-area` を下げる．
- numpy と scipy が要る (この点検のときだけ)．
"""
import argparse
import collections
import csv
import os
import re
import sys

try:
    import numpy as np
    from scipy import ndimage as ndi
except ImportError:
    sys.exit('numpy と scipy が要る: pip install numpy scipy')
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def table_dir(table):
    return re.sub(r'\d+', lambda m: '%03d' % int(m.group()), table)


def blobs(path, box, min_area, threshold=128):
    """字のかたまりを (x, y, 幅, 高さ, 面積) の配列で返す．長い罫線と破線は除く"""
    x0, y0, x1, y1 = box
    im = np.array(Image.open(path).convert('L'))[y0:y1, x0:x1] < threshold
    rule = ndi.binary_dilation(ndi.binary_opening(im, structure=np.ones((70, 1))), structure=np.ones((1, 3)))
    im = im & ~rule
    rule = ndi.binary_dilation(ndi.binary_opening(im, structure=np.ones((1, 44))), structure=np.ones((3, 1)))
    im = im & ~rule
    lab, _ = ndi.label(im, structure=np.ones((3, 3)))
    out = []
    for i, sl in enumerate(ndi.find_objects(lab)):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        area = int((lab[sl] == i + 1).sum())
        if area < min_area or (h <= 5 and w >= 12) or (w <= 6 and h >= 8):      # 横・縦の破線
            continue
        out.append((x0 + (sl[1].start + sl[1].stop) / 2, y0 + (sl[0].start + sl[0].stop) / 2, w, h, area))
    return np.array(out)


def find_columns(dots, plots, box):
    """上の方の `・` の x の山から，列の中心の候補を返す"""
    x0, y0, x1, _ = box
    top = dots[dots[:, 1] < y0 + 1800]
    hist, edges = np.histogram(top[:, 0], bins=np.arange(x0, x1 + 1, 2))
    smooth = np.convolve(hist, np.ones(5), 'same')
    peaks = [i for i in range(2, len(smooth) - 2)
             if smooth[i] == smooth[i - 2:i + 3].max() and smooth[i] > smooth.max() * .25]
    kept = []
    for p in peaks:
        if not kept or p - kept[-1] >= 20:
            kept.append(p)
    return [float(edges[p] + 1) for p in kept]


def track(items, dots, cxs, y0, tol=.32):
    """各列の中心を y の 2 次式で追い，字を近い列へ割り当てる"""
    pitch = float(np.median(np.diff(cxs)))
    cols = []
    for cx in cxs:
        coef = np.array([0, 0, cx], float)
        yy = (dots[:, 1] - y0) / 1000
        for it in range(4):
            sel = np.abs(dots[:, 0] - np.polyval(coef, yy)) < pitch * (.30 if it else .35)
            if sel.sum() < 30:
                break
            coef = np.polyfit(yy[sel], dots[sel, 0], 2)
        cols.append(coef)
    yy = (items[:, 1] - y0) / 1000
    dist = np.abs(np.array([np.polyval(c, yy) for c in cols]) - items[:, 0][None, :])
    near = dist.argmin(axis=0)
    assign = np.where(dist[near, np.arange(len(items))] < pitch * tol, near, -1)
    return assign


def cell_type(group, is_dot, wide):
    if not group:
        return 'x'
    if len(group) == 1 and is_dot(group[0]):
        return 'd'
    left = min(q[0] - q[2] / 2 for q in group)
    right = max(q[0] + q[2] / 2 for q in group)
    return 'c' if right - left > wide else 'v'


def image_cells(items, assign, n, is_dot, wide, gap=6, min_share=.5):
    """行の格子の y と，[列][行] のセルの型を返す"""
    ys = np.sort(items[assign >= 0, 1])
    groups = [[ys[0]]]
    for y in ys[1:]:
        if y - groups[-1][-1] > gap:
            groups.append([y])
        else:
            groups[-1].append(y)
    grid = np.array([np.mean(g) for g in groups if len(g) >= min_share * n])
    offset = np.zeros(n)
    for c in range(n):
        col = items[assign == c, 1]
        if len(col):
            offset[c] = np.median([y - grid[np.argmin(np.abs(grid - y))] for y in col])
    tol = .42 * float(np.percentile(np.diff(grid), 10))
    cells = {}
    for c in range(n):
        for q in items[assign == c]:
            g = int(np.argmin(np.abs(grid + offset[c] - q[1])))
            if abs(grid[g] + offset[c] - q[1]) < tol:
                cells.setdefault((c, g), []).append(q)
    return grid, [[cell_type(cells.get((c, g), []), is_dot, wide) for g in range(len(grid))] for c in range(n)]


def typed_cells(path):
    """転記の行の名前と，[行][列] のセルの型を返す"""
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE))
    cols = [i for i, c in enumerate(rows[0]) if c.isdigit()]
    names, cells, last = [], [], ''
    for r in rows[1:]:
        if not r or r[0] != 'sp':
            continue
        last = r[4] or r[3] or last
        names.append(f'{last} {r[5]}')
        vals = [r[i].strip() if i < len(r) else '' for i in cols]
        cells.append(['d' if v in ('・', '') else 'c' if '・' in v or len(v) > 2 else 'v' for v in vals])
    return names, cells


def match_rows(typed, image, skip=4):
    """転記の行と画像の行を，全体で最も合うように対応づける．(行, 格子) の組の並びを返す"""
    r_n, g_n, n = len(typed), len(image[0]), len(image)

    def cost(r, g):
        k = 0.0
        for c in range(n):
            t, u = typed[r][c], image[c][g]
            if t != u:
                k += .2 if t == 'd' and u == 'x' else .5 if {t, u} <= {'v', 'c'} else 1
        return k

    costs = [[cost(r, g) for g in range(g_n)] for r in range(r_n)]
    best = np.zeros((r_n + 1, g_n + 1))
    best[:, 0] = np.arange(r_n + 1) * skip
    best[0, :] = np.arange(g_n + 1) * skip
    for r in range(1, r_n + 1):
        for g in range(1, g_n + 1):
            best[r, g] = min(best[r - 1, g - 1] + costs[r - 1][g - 1], best[r - 1, g] + skip, best[r, g - 1] + skip)
    r, g, pairs = r_n, g_n, []
    while r > 0 and g > 0:
        if abs(best[r, g] - best[r - 1, g - 1] - costs[r - 1][g - 1]) < 1e-9:
            pairs.append((r - 1, g - 1))
            r, g = r - 1, g - 1
        elif abs(best[r, g] - best[r - 1, g] - skip) < 1e-9:
            r -= 1
        else:
            g -= 1
    return pairs[::-1]


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('image')
    ap.add_argument('out')
    ap.add_argument('table', help='表の名前 (Tab.9 など)')
    ap.add_argument('--box', type=int, nargs=4, required=True, metavar=('X0', 'Y0', 'X1', 'Y1'))
    ap.add_argument('--first', type=float, help='第 1 列の中心の x (原寸)')
    ap.add_argument('--pitch', type=float, help='列の間隔 (px)')
    ap.add_argument('--dot-w', type=int, default=12, help='これ以下の幅を点とみなす')
    ap.add_argument('--dot-h', type=int, default=9, help='これ以下の高さを点とみなす')
    ap.add_argument('--min-area', type=int, default=18, help='これより小さい字を捨てる')
    ap.add_argument('--wide', type=int, default=26, help='これより広いセルを `1・2` の形とみなす')
    ap.add_argument('--limit', type=int, default=60, help='[違い] を出す上限')
    a = ap.parse_args(argv)

    names, typed = typed_cells(os.path.join(a.out, 'transcripts', table_dir(a.table), 'body.tsv'))
    n = len(typed[0])
    box = tuple(a.box)
    items = blobs(a.image, box, a.min_area)

    def is_dot(q):
        return q[2] <= a.dot_w and q[3] <= a.dot_h

    dots = items[[is_dot(q) for q in items]]
    if a.first is not None and a.pitch:
        cxs = [a.first + i * a.pitch for i in range(n)]
    else:
        cxs = find_columns(dots, n, box)
    print(f'列の候補 {len(cxs)}・地点 {n}')
    if len(cxs) < n:
        sys.exit('列が足りない．--first と --pitch を渡す')
    cxs = cxs[:n]
    assign = track(items, dots, cxs, box[1])
    grid, image = image_cells(items, assign, n, is_dot, a.wide)
    pairs = match_rows(typed, image)
    print(f'画像の行 {len(grid)}・転記の行 {len(typed)}・対応した行 {len(pairs)}')
    diff = [(r, c, g) for r, g in pairs for c in range(n)
            if typed[r][c] != image[c][g] and not (typed[r][c] == 'd' and image[c][g] == 'x')
            and {typed[r][c], image[c][g]} - {'v', 'c'}]
    done = {r for r, _ in pairs}
    print('対応しない転記の行:', [names[r] for r in range(len(typed)) if r not in done][:10])
    for r, c, g in diff[:a.limit]:
        print(f'[違い] {names[r]}: 地点 {c + 1} 転記 {typed[r][c]}・画像 {image[c][g]} (y={round(float(grid[g]))})')
    print(f'違い {len(diff)} セル / {len(pairs) * n} セル')
    rows = collections.Counter(r for r, _, _ in diff)
    print('違いの多い行:', [(names[r], k) for r, k in rows.most_common(5)])
    cols = collections.Counter(c + 1 for _, c, _ in diff)
    print('違いの多い列:', cols.most_common(5))


if __name__ == '__main__':
    main()
