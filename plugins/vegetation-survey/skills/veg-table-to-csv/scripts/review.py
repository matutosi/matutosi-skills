"""AI が決められなかった和名などを，ユーザが画像を見てブラウザで判断するための道具．

    python scripts/review.py import <置き場> <一覧.tsv>    # 判断してほしい項目を review.tsv に積む
    python scripts/review.py serve <置き場>                # ブラウザが開く (http://127.0.0.1:8766/)
    python scripts/review.py apply <置き場>                # 答えを転記へ反映する

- 一覧.tsv の列: table field current candidates page x0 y0 x1 y1 note
  `field` は `j_name` か `s_name` (ほかの項目も積めるが，`apply` は反映しない)．
  `candidates` は `;` 区切りの候補．`page` はページ画像のパス (<置き場> からの相対でよい)．
  `x0 y0 x1 y1` は見てほしい範囲の原寸の座標．種の行は上下に数行広めに取る．
- ブラウザの左に画像，右に入力欄が並ぶ．欄からフォーカスが外れた時点で review.tsv に書き戻す．
  画像は `上へ`・`下へ` で動かせる (行の見積もりが外れていても，その場で探せる)．
- 判断は `fix` (答えのとおりに直す)・`ok` (印字どおり)・`unreadable` (読めない)・`skip` (保留)．
- `apply` は `fix` の項目だけを，その表の body.tsv・once.tsv・sparse*.txt へ反映する．
  名前の欄が `current` と完全に同じ所だけを直す．`--source` で，ほかの元の転記も直せる．

標準ライブラリと Pillow だけで動く．サーバは 127.0.0.1 だけで待ち受ける．
"""
import argparse
import csv
import glob
import io
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image

import crop
from sparse import table_dir

Image.MAX_IMAGE_PIXELS = None

COLS = ['id', 'table', 'field', 'current', 'candidates', 'page', 'x0', 'y0', 'x1', 'y1', 'note',
        'answer', 'state', 'memo']
IMPORT_COLS = COLS[1:11]
STATES = ('open', 'fix', 'ok', 'unreadable', 'skip', 'applied')
NAME_COLUMN = {'s_name': 0, 'j_name': 1}          # sparse の行の列
lock = threading.Lock()


def queue_path(root):
    return os.path.join(root, 'review.tsv')


def read_queue(root):
    if not os.path.exists(queue_path(root)):
        return []
    with open(queue_path(root), encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE))


def write_queue(root, rows):
    tmp = queue_path(root) + '.tmp'                # 途中で失敗しても元のファイルは壊れない
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, COLS, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar=None,
                           lineterminator='\n', escapechar=None)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, queue_path(root))


def import_rows(root, path):
    rows = read_queue(root)
    seen = {(r['table'], r['field'], r['current']) for r in rows}
    next_id = max((int(r['id']) for r in rows), default=0) + 1
    added = 0
    with open(path, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE):
            miss = [c for c in IMPORT_COLS if c not in r and c != 'note']
            if miss:
                sys.exit(f'列が無い: {miss}')
            key = (r['table'], r['field'], r['current'])
            if key in seen:
                continue
            seen.add(key)
            rows.append(dict({c: r.get(c) or '' for c in IMPORT_COLS}, id=str(next_id), answer='', state='open', memo=''))
            next_id += 1
            added += 1
    write_queue(root, rows)
    return added, len(rows)


def clean(text):
    """TSV を壊す字を除く"""
    return ' '.join(str(text).replace('\t', ' ').split())


def save_row(root, data):
    if data.get('state') not in STATES:
        raise ValueError('state が違う')
    with lock:
        rows = read_queue(root)
        hit = next((r for r in rows if r['id'] == str(data.get('id'))), None)
        if hit is None:
            raise LookupError('その項目が無い')
        hit['answer'], hit['memo'], hit['state'] = clean(data.get('answer', '')), clean(data.get('memo', '')), data['state']
        write_queue(root, rows)


class Pages:
    """大きいページ画像を 2 枚まで開いたままにする"""

    def __init__(self, root):
        self.root, self.cache, self.lock = root, {}, threading.Lock()

    def get(self, page):
        path = page if os.path.isabs(page) else os.path.join(self.root, page)
        with self.lock:
            if path not in self.cache:
                if len(self.cache) >= 2:
                    self.cache.pop(next(iter(self.cache)))
                self.cache[path] = Image.open(path).convert('L')
            return self.cache[path]


def render(pages, row, dy=0, scale=2.0):
    im = pages.get(row['page'])
    x0, y0, x1, y1 = (int(row[k]) for k in ('x0', 'y0', 'x1', 'y1'))
    box = (max(0, x0), max(0, y0 + dy), min(im.width, x1), min(im.height, y1 + dy))
    out, _ = crop.ruled(im, box, 1500, False, scale)
    buf = io.BytesIO()
    out.save(buf, 'PNG')
    return buf.getvalue()


