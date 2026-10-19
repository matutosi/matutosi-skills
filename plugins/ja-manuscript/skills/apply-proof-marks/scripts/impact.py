#!/usr/bin/env python3
"""節・図・コードを動かす (消す・移す・番号を振り直す) 判断の影響を調べる.

    python impact.py [--root DIR] [--json] label LABEL
    python impact.py [--root DIR] [--json] range FILE:A-B
    python impact.py [--root DIR] [--json] text STRING [--prose]
    python impact.py [--root DIR] [--json] figure 11_03|ファイル名

原稿の記法: 見出しの {#ラベル}，相互参照 \\@ref(ラベル)，
図は ![説明](figures/...) と「図．NN_NN_R：…」の図題，本文の「図 NN_NN」，
コードブロック先頭行の「# code_NN_NN_R」．対象は --root 直下の *.md.
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

RE_DEF = re.compile(r"\{#([^\s}]+)\}")
RE_REF = re.compile(r"\\@ref\(([^)\s]+)\)")
RE_IMG = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
RE_CAP = re.compile(r"^\s*図[．.]\s*(\d+_\d+)(?:_\w+)?")
RE_FIGTXT = re.compile(r"図\s*(\d+_\d+)")
RE_CODEID = re.compile(r"code_\d+_\d+_\w+")
RE_CODEHEAD = re.compile(r"^\s*#\s*(code_\d+_\d+_\w+)")
RE_NUM = re.compile(r"(\d+_\d+)")
RE_FENCE = re.compile(r"^\s*(```|~~~)")


def read_lines(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8-sig", "replace").splitlines()


def load(root):
    docs = {}
    for n in sorted(os.listdir(root)):
        if n.endswith(".md"):
            lines = read_lines(os.path.join(root, n))
            incode, flags = False, []
            for ln in lines:
                if RE_FENCE.match(ln):
                    flags.append(True)       # フェンス行もコード扱い
                    incode = not incode
                else:
                    flags.append(incode)
            docs[n] = {"lines": lines, "code": flags}
    return docs


def hit(f, i, kind, line, extra=None):
    h = {"file": f, "line": i + 1, "kind": kind, "text": line.strip()[:60]}
    if extra:
        h.update(extra)
    return h


def heading_ctx(lines):
    """各行が属する直近の見出し行を返す."""
    ctx, cur = [], ""
    for ln in lines:
        if re.match(r"^#{1,6}\s", ln):
            cur = ln
        ctx.append(cur)
    return ctx


def defs_label(docs, label):
    out = []
    for f, d in docs.items():
        for i, ln in enumerate(d["lines"]):
            if not d["code"][i] and any(m.group(1) == label for m in RE_DEF.finditer(ln)):
                out.append(hit(f, i, "定義", ln))
    return out


def refs_label(docs, label):
    out = []
    for f, d in docs.items():
        for i, ln in enumerate(d["lines"]):
            if any(m.group(1) == label for m in RE_REF.finditer(ln)):
                out.append(hit(f, i, "参照", ln))
    return out


def figure_hits(docs, key):
    """図番号 (NN_NN) またはファイル名の出現を種類別に集める."""
    is_num = RE_NUM.fullmatch(key) is not None
    out = []
    for f, d in docs.items():
        ctx = heading_ctx(d["lines"])
        for i, ln in enumerate(d["lines"]):
            if d["code"][i]:
                continue
            kinds = []
            if is_num:
                cap = RE_CAP.match(ln)
                if cap:
                    if cap.group(1) == key:
                        kinds.append("図題")
                elif any(x.group(1) == key for x in RE_FIGTXT.finditer(ln)):
                    kinds.append("本文")
                for im in RE_IMG.finditer(ln):
                    if key in os.path.basename(im.group(1)):
                        kinds.append("画像リンク")
            else:
                for im in RE_IMG.finditer(ln):
                    if key in im.group(1):
                        kinds.append("画像リンク")
                if not kinds and key in ln:
                    kinds.append("本文")
            for k in kinds:
                where = f + " " + ctx[i]
                if re.search(r"練習|演習|exercise|practice", where, re.I):
                    k = "練習問題"
                elif re.search(r"付録|appendix", where, re.I):
                    k = "付録"
                out.append(hit(f, i, k, ln))
    return out


def cmd_label(docs, a):
    return {"title": "ラベル %s の影響" % a.arg,
            "sections": [("定義", defs_label(docs, a.arg)),
                         ("参照元", refs_label(docs, a.arg))]}


def cmd_figure(docs, a):
    return {"title": "図 %s の参照元" % a.arg,
            "sections": [("参照元", figure_hits(docs, a.arg))]}


def cmd_text(docs, a):
    out = []
    for f, d in docs.items():
        for i, ln in enumerate(d["lines"]):
            s = ln
            if a.prose:
                if d["code"][i]:
                    continue
                s = re.sub(r"`[^`]*`", "", s)
            c = s.count(a.arg)
            if c:
                out.append(hit(f, i, "出現", ln, {"count": c}))
    total = sum(h["count"] for h in out)
    return {"title": "文字列「%s」の出現%s: 合計 %d 件" % (
        a.arg, " (コードとインラインコードを除く)" if a.prose else "", total),
        "sections": [("出現", out)]}


def cmd_range(docs, a):
    m = re.fullmatch(r"(.+):(\d+)-(\d+)", a.arg)
    if not m or m.group(1) not in docs:
        sys.exit("FILE:A-B の形で，--root 直下の既存ファイルを指定してください: %s" % a.arg)
    f, lo, hi = m.group(1), int(m.group(2)), int(m.group(3))
    d = docs[f]
    labels, figs, codes = set(), set(), set()
    for i in range(lo - 1, min(hi, len(d["lines"]))):
        ln = d["lines"][i]
        if not d["code"][i]:
            labels.update(x.group(1) for x in RE_DEF.finditer(ln))
            c = RE_CAP.match(ln)
            if c:
                figs.add(c.group(1))
            for im in RE_IMG.finditer(ln):
                n = RE_NUM.search(os.path.basename(im.group(1)))
                if n:
                    figs.add(n.group(1))
        else:
            c = RE_CODEHEAD.match(ln)
            if c:
                codes.add(c.group(1))

    def outside(h):
        return not (h["file"] == f and lo <= h["line"] <= hi)

    broken = []
    for lb in sorted(labels):
        broken += [dict(h, kind="参照 " + lb) for h in refs_label(docs, lb) if outside(h)]
    for fg in sorted(figs):
        broken += [dict(h, kind="図 %s の%s" % (fg, h["kind"]))
                   for h in figure_hits(docs, fg) if outside(h)]
    for cid in sorted(codes):
        for g, dd in docs.items():
            for i, ln in enumerate(dd["lines"]):
                h = hit(g, i, "コード " + cid, ln)
                if cid in ln and outside(h):
                    broken.append(h)
    # 範囲より後ろの図・コード (同じファイル) = 番号を振り直す対象
    shift_figs, shift_codes = [], []
    for i in range(hi, len(d["lines"])):
        ln = d["lines"][i]
        if not d["code"][i]:
            c = RE_CAP.match(ln)
            if c:
                shift_figs.append(hit(f, i, "図 " + c.group(1), ln))
        else:
            c = RE_CODEHEAD.match(ln)
            if c:
                shift_codes.append(hit(f, i, c.group(1), ln))
    summary = ("範囲内: ラベル %d・図 %d・コード %d / 壊れる参照 %d 件 / "
               "繰り上がる図 %d 件・コード %d 件" % (
                   len(labels), len(figs), len(codes), len(broken),
                   len(shift_figs), len(shift_codes)))
    return {"title": "%s の範囲を動かした場合の影響" % a.arg, "summary": summary,
            "found": {"labels": sorted(labels), "figures": sorted(figs), "codes": sorted(codes)},
            "counts": {"broken": len(broken), "shift_figures": len(shift_figs),
                       "shift_codes": len(shift_codes)},
            "sections": [("壊れる参照 (範囲の外から)", broken),
                         ("繰り上がる図 (同じファイルの後ろ)", shift_figs),
                         ("繰り上がるコード (同じファイルの後ろ)", shift_codes)]}


def show(res):
    print(res["title"])
    if res.get("summary"):
        print(res["summary"])
    for k, v in (res.get("found") or {}).items():
        print("  %s: %s" % (k, ", ".join(v) or "なし"))
    for name, hits in res["sections"]:
        print("\n[%s] %d 件" % (name, len(hits)))
        for h in hits:
            print("  %s:%d\t%s\t%s" % (h["file"], h["line"], h["kind"], h["text"]))


def main():
    ap = argparse.ArgumentParser(description="構造を変える判断の影響を調べる")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("label", "range", "text", "figure"):
        p = sub.add_parser(n)
        p.add_argument("arg")
        p.add_argument("--root", default=argparse.SUPPRESS)
        p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        if n == "text":
            p.add_argument("--prose", action="store_true")
    a = ap.parse_args()
    docs = load(a.root)
    res = {"label": cmd_label, "range": cmd_range, "text": cmd_text,
           "figure": cmd_figure}[a.cmd](docs, a)
    if a.json:
        res["sections"] = [{"name": n, "hits": h} for n, h in res["sections"]]
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        show(res)


if __name__ == "__main__":
    main()
