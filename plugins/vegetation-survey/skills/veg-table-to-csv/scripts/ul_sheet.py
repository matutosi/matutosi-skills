"""下線の確認シート: 指定した行 (または下線の付いた値の全セル) を原寸の 3〜4 倍で切り出し，1 枚に並べる．

    python scripts/ul_sheet.py <画像> <出力> <表> --grid <grid.tsv> --colx <col_x.tsv>                 # note に下線のあるセル
    python scripts/ul_sheet.py <画像> <出力> <表> --grid ... --centers X1 X2 … --rows 8-12,30        # 指定した行の値のセル
    python scripts/ul_sheet.py <画像> <出力> <表> --grid ... --first-x X --pitch P --mode multi       # 階層が 2 つ以上の行の値のセル

なぜ要るか: 帯の画像 (marks_grid.py `--scale`) は縮小と罫線消しのため，一重の下線が二重に見え，行と行の間の下線は
どちらの行のものか分からない．下線の種類 (一重・二重・波線) と，どの行の値に付くかは，原寸の拡大で決める．

- 行の y は marks_grid.py `--tsv` が書く表 (`--grid`) の y_first・y_last．列の x は `--colx` (marks_grid.py が書く col_x.tsv)・
  `--centers`・`--first-x` と `--pitch` のどれか．行ごとの y は，第 1 列から最後の列へ直線で補う (紙面の傾き)．
- 転記の種の行の数と grid.tsv の行の数が違うときは，まとめた行を `--merge-rows`・`--merge-split` で marks_grid.py と同じに渡す．
- 選ぶセル: `--rows 8-12,30` は転記の種の行 (1 始まり) の値のあるセル全部．省くと `--mode` で決める．
  `--mode underlined` (既定) は note に `N: 下線`・`N: 二重下線`・`N: 一重下線`・`N: 波線` のある地点のセル，
  `--mode multi` は階層が 2 つ以上 (`S;K`) の行の値のあるセル．
- 1 つのセルは，列の幅の `--width` 倍 (既定 1.0)・行の間隔の上 `--up` 倍 (0.45)・下 `--down` 倍 (0.8) を `--zoom` 倍 (既定 3) で切る．
  下線は値の下に印字されるので下を広く取る．ラベルは `行:地点 値`．シートは `--per-row` (既定 6) 枚ずつ横に並べ，
  `--max-tiles` (既定 48) 枚で次のシートに分ける．
- 出力: `<出力>/ul_<表>_NN.png`．
"""
import argparse
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

Image.MAX_IMAGE_PIXELS = None

UL_NOTE = re.compile(r'^\s*(\d+)\s*[:：]\s*(.*)$')


def parse_rows(spec, n):
    """`8-12,30` -> 0 始まりの添字の集合"""
    out = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition('-')
        a, b = int(lo), int(hi or lo)
        if not 1 <= a <= b <= n:
            sys.exit(f'--rows {part} が範囲 (1〜{n}) の外')
        out |= set(range(a - 1, b))
    return out


def underlined_plots(note):
    """note の `N: 下線` などから，下線 (一重・二重・波線) のある地点の番号 (1 始まり) の集合"""
    out = set()
    for part in re.split(r'[;；]', note or ''):
        m = UL_NOTE.match(part)
        if not m:
            continue
        body = m.group(2).strip()
        if re.match(r'(?:二重|一重|二本)?下線(?!なし|無し)', body) or body.startswith('波線'):
            out.add(int(m.group(1)))
    return out


