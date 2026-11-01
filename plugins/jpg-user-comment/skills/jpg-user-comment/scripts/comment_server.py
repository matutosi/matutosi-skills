"""CSV のコメントを，写真を見ながらブラウザで直す簡易サーバ．

    python scripts/comment_server.py comments.csv
    python scripts/comment_server.py comments.csv --base photos/ --port 8765 --no-browser

ブラウザの左に写真，右にコメント欄が縦に並ぶ．欄から離れた時点で CSV に書き戻す．
**写真そのものは書き換えない**．直し終えたら jpg_comment.py の import で写真へ書き戻す
(`--overwrite-all`．既定の --append だと，もとのコメントに継ぎ足される)．

- CSV の `filename` は絶対パスか，`--base` 基準の相対パス (既定は CSV と同じディレクトリ)．
- 「写真を削除」は CSV の隣の `_trash/` へ移すだけで，消さない (`_trash/deleted.csv` に記録)．
- 見せる写真と書き換える行は，CSV に載っているものだけ．サーバは 127.0.0.1 だけで待ち受ける．
- 標準ライブラリだけで動く．Pillow があれば縮小と表示の回転が効く (無ければ原寸を送る)．
"""
import argparse
import csv
import datetime
import html
import io
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

try:
    from PIL import Image
except ImportError:
    Image = None

WIDTHS = [400, 600, 800, 1000, 1200, 1600]
DEFAULT_WIDTH = 800


