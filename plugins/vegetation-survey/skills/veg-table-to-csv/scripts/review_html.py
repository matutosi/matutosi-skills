"""値や名前の確認用に，赤い印つきの画像を埋め込んだ 1 枚の HTML を作る．

    python scripts/review_html.py <項目.json> <出力.html> [--title 題] [--region 地方名] [--choices val,none,skip]
    python scripts/review_html.py <置き場>/user_review.tsv <出力.html>   # 読みながら積んだ項目から作る

`--split` を付けると，区分ごとに review_A.html〜review_D.html に分ける (out は置き場のディレクトリ)．
区分は kind の頭の記号 (`A. 読めない値` など) か，kind の語で決まる:
A 値の読み (読めない値・常在度の値) / B 下線・階層・種名 / C 行と種の割り当て (推定の割り当て・印字の重複・
見出しの欠け・出現種数) / D 表頭と注記．A の項目は「今の転記でよい・値を入力・値の印字は無い」で答える．

任意の列 `current` に今の転記の値 (例: `K +・2`) を書くと，選択肢が「今の転記 (K +・2) でよい」になる．
赤枠の行 (j_name) と列 (地点 plot) は画像の余白に青字で書く．`--head-rows <tsv> --head-region <地方>` で
表頭の通し番号の行の位置 (列: region table page y0 y1 note) を渡すと，その行を画像の上に貼る．

user_review.tsv の列: table plot j_name kind what page x0 y0 x1 y1 (座標はページ画像の原寸．page は
work/ のページ名か画像のパス．置き場からの相対)．範囲を赤枠で囲み，周りを広げて切る．

サーバは要らない．できた HTML をブラウザで開き，回答を JSON で保存してもらう．
`review.py` (サーバ版．名前の直しを転記へ反映する) と違い，**値の確認など 1 回きりの質問**向け．

項目.json は次の形のリスト:

    [{"id": "K01", "title": "Tab.16 地点 16 イトスゲ", "layer": "K",
      "meta": "Carex fernaldiana ／ 1 回出現の段落 ／ 転記の暫定値: ?",
      "note": "段落 in 16: の最後の語．K の後に値が無く句点だけ",
      "images": [
         {"page": "work/kinki_005.png", "crop": [700, 60, 1900, 200],
          "caption": "1 回出現の段落",
          "marks": [{"box": [772, 100, 858, 128]},
                    {"underline": [860, 882, 130]}]}]}]

- 画像は `page` (ページ画像) と `crop` (切り出す範囲 x0,y0,x1,y1) で指す．
  `marks` の座標は**ページ画像の座標**で書く (切り出しの分は自動でずらす)．
  切り出し済みの画像を使うなら `image` に書き，`marks` はその画像の座標にする．
  表全体のような大きな範囲は `"scale": 0.25` のように縮めて埋め込む (印は縮める前の座標で書く)．
- **何行目がどの種か・何列目がどの地点かを必ず示す**．いちばん手軽なのは，同じページの種名の列と表頭の通し番号の行を
  貼り合わせること: `"names_x": [x0, x1]` (種名の列の左右) と `"head_y": [y0, y1]` (通し番号の行の上下) を書くと，
  切り出しと同じ高さの種名の列が左に，同じ幅の通し番号の行が上に付く (表ごとに 1 回測れば，全項目に使える．
  行が右ほど傾く表では，傾きのぶんだけずれるので，そのときは rows・cols を使う)．
  座標で書くとき: 種名や表頭の通し番号が写らない切り出しには
  `"rows": [[y, "ナナカマド K"], …]` と `"cols": [[x, "46"], …]` (ページの原寸の座標) を書く．
  行の名は左の余白に，地点番号は上の余白に青で書き込まれる (赤は確かめてほしい箇所，青は位置の目印)．
- **階層の下線が判断の材料になる項目** (下線の対応・階層の印字) は，階層の列 (字と下線) が画像に写るようにする．
  切り出しが階層の列を含まないときは `"layer_x": [x0, x1]` (階層の列の左右．ページ原寸) を書くと，切り出しと同じ高さの
  階層の列が左に付く (`names_x` もあれば，その右に続けて貼る)．範囲が切り出しの中にあれば貼らない．
  user_review.tsv では任意の列 `layer_x0`・`layer_x1` に書く．
- `marks` の種類 (赤で描く):
  - `{"box": [x0, y0, x1, y1]}` 対象の語やセルを囲む枠
  - `{"underline": [x0, x1, y]}` 値を入れる位置の下線と ▼ (値が無いところを指すとき)
  - `{"arrow": [x, y]}` その点を指す ▼
- 画像の相対パスは項目.json のあるディレクトリから見る．
- 選択肢は項目ごとに `options` で決める: `[{"value": "a", "label": "…", "input": false}, …]`．
  `input` が true の選択肢には入力欄が付く．`判断できない` (skip) は自動で足す．
  `options` が無い項目は `val` (値を入力)・`none` (印字に無い)・`skip` (`--choices` で選ぶ)．
  user_review.tsv から作る項目は a. 今の転記でよい・b. 違う (メモに)．
  欄の入力は自動で端末ではなくブラウザの localStorage に保存され，閉じても残る．
  「回答を JSON で保存」ボタンで `{id: {choice, value, memo}}` が落ちる．ファイル名は `<地方名>_review_answers.json`
  (`--region kanto` なら `kanto_review_answers.json`．`--region` を省くと出力 HTML の名前 (`okinawa.html` → `okinawa`) から
  決める．地方ごとの HTML の回答がダウンロードフォルダで同じ名前にならないように．2026-11-05)．
  「回答を読み込む」はファイル名を見ないので，どの名前の JSON でも読める．

標準ライブラリと Pillow だけで動く．
"""
import argparse
import base64
import collections
import glob
import html
import io
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None
RED = (220, 0, 0)
MARGIN = 20
LABELS = {'val': '値を入力:', 'none': '印字に値が無い (出現のみ・値は空)', 'skip': '判断できない (そのまま)'}


def draw_marks(im, marks, dx, dy):
    """im (切り出し後) に赤い印を描く．marks は元の座標，(dx, dy) は切り出しの左上"""
    d = ImageDraw.Draw(im)
    for m in marks:
        if 'box' in m:
            x0, y0, x1, y1 = m['box']
            d.rectangle((x0 - dx, y0 - dy, x1 - dx, y1 - dy), outline=RED, width=3)
        if 'underline' in m:
            x0, x1, y = m['underline']
            d.line((x0 - dx, y - dy, x1 - dx, y - dy), fill=RED, width=4)
            _arrow(d, (x0 + x1) / 2 - dx, y - dy + 4)
        if 'arrow' in m:
            x, y = m['arrow']
            _arrow(d, x - dx, y - dy)