def replace_tsv(path, field, old, new):
    with open(path, encoding='utf-8-sig', newline='') as f:
        lines = f.read().split('\n')
    head = lines[0].rstrip('\r').split('\t')
    if field not in head:
        return 0
    col, n = head.index(field), 0
    for i, line in enumerate(lines[1:], 1):
        cells = line.rstrip('\r').split('\t')
        if len(cells) > col and cells[col] == old:
            cells[col] = new
            lines[i] = '\t'.join(cells) + ('\r' if line.endswith('\r') else '')
            n += 1
    if n:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write('\n'.join(lines))
    return n


def replace_sparse(path, field, old, new):
    col = NAME_COLUMN[field]
    with open(path, encoding='utf-8-sig', newline='') as f:
        lines = f.read().split('\n')
    n = 0
    for i, line in enumerate(lines):
        if line.startswith(('#', 'g|')):
            continue
        cells = line.split('|')
        if len(cells) > col + 1 and cells[col].strip() == old:
            cells[col] = new
            lines[i] = '|'.join(cells)
            n += 1
    if n:
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write('\n'.join(lines))
    return n


def apply_rows(root, sources=()):
    rows = read_queue(root)
    done = missed = other = 0
    for r in rows:
        if r['state'] != 'fix':
            continue
        if r['field'] not in NAME_COLUMN:
            other += 1
            print(f"[手で直す] {r['table']} {r['field']}: {r['current']} → {r['answer']}")
            continue
        tdir = os.path.join(root, 'transcripts', table_dir(r['table']))
        n = 0
        for name in ('body.tsv', 'once.tsv'):
            path = os.path.join(tdir, name)
            if os.path.exists(path):
                n += replace_tsv(path, r['field'], r['current'], r['answer'])
        for path in glob.glob(os.path.join(tdir, 'sparse*.txt')) + list(sources):
            n += replace_sparse(path, r['field'], r['current'], r['answer'])
        if n:
            r['state'] = 'applied'
            done += 1
            print(f"{r['table']}: {r['current']} → {r['answer']} ({n} か所)")
        else:
            missed += 1
            print(f"[見つからない] {r['table']} {r['field']}: {r['current']}")
    write_queue(root, rows)
    print(f'反映 {done}・見つからない {missed}・手で直す {other}．続けて to_csv.py と check_species.py を流す')
    return done, missed, other


PAGE = r"""<!doctype html>
<html lang="ja"><meta charset="utf-8"><title>組成表の確認</title>
<style>
 body{margin:0;background:#faf8f5;color:#222;font-family:"Yu Gothic UI","Meiryo",system-ui,sans-serif}
 header{position:sticky;top:0;z-index:2;background:#faf8f5;border-bottom:1px solid #ddd;padding:.6rem 1rem;
        display:flex;flex-wrap:wrap;gap:.8rem;align-items:center;font-size:.9rem}
 h1{font-size:1rem;margin:0}
 .row{display:grid;grid-template-columns:minmax(0,1fr) 22rem;gap:1rem;padding:.8rem 1rem;border-bottom:1px solid #e3ded7}
 .row.done{background:#f1f5ef}
 .view img{display:block;max-width:100%;background:#fff;border:1px solid #ddd}
 .move{margin-top:.3rem;display:flex;gap:.3rem}
 .cur{font-size:1.25rem;font-weight:600}
 .meta{color:#666;font-size:.85rem;margin:.2rem 0 .5rem}
 .note{color:#845;font-size:.85rem;margin-bottom:.4rem}
 input[type=text]{width:100%;box-sizing:border-box;padding:.4rem;font-size:1.1rem;margin:.3rem 0}
 button{padding:.3rem .6rem;font-size:.85rem;cursor:pointer}
 .chips,.acts{display:flex;flex-wrap:wrap;gap:.3rem;margin:.3rem 0}
 .state{font-size:.85rem;color:#555;margin-top:.3rem}
 @media(max-width:800px){.row{grid-template-columns:1fr}}
</style>
<header><h1>組成表の確認</h1>
 <label><input type="radio" name="f" value="open" checked> 未判定</label>
 <label><input type="radio" name="f" value="all"> 全部</label>
 <span id="count"></span></header>
<main id="list"></main>
<script>
let rows=[];
const LABEL={open:'未判定',fix:'直す',ok:'印字どおり',unreadable:'読めない',skip:'保留',applied:'反映済み'};
const list=document.getElementById('list');
async function save(r){
  const res=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:r.id,answer:r.answer,memo:r.memo,state:r.state})});
  if(!res.ok) alert('保存できなかった: '+await res.text());
  update();
}
function update(){
  const left=rows.filter(r=>r.state==='open').length;
  document.getElementById('count').textContent='未判定 '+left+' / '+rows.length;
}
function card(r){
  const d=document.createElement('div');d.className='row'+(r.state==='open'?'':' done');
  let dy=0;
  const view=document.createElement('div');view.className='view';
  const img=new Image();img.loading='lazy';
  const load=()=>img.src='/img?id='+r.id+'&dy='+dy;load();
  const move=document.createElement('div');move.className='move';
  for(const [t,n] of [['上へ',-200],['少し上',-50],['少し下',50],['下へ',200]]){
    const b=document.createElement('button');b.textContent=t;b.onclick=()=>{dy+=n;load()};move.append(b)}
  view.append(img,move);
  const side=document.createElement('div');
  const cur=document.createElement('div');cur.className='cur';cur.textContent=r.current;
  const meta=document.createElement('div');meta.className='meta';meta.textContent=r.table+' / '+r.field;
  side.append(cur,meta);
  if(r.note){const n=document.createElement('div');n.className='note';n.textContent=r.note;side.append(n)}
  const input=document.createElement('input');input.type='text';input.value=r.answer;input.placeholder='正しい名前';
  const memo=document.createElement('input');memo.type='text';memo.value=r.memo;memo.placeholder='メモ (任意)';
  const state=document.createElement('div');state.className='state';
  const show=()=>{state.textContent=LABEL[r.state];d.className='row'+(r.state==='open'?'':' done')};show();
  const set=s=>{r.state=s;r.answer=input.value.trim();r.memo=memo.value.trim();show();save(r)};
  const chips=document.createElement('div');chips.className='chips';
  for(const c of r.candidates.split(';').filter(Boolean)){
    const b=document.createElement('button');b.textContent=c;b.onclick=()=>{input.value=c;set('fix')};chips.append(b)}
  input.onblur=()=>{const v=input.value.trim();if(v!==r.answer){set(v?'fix':'open')}};
  memo.onblur=()=>{if(memo.value.trim()!==r.memo){set(r.state)}};
  input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();input.blur();
    const all=[...document.querySelectorAll('input[data-a]')];const i=all.indexOf(input);if(all[i+1])all[i+1].focus()}};
  input.dataset.a=1;
  const acts=document.createElement('div');acts.className='acts';
  for(const [t,s] of [['印字どおり','ok'],['読めない','unreadable'],['保留','skip'],['未判定に戻す','open']]){
    const b=document.createElement('button');b.textContent=t;b.onclick=()=>{if(s!=='fix'){input.value=''}set(s)};acts.append(b)}
  side.append(chips,input,acts,memo,state);
  d.append(view,side);return d;
}
function draw(){
  const all=document.querySelector('input[name=f]:checked').value==='all';
  list.replaceChildren(...rows.filter(r=>all||r.state==='open').map(card));update();
}
document.querySelectorAll('input[name=f]').forEach(e=>e.onchange=draw);
fetch('/api/rows').then(r=>r.json()).then(j=>{rows=j;draw()});
</script></html>
"""