class Store:
    """CSV の読み書きと，写真の移動．書き込みは 1 つずつ行う"""

    def __init__(self, csv_path, base=None):
        self.csv_path = os.path.abspath(csv_path)
        self.base = os.path.abspath(base or os.path.dirname(self.csv_path))
        self.trash_dir = os.path.join(os.path.dirname(self.csv_path), "_trash")
        self.trashed = set()                    # このサーバが移した写真 (見せてよい)
        self.lock = threading.Lock()

    def read(self):
        """(見出し, 本体の行) を返す．見出しは省略できる"""
        with open(self.csv_path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.reader(handle))
        if rows and rows[0] and rows[0][0].strip().lower() == "filename":
            return rows[0], rows[1:]
        return None, rows

    def write(self, header, body):
        tmp = self.csv_path + ".tmp"            # 途中で失敗しても元の CSV は壊れない
        with open(tmp, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            if header:
                writer.writerow(header)
            writer.writerows(body)
        os.replace(tmp, self.csv_path)

    def resolve(self, key):
        return key if os.path.isabs(key) else os.path.normpath(os.path.join(self.base, key))

    def rows(self):
        out = []
        for row in self.read()[1]:
            if row and row[0].strip():
                path = self.resolve(row[0])
                try:
                    name = os.path.relpath(path, self.base)
                except ValueError:              # 別のドライブ
                    name = path
                out.append({"path": row[0], "name": name, "comment": row[1] if len(row) > 1 else ""})
        return out

    def image_path(self, key):
        """見せてよい写真の実際のパス．CSV に無ければ None"""
        if key in self.trashed:
            return key
        return self.resolve(key) if any(r["path"] == key for r in self.rows()) else None

    def save(self, key, comment):
        with self.lock:
            header, body = self.read()
            for row in body:
                if row and row[0] == key:
                    row[1:2] = [comment]
                    self.write(header, body)
                    return True
        return False

    def delete(self, key):
        """写真を _trash へ移し，CSV からその行を落とす．(何行目か, 移した先, コメント) を返す"""
        path = self.resolve(key)
        try:
            rel = os.path.relpath(path, self.base)
        except ValueError:
            rel = os.path.basename(path)
        if rel.startswith(".."):
            rel = os.path.basename(path)
        trash = os.path.join(self.trash_dir, rel)
        with self.lock:
            header, body = self.read()
            index = next((i for i, row in enumerate(body) if row and row[0] == key), None)
            if index is None:
                raise LookupError("CSV に該当する行が無い")
            comment = body[index][1] if len(body[index]) > 1 else ""
            os.makedirs(os.path.dirname(trash), exist_ok=True)
            stem, ext = os.path.splitext(trash)
            n = 2
            while os.path.exists(trash):        # 同名があれば連番を足す
                trash = "%s_%d%s" % (stem, n, ext)
                n += 1
            os.replace(path, trash)
            del body[index]
            self.write(header, body)
            self.trashed.add(trash)
            with open(os.path.join(self.trash_dir, "deleted.csv"), "a", encoding="utf-8-sig", newline="") as handle:
                csv.writer(handle).writerow(
                    [datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), index, key, trash, comment])
        return index, trash, comment

    def restore(self, key, trash, comment, index):
        """delete を取り消す．写真を元へ戻し，CSV の元の位置へ行を挿し直す"""
        with self.lock:
            if trash not in self.trashed or not os.path.isfile(trash):
                raise LookupError("移した写真が無い")
            path = self.resolve(key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            os.replace(trash, path)
            self.trashed.discard(trash)
            header, body = self.read()
            body.insert(max(0, min(index, len(body))), [key, comment])
            self.write(header, body)


def render_image(path, width, rotate=0):
    """指定の幅に収めた JPEG のバイト列を返す．元のファイルには手を触れない"""
    if Image is None or (width == 0 and not rotate):
        with open(path, "rb") as handle:
            return handle.read()
    with Image.open(path) as im:
        if width:
            im.draft("RGB", (width * 2, width * 2))   # JPEG を粗く復号して速くする
        im = im.convert("RGB")
        if rotate:
            im = im.rotate(-rotate, expand=True)      # 時計回りに rotate 度
        if width:
            im.thumbnail((width, int(width * 0.75)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        return buf.getvalue()


PAGE = u"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>写真コメント編集 __NAME__</title>
<style>
 :root { --bg:#faf9f7; --fg:#23201c; --line:#ddd8d0; --accent:#3b6ea5; }
 * { box-sizing: border-box; }
 body { margin:0; background:var(--bg); color:var(--fg);
        font-family: "Yu Gothic UI","Meiryo",system-ui,sans-serif; font-size:14px; }
 header { position:sticky; top:0; z-index:10; background:#fff; border-bottom:1px solid var(--line);
          padding:10px 16px; display:flex; gap:18px; align-items:center; flex-wrap:wrap;
          box-shadow:0 1px 4px rgba(0,0,0,.06); }
 header h1 { font-size:16px; margin:0; font-weight:600; }
 header label { display:flex; gap:6px; align-items:center; }
 select { font:inherit; padding:3px 6px; }
 #count { color:#6b6560; }
 #status { margin-left:auto; min-width:9em; text-align:right; color:#6b6560; }
 #status.ok { color:#2e7d32; }
 #status.err { color:#c0392b; }
 main { padding:16px; }
 .row { display:flex; gap:16px; background:#fff; border:1px solid var(--line);
        border-radius:6px; padding:12px; margin-bottom:14px; align-items:flex-start; }
 .row.empty { border-left:4px solid #e0a030; }
 .row.saving { outline:2px solid #f0c060; }
 .row.saved  { outline:2px solid #7fc47f; }
 .row.trashed { border-left:4px solid #c0392b; opacity:.85; }
 .thumb { position:relative; flex:0 0 auto; max-width:72%; background:#f0ede8;
          display:flex; align-items:center; justify-content:center; }
 .thumb img { display:block; max-width:100%; height:auto; }
 .thumb.trashed img { filter:grayscale(1) brightness(.7); }
 .badge { position:absolute; top:8px; left:8px; background:#c0392b; color:#fff;
          font-weight:600; padding:3px 8px; border-radius:4px; font-size:12px; }
 .side { flex:1 1 auto; min-width:260px; display:flex; flex-direction:column;
         gap:8px; justify-content:center; align-self:stretch; }
 .name { font-family:Consolas,monospace; font-size:12px; color:#6b6560; word-break:break-all; }
 .no { font-weight:600; color:var(--accent); }
 textarea { font:inherit; width:100%; min-height:5em; padding:8px; resize:vertical;
            border:1px solid var(--line); border-radius:4px; background:#fffdfa; }
 textarea:focus { outline:2px solid var(--accent); border-color:transparent; }
 .hint { color:#8b857f; font-size:12px; }
 .tools { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
 button { font:inherit; padding:3px 10px; border:1px solid var(--line); border-radius:4px;
          background:#fff; cursor:pointer; }
 button:hover { background:#f2efe9; }
 button.big { font-size:15px; padding:8px 16px; font-weight:600; }
 button.warn:hover { background:#fdecea; border-color:#e0a0a0; }
 kbd { background:#eee; border:1px solid #ccc; border-bottom-width:2px; border-radius:3px;
       padding:0 4px; font-family:inherit; font-size:11px; }
 .thumb a { display:block; }
 .row.trashing { opacity:.4; }
</style>
</head>
<body>
<header>
  <h1>写真コメント編集 <span id="year">__NAME__</span></h1>
  <label>画像の幅
    <select id="width">__WIDTH_OPTIONS__</select>
  </label>
  <label>表示
    <select id="filter">
      <option value="all">全部</option>
      <option value="empty">コメントが空のものだけ</option>
      <option value="q">？が付くものだけ</option>
    </select>
  </label>
  <span id="count"></span>
  <span id="status"></span>
</header>
<main id="list"></main>

<script>
const HAS_PIL = __HAS_PIL__;
let ROWS = [];

const $list = document.getElementById('list');
const $width = document.getElementById('width');
const $filter = document.getElementById('filter');
const $count = document.getElementById('count');
const $status = document.getElementById('status');

function setStatus(text, cls) {
  $status.textContent = text;
  $status.className = cls || '';
  if (cls === 'ok') setTimeout(() => { if ($status.textContent === text) $status.textContent = ''; }, 1600);
}

function visible(r) {
  const f = $filter.value;
  if (f === 'empty') return r.comment.trim() === '';
  if (f === 'q') return r.comment.indexOf('？') >= 0 || r.comment.indexOf('?') >= 0;
  return true;
}

// 表示だけの回転を覚えておく (元のファイルは変えない)
const ROT = JSON.parse(localStorage.getItem('photoEditRot') || '{}');
function rotOf(path) { return ROT[path] || 0; }
function setRot(path, deg) {
  if (deg) ROT[path] = deg; else delete ROT[path];
  localStorage.setItem('photoEditRot', JSON.stringify(ROT));
}

function imgUrl(path, w) {
  return '/img?w=' + w + '&r=' + rotOf(path) + '&p=' + encodeURIComponent(path);
}

function render() {
  const w = parseInt($width.value, 10);
  const shown = ROWS.filter(visible);
  const empties = ROWS.filter(r => r.comment.trim() === '').length;
  $count.textContent = '表示 ' + shown.length + ' / 全 ' + ROWS.length + ' 枚 (空 ' + empties + ')';
  $list.textContent = '';
  const frag = document.createDocumentFragment();
  let prevTa = null;          // 直前の行の textarea (「上のコメントを複写」用)
  for (const r of shown) {
    const above = prevTa;
    const trashed = !!r.trashed;
    const row = document.createElement('div');
    row.className = 'row' + (r.comment.trim() === '' ? ' empty' : '') + (trashed ? ' trashed' : '');
    row.dataset.path = r.path;

    const thumb = document.createElement('div');
    thumb.className = 'thumb' + (trashed ? ' trashed' : '');
    let img, link;
    if (trashed) {
      thumb.style.width = '200px';
      img = document.createElement('img');
      img.loading = 'lazy';
      img.decoding = 'async';
      img.src = imgUrl(r.trashInfo.trash, 200);
      img.alt = r.name;
      img.title = r.name + ' (削除済み)';
      const badge = document.createElement('div');
      badge.className = 'badge';
      badge.textContent = '削除済み';
      thumb.appendChild(img);
      thumb.appendChild(badge);
    } else {
      thumb.style.width = (w === 0 ? 'auto' : w + 'px');   // Pillow が無いときは原寸をこの幅で見せる
      link = document.createElement('a');
      link.target = '_blank';
      link.rel = 'noopener';
      link.title = 'クリックで原寸表示 (別ページ)';
      img = document.createElement('img');
      img.loading = 'lazy';
      img.decoding = 'async';
      img.src = imgUrl(r.path, w);
      img.alt = r.name;
      img.title = r.name;
      link.href = imgUrl(r.path, 0);
      link.appendChild(img);
      thumb.appendChild(link);
    }

    const side = document.createElement('div');
    side.className = 'side';
    const name = document.createElement('div');
    name.className = 'name';
    const no = document.createElement('span');
    no.className = 'no';
    no.textContent = (r.index + 1) + '.';
    name.appendChild(no);
    name.appendChild(document.createTextNode(' ' + r.name));
    const ta = document.createElement('textarea');
    ta.value = r.comment;
    ta.spellcheck = false;
    ta.disabled = trashed;
    ta.addEventListener('change', () => save(row, r, ta));
    ta.addEventListener('keydown', ev => {
      if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); ta.blur(); }
    });

    const copyAbove = document.createElement('button');
    copyAbove.className = 'big';
    copyAbove.textContent = '↑ 上のコメントを複写';
    copyAbove.disabled = !above || trashed;
    copyAbove.onclick = () => {
      if (!above) return;
      ta.value = above.value;
      save(row, r, ta);
    };

    const tools = document.createElement('div');
    tools.className = 'tools';
    const rotL = document.createElement('button');
    rotL.textContent = '⟲ 左90°';
    rotL.title = '表示だけ回す (元のファイルは変えない)';
    rotL.disabled = trashed || !HAS_PIL;
    rotL.onclick = () => { setRot(r.path, (rotOf(r.path) + 270) % 360); img.src = imgUrl(r.path, w); link.href = imgUrl(r.path, 0); };
    const rotR = document.createElement('button');
    rotR.textContent = '⟳ 右90°';
    rotR.title = '表示だけ回す (元のファイルは変えない)';
    rotR.disabled = trashed || !HAS_PIL;
    rotR.onclick = () => { setRot(r.path, (rotOf(r.path) + 90) % 360); img.src = imgUrl(r.path, w); link.href = imgUrl(r.path, 0); };
    const clearQ = document.createElement('button');
    clearQ.textContent = '？を削除';
    clearQ.title = 'コメント中の ? と ？ を取り除く';
    clearQ.disabled = trashed;
    clearQ.onclick = () => {
      ta.value = ta.value.replace(/[?？]/g, '').replace(/[ 　]{2,}/g, ' ').trim();
      save(row, r, ta);
    };
    const clearComment = document.createElement('button');
    clearComment.className = 'warn';
    clearComment.textContent = 'コメント削除';
    clearComment.disabled = trashed;
    clearComment.onclick = () => {
      if (ta.value.trim() === '') return;
      r.commentBackup = ta.value;
      restoreComment.disabled = false;
      ta.value = '';
      save(row, r, ta);
    };
    const restoreComment = document.createElement('button');
    restoreComment.textContent = 'コメントを復元';
    restoreComment.title = 'このブラウザを閉じるまで, 削除前のコメントに戻せる';
    restoreComment.disabled = trashed || r.commentBackup == null;
    restoreComment.onclick = () => {
      if (r.commentBackup == null) return;
      ta.value = r.commentBackup;
      save(row, r, ta);
    };
    const searchText = document.createElement('button');
    searchText.textContent = 'コメントで画像検索';
    searchText.title = 'コメント欄のテキストで Google 画像検索';
    searchText.disabled = trashed;
    searchText.onclick = () => {
      const q = ta.value.trim();
      if (!q) { alert('コメントが空です'); return; }
      window.open('https://www.google.com/search?tbm=isch&q=' + encodeURIComponent(q), '_blank');
    };
    const searchImage = document.createElement('button');
    searchImage.textContent = '画像で画像検索';
    searchImage.title = 'この写真そのもので Google 画像検索 (逆画像検索)';
    searchImage.disabled = trashed;
    searchImage.onclick = () => reverseImageSearch(r, w, searchImage);
    const trashBtn = document.createElement('button');
    trashBtn.className = 'warn';
    trashBtn.textContent = '写真を削除';
    trashBtn.title = 'CSV の隣の _trash へ移す (このブラウザを閉じるまで元に戻せる)';
    trashBtn.disabled = trashed;
    trashBtn.onclick = () => deletePhoto(row, r);
    const restorePhotoBtn = document.createElement('button');
    restorePhotoBtn.textContent = '写真を復活';
    restorePhotoBtn.title = '元の場所へ戻す';
    restorePhotoBtn.disabled = !trashed;
    restorePhotoBtn.onclick = () => restorePhoto(row, r);
    const hint = document.createElement('span');
    hint.className = 'hint';
    hint.innerHTML = '欄を離れると保存 (<kbd>Ctrl</kbd>+<kbd>Enter</kbd> でも保存)';
    tools.appendChild(rotL); tools.appendChild(rotR); tools.appendChild(clearQ);
    tools.appendChild(clearComment); tools.appendChild(restoreComment);
    tools.appendChild(searchText); tools.appendChild(searchImage);
    tools.appendChild(trashBtn); tools.appendChild(restorePhotoBtn); tools.appendChild(hint);

    side.appendChild(name); side.appendChild(copyAbove); side.appendChild(ta); side.appendChild(tools);
    row.appendChild(thumb); row.appendChild(side);
    frag.appendChild(row);
    prevTa = ta;
  }
  $list.appendChild(frag);
}

// JPEG の Blob を PNG に変換する (クリップボードへの画像コピーは PNG が確実)
function toPngBlob(blob) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext('2d').drawImage(img, 0, 0);
      URL.revokeObjectURL(img.src);
      canvas.toBlob(b => b ? resolve(b) : reject(new Error('PNG への変換に失敗')), 'image/png');
    };
    img.onerror = () => { URL.revokeObjectURL(img.src); reject(new Error('画像の読み込みに失敗')); };
    img.src = URL.createObjectURL(blob);
  });
}

// Google の /searchbyimage/upload は自動送信を 403 で弾くようになったため,
// 画像をクリップボードへコピーし, Google 画像検索を開いて Ctrl+V で貼り付けてもらう.
async function reverseImageSearch(r, w, btn) {
  const original = btn.textContent;
  btn.disabled = true; btn.textContent = '準備中…';
  try {
    if (!navigator.clipboard || !window.ClipboardItem) {
      throw new Error('このブラウザはクリップボードへの画像コピーに対応していません');
    }
    const resp = await fetch(imgUrl(r.path, 0));
    if (!resp.ok) throw new Error('画像の取得に失敗');
    const blob = await resp.blob();
    const png = await toPngBlob(blob);
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
    window.open('https://images.google.com/', '_blank');
    setStatus('画像をコピーしました. 開いたタブの検索欄に Ctrl+V で貼り付けてください', 'ok');
  } catch (e) {
    setStatus('画像検索を開けません: ' + e.message, 'err');
    alert('画像検索を開けませんでした\\n' + e.message +
          '\\n\\n(このブラウザではコピーできない場合, 画像を右クリックし' +
          '「Google で画像を検索」を選んでください)');
  } finally {
    btn.disabled = false; btn.textContent = original;
  }
}

async function deletePhoto(row, r) {
  row.classList.add('trashing');
  setStatus('削除中…');
  try {
    const res = await fetch('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: r.path })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || ('HTTP ' + res.status));
    r.trashed = true;
    r.trashInfo = { trash: data.trash, index: data.index, comment: data.comment };
    setStatus('削除しました (このブラウザを閉じるまで元に戻せます)', 'ok');
    render();
  } catch (e) {
    row.classList.remove('trashing');
    setStatus('削除できません: ' + e.message, 'err');
    alert('削除できませんでした\\n' + e.message);
  }
}

async function restorePhoto(row, r) {
  if (!r.trashInfo) return;
  row.classList.add('trashing');
  setStatus('復元中…');
  try {
    const res = await fetch('/api/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: r.path,
        trash: r.trashInfo.trash, comment: r.trashInfo.comment, index: r.trashInfo.index,
      })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || ('HTTP ' + res.status));
    r.trashed = false;
    r.trashInfo = null;
    setStatus('復元しました', 'ok');
    render();
  } catch (e) {
    row.classList.remove('trashing');
    setStatus('復元できません: ' + e.message, 'err');
    alert('復元できませんでした\\n' + e.message);
  }
}

async function save(row, r, ta) {
  const value = ta.value;
  if (value === r.comment) return;
  row.classList.remove('saved'); row.classList.add('saving');
  setStatus('保存中…');
  try {
    const res = await fetch('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: r.path, comment: value })
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || ('HTTP ' + res.status));
    r.comment = value;
    row.classList.remove('saving'); row.classList.add('saved');
    row.classList.toggle('empty', value.trim() === '');
    setTimeout(() => row.classList.remove('saved'), 1200);
    const empties = ROWS.filter(x => x.comment.trim() === '').length;
    $count.textContent = $count.textContent.replace(/\\(空 \\d+\\)/, '(空 ' + empties + ')');
    setStatus('保存しました', 'ok');
  } catch (e) {
    row.classList.remove('saving');
    setStatus('保存できません: ' + e.message, 'err');
    alert('保存できませんでした\\n' + e.message);
  }
}

$width.addEventListener('change', () => {
  localStorage.setItem('photoEditWidth', $width.value);
  render();
});
$filter.addEventListener('change', () => {
  localStorage.setItem('photoEditFilter', $filter.value);
  render();
});

(async function init() {
  const saved = localStorage.getItem('photoEditWidth');
  if (saved && [...$width.options].some(o => o.value === saved)) $width.value = saved;
  const savedF = localStorage.getItem('photoEditFilter');
  if (savedF) $filter.value = savedF;
  setStatus('読み込み中…');
  const res = await fetch('/api/rows');
  ROWS = await res.json();
  ROWS.forEach((r, i) => {
    r.index = i;
    r.commentBackup = null;   // 「コメント削除」の直前の値 (このブラウザを閉じるまで保持)
    r.trashed = false;
    r.trashInfo = null;       // 削除した写真の {trash, index, comment} (復活に使う)
  });
  setStatus('');
  render();
})();
</script>
</body>
</html>
"""


def make_page(name):
    options = "".join('<option value="%d"%s>%d px</option>' % (w, " selected" if w == DEFAULT_WIDTH else "", w)
                      for w in WIDTHS) + '<option value="0">原寸</option>'
    return (PAGE.replace("__NAME__", html.escape(name))
                .replace("__WIDTH_OPTIONS__", options)
                .replace("__HAS_PIL__", "true" if Image else "false"))


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            parts = urlparse(self.path)
            query = parse_qs(parts.query)
            if parts.path == "/":
                self._send(200, make_page(os.path.basename(store.csv_path)).encode("utf-8"), "text/html; charset=utf-8")
            elif parts.path == "/api/rows":
                self._json(store.rows())
            elif parts.path == "/img":
                path = store.image_path(query.get("p", [""])[0])
                rotate = int(query.get("r", ["0"])[0]) % 360
                if not path or not os.path.isfile(path):
                    return self._json({"error": "not found"}, 404)
                try:
                    body = render_image(path, int(query.get("w", [str(DEFAULT_WIDTH)])[0]),
                                        rotate if rotate in (90, 180, 270) else 0)
                except Exception as error:      # 壊れた画像でも落とさない
                    return self._json({"error": str(error)}, 500)
                self._send(200, body, "image/jpeg")
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            origin = self.headers.get("Origin", "")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):   # ほかのページからの書き込みを断る
                return self._json({"ok": False, "error": "forbidden"}, 403)
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                self._json(self.act(urlparse(self.path).path, data))
            except (ValueError, KeyError, TypeError) as error:
                self._json({"ok": False, "error": "壊れた要求: %s" % error}, 400)
            except LookupError as error:
                self._json({"ok": False, "error": str(error)}, 404)
            except OSError as error:
                self._json({"ok": False, "error": str(error)}, 500)

        def act(self, path, data):
            if path == "/api/save":
                if not store.save(data["path"], data["comment"]):
                    raise LookupError("CSV に該当する行が無い")
                return {"ok": True}
            if path == "/api/delete":
                index, trash, comment = store.delete(data["path"])
                return {"ok": True, "trash": trash, "index": index, "comment": comment}
            if path == "/api/restore":
                store.restore(data["path"], data["trash"], data["comment"], int(data["index"]))
                return {"ok": True}
            raise LookupError("not found")
    return Handler


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv", help="CSV (filename,comment)．jpg_comment.py export で作る")
    ap.add_argument("--base", help="filename を解決する基準ディレクトリ (既定: CSV と同じ場所)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.csv):
        sys.exit("CSV が無い: %s" % a.csv)
    store = Store(a.csv, a.base)
    if Image is None:
        print("Pillow が無いので，写真は原寸のまま送る (回転は使えない)")
    server = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(store))
    url = "http://127.0.0.1:%d/" % a.port
    print("%s を編集する．%s を開く (終了は Ctrl+C)" % (store.csv_path, url))
    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