BLUE = (0, 70, 200)
FONTS = ('YuGothM.ttc', 'meiryo.ttc', 'msgothic.ttc', 'NotoSansCJK-Regular.ttc', 'DejaVuSans.ttf')


def _font(size):
    for name in FONTS:
        for d in ('', 'C:/Windows/Fonts/', '/usr/share/fonts/opentype/noto/', '/System/Library/Fonts/'):
            try:
                return ImageFont.truetype(d + name, size)
            except OSError:
                continue
    return ImageFont.load_default()


def parse_plots(text):
    """'6,9-12,14' や '8?,17' を地点番号のリストにする．数でない字があれば []"""
    out = []
    for part in re.split(r'[,，、・ ]+', text.strip()):
        part = part.strip().rstrip('?？')
        if not part:
            continue
        m = re.fullmatch(r'(\d+)(?:[-–〜~](\d+))?', part)
        if not m:
            return []
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        out += list(range(a, b + 1))
    return sorted(set(out))


def _projection(page, x0, x1, y0, y1):
    """x0〜x1 の縦の投影 (黒の数)．縦の罫線 (長い縦の連なり) と横の線 (行の半分を超える黒) は除く"""
    im = page.crop((x0, y0, x1, y1)).convert('L')
    w, h = im.size
    px = im.load()
    dark = [[px[x, y] < 128 for x in range(w)] for y in range(h)]
    rows_ok = [sum(r) < w * 0.5 for r in dark]
    proj = [0] * w
    for x in range(w):
        run = best = s = 0
        for y in range(h):
            if dark[y][x] and rows_ok[y]:
                run += 1
                s += 1
                best = max(best, run)
            else:
                run = 0
        proj[x] = 0 if best > 40 else s
    return proj


