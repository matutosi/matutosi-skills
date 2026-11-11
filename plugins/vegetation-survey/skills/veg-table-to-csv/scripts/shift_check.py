"""列ごとの 1 行ずれを点検する．画像の印の y と転記 (body.tsv の種の行) を，帯を使わずに直接比べる．
報告だけで，転記は書き換えない．

    python scripts/shift_check.py <画像> <出力> <表> --box X0 Y0 X1 Y1 --ref X0 X1
    python scripts/shift_check.py <画像> <出力> <表> --box ... --ref ... --ref2 X0 X1     # 行が傾く表
    python scripts/shift_check.py <画像> <出力> <表> --box ... --ref ... --track up       # 折り目で右上ほど行が下がる表
    python scripts/shift_check.py <画像> <出力> <表> --box ... --ref ... --merge-rows 8-9 # 1 印字行を 2 行に分けた転記

なぜ要るか: 帯の画像 (marks_grid.py・crop.py) の `--box` の上端・下端が端の行の印に掛かると，その列だけ
1 行目 (最後の行) を落として，列の値がまるごと 1 行ずれる．帯の左の和名は第 1 列の高さなので画像を見ても気づけず，
同じ帯での照合でも，出現種数の照合でも見つからない (列の中で値が動くだけ)．

- `--box` は値の列の範囲．y は本体の最初の種の行から最後の種の行まで．印は上下に `--margin` (既定 120 px) 広げて拾うので，
  端の行に掛けて切っても落とさない．
- `--ref` は行の y を測る x の範囲．**種の行のどれにも字がある列** (階層の列，階層の列が無ければ和名の列)．
  ここで数えた行の数が転記の種の行の数と合わなければ止まる (群の見出しも数えた数と合えば，見出しを除いて続ける)．
  測れない表は `--rows-in` に行の y を 1 行ずつ書いて渡す．
- `--ref2` は右側でもう 1 か所行の y を測る範囲 (行が傾く表．2 か所の y を列の x で直線に補間する)．
- 列の中心は点 (`・`) の x の山で測り，列ごとに点の x を y の直線で当て直す (紙面が下ほど左へ寄る表)．
  測れない表は `--centers` (全列)・`--first-x` と `--pitch`・`--colx` (marks_grid.py が書く col_x.tsv) で渡す．
- 横に続くかたまり (`1・1`・`V(+-2)` の字と括弧) を 1 つの印 (語) にまとめ，列に当てる．常在度の列の値は
  点の位置から右へ印字されるので語の左端で，ほかの列は語の中央で列を決める (隣の列の値の食い込みを数えない)．
  印の種類は marks_grid.py と同じ決まり (点 1〜2 つ・点 + 線の切れ端・点 + すぐそばの小さなよごれは点．
  白抜きの点 (中の白い丸) も点．点の大きさは marks_grid.py と同じ決め方で自動で測る．`--dot-max` で指定)．
  印は最も近い行に当てる (行の間隔の 0.45 倍より離れた印は捨てる)．
- `--fold X …` は縦の折り目の線の x．その列は [ずれ]・[多い] の判定から外し，縦帯を書く．
- `--track chain` は列ごとに印の並びを隣の列の行の y に DP でつなぐ (傾きが直線でない・折り目で曲がる表)．
- 行の数が合わないときは，値の範囲に印の少ない行 (見出し・枠の破線の候補) を測った行の番号と y で出す．
  階層の印字が `-` だけの行も 1 行と数える．
- 行の y と列の印の差 (紙面の傾き) は列ごとに中央値で補正し，隣の列へ引き継ぐ．
  `--track up` は表の下から上へ，`--track down` は上から下へ，印ごとに差を追う (折り目で行の高さが y で変わる表)．
- 列ごとに，転記で値のある行の集合 T と画像で値のある行の集合 I を，ずらし d = -1・0・+1 で比べる (|T+d △ I|)．
  **d=+1 は「画像の値が転記の 1 行下にある」**．次の列を挙げる．
  - `[ずれ]` d=0 より d=±1 のほうが食い違いが少ない列．または列の一部 (行 a〜b) で d=±1 のほうが `--gain` (既定 2) 以上少ない区間．
  - `[多い]` d=0 でも食い違いが `--many` (既定 3) 以上の列 (折り目の線・枠の破線・よごれ・点の大きさの取り違えも混じる)．
- `--merge-rows 8-9` は 1 つの印字の行を 2 行に分けた転記 (括弧書きの種など．転記の種の行の番号) を 1 行にまとめて比べる．
  `--merge-split` は階層ごとに分けた行 (note に同じ「印字は B1,B2,S」) をまとめる (marks_grid.py と同じ)．
- `--strips <置き場>` は挙げた列の縦帯 (`--ref` の範囲と列を並べ，行番号と転記の値を添える) を書く．目で確かめる．
- numpy・scipy・Pillow が要る．
"""
import argparse
import csv
import os
import re
import sys

try:
    import numpy as np
    from scipy import ndimage as ndi
except ImportError:                                     # pragma: no cover
    sys.exit('numpy と scipy が要る (pip install numpy scipy)')
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
CONST_RE = re.compile(r'^(?:[IV]+|r|\+)\(|^[IV]+$')
PRINTED = re.compile(r'印字は\s*([A-Za-z]\d?(?:\s*[,，]\s*[A-Za-z]\d?)+)')


def table_dir(table):
    return re.sub(r'\d+', lambda m: '%03d' % int(m.group()), table)


def has_value(v):
    return v.strip() not in ('', '・', '.')


# ---- 転記 ----

def read_body(path):
    """種の行 (名前・[列の値]・階層・note) と，種の行と見出しの並び ('sp' / 'group')"""
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE))
    if not rows:
        sys.exit(f'{path} が空')
    cols = [i for i, c in enumerate(rows[0]) if c.strip().isdigit()]
    ni = rows[0].index('note') if 'note' in rows[0] else None
    sp, kinds, last = [], [], ''
    for r in rows[1:]:
        if not r or r[0] not in ('sp', 'group'):
            continue
        kinds.append(r[0])
        if r[0] != 'sp':
            continue
        named = bool((r[4] if len(r) > 4 else '') or (r[3] if len(r) > 3 else ''))
        last = (r[4] if len(r) > 4 else '') or (r[3] if len(r) > 3 else '') or last
        layer = r[5].strip() if len(r) > 5 else ''
        note = r[ni] if ni is not None and ni < len(r) else ''
        sp.append(dict(name=f'{last} {layer}'.strip(), vals=[r[i].strip() if i < len(r) else '' for i in cols],
                       layer=layer, note=note if named else '\x00' + note))
    return sp, kinds, len(cols)


