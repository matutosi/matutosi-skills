"""値や名前の確認用に，赤い印つきの画像を埋め込んだ 1 枚の HTML を作る．

    python scripts/review_html.py <項目.json> <出力.html> [--title 題] [--choices val,none,skip]
    python scripts/review_html.py <置き場>/user_review.tsv <出力.html>   # 読みながら積んだ項目から作る

`--split` を付けると，区分ごとに review_A.html〜review_D.html に分ける (out は置き場のディレクトリ)．
区分は kind の頭の記号 (`A. 読めない値` など) か，kind の語で決まる:
A 値の読み (読めない値・常在度の値) / B 下線・階層・種名 / C 行と種の割り当て (推定の割り当て・印字の重複・
見出しの欠け・出現種数) / D 表頭と注記．A の項目は「今の転記でよい・値を入力・値の印字は無い」で答える．

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
- **何行目がどの種か・何列目がどの地点かを必ず示す**: 種名や表頭の通し番号が写らない切り出しには
  `"rows": [[y, "ナナカマド K"], …]` と `"cols": [[x, "46"], …]` (ページの原寸の座標) を書く．
  行の名は左の余白に，地点番号は上の余白に青で書き込まれる (赤は確かめてほしい箇所，青は位置の目印)．
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
  「回答を JSON で保存」ボタンで `{id: {choice, value, memo}}` が落ちる．

標準ライブラリと Pillow だけで動く．
"""
import argparse
import base64
import html
import io
import json
import os
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


def _arrow(d, x, y):
    d.polygon([(x - 8, y), (x + 8, y), (x, y + 12)], fill=RED)


def make_image(base, spec):
    """spec から (赤い印つき PNG の base64, 説明) を返す"""
    marks = spec.get('marks', [])
    if 'page' in spec:
        im = Image.open(os.path.join(base, spec['page'])).convert('RGB')
        x0, y0, x1, y1 = spec['crop'] if 'crop' in spec else (0, 0, im.width, im.height)
        im = im.crop((x0, y0, x1, y1))
        dx, dy = x0, y0
    else:
        im = Image.open(os.path.join(base, spec['image'])).convert('RGB')
        dx = dy = 0
    canvas = Image.new('RGB', (im.width + 2 * MARGIN, im.height + 2 * MARGIN), 'white')
    canvas.paste(im, (MARGIN, MARGIN))
    draw_marks(canvas, marks, dx - MARGIN, dy - MARGIN)
    if spec.get('rows') or spec.get('cols'):          # 何行目がどの種か・何列目がどの地点かを書き込む
        canvas = add_labels(canvas, spec.get('rows', []), spec.get('cols', []), dx - MARGIN, dy - MARGIN)
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
    """user_review.tsv (読みながら積んだ確認の項目) を項目のリストにする．範囲は赤枠で囲み，周りを PAD px 広げて切る"""
    import csv
    items = []
    with open(path, encoding='utf-8-sig', newline='') as f:
        for i, r in enumerate(csv.DictReader(f, delimiter='	'), 1):
            page = r['page'] if r['page'].lower().endswith(('.png', '.jpg')) else os.path.join('work', r['page'] + '.png')
            x0, y0, x1, y1 = (int(float(r[k])) for k in ('x0', 'y0', 'x1', 'y1'))
            g = group_of(r.get('kind', ''))
            items.append({'id': f'U{i:02d}', 'group': g,
                          'title': ' '.join(x for x in (r['table'], '地点 ' + r['plot'] if r['plot'] else '', r['j_name']) if x),
                          'layer': r.get('kind', ''), 'note': r['what'], 'options': VALUE if g == 'A' else CONFIRM,
                          'images': [{'page': page, 'crop': [max(0, x0 - PAD), max(0, y0 - PAD), x1 + PAD, y1 + PAD],
                                      'caption': r['table'], 'marks': [{'box': [x0, y0, x1, y1]}]}]})
    return items