def tile_font(size):
    for name in ('arial.ttf', 'DejaVuSans.ttf', 'msgothic.ttc', 'meiryo.ttc'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def select_cells(sp, phys, mode, rows):
    """[(物理の行の添字, 転記の種の行の添字のリスト, 地点の添字)]．rows は転記の種の行の添字の集合か None"""
    cells = []
    for k, g in enumerate(phys):
        for c in range(len(sp[g[0]]['vals'])):
            hit = False
            for r in g:
                v = sp[r]['vals'][c]
                if v.strip() in ('', '・', '.'):
                    continue
                if rows is not None:
                    hit = hit or r in rows
                elif mode == 'multi':
                    hit = hit or ';' in sp[r]['layer']
                else:
                    hit = hit or (c + 1) in underlined_plots(sp[r]['note'].lstrip('\x00'))
            if hit:
                cells.append((k, g, c))
    return cells


def make_sheet(tiles, per_row, zoom, path):
    """tiles: [(ラベル, 画像)]．横に per_row 枚ずつ並べて保存する"""
    f = tile_font(14)
    tw = max(t.width for _, t in tiles) + 8
    th = max(t.height for _, t in tiles) + 24
    rows = (len(tiles) + per_row - 1) // per_row
    sheet = Image.new('RGB', (tw * min(per_row, len(tiles)), th * rows), 'white')
    d = ImageDraw.Draw(sheet)
    for i, (lab, t) in enumerate(tiles):
        x, y = (i % per_row) * tw, (i // per_row) * th
        sheet.paste(t.convert('RGB'), (x + 4, y + 20))
        d.rectangle((x + 3, y + 19, x + 4 + t.width, y + 20 + t.height), outline=(190, 190, 190))
        d.text((x + 4, y + 2), lab, fill=(200, 0, 0), font=f)
    sheet.save(path)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    import shift_check as sc
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('image')
    ap.add_argument('out')
    ap.add_argument('table', help='表の名前 (Tab.9 など)')
    ap.add_argument('--grid', required=True, help='marks_grid.py --tsv が書く表 (行の y_first・y_last)')
    ap.add_argument('--colx', help='marks_grid.py が書く col_x.tsv')
    ap.add_argument('--centers', type=float, nargs='+', help='全列の中心の x')
    ap.add_argument('--first-x', type=float)
    ap.add_argument('--pitch', type=float)
    ap.add_argument('--rows', help='転記の種の行 (1 始まり．例: 8-12,30) の値のあるセル全部')
    ap.add_argument('--mode', choices=('underlined', 'multi'), default='underlined')
    ap.add_argument('--merge-split', action='store_true')
    ap.add_argument('--merge-rows', nargs='+', default=[], metavar='K0-K1')
    ap.add_argument('--zoom', type=float, default=3.0, help='拡大の倍率 (3〜4)')
    ap.add_argument('--width', type=float, default=1.0, help='セルの幅 (列の間隔の倍数)')
    ap.add_argument('--up', type=float, default=.45, help='行の y から上へ (行の間隔の倍数)')
    ap.add_argument('--down', type=float, default=.8, help='行の y から下へ (行の間隔の倍数．下線は値の下)')
    ap.add_argument('--per-row', type=int, default=6)
    ap.add_argument('--max-tiles', type=int, default=48)
    a = ap.parse_args(argv)

    sp, kinds, n = sc.read_body(os.path.join(a.out, 'transcripts', sc.table_dir(a.table), 'body.tsv'))
    if not sp or not n:
        sys.exit('body.tsv に種の行・地点の列が無い')
    manual = sc.parse_merge(a.merge_rows)
    groups = (sc.split_groups(sp, manual) if a.merge_split else sorted(manual)) if (a.merge_split or a.merge_rows) else []
    phys = sc.physical_rows(len(sp), groups)

    first, last = sc.read_grid(a.grid, 'first'), sc.read_grid(a.grid, 'last')
    if len(first) == len(sp) and not groups:
        phys = [[r] for r in range(len(sp))]
    elif len(first) != len(phys):
        sys.exit(f'grid.tsv の行は {len(first)}．転記の種の行 {len(sp)}・まとめた行 {len(phys)}'
                 '．まとめた行は --merge-rows・--merge-split を marks_grid.py と同じに渡す')

    page = os.path.splitext(os.path.basename(a.image))[0]
    if a.centers:
        cx = sorted(a.centers)
    elif a.first_x is not None and a.pitch:
        cx = [a.first_x + a.pitch * k for k in range(n)]
    elif a.colx:
        cx = sc.read_colx(a.colx, a.table, page)
    else:
        sys.exit('列の x が要る (--colx・--centers・--first-x と --pitch のどれか)')
    if len(cx) != n:
        sys.exit(f'列の x が {len(cx)} 個．地点は {n}')

    rows = parse_rows(a.rows, len(sp)) if a.rows else None
    cells = select_cells(sp, phys, a.mode, rows)
    if not cells:
        print('切り出すセルが無い (--rows か --mode を見直す．下線は note に `N: 下線` と書いた地点)')
        return 0
    row_pitch = float(sorted(b - c for c, b in zip(first, first[1:]))[len(first) // 2]) if len(first) > 1 else 60.0
    col_pitch = (cx[-1] - cx[0]) / (n - 1) if n > 1 else 80.0
    im = Image.open(a.image).convert('L')
    span = (cx[-1] - cx[0]) or 1.0
    tiles = []
    for k, g, c in cells:
        y = first[k] + (last[k] - first[k]) * (cx[c] - cx[0]) / span     # 第 1 列から最後の列へ直線で補う
        box = (round(cx[c] - a.width * col_pitch / 2), round(y - a.up * row_pitch),
               round(cx[c] + a.width * col_pitch / 2), round(y + a.down * row_pitch))
        t = im.crop(box)
        t = t.resize((max(1, round(t.width * a.zoom)), max(1, round(t.height * a.zoom))), Image.LANCZOS)
        vals = ' / '.join(sp[r]['vals'][c] for r in g if sp[r]['vals'][c].strip() not in ('', '・'))
        tiles.append((f'{g[0] + 1}:{c + 1} {vals}', t))
    os.makedirs(a.out, exist_ok=True)
    paths = []
    for i in range(0, len(tiles), a.max_tiles):
        path = os.path.join(a.out, f'ul_{sc.table_dir(a.table)}_{i // a.max_tiles + 1:02d}.png')
        make_sheet(tiles[i:i + a.max_tiles], a.per_row, a.zoom, path)
        paths.append(path)
    print(f'下線の確認シート: {len(tiles)} セル (原寸の {a.zoom:g} 倍)')
    for p in paths:
        print(p)
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main())