def make_handler(root, pages):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, kind):
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == '/':
                self.send(200, PAGE.encode('utf-8'), 'text/html; charset=utf-8')
            elif url.path == '/api/rows':
                self.send(200, json.dumps(read_queue(root), ensure_ascii=False).encode('utf-8'), 'application/json')
            elif url.path == '/img':
                q = parse_qs(url.query)
                row = next((r for r in read_queue(root) if r['id'] == q.get('id', [''])[0]), None)
                if row is None:
                    return self.send(404, b'not found', 'text/plain')
                self.send(200, render(pages, row, int(q.get('dy', ['0'])[0])), 'image/png')
            else:
                self.send(404, b'not found', 'text/plain')

        def do_POST(self):
            origin = self.headers.get('Origin', '')
            if origin and urlparse(origin).netloc != self.headers.get('Host'):   # ほかのページからの書き込みを断る
                return self.send(403, b'forbidden', 'text/plain')
            if urlparse(self.path).path != '/api/save':
                return self.send(404, b'not found', 'text/plain')
            try:
                data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))).decode('utf-8'))
                save_row(root, data)
            except (ValueError, LookupError) as e:
                return self.send(400, str(e).encode('utf-8'), 'text/plain; charset=utf-8')
            self.send(200, b'ok', 'text/plain')
    return Handler


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('import')
    p.add_argument('dir')
    p.add_argument('tsv')
    p = sub.add_parser('serve')
    p.add_argument('dir')
    p.add_argument('--port', type=int, default=8766)
    p.add_argument('--no-browser', action='store_true')
    p = sub.add_parser('apply')
    p.add_argument('dir')
    p.add_argument('--source', action='append', default=[], help='ほかの疎な転記 (sparse.py の入力)')
    a = ap.parse_args(argv)
    if a.cmd == 'import':
        added, total = import_rows(a.dir, a.tsv)
        print(f'{added} 件を足した (全部で {total} 件) → {queue_path(a.dir)}')
    elif a.cmd == 'apply':
        apply_rows(a.dir, a.source)
    else:
        if not read_queue(a.dir):
            sys.exit('review.tsv に項目が無い．先に import する')
        server = ThreadingHTTPServer(('127.0.0.1', a.port), make_handler(a.dir, Pages(a.dir)))
        url = f'http://127.0.0.1:{a.port}/'
        print(f'{url} を開く．終わるときは Ctrl+C')
        if not a.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
