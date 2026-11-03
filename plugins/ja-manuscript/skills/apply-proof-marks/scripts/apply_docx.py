#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Word (.docx) の原稿に，置換リストの修正を当てる (標準ライブラリだけで動く)。

    python apply_docx.py fixes.json                       # 確かめるだけ (何も書かない)
    python apply_docx.py fixes.json --apply               # 変更履歴として当てる (既定)
    python apply_docx.py fixes.json --apply --mode direct  # 直接書き換える
    python apply_docx.py fixes.json --apply --mode comment # 本文は変えず，コメントで示す
    python apply_docx.py text 原稿.docx                    # 本文を段落ごとに 1 行で出す (照合用)

置換リストは apply_fixes.py と同じ形: [{"file": "原稿.docx", "old": "…", "new": "…"}, ...]
(キーは before/after でもよい。count を書けば，その回数ちょうど現れることを確かめて全部に当てる)。

- **mode**: track (既定) は Word の変更履歴 (w:del / w:ins) で当てるので，Word の「承諾」「元に戻す」で採否できる。
  修正前と修正後で共通する前後は残し，違う部分だけを消して足す (「投稿先で」→「PDF で」なら「投稿先」を消し「PDF 」を足す)。
  direct は本文を書き換える。comment は本文を変えず，修正前の範囲にコメント「朱書き: 「old」→「new」」を付ける。
- 本文 (word/document.xml) の段落の中だけを探す。書式で細かく割れた run をつなげて探し，境目で run を割って当てる。
  見出し・表の中の段落も対象。脚注・ヘッダ・フッタ・テキストボックスの代替表示 (mc:Fallback) は対象外。
- 当てないもの (理由を出して止まる): 段落をまたぐ置換 (old に改行がある)・フィールドや図を含む run にかかる置換・
  回数が合わない置換。**1 件でも当たらなければ何も書かない**。
- 初回の書き込みで <原稿>.docx.bak を残す (以後は上書きしない)。
- XML を書き直しても名前空間の宣言が落ちないよう，最上位の要素の開始タグは元の文字列を戻す
  (落ちると Word が「読み取れない内容がある」と言う)。
