#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修正案を，差分 (と朱書きの帯の画像) を見ながらブラウザで採否を決める 1 枚の静的な HTML を作る。

    python proof_review.py html _review/marks/items_*.json --out review.html   # HTML を書く (サーバは要らない)
    python proof_review.py status items_*.json --decisions 回答.json           # 未決・採用・不採用・保留・反映済みの件数
    python proof_review.py apply items_*.json --decisions 回答.json            # 採用した分の置換を確かめる (書かない)
    python proof_review.py apply items_*.json --decisions 回答.json --apply    # 原稿へ当て，反映済みにする

できた HTML をブラウザで開く。右に修正前と修正後の差分と案 a/b/c が並び，画像のある項目だけ左に帯の画像
(朱書き入り．拡大・朱書きを消した版も切り替えられる) が出る。画像が無い項目 (原稿だけから作った修正案) は 1 段組。
押した決定はブラウザの localStorage に残り (閉じても消えない)，「回答を JSON で保存」で
decisions.json (decisions.py と同じ形) を落とす。ファイル名は `<HTML の名前>_decisions.json`。
「回答を読み込む」で，保存した回答から続けられる。HTML を作るときに --decisions の記録があれば，それを初めの状態にする。
**原稿そのものは HTML では書き換えない**。当てるのは apply --apply だけ。

項目 JSON (読み取りのエージェントが書く) の形:

    {"title": "第1章", "items": [
      {"id": "01-01", "kind": "simple", "page": 12, "band": "p012_b1",
       "label": "「見本の語」を「例の語」に置き換え", "tag": "ch01",
       "images": ["p012_b1.png", "p012_z1.png"],
       "reading": "朱書きの読み取り", "note": "気になる点",
       "options": [{"key": "a", "label": "朱書きどおり", "recommended": true,
                    "items": [{"file": "ch01.md", "old": "見本の語", "new": "例の語"}]}]}]}

- kind は simple (単純な修正)・judge (要判断．案が複数)・unreadable (判読不能．案なし)。
- images は項目 JSON のあるディレクトリから見た相対パス (絶対パスも可)。見せるのはここに載った画像だけ。
- 項目の file は --base (既定: 今のディレクトリ) から見る。修正前と修正後が原稿に何回あるかで
  「未反映・反映済み・見当たらない」を出す (check_applied.py と同じ考え方)。
- どの項目にも「自分で書く」欄がある (判読不能の朱書きや，案と違う直し方のとき)。ファイルの欄の既定は，その項目の案の原稿。
- 決定は decisions.json の 1 件になる: status は approved (採用)・rejected (不採用)・pending (保留)。
  選んだ案と，欄で直した修正後の文が items に入り，choice・memo・page・band も残る。
