"""値や名前の確認用に，赤い印つきの画像を埋め込んだ 1 枚の HTML を作る．

    python scripts/review_html.py <項目.json> <出力.html> [--title 題] [--choices val,none,skip]

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
- `marks` の種類 (赤で描く):
  - `{"box": [x0, y0, x1, y1]}` 対象の語やセルを囲む枠
  - `{"underline": [x0, x1, y]}` 値を入れる位置の下線と ▼ (値が無いところを指すとき)
  - `{"arrow": [x, y]}` その点を指す ▼
- 画像の相対パスは項目.json のあるディレクトリから見る．
- 回答は `val` (値を入力)・`none` (印字に無い)・`skip` (判断できない)．`--choices` で選ぶ．
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

from PIL import Image, ImageDraw

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
    buf = io.BytesIO()
    canvas.save(buf, 'PNG', optimize=True)
    return base64.b64encode(buf.getvalue()).decode('ascii')


CSS = """
:root{--bg:#fafafa;--fg:#222;--card:#fff;--line:#ccc;--acc:#0a5}
@media (prefers-color-scheme:dark){:root{--bg:#1c1c1c;--fg:#eee;--card:#262626;--line:#555;--acc:#4c8}}
body{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,'Yu Gothic',sans-serif;margin:0;padding:16px;max-width:1100px;margin-inline:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:16px 0}
h2{font-size:17px;margin:0 0 4px}.lay{font-size:13px;margin-left:10px;border:1px solid var(--line);border-radius:4px;padding:0 6px}
.meta{margin:0;font-size:13px}.memo{margin:2px 0 8px;font-size:12px;opacity:.8}
.imgs{display:flex;flex-direction:column;gap:6px;overflow-x:auto}figure{margin:0}
img{max-width:100%;border:1px solid var(--line);background:#fff}figcaption{font-size:11px;opacity:.6}
.ans{margin-top:8px;display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center}
input[type=text]{padding:3px 6px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg)}
.v{width:9em}.m{width:16em}
button{padding:8px 16px;border:0;border-radius:6px;background:var(--acc);color:#fff;font-size:15px;cursor:pointer}
#bar{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:2}
"""

JS = """
const KEY='review_html:'+document.title, cards=[...document.querySelectorAll('.card')];
let st={}; try{st=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function collect(c){const id=c.dataset.id, r=c.querySelector('input[type=radio]:checked');
  return {choice:r?r.value:'', value:c.querySelector('.v')?c.querySelector('.v').value:'', memo:c.querySelector('.m').value}}
function save(){const o={};cards.forEach(c=>o[c.dataset.id]=collect(c));
  try{localStorage.setItem(KEY,JSON.stringify(o))}catch(e){}
  document.getElementById('n').textContent=cards.filter(c=>{const a=o[c.dataset.id];return a.choice&&(a.choice!=='val'||a.value)}).length}
cards.forEach(c=>{const a=st[c.dataset.id]; if(a){
  const r=c.querySelector('input[type=radio][value="'+a.choice+'"]'); if(r) r.checked=true;
  if(c.querySelector('.v')) c.querySelector('.v').value=a.value||''; c.querySelector('.m').value=a.memo||''}
  c.addEventListener('input',()=>{ if(c.querySelector('.v')&&c.querySelector('.v').value&&!c.querySelector('input[type=radio]:checked')){const r=c.querySelector('input[value="val"]'); if(r) r.checked=true} save()})});
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
    for c in choices:
        if c == 'val':
            out.append(f'<label><input type="radio" name="{e(it["id"])}" value="val"> {LABELS[c]}</label> '
                       '<input type="text" class="v" placeholder="例: 1・2 / + / +・2">')
        else:
            out.append(f'<label><input type="radio" name="{e(it["id"])}" value="{c}"> {LABELS[c]}</label>')
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
    a = ap.parse_args(argv)
    choices = [c for c in a.choices.split(',') if c in LABELS]
    with open(a.items, encoding='utf-8-sig') as f:
        items = json.load(f)
    base = os.path.dirname(os.path.abspath(a.items))
    cards = ''.join(card(base, it, choices) for it in items)
    n = len(items)
    page = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(a.title)}</title>'
            f'<style>{CSS}</style></head><body>'
            f'<div id="bar"><b>{html.escape(a.title)} ({n} 件)</b>　回答済み <span id="n">0</span> / {n}　'
            f'<button id="dl">回答を JSON で保存</button></div>'
            f'<p>赤枠・赤線が該当の位置です．画像を見て，値を入力するか，印字に無いとき・判断できないときは選んでください．'
            f'入力は自動で保存され，閉じても残ります．</p>{cards}<script>{JS}</script></body></html>')
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(page)
    print(f'{n} 件 → {a.out} ({os.path.getsize(a.out) / 1e6:.1f} MB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
