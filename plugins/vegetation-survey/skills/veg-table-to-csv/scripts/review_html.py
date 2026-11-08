"""値や名前の確認用に，赤い印つきの画像を埋め込んだ 1 枚の HTML を作る．

    python scripts/review_html.py <項目.json> <出力.html> [--title 題] [--region 地方名] [--choices val,none,skip]
    python scripts/review_html.py <置き場>/user_review.tsv <出力.html>   # 読みながら積んだ項目から作る

`--split` を付けると，区分ごとに review_A.html〜review_D.html に分ける (out は置き場のディレクトリ)．
区分は kind の頭の記号 (`A. 読めない値` など) か，kind の語で決まる:
A 値の読み (読めない値・常在度の値) / B 下線・階層・種名 / C 行と種の割り当て (推定の割り当て・印字の重複・
見出しの欠け・出現種数) / D 表頭と注記．A の項目は「今の転記でよい・値を入力・値の印字は無い」で答える．

任意の列 `current` に今の転記の値 (例: `K +・2`) を書くと，選択肢が「今の転記 (K +・2) でよい」になる．

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
    page = Image.open(os.path.join(base, spec['page'])).convert('RGB')
    left = top = None
    pieces = []
    if spec.get('names_x'):
        nx0, nx1 = spec['names_x']
        pieces.append(page.crop((nx0, dy, nx1, dy + canvas.height)))
    if layer_strip_needed(spec):
        lx0, lx1 = spec['layer_x']
        if pieces and spec['names_x'][1] > lx0:          # 種名の列と重なるぶんは除く
            lx0 = min(spec['names_x'][1], lx1 - 1)
        pieces.append(page.crop((lx0, dy, lx1, dy + canvas.height)))
    if pieces:
        left = Image.new('RGB', (sum(p.width for p in pieces), canvas.height), 'white')
        x = 0
        for p in pieces:
            left.paste(p, (x, 0))
            x += p.width
    if spec.get('head_y'):
        hy0, hy1 = spec['head_y']
        top = page.crop((dx, hy0, dx + canvas.width, hy1))
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
        path = os.path.join(base, spec['page'])
        if not os.path.exists(path):                    # 同じ置き場の work_* (近畿の小古は work_sho．0.5.14)
            alt = sorted(glob.glob(os.path.join(os.path.dirname(os.path.dirname(path)), 'work*', os.path.basename(path))))
            path = alt[0] if alt else path
        im = Image.open(path).convert('RGB')
        x0, y0, x1, y1 = spec['crop'] if 'crop' in spec else (0, 0, im.width, im.height)
        im = im.crop((x0, y0, x1, y1))
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
    canvas.save(buf, 'PNG', optimize=True)
    return base64.b64encode(buf.getvalue()).decode('ascii')


CONFIRM = [{'value': 'a', 'label': '今の転記でよい'},
           {'value': 'b', 'label': '違う (正しい読み・扱いをメモに)'}]
VALUE = [{'value': 'a', 'label': '今の転記でよい'},
         {'value': 'val', 'label': '値を入力', 'input': True},
         {'value': 'none', 'label': '値の印字は無い (出現なし)'}]
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


def from_tsv(path):
    """user_review.tsv (読みながら積んだ確認の項目) を項目のリストにする．範囲は赤枠で囲み，周りを PAD px 広げて切る．
    任意の列 layer_x0・layer_x1 (階層の列の左右) があれば，切り出しに入らない階層の列を左に貼る"""
    import csv
    items = []
    with open(path, encoding='utf-8-sig', newline='') as f:
        for i, r in enumerate(csv.DictReader(f, delimiter='	'), 1):
            page = r['page'] if r['page'].lower().endswith(('.png', '.jpg')) else os.path.join('work', r['page'] + '.png')
            x0, y0, x1, y1 = (int(float(r[k])) for k in ('x0', 'y0', 'x1', 'y1'))
            g = group_of(r.get('kind', ''))
            sp = {'page': page, 'crop': [max(0, x0 - PAD), max(0, y0 - PAD), x1 + PAD, y1 + PAD],
                  'caption': r['table'], 'marks': [{'box': [x0, y0, x1, y1]}]}
            lx = [(r.get(k) or '').strip() for k in ('layer_x0', 'layer_x1')]
            if all(lx):
                sp['layer_x'] = [int(float(v)) for v in lx]
                if layer_strip_needed(sp):
                    sp['caption'] += '．左は同じ高さの階層の列'
            # 赤枠の行 (種名) と列 (地点) を画像の余白に青で書く (2026-11-08 ユーザ指示．四国 U53 で行と列が分からなかった)
            name = r.get('j_name', '').strip()
            plot = r.get('plot', '').strip()
            if name:
                sp['rows'] = [[(y0 + y1) // 2, name if len(name) <= 16 else name[:15] + '…']]
            if plot:
                sp['cols'] = [[(x0 + x1) // 2, f'地点 {plot}']]
            where = '・'.join(x for x in (f'行 = {name}' if name else '', f'列 = 地点 {plot}' if plot else '') if x)
            if where:
                sp['caption'] += f'．赤枠は {where} (青字)'
            items.append({'id': f'U{i:02d}', 'group': g,
                          'title': ' '.join(x for x in (r['table'], '地点 ' + r['plot'] if r['plot'] else '', r['j_name']) if x),
                          'layer': r.get('kind', ''), 'note': r['what'],
                          'options': with_current(VALUE if g == 'A' else CONFIRM, r.get('current', '')),
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
        out.append(f'<figure><img src="data:image/png;base64,{make_image(base, sp)}"><figcaption>{cap}</figcaption></figure>')
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
    a = ap.parse_args(argv)
    choices = [c for c in a.choices.split(',') if c in LABELS]
    if a.items.lower().endswith('.tsv'):
        items = from_tsv(a.items)
    else:
        with open(a.items, encoding='utf-8-sig') as f:
            items = json.load(f)
    base = os.path.dirname(os.path.abspath(a.items))
    region = a.region if a.region is not None else (
        os.path.basename(os.path.normpath(os.path.abspath(a.out))) if a.split
        else os.path.splitext(os.path.basename(a.out))[0])
    title = a.title if a.title is not None else (f'確認 ({a.region})' if a.region else '確認')
    if a.split:
        os.makedirs(a.out, exist_ok=True)
        for g, name in GROUPS.items():
            sub = [it for it in items if it.get('group', group_of(it.get('layer', ''))) == g]
            if sub:
                write_page(base, sub, choices, os.path.join(a.out, f'review_{g}.html'), f'{title} {g}. {name}', a.layout,
                           f'{region}_{g}' if region else g)
        return 0
    write_page(base, items, choices, a.out, title, a.layout, region)
    return 0


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