def split_groups(sp, manual=()):
    """1 つの印字の行を階層ごとに分けて書いた行の組 (0 始まり)．marks_grid.py の split_groups と同じ決まり"""
    layers = [s['layer'] for s in sp]
    notes = [s['note'] for s in sp]
    groups, used = [], set()
    for g in manual:
        groups.append(list(g))
        used |= set(g)
    i = 0
    while i < len(layers):
        m = PRINTED.search(notes[i]) if i not in used and not notes[i].startswith('\x00') else None
        if m:
            printed = [x.strip() for x in re.split(r'[,，]', m.group(1))]
            g = [i]
            j = i + 1
            while (j < len(layers) and j not in used and len(g) < len(printed) and notes[j].startswith('\x00')
                   and layers[j] in printed and layers[j] not in [layers[k] for k in g]
                   and (PRINTED.search(notes[j]) or [None, m.group(1)])[1] == m.group(1)):
                g.append(j)
                j += 1
            if (len(g) > 1 and ';' not in layers[i] and all(layers[k] in printed and ';' not in layers[k] for k in g)
                    and len({layers[k] for k in g}) == len(g)):
                groups.append(g)
                used |= set(g)
                i = j
                continue
        i += 1
    return sorted(groups)


def physical_rows(n_sp, groups):
    """転記の種の行を物理の行にまとめる．[[転記の行, …], …] (0 始まり)"""
    first = {g[0]: g for g in groups}
    skip = {k for g in groups for k in g[1:]}
    return [first.get(r, [r]) for r in range(n_sp) if r not in skip]


def parse_merge(specs):
    out = []
    for s in specs:
        lo, _, hi = s.partition('-')
        out.append(list(range(int(lo) - 1, int(hi or lo))))
    return out


# ---- 画像 ----

def remove_rules(bw, length):
    """length 以上続く縦・横の線を消す (罫線・折り目の線・枠)"""
    u = bw.view(np.uint8)
    rule = np.zeros_like(bw)
    for axis in (0, 1):
        o = ndi.maximum_filter1d(ndi.minimum_filter1d(u, length, axis=axis), length, axis=axis)
        rule |= o.astype(bool)
    rule = ndi.binary_dilation(rule, structure=np.ones((3, 3), bool))
    return bw & ~rule


def components(im, box, threshold=128, rule=60, min_area=8, strip=1500, margin=80):
    """box の中の字のかたまり．列は (x 中心, y 中心, 幅, 高さ, 面積, 充填率, 上, 下) (原寸の座標)"""
    x0, y0, x1, y1 = box
    out = []
    for top in range(y0, y1, strip):
        a, b = max(y0, top - margin), min(y1, top + strip + margin)
        bw = np.asarray(im.crop((x0, a, x1, b))) < threshold
        if rule:
            bw = remove_rules(bw, rule)
        lab, n = ndi.label(bw, structure=np.ones((3, 3), bool))
        if not n:
            continue
        area = np.bincount(lab.ravel())
        for i, sl in enumerate(ndi.find_objects(lab), 1):
            if sl is None or area[i] < min_area:
                continue
            ya, yb, xa, xb = sl[0].start + a, sl[0].stop + a, sl[1].start + x0, sl[1].stop + x0
            yc = (ya + yb) / 2
            if not top <= yc < min(y1, top + strip):        # 重なりの分は隣の帯で拾う
                continue
            w, h = xb - xa, yb - ya
            hole = 0
            if 6 <= w <= 40 and 6 <= h <= 40:               # 点の大きさのかたまりだけ，中の穴 (白抜きの点) を数える
                sub = lab[sl] == i
                hole = int(ndi.binary_fill_holes(sub).sum() - sub.sum())
            out.append(((xa + xb) / 2, yc, w, h, area[i], area[i] / (w * h), ya, yb, hole))
    return np.array(out, float).reshape(-1, 9)


def join_split(c, gap=6):
    """横の線 (折り目・罫線) を消して上下に割れた字を 1 つに戻す．x が重なり，縦の隙間が gap 以下で，
    幅が近く (狭いほうが広いほうの半分以上)，つないでも字の高さの 1.3 倍に収まるかたまりをつなぐ
    (コンマと下線のように幅の違うものはつながない)"""
    if len(c) < 2:
        return c
    big = c[c[:, 3] >= 12]
    limit = 1.3 * float(np.median(big[:, 3])) if len(big) else 60.0
    xa, xb = c[:, 0] - c[:, 2] / 2, c[:, 0] + c[:, 2] / 2
    ya, yb = c[:, 6].copy(), c[:, 7].copy()
    xa, xb = xa.copy(), xb.copy()
    alive = np.ones(len(c), bool)
    order = np.argsort(ya)
    for i in order:
        if not alive[i]:
            continue
        j = np.where(alive & (np.arange(len(c)) != i) & (xa < xb[i]) & (xb > xa[i])
                     & (ya >= yb[i] - 1) & (ya - yb[i] <= gap))[0]
        for k in j:                                     # 上のかたまり i に，すぐ下のかたまり k をつなぐ
            wi, wk = xb[i] - xa[i], xb[k] - xa[k]
            if min(wi, wk) < .5 * max(wi, wk) or max(yb[i], yb[k]) - ya[i] > limit:
                continue
            xa[i], xb[i] = min(xa[i], xa[k]), max(xb[i], xb[k])
            yb[i] = max(yb[i], yb[k])
            alive[k] = False
    out = c[alive].copy()
    xa, xb, ya, yb = xa[alive], xb[alive], ya[alive], yb[alive]
    out[:, 0], out[:, 1] = (xa + xb) / 2, (ya + yb) / 2
    out[:, 2], out[:, 3] = xb - xa, yb - ya
    out[:, 6], out[:, 7] = ya, yb
    return out