- 画像は HTML に埋め込む (項目に載った画像だけ)。標準ライブラリだけで動く。
"""
import argparse
import base64
import difflib
import glob
import hashlib
import html
import json
import mimetypes
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import decisions as D  # noqa: E402  (同じディレクトリの decisions.py)

KINDS = ("simple", "judge", "unreadable")


def expand(patterns):
    out = []
    for p in patterns:
        hits = sorted(glob.glob(p))
        out.extend(hits if hits else [p])
    return out


def load_items(paths):
    """項目 JSON を読み，(題, 項目のリスト) を返す。画像は絶対パスにする。id の重複は止める。"""
    titles, items, seen = [], [], set()
    for path in paths:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        rows = data.get("items") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError('%s: {"items": [...]} の形でない' % path)
        if isinstance(data, dict) and data.get("title"):
            titles.append(data["title"])
        root = os.path.dirname(os.path.abspath(path))
        for n, it in enumerate(rows, 1):
            iid = str(it.get("id") or "")
            if not iid:
                raise ValueError("%s #%d: id が無い" % (path, n))
            if iid in seen:
                raise ValueError("id が重複している: %s" % iid)
            seen.add(iid)
            kind = it.get("kind", "simple")
            if kind not in KINDS:
                raise ValueError("%s: kind は %s のどれか" % (iid, "/".join(KINDS)))
            opts = []
            for k, o in enumerate(it.get("options") or []):
                subs = []
                for r in o.get("items") or []:
                    old = r["old"] if "old" in r else r.get("before")
                    new = r["new"] if "new" in r else r.get("after")
                    if "file" not in r or old is None or new is None:
                        raise ValueError("%s: 案 %s の items に file・old・new が要る" % (iid, o.get("key", k)))
                    subs.append({"file": r["file"], "old": old, "new": new})
                opts.append({"key": o.get("key") or "abcdefgh"[k], "label": o.get("label", ""),
                             "recommended": bool(o.get("recommended")), "items": subs})
            imgs = [p if os.path.isabs(p) else os.path.normpath(os.path.join(root, p))
                    for p in it.get("images") or []]
            items.append({"id": iid, "kind": kind, "page": it.get("page"), "band": it.get("band", ""),
                          "label": it.get("label", ""), "tag": it.get("tag", ""),
                          "reading": it.get("reading", ""), "note": it.get("note", ""),
                          "images": imgs, "options": opts, "source": os.path.basename(path)})
    return " ／ ".join(dict.fromkeys(titles)), items


def diff_html(old, new):
    """(修正前の HTML, 修正後の HTML)．消す部分を <del>，足す部分を <ins> で囲む。"""
    def esc(s):
        return html.escape(s).replace("\n", "<span class=nl>↵</span>\n")
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    a, b = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            a.append(esc(old[i1:i2]))
            b.append(esc(new[j1:j2]))
        else:
            if i2 > i1:
                a.append("<del>%s</del>" % esc(old[i1:i2]))
            if j2 > j1:
                b.append("<ins>%s</ins>" % esc(new[j1:j2]))
    return "".join(a), "".join(b)


class Store:
    def __init__(self, item_paths, decisions_path, base):
        self.item_paths = item_paths
        self.decisions_path = decisions_path
        self.base = os.path.abspath(base)
        self.lock = threading.Lock()
        self.title, self.items = load_items(item_paths)
        self.by_id = {it["id"]: it for it in self.items}
        self.images = {p for it in self.items for p in it["images"]}
        self._text = {}

    # ---- 原稿 ----
    def text(self, rel):
        path = rel if os.path.isabs(rel) else os.path.join(self.base, rel)
        try:
            st = os.stat(path)
        except OSError:
            return None
        # 更新時刻だけでは，Windows で同じ時刻のうちに書き直すと古い中身を返す (CI で時々落ちた)．大きさも鍵にする
        mtime = (st.st_mtime_ns, st.st_size)
        hit = self._text.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
        if path.lower().endswith(".docx"):         # Word の原稿は本文を段落ごとに取り出す (変更履歴は承諾した後の文字)
            import apply_docx
            body = apply_docx.docx_text(path)
        else:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                body = fh.read().replace("\r\n", "\n")
        self._text[path] = (mtime, body)
        return body

    def where(self, sub):
        """原稿での状態: (状態, 行番号)．状態は pending (未反映)・applied (反映済み)・both・moot・nofile。"""
        body = self.text(sub["file"])
        if body is None:
            return "nofile", None
        old, new = sub["old"], sub["new"]
        n_old = body.count(old) if old else 0
        n_new = body.count(new) if new else 0
        if old and new and old in new:      # 足すだけの直し: 修正後があれば反映済み
            n_old = max(0, n_old - n_new)
        if n_old and n_new and old not in new and new not in old:
            state = "both"
        elif n_old:
            state = "pending"
        elif n_new or (not new and not n_old and old):
            state = "applied" if new or not n_old else "pending"
        else:
            state = "moot"
        pos = body.find(old if n_old else new) if (n_old or n_new) else -1
        line = body.count("\n", 0, pos) + 1 if pos >= 0 else None
        return state, line

    # ---- 決定 ----
    def decisions(self):
        decs, _ = D.load(self.decisions_path)
        return {d.get("id"): d for d in decs}

    def view(self):
        decs = self.decisions()
        out = []
        for it in self.items:
            opts = []
            for o in it["options"]:
                subs = []
                for s in o["items"]:
                    a, b = diff_html(s["old"], s["new"])
                    state, line = self.where(s)
                    subs.append(dict(s, old_html=a, new_html=b, state=state, line=line))
                opts.append(dict(o, items=subs))
            dec = decs.get(it["id"])
            edited = []
            if dec:
                for s in dec.get("items", []):
                    a, b = diff_html(s["old"], s["new"])
                    state, line = self.where(s)
                    edited.append(dict(s, old_html=a, new_html=b, state=state, line=line))
            out.append(dict({k: v for k, v in it.items() if k != "images"},
                            images=[{"key": p, "name": os.path.basename(p)} for p in it["images"]],
                            options=opts, decision=dec, decided_items=edited))
        files = sorted({s["file"] for it in self.items for o in it["options"] for s in o["items"]})
        return {"title": self.title, "decisions_path": os.path.abspath(self.decisions_path),
                "base": self.base, "files": files, "items": out}

    def decide(self, data):
        """data: {id, status, choice, items?, memo}．items が無ければ選んだ案の items を使う。"""
        iid = data["id"]
        it = self.by_id.get(iid)
        if it is None:
            raise LookupError("項目が無い: %s" % iid)
        status = data["status"]
        if status not in ("approved", "rejected", "pending", "undecided"):
            raise ValueError("status が不正: %s" % status)
        choice = data.get("choice") or ""
        with self.lock:
            decs, bom = D.load(self.decisions_path)
            decs = [d for d in decs if d.get("id") != iid]
            if status != "undecided":
                if data.get("items") is not None:
                    subs = [{"file": s["file"], "old": s["old"], "new": s["new"]} for s in data["items"]]
                else:
                    opt = next((o for o in it["options"] if o["key"] == choice), None)
                    subs = [dict(s) for s in opt["items"]] if opt else []
                for s in subs:
                    if not s["file"] or (not s["old"] and not s["new"]):
                        raise ValueError("file と，修正前か修正後のどちらかが要る")
                    s["count"] = 1
                opt = next((o for o in it["options"] if o["key"] == choice), None)
                label = it["label"] or iid
                if opt and len(it["options"]) > 1 and opt["label"]:
                    label = "%s (%s: %s)" % (label, choice, opt["label"])
                if choice == "own":
                    label = "%s (自分で書いた直し)" % label
                entry = {"id": iid, "tag": it["tag"] or "proof", "label": label, "status": status,
                         "files": [], "items": subs, "choice": choice, "memo": data.get("memo", ""),
                         "page": it["page"], "band": it["band"]}
                if data.get("edited"):
                    entry["edited"] = True
                decs.append(entry)
                order = {x["id"]: n for n, x in enumerate(self.items)}
                decs.sort(key=lambda d: order.get(d.get("id"), -1))
            D.save(self.decisions_path, decs, bom)
        return {"ok": True}

    def counts(self):
        decs = self.decisions()
        c = {"undecided": 0, "approved": 0, "rejected": 0, "pending": 0, "applied": 0}
        for it in self.items:
            st = (decs.get(it["id"]) or {}).get("status", "undecided")
            c[st] = c.get(st, 0) + 1
        return c


# ---------------------------------------------------------------- ページ
PAGE = r"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fafaf7;--fg:#222;--mut:#666;--line:#ddd;--card:#fff;--del:#ffd6d6;--ins:#cdf3d0;--acc:#0b5cad;
 --ok:#1a7f37;--ng:#b42318;--hold:#9a6700}
@media (prefers-color-scheme: dark){:root{--bg:#1c1c1c;--fg:#e8e8e8;--mut:#aaa;--line:#444;--card:#262626;
 --del:#5c2626;--ins:#24502b;--acc:#6fb3ff;--ok:#4cc26a;--ng:#ff7b72;--hold:#e3b341}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 "BIZ UDPGothic","Yu Gothic UI",sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:8px 16px;
 display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center}
header h1{font-size:17px;margin:0}
header .cnt span{margin-right:10px}
header select,header button{font:inherit;padding:2px 8px}
main{padding:12px 16px 80px;max-width:1500px}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;margin:0 0 14px;display:grid;
 grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:12px;padding:10px}
.card.noimg{grid-template-columns:minmax(0,1fr);max-width:980px}
.card.focus{outline:3px solid var(--acc)}
@media (max-width:900px){.card{grid-template-columns:1fr}}
.imgs img{max-width:100%;display:block;border:1px solid var(--line);background:#fff}
.imgs .tabs button{font:inherit;font-size:13px;margin:0 4px 4px 0;padding:1px 6px}
.imgs .tabs button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.hd{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}
.id{font-weight:bold}.mut{color:var(--mut);font-size:13px}
.badge{font-size:12px;border:1px solid var(--line);border-radius:10px;padding:0 7px}
.k-judge{border-color:var(--hold);color:var(--hold)}.k-unreadable{border-color:var(--ng);color:var(--ng)}
.label{font-weight:bold;margin:2px 0}
.reading,.note{font-size:14px;margin:2px 0}.note{color:var(--hold)}
.opt{border:1px solid var(--line);border-radius:5px;padding:6px 8px;margin:6px 0;cursor:pointer}
.opt.sel{border-color:var(--acc);box-shadow:0 0 0 1px var(--acc)}
.opt .ol{font-weight:bold}.rec{color:var(--ok);font-size:12px;margin-left:6px}
.sub{margin:4px 0 0;font-size:14px}
.pair{display:grid;grid-template-columns:3.5em 1fr;gap:2px 6px;white-space:pre-wrap;word-break:break-all}
.pair .t{color:var(--mut);font-size:12px}
del{background:var(--del);text-decoration:line-through}ins{background:var(--ins);text-decoration:none}
.nl{color:var(--mut)}
.st{font-size:12px;margin-left:4px}.st-applied{color:var(--ok)}.st-moot,.st-nofile,.st-both{color:var(--ng)}
textarea,input[type=text]{width:100%;font:13px/1.5 Consolas,"BIZ UDGothic",monospace;padding:4px;
 background:var(--card);color:var(--fg);border:1px solid var(--line)}
.own{display:none;margin-top:4px}.opt.sel .own{display:block}
.btns{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.btns button{font:inherit;padding:3px 12px;border-radius:4px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
.btns .ap.on{background:var(--ok);color:#fff}.btns .rj.on{background:var(--ng);color:#fff}
.btns .hd2.on{background:var(--hold);color:#fff}
.state{font-size:13px;font-weight:bold}
.s-approved{color:var(--ok)}.s-rejected{color:var(--ng)}.s-pending{color:var(--hold)}.s-applied{color:var(--ok)}
.toast{position:fixed;right:16px;bottom:16px;background:var(--fg);color:var(--bg);padding:6px 12px;border-radius:4px;opacity:0;transition:opacity .2s}
.toast.on{opacity:.9}
.help{font-size:12px;color:var(--mut)}
#save{font-weight:bold}
</style></head><body>
<header>
 <h1 id="title"></h1>
 <div class="cnt" id="cnt"></div>
 <label>表示 <select id="filter">
  <option value="undecided">未決だけ</option><option value="all">すべて</option>
  <option value="simple">単純な修正</option><option value="judge">要判断</option>
  <option value="unreadable">判読不能</option><option value="pending">保留</option>
  <option value="approved">採用 (未反映)</option><option value="rejected">不採用</option></select></label>
 <button id="bulk" title="表示中の単純な修正のうち，未決のものをすべて案 a で採用する">表示中の単純な修正を一括採用</button>
 <button id="save" title="decisions.json と同じ形で落とす">回答を JSON で保存</button>
 <label><button id="loadbtn" type="button">回答を読み込む</button><input type="file" id="loadfile" accept=".json,application/json" hidden></label>
 <span class="help">キー: j/k 移動・1〜3 案・a 採用・r 不採用・h 保留・u 取り消し．決定はこのブラウザに自動で残ります</span>
</header>
<main id="list"></main>
<div class="toast" id="toast"></div>
<script>
const DATA = __DATA__;
const KEY = "proof_review:" + DATA.key;
const $ = s => document.querySelector(s);
let FOCUS = 0;
const KIND = {simple:"単純", judge:"要判断", unreadable:"判読不能"};
const STATE = {pending:"未反映", applied:"反映済み", both:"一部反映", moot:"原稿に見当たらない", nofile:"ファイルが無い", typed:"手入力 (HTML を作ったときの原稿で確かめていない)"};
const DEC = {approved:"採用", rejected:"不採用", pending:"保留", applied:"反映済み"};
function esc(s){return String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function toast(m){const t=$("#toast");t.textContent=m;t.classList.add("on");clearTimeout(t._h);t._h=setTimeout(()=>t.classList.remove("on"),1800)}
function diffHtml(a,b){a=a||"";b=b||"";let p=0;while(p<a.length&&p<b.length&&a[p]===b[p])p++;
 let s=0;while(s<a.length-p&&s<b.length-p&&a[a.length-1-s]===b[b.length-1-s])s++;
 const e=x=>esc(x).replace(/\n/g,"<span class=nl>↵</span>\n");
 const mid=(x,tag)=>x?`<${tag}>${e(x)}</${tag}>`:"";
 return [e(a.slice(0,p))+mid(a.slice(p,a.length-s),"del")+e(a.slice(a.length-s)),
         e(b.slice(0,p))+mid(b.slice(p,b.length-s),"ins")+e(b.slice(b.length-s))]}
// 決定: {id: decisions.json の 1 件}．初めは HTML に入れた記録，ブラウザに残した分で上書きする
let DECS = {};
DATA.items.forEach(it=>{if(it.decision)DECS[it.id]=it.decision});
try{Object.assign(DECS, JSON.parse(localStorage.getItem(KEY)||"{}"))}catch(e){}
function persist(){try{localStorage.setItem(KEY,JSON.stringify(DECS))}catch(e){toast("ブラウザに保存できません．こまめに「回答を JSON で保存」してください")}}
function status(it){const d=DECS[it.id];return d?d.status:"undecided"}
function visible(it){const f=$("#filter").value, s=status(it);
 if(f==="all")return true; if(f==="undecided")return s==="undecided";
 if(["simple","judge","unreadable"].includes(f))return it.kind===f; return s===f}
function counts(){const c={undecided:0,approved:0,rejected:0,pending:0,applied:0};
 DATA.items.forEach(it=>c[status(it)]=(c[status(it)]||0)+1);
 $("#cnt").innerHTML=`<span>全 ${DATA.items.length}</span><span>未決 ${c.undecided}</span><span class="s-approved">採用 ${c.approved}</span>`+
 `<span class="s-rejected">不採用 ${c.rejected}</span><span class="s-pending">保留 ${c.pending}</span><span class="s-applied">反映済み ${c.applied}</span>`}
function subHtml(s, editable, iid, k, n){
 const st=`<span class="st st-${s.state}">${STATE[s.state]||s.state}${s.line?` (${esc(s.file)}:${s.line})`:` (${esc(s.file)})`}</span>`;
 let h=`<div class="sub">${st}<div class="pair"><span class="t">修正前</span><span>${s.old_html||'<span class=mut>(なし)</span>'}</span>`+
  `<span class="t">修正後</span><span>${s.new_html||'<span class=mut>(削除)</span>'}</span></div>`;
 if(editable) h+=`<details><summary class="mut">修正後を直す</summary><textarea rows="3" data-edit="${iid}|${k}|${n}">${esc(s.new)}</textarea></details>`;
 return h+`</div>`}
function chosen(it){const d=DECS[it.id]; if(d&&d.choice)return d.choice;
 const r=it.options.find(o=>o.recommended)||it.options[0]; return r?r.key:"own"}
function shown(it, o){ // 選んだ案を欄で直していれば，直した文で見せる
 const d=DECS[it.id];
 if(!(d&&d.choice===o.key&&d.edited))return o.items;
 return d.items.map((x,n)=>{const base=o.items[n]||{};const [a,b]=diffHtml(x.old,x.new);
  return Object.assign({},base,x,{old_html:a,new_html:b,state:x.new===base.new?base.state:"typed",line:base.line})})}
function ownFile(it){const o=it.options.find(x=>x.items.length);return o?o.items[0].file:(DATA.files[0]||"")}
function card(it, idx){
 const d=DECS[it.id], s=status(it), ch=chosen(it), hasImg=it.images.length>0;
 const imgs=hasImg?`<div class="imgs"><div class="tabs">`+it.images.map((m,i)=>`<button data-img="${idx}|${i}" class="${i?"":"on"}">${esc(m.name)}</button>`).join("")+
  `</div><img id="img${idx}" src="${it.images[0].src}" alt="${esc(it.images[0].name)}"></div>`:"";
 let opts=it.options.map(o=>{
  const subs=shown(it,o).map((x,n)=>subHtml(x,true,it.id,o.key,n)).join("") || '<div class="mut">原稿は変えない</div>';
  return `<div class="opt ${ch===o.key?"sel":""}" data-opt="${it.id}|${o.key}"><span class="ol">${esc(o.key)}.</span> ${esc(o.label)}${o.recommended?'<span class="rec">おすすめ</span>':""}${subs}</div>`}).join("");
 const own = d&&d.choice==="own"&&d.items[0] ? d.items[0] : {file:ownFile(it),old:"",new:""};
 opts+=`<div class="opt ${ch==="own"?"sel":""}" data-opt="${it.id}|own"><span class="ol">自分で書く</span>`+
  `<div class="own"><input type="text" data-own="${it.id}|file" value="${esc(own.file)}" placeholder="ファイル">`+
  `<textarea rows="2" data-own="${it.id}|old" placeholder="修正前 (原稿の文字どおり)">${esc(own.old)}</textarea>`+
  `<textarea rows="2" data-own="${it.id}|new" placeholder="修正後">${esc(own.new)}</textarea></div></div>`;
 const where=[it.page!=null&&it.page!==""?`p.${esc(it.page)}`:"", esc(it.band||"")].filter(Boolean).join(" ");
 return `<section class="card${hasImg?"":" noimg"}" id="c${idx}" data-idx="${idx}">${imgs}<div>`+
  `<div class="hd"><span class="id">${esc(it.id)}</span><span class="badge k-${it.kind}">${KIND[it.kind]||it.kind}</span>`+
  (where?`<span class="mut">${where}</span>`:"")+`<span class="state s-${s}">${DEC[s]||""}</span></div>`+
  `<div class="label">${esc(it.label)}</div>`+
  (it.reading?`<div class="reading"><span class="mut">${esc(DATA.reading_label)}:</span> ${esc(it.reading)}</div>`:"")+
  (it.note?`<div class="note">${esc(it.note)}</div>`:"")+ opts +
  `<div class="btns"><button class="ap ${s==="approved"?"on":""}" data-act="${it.id}|approved">採用 (a)</button>`+
  `<button class="rj ${s==="rejected"?"on":""}" data-act="${it.id}|rejected">不採用 (r)</button>`+
  `<button class="hd2 ${s==="pending"?"on":""}" data-act="${it.id}|pending">保留 (h)</button>`+
  `<button data-act="${it.id}|undecided">取り消し (u)</button></div>`+
  `<textarea rows="1" data-memo="${it.id}" placeholder="メモ (保留の理由など．欄から離れると保存)">${esc(d?d.memo:"")}</textarea>`+
  `</div></section>`}
function render(){ $("#title").textContent = DATA.title; document.title = DATA.title; counts();
 const list=DATA.items.map((it,i)=>visible(it)?card(it,i):"").join("");
 $("#list").innerHTML = list || '<p class="mut">この表示に当たる項目はありません．</p>';
 const cards=[...document.querySelectorAll(".card")]; if(cards.length){FOCUS=Math.min(FOCUS,cards.length-1);cards[FOCUS].classList.add("focus")}}
function item(id){return DATA.items.find(x=>x.id===id)}
function selected(id){const el=document.querySelector(`.opt.sel[data-opt^="${CSS.escape(id)}|"]`); return el?el.dataset.opt.split("|")[1]:chosen(item(id))}
function gather(id){
 const it=item(id), ch=selected(id), memo=(document.querySelector(`[data-memo="${CSS.escape(id)}"]`)||{}).value||"";
 if(ch==="own"){const g=f=>(document.querySelector(`[data-own="${CSS.escape(id)}|${f}"]`)||{}).value||"";
  return {choice:"own", memo, items:[{file:g("file"),old:g("old"),new:g("new")}]}}
 const o=it.options.find(x=>x.key===ch); if(!o) return {choice:ch, memo, items:[]};
 let edited=false; const items=o.items.map((s,n)=>{const ta=document.querySelector(`[data-edit="${CSS.escape(id)}|${ch}|${n}"]`);
  const nv=ta?ta.value:s.new; if(nv!==s.new)edited=true; return {file:s.file,old:s.old,new:nv}});
 return {choice:ch,memo,items,edited}}
function decide(id, st, given){ // decisions.json の 1 件を作る (proof_review.py の Store.decide と同じ形)
 const it=item(id), g=given||gather(id);
 if(st==="approved"&&it.kind==="unreadable"&&g.choice!=="own"){toast("判読不能の項目は「自分で書く」に直し方を書いてから採用します");return false}
 if(st==="undecided"){delete DECS[id]}
 else{
  for(const s of g.items){if(!s.file||(!s.old&&!s.new)){toast("ファイルと，修正前か修正後のどちらかが要ります");return false}}
  const o=it.options.find(x=>x.key===g.choice);
  let label=it.label||id;
  if(o&&it.options.length>1&&o.label)label=`${label} (${g.choice}: ${o.label})`;
  if(g.choice==="own")label=`${label} (自分で書いた直し)`;
  const e={id, tag:it.tag||"proof", label, status:st, files:[], items:g.items.map(s=>({file:s.file,old:s.old,new:s.new,count:1})),
   choice:g.choice, memo:g.memo||"", page:it.page??null, band:it.band||""};
  if(g.edited)e.edited=true;
  DECS[id]=e}
 persist(); return true}
function act(id, st){if(!decide(id,st))return; toast(`${id}: ${DEC[st]||"未決に戻した"}`);const y=window.scrollY;render();window.scrollTo(0,y)}
function fname(){return DATA.answers_name}
$("#save").addEventListener("click",()=>{
 const order={};DATA.items.forEach((it,i)=>order[it.id]=i);
 const decs=Object.values(DECS).filter(d=>d.id in order).sort((a,b)=>order[a.id]-order[b.id]);
 const a=document.createElement("a");
 a.href=URL.createObjectURL(new Blob([JSON.stringify({decisions:decs},null,2)+"\n"],{type:"application/json"}));
 a.download=fname();a.click();toast(`${decs.length} 件を ${fname()} に保存`)});
$("#loadbtn").addEventListener("click",()=>$("#loadfile").click());
$("#loadfile").addEventListener("change",e=>{const f=e.target.files[0]; if(!f)return;
 f.text().then(t=>{const j=JSON.parse(t); const list=Array.isArray(j)?j:(j.decisions||[]); let n=0;
  for(const d of list){if(d&&d.id&&item(d.id)){DECS[d.id]=d;n++}}
  persist();render();toast(`${n} 件を読み込んだ`)}).catch(err=>toast("読めません: "+err));e.target.value=""});
document.addEventListener("click",e=>{
 const t=e.target.closest("[data-act],[data-opt],[data-img]"); if(!t)return;
 if(t.dataset.act){const [id,st]=t.dataset.act.split("|");act(id,st);return}
 if(t.dataset.img){const [i,k]=t.dataset.img.split("|").map(Number);const it=DATA.items[i];
  $("#img"+i).src=it.images[k].src;
  t.parentNode.querySelectorAll("button").forEach(b=>b.classList.toggle("on",b===t));return}
 if(t.dataset.opt&&!e.target.closest("textarea,input,summary")){const [id]=t.dataset.opt.split("|");
  document.querySelectorAll(`[data-opt^="${CSS.escape(id)}|"]`).forEach(o=>o.classList.toggle("sel",o===t))}});
document.addEventListener("change",e=>{const t=e.target;
 if(t.dataset.memo!==undefined){const id=t.dataset.memo; if(DECS[id]){DECS[id].memo=t.value;persist();toast(`${id}: メモを保存`)}}});
$("#filter").addEventListener("change",()=>{FOCUS=0;render()});
$("#bulk").addEventListener("click",()=>{
 const ids=DATA.items.filter(it=>visible(it)&&it.kind==="simple"&&status(it)==="undecided").map(it=>it.id);
 if(!ids.length){toast("対象がありません");return}
 if(!confirm(`表示中の単純な修正 ${ids.length} 件を，案 a のまま採用します．`))return;
 for(const id of ids){const it=item(id),o=it.options.find(x=>x.key===chosen(it));
  decide(id,"approved",{choice:o?o.key:"",memo:"",items:o?o.items.map(s=>({file:s.file,old:s.old,new:s.new})):[],edited:false})}
 toast(`${ids.length} 件を採用`); render()});
document.addEventListener("keydown",e=>{
 if(e.target.closest("textarea,input,select")||e.ctrlKey||e.metaKey||e.altKey)return;
 const cards=[...document.querySelectorAll(".card")]; if(!cards.length)return;
 const cur=cards[FOCUS], it=DATA.items[+cur.dataset.idx];
 const move=n=>{cur.classList.remove("focus");FOCUS=Math.max(0,Math.min(cards.length-1,FOCUS+n));
  cards[FOCUS].classList.add("focus");cards[FOCUS].scrollIntoView({block:"start",behavior:"smooth"})};
 if(e.key==="j")move(1); else if(e.key==="k")move(-1);
 else if("123".includes(e.key)){const o=it.options[+e.key-1]; if(o){const el=cur.querySelector(`[data-opt="${CSS.escape(it.id)}|${o.key}"]`); el&&el.click()}}
 else if(e.key==="a")act(it.id,"approved"); else if(e.key==="r")act(it.id,"rejected");
 else if(e.key==="h")act(it.id,"pending"); else if(e.key==="u")act(it.id,"undecided");});
render();
</script></body></html>
"""


