#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""植生調査票の読み取り結果 (JSON) を，調査票の画像と見比べながらブラウザで直す簡易サーバ.

    python review.py serve data.json --image sheet1.png [sheet2.png ...] [--names names.tsv]
    python review.py serve data.json --image p1.png --port 8767 --no-browser

- 左に調査票の画像 (ホイールで拡大縮小，ドラッグで移動)，右に地点情報の欄と種の表が並ぶ.
  欄はその場で直せ，行の追加・削除・並べ替え，列の追加もできる.
- 「保存」(Ctrl+S) で data.json に書き戻す. 初回の保存で data.json.bak を残す (以後は上書きしない).
  空にした欄は JSON から消す (build_csv.py は無い列を空欄／NA にする).
  保存のたびに build_csv.py と同じ点検を走らせ，警告 (階層名・学名が空・出現種数の食い違い など) を画面に出す.
- 色が付く行: 種名の照合 (check_names.py --report の names.tsv) が none・similar・ambiguous の行と，
  読み取りで「要確認」を付けた行. site の「要確認」は {列名: 理由}，species の「要確認」は理由の文字列.
  「要確認の行だけ」で絞り込める. 直したら「要確認」の欄を空にすれば印が消える.
- --image は sheets の順に対応させる (1 枚目の画像 = 1 枚目の調査票). 見せるのはここに渡した画像だけ.
- CSV は作り直さない. 直したあとで build_csv.py を流す.
- サーバは 127.0.0.1 だけで待ち受け，ほかのページからの書き込みは断る. 標準ライブラリだけで動く.
"""
import argparse
import copy
import csv
import json
import mimetypes
import os
import shutil
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_csv as B  # noqa: E402  (同じディレクトリの build_csv.py)

FLAG_STATUS = ("none", "similar", "ambiguous")
SPECIES_ORDER = ["階層", "種名", "被度・群度", "被度階級値", "群度", "被度百分率", "学名", "科名",
                 "種名（公開用）", "絶滅危惧種フラグ", "行番号", "要確認"]
SITE_ORDER = B.SITE_COLS + ["出現種数"]


def read_names(path):
    """check_names.py --report の TSV から {入力の種名: {status, hub, candidates, note}} を作る."""
    out = {}
    if not path:
        return out
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            name = (r.get("入力") or "").strip()
            if name:
                out[name] = {"status": r.get("状態", ""), "hub": r.get("標準和名", ""),
                             "candidates": [c for c in (r.get("候補") or "").split("，") if c],
                             "note": r.get("備考", "")}
    return out


def clean_value(v):
    if v is None:
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    return str(v).strip()


def clean_site(site):
    if not isinstance(site, dict):
        raise ValueError("site は辞書")
    out = {}
    for k, v in site.items():
        k = str(k).strip()
        if not k:
            continue
        if k == "要確認":
            if isinstance(v, dict):
                flags = {str(a): str(b).strip() for a, b in v.items() if str(b).strip()}
                if flags:
                    out[k] = flags
            continue
        v = clean_value(v)
        if v != "":
            out[k] = v
    return out


def clean_species(species):
    if not isinstance(species, list):
        raise ValueError("species はリスト")
    out = []
    for sp in species:
        if not isinstance(sp, dict):
            raise ValueError("species の要素は辞書")
        row = {}
        for k, v in sp.items():
            k = str(k).strip()
            v = clean_value(v)
            if k and v != "":
                row[k] = v
        if row:                      # 全部空の行は捨てる
            out.append(row)
    return out


def sheet_warnings(i, sheet):
    """build_csv.py と同じ点検 (被度・群度を分けてから) を 1 枚分走らせる."""
    s = {"site": dict(sheet.get("site", {})), "species": [dict(x) for x in sheet.get("species", [])]}
    for sp in s["species"]:
        B.split_cover(sp)
    w = []
    B.check_sheet(i, s, w)
    return w


class Store:
    def __init__(self, data_path, images=(), names_path=None):
        self.path = os.path.abspath(data_path)
        self.images = [os.path.abspath(p) for p in images]
        self.names = read_names(names_path)
        self.lock = threading.Lock()
        missing = [p for p in self.images if not os.path.exists(p)]
        if missing:
            raise FileNotFoundError("画像が無い: " + ", ".join(missing))
        self.load()   # 読めない JSON はここで止める

    def load(self):
        with open(self.path, encoding="utf-8-sig") as fh:
            return json.load(fh)

    @staticmethod
    def sheets_of(data):
        return data["sheets"] if "sheets" in data else [data]

    def payload(self):
        data = self.load()
        sheets = []
        for i, s in enumerate(self.sheets_of(data)):
            sheets.append({"site": s.get("site", {}), "species": s.get("species", []),
                           "image": i if i < len(self.images) else None,
                           "image_name": os.path.basename(self.images[i]) if i < len(self.images) else "",
                           "warnings": sheet_warnings(i + 1, s)})
        return {"file": os.path.basename(self.path), "sheets": sheets, "names": self.names,
                "site_cols": SITE_ORDER, "species_cols": SPECIES_ORDER + [c for c in B.SPECIES_COLS if c not in SPECIES_ORDER],
                "layers": B.LAYERS, "bak": os.path.exists(self.path + ".bak")}

    def save(self, idx, site, species):
        site, species = clean_site(site), clean_species(species)
        with self.lock:
            data = self.load()
            sheets = self.sheets_of(data)
            if not isinstance(idx, int) or not 0 <= idx < len(sheets):
                raise ValueError("調査票の番号が範囲外: %r" % idx)
            sheets[idx]["site"] = site
            sheets[idx]["species"] = species
            bak = self.path + ".bak"
            if not os.path.exists(bak):
                shutil.copy2(self.path, bak)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, self.path)
        return sheet_warnings(idx + 1, sheets[idx])


PAGE = r"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>調査票の確認</title>
<style>
:root{--bg:#fafaf7;--fg:#222;--mut:#777;--line:#ddd;--flag:#fff1d6;--bad:#ffe0e0;--acc:#1f5fa8;--sel:#e8f0fb}
@media (prefers-color-scheme: dark){:root{--bg:#1d1f21;--fg:#e6e6e6;--mut:#999;--line:#444;--flag:#4a3b18;--bad:#5a2626;--acc:#7fb0ff;--sel:#26364d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,"Yu Gothic UI",sans-serif}
header{position:sticky;top:0;z-index:5;display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:6px 12px;background:var(--bg);border-bottom:1px solid var(--line)}
header h1{font-size:15px;margin:0}.mut{color:var(--mut)}
button{font:inherit;padding:3px 10px;border:1px solid var(--line);border-radius:4px;background:transparent;color:inherit;cursor:pointer}
button.pri{background:var(--acc);color:#fff;border-color:var(--acc)}button:disabled{opacity:.5}
main{display:grid;grid-template-columns:minmax(300px,1fr) minmax(420px,1.15fr);height:calc(100vh - 46px)}
#view{position:relative;overflow:hidden;border-right:1px solid var(--line);background:#888;cursor:grab;touch-action:none}
#view.drag{cursor:grabbing}#view img{position:absolute;left:0;top:0;transform-origin:0 0;user-select:none;-webkit-user-drag:none;max-width:none}
#zoom{position:absolute;right:8px;top:8px;display:flex;gap:4px;z-index:2}#zoom button{background:var(--bg)}
#noimg{padding:20px;color:#fff}
#edit{overflow:auto;padding:10px 14px 60px}
h2{font-size:14px;margin:14px 0 6px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid var(--line);padding:1px 3px;vertical-align:top}
th{background:var(--sel);font-weight:600;text-align:left;white-space:nowrap}
input{font:inherit;width:100%;border:0;background:transparent;color:inherit;padding:2px}
input:focus{outline:2px solid var(--acc);background:var(--bg)}
tr.flag td{background:var(--flag)}tr.bad td{background:var(--bad)}td.ops{white-space:nowrap;width:1%}
td.ops button{padding:0 5px}.why{font-size:12px;color:var(--mut)}
#site td.k{width:11em;white-space:nowrap}
#warn{margin:6px 0;padding:6px 10px;border-left:3px solid #c0392b;background:var(--bad);display:none;white-space:pre-wrap;font-size:13px}
#toast{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);background:#333;color:#fff;padding:6px 14px;border-radius:4px;display:none}
@media (max-width:800px){main{grid-template-columns:1fr;height:auto}#view{height:55vh}}
</style></head><body>
<header><h1 id="title">調査票の確認</h1><select id="sheet"></select>
<label><input type="checkbox" id="only" style="width:auto"> 要確認の行だけ</label>
<span id="count" class="mut"></span><span id="state" class="mut"></span>
<button class="pri" id="save">保存 (Ctrl+S)</button></header>
<main><div id="view"><div id="zoom"><button data-z="1.25">＋</button><button data-z="0.8">－</button><button data-z="fit">合わせる</button></div><img id="img" alt="調査票"><div id="noimg" hidden>この調査票の画像は渡されていない (--image)</div></div>
<div id="edit"><div id="warn"></div>
<h2>地点情報</h2><table id="site"></table>
<p><select id="addsite"><option value="">列を足す…</option></select></p>
<h2>種 <span class="mut" id="spn"></span></h2><table id="sp"></table>
<p><button id="addrow">行を足す</button> <select id="addcol"><option value="">列を足す…</option></select></p>
<p class="mut">色: 黄 = 要確認・照合で似た名前 (similar)，赤 = 照合で見つからない (none)・複数に当たる (ambiguous)．種名の欄にマウスを置くと照合の結果が出る．</p>
</div></main><div id="toast"></div>
<datalist id="layers"></datalist>
<script>
let DATA=null, CUR=0, DIRTY=false, SCALE=1, TX=0, TY=0;
const $=s=>document.querySelector(s), esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function toast(t){const e=$("#toast");e.textContent=t;e.style.display="block";clearTimeout(e._t);e._t=setTimeout(()=>e.style.display="none",2200)}
function dirty(v){DIRTY=v;$("#state").textContent=v?"未保存":"保存済み"}
function sheet(){return DATA.sheets[CUR]}
function nameInfo(n){return DATA.names[String(n??"").trim()]}
function rowClass(sp){const ni=nameInfo(sp["種名"]);
 if(ni&&(ni.status==="none"||ni.status==="ambiguous"))return "bad";
 if(String(sp["要確認"]??"").trim()||(ni&&ni.status==="similar"))return "flag"; return ""}
function spCols(){const s=sheet(), have=new Set(); s.species.forEach(r=>Object.keys(r).forEach(k=>have.add(k)));
 ["階層","種名","学名","要確認"].forEach(k=>have.add(k)); if(!have.has("被度階級値"))have.add("被度・群度");
 (s._extra||[]).forEach(k=>have.add(k));
 const order=DATA.species_cols.filter(c=>have.has(c)); have.forEach(k=>{if(!order.includes(k))order.push(k)}); return order}
function load(){fetch("/api/data").then(r=>r.json()).then(d=>{DATA=d;$("#title").textContent=d.file;
 $("#sheet").innerHTML=d.sheets.map((s,i)=>`<option value="${i}">${i+1}. ${esc(s.site["調査年月日"]||"")} ${esc(s.site["市郡町村区名"]||s.site["群落名"]||"")} ${esc(s.image_name)}</option>`).join("");
 $("#sheet").hidden=d.sheets.length<2; $("#layers").innerHTML=d.layers.map(l=>`<option value="${l}">`).join("");
 show(0); dirty(false)})}
function show(i){CUR=i;$("#sheet").value=i;const s=sheet();
 if(s.image===null){$("#img").hidden=true;$("#noimg").hidden=false}else{$("#noimg").hidden=true;const im=$("#img");im.hidden=false;im.onload=fit;im.src="/img?i="+s.image}
 renderSite();renderSp();warn(s.warnings)}
function warn(w){const e=$("#warn");if(w&&w.length){e.style.display="block";e.textContent="点検 ("+w.length+" 件):\n"+w.join("\n")}else e.style.display="none"}
function renderSite(){const s=sheet(), f=s.site["要確認"]||{};
 const keys=Object.keys(s.site).filter(k=>k!=="要確認"); Object.keys(f).forEach(k=>{if(!keys.includes(k))keys.push(k)});
 keys.sort((a,b)=>{const ia=DATA.site_cols.indexOf(a),ib=DATA.site_cols.indexOf(b);return (ia<0?999:ia)-(ib<0?999:ib)});
 $("#site").innerHTML=keys.map(k=>`<tr class="${f[k]?"flag":""}"><td class="k">${esc(k)}${f[k]?`<div class="why">要確認: ${esc(f[k])} <button data-unflag="${esc(k)}">確認済み</button></div>`:""}</td><td><input data-site="${esc(k)}" value="${esc(s.site[k])}"></td></tr>`).join("");
 $("#addsite").innerHTML=`<option value="">列を足す…</option>`+DATA.site_cols.filter(c=>!keys.includes(c)).map(c=>`<option>${esc(c)}</option>`).join("")}
function renderSp(){const s=sheet(), cols=spCols(), only=$("#only").checked;
 let h="<tr><th></th>"+cols.map(c=>`<th>${esc(c)}</th>`).join("")+"<th></th></tr>";
 s.species.forEach((r,i)=>{const cl=rowClass(r); if(only&&!cl)return; const ni=nameInfo(r["種名"]);
  const tip=ni?`照合: ${ni.status}${ni.hub?" → "+ni.hub:""}${ni.candidates.length?" 候補: "+ni.candidates.join("，"):""}${ni.note?" ("+ni.note+")":""}`:"";
  h+=`<tr class="${cl}" data-row="${i}"><td class="mut">${i+1}</td>`+cols.map(c=>`<td${c==="種名"&&tip?` title="${esc(tip)}"`:""}><input data-r="${i}" data-c="${esc(c)}" value="${esc(r[c])}"${c==="階層"?' list="layers" style="width:3.5em"':""}></td>`).join("")+
   `<td class="ops"><button data-op="up" data-i="${i}" title="上へ">↑</button><button data-op="down" data-i="${i}" title="下へ">↓</button><button data-op="ins" data-i="${i}" title="下に行を足す">＋</button><button data-op="del" data-i="${i}" title="行を消す">✕</button></td></tr>`});
 $("#sp").innerHTML=h;
 const names=new Set(s.species.map(r=>String(r["種名"]??"").trim()).filter(x=>x)), n=s.site["出現種数"];
 $("#spn").textContent=`${s.species.length} 行・種名 ${names.size}`+(n!==undefined&&n!==""?`（出現種数 ${n}${String(n)===String(names.size)?" 一致":" 不一致"}）`:"");
 $("#count").textContent=`要確認 ${s.species.filter(rowClass).length+Object.keys(s.site["要確認"]||{}).length} 件`;
 $("#addcol").innerHTML=`<option value="">列を足す…</option>`+DATA.species_cols.filter(c=>!cols.includes(c)).map(c=>`<option>${esc(c)}</option>`).join("")}
document.addEventListener("input",e=>{const t=e.target;
 if(t.dataset.site!==undefined){sheet().site[t.dataset.site]=t.value;dirty(true)}
 else if(t.dataset.r!==undefined){const r=sheet().species[+t.dataset.r];r[t.dataset.c]=t.value;dirty(true);
  const tr=t.closest("tr");tr.className=rowClass(r)}});
document.addEventListener("change",e=>{const t=e.target;
 if(t.dataset.r!==undefined&&(t.dataset.c==="種名"||t.dataset.c==="要確認"))renderSp()});
document.addEventListener("click",e=>{const t=e.target.closest("button");if(!t)return;
 if(t.dataset.op){const a=sheet().species,i=+t.dataset.i;
  if(t.dataset.op==="up"&&i>0)[a[i-1],a[i]]=[a[i],a[i-1]];
  else if(t.dataset.op==="down"&&i<a.length-1)[a[i+1],a[i]]=[a[i],a[i+1]];
  else if(t.dataset.op==="ins")a.splice(i+1,0,{"階層":a[i]["階層"]||""});
  else if(t.dataset.op==="del"){if(!confirm(`${i+1} 行目 (${a[i]["種名"]||""}) を消します`))return;a.splice(i,1)}
  dirty(true);renderSp();return}
 if(t.dataset.unflag!==undefined){const f=sheet().site["要確認"];delete f[t.dataset.unflag];if(!Object.keys(f).length)delete sheet().site["要確認"];dirty(true);renderSite();renderSp();return}
 if(t.dataset.z){if(t.dataset.z==="fit")fit();else zoomAt(+t.dataset.z,$("#view").clientWidth/2,$("#view").clientHeight/2);return}});
$("#addrow").onclick=()=>{const a=sheet().species;a.push({"階層":a.length?a[a.length-1]["階層"]||"":""});dirty(true);renderSp();
 const ins=document.querySelectorAll(`[data-r="${a.length-1}"]`);if(ins[1])ins[1].focus()};
$("#addcol").onchange=e=>{const c=e.target.value;if(!c)return;const s=sheet();s._extra=(s._extra||[]).concat([c]);renderSp()};
$("#addsite").onchange=e=>{const c=e.target.value;if(!c)return;sheet().site[c]="";renderSite();const i=document.querySelector(`[data-site="${CSS.escape(c)}"]`);if(i)i.focus()};
$("#only").onchange=renderSp;
$("#sheet").onchange=e=>{show(+e.target.value)};
async function save(){const s=sheet();$("#save").disabled=true;
 try{const r=await fetch("/api/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sheet:CUR,site:s.site,species:s.species})});
  const j=await r.json();if(!j.ok){toast("保存できません: "+j.error);return}
  const extra=s._extra; const d=await (await fetch("/api/data")).json(); DATA=d; if(extra)sheet()._extra=extra;
  show(CUR); dirty(false); toast(j.bak?"保存した (初回の写しは "+j.bak+")":"保存した")}
 finally{$("#save").disabled=false}}
$("#save").onclick=save;
document.addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key==="s"){e.preventDefault();save()}});
window.addEventListener("beforeunload",e=>{if(DIRTY){e.preventDefault();e.returnValue=""}});
// 画像: ホイールで拡大縮小，ドラッグで移動
function apply(){$("#img").style.transform=`translate(${TX}px,${TY}px) scale(${SCALE})`}
function fit(){const v=$("#view"),im=$("#img");if(!im.naturalWidth)return;SCALE=Math.min(v.clientWidth/im.naturalWidth,v.clientHeight/im.naturalHeight);TX=(v.clientWidth-im.naturalWidth*SCALE)/2;TY=0;apply()}
function zoomAt(f,x,y){const ns=Math.min(12,Math.max(0.05,SCALE*f));TX=x-(x-TX)*ns/SCALE;TY=y-(y-TY)*ns/SCALE;SCALE=ns;apply()}
$("#view").addEventListener("wheel",e=>{e.preventDefault();const b=$("#view").getBoundingClientRect();zoomAt(e.deltaY<0?1.15:1/1.15,e.clientX-b.left,e.clientY-b.top)},{passive:false});
let drag=null;$("#view").addEventListener("pointerdown",e=>{if(e.target.closest("#zoom"))return;drag={x:e.clientX,y:e.clientY,tx:TX,ty:TY};$("#view").classList.add("drag");$("#view").setPointerCapture(e.pointerId)});
$("#view").addEventListener("pointermove",e=>{if(!drag)return;TX=drag.tx+e.clientX-drag.x;TY=drag.ty+e.clientY-drag.y;apply()});
$("#view").addEventListener("pointerup",()=>{drag=null;$("#view").classList.remove("drag")});
window.addEventListener("resize",()=>{});
load();
</script></body></html>
"""


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
            if parts.path == "/":
                return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if parts.path == "/api/data":
                try:
                    return self._json(store.payload())
                except Exception as e:  # noqa: BLE001  (JSON が壊れているときなど，画面に理由を出す)
                    return self._json({"ok": False, "error": str(e)}, 500)
            if parts.path == "/img":
                try:
                    i = int(parse_qs(parts.query).get("i", [""])[0])
                    path = store.images[i]
                except (ValueError, IndexError):
                    return self._send(404, b"not found", "text/plain")
                with open(path, "rb") as fh:
                    body = fh.read()
                return self._send(200, body, mimetypes.guess_type(path)[0] or "application/octet-stream")
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            origin = self.headers.get("Origin", "")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):   # ほかのページからの書き込みを断る
                return self._json({"ok": False, "error": "forbidden"}, 403)
            if urlparse(self.path).path != "/api/save":
                return self._json({"ok": False, "error": "not found"}, 404)
            try:
                n = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(n).decode("utf-8"))
                had_bak = os.path.exists(store.path + ".bak")
                warnings = store.save(data.get("sheet"), data.get("site", {}), data.get("species", []))
            except (ValueError, KeyError, UnicodeDecodeError) as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            return self._json({"ok": True, "warnings": warnings,
                               "bak": "" if had_bak else os.path.basename(store.path) + ".bak"})
    return Handler


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("serve", help="ブラウザで直す画面を開く")
    p.add_argument("data", help="読み取り結果の JSON (build_csv.py に渡すもの)")
    p.add_argument("--image", nargs="*", default=[], help="調査票の画像 (sheets の順)")
    p.add_argument("--names", help="check_names.py --report の TSV (照合で引っかかった種名に色を付ける)")
    p.add_argument("--port", type=int, default=8767, help="既定 8767 (8766 は ja-manuscript と veg-table-to-csv が使う)")
    p.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    a = ap.parse_args(argv)
    store = Store(a.data, a.image, a.names)
    n = len(Store.sheets_of(store.load()))
    if store.images and len(store.images) != n:
        print("注意: 調査票 %d 枚に画像 %d 枚 (順に対応させる)" % (n, len(store.images)))
    server = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(store))
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    print("調査票 %d 枚．保存先: %s" % (n, store.path))
    print("%s を開く (終了は Ctrl+C)" % url, flush=True)
    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