def column_centers(page, x0, x1, y0, y1, n):
    """ページ画像の x0〜x1 (赤枠の左右) にある n 本の列の中心 x を，字と点の縦の投影の山から測る．
    縦の罫線と横の線は除く．山の位置は窓の中の黒の重心で取る．列の間隔が不ぞろいなら当てにせず None"""
    if n < 2 or x1 - x0 < n * 8:
        return None
    proj = _projection(page, x0, x1, y0, y1)
    w = len(proj)
    sp = w / n
    k = max(1, int(sp / 6))
    sm = [sum(proj[max(0, i - k):i + k + 1]) for i in range(w)]
    peaks = []
    for i in sorted(range(w), key=lambda i: -sm[i]):
        if sm[i] <= 0 or len(peaks) >= n:
            break
        if all(abs(i - p) >= 0.6 * sp for p in peaks):
            peaks.append(i)
    if len(peaks) != n:
        return None
    out = []
    for p in sorted(peaks):                                  # 平らな頂上の端でなく，窓の中の黒の重心
        lo, hi = max(0, p - k), min(w, p + k + 1)
        tot = sum(proj[lo:hi])
        out.append(round(sum(x * proj[x] for x in range(lo, hi)) / tot) if tot else p)
    gaps = [b - a for a, b in zip(out, out[1:])]
    med = sorted(gaps)[len(gaps) // 2]
    if any(g < 0.6 * med or g > 1.6 * med for g in gaps):    # 列の間隔が不ぞろいなら当てにしない
        return None
    return [x0 + p for p in out]


def plot_cols(base, page_rel, box, crop, plot_text):
    """赤枠の列に地点番号を振る．複数の地点 (23,27 や 10-14) なら赤枠の中の列を測り，
    最小〜最大の番号を左から振る．測れなければ赤枠の中央に地点の文字列をまとめて書く"""
    x0, y0, x1, y1 = box
    plots = parse_plots(plot_text)
    if len(plots) >= 2:
        try:
            page = load_page(base, page_rel)
        except OSError:
            page = None
        # 赤枠が最小〜最大の地点を囲む形と，行全体 (地点 1 から) を囲む形を順に試す
        for first in dict.fromkeys((plots[0], 1)):
            n = plots[-1] - first + 1
            cs = page and column_centers(page, x0, x1, max(crop[1], 0), min(crop[3], page.height), n)
            if cs:
                return [[c, str(first + i)] for i, c in enumerate(cs)], True
    return [[(x0 + x1) // 2, f'地点 {plot_text}']], False


def plot_x_map(page, head_y, n, band, xr=None):
    """表頭の通し番号の行 (head_y = [y0, y1]) の数字のかたまりから，地点 1〜n の列の中心 x を {地点: x} で返す．
    等間隔に並ぶかたまりのうち，項目の行のあたり (band = [y0, y1]) に点や値が並ぶ n 本を地点の列とみる
    (同じページの別の表や項目名の字を除くため)．xr = [x0, x1] があれば，その左右の範囲 (その表) だけで探す
    (同じ高さに別の表が並ぶページで，隣の表の番号を拾わないため)．決まらなければ None"""
    y0, y1 = head_y
    ox = max(0, int(xr[0])) if xr else 0
    page = page.crop((ox, 0, min(page.width, int(xr[1])), page.height)) if xr else page
    strip = page.crop((0, y0, page.width, y1)).convert('L')
    w, h = strip.size
    px = strip.load()
    proj = [sum(1 for y in range(h) if px[x, y] < 128) for x in range(w)]
    segs, start = [], None
    for x, v in enumerate(proj + [0]):
        if v and start is None:
            start = x
        elif not v and start is not None:
            segs.append([start, x - 1])
            start = None
    merged = []
    for s in segs:                                   # 字の中の切れ目はつなぐ
        if merged and s[0] - merged[-1][1] < 8:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    gaps = sorted(b[0] - a[1] for a, b in zip(merged, merged[1:]))
    if not gaps:
        return None
    big = gaps[len(gaps) // 2]
    cl = []
    for s in merged:                                 # 2 桁・3 桁の数字はつなぐ
        if cl and s[0] - cl[-1][1] < max(10, 0.35 * big):
            cl[-1][1] = s[1]
        else:
            cl.append(list(s))
    cs = [(a + b) // 2 for a, b in cl]
    d = [b - a for a, b in zip(cs, cs[1:])]
    if not d:
        return None
    sp = sorted(d)[len(d) // 2]
    runs, cur = [], [cs[0]]                          # 等間隔に並ぶかたまりの続き
    for k, g in enumerate(d):
        if 0.7 * sp <= g <= 1.4 * sp:
            cur.append(cs[k + 1])
        else:
            runs.append(cur)
            cur = [cs[k + 1]]
    runs.append(cur)
    body = page.crop((0, max(0, band[0]), page.width, min(page.height, band[1]))).convert('L')
    bw, bh = body.size
    bp = body.load()

    def ink(x):
        return sum(1 for xx in range(max(0, x - 12), min(bw, x + 13)) for y in range(0, bh, 2) if bp[xx, y] < 128)
    best = None
    for run in runs:
        if len(run) < n:
            continue
        for k in range(len(run) - n + 1):
            win = run[k:k + n]
            score = sum(ink(x) for x in win)
            if best is None or score > best[0]:
                best = (score, win)
    if not best:
        return None
    return {p + 1: x + ox for p, x in enumerate(best[1])}


WARNINGS = []
_COLX = {}


def table_key(table):
    """Tab.9 と Tab.009 をそろえる"""
    m = re.search(r'\d+', table or '')
    return f'Tab.{int(m.group())}' if m else table


def load_col_x(base):
    """置き場の col_x.tsv (列: table page plot x．marks_grid.py が書く) を {(表, ページ): {地点: x}} で返す．無ければ {}"""
    if base not in _COLX:
        out = {}
        p = os.path.join(base, 'col_x.tsv')
        if os.path.exists(p):
            import csv
            with open(p, encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f, delimiter='\t'):
                    out.setdefault((table_key(r['table']), r['page']), {})[int(r['plot'])] = int(float(r['x']))
        _COLX[base] = out
    return _COLX[base]


def box_off_column(xmap, plots, box):
    """赤枠の左右の範囲に，確かめる地点の列の中心が入っていなければ，ずれの説明を返す (入っていれば None)"""
    if not xmap or not plots:
        return None
    xs = [xmap[p] for p in plots if p in xmap]
    if not xs:
        return None
    n = max(xmap)
    sp = (xmap[n] - xmap[min(xmap)]) / max(1, n - min(xmap))
    out = [x for x in xs if not (box[0] - 0.3 * sp <= x <= box[2] + 0.3 * sp)]
    if not out:
        return None
    near = min(xmap, key=lambda p: abs(xmap[p] - (box[0] + box[2]) / 2))
    return f'赤枠 (x {box[0]}-{box[2]}) に地点の列 (x {", ".join(map(str, out))}) が入っていない．赤枠の中央はおよそ地点 {near} の列'


def n_plots_of(base, table):
    """置き場の transcripts/Tab.NNN/body.tsv の見出しにある地点の列の数．無ければ 0"""
    p = os.path.join(base, 'transcripts', 'Tab.%03d' % int(re.sub(r'\D', '', table) or 0), 'body.tsv')
    if not os.path.exists(p):
        return 0
    with open(p, encoding='utf-8') as f:
        return sum(1 for c in f.readline().rstrip('\r\n').split('\t') if c.strip().isdigit())


def narrow_crop(crop, xmap, plots, around=2, box=None):
    """確かめる地点 (plots) とその前後 around 地点だけが入るように，切り出しの左右を狭める．
    狭められないとき (地点が表に無い・もとより狭い・測った地点の x が赤枠 box の外) は crop を返す．
    列の間隔が不ぞろいな表 (常在度の列が混じるなど) では当てはめが外れることがあるので，box で確かめる (中部 80)"""
    if not xmap or not plots:
        return crop
    n = max(xmap)
    lo, hi = max(1, min(plots) - around), min(n, max(plots) + around)
    if lo not in xmap or hi not in xmap or min(plots) not in xmap or max(plots) not in xmap:
        return crop
    sp = (xmap[n] - xmap[1]) / max(1, n - 1)
    if box and not (box[0] - sp <= xmap[min(plots)] and xmap[max(plots)] <= box[2] + sp):
        return crop
    x0, x1 = int(xmap[lo] - 0.7 * sp), int(xmap[hi] + 0.7 * sp)
    if x1 - x0 >= crop[2] - crop[0]:
        return crop
    if box and (box[0] < x0 - sp or box[2] > x1 + sp):
        return crop      # 赤枠が狭めた範囲からはみ出す (段落や行を囲んだ) ときは狭めない (2026-11-09．中国 U86)
    return [max(0, x0), crop[1], x1, crop[3]]


def page_path(base, rel):
    """ページ画像の場所．無ければ同じ置き場の work_* を探す (近畿の小古は work_sho．0.5.14)"""
    path = os.path.join(base, rel)
    if not os.path.exists(path):
        alt = sorted(glob.glob(os.path.join(os.path.dirname(os.path.dirname(path)), 'work*', os.path.basename(path))))
        path = alt[0] if alt else path
    return path


_PAGES = collections.OrderedDict()
PAGE_CACHE = 2     # ページ画像は 1 枚 2 億画素ほど (グレーで約 200 MB) あるので，覚えておくのは直近の 2 枚だけ


def load_page(base, rel):
    """ページ画像を読み込んで返す (直近の PAGE_CACHE 枚は使い回す)．RGB への変換は切り出してから呼び手が行う．
    項目ごとにページ全体を読み直して RGB にしていたのが遅さの元だった (2026-11-08．四国 173 項目で約 3 分)"""
    path = os.path.abspath(page_path(base, rel))
    im = _PAGES.pop(path, None)
    if im is None:
        im = Image.open(path)
        im.load()
    _PAGES[path] = im
    while len(_PAGES) > PAGE_CACHE:
        _PAGES.popitem(last=False)
    return im


def add_labels(canvas, rows, cols, dx, dy, size=28):
    """行 (種名) を左の余白に，列 (地点番号) を上の余白に青で書き，対応する行・列に細い補助線を引く．
    rows・cols は元の座標 [[y, 名前], …]・[[x, 番号], …]．(dx, dy) は canvas の左上の元の座標"""
    f = _font(size)
    lw = max([int(f.getlength(str(t))) for _, t in rows] + [0]) + (20 if rows else 0)
    th = size + 16 if cols else 0
    out = Image.new('RGB', (canvas.width + lw, canvas.height + th), 'white')
    out.paste(canvas, (lw, th))
    d = ImageDraw.Draw(out)
    for y, t in rows:
        yy = y - dy + th
        d.text((6, yy - size // 2), str(t), fill=BLUE, font=f)
        d.line((lw - 12, yy, lw - 2, yy), fill=BLUE, width=2)
    for x, t in cols:
        xx = x - dx + lw
        w = f.getlength(str(t))
        d.text((xx - w / 2, 4), str(t), fill=BLUE, font=f)
        d.line((xx, th - 8, xx, th), fill=BLUE, width=2)
    return out


def layer_strip_needed(spec):
    """layer_x (階層の列) を左に貼るか．範囲が切り出し (crop) の中にあれば貼らない"""
    lx = spec.get('layer_x')
    if not lx or 'page' not in spec:
        return False
    if 'crop' not in spec:
        return False
    return lx[0] < spec['crop'][0]


def add_strips(base, spec, canvas, dx, dy):
    """同じページから，種名の列 (names_x の範囲．切り出しと同じ高さ) と階層の列 (layer_x) を左に，表頭の通し番号の行
    (head_y の範囲．切り出しと同じ幅) を上に貼る．座標を読まずに，何行目がどの種か・何列目がどの地点か・
    階層の字に下線があるかが分かる"""
    page = load_page(base, spec['page'])
    left = top = None
    pieces = []
    if spec.get('names_x'):
        nx0, nx1 = spec['names_x']
        pieces.append(page.crop((nx0, dy, nx1, dy + canvas.height)).convert('RGB'))
    if layer_strip_needed(spec):
        lx0, lx1 = spec['layer_x']
        if pieces and spec['names_x'][1] > lx0:          # 種名の列と重なるぶんは除く
            lx0 = min(spec['names_x'][1], lx1 - 1)
        pieces.append(page.crop((lx0, dy, lx1, dy + canvas.height)).convert('RGB'))
    if pieces:
        left = Image.new('RGB', (sum(p.width for p in pieces), canvas.height), 'white')
        x = 0
        for p in pieces:
            left.paste(p, (x, 0))
            x += p.width
    if spec.get('head_y'):
        hy0, hy1 = spec['head_y']
        top = page.crop((dx, hy0, dx + canvas.width, hy1)).convert('RGB')
    lw = left.width + 8 if left else 0
    th = top.height + 8 if top else 0
    out = Image.new('RGB', (canvas.width + lw, canvas.height + th), 'white')
    out.paste(canvas, (lw, th))
    d = ImageDraw.Draw(out)
    if left:
        out.paste(left, (0, th))
        d.line((lw - 4, th, lw - 4, out.height), fill=BLUE, width=2)
    if top:
        out.paste(top, (lw, 0))
        d.line((lw, th - 4, out.width, th - 4), fill=BLUE, width=2)
    return out


def _arrow(d, x, y):
    d.polygon([(x - 8, y), (x + 8, y), (x, y + 12)], fill=RED)


def make_image(base, spec):
    """spec から (赤い印つき PNG の base64, 説明) を返す"""
    marks = spec.get('marks', [])
    if 'page' in spec:
        page = load_page(base, spec['page'])
        x0, y0, x1, y1 = spec['crop'] if 'crop' in spec else (0, 0, page.width, page.height)
        im = page.crop((x0, y0, x1, y1)).convert('RGB')      # 切り出してから RGB に (全体を変換しない)
        dx, dy = x0, y0
    else:
        im = Image.open(os.path.join(base, spec['image'])).convert('RGB')
        dx = dy = 0
    canvas = Image.new('RGB', (im.width + 2 * MARGIN, im.height + 2 * MARGIN), 'white')
    canvas.paste(im, (MARGIN, MARGIN))
    draw_marks(canvas, marks, dx - MARGIN, dy - MARGIN)
    ox, oy = dx - MARGIN, dy - MARGIN                 # canvas の左上の元の座標
    if 'page' in spec and (spec.get('names_x') or spec.get('head_y') or layer_strip_needed(spec)):
        w0, h0 = canvas.size
        canvas = add_strips(base, spec, canvas, ox, oy)
        ox, oy = ox - (canvas.width - w0), oy - (canvas.height - h0)   # 左・上に貼ったぶんずらす
    if spec.get('rows') or spec.get('cols'):          # 何行目がどの種か・何列目がどの地点かを書き込む
        canvas = add_labels(canvas, spec.get('rows', []), spec.get('cols', []), ox, oy)
    if spec.get('scale'):                             # 表全体など大きな範囲は縮めて埋め込む
        k = float(spec['scale'])
        canvas = canvas.resize((max(1, int(canvas.width * k)), max(1, int(canvas.height * k))), Image.LANCZOS)
    buf = io.BytesIO()
    canvas.save(buf, 'PNG')       # optimize=True は大きな画像で遅い (2026-11-08．画質は同じ)
    return base64.b64encode(buf.getvalue()).decode('ascii')


CONFIRM = [{'value': 'a', 'label': '今の転記でよい'},
           {'value': 'b', 'label': '違う (正しい読み・扱いをメモに)'}]
VALUE = [{'value': 'a', 'label': '今の転記でよい'},
         {'value': 'val', 'label': '値を入力', 'input': True},
         {'value': 'none', 'label': '値の印字は無い (出現なし)'}]
OPT_RE = re.compile(r'選択肢\s*(?:\(おすすめの?順\))?\s*[:：]\s*')
OPT_END = re.compile(r'(でよい|する|入力|のまま|まま|消す|直す|移す|残す|みる|とみる|分ける)\s*(\([^()]*\))?$')


def _split_top(s, sep):
    """括弧の外の sep で分ける"""
    out, depth, cur, i = [], 0, '', 0
    while i < len(s):
        c = s[i]
        depth += c in '(（'
        depth -= c in ')）'
        if depth == 0 and s.startswith(sep, i):
            out.append(cur.strip())
            cur = ''
            i += len(sep)
            continue
        cur += c
        i += 1
    out.append(cur.strip())
    return [x for x in out if x]


def _cut_tail(s):
    """括弧の外の最初の「．」で (前, 後ろ) に分ける"""
    depth = 0
    for i, c in enumerate(s):
        depth += c in '(（'
        depth -= c in ')）'
        if c == '．' and depth == 0:
            return s[:i].strip(), s[i + 1:].strip(' ．')
    return s.strip(), ''


CUR_END = re.compile(r'今の転記\s*\([^()]*\)$')


def _split_dot(text):
    """「A・B・C」を，括弧の外の「・」のうち直前が選択肢の終わり方 (〜でよい・〜とする・今の転記 (…) など) の所だけで分ける．
    値の「1・2」や「11・23」では分けない"""
    out, depth, cur = [], 0, ''
    for c in text:
        depth += c in '(（'
        depth -= c in ')）'
        if c == '・' and depth == 0 and (OPT_END.search(cur.strip()) or CUR_END.search(cur.strip())):
            out.append(cur.strip())
            cur = ''
            continue
        cur += c
    out.append(cur.strip())
    return [x for x in out if x]


def _labels(text):
    """「A / B / C」(なければ「A・B・C」) を選択肢の文のリストにする．選択肢らしくなければ []"""
    labs = _split_top(text, ' / ')
    if len(labs) < 2:
        labs = _split_dot(text)
        if len(labs) < 2:
            return []
    return labs


def options_from_what(what):
    """what に文で書いた選択肢 (「選択肢: A / B / C」．「選択肢:」が無く文末に「A / B」が並ぶ形も) を取り出す．
    返り値は (選択肢を除いた説明, 選択肢の文のリスト)．無ければ (what, [])．2026-11-08 ユーザ指示 (四国 U02)"""
    m = OPT_RE.search(what or '')
    if m:
        head, body = what[:m.start()].rstrip(' ．'), what[m.end():]
    else:
        k = (what or '').find(' / ')
        if k < 0:
            return what, []
        depth, start = 0, -1                     # 「/」の前の，括弧の外の最後の「．」から後ろを選択肢とみる
        for i, c in enumerate(what[:k]):
            depth += c in '(（'
            depth -= c in ')）'
            if c == '．' and depth == 0:
                start = i
        head, body = what[:start].rstrip(' ．') if start >= 0 else '', what[start + 1:]
    # 選択肢の頭の記号 (a: ・b) ・1) ・(2) ・A．) は付けない (2026-11-09 ユーザ指示．並べ替えて出すので記号はずれる)．
    # 「1)」の閉じ括弧が括弧の深さの数えを狂わせるので，分ける前に外す
    mark = r'[(（]?\s*(?:[a-hA-H]|[1-9])\s*[)）:：．.]\s*'
    body = re.sub(rf'(^\s*|\s/\s){mark}', r'\1', body)
    labs = _labels(body.strip().rstrip('．'))
    if not labs:
        return what, []
    labs = [re.sub(rf'^\s*{mark}', '', x) for x in labs]
    labs[-1], tail = _cut_tail(labs[-1])
    note = head + ('．' if head else '') + (tail + '．' if tail else '')
    return note, labs


def options_of(g, labels, current):
    """選択肢の文から options を作る．A は入力欄つきの「値を入力」が無ければ足す．
    「今の転記」の選択肢が無く current があれば足す"""
    opts = [{'value': 'abcdefgh'[j], 'label': lab, **({'input': True} if '入力' in lab else {})}
            for j, lab in enumerate(labels)]
    if current and not any(l.startswith('今の転記') for l in labels):
        opts.append({'value': 'cur', 'label': f'今の転記 ({current}) でよい'})
    if g == 'A' and not any(o.get('input') for o in opts):
        opts.append({'value': 'val', 'label': '値を入力', 'input': True})
    return opts


OPTION_WARNINGS = []
BARE_CURRENT = re.compile(r'^今の転記(?:のまま)?\s*(?:で|が)?\s*(?:よい|良い)?\s*$')


def option_problems(labels, current):
    """選択肢に判断の根拠と結果が書かれているかを見る．問題の説明 (無ければ空)．
    「今の転記でよい」だけで中身 (値・階層と根拠) が無い，選択肢が無い (既定の「今の転記でよい / 違う」になる) を知らせる"""
    if not labels:
        return '選択肢が無い (既定の「今の転記でよい」になる)．根拠と結果を書いた選択肢を足す'
    bare = [l for l in labels if BARE_CURRENT.match(l.strip())]
    if bare and not current:
        return '「今の転記でよい」に中身が無い．「今の転記 (下線なしのため K) でよい」のように根拠と結果を書く'
    return ''


def with_current(opts, current):
    """「今の転記でよい」の選択肢に今の値を書き込む (user_review.tsv の current 列．例: 今の転記 (K +・2) でよい)"""
    if not current:
        return opts
    out = [dict(o) for o in opts]
    out[0]['label'] = f'今の転記 ({current}) でよい'
    return out


GROUPS = {'A': '値の読み', 'B': '下線・階層・種名', 'C': '行と種の割り当て', 'D': '表頭と注記'}


def group_of(kind):
    """user_review.tsv の kind から区分 (A〜D) を決める．`A. 読めない値` の形ならその記号，そうでなければ語で寄せる"""
    k = (kind or '').strip()
    if k[:1] in GROUPS and k[1:2] in ('.', '．', ' ', ':'):
        return k[:1]
    if any(w in k for w in ('表頭', '注記', '調査地', '出典', '単位')):
        return 'D'
    if any(w in k for w in ('読めない', '常在度の値', '値の読み', 'かすれ')):
        return 'A'
    if any(w in k for w in ('下線', '階層', '種名', '学名', '取り消し')):
        return 'B'
    return 'C'


TSV_COLS = ['table', 'plot', 'j_name', 'kind', 'what', 'page', 'x0', 'y0', 'x1', 'y1']
PAD = 150


PARA_KIND = re.compile(r'見出しの欠け|注記の字|^G\. 注記|注記$|種数の差')
PARA_WHAT = re.compile(r'1 回出現|出現 ?2 回|出現1回|^注記|調査地の注記|^出典|in \d+:')


def is_paragraph(kind, what):
    """表の本体のセルではなく，1 回出現・注記・調査地などの段落 (文章) を指す項目か (区分名か，説明の頭 30 字で見る)．
    段落には列が無いので，列の番号や通し番号の帯を付けると誤る (2026-11-08．近畿 U05)"""
    return bool(PARA_KIND.search(kind or '') or PARA_WHAT.search((what or '')[:30]))


def load_head_rows(path, region=None):
    """表頭の通し番号の行の位置 {(表, ページ): [y0, y1]}．y0 が空の行 (そのページに通し番号の行が無い) は除く．
    任意の列 x0・x1 (その表の左右) があれば [y0, y1, x0, x1] にする (plot_x_map が隣の表の番号を拾わないため)"""
    import csv
    out = {}
    with open(path, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            if region and r['region'] != region:
                continue
            if (r.get('y0') or '').strip() and (r.get('y1') or '').strip():
                v = [int(float(r['y0'])), int(float(r['y1']))]
                if (r.get('x0') or '').strip() and (r.get('x1') or '').strip():
                    v += [int(float(r['x0'])), int(float(r['x1']))]
                out[(r['table'], r['page'])] = v
    return out


def from_tsv(path, heads=None):
    """user_review.tsv (読みながら積んだ確認の項目) を項目のリストにする．範囲は赤枠で囲み，周りを PAD px 広げて切る．
    任意の列 layer_x0・layer_x1 (階層の列の左右) があれば，切り出しに入らない階層の列を左に貼る．
    heads ({(表, ページ): [y0, y1]}) に表があれば，表頭の通し番号の行を画像の上に貼る (切り出しに入っていなければ)"""
    heads = heads or {}
    import csv
    base = os.path.dirname(os.path.abspath(path))
    items = []
    with open(path, encoding='utf-8-sig', newline='') as f:
        for i, r in enumerate(csv.DictReader(f, delimiter='	'), 1):
            page = r['page'] if r['page'].lower().endswith(('.png', '.jpg')) else os.path.join('work', r['page'] + '.png')
            x0, y0, x1, y1 = (int(float(r[k])) for k in ('x0', 'y0', 'x1', 'y1'))
            g = group_of(r.get('kind', ''))
            sp = {'page': page, 'crop': [max(0, x0 - PAD), max(0, y0 - PAD), x1 + PAD, y1 + PAD],
                  'caption': r['table'], 'marks': [{'box': [x0, y0, x1, y1]}]}
            # 確かめる地点とその前後 2 地点だけを切り出す (2026-11-08 ユーザ指示)．列の x は col_x.tsv (marks_grid.py が
            # 書く) があればそれを，無ければ通し番号の行から測る (plot_x_map．列が等間隔の表だけ)
            hy0 = heads.get((r['table'], r['page']))
            plots0 = parse_plots(r.get('plot', ''))
            xmap = None
            if plots0 and not is_paragraph(r.get('kind', ''), r['what']):
                xmap = load_col_x(base).get((table_key(r['table']), r['page']))
                n = n_plots_of(base, r['table'])
                if not xmap and hy0 and n:
                    try:
                        xmap = plot_x_map(load_page(base, page), hy0[:2], n, [y0 - 300, y1 + 300],
                                          xr=hy0[2:4] if len(hy0) >= 4 else None)
                    except OSError:
                        xmap = None
                warn = box_off_column(xmap, plots0, [x0, y0, x1, y1])
                if warn:                                  # 赤枠がその地点の列から外れている (2026-11-08．中部 145)
                    print(f'!! U{i:02d} {r["table"]} 地点 {r["plot"]}: {warn}')
                    WARNINGS.append((f'U{i:02d}', r['table'], r['plot'], warn))
                sp['crop'] = narrow_crop(sp['crop'], xmap, plots0, box=[x0, y0, x1, y1])
                if len(plots0) == 1 and xmap and plots0[0] in xmap and len(xmap) > 1 and not warn:
                    # 見るのが 1 地点だけなのに赤枠が横に長い (行を囲んだ) ときは，その地点の列にも縦の赤枠を付ける
                    # (2026-11-09 ユーザ指示．中国 U47．行と列の赤枠の交わりが見るセル)
                    xs = sorted(xmap.values())
                    pitch = sorted(b - a for a, b in zip(xs, xs[1:]))[(len(xs) - 1) // 2]
                    if x1 - x0 > 1.6 * pitch:
                        xc = xmap[plots0[0]]
                        sp['marks'].append({'box': [int(xc - .5 * pitch), sp['crop'][1] + 6,
                                                    int(xc + .5 * pitch), sp['crop'][3] - 6]})
                        sp['caption'] += f'．縦の赤枠は地点 {plots0[0]} の列 (横の赤枠との交わりが見るセル)'
            nx = [(r.get(k) or '').strip() for k in ('names_x0', 'names_x1')]
            if all(nx):                               # 種名の列を左に貼る (赤枠を種名まで広げない．2026-11-08)
                sp['names_x'] = [int(float(v)) for v in nx]
                sp['caption'] += '．左は同じ高さの種名の列'
            lx = [(r.get(k) or '').strip() for k in ('layer_x0', 'layer_x1')]
            if all(lx):
                sp['layer_x'] = [int(float(v)) for v in lx]
                if layer_strip_needed(sp):
                    sp['caption'] += '．左は同じ高さの階層の列'
            # 赤枠の行 (種名) と列 (地点) を画像の余白に青で書く (2026-11-08 ユーザ指示．四国 U53 で行と列が分からなかった)
            name = r.get('j_name', '').strip()
            plot = r.get('plot', '').strip()
            para = is_paragraph(r.get('kind', ''), r['what'])
            if name and not para:
                sp['rows'] = [[(y0 + y1) // 2, name if len(name) <= 16 else name[:15] + '…']]
            measured = False
            hy = heads.get((r['table'], r['page']))
            if para:      # 1 回出現・注記の段落 (文章) には列が無いので，行・列の印も通し番号の帯も付けない
                pass
            elif hy and not (sp['crop'][1] <= hy[0] and hy[1] <= sp['crop'][3]):
                sp['head_y'] = hy[:2]         # 表頭の通し番号の行を上に貼る
            elif plot and xmap and all(p in xmap for p in plots0):   # 列の x が分かれば，その列の上に地点番号を書く
                lo_, hi_ = max(min(xmap), min(plots0) - 2), min(max(xmap), max(plots0) + 2)
                sp['cols'] = [[xmap[p], str(p)] for p in range(lo_, hi_ + 1) if p in xmap]
                measured = True
            elif plot:    # 複数の地点は赤枠の中の列を測って 1 列ずつ番号を振る
                sp['cols'], measured = plot_cols(base, page, [x0, y0, x1, y1], sp['crop'], plot)
            where = '・'.join(x for x in (f'行 = {name}' if name else '', f'列 = 地点 {plot}' if plot else '') if x)
            if para and plot:
                sp['caption'] += f'．赤枠は地点 {plot} の記載 (段落)'
            elif where:
                sp['caption'] += f'．赤枠は {where}'
                sp['caption'] += ('．上の帯は表頭の通し番号の行' if 'head_y' in sp
                                  else ' (青字．上の数字は列ごとの地点番号)' if measured else ' (青字)')
            cur = (r.get('current') or '').strip()
            note, labels = options_from_what(r['what'])   # 文で書いた選択肢はラジオボタンにする
            opts = options_of(g, labels, cur) if labels else with_current(VALUE if g == 'A' else CONFIRM, cur)
            weak = option_problems(labels, cur)
            if weak:                                  # 判断の根拠と結果の無い選択肢 (2026-11-09 ユーザ指示．中国 U29)
                OPTION_WARNINGS.append((f'U{i:02d}', r['table'], weak))
            items.append({'id': f'U{i:02d}', 'group': g,
                          'title': ' '.join(x for x in (r['table'], '地点 ' + r['plot'] if r['plot'] else '', r['j_name']) if x),
                          'layer': r.get('kind', ''), 'note': note,
                          'options': opts,
                          'images': [sp]})
    return items


CSS = """
:root{--bg:#fafafa;--fg:#222;--card:#fff;--line:#ccc;--acc:#0a5}
@media (prefers-color-scheme:dark){:root{--bg:#1c1c1c;--fg:#eee;--card:#262626;--line:#555;--acc:#4c8}}
body{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,'Yu Gothic',sans-serif;margin:0;padding:16px;max-width:1100px;margin-inline:auto}
body.side{max-width:1600px}
.pane{display:block}body.side .pane{display:grid;grid-template-columns:minmax(0,3fr) minmax(15em,2fr);gap:16px;align-items:start}
body.side .ans{margin-top:0;position:sticky;top:56px}
@media (max-width:800px){body.side .pane{display:block}body.side .ans{margin-top:8px;position:static}}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:16px 0}
.topic{margin:28px 0 0;padding:4px 8px;border-left:5px solid var(--acc);font-size:16px}
h2{font-size:17px;margin:0 0 4px}.lay{font-size:13px;margin-left:10px;border:1px solid var(--line);border-radius:4px;padding:0 6px}
.meta{margin:0;font-size:13px}.memo{margin:2px 0 8px;font-size:12px;opacity:.8}
.imgs{display:flex;flex-direction:column;gap:6px;overflow-x:auto}figure{margin:0}
img{max-width:100%;border:1px solid var(--line);background:#fff}figcaption{font-size:11px;opacity:.6}
.ans{margin-top:8px;display:flex;flex-direction:column;gap:6px}.ans label{display:flex;gap:6px;align-items:baseline}
input[type=text]{padding:3px 6px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg)}
.v{width:12em}.m{width:24em;max-width:100%}
select{padding:4px;font-size:14px}#bar label{font-size:13px}
button{padding:8px 16px;border:0;border-radius:6px;background:var(--acc);color:#fff;font-size:15px;cursor:pointer}
#bar{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:2}
"""

JS = """
const KEY='review_html:'+document.title, cards=[...document.querySelectorAll('.card')];
let st={}; try{st=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function collect(c){const r=c.querySelector('input[type=radio]:checked');
  const v=r?c.querySelector('.v[data-opt="'+r.value+'"]'):null;
  return {choice:r?r.value:'', value:v?v.value:'', memo:c.querySelector('.m').value}}
function save(){const o={};cards.forEach(c=>o[c.dataset.id]=collect(c));
  try{localStorage.setItem(KEY,JSON.stringify(o))}catch(e){}
  document.getElementById('n').textContent=cards.filter(c=>{const a=o[c.dataset.id];
    const need=a.choice&&c.querySelector('.v[data-opt="'+a.choice+'"]');return a.choice&&(!need||a.value)}).length}
function restore(c,a){if(!a) return;
  const r=c.querySelector('input[type=radio][value="'+a.choice+'"]'); if(r) r.checked=true;
  const v=c.querySelector('.v[data-opt="'+a.choice+'"]'); if(v) v.value=a.value||''; c.querySelector('.m').value=a.memo||''}
cards.forEach(c=>{restore(c,st[c.dataset.id]);
  c.addEventListener('input',ev=>{const t=ev.target; if(t.classList&&t.classList.contains('v')&&t.value){
    const r=c.querySelector('input[type=radio][value="'+t.dataset.opt+'"]'); if(r) r.checked=true} save()})});
save();
// 絞り込み: すべて / 未回答だけ / 回答済みだけ (選んだ直後には隠さず，選び直したときに効く)
const flt=document.getElementById('flt');
function answered(c){return !!c.querySelector('input[type=radio]:checked')}
function applyFilter(){const m=flt.value; let shown=0;
  cards.forEach(c=>{const a=answered(c), hide=(m==='todo'&&a)||(m==='done'&&!a); c.style.display=hide?'none':''; if(!hide) shown++});
  document.getElementById('shown').textContent=shown;
  try{localStorage.setItem(KEY+':flt',m)}catch(e){}}
try{flt.value=localStorage.getItem(KEY+':flt')||'all'}catch(e){}
flt.onchange=applyFilter; document.getElementById('re').onclick=applyFilter; applyFilter();
// 保存した回答の JSON を読み込む (別の端末で答えた分を続けるとき)
document.getElementById('imp').onchange=ev=>{const f=ev.target.files[0]; if(!f) return;
  f.text().then(t=>{const o=JSON.parse(t); cards.forEach(c=>{if(o[c.dataset.id]&&o[c.dataset.id].choice) restore(c,o[c.dataset.id])}); save(); applyFilter()})};
document.getElementById('dl').onclick=()=>{const o={};cards.forEach(c=>o[c.dataset.id]=collect(c));
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(o,null,1)],{type:'application/json'}));
  a.download=FNAME;a.click()};
"""


def answers_name(region):
    """回答 JSON の保存ファイル名．地方名 (region) を頭に付けて，地方の HTML どうしでダウンロードフォルダの名前が重ならない
    ようにする (例: kanto → kanto_review_answers.json)．region が空なら review_answers.json"""
    r = re.sub(r'[\\/:*?"<>|\s]+', '_', (region or '').strip()).strip('_.')
    return f'{r}_review_answers.json' if r else 'review_answers.json'


def card(base, it, choices):
    e = html.escape
    out = [f'<section class="card" data-id="{e(it["id"])}">']
    lay = f'<span class="lay">{e(it["layer"])}</span>' if it.get('layer') else ''
    out.append(f'<h2>{e(it["id"])}　{e(it.get("title", ""))}{lay}</h2>')
    if it.get('meta'):
        out.append(f'<p class="meta">{e(it["meta"])}</p>')
    if it.get('note'):
        out.append(f'<p class="memo">{e(it["note"])}</p>')
    out.append('<div class="pane"><div class="imgs">')
    for sp in it['images']:
        cap = e(sp.get('caption', '')) + '　(赤枠・赤線 = 該当)'
        b64 = sp.pop('_b64', None) or make_image(base, sp)
        out.append(f'<figure><img src="data:image/png;base64,{b64}"><figcaption>{cap}</figcaption></figure>')
    out.append('</div><div class="ans">')
    opts = it.get('options') or [{'value': c, 'label': LABELS[c], 'input': c == 'val'} for c in choices]
    if not any(o['value'] == 'skip' for o in opts):
        opts = opts + [{'value': 'skip', 'label': LABELS['skip']}]
    for o in opts:
        box = (f' <input type="text" class="v" data-opt="{e(o["value"])}" placeholder="{e(o.get("placeholder", "例: 1・2 / + / +・2"))}">'
               if o.get('input') else '')
        out.append(f'<label><input type="radio" name="{e(it["id"])}" value="{e(o["value"])}"> '
                   f'{e(o["label"])}{box}</label>')
    out.append('<input type="text" class="m" placeholder="メモ (任意)"></div></div></section>')
    return ''.join(out)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('items')
    ap.add_argument('out')
    ap.add_argument('--title', default=None, help='ページの題 (既定: 確認．--region があれば「確認 (地方名)」)')
    ap.add_argument('--region', default=None,
                    help='地方名 (例: kanto・okinawa．地方の出力フォルダ名)．回答の保存ファイル名を <地方名>_review_answers.json にする．'
                         '省くと出力 HTML の名前 (okinawa.html なら okinawa．--split なら出力フォルダの名前) から決める')
    ap.add_argument('--choices', default='val,none,skip', help='val,none,skip のうち出すもの (カンマ区切り)')
    ap.add_argument('--layout', choices=['side', 'stack'], default='side',
                    help='side = 画像を左・選択肢を右 (既定．幅の狭い画面では上下になる)，stack = 画像の下に選択肢')
    ap.add_argument('--split', action='store_true',
                    help='区分 (A 値の読み・B 下線・階層・種名・C 行と種の割り当て・D 表頭と注記) ごとに別の HTML にする．out は置き場のディレクトリ')
    ap.add_argument('--head-rows', default=None,
                    help='表頭の通し番号の行の位置の表 (列: region table page y0 y1 note)．user_review.tsv から作るとき，'
                         'その行を画像の上に貼る (列ごとの地点番号が読める)')
    ap.add_argument('--head-region', default=None, help='--head-rows の region 列の値 (例: shikoku)．省くと全部の行を使う')
    ap.add_argument('--settled', nargs='*', default=[],
                    help='反映済みの回答 JSON．選択肢を選んだ項目は HTML から外す (番号は変えない)')
    ap.add_argument('--only', default=None, help='--split のとき作る区分 (例: B または BD)．省くと全部')
    ap.add_argument('--export-png', default=None, metavar='DIR',
                    help='各項目の画像を DIR に PNG で書き出す (U12_0.png の形)．赤枠が説明の場所と合うかを 1 枚ずつ確かめるため')
    a = ap.parse_args(argv)
    choices = [c for c in a.choices.split(',') if c in LABELS]
    if a.items.lower().endswith('.tsv'):
        heads = load_head_rows(a.head_rows, a.head_region) if a.head_rows else {}
        items = from_tsv(a.items, heads)
    else:
        with open(a.items, encoding='utf-8-sig') as f:
            items = json.load(f)
    base = os.path.dirname(os.path.abspath(a.items))
    region = a.region if a.region is not None else (
        os.path.basename(os.path.normpath(os.path.abspath(a.out))) if a.split
        else os.path.splitext(os.path.basename(a.out))[0])
    title = a.title if a.title is not None else (f'確認 ({a.region})' if a.region else '確認')
    done = set()
    for p in a.settled:                  # 反映済みの回答 (選択肢を選んだもの) は外す
        with open(p, encoding='utf-8-sig') as f:
            done |= {k for k, v in json.load(f).items() if (v or {}).get('choice')}
    if done:
        items = [it for it in items if it['id'] not in done]
        print(f'反映済み {len(done)} 件を外した')
    if a.split and a.only:
        items = [it for it in items if it.get('group', group_of(it.get('layer', ''))) in a.only]
    shown = {it['id'] for it in items}
    box_warn = [w for w in WARNINGS if w[0] in shown]   # 回答済みで外した項目の警告は数えない
    if box_warn:          # 赤枠が地点の列から外れている項目 (画像の準備の担当が画像を見て直す．SKILL.md 8 節)
        print(f'!! 赤枠が確かめる地点の列から外れている項目が {len(box_warn)} 件．画像を見て user_review.tsv の座標を直す')
    weak = [w for w in OPTION_WARNINGS if w[0] in shown]
    for uid, table, msg in weak:
        print(f'!! {uid} {table}: {msg}')
    if weak:              # 判断の根拠と結果の無い選択肢 (SKILL.md 8.3)
        print(f'!! 選択肢に根拠と結果の無い項目が {len(weak)} 件．user_review.tsv の what を直す')
    prerender(base, items)
    if a.export_png:      # 赤枠が説明の場所と合うかを確かめる画像 (2026-11-09 ユーザ指示．SKILL.md 8.6)
        os.makedirs(a.export_png, exist_ok=True)
        n = 0
        for it in items:
            for k, sp in enumerate(it.get('images', [])):
                img = make_image(base, sp)
                b64 = (img[0] if isinstance(img, tuple) else img).split(',', 1)[-1]
                with open(os.path.join(a.export_png, f"{it['id']}_{k}.png"), 'wb') as f:
                    f.write(base64.b64decode(b64))
                n += 1
        print(f'画像 {n} 枚を書き出した: {a.export_png} (赤枠が説明の場所と合うかを 1 枚ずつ確かめる)')
    if a.split:
        os.makedirs(a.out, exist_ok=True)
        for g, name in GROUPS.items():
            if a.only and g not in a.only:
                continue
            sub = [it for it in items if it.get('group', group_of(it.get('layer', ''))) == g]
            if sub:
                write_page(base, sub, choices, os.path.join(a.out, f'review_{g}.html'), f'{title} {g}. {name}', a.layout,
                           f'{region}_{g}' if region else g)
        return 0
    write_page(base, items, choices, a.out, title, a.layout, region)
    return 0


def prerender(base, items):
    """画像をページ順に作っておく (sp['_b64'])．HTML の項目は区分・話題の順で並ぶのでページが行き来し，
    ページの使い回し (load_page) が効かなくなるため (2026-11-08)"""
    specs = [sp for it in items for sp in it.get('images', []) if 'page' in sp]
    for sp in sorted(specs, key=lambda sp: os.path.abspath(page_path(base, sp['page']))):
        sp['_b64'] = make_image(base, sp)
    _PAGES.clear()


def write_page(base, items, choices, out, title, layout='side', region=''):
    """1 枚の HTML を書く．回答の保存ボタンのファイル名は answers_name(region)"""
    parts, prev = [], None
    for i, it in enumerate(items):  # 似た内容の項目は topic でまとめ，変わり目に見出しを出す (件数は続く分だけ)
        t = it.get('topic', '')
        if t and t != prev:
            k = next((j for j in range(i, len(items)) if items[j].get('topic', '') != t), len(items)) - i
            parts.append(f'<h3 class="topic">{html.escape(t)} ({k} 件)</h3>')
        prev = t
        parts.append(card(base, it, choices))
    cards = ''.join(parts)
    n = len(items)
    fname = answers_name(region)
    page = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
            f'<style>{CSS}</style></head><body class="{layout}">'
            f'<div id="bar"><b>{html.escape(title)} ({n} 件)</b>　回答済み <span id="n">0</span> / {n}　'
            f'<button id="dl">回答を JSON で保存</button>　'
            f'表示 <select id="flt"><option value="all">すべて</option><option value="todo">未回答だけ</option>'
            f'<option value="done">回答済みだけ</option></select> <button id="re" type="button">絞り込み直す</button> '
            f'(<span id="shown">{n}</span> 件)　<label>回答を読み込む <input type="file" id="imp" accept=".json"></label></div>'
            f'<p>赤枠・赤線が該当の位置です．画像を見て，値を入力するか，印字に無いとき・判断できないときは選んでください．'
            f'入力は自動で保存され，閉じても残ります．回答は「回答を JSON で保存」で {html.escape(fname)} として落ちます．</p>'
            f'{cards}<script>const FNAME={json.dumps(fname)};{JS}</script></body></html>')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(page)
    print(f'{n} 件 → {out} ({os.path.getsize(out) / 1e6:.1f} MB．回答の保存名 {fname})')


if __name__ == '__main__':
    sys.exit(main())