def data_uri(path):
    with open(path, "rb") as fh:
        body = fh.read()
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    return "data:%s;base64,%s" % (ctype, base64.b64encode(body).decode("ascii"))


def build_page(store, out, title=None, reading_label=None):
    """1 枚の HTML の文字列を返す。差分・原稿での状態は作った時点の原稿で決める。画像は埋め込む。"""
    view = store.view()
    items = []
    for it in view["items"]:
        imgs = []
        for m in it["images"]:
            if not os.path.isfile(m["key"]):
                raise ValueError("%s: 画像が無い: %s" % (it["id"], m["key"]))
            imgs.append({"name": m["name"], "src": data_uri(m["key"])})
        row = {k: v for k, v in it.items() if k not in ("images", "decided_items")}
        row["images"] = imgs
        items.append(row)
    has_img = any(it["images"] for it in items)
    stem = os.path.splitext(os.path.basename(out))[0]
    key = hashlib.sha1(json.dumps([stem, [it["id"] for it in items]], ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    data = {"title": title or view["title"] or ("朱書きの採否" if has_img else "修正案の採否"),
            "reading_label": reading_label or ("朱書き" if has_img else "読み取り"),
            "key": key, "answers_name": "%s_decisions.json" % stem,
            "files": view["files"], "items": items}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__TITLE__", html.escape(data["title"])).replace("__DATA__", blob)


# ---------------------------------------------------------------- コマンド
def default_decisions(item_paths):
    return os.path.join(os.path.dirname(os.path.abspath(item_paths[0])), "decisions.json")


def make_store(a):
    paths = expand(a.items)
    for p in paths:
        if not os.path.isfile(p):
            sys.exit("項目 JSON が無い: %s" % p)
    return Store(paths, a.decisions or default_decisions(paths), a.base)


def cmd_html(a):
    store = make_store(a)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(store.item_paths[0])), "review.html")
    page = build_page(store, out, a.title, a.reading_label)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(page)
    stem = os.path.splitext(os.path.basename(out))[0]
    print("項目 %d 件 → %s (%d KB)" % (len(store.items), os.path.abspath(out), len(page.encode("utf-8")) // 1024))
    print("ブラウザで開き，決め終えたら「回答を JSON で保存」(%s_decisions.json)。" % stem)
    print("当てるとき: apply <項目 JSON> --decisions <保存した JSON> --base <原稿> [--apply]")


def cmd_status(a):
    store = make_store(a)
    c = store.counts()
    print("全 %d 件: 未決 %d・採用 %d・不採用 %d・保留 %d・反映済み %d" % (
        len(store.items), c["undecided"], c["approved"], c["rejected"], c["pending"], c["applied"]))
    decs = store.decisions()
    for it in store.items:
        d = decs.get(it["id"])
        if d and d.get("status") == "pending":
            print("  保留 %s: %s%s" % (it["id"], it["label"], ("  ／ " + d["memo"]) if d.get("memo") else ""))


def cmd_apply(a):
    """採用した分を置換リストにし，apply_fixes.py に渡す。--apply なら当てて反映済みにする。"""
    store = make_store(a)
    decs = store.decisions()
    ids = [it["id"] for it in store.items if (decs.get(it["id"]) or {}).get("status") == "approved"]
    if not ids:
        print("採用して未反映の項目はない")
        return 0
    groups = {"text": ([], []), "docx": ([], [])}      # (置換, 項目の id)．Word の原稿は apply_docx.py で当てる
    for i in ids:
        for s in decs[i].get("items", []):
            g = groups["docx" if s["file"].lower().endswith(".docx") else "text"]
            g[0].append({"file": s["file"], "old": s["old"], "new": s["new"]})
            g[1].append(i)
    empty = [i for i in ids if not decs[i].get("items")]
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(store.decisions_path)), "fixes_review.json")
    paths = {"text": out, "docx": os.path.splitext(out)[0] + "_docx.json"}
    n_rows = sum(len(g[0]) for g in groups.values())
    for kind, (rows, _owner) in groups.items():
        if rows:
            with open(paths[kind], "w", encoding="utf-8") as fh:
                json.dump(rows, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
    print("採用 %d 件 (置換 %d 件．原稿を変えない項目 %d 件) → %s" % (
        len(ids), n_rows, len(empty), " ・ ".join(paths[k] for k, g in groups.items() if g[0]) or "(置換なし)"), flush=True)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")

    def call(kind, write):
        if kind == "text":
            cmd = [sys.executable, os.path.join(HERE, "apply_fixes.py"), paths[kind]]
        else:
            cmd = [sys.executable, os.path.join(HERE, "apply_docx.py"), paths[kind],
                   "--mode", a.docx_mode, "--author", a.author]
        return subprocess.call(cmd + (["--apply"] if write else []), cwd=store.base, env=env)

    kinds = [k for k, g in groups.items() if g[0]]
    rc, failed = 0, []
    if a.apply and len(kinds) > 1:                  # 両方あるときは，先に両方を確かめてから書く (片方だけ当たるのを防ぐ)
        failed = [k for k in kinds if call(k, False) != 0]
    if not failed:
        for k in kinds:
            if call(k, a.apply) != 0:
                failed.append(k)
    rc = 1 if failed else 0
    if failed:
        # apply_fixes.py の案内は「--partial」だが，このコマンドには無い．#番号を項目の id に引き直して案内する
        for k in failed:
            print()
            print("置換の番号と項目 (%s．#番号は上の出力と同じ):" % ("Word の原稿" if k == "docx" else "テキストの原稿"))
            for n, i in enumerate(groups[k][1], 1):
                print("  #%d %s" % (n, i))
        for line in ("当てられない置換があるので，何も書いていない (この apply に --partial は無い)。",
                     "  - 2 つの項目が同じ箇所を書き換えると，先に当たった方で後の修正前が消える。",
                     "    片方の案に他方が含まれていれば，含まれる方を不採用にしてから当て直す。",
                     "  - 修正前が原稿に無いときは，その項目を「自分で書く」で直すか，保留にする。"):
            print(line)
    if a.apply and rc == 0:
        all_decs, bom = D.load(store.decisions_path)
        for d in all_decs:
            if d.get("id") in ids:
                d["status"] = "applied"
        D.save(store.decisions_path, all_decs, bom)
        print("反映済みにした: %s" % ",".join(ids))
    elif not a.apply:
        print("(確かめただけ．当てるときは --apply を付ける)")
    return rc


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("html", "status", "apply"):
        p = sub.add_parser(name)
        p.add_argument("items", nargs="+", help="項目 JSON (glob 可)")
        p.add_argument("--decisions", help="決定の記録．HTML で保存した回答もこれで渡す "
                                           "(既定: 最初の項目 JSON と同じ場所の decisions.json)")
        p.add_argument("--base", default=".", help="項目の file を解決する原稿のディレクトリ (既定: 今のディレクトリ)")
        if name == "html":
            p.add_argument("--out", help="書き出す HTML (既定: 最初の項目 JSON と同じ場所の review.html)")
            p.add_argument("--title", help="ページの題 (既定: 項目 JSON の title)")
            p.add_argument("--reading-label", help="reading の見出し (既定: 画像があれば「朱書き」，無ければ「読み取り」)")
        if name == "apply":
            p.add_argument("--apply", action="store_true", help="原稿へ当てる (付けなければ確かめるだけ)")
            p.add_argument("--out", help="置換リストの書き出し先 (既定: decisions.json と同じ場所の fixes_review.json)")
            p.add_argument("--docx-mode", choices=("track", "direct", "comment"), default="track",
                           help="Word の原稿の当て方: track (変更履歴．既定)・direct (書き換え)・comment (コメント)")
            p.add_argument("--author", default="apply-proof-marks", help="Word の変更履歴・コメントの作成者名")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "html":
            return cmd_html(a)
        if a.cmd == "status":
            return cmd_status(a)
        return cmd_apply(a)
    except ValueError as error:
        sys.exit("項目 JSON が読めない: %s" % error)


if __name__ == "__main__":
    sys.exit(main() or 0)