def detect_rows(im, x0, x1, y0, y1, a):
    """--ref の範囲で行を取る．字の大きさのかたまりを中心の y で寄せ，行の中心の y の配列を返す．
    下線・コンマ・字の間の縦の印 (幅の狭いかたまりだけの寄せ) は行とみない"""
    allc = join_split(components(im, (x0, y0, x1, y1), a.threshold, a.rule, 6))
    c = allc[(allc[:, 3] >= 6) & (allc[:, 3] <= 60) & ~((allc[:, 3] < 16) & (allc[:, 2] >= 2.5 * allc[:, 3]))]
    big = c[c[:, 3] >= 12]
    if not len(big):
        return np.array([], float)
    medh = float(np.median(big[:, 3]))
    c = c[(c[:, 3] >= .55 * medh) & (c[:, 3] <= 1.8 * medh)]
    # 階層の印字が `-` だけの行: 字の高さの半分より低い横棒で，上下に字が無いもの (下線とは分ける)
    dash = allc[(allc[:, 3] <= .4 * medh) & (allc[:, 2] >= 2.5 * allc[:, 3]) & (allc[:, 2] >= .3 * medh)
                & (allc[:, 2] <= 1.5 * medh)]
    lone = [q for q in dash if not np.any(np.abs(c[:, 1] - q[1]) < 1.2 * medh)]   # その高さに字が 1 つも無い
    if lone:
        fake = np.array(lone, float)
        fake[:, 3] = medh                               # 字の高さの行として数える
        fake[:, 6], fake[:, 7] = fake[:, 1] - medh / 2, fake[:, 1] + medh / 2
        fake[:, 2] = np.maximum(fake[:, 2], np.median(c[:, 2]))
        c = np.vstack([c, fake])
    medw = float(np.median(c[:, 2]))
    c = c[np.argsort(c[:, 1])]
    groups = []
    for q in c:
        if groups and q[1] - groups[-1][-1][1] <= max(6.0, a.row_gap * medh):
            groups[-1].append(q)
        else:
            groups.append([q])
    out = []
    for g in groups:
        g = np.array(g)
        if g[:, 2].max() < .6 * medw:                   # 幅の狭いかたまりだけ (字の間の縦の印・1 だけの欠け)
            continue
        if g[:, 6].min() <= y0 + 1 or g[:, 7].max() >= y1 - 1:   # 範囲の端で切れた字
            continue
        out.append(float(np.median((g[:, 6] + g[:, 7]) / 2)))
    return np.array(out, float)


def dot_size(c, a=None, dot_min=3, least=10):
    """点の大きさ (px) を測る (marks_grid.py の measure_dot_size と同じ決まり)．小さく丸く詰まったかたまり
    (充填率 0.6 以上・縦横比 1.5 以内) の幅と高さの大きいほうの最頻値 (1 px のぶれをならす)"""
    if not len(c):
        return None
    w, h, fill = c[:, 2], c[:, 3], c[:, 5]
    ok = (fill >= .6) & (np.maximum(w, h) <= 1.5 * np.minimum(w, h)) & (np.minimum(w, h) >= dot_min) & (np.maximum(w, h) <= 60)
    size = np.maximum(w, h)[ok].astype(int)
    if len(size) < least:
        return None
    cnt = np.bincount(size)
    sm = cnt + .5 * (np.r_[0, cnt[:-1]] + np.r_[cnt[1:], 0])
    return int(sm.argmax())


def auto_dot_max(size, floor=16):
    """marks_grid.py の auto_dot_max と同じ (点の大きさの 1.25 倍．16 より下げない)"""
    return floor if size is None else max(floor, int(np.ceil(1.25 * size)))


def is_dot(q, dot_max, a):
    w, h, fill = q[2], q[3], q[5]
    return 3 <= min(w, h) and max(w, h) <= dot_max and fill >= a.dot_fill and max(w, h) <= 1.8 * min(w, h)


def is_ring(q, dot_max):
    """白抜きの点 (中の白い丸．点の刷りの欠け)．点の大きさで丸く，充填率が点より低い"""
    w, h, fill = q[2], q[3], q[5]
    return (min(w, h) >= 6 and max(w, h) <= dot_max and max(w, h) <= 1.3 * min(w, h) and .25 <= fill
            and len(q) > 8 and q[8] >= .12 * w * h)         # 中に穴がある (+ や 1 には穴が無い)


def sliver(q, dot_area):
    """折り目・線の切れ端 (marks_grid.py と同じ)"""
    return min(q[2], q[3]) <= 3 and max(q[2], q[3]) >= 3 * min(q[2], q[3]) and q[4] < .5 * dot_area


def make_words(comps, pitch, gap):
    """同じ行の高さで横に gap 以下の隙間で続くかたまりを 1 つの印 (語) にまとめる．
    戻り: かたまりの添字の組のリスト (左から)"""
    order = np.lexsort((comps[:, 0], comps[:, 1]))
    words = []                                          # [添字のリスト, 右端, y]
    for i in order:
        q = comps[i]
        xa = q[0] - q[2] / 2
        best = None
        for w in words[-40:]:
            if abs(w[2] - q[1]) <= .3 * pitch and -2 <= xa - w[1] <= gap:
                best = w
        if best is not None:
            best[0].append(int(i))
            best[1] = max(best[1], q[0] + q[2] / 2)
            best[2] = float(np.mean(comps[best[0], 1]))
        else:
            words.append([[int(i)], q[0] + q[2] / 2, float(q[1])])
    return [sorted(w[0], key=lambda k: comps[k, 0]) for w in words]


def word_kind(g, comps, isdot, dot_max, dot_area, speck=.7):
    """1 つの印 (語) の種類: 'd' 点・'r' 白抜きの点・'v' 値・None 捨てる (marks_grid.py の mark_kind と同じ考え)"""
    dots = [k for k in g if isdot[k]]
    rest = [k for k in g if not isdot[k]]
    if not rest and len(dots) in (1, 2):
        return 'd'
    if len(dots) == 1:
        d = comps[dots[0]]
        if all(sliver(comps[k], max(dot_area, d[4])) for k in rest):
            return 'd'
        if len(rest) == 1 and comps[rest[0], 4] < speck * d[4] and max(comps[rest[0], 2:4]) <= max(d[2:4]):
            return 'd'
    if not dots and all(sliver(comps[k], dot_area) for k in g):
        return None
    if len(g) == 1 and is_ring(comps[g[0]], dot_max):
        return 'r'
    return 'v'