CSS = """
:root{--bg:#fafafa;--fg:#222;--card:#fff;--line:#ccc;--acc:#0a5}
@media (prefers-color-scheme:dark){:root{--bg:#1c1c1c;--fg:#eee;--card:#262626;--line:#555;--acc:#4c8}}
body{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,'Yu Gothic',sans-serif;margin:0;padding:16px;max-width:1100px;margin-inline:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:16px 0}
h2{font-size:17px;margin:0 0 4px}.lay{font-size:13px;margin-left:10px;border:1px solid var(--line);border-radius:4px;padding:0 6px}
.meta{margin:0;font-size:13px}.memo{margin:2px 0 8px;font-size:12px;opacity:.8}
.imgs{display:flex;flex-direction:column;gap:6px;overflow-x:auto}figure{margin:0}
img{max-width:100%;border:1px solid var(--line);background:#fff}figcaption{font-size:11px;opacity:.6}
.ans{margin-top:8px;display:flex;flex-direction:column;gap:6px}.ans label{display:flex;gap:6px;align-items:baseline}
input[type=text]{padding:3px 6px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg)}
.v{width:12em}.m{width:24em;max-width:100%}
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
cards.forEach(c=>{const a=st[c.dataset.id]; if(a){
  const r=c.querySelector('input[type=radio][value="'+a.choice+'"]'); if(r) r.checked=true;
  const v=c.querySelector('.v[data-opt="'+a.choice+'"]'); if(v) v.value=a.value||''; c.querySelector('.m').value=a.memo||''}
  c.addEventListener('input',ev=>{const t=ev.target; if(t.classList&&t.classList.contains('v')&&t.value){
    const r=c.querySelector('input[type=radio][value="'+t.dataset.opt+'"]'); if(r) r.checked=true} save()})});
save();
document.getElementById('dl').onclick=()=>{const o={};cards.forEach(c=>o[c.dataset.id]=collect(c));
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(o,null,1)],{type:'application/json'}));
  a.download='review_answers.json';a.click()};
"""


def card(base, it, choices):
    e = html.escape
    out = [f'<section class="card" data-id="{e(it["id"])}">']
    lay = f'<span class="lay">{e(it["layer"])}</span>' if it.get('layer') else ''
    out.append(f'<h2>{e(it["id"])}　{e(it.get("title", ""))}{lay}</h2>')
    if it.get('meta'):
        out.append(f'<p class="meta">{e(it["meta"])}</p>')
    if it.get('note'):
        out.append(f'<p class="memo">{e(it["note"])}</p>')
    out.append('<div class="imgs">')
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
                   f'{e(o["value"]) + ". " if len(o["value"]) == 1 else ""}{e(o["label"])}{box}</label>')
    out.append('<input type="text" class="m" placeholder="メモ (任意)"></div></section>')
    return ''.join(out)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('items')
    ap.add_argument('out')
    ap.add_argument('--title', default='確認')
    ap.add_argument('--choices', default='val,none,skip', help='val,none,skip のうち出すもの (カンマ区切り)')
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
    if a.split:
        os.makedirs(a.out, exist_ok=True)
        for g, name in GROUPS.items():
            sub = [it for it in items if it.get('group', group_of(it.get('layer', ''))) == g]
            if sub:
                write_page(base, sub, choices, os.path.join(a.out, f'review_{g}.html'), f'{a.title} {g}. {name}')
        return 0
    write_page(base, items, choices, a.out, a.title)
    return 0


def write_page(base, items, choices, out, title):
    cards = ''.join(card(base, it, choices) for it in items)
    n = len(items)
    page = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
            f'<style>{CSS}</style></head><body>'
            f'<div id="bar"><b>{html.escape(title)} ({n} 件)</b>　回答済み <span id="n">0</span> / {n}　'
            f'<button id="dl">回答を JSON で保存</button></div>'
            f'<p>赤枠・赤線が該当の位置です．画像を見て，値を入力するか，印字に無いとき・判断できないときは選んでください．'
            f'入力は自動で保存され，閉じても残ります．</p>{cards}<script>{JS}</script></body></html>')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(page)
    print(f'{n} 件 → {out} ({os.path.getsize(out) / 1e6:.1f} MB)')


if __name__ == '__main__':
    sys.exit(main())
