"""列ごとの印 (点と値) の並びで行の格子を作り，全セルの値の有無を転記と照合する．報告だけで，転記は書き換えない．

    python scripts/marks_grid.py <画像> <出力> <表> --box X0 Y0 X1 Y1
    python scripts/marks_grid.py <画像> <出力> <表> --box X0 Y0 X1 Y1 --centers 2082 2177 ... --diff-png d.png
    python scripts/marks_grid.py <画像> <出力> <表> --box X0 Y0 X1 Y1 --band 1 40 --band-png b.png --label 1250 1720

- `--box` は値の列だけを囲む (常在度の列は値が右へ伸びるので，その分も入れる)．座標は原寸の画像のもの．
- 罫線 (長い縦・横の線) を消し，字のかたまりを取る．点 (`・`) の x の山から列の中心を測り，
  縦に 1500 px ごとに測り直して紙面の傾きを追う．山が列の数に足りないときや，山の間隔が不ぞろい (点線の枠の破線を
  列と取り違えた) で等間隔の列がどれも点に当たるときは，等間隔の n 列を当てはめる (0.5.14)．
  それでも測れない表は `--centers` で全列の x を渡す．
- 列ごとに印 (点か値のかたまり) を上から拾う．印の数が最も多くの列で同じ数 (= 画像の行の数) になる列を起点にし，
  隣の列へ，前の列の行の y との差がなめらかに変わるように印を順につなぐ (動的計画法)．
  列の間隔が不等・右や下ほど行がずれる・貼り合わせの紙片で行が跳ぶ表でも追える．
- 画像の行と body.tsv の種の行を対応づけ，セルの値の有無を比べる．`[画像に値]` は転記が `・` で画像に値，
  `[転記に値]` は転記に値があって画像が点か空 (印なし)．枠の線・よごれ・値の下線の切れも混じるので，画像で確かめる．
- 点と値の見分けはかたまりの大きさ (`--dot-min`・`--dot-max`) と充填率 (`--dot-fill`．中部 Tab.57 は 0.56)．
  点の大きい表で `+` を点と見るときは `--dot-fill` を上げ，点を値と見るときは `--dot-max` を上げる．
- 常在度の列 (`V(1-2)` のようにローマ数字と括弧) は body.tsv の値から自動で見分け，値が点の位置から右へ伸びるとみる．
  `--const 9 10 11` で列を指定することもできる．
- `--diff-png` は食い違いのセルを切り出して並べた画像 (多いときは `_01` `_02` …)，
  `--band K0 K1 --band-png` は画像の行 K0〜K1 を，列ごとの行の y で切って横にそろえた帯の画像．
  `--tsv` は行 × 列の印の表 (d 点・v 値・_ 印なし) と y を書く．
- numpy・scipy・Pillow が要る．
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
except ImportError:                                     # pragma: no cover
    sys.exit('numpy と scipy が要る (pip install numpy scipy)')
from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
CONST_RE = re.compile(r'^(?:[IV]+|r|\+)\(|^[IV]+$')


def table_dir(table):
    return re.sub(r'\d+', lambda m: '%03d' % int(m.group()), table)


def read_rows(path):
    """種の行の名前 (和名か学名 + 階層)・[行][列] の転記の値・地点の数・階層・note"""
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE))
    cols = [i for i, c in enumerate(rows[0]) if c.strip().isdigit()]
    ni = rows[0].index('note') if 'note' in rows[0] else None
    names, vals, layers, notes, last = [], [], [], [], ''
    for r in rows[1:]:
        if not r or r[0] != 'sp':
            continue
        named = bool((r[4] if len(r) > 4 else '') or (r[3] if len(r) > 3 else ''))
        last = (r[4] if len(r) > 4 else '') or (r[3] if len(r) > 3 else '') or last
        names.append(f"{last} {r[5] if len(r) > 5 else ''}".strip())
        vals.append([r[i].strip() if i < len(r) else '' for i in cols])
        layers.append(r[5].strip() if len(r) > 5 else '')
        note = r[ni] if ni is not None and ni < len(r) else ''
        notes.append(note if named else '\x00' + note)  # 先頭の \x00 は名前の無い続きの行の印
    return names, vals, len(cols), layers, notes


def read_body(path):
    """種の行の名前 (和名か学名 + 階層) と，[行][列] の転記の値 (前後の空白を除いた文字列)"""
    names, vals, n, _, _ = read_rows(path)
    return names, vals, n


PRINTED = re.compile(r'印字は\s*([A-Za-z]\d?(?:\s*[,，]\s*[A-Za-z]\d?)+)')


def split_groups(layers, notes, manual=()):
    """1 つの印字の行を階層ごと (下線の種類で) に分けて書いた行の組 [[行, …], …] (0 始まり)．
    名前のある行に続く名前の無い行で，note に同じ「印字は B1,B2,S」があり，各行の階層がその 1 つずつのとき．
    note の先頭の \\x00 は名前の無い続きの行の印 (read_rows)．manual は手で渡す組 (0 始まり)"""
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
                   and (PRINTED.search(notes[j]) or [None, m.group(1)])[1] == m.group(1)):   # 同じ印か印なし
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


def merge_split(names, vals, groups):
    """分けた行の組を 1 行にまとめる (値はどれかの行にあれば値．文字列は / でつなぐ)．
    戻り値は (名前, 値, 元の行の組 [[行, …] …])"""
    first = {g[0]: g for g in groups}
    skip = {k for g in groups for k in g[1:]}
    out_n, out_v, src = [], [], []
    for r in range(len(vals)):
        if r in skip:
            continue
        g = first.get(r, [r])
        out_n.append(names[r] + (f' (+{len(g) - 1} 行)' if len(g) > 1 else ''))
        out_v.append(['/'.join(v for v in (vals[k][c] for k in g) if has_value(v)) or vals[r][c]
                      for c in range(len(vals[r]))])
        src.append(g)
    return out_n, out_v, src


def has_value(v):
    return v not in ('', '・', '.')


def const_columns(vals):
    """値の半分以上が常在度の書式 (`V(1-2)`・`+(+)`) の列 (0 始まり)"""
    out = set()
    for c in range(len(vals[0]) if vals else 0):
        got = [row[c] for row in vals if has_value(row[c])]
        if got and sum(bool(CONST_RE.match(v)) for v in got) >= len(got) / 2:
            out.add(c)
    return out


# ---- 画像からかたまりを取る ----

def remove_rules(bw, length):
    """length 以上続く縦・横の線を消す (1 次元の opening．罫線と枠)"""
    u = bw.view(np.uint8)
    rule = np.zeros_like(bw)
    for axis in (0, 1):
        o = ndi.maximum_filter1d(ndi.minimum_filter1d(u, length, axis=axis), length, axis=axis)
        rule |= o.astype(bool)
    rule = ndi.binary_dilation(rule, structure=np.ones((3, 3), bool))
    return bw & ~rule


def components(path, box, threshold=128, rule=60, min_area=8, strip=2000, margin=80):
    """--box の中の字のかたまり．列は (x 中心, y 中心, 幅, 高さ, 面積, 充填率, 左, 右, 上, 下) (原寸の座標)"""
    x0, y0, x1, y1 = box
    im = Image.open(path).convert('L')
    out = []
    for top in range(y0, y1, strip):
        a, b = max(y0, top - margin), min(y1, top + strip + margin)
        bw = np.asarray(im.crop((x0, a, x1, b))) < threshold
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
            out.append(((xa + xb) / 2, yc, w, h, area[i], area[i] / (w * h), xa, xb, ya, yb))
    return np.array(out, float).reshape(-1, 10)


def is_dot(q, a):
    w, h, fill = q[2], q[3], q[5]
    return (a.dot_min <= w <= a.dot_max and a.dot_min <= h <= a.dot_max
            and fill >= a.dot_fill and max(w, h) <= 1.8 * min(w, h))


# ---- 列 ----

def column_peaks(xs, n, x0, x1):
    """点の x の山から，列の中心を n 個選ぶ．足りなければ None"""
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


def projection(xs, x0, x1):
    hist = np.bincount((np.asarray(xs) - x0).astype(int).clip(0, x1 - x0), minlength=x1 - x0 + 1).astype(float)
    return np.convolve(hist, np.ones(7), 'same')


def regular_columns(xs, n, x0, x1):
    """点の x の投影に，等間隔の n 列を当てはめる (間隔と位置を総当たりで選ぶ)．
    点線の枠の縦の破線を列と取り違える・点の少ない列を落とすのを防ぐ (0.5.14．近畿 Tab.061)"""
    sm = projection(xs, x0, x1)
    w = len(sm) - 1
    if n == 1 or w <= 0:
        return [x0 + int(sm.argmax()) + .5], float(sm.max())
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
    s, p, o = best
    xs = np.asarray(xs, float) - x0                   # 列ごとに近くの点の中央値を取り，直線で当て直す (平滑の幅のずれを消す)
    cs, ms = [], []
    for c in range(n):
        near = xs[np.abs(xs - (o + c * p)) <= p / 4]
        if len(near):
            cs.append(c)
            ms.append(float(np.median(near)))
    if len(cs) >= 2:
        p, o = np.polyfit(cs, ms, 1)
    return [float(x0 + o + c * p) for c in range(n)], s


def pick_columns(xs, n, x0, x1):
    """列の中心と，測り方．山で n 列が取れて間隔がそろうときは山，そうでないときは等間隔の当てはめ"""
    peaks = column_peaks(xs, n, x0, x1)
    reg, rs = regular_columns(xs, n, x0, x1) if len(xs) else (None, 0)
    if peaks is None:
        return reg, '等間隔の当てはめ (山が列の数に足りない)'
    gaps = np.diff(peaks)
    if len(gaps) and gaps.max() > 1.5 * gaps.min():
        sm = projection(xs, x0, x1)                   # 等間隔の列がどれも点に当たるなら，そちらを取る
        if all(sm[int(round(x - x0 - .5))] > 0 for x in reg):
            return reg, '等間隔の当てはめ (山の間隔が不ぞろい)'
    return peaks, '点の投影'


class Columns:
    """列の中心を y で補間する (縦 band px ごとに点の x の中央値で測り直す)"""

    def __init__(self, base, dots, y0, y1, band=1500):
        self.base = np.array(base, float)
        gaps = np.diff(self.base)
        self.pitch = float(np.median(gaps)) if len(gaps) else 50.0
        near = np.minimum(np.r_[gaps, np.inf], np.r_[np.inf, gaps]) if len(gaps) else np.array([self.pitch])
        ys, rows = [], []
        for top in range(y0, y1, band):
            sel = dots[(dots[:, 1] >= top) & (dots[:, 1] < top + band)]
            row = self.base.copy()
            for c, cx in enumerate(self.base):
                xs = sel[np.abs(sel[:, 0] - cx) < .3 * near[c], 0]
                if len(xs) >= 3:
                    row[c] = np.median(xs)
            ys.append(min(top + band / 2, (top + y1) / 2))
            rows.append(row)
        self.ys, self.table = np.array(ys), np.array(rows)

    def at(self, y):
        """y (スカラーか配列) での全列の中心．形は (len(y), 列)"""
        y = np.atleast_1d(np.asarray(y, float))
        return np.stack([np.interp(y, self.ys, self.table[:, c]) for c in range(self.table.shape[1])], axis=1)


def assign_columns(comps, cols, const, a):
    """かたまりを列に割り当てる．-1 は捨てる (列の外・線の切れ)"""
    n = len(cols.base)
    cx = cols.at(comps[:, 1])
    gap = np.diff(cx, axis=1)
    p = cols.pitch
    bound = cx[:, :-1] + gap / 2
    for c in const:
        if c < n - 1:                                   # 常在度の値は点の位置から右へ伸びる
            bound[:, c] = cx[:, c + 1] - np.minimum(gap[:, c] / 2, .45 * p)
    xc = comps[:, 0]
    col = (xc[:, None] > bound).sum(axis=1)
    right = cx[:, -1] + (1.5 if n - 1 in const else .5) * p
    col[(xc < cx[:, 0] - .5 * p) | (xc > right)] = -1
    w, h = comps[:, 2], comps[:, 3]
    thin, long_ = np.minimum(w, h), np.maximum(w, h)
    flat = (thin <= a.thin) & (long_ >= 3 * thin)
    col[(w >= 3 * h) & (h <= 2 * a.thin)] = -1          # 横の線の切れ・下線・折り目・`-`
    dx = xc - cx[np.arange(len(xc)), col.clip(0)]
    isconst = np.isin(col, list(const))
    tall = (flat & (w < h)) | ((h >= 2.2 * w) & (h >= a.dot_max))
    col[tall & ~isconst & (np.abs(dx) > .3 * p)] = -1   # 列の間の縦の罫線の切れ・破線
    col[flat & (w < h) & ~isconst & (np.abs(dx) > 2 * a.dot_max)] = -1   # 列の間が広い表の枠の破線
    col[flat & (w < h) & isconst & (dx < -.3 * p)] = -1   # 常在度の列は値が右へ伸びるので，左だけを見る
    col[(h > a.max_h) | (w > 1.3 * p)] = -1
    col[comps[:, 4] < a.speck_area] = -1                # 点より小さいよごれ
    return col


def group_marks(comps, col, n, merge, a):
    """列ごとの印の並び．印は (y, 種類 d/v, 左, 右, 上, 下)．y の近いかたまりを 1 つの印にまとめる"""
    out = []
    for c in range(n):
        qs = comps[col == c]
        qs = qs[np.argsort(qs[:, 1])]
        groups = []
        for q in qs:
            if groups and q[1] - np.mean([g[1] for g in groups[-1]]) < merge:
                groups[-1].append(q)
            else:
                groups.append([q])
        ms = []
        for g in groups:
            kind = 'd' if len(g) == 1 and is_dot(g[0], a) else 'v'
            ya, yb = min(q[8] for q in g), max(q[9] for q in g)
            ms.append(((ya + yb) / 2, kind, min(q[6] for q in g), max(q[7] for q in g), ya, yb))
        out.append(ms)
    return out


def row_pitch(marks):
    d = [b[0] - a[0] for ms in marks for a, b in zip(ms, ms[1:])]
    d = [v for v in d if v > 4]
    return float(np.median(d)) if d else 20.0


# ---- 行の格子 ----

def shift(ms, ref, pitch):
    """前の列の行から見た印の y のずれ (近い組の中央値)"""
    ms, ref = np.sort(np.asarray(ms, float)), np.asarray(ref, float)
    if not len(ms) or not len(ref):
        return 0.0
    tol = .2 * pitch
    best = (-1, 0.0)
    for s in np.arange(-.6 * pitch, .6 * pitch + 1, 1.0):     # 印が行の近くに最も多く来るずれ
        t = ref + s
        hit = int((np.searchsorted(ms, t + tol) - np.searchsorted(ms, t - tol) > 0).sum())
        if hit > best[0] or (hit == best[0] and abs(s) < abs(best[1])):
            best = (hit, float(s))
    t = ref + best[1]
    i = np.searchsorted(ms, t).clip(1, len(ms) - 1) if len(ms) > 1 else np.zeros(len(t), int)
    cand = np.stack([ms[i - 1 if len(ms) > 1 else i], ms[i]], axis=1) - ref[:, None]
    d = cand[np.arange(len(ref)), np.abs(cand - best[1]).argmin(axis=1)]
    d = d[np.abs(d - best[1]) < tol]
    return float(np.median(d)) if len(d) else best[1]


def link(ms, ref, pitch, d0=None, gap=.45, jump=.35):
    """印の y の並び ms を，前の列の行の y の並び ref に順を保って当てる．
    差 (印 - 行) の変わり方が最も小さくなる当て方を選ぶ．戻り: (行ごとの印の番号 (無ければ -1), 余った印の番号)"""
    ms, ref = np.asarray(ms, float), np.asarray(ref, float)
    n, m = len(ms), len(ref)
    if d0 is None:
        d0 = shift(ms, ref, pitch)
    G, J, W = gap * pitch, jump * pitch, 4 * pitch
    INF = 1e18
    cost = np.full((n + 1, m + 1), INF)
    dl = np.zeros((n + 1, m + 1))
    bp = np.zeros((n + 1, m + 1), np.int8)
    cost[0, 0], dl[0, 0] = 0, d0
    lo = np.searchsorted(ref, ms - d0 - W)
    hi = np.searchsorted(ref, ms - d0 + W)
    loc = np.full(m, d0)                                # 24 行ごとのずれ．よごれに引かれた差をここへ戻せるようにする
    for s in range(0, m, 12):
        part = ref[s:s + 24]
        near = ms[(ms > part[0] - W) & (ms < part[-1] + W)]
        if len(part) >= 4 and len(near) >= 4:
            loc[s:s + 24] = shift(near, part, pitch)
    for i in range(n + 1):
        ja = 0 if i == 0 else max(0, int(lo[i - 1]) - 1)
        jb = m if i == n else min(m, int(hi[i]) + 1)
        for j in range(ja, jb + 1):
            c0 = cost[i, j]
            if c0 >= INF:
                continue
            if i < n and j < m:
                d = ms[i] - ref[j]
                e = min(abs(d - dl[i, j]), abs(d - loc[j]) + .1 * pitch)
                if e <= J and c0 + e < cost[i + 1, j + 1]:
                    cost[i + 1, j + 1], dl[i + 1, j + 1], bp[i + 1, j + 1] = c0 + e, d, 0
            if i < n and c0 + G < cost[i + 1, j]:
                cost[i + 1, j], dl[i + 1, j], bp[i + 1, j] = c0 + G, dl[i, j], 1
            if j < m and c0 + G < cost[i, j + 1]:
                cost[i, j + 1], dl[i, j + 1], bp[i, j + 1] = c0 + G, dl[i, j], 2
    asg, extra = [-1] * m, []
    i, j = n, m
    while i > 0 or j > 0:
        b = bp[i, j]
        if b == 0:
            asg[j - 1] = i - 1
            i, j = i - 1, j - 1
        elif b == 1:
            extra.append(i - 1)
            i -= 1
        else:
            j -= 1
    return asg, sorted(extra)


def fill_rows(ys, asg, ref, d0):
    """当てた印の y．印の無い行は前の列の行に近くの差の中央値を足す"""
    m = len(ref)
    d = np.array([ys[asg[k]] - ref[k] if asg[k] >= 0 else np.nan for k in range(m)])
    out = np.empty(m)
    for k in range(m):
        if asg[k] >= 0:
            out[k] = ys[asg[k]]
        else:
            near = d[max(0, k - 6):k + 7]
            near = near[~np.isnan(near)]
            out[k] = ref[k] + (np.median(near) if len(near) else d0)
    return out


def build_grid(marks, pitch, nrows=None, seed=None):
    """行の格子．戻り: (行の数, 起点の列, rowy[列] (行ごとの y), asg[列] (行ごとの印の番号), extra[列])"""
    n = len(marks)
    counts = [len(ms) for ms in marks]
    if nrows is None:
        freq = collections.Counter(counts)
        nrows = max(freq, key=lambda k: (freq[k], k))
    ys_of = [np.array([m[0] for m in ms]) for ms in marks]

    def smooth(c, e):                                   # 2 列の印を順番どおりに組んだとき，差がなめらかか
        return np.abs(np.diff(ys_of[c] - ys_of[e])).max(initial=0) <= .4 * pitch

    exact = [c for c in range(n) if counts[c] == nrows]
    trusted = []
    for i, c in enumerate(exact):                       # 数が合う列のうち，隣の数が合う列となめらかにつながるもの
        near = [e for e in exact[max(0, i - 1):i + 2] if e != c]
        if not near or any(smooth(c, e) for e in near):
            trusted.append(c)
    if seed is None:
        seed = (trusted or exact or [min(range(n), key=lambda c: abs(counts[c] - nrows))])[0]
        if trusted:
            runs, cur = [], [trusted[0]]
            for c in trusted[1:]:
                if c == cur[-1] + 1:
                    cur.append(c)
                else:
                    runs.append(cur)
                    cur = [c]
            runs.append(cur)
            best = max(runs, key=len)
            seed = best[len(best) // 2]
    if seed not in trusted:
        trusted = [seed]
    rowy, asg, extra = [None] * n, [None] * n, [[] for _ in range(n)]
    for c in trusted:
        ys = ys_of[c]
        if len(ys) == nrows:
            rowy[c], asg[c] = ys, list(range(nrows))
        else:                                           # 起点の数が合わない (--rows を渡したとき)
            ref = np.linspace(ys[0], ys[-1], nrows) if len(ys) > 1 else np.full(nrows, ys[0] if len(ys) else 0.)
            a, ex = link(ys, ref, pitch, 0.)
            rowy[c], asg[c], extra[c] = fill_rows(ys, a, ref, 0.), a, ex
    while any(r is None for r in rowy):                 # 決まった列の隣へ順につなぐ
        for c in range(n):
            if rowy[c] is not None:
                continue
            ps = [p for p in (c - 1, c + 1) if 0 <= p < n and rowy[p] is not None]
            if not ps:
                continue
            ys = ys_of[c]
            best = None
            for p in ps:
                d0 = shift(ys, rowy[p], pitch)
                a, ex = link(ys, rowy[p], pitch, d0)
                score = a.count(-1) + len(ex)
                if best is None or score < best[0]:
                    best = (score, a, ex, rowy[p], d0)
            _, a, ex, ref, d0 = best
            rowy[c], asg[c], extra[c] = fill_rows(ys, a, ref, d0), a, ex
    return nrows, seed, rowy, asg, extra


def match_rows(typed, image, skip=None):
    """転記の行と画像の行を，値の有無が全体で最も合うように順に対応づける．(転記の行, 画像の行) の組の並び"""
    r_n, g_n = len(typed), len(image)
    if r_n == g_n:
        return [(k, k) for k in range(r_n)]
    n = len(typed[0]) if typed else 1
    skip = skip if skip is not None else max(2.0, .15 * n)
    t, g = np.array(typed, bool).reshape(r_n, -1), np.array(image, bool).reshape(g_n, -1)
    costs = (t[:, None, :] != g[None, :, :]).sum(axis=2)
    best = np.zeros((r_n + 1, g_n + 1))
    best[:, 0] = np.arange(r_n + 1) * skip
    best[0, :] = np.arange(g_n + 1) * skip
    for r in range(1, r_n + 1):
        for k in range(1, g_n + 1):
            best[r, k] = min(best[r - 1, k - 1] + costs[r - 1, k - 1], best[r - 1, k] + skip, best[r, k - 1] + skip)
    r, k, pairs = r_n, g_n, []
    while r > 0 and k > 0:
        if abs(best[r, k] - best[r - 1, k - 1] - costs[r - 1, k - 1]) < 1e-9:
            pairs.append((r - 1, k - 1))
            r, k = r - 1, k - 1
        elif abs(best[r, k] - best[r - 1, k] - skip) < 1e-9:
            r -= 1
        else:
            k -= 1
    return pairs[::-1]


# ---- 画像の書き出し ----

def font(size=16):
    try:
        return ImageFont.truetype('arial.ttf', size)
    except OSError:
        return ImageFont.load_default()


def ascii_label(s):
    return s.replace('・', '.').encode('ascii', 'replace').decode()


def diff_sheets(src, items, cols, pitch_y, path, per=48, ncol=6):
    """食い違いのセルを，上下 1 行ずつを含めて切り出して並べる．items は (列, y, 札)"""
    tw, th = int(2.2 * cols.pitch), int(3.2 * pitch_y)
    f = font(14)
    stem, ext = os.path.splitext(path)
    paths = []
    for s in range(0, len(items), per):
        part = items[s:s + per]
        rows = (len(part) + ncol - 1) // ncol
        sheet = Image.new('RGB', (ncol * (tw + 6), rows * (th + 22)), 'white')
        d = ImageDraw.Draw(sheet)
        for i, (c, y, label) in enumerate(part):
            x = float(cols.at(y)[0, c])
            cell = src.crop((int(x - tw / 2), int(y - th / 2), int(x - tw / 2) + tw, int(y - th / 2) + th)).convert('RGB')
            ox, oy = (i % ncol) * (tw + 6), (i // ncol) * (th + 22)
            sheet.paste(cell, (ox, oy + 20))
            d.rectangle([ox + tw * .25, oy + 20 + th / 2 - pitch_y * .55, ox + tw * .75, oy + 20 + th / 2 + pitch_y * .55],
                        outline=(255, 0, 0), width=2)
            d.text((ox + 2, oy + 2), ascii_label(label), fill=(0, 0, 255), font=f)
        out = path if len(items) <= per else f'{stem}_{s // per + 1:02d}{ext}'
        sheet.save(out)
        paths.append(out)
    return paths


def band_image(src, rowy, asg, cols, pitch_y, k0, k1, c0, c1, label, path, scale=1.0, const=()):
    """画像の行 k0..k1 (1 始まり) を，列ごとの行の y で切って横にそろえる．印の当たらないセルは赤い枠．
    常在度の列は値が右へ伸びるので，広めに切る"""
    H, P = int(pitch_y * 1.05), int(cols.pitch)
    LW = (label[1] - label[0]) if label else 0
    f = font(16)
    cl = list(range(c0, c1 + 1))
    widths = {c: int(P * 1.7) if c in const else P for c in cl}
    left = {c: P // 2 for c in cl}
    starts, pos = {}, 50 + LW
    for c in cl:
        starts[c] = pos
        pos += widths[c]
    W = pos + 50
    can = Image.new('RGB', (W, 26 + (k1 - k0 + 1) * H), 'white')
    d = ImageDraw.Draw(can)
    for c in cl:
        d.text((starts[c] + P // 2 - 8, 4), str(c + 1), fill=(0, 0, 255), font=f)
    for j, k in enumerate(range(k0 - 1, k1)):
        yy = 26 + j * H
        d.text((4, yy + H // 2 - 8), str(k + 1), fill=(255, 0, 0), font=f)
        if label:
            y = rowy[0][k]
            can.paste(src.crop((label[0], int(y - H / 2), label[1], int(y - H / 2) + H)).convert('RGB'), (50, yy))
        for c in cl:
            y = rowy[c][k]
            x = float(cols.at(y)[0, c])
            xx, cw = starts[c], widths[c]
            can.paste(src.crop((int(x - left[c]), int(y - H / 2), int(x - left[c]) + cw, int(y - H / 2) + H)).convert('RGB'), (xx, yy))
            d.line([(xx, yy), (xx, yy + H - 1)], fill=(170, 200, 255))
            if asg[c][k] < 0:
                d.rectangle([xx + 1, yy + 1, xx + cw - 2, yy + H - 2], outline=(255, 0, 0), width=2)
        d.line([(0, yy + H - 1), (W, yy + H - 1)], fill=(225, 225, 225))
    if scale != 1:
        can = can.resize((int(can.width * scale), int(can.height * scale)), Image.LANCZOS)
    can.save(path)
    return can.size


# ---- 本体 ----

def save_col_x(path, table, page, xs):
    """測った列の中心 x を col_x.tsv (列: table page plot x) に書く．同じ表・ページの行は置き換える．
    確認の HTML (review_html.py) が切り出し・地点番号の青字・赤枠の点検に使う (2026-11-08．列が等間隔でない表のため)"""
    rows = []
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            rows = [l.rstrip('\r\n').split('\t') for l in f if l.strip()][1:]
    rows = [r for r in rows if not (r[0] == table and r[1] == page)]
    rows += [[table, page, str(k + 1), f'{x:.0f}'] for k, x in enumerate(xs)]
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('table\tpage\tplot\tx\n' + ''.join('\t'.join(r) + '\n' for r in rows))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('image')
    ap.add_argument('out')
    ap.add_argument('table', help='表の名前 (Tab.9 など)')
    ap.add_argument('--box', type=int, nargs=4, required=True, metavar=('X0', 'Y0', 'X1', 'Y1'), help='値の列の範囲 (原寸)')
    ap.add_argument('--centers', type=float, nargs='+', help='全列の中心の x (省くと点の投影で測る)')
    ap.add_argument('--const', type=int, nargs='*', help='常在度の列 (1 始まり．省くと転記から見分ける)')
    ap.add_argument('--rows', type=int, help='画像の行の数 (省くと列ごとの印の数の最頻値)')
    ap.add_argument('--seed', type=int, help='起点の列 (1 始まり)')
    ap.add_argument('--threshold', type=int, default=128, help='これより暗い画素を字とみる')
    ap.add_argument('--rule', type=int, default=60, help='これ以上続く縦・横の線を罫線として消す (px)')
    ap.add_argument('--min-area', type=int, default=8, help='これより小さいかたまりを捨てる (よごれ)')
    ap.add_argument('--dot-min', type=int, default=3, help='点の幅・高さの下限')
    ap.add_argument('--dot-max', type=int, default=16, help='点の幅・高さの上限')
    ap.add_argument('--dot-fill', type=float, default=.5, help='点の充填率の下限 (中部 Tab.57 は 0.56)')
    ap.add_argument('--speck', type=float, default=.45, help='点の面積の中央値のこの割合より小さいかたまりをよごれとして捨てる')
    ap.add_argument('--thin', type=int, default=5, help='この太さ以下の細長いかたまりを線の切れとみる')
    ap.add_argument('--max-h', type=int, default=45, help='これより高いかたまりを捨てる')
    ap.add_argument('--limit', type=int, default=200, help='食い違いを表示する上限')
    ap.add_argument('--tsv', help='行 x 列の印の表を書く')
    ap.add_argument('--diff-png', help='食い違いのセルを切り出して並べた画像を書く')
    ap.add_argument('--band', type=int, nargs=2, metavar=('K0', 'K1'), help='帯の画像にする画像の行 (1 始まり)')
    ap.add_argument('--band-cols', type=int, nargs=2, metavar=('C0', 'C1'), help='帯の画像の列 (1 始まり．既定は全列)')
    ap.add_argument('--band-png', help='帯の画像の出力先')
    ap.add_argument('--label', type=int, nargs=2, metavar=('X0', 'X1'), help='帯の画像の左に貼る範囲 (和名と階層の x)')
    ap.add_argument('--scale', type=float, default=1.0, help='帯の画像の縮小率')
    ap.add_argument('--merge-split', action='store_true',
                    help='1 つの印字の行を階層ごとに分けた転記 (note に「印字は B1,B2,S」・名前の無い続きの行) を 1 行にまとめて照合する')
    ap.add_argument('--merge-rows', nargs='+', default=[], metavar='K0-K1',
                    help='1 行にまとめて照合する転記の種の行 (1 始まり．括弧の中の種を分けた行など．例: 12-13 40-42)')
    ap.add_argument('--shear', type=float, default=0.0,
                    help='行の傾き: --box の右端で行が左端より何 px 下がるか (右下がりは正)．印の y を補正して格子を作る')
    a = ap.parse_args(argv)

    names, vals, n, layers, notes = read_rows(os.path.join(a.out, 'transcripts', table_dir(a.table), 'body.tsv'))
    if a.merge_split or a.merge_rows:
        manual = []
        for s in a.merge_rows:
            lo, _, hi = s.partition('-')
            manual.append(list(range(int(lo) - 1, int(hi or lo))))
        groups = split_groups(layers, notes, manual) if a.merge_split else sorted(manual)
        if groups:
            names, vals, _ = merge_split(names, vals, groups)
            print(f'分けた行をまとめた: {len(groups)} 組 ' + ' '.join(f'{g[0] + 1}-{g[-1] + 1}' for g in groups[:12])
                  + (' …' if len(groups) > 12 else ''))
    if not n:
        sys.exit('body.tsv の見出しに地点の列 (1, 2, …) が無い')
    if not vals:
        print('body.tsv に種の行が無い．照合はせず，行の格子と画像だけを作る')
    const = {c - 1 for c in a.const} if a.const is not None else const_columns(vals)
    box = tuple(a.box)
    comps = components(a.image, box, a.threshold, a.rule, a.min_area)
    if not len(comps):
        sys.exit('--box の中に字が無い')
    width = max(1, box[2] - box[0])

    def tilt(x):                                        # 行の傾きで下がる量 (右下がりは正)
        return a.shear * (np.asarray(x, float) - box[0]) / width
    if a.shear:                                         # 印の y を左端の高さにそろえる (出力では元の y に戻す)
        off = tilt(comps[:, 0])
        comps[:, 1] -= off
        comps[:, 8] -= off
        comps[:, 9] -= off
        print(f'行の傾きを補正した: 右端で {a.shear:+.0f} px')
    dots = comps[[is_dot(q, a) for q in comps]]
    a.speck_area = a.speck * (float(np.median(dots[:, 4])) if len(dots) else 0)
    if a.centers:
        if len(a.centers) != n:
            sys.exit(f'--centers は {len(a.centers)} 個．地点は {n}')
        base, how = sorted(a.centers), '引数'
    else:
        base, how = pick_columns(dots[:, 0], n, box[0], box[2])
        if base is None:
            sys.exit(f'点の山が {n} 列に足りない．--centers で全列の x を渡す (点 {len(dots)} 個)')
    cols = Columns(base, dots, box[1], box[3])
    gaps = np.diff(cols.base)
    print(f'列の中心 ({how}): {n} 列．第 1 列 x={cols.base[0]:.0f}・最後 x={cols.base[-1]:.0f}．'
          f'間隔 {gaps.min():.0f}-{gaps.max():.0f} (中央値 {cols.pitch:.1f})' if len(gaps) else f'列の中心: x={cols.base[0]:.0f}')
    if not a.centers:
        print('  x: ' + ' '.join(f'{v:.0f}' for v in cols.base))
    save_col_x(os.path.join(a.out, 'col_x.tsv'), a.table, os.path.splitext(os.path.basename(a.image))[0], cols.base)
    if const:
        print('常在度の列: ' + ' '.join(str(c + 1) for c in sorted(const)))
    col = assign_columns(comps, cols, const, a)
    pitch_y = row_pitch(group_marks(comps, col, n, 8, a))
    marks = group_marks(comps, col, n, .4 * pitch_y, a)
    pitch_y = row_pitch(marks)
    nrows, seed, rowy, asg, extra = build_grid(marks, pitch_y, a.rows, a.seed - 1 if a.seed else None)
    keep = [k for k in range(nrows) if sum(asg[c][k] >= 0 for c in range(n)) >= .3 * n]
    if len(keep) < nrows:                               # 起点の列のよごれで作った行
        print(f'印の当たる列が 3 割に満たない行を除いた: {[k + 1 for k in range(nrows) if k not in keep]}')
        for c in range(n):
            extra[c] = sorted(extra[c] + [asg[c][k] for k in range(nrows) if k not in keep and asg[c][k] >= 0])
        rowy = [r[keep] for r in rowy]
        asg = [[s[k] for k in keep] for s in asg]
        nrows = len(keep)
    if a.shear:                                         # 行の y を画像の元の高さに戻す (列ごとに列の x で)
        rowy = [np.asarray(r, float) + float(tilt(cols.base[c])) for c, r in enumerate(rowy)]
    counts = [len(ms) for ms in marks]
    print(f'行の間隔 {pitch_y:.1f} px．画像の行 {nrows}・転記の種の行 {len(vals)}．起点の列 {seed + 1}．'
          f'印の数が行と合う列 {sum(k == nrows for k in counts)} / {n}')
    for c in range(n):
        miss = [k + 1 for k in range(nrows) if asg[c][k] < 0]
        if miss or extra[c]:
            ex = [round(marks[c][i][0]) for i in extra[c]]
            print(f'  列 {c + 1}: 印 {counts[c]}．印の無い行 {miss[:12]}{" …" if len(miss) > 12 else ""}'
                  f'・余りの印 y={ex[:8]}{" …" if len(ex) > 8 else ""}')
    image = [[asg[c][k] >= 0 and marks[c][asg[c][k]][1] == 'v' for c in range(n)] for k in range(nrows)]
    typed = [[has_value(v) for v in row] for row in vals]
    pairs = match_rows(typed, image) if typed else []
    done_r, done_k = {r for r, _ in pairs}, {k for _, k in pairs}
    lost_r = [names[r] for r in range(len(vals)) if r not in done_r]
    lost_k = [k + 1 for k in range(nrows) if k not in done_k]
    print(f'対応した行 {len(pairs)}．転記だけの行 {len(lost_r)} {lost_r[:8]}・画像だけの行 {len(lost_k)} {lost_k[:8]}')

    diffs = []
    for r, k in pairs:
        for c in range(n):
            if typed[r][c] == image[k][c]:
                continue
            y = rowy[c][k]
            x = float(cols.at(y)[0, c])
            if image[k][c]:
                diffs.append((r, k, c, f'[画像に値] {names[r]}: 地点 {c + 1} 転記 {vals[r][c] or "空"} (行 {k + 1}・x={x:.0f} y={y:.0f})'))
            else:
                what = '点' if asg[c][k] >= 0 else '印なし'
                diffs.append((r, k, c, f'[転記に値] {names[r]}: 地点 {c + 1} 転記 {vals[r][c]}・画像は{what} (行 {k + 1}・x={x:.0f} y={y:.0f})'))
    for *_, msg in diffs[:a.limit]:
        print(msg)
    if len(diffs) > a.limit:
        print(f'… ほか {len(diffs) - a.limit} 件 (--limit で増やす)')
    n_img = sum(m.startswith('[画像に値]') for *_, m in diffs)
    print(f'食い違い {len(diffs)} セル / {len(pairs) * n} セル (画像に値 {n_img}・転記に値 {len(diffs) - n_img})')
    if diffs:
        print('食い違いの多い行:', [(names[r], k) for r, k in collections.Counter(d[0] for d in diffs).most_common(5)])
        print('食い違いの多い列:', collections.Counter(d[2] + 1 for d in diffs).most_common(5))

    if a.tsv:
        back = {k: r for r, k in pairs}
        with open(a.tsv, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, delimiter='\t', lineterminator='\n')
            w.writerow(['row', 'species'] + [str(c + 1) for c in range(n)] + ['y_first', 'y_last'])
            for k in range(nrows):
                cells = [marks[c][asg[c][k]][1] if asg[c][k] >= 0 else '_' for c in range(n)]
                w.writerow([k + 1, names[back[k]] if k in back else ''] + cells + [round(rowy[0][k]), round(rowy[-1][k])])
        print(f'印の表: {a.tsv}')
    src = None
    if a.diff_png and diffs:
        src = Image.open(a.image).convert('L')
        items = [(c, rowy[c][k], f'r{k + 1} c{c + 1} t={vals[r][c] or "-"}') for r, k, c, _ in diffs]
        for p in diff_sheets(src, items, cols, pitch_y, a.diff_png):
            print(f'食い違いの画像: {p}')
    if a.band:
        if not a.band_png:
            sys.exit('--band には --band-png が要る')
        src = src or Image.open(a.image).convert('L')
        k0, k1 = max(1, a.band[0]), min(nrows, a.band[1])
        c0, c1 = (a.band_cols[0] - 1, a.band_cols[1] - 1) if a.band_cols else (0, n - 1)
        size = band_image(src, rowy, asg, cols, pitch_y, k0, k1, c0, c1, a.label, a.band_png, a.scale, const)
        print(f'帯の画像: {a.band_png} {size}')
    print('(画像で確かめる．転記は書き換えていない)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