def chain_rows(prev_y, ys, tol, gap=30.0):
    """予測の行の y (prev_y) と印の y (ys．昇順) を単調に対応づける (DP)．{行: 印} を返す"""
    n, m = len(prev_y), len(ys)
    INF = 1e18
    D = np.full((n + 1, m + 1), INF)
    B = np.zeros((n + 1, m + 1), np.int8)
    D[0, :] = np.arange(m + 1) * gap
    D[:, 0] = np.arange(n + 1) * gap
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best, bb = D[i - 1, j] + gap, 1
            v = D[i, j - 1] + gap
            if v < best:
                best, bb = v, 2
            d = abs(prev_y[i - 1] - ys[j - 1])
            if d <= tol and D[i - 1, j - 1] + d < best:
                best, bb = D[i - 1, j - 1] + d, 0
            D[i, j], B[i, j] = best, bb
    i, j, pairs = n, m, {}
    while i > 0 and j > 0:
        if B[i, j] == 0:
            pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif B[i, j] == 1:
            i -= 1
        else:
            j -= 1
    return pairs


def column_peaks(xs, n, x0, x1):
    """点の x の山から，列の中心を n 個選ぶ．足りなければ None (marks_grid.py と同じ)"""
    if len(xs) == 0:
        return None
    hist = np.bincount((xs - x0).astype(int).clip(0, x1 - x0), minlength=x1 - x0 + 1).astype(float)
    sm = np.convolve(hist, np.ones(7), 'same')
    sep = .4 * (x1 - x0) / n
    cand = [i for i in range(len(sm)) if sm[i] > 0 and sm[i] == sm[max(0, i - 8):i + 9].max()]
    kept = []
    for i in sorted(cand, key=lambda i: -sm[i]):
        if sm[i] >= sm.max() * .08 and all(abs(i - k) >= sep for k in kept):
            kept.append(i)
    if len(kept) < n:
        return None
    kept = sorted(sorted(kept, key=lambda i: -sm[i])[:n])
    return [x0 + k + .5 for k in kept]


def regular_columns(xs, n, x0, x1):
    """点の x の投影に，等間隔の n 列を当てはめる (marks_grid.py と同じ)"""
    hist = np.bincount((np.asarray(xs) - x0).astype(int).clip(0, x1 - x0), minlength=x1 - x0 + 1).astype(float)
    sm = np.convolve(hist, np.ones(7), 'same')
    w = len(sm) - 1
    if n == 1 or w <= 0:
        return [x0 + int(sm.argmax()) + .5]
    best = (-1.0, 0.0, 0.0)
    k = np.arange(n)
    for p in np.arange(max(8.0, .45 * w / n), 1.05 * w / (n - 1) + .5, .5):
        offs = np.arange(0, w - (n - 1) * p + 1)
        if not len(offs):
            continue
        pos = np.rint(offs[:, None] + k[None, :] * p).astype(int).clip(0, w)
        score = sm[pos].sum(axis=1)
        i = int(score.argmax())
        if score[i] > best[0]:
            best = (float(score[i]), float(p), float(offs[i]))
    _, p, o = best
    xs = np.asarray(xs, float) - x0
    cs, ms = [], []
    for c in range(n):
        near = xs[np.abs(xs - (o + c * p)) <= p / 4]
        if len(near):
            cs.append(c)
            ms.append(float(np.median(near)))
    if len(cs) >= 2:
        p, o = np.polyfit(cs, ms, 1)
    return [float(x0 + o + c * p) for c in range(n)]


def pick_columns(xs, n, x0, x1):
    peaks = column_peaks(xs, n, x0, x1)
    if len(xs) == 0:
        return None, '点が無い'
    reg = regular_columns(xs, n, x0, x1)
    if peaks is None:
        return reg, '等間隔の当てはめ (山が列の数に足りない)'
    gaps = np.diff(peaks)
    if len(gaps) and gaps.max() > 1.5 * gaps.min():
        hist = np.bincount((np.asarray(xs) - x0).astype(int).clip(0, x1 - x0), minlength=x1 - x0 + 1)
        sm = np.convolve(hist, np.ones(7), 'same')
        if all(sm[int(round(x - x0 - .5))] > 0 for x in reg):
            return reg, '等間隔の当てはめ (山の間隔が不ぞろい)'
    return peaks, '点の投影'


def read_colx(path, table, page):
    xs = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            p = line.rstrip('\r\n').split('\t')
            if len(p) >= 4 and p[0] == table and (p[1] == page or not page) and p[2].isdigit():
                xs.append((int(p[2]), float(p[3])))
    return [x for _, x in sorted(xs)]


def column_lines(base, dots, half):
    """列ごとに，点の x を y の直線 x = a + b*y で当て直す (紙面が下ほど左へ寄る表)．[(a, b)]"""
    out = []
    for x in base:
        near = dots[np.abs(dots[:, 0] - x) <= half]
        if len(near) >= 8:
            ys = near[:, 1]
            mid = float(np.median(ys))
            lo, hi = near[ys <= mid], near[ys > mid]
            if len(lo) >= 4 and len(hi) >= 4 and np.median(hi[:, 1]) - np.median(lo[:, 1]) > 200:
                y1, y2 = float(np.median(lo[:, 1])), float(np.median(hi[:, 1]))
                x1, x2 = float(np.median(lo[:, 0])), float(np.median(hi[:, 0]))
                b = (x2 - x1) / (y2 - y1)
                out.append((x1 - b * y1, b))
                continue
            out.append((float(np.median(near[:, 0])), 0.0))
        else:
            out.append((float(x), 0.0))
    return out


# ---- 比べる ----

def best_segment(e0, ed, min_gain):
    """e0 - ed の和が最大の区間 (Kadane)．(利得, 始め, 終わり) か None (0 始まり)"""
    best, cur, start, out = 0, 0, 0, None
    for i, g in enumerate(e0 - ed):
        if cur <= 0:
            cur, start = g, i
        else:
            cur += g
        if cur > best:
            best, out = cur, (int(cur), start, i)
    return out if out and out[0] >= min_gain else None


def compare(T, I, nrows, min_gain):
    """ずらし d ごとの食い違いの数と，d=±1 で良くなる区間"""
    n = {}
    e = {}
    for d in (-1, 0, 1):
        s = {r + d for r in T}
        n[d] = len(s ^ I)
        e[d] = np.array([int((r in s) != (r in I)) for r in range(-1, nrows + 1)])
    segs = {}
    for d in (-1, 1):
        seg = best_segment(e[0], e[d], min_gain)
        if seg:
            segs[d] = (seg[0], max(0, seg[1] - 1), min(nrows - 1, seg[2] - 1))   # e の添字は 1 行目の上から
    return n, segs


