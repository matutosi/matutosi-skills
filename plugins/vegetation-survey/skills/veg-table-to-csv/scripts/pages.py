"""組成表の入力 (PDF・PNG・JPG) を，1 ページ 1 枚の PNG にそろえる．

    python scripts/pages.py <入力> [<入力> ...] --out <作業ディレクトリ> [--pages 10-20,35]

- PDF は 1 ページずつ書き出す．ページが 1 枚のスキャン画像だけなら，
  その画像を**原寸のまま**取り出す (描画し直すと解像度が変わるため)．
  それ以外は 300 dpi で描画する．
- PNG・JPG はそのまま写す (EXIF の向きは直す)．
- 書き出した各ページについて，全体を見渡すための縮小画像
  (`<名前>_overview.png`．目盛りの数字は原寸の px) も作る．
- ページが 2 枚以上あれば，縮小画像を並べた一覧 (`contact_01.png`…．各コマにページ名)
  も作る．**表のあるページを選ぶのに使う** (本の全ページの見渡しを 1 枚ずつ読むと重い)．
- 最後に，ページの一覧 (名前・幅・高さ・縮小率) を表示し，`pages.tsv` に書く．
"""
import argparse
import io
import os
import sys

from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crop import _font, ruled  # noqa: E402

Image.MAX_IMAGE_PIXELS = None               # A0 の折り込みは 1 億画素を超える

THUMB_W, THUMB_H, CONTACT_COLS, CONTACT_ROWS = 440, 620, 4, 3


def parse_pages(spec):
    """`10-20,35` を {10, …, 20, 35} にする．空なら None (全ページ)"""
    if not spec:
        return None
    out = set()
    for part in spec.split(','):
        lo, _, hi = part.strip().partition('-')
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def pdf_pages(path, wanted=None):
    """(ページ番号, 総ページ数, 画像) を 1 枚ずつ返す (全ページを同時に持たない)"""
    import pymupdf
    doc = pymupdf.open(path)
    for i, page in enumerate(doc, 1):
        if wanted is not None and i not in wanted:
            continue
        imgs = page.get_images(full=True)
        im = None
        if len(imgs) == 1 and not page.get_text().strip():   # 文字の層があれば，図だけを取らない
            info = doc.extract_image(imgs[0][0])
            try:
                im = Image.open(io.BytesIO(info['image']))
                im.load()
                if page.rotation:                     # 画像そのものはページの回転を含まない
                    im = im.rotate(-page.rotation, expand=True)
            except Exception:
                im = None
        if im is None:
            pix = page.get_pixmap(dpi=300)
            im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        yield i, doc.page_count, im


def items_of(src, wanted):
    base = os.path.splitext(os.path.basename(src))[0]
    if not src.lower().endswith('.pdf'):
        yield base, ImageOps.exif_transpose(Image.open(src))
        return
    for i, n, im in pdf_pages(src, wanted):
        yield (base if n == 1 else f'{base}_p{i:0{max(2, len(str(n)))}d}'), im


def thumb(im, name):
    """見出しつきの小さなコマを作る"""
    t = im.convert('RGB')
    t.thumbnail((THUMB_W - 8, THUMB_H - 30))
    cell = Image.new('RGB', (THUMB_W, THUMB_H), 'white')
    cell.paste(t, (4, 26))
    d = ImageDraw.Draw(cell)
    d.text((6, 4), name, fill=(200, 0, 0), font=_font(16))
    d.rectangle((0, 0, THUMB_W - 1, THUMB_H - 1), outline=(190, 190, 190))
    return cell


def write_contacts(cells, out):
    per = CONTACT_COLS * CONTACT_ROWS
    paths = []
    for k in range(0, len(cells), per):
        sheet = Image.new('RGB', (THUMB_W * CONTACT_COLS, THUMB_H * CONTACT_ROWS), 'white')
        for j, cell in enumerate(cells[k:k + per]):
            sheet.paste(cell, (j % CONTACT_COLS * THUMB_W, j // CONTACT_COLS * THUMB_H))
        paths.append(os.path.join(out, 'contact_%02d.png' % (k // per + 1)))
        sheet.save(paths[-1])
    return paths


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('inputs', nargs='+')
    ap.add_argument('--out', required=True, help='作業ディレクトリ')
    ap.add_argument('--pages', help='PDF のうち書き出すページ (例: 10-20,35)')
    ap.add_argument('--overview', type=int, default=1800,
                    help='見渡し画像の長辺 (px．既定 1800)')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    wanted = parse_pages(a.pages)
    rows, cells = [], []
    for src in a.inputs:
        for name, im in items_of(src, wanted):
            if im.mode not in ('RGB', 'L'):
                im = im.convert('RGB')
            im.save(os.path.join(a.out, name + '.png'))
            ov, scale = ruled(im, (0, 0, im.width, im.height), a.overview)
            ov.save(os.path.join(a.out, name + '_overview.png'))
            rows.append((name, im.width, im.height, scale))
            cells.append(thumb(im, name))
    with open(os.path.join(a.out, 'pages.tsv'), 'w', encoding='utf-8') as f:
        f.write('page\twidth\theight\toverview_scale\n')
        for r in rows:
            f.write('%s\t%d\t%d\t%.3f\n' % r)
    for name, w, h, s in rows:
        print(f'{name}: {w} x {h} px  (見渡しの縮小率 {s:.3f})')
    if len(cells) > 1:
        paths = write_contacts(cells, a.out)
        print(f'一覧: {len(paths)} 枚 ({os.path.basename(paths[0])} …)．表のあるページを選ぶのに使う')


if __name__ == '__main__':
    main()