"""
import argparse
import copy
import datetime
import io
import json
import os
import re
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
REL_COMMENTS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
CT_COMMENTS = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
MODES = ("track", "direct", "comment")


def w(tag):
    return "{%s}%s" % (W, tag)


# run を探しに入る入れ物 (段落の直下にあるもの)．w:del の中 (消した文字) には入らない
CONTAINERS = {w(t) for t in ("hyperlink", "ins", "smartTag", "sdt", "sdtContent", "fldSimple", "customXml", "moveTo")}
SKIP = {w("del"), w("moveFrom")}
PLAIN_CHILDREN = {w("rPr"), w("t"), w("lastRenderedPageBreak")}


class DocxError(Exception):
    pass


# ---------------------------------------------------------------- XML の読み書き

def parse_part(raw):
    """(要素, 元の XML 宣言, 元の最上位の開始タグ) を返す。名前空間の接頭辞は元のものを登録する。"""
    for _ev, (prefix, uri) in ET.iterparse(io.BytesIO(raw), events=("start-ns",)):
        if prefix and not re.match(r"ns\d+$", prefix):
            try:
                ET.register_namespace(prefix, uri)
            except ValueError:
                pass
    text = raw.decode("utf-8")
    m = re.match(r"\s*(<\?xml[^>]*\?>)?\s*", text)
    decl = m.group(1) or '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    root_tag = re.search(r"<(?![?!])[^>]*>", text[m.end():]).group(0)
    return ET.fromstring(raw), decl, root_tag


def dump_part(root, decl, root_tag):
    body = ET.tostring(root, encoding="unicode")
    first = re.match(r"<[^>]*>", body).group(0)
    if not first.endswith("/>"):
        body = root_tag + body[len(first):]
    return (decl + "\r\n" + body).encode("utf-8")


# ---------------------------------------------------------------- 段落と run

def parent_map(root):
    return {c: p for p in root.iter() for c in p}


def body_paragraphs(root, parents):
    """対象の段落 (mc:Fallback の中は除く) を文書の順に返す。"""
    out = []
    for p in root.iter(w("p")):
        a, skip = parents.get(p), False
        while a is not None:
            if a.tag == "{%s}Fallback" % MC:
                skip = True
                break
            a = parents.get(a)
        if not skip:
            out.append(p)
    return out


def run_text(r):
    s = []
    for c in r:
        if c.tag == w("t"):
            s.append(c.text or "")
        elif c.tag == w("tab"):
            s.append("\t")
        elif c.tag in (w("br"), w("cr")):
            s.append("\n")
    return "".join(s)


def is_plain(r):
    kids = [c.tag for c in r]
    return w("t") in kids and all(k in PLAIN_CHILDREN for k in kids)


def runs_of(p):
    """段落の run を順に返す (消した文字・入れ子の段落には入らない)。"""
    out = []

    def walk(e):
        for c in e:
            if c.tag in SKIP:
                continue
            if c.tag == w("r"):
                out.append(c)
            elif c.tag in CONTAINERS:
                walk(c)
    walk(p)
    return out


def segments(p):
    """[(run, 始まり, 終わり)] と段落の文字列。"""
    segs, pos, parts = [], 0, []
    for r in runs_of(p):
        t = run_text(r)
        segs.append((r, pos, pos + len(t)))
        parts.append(t)
        pos += len(t)
    return segs, "".join(parts)


def docx_text(path):
    """本文を段落ごとに改行でつないで返す (変更履歴は承諾した後の文字)。"""
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    parents = parent_map(root)
    return "\n".join(segments(p)[1] for p in body_paragraphs(root, parents))


# ---------------------------------------------------------------- run を割る

def set_text(r, text):
    """平らな run の文字を 1 つの w:t にまとめて text にする。"""
    ts = [c for c in r if c.tag == w("t")]
    for c in list(r):
        if c.tag in (w("t"), w("lastRenderedPageBreak")) and c is not ts[0]:
            r.remove(c)
    ts[0].text = text
    ts[0].set(XML_SPACE, "preserve")


def split_run(r, k, parents):
    """run を k 文字目で割り，前半を新しい run として r の前に入れる。前半の run を返す。"""
    text = run_text(r)
    left = copy.deepcopy(r)
    set_text(left, text[:k])
    set_text(r, text[k:])
    par = parents[r]
    par.insert(list(par).index(r), left)
    parents[left] = par
    return left


def isolate(p, s, e, parents):
    """段落の [s, e) をちょうど覆う run のリストを返す (境目の run は割る)。"""
    segs, _ = segments(p)
    hit = [(r, a, b) for r, a, b in segs if a < e and b > s]
    for r, a, b in hit:
        if not is_plain(r):
            raise DocxError("フィールド・図・改行などを含む run にかかる")
    if not hit:
        return []
    r0, a0, _b0 = hit[0]
    if s > a0:
        split_run(r0, s - a0, parents)                # r0 は後半 (s から) になる
    segs, _ = segments(p)
    hit = [(r, a, b) for r, a, b in segs if a < e and b > s]
    rl, al, bl = hit[-1]
    if e < bl:
        left = split_run(rl, e - al, parents)         # 前半 (e まで) が対象
        hit[-1] = (left, al, e)
    return [r for r, _a, _b in hit]


def new_run_like(r, text, tag="t"):
    nr = ET.Element(w("r"))
    rpr = r.find(w("rPr")) if r is not None else None
    if rpr is not None:
        nr.append(copy.deepcopy(rpr))
    t = ET.SubElement(nr, w(tag))
    t.text = text
    t.set(XML_SPACE, "preserve")
    return nr


def insert_after(parents, ref, elem):
    par = parents[ref]
    par.insert(list(par).index(ref) + 1, elem)
    parents[elem] = par


def insert_before(parents, ref, elem):
    par = parents[ref]
    par.insert(list(par).index(ref), elem)
    parents[elem] = par


# ---------------------------------------------------------------- 当てる

class Doc:
    def __init__(self, path, mode, author, date):
        self.path, self.mode, self.author, self.date = path, mode, author, date
        with zipfile.ZipFile(path) as z:
            self.names = z.namelist()
            self.raw = {n: z.read(n) for n in self.names}
            self.info = {n: z.getinfo(n) for n in self.names}
        self.root, self.decl, self.root_tag = parse_part(self.raw["word/document.xml"])
        self.parents = parent_map(self.root)
        ids = [int(v) for e in self.root.iter() for k, v in e.attrib.items() if k == w("id") and v.lstrip("-").isdigit()]
        self.next_id = max(ids + [0]) + 1
        self.comments = []      # (id, 文字)

    def new_id(self):
        self.next_id += 1
        return str(self.next_id)

    def paragraphs(self):
        return body_paragraphs(self.root, self.parents)

    def find(self, old):
        """[(段落, 始まり, 段落の文字)]．"""
        hits = []
        for p in self.paragraphs():
            _segs, text = segments(p)
            start = 0
            while True:
                i = text.find(old, start)
                if i < 0:
                    break
                hits.append((p, i, text))
                start = i + len(old)
        return hits

    def apply_one(self, p, s, old, new):
        e = s + len(old)
        if self.mode == "comment":
            runs = isolate(p, s, e, self.parents)
            cid = self.new_id()
            st = ET.Element(w("commentRangeStart"), {w("id"): cid})
            en = ET.Element(w("commentRangeEnd"), {w("id"): cid})
            insert_before(self.parents, runs[0], st)
            insert_after(self.parents, runs[-1], en)
            ref = ET.Element(w("r"))
            ET.SubElement(ref, w("commentReference"), {w("id"): cid})
            insert_after(self.parents, en, ref)
            self.comments.append((cid, "朱書き: 「%s」→「%s」" % (old, new)))
            return
        # 共通する前後を除いた，違う部分だけを当てる
        a = 0
        while a < min(len(old), len(new)) and old[a] == new[a]:
            a += 1
        b = 0
        while b < min(len(old), len(new)) - a and old[len(old) - 1 - b] == new[len(new) - 1 - b]:
            b += 1
        s2, e2, mid = s + a, e - b, new[a:len(new) - b]
        if s2 == e2:                                  # 足すだけ
            self.insert_text(p, s2, mid)
            return
        runs = isolate(p, s2, e2, self.parents)
        if self.mode == "direct":
            set_text(runs[0], mid)
            for r in runs[1:]:
                self.parents[r].remove(r)
            if mid == "":
                self.parents[runs[0]].remove(runs[0])
            return
        last = None
        for r in runs:                                # track: 1 つずつ w:del で包む
            d = ET.Element(w("del"), {w("id"): self.new_id(), w("author"): self.author, w("date"): self.date})
            insert_before(self.parents, r, d)
            self.parents[r].remove(r)
            d.append(r)
            self.parents[r] = d
            for t in r.findall(w("t")):
                t.tag = w("delText")
                t.set(XML_SPACE, "preserve")
            last = d
        if mid:
            ins = ET.Element(w("ins"), {w("id"): self.new_id(), w("author"): self.author, w("date"): self.date})
            ins.append(new_run_like(runs[0], mid))
            insert_after(self.parents, last, ins)

    def insert_text(self, p, x, text):
        segs, _ = segments(p)
        if not segs:
            raise DocxError("文字の無い段落には足せない")
        if x == 0:
            ref, where = segs[0][0], "before"
        else:
            r, a, b = next((r, a, b) for r, a, b in segs if a < x <= b)
            if not is_plain(r):
                raise DocxError("フィールド・図・改行などを含む run にかかる")
            if x < b:
                split_run(r, x - a, self.parents)
                segs, _ = segments(p)
                r = next(rr for rr, aa, bb in segs if bb == x)
            ref, where = r, "after"
        if self.mode == "direct":
            if is_plain(ref):
                t = run_text(ref)
                set_text(ref, text + t if where == "before" else t + text)
                return
            nr = new_run_like(ref, text)
            (insert_before if where == "before" else insert_after)(self.parents, ref, nr)
            return
        ins = ET.Element(w("ins"), {w("id"): self.new_id(), w("author"): self.author, w("date"): self.date})
        ins.append(new_run_like(ref, text))
        (insert_before if where == "before" else insert_after)(self.parents, ref, ins)

    # ---- 書き出し
    def comments_part(self):
        name = "word/comments.xml"
        if name in self.raw:
            root, decl, tag = parse_part(self.raw[name])
        else:
            root, decl = ET.Element(w("comments")), '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            tag = '<w:comments xmlns:w="%s">' % W
        for cid, text in self.comments:
            c = ET.SubElement(root, w("comment"), {w("id"): cid, w("author"): self.author, w("date"): self.date,
                                                     w("initials"): self.author[:2]})
            pp = ET.SubElement(c, w("p"))
            rr = ET.SubElement(pp, w("r"))
            t = ET.SubElement(rr, w("t"))
            t.text = text
            t.set(XML_SPACE, "preserve")
        return dump_part(root, decl, tag)

    def write(self):
        out = dict(self.raw)
        out["word/document.xml"] = dump_part(self.root, self.decl, self.root_tag)
        names = list(self.names)
        if self.comments:
            if "word/comments.xml" not in out:
                names.append("word/comments.xml")
                rels = out["word/_rels/document.xml.rels"].decode("utf-8")
                used = set(re.findall(r'Id="(rId\d+)"', rels))
                n = 1
                while "rId%d" % n in used:
                    n += 1
                rels = rels.replace("</Relationships>", '<Relationship Id="rId%d" Type="%s" Target="comments.xml"/></Relationships>' % (n, REL_COMMENTS))
                out["word/_rels/document.xml.rels"] = rels.encode("utf-8")
                ct = out["[Content_Types].xml"].decode("utf-8")
                if "/word/comments.xml" not in ct:
                    ct = ct.replace("</Types>", '<Override PartName="/word/comments.xml" ContentType="%s"/></Types>' % CT_COMMENTS)
                out["[Content_Types].xml"] = ct.encode("utf-8")
            out["word/comments.xml"] = self.comments_part()
        bak = self.path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(self.path, bak)
        tmp = self.path + ".tmp"
        with zipfile.ZipFile(tmp, "w") as z:
            for n in names:
                info = self.info.get(n)
                if info is not None:
                    zi = zipfile.ZipInfo(n, date_time=info.date_time)
                    zi.compress_type, zi.external_attr = info.compress_type, info.external_attr
                else:
                    zi = zipfile.ZipInfo(n, date_time=datetime.datetime.now().timetuple()[:6])
                    zi.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(zi, out[n])
        os.replace(tmp, self.path)


def load_fixes(path):
    with open(path, encoding="utf-8-sig") as fh:
        rows = json.load(fh)
    out = []
    for n, r in enumerate(rows, 1):
        old = r["old"] if "old" in r else r.get("before")
        new = r["new"] if "new" in r else r.get("after")
        if "file" not in r or old is None or new is None:
            raise SystemExit("#%d: file・old・new が要る" % n)
        out.append({"n": n, "file": r["file"], "old": old, "new": new, "count": int(r.get("count", 1))})
    return out


def context(text, i, old, new, width=22):
    a = text[max(0, i - width):i]
    b = text[i + len(old):i + len(old) + width]
    return ("…%s【%s】%s…" % (a, old, b), "…%s【%s】%s…" % (a, new, b))


def run(fixes, base=".", apply=False, mode="track", author="apply-proof-marks", date=None):
    """置換を当てる。(当てられた数, [(番号, 理由)]) を返す。apply で 1 件も失敗が無ければ書く。"""
    date = date or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    docs, ok, bad = {}, 0, []
    for f in fixes:
        path = f["file"] if os.path.isabs(f["file"]) else os.path.join(base, f["file"])
        if not path.lower().endswith(".docx"):
            bad.append((f["n"], "docx ではない: %s" % f["file"]))
            continue
        if path not in docs:
            try:
                docs[path] = Doc(path, mode, author, date)
            except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
                bad.append((f["n"], "開けない: %s (%s)" % (f["file"], e)))
                continue
        d = docs[path]
        if not f["old"]:
            bad.append((f["n"], "修正前が空 (足す位置が決まらない)．前後の文字を含めて書く"))
            continue
        if f["old"] == f["new"]:
            bad.append((f["n"], "修正前と修正後が同じ"))
            continue
        if "\n" in f["old"] or "\n" in f["new"]:
            bad.append((f["n"], "改行を含む (段落をまたぐ置換は当てられない．段落ごとに分けるか手で直す)"))
            continue
        hits = d.find(f["old"])
        if len(hits) != f["count"]:
            bad.append((f["n"], "%d 件ヒット (%d 件のはず) — %s" % (len(hits), f["count"], f["old"][:40])))
            continue
        try:
            for p, i, text in reversed(hits):
                before, after = context(text, i, f["old"], f["new"])
                d.apply_one(p, i, f["old"], f["new"])
            print("  #%d %s\n    前: %s\n    後: %s" % (f["n"], os.path.basename(path), before, after))
            ok += 1
        except DocxError as e:
            bad.append((f["n"], "%s — %s" % (e, f["old"][:40])))
    print("当てられる %d 件 / 当てられない %d 件 (mode=%s)" % (ok, len(bad), mode))
    for n, why in bad:
        print("  - #%d %s" % (n, why))
    if bad:
        print("止めました (何も書いていない)。")
        return ok, bad
    if apply:
        for path, d in docs.items():
            d.write()
            print("  書き換え: %s (初回の写しは %s.bak)" % (path, os.path.basename(path)))
    else:
        print("(確かめただけ．当てるときは --apply を付ける)")
    return ok, bad


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["text"]:
        ap = argparse.ArgumentParser(prog="apply_docx.py text")
        ap.add_argument("docx")
        a = ap.parse_args(argv[1:])
        print(docx_text(a.docx))
        return 0
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("fixes", help="置換リスト (JSON)")
    ap.add_argument("--apply", action="store_true", help="書き込む (付けなければ確かめるだけ)")
    ap.add_argument("--mode", choices=MODES, default="track", help="track (変更履歴．既定)・direct (書き換え)・comment (コメント)")
    ap.add_argument("--author", default="apply-proof-marks", help="変更履歴とコメントの作成者名")
    ap.add_argument("--base", default=".", help="file を解決するディレクトリ")
    a = ap.parse_args(argv)
    _ok, bad = run(load_fixes(a.fixes), a.base, a.apply, a.mode, a.author)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