def font(size=16):
    for name in ('arial.ttf', 'DejaVuSans.ttf', 'msgothic.ttc', 'meiryo.ttc'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def strip_image(im, ref, cx, half, rowy, k0, k1, labels, path, pitch):
    """--ref の範囲と列の縦帯を並べ，左に行番号，右に転記の値を書く"""
    top, bottom = int(rowy[k0] - pitch), int(rowy[k1] + pitch)
    names = im.crop((ref[0], top, ref[1], bottom))
    col = im.crop((int(cx - 2 * half), top, int(cx + 2 * half), bottom))
    lw, tw = 60, 120
    out = Image.new('RGB', (lw + names.width + 10 + col.width + tw, names.height), 'white')
    out.paste(names, (lw, 0))
    out.paste(col, (lw + names.width + 10, 0))
    d = ImageDraw.Draw(out)
    f = font(18)
    for k in range(k0, k1 + 1):
        y = rowy[k] - top
        d.text((4, y - 10), str(k + 1), fill=(200, 0, 0), font=f)
        d.text((out.width - tw + 6, y - 10), labels[k].replace('・', '·'), fill=(0, 0, 200), font=f)
    out.save(path)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('image')
    ap.add_argument('out')
    ap.add_argument('table', help='表の名前 (Tab.9 など)')
    ap.add_argument('--box', type=int, nargs=4, required=True, metavar=('X0', 'Y0', 'X1', 'Y1'),
                    help='値の列の範囲 (原寸)．y は最初の種の行から最後の種の行まで')
    ap.add_argument('--ref', type=int, nargs=2, metavar=('X0', 'X1'), help='行の y を測る x の範囲 (階層か和名の列)')
    ap.add_argument('--ref2', type=int, nargs=2, metavar=('X0', 'X1'), help='右側でもう 1 か所行の y を測る範囲 (傾きの補間)')
    ap.add_argument('--rows-in', help='行の y を 1 行ずつ書いたファイル (転記の種の行の数か，まとめた物理の行の数)')
    ap.add_argument('--rows-out', help='測った行の y を書く')
    ap.add_argument('--edge', type=int, default=30, help='行を測る範囲を --box の上下に広げる幅 (px)')
    ap.add_argument('--row-gap', type=float, default=.45,
                    help='行を測るとき，字の中心の y の差がこの割合 (字の高さに対して) 以下なら同じ行')
    ap.add_argument('--centers', type=float, nargs='+', help='全列の中心の x')
    ap.add_argument('--first-x', type=float, help='第 1 列の中心の x (--pitch と組)')
    ap.add_argument('--pitch', type=float, help='列の間隔 (--first-x と組)')
    ap.add_argument('--colx', help='marks_grid.py が書く col_x.tsv (この表の列の中心)')
    ap.add_argument('--const', type=int, nargs='*', help='常在度の列 (1 始まり．省くと転記から見分ける)')
    ap.add_argument('--margin', type=int, default=120, help='印を --box の上下に広げて拾う幅 (px)')
    ap.add_argument('--threshold', type=int, default=128)
    ap.add_argument('--rule', type=int, default=60, help='これ以上続く縦・横の線を消す (px．0 で消さない)')
    ap.add_argument('--dot-max', type=int, help='点の幅・高さの上限 (省くと点の大きさを測って決める)')
    ap.add_argument('--dot-fill', type=float, default=.5, help='点の充填率の下限')
    ap.add_argument('--fold', type=float, nargs='+', help='縦の折り目の線の x (原寸)．その列はずれ・多いの判定から外し，縦帯で見る')
    ap.add_argument('--track', choices=('none', 'up', 'down', 'chain'), default='none',
                    help='列の中で行と印の差を印ごとに追う (up: 表の下から上へ．折り目で右上ほど行が下がる表)')
    ap.add_argument('--merge-split', action='store_true', help='階層ごとに分けた転記の行を 1 行にまとめて比べる')
    ap.add_argument('--merge-rows', nargs='+', default=[], metavar='K0-K1',
                    help='1 行にまとめて比べる転記の種の行 (1 始まり．括弧書きの種を分けた行など．例: 8-9)')
    ap.add_argument('--many', type=int, default=3, help='d=0 の食い違いがこれ以上の列を挙げる')
    ap.add_argument('--gain', type=int, default=2, help='d=±1 で食い違いがこれ以上減る区間を挙げる')
    ap.add_argument('--cols', help='見る列だけ (例: 3,14-20)')
    ap.add_argument('--diff', action='store_true', help='全部の列の食い違いの行を出す (既定は挙げた列だけ)')
    ap.add_argument('--strips', help='挙げた列の縦帯の画像を書く置き場')
    a = ap.parse_args(argv)

    sp, kinds, n = read_body(os.path.join(a.out, 'transcripts', table_dir(a.table), 'body.tsv'))
    if not n:
        sys.exit('body.tsv の見出しに地点の列 (1, 2, …) が無い')
    if not sp:
        sys.exit('body.tsv に種の行が無い')
    groups = []
    if a.merge_split or a.merge_rows:
        manual = parse_merge(a.merge_rows)
        groups = split_groups(sp, manual) if a.merge_split else sorted(manual)
        if groups:
            print(f'分けた行をまとめた: {len(groups)} 組 ' + ' '.join(f'{g[0] + 1}-{g[-1] + 1}' for g in groups[:12])
                  + (' …' if len(groups) > 12 else ''))
    phys = physical_rows(len(sp), groups)
    im = Image.open(a.image).convert('L')
    X0, Y0, X1, Y1 = a.box

    # 0. 値の範囲の印 (上下に --margin 広げて拾う．端の行に掛けて切っても落とさない)
    top, bottom = max(0, Y0 - a.margin), min(im.height, Y1 + a.margin)
    comps = components(im, (X0, top, X1, bottom), a.threshold, a.rule)
    if not len(comps):
        sys.exit('--box の中に字が無い')
    comps = comps[(comps[:, 3] <= 45) & (comps[:, 2] <= 90)]
    comps = comps[~((comps[:, 3] < 8) & (comps[:, 2] >= 3 * comps[:, 3]))]          # 下線・横線
    comps = comps[~((comps[:, 2] <= 6) & (comps[:, 3] >= 15))]                      # 縦の線の切れ
    if not len(comps):
        sys.exit('--box の中に字が無い')

    def drop_headings(ys, want):
        """値の範囲に印のほとんど無い行 (群の見出し) を除いて want 行になれば，その y を返す"""
        if len(ys) <= want or len(ys) < 2:
            return None
        p = float(np.median(np.diff(ys)))
        cnt = np.array([int(np.sum(np.abs(comps[:, 1] - y) <= .3 * p)) for y in ys])
        empty = np.where(cnt < max(1, .2 * n))[0]
        if len(ys) - len(empty) == want:
            return np.delete(ys, empty), [round(ys[i]) for i in empty]
        return None

    # 1. 行の y
    if a.rows_in:
        with open(a.rows_in, encoding='utf-8') as f:
            ys = [float(v) for v in f.read().split()]
        if len(ys) == len(sp) and not groups:          # 転記の行ごとの y．同じ y は同じ物理の行
            phys, rowy = [], []
            for r, y in enumerate(ys):
                if rowy and y == rowy[-1]:
                    phys[-1].append(r)
                else:
                    phys.append([r])
                    rowy.append(y)
            rowy = np.array(rowy)
        elif len(ys) == len(phys):
            rowy = np.array(ys)
        else:
            sys.exit(f'--rows-in の y は {len(ys)} 個．転記の種の行 {len(sp)}・まとめた行 {len(phys)}')
        rowy2, xr, xr2 = None, X0, None
        print(f'行の y: --rows-in ({len(rowy)} 行)')
    else:
        if not a.ref:
            sys.exit('--ref (行の y を測る x の範囲) か --rows-in が要る')

        def measure(ref, label):
            ys = detect_rows(im, ref[0], ref[1], max(0, Y0 - a.edge), min(im.height, Y1 + a.edge), a)
            if len(ys) == len(phys):
                return ys
            n_group = kinds.count('group')
            if n_group and len(ys) == len(phys) + n_group and not groups:     # 見出しも 1 行と数えた
                print(f'{label}: 群の見出し {n_group} 行も数えたので，転記の並びで除いた')
                return np.array([y for y, k in zip(ys, kinds) if k == 'sp'])
            got = drop_headings(ys, len(phys))
            if got:
                print(f'{label}: 値の範囲に印の無い行 (群の見出し) を除いた y={got[1]}')
                return got[0]
            d = np.diff(ys) if len(ys) > 1 else np.array([0.0])
            med = float(np.median(d)) if len(d) else 0
            print(f'{label}: 行の数が合わない．画像 {len(ys)} 行・転記の種の行 {len(phys)}'
                  + (f' (分けた行をまとめる前は {len(sp)})' if groups else '')
                  + f'．行の間隔の中央値 {med:.0f} px')
            if len(ys):
                print(f'  最初の行 y={ys[0]:.0f}・最後の行 y={ys[-1]:.0f}')
            wide = [(round(ys[i]), round(ys[i + 1])) for i in range(len(d)) if d[i] > 1.5 * med]
            narrow = [(round(ys[i]), round(ys[i + 1])) for i in range(len(d)) if d[i] < .6 * med]
            if wide:
                print(f'  間隔の広い所 (行の落ちか見出し) {wide[:10]}')
            if narrow:
                print(f'  間隔の狭い所 (2 行に分かれた字か，余分な字) {narrow[:10]}')
            if len(ys) > 1:                             # 余分の行の候補: 値の範囲に印の少ない行 (見出し・枠の破線・- だけの行)
                cnt = np.array([int(np.sum(np.abs(comps[:, 1] - y) <= .3 * med)) for y in ys])
                low = [(i + 1, round(ys[i]), int(cnt[i])) for i in np.argsort(cnt)[:max(3, abs(len(ys) - len(phys)) + 2)]
                       if cnt[i] < max(2, .3 * n)]
                if low:
                    print('  値の範囲に印の少ない行 (測った行の番号, y, 印の数．見出し・枠の線の候補): '
                          + ' '.join(f'{k}:{y}({c})' for k, y, c in sorted(low)))
            if a.rows_out:                              # 測った y を書き，直して --rows-in で渡せるようにする
                with open(a.rows_out, 'w', encoding='utf-8') as f:
                    f.write(''.join(f'{y:.0f}\n' for y in ys))
                print(f'  測った行の y を {a.rows_out} に書いた (直して --rows-in で渡せる)')
            print('  --box の y・--ref の x を見直す．1 印字行を 2 行に分けた転記は --merge-rows・--merge-split，'
                  '測れない表は --rows-in')
            return None
        rowy = measure(a.ref, '--ref')
        if rowy is None:
            return 1
        xr = (a.ref[0] + a.ref[1]) / 2
        rowy2 = xr2 = None
        if a.ref2:
            rowy2 = measure(a.ref2, '--ref2')
            if rowy2 is None:
                print('  --ref2 は使わない (左の 1 か所だけで測る)')
            else:
                xr2 = (a.ref2[0] + a.ref2[1]) / 2
                dd = rowy2 - rowy
                print(f'--ref2: 右で行が {float(np.median(dd)):+.0f} px (最小 {dd.min():+.0f}・最大 {dd.max():+.0f})')
    nrows = len(rowy)
    pitch = float(np.median(np.diff(rowy))) if nrows > 1 else 60.0
    tol = .45 * pitch
    print(f'行: {nrows} 行・間隔 {pitch:.1f} px・最初 y={rowy[0]:.0f}・最後 y={rowy[-1]:.0f}')
    if a.rows_out:
        with open(a.rows_out, 'w', encoding='utf-8') as f:
            f.write(''.join(f'{y:.0f}\n' for y in rowy))

    def rows_at(x):
        if rowy2 is None:
            return rowy
        return rowy + (x - xr) / (xr2 - xr) * (rowy2 - rowy)

    # 2. 列
    dot_max = a.dot_max
    m = dot_size(comps)
    if dot_max is None:
        dot_max = auto_dot_max(m)
        print(f'点の大きさ {m} px とみて，点の上限を {dot_max} px にした (marks_grid.py と同じ決め方．--dot-max で変える)')
    isdot = np.array([is_dot(q, dot_max, a) for q in comps])
    dot_area = float(np.median(comps[isdot, 4])) if isdot.any() else 0.0
    dots = comps[isdot]
    if a.centers:
        base, how = sorted(a.centers), '引数'
    elif a.first_x is not None and a.pitch:
        base, how = [a.first_x + a.pitch * k for k in range(n)], '引数 (--first-x・--pitch)'
    elif a.colx:
        base, how = read_colx(a.colx, a.table, os.path.splitext(os.path.basename(a.image))[0]), 'col_x.tsv'
    else:
        base, how = pick_columns(dots[:, 0] if len(dots) else np.array([]), n, X0, X1)
    if not base or len(base) != n:
        sys.exit(f'列の中心が {0 if not base else len(base)} 個．地点は {n}．--centers で全列の x を渡す')
    gaps = np.diff(base) if n > 1 else np.array([120.0])
    halves = [.42 * min(gaps[max(0, c - 1)], gaps[min(len(gaps) - 1, c)]) for c in range(n)]
    lines = column_lines(base, dots, min(halves))
    print(f'列の中心 ({how}): {n} 列．第 1 列 x={base[0]:.0f}・最後 x={base[-1]:.0f}・間隔 {gaps.min():.0f}-{gaps.max():.0f}')
    tilt = [b for _, b in lines]
    if max(abs(t) for t in tilt) * (Y1 - Y0) > 10:
        print(f'列が y で横へ寄る: 表の上から下で最大 {max(tilt, key=abs) * (Y1 - Y0):+.0f} px (列ごとに直線で当てた)')
    vals = [[any(has_value(sp[k]['vals'][c]) for k in g) for c in range(n)] for g in phys]
    text = [[' / '.join(sp[k]['vals'][c] for k in g if has_value(sp[k]['vals'][c])) or '・' for c in range(n)] for g in phys]
    const = {c - 1 for c in a.const} if a.const is not None else {
        c for c in range(n) if (lambda got: got and sum(bool(CONST_RE.match(v)) for v in got) * 2 >= len(got))(
            [sp[k]['vals'][c] for k in range(len(sp)) if has_value(sp[k]['vals'][c])])}
    if const:
        print('常在度の列: ' + ' '.join(str(c + 1) for c in sorted(const)))
    cols = range(n)
    if a.cols:
        cols = []
        for part in a.cols.split(','):
            lo, _, hi = part.partition('-')
            cols += list(range(int(lo) - 1, int(hi or lo)))

    # 3. 印 (語) を作り，列に当てる．横に続くかたまり (1・1・V(+-2) の字と括弧) は 1 つの印．
    #    常在度の列の値は点の位置から右へ印字されるので左端で，ほかの列は語の中央で列を決める
    gapx = max(4.0, min(.22 * float(gaps.min()), 1.2 * (m or 12)))
    words = make_words(comps, pitch, gapx)
    wmarks = []                                          # (x, y, 種類, 列)
    for g in words:
        kind = word_kind(g, comps, isdot, dot_max, dot_area)
        if kind is None:
            continue
        q = comps[g]
        y = float(np.median(q[:, 1]))
        xl = float(q[0, 0])
        xc = float(((q[:, 0] - q[:, 2] / 2).min() + (q[:, 0] + q[:, 2] / 2).max()) / 2)
        at = [lines[c][0] + lines[c][1] * y for c in range(n)]
        cl = int(np.argmin([abs(xl - x) for x in at]))
        cc = int(np.argmin([abs(xc - x) for x in at]))
        if cl in const and abs(xl - at[cl]) <= halves[cl]:
            col = cl
        elif abs(xc - at[cc]) <= halves[cc] * (1.0 if cc not in const else 2.5):
            col = cc
        else:
            continue
        wmarks.append((xc, y, kind, col))
    folds = set()
    for f in a.fold or []:
        folds |= {c for c in range(n) if abs(lines[c][0] + lines[c][1] * (Y0 + Y1) / 2 - f) <= halves[c]}
    if folds:
        print('折り目の線が通る列 (ずれ・多いの判定から外す): ' + ' '.join(str(c + 1) for c in sorted(folds)))

    # 4. 列ごとに印を行に当て，ずらしを比べる
    flagged, many, results = [], [], {}
    prev = 0.0
    cur = None
    rings = 0
    for c in cols:
        a0, b0 = lines[c]
        half = halves[c]
        mine = [w for w in wmarks if w[3] == c]
        ms = np.array([[w[0], w[1]] for w in mine], float).reshape(-1, 2)
        mdot = np.array([w[2] in ('d', 'r') for w in mine], bool)
        rings += sum(1 for w in mine if w[2] == 'r')
        cx = a0 + b0 * (Y0 + Y1) / 2
        ry = rows_at(cx)
        order = np.argsort(ms[:, 1])
        ms, mdot = ms[order], mdot[order]
        offs = np.zeros(len(ms))
        chained = None
        if a.track == 'chain':                           # 隣の列の行の y から，印の並びを DP でつなぐ
            pred = cur if cur is not None else ry
            res = [ms[i, 1] - pred[int(np.argmin(np.abs(pred - ms[i, 1])))] for i in range(len(ms))]
            res = [r for r in res if abs(r) < .5 * pitch]
            o = float(np.median(res)) if res else 0.0
            pairs = chain_rows(pred + o, ms[:, 1], .4 * pitch)
            dif = np.full(nrows, np.nan)
            for i, j in pairs.items():
                dif[i] = ms[j, 1] - (pred[i] + o)
            idx = np.where(~np.isnan(dif))[0]
            fill = np.interp(np.arange(nrows), idx, dif[idx]) if len(idx) else np.zeros(nrows)
            cur = pred + o + fill
            chained = {}                                 # 行の y を直したあと，全部の印を最も近い行に当てる
            for j in range(len(ms)):                     # (1 つの行に印が 2 つある値も落とさない)
                i = int(np.argmin(np.abs(cur - ms[j, 1])))
                if abs(cur[i] - ms[j, 1]) <= tol:
                    chained[j] = i
            off = o
        elif a.track == 'none':
            res = []
            for y in ms[:, 1]:
                k = int(np.argmin(np.abs(ry + prev - y)))
                r = y - ry[k] - prev
                if abs(r) < .5 * pitch:
                    res.append(r)
            off = prev + (float(np.median(res)) if res else 0.0)
            prev = off
            offs[:] = off
        else:
            idx = list(range(len(ms)))[::-1] if a.track == 'up' else list(range(len(ms)))
            start = idx[:12]
            o = float(np.median([ms[i, 1] - ry[int(np.argmin(np.abs(ry - ms[i, 1])))] for i in start])) if start else 0.0
            for i in idx:
                k = int(np.argmin(np.abs(ry + o - ms[i, 1])))
                r = ms[i, 1] - ry[k] - o
                if abs(r) < .35 * pitch:
                    o += .25 * r
                offs[i] = o
            off = o
        img_val, img_any, lost = set(), set(), 0
        for j, (q, d, o) in enumerate(zip(ms, mdot, offs)):
            if chained is not None:
                if j not in chained:
                    lost += 1
                    continue
                k = chained[j]
            else:
                k = int(np.argmin(np.abs(ry + o - q[1])))
                if abs(ry[k] + o - q[1]) > tol:
                    lost += 1
                    continue
            img_any.add(k)
            if not d:
                img_val.add(k)
        T = {k for k in range(nrows) if vals[k][c]}
        nd, segs = compare(T, img_val, nrows, a.gain)
        whole = min((-1, 1), key=lambda d: nd[d])
        shift = whole if nd[whole] < nd[0] else 0
        if shift:                                        # 列全体がずれていれば，区間は見ない (d=0 との比べは意味が無い)
            segs = {}
        bad = bool(shift or segs) and c not in folds
        if bad:
            flagged.append(c)
        if nd[0] >= a.many and c not in folds:
            many.append(c)
        results[c] = dict(T=T, I=img_val, nd=nd, segs=segs, shift=shift, cx=cx, half=half, off=float(np.median(offs)) if len(offs) else off)
        mark = ' <<' if bad else (' <' if nd[0] >= a.many else '')
        print(f'列 {c + 1}: x={cx:.0f} 差 {off:+.0f} 値 画像 {len(img_val)}・転記 {len(T)}．印の無い行 {nrows - len(img_any)}．'
              f'食い違い d=-1:{nd[-1]} 0:{nd[0]} +1:{nd[1]}{mark}')
        for d, (g, k0, k1) in sorted(segs.items()):
            print(f'    行 {k0 + 1}-{k1 + 1} で d={d:+d} だと {g} 減る')
        if a.diff or bad or nd[0] >= a.many:
            only_img = sorted(img_val - T)
            only_tr = sorted(T - img_val)
            if only_img:
                print('    画像だけに値: ' + ', '.join(f'{k + 1} {phys_name(sp, phys, k)}' for k in only_img[:12])
                      + (' …' if len(only_img) > 12 else ''))
            if only_tr:
                print('    転記だけに値: ' + ', '.join(f'{k + 1} {phys_name(sp, phys, k)} {text[k][c]}' for k in only_tr[:12])
                      + (' …' if len(only_tr) > 12 else ''))

    print('---')
    if flagged:
        print('[ずれ] 1 行ずれの疑い (d=+1 は画像の値が転記の 1 行下):')
        for c in flagged:
            r = results[c]
            if r['shift']:
                print(f"  列 {c + 1}: 列全体で d={r['shift']:+d} (食い違い {r['nd'][0]} → {r['nd'][r['shift']]})")
            for d, (g, k0, k1) in sorted(r['segs'].items()):
                print(f'  列 {c + 1}: 行 {k0 + 1}-{k1 + 1} ({phys_name(sp, phys, k0)} 〜 {phys_name(sp, phys, k1)}) で d={d:+d} '
                      f'({g} 減る)')
    else:
        print('[ずれ] 1 行ずれの疑いのある列は無い')
    rest = [c for c in many if c not in flagged]
    if rest:
        print(f'[多い] d=0 でも食い違いが {a.many} 以上の列 (目安．ずれの判定は [ずれ] だけを見る): '
              + ' '.join(str(c + 1) for c in rest)
              + ' (折り目の線・枠の破線・よごれ・点の大きさを疑う．--dot-max・--box・--fold を見直す)')
        for c in rest:
            r = results[c]
            oi, ot = sorted(r['I'] - r['T']), sorted(r['T'] - r['I'])
            print(f'  列 {c + 1}: 画像だけに値 ' + (', '.join(str(k + 1) for k in oi[:10]) or '-')
                  + '．転記だけに値 ' + (', '.join(str(k + 1) for k in ot[:10]) or '-'))
    fold_bad = [c for c in folds if c in results and (results[c]['shift'] or results[c]['segs'] or results[c]['nd'][0] >= a.many)]
    if fold_bad:
        print('(折り目の列で食い違い: ' + ' '.join(str(c + 1) for c in sorted(fold_bad)) + '．縦帯で目で確かめる)')
    if rings:
        print(f'白抜きの点 (中の白い丸) {rings} 個を点とみた (値として印字された ○ の表では注意)')
    print(f'見た列 {len(results)}・ずれの疑い {len(flagged)} 列・食い違いの多い列 {len(rest)}')
    if a.strips and (flagged or rest or fold_bad):
        os.makedirs(a.strips, exist_ok=True)
        for c in flagged + rest + fold_bad:
            r = results[c]
            k0, k1 = 0, nrows - 1
            if r['segs']:
                g, k0, k1 = max(r['segs'].values())
                k0, k1 = max(0, k0 - 3), min(nrows - 1, k1 + 3)
            ry = rows_at(r['cx']) + r['off']
            ref = tuple(a.ref) if a.ref else (int(r['cx'] - 6 * r['half']), int(r['cx'] - 2 * r['half']))
            labels = [text[k][c] for k in range(nrows)]
            for s in range(k0, k1 + 1, 40):
                path = os.path.join(a.strips, f'{table_dir(a.table)}_c{c + 1:02d}_r{s + 1:03d}.png')
                strip_image(im, ref, r['cx'], r['half'], ry, s, min(k1, s + 39), labels, path, pitch)
                print(f'縦帯: {path}')
    print('(画像で確かめる．転記は書き換えていない)')
    return 0


def phys_name(sp, phys, k):
    return sp[phys[k][0]]['name'] + (f' (+{len(phys[k]) - 1} 行)' if len(phys[k]) > 1 else '')


if __name__ == '__main__':
    sys.exit(main())
