#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指摘の「型」ごとに、原稿全体を照合する。

同じ型の指摘が2回出たら、個別に直すだけでは必ず取り残しが出る。
その型を原稿全体で洗うのがこのスクリプト。

使い方:
  python scan_recurring.py --list                # 型の一覧
  python scan_recurring.py                       # 機械照合できる型を全部
  python scan_recurring.py --type terms fig-leaf # 型を指定
  python scan_recurring.py --glob "body/*.md"    # 原稿の場所を指定

設定(任意): カレントの _polish/config.json
  {"manuscript": "chapter_*.md",
   "figure_sources": ["make_flowcharts.R"],
   "terms": [["デンドログラム", "樹形図"]]}

注意: `\\n` を含む文字列を扱うので、置換には chr(92) を使う。
      ヒアドキュメント経由で書くと `\\\\` が潰れて空振りする。
"""
import argparse
import collections
import glob as globmod
import io
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BS = chr(92)   # バックスラッシュ。リテラルで書くと環境によって潰れる

DEFAULT_TERMS = [
    ("カラーバー", "色バー"), ("バイオリンプロット", "バイオリン図"),
    ("デンドログラム", "樹形図"), ("モザイクプロット", "モザイク図"),
    ("三角グラフ", "三角図"), ("どうし", "同士"), ("乱数種", "乱数の種"),
    ("パネル記号", "タグ"), ("図題", "キャプション"), ("標本サイズ", "標本数"),
    ("既定", "デフォルト"), ("読み手", "受け手"),
]
FORBIDDEN = [("全角括弧", "（"), ("全角括弧", "）"), ("読点、", "、"), ("句点。", "。"),
             ("en ダッシュ", "–"), ("≈", "≈"), ("波ダッシュ", "〜")]


def load_config():
    cfg = {}
    p = os.path.join("_polish", "config.json")
    if os.path.exists(p):
        cfg = json.loads(io.open(p, encoding="utf-8").read())
    return cfg


def body_lines(path):
    """コードブロックの外の行だけを (行番号, 行) で返す。"""
    fence = False
    for i, ln in enumerate(io.open(path, encoding="utf-8"), 1):
        if ln.lstrip().startswith("```"):
            fence = not fence
            continue
        if not fence:
            yield i, ln.rstrip("\n")


def short(path):
    return os.path.basename(path).replace("chapter_", "ch")[:8]


# --- 型ごとの照合 --------------------------------------------------------

def t_next(files, cfg):
    """「次の」で複数を指していないか(1つのときだけ「次の」)。"""
    hits = []
    for f in files:
        for i, ln in body_lines(f):
            m = re.search(r"次の(\d+|いくつか|どれか|ような)", ln)
            if m:
                hits.append("%s:%d %s" % (short(f), i, ln.strip()[:58]))
    return hits


def t_plain(files, cfg):
    """地の文の常体。"""
    hits = []
    for f in files:
        for i, ln in body_lines(f):
            s = ln.strip()
            if not s or s[0] in "|-># ![":
                continue
            if re.search(r"(である|であった|だった|していた|ではない)．$", s):
                hits.append("%s:%d %s" % (short(f), i, s[:58]))
    return hits


def t_becomes(files, cfg):
    """変化でない「〜になります」。"""
    hits = []
    for f in files:
        for i, ln in body_lines(f):
            if re.search(r"(です|ます|ある|同じ|とおり|結果|こと|よう)になります", ln):
                hits.append("%s:%d %s" % (short(f), i, ln.strip()[:58]))
    return hits


def t_donoun(files, cfg):
    """「Xを行う」(慣用のものは目視で外す)。"""
    hits = []
    for f in files:
        for i, ln in body_lines(f):
            if re.search(r"[ぁ-んァ-ヶ一-龥]を(行い|行う|行っ|実施す)", ln):
                hits.append("%s:%d %s" % (short(f), i, ln.strip()[:58]))
    return hits


def t_terms(files, cfg):
    """用語のゆれ。config の terms を足せる。"""
    pairs = DEFAULT_TERMS + [tuple(x) for x in cfg.get("terms", [])]
    texts = {f: io.open(f, encoding="utf-8").read() for f in files}
    allt = "".join(texts.values())
    hits = []
    for good, bad in pairs:
        # 「目盛」が「目盛り」に含まれるような部分一致を避ける
        pat = re.escape(bad) + (r"(?!" + re.escape(good[len(bad):]) + r")" if good.startswith(bad) else "")
        n = len(re.findall(pat, allt))
        if n:
            where = [short(f) for f in files if re.search(pat, texts[f])]
            hits.append("「%s」%d 件 ←→ 正 「%s」%d 件  %s"
                        % (bad, n, good, allt.count(good), " ".join(where)))
    return hits


def t_forbidden(files, cfg):
    hits = []
    for f in files:
        for i, ln in enumerate(io.open(f, encoding="utf-8"), 1):
            for label, ch in FORBIDDEN:
                if ch in ln:
                    hits.append("%s:%d %s  %s" % (short(f), i, label, ln.strip()[:44]))
    return hits


def t_heading(files, cfg):
    """見出しの節番号の直後の空白(一括置換の巻き添えで消えやすい)。"""
    hits = []
    for f in files:
        for i, ln in body_lines(f):
            # 「4組は」のような数え上げを節番号と誤認しないよう、点を含む番号だけ見る
            m = re.match(r"^(#+)\s+(\d+\.\d+(?:\.\d+)*)(.)", ln)
            if m and m.group(3) != " ":
                hits.append("%s:%d %s" % (short(f), i, ln.strip()[:50]))
    return hits


def t_selfref(files, cfg):
    """自分の章を指す参照。"""
    hits = []
    for f in files:
        txt = io.open(f, encoding="utf-8").read()
        m = re.search(r"^# .*\{#([" + r"\w-" + r"]+)\}", txt, re.M)
        if not m:
            continue
        for i, ln in body_lines(f):
            if re.search(r"@ref\(" + re.escape(m.group(1)) + r"\)", ln):
                hits.append("%s:%d %s" % (short(f), i, ln.strip()[:56]))
    return hits


def t_exercises(files, cfg):
    """練習問題の数と解答の数。"""
    hits = []
    for f in files:
        txt = io.open(f, encoding="utf-8").read()
        q = re.search(r"## [\d.]+ 練習問題 \{[^}]*\}(.*?)(?=\n## )", txt, re.S)
        a = re.search(r"## [\d.]+ 練習問題の解答例 \{[^}]*\}(.*)", txt, re.S)
        if not q or not a:
            continue
        nq = len(re.findall(r"^\d+\. ", q.group(1), re.M))
        na = len(re.findall(r"^### 解答", a.group(1), re.M))
        if nq != na:
            hits.append("%s 問 %d / 解答 %d" % (short(f), nq, na))
    return hits


def t_axis(files, cfg):
    """図の軸ラベルにコードの内部名が出ていないか。"""
    pat = re.compile(r"(?:labs|set_xlabel|set_ylabel|xlab|ylab)\s*\(([^\n]*)")
    hits = []
    for f in files:
        fence = None
        for i, ln in enumerate(io.open(f, encoding="utf-8"), 1):
            s = ln.strip()
            if s.startswith("```"):
                fence = None if fence is not None else s[3:]
                continue
            if fence is None:
                continue
            code = ln.split("#")[0]     # コメントの中の語を拾わない
            m = pat.search(code)
            if not m:
                continue
            # 引用符の外に出ている式(reorder(...) など)や Var1/Var2 を疑う
            if re.search(r"(reorder|factor|as\.|\bVar\d\b|aes\()", m.group(1)):
                hits.append("%s:%d %s" % (short(f), i, s[:58]))
    return hits


def t_lablang(files, cfg):
    """R版とPython版で、図の中の文字の言語が食い違っていないか。"""
    LAB = re.compile(r"(?:labs|set_xlabel|set_ylabel|xlab|ylab)\s*\(([^\n]*)")
    hits = []
    for f in files:
        txt = io.open(f, encoding="utf-8").read()
        blocks = re.findall(r"```(?:r|python)\n# (code_\d+_\d+_(?:R|py))\n(.*?)```", txt, re.S)
        d = {}
        for cid, code in blocks:
            labs = []
            for m in LAB.finditer(code):
                for v in re.findall(r'"([^"]+)"', m.group(1)):
                    if not re.fullmatch(r"[\s%.\-0-9]*", v):
                        labs.append(v)
            d[cid] = labs
        for cid in d:
            if not cid.endswith("_R"):
                continue
            py = cid[:-2] + "_py"
            if py not in d or not d[cid] or not d[py]:
                continue
            ja = lambda xs: any(re.search(r"[ぁ-んァ-ヶ一-龥]", x) for x in xs)
            if ja(d[cid]) != ja(d[py]):
                hits.append("%s %s  R:%s / Py:%s"
                            % (short(f), cid[:-2], "，".join(d[cid])[:26], "，".join(d[py])[:26]))
    return hits


def t_figleaf(files, cfg):
    """図の生成元にある「行き先(葉)」の語が、本文にも同じ表記であるか。

    分岐の問い(「見せたいのは」など)は本文に出なくて当然なので、
    各 c(...) の**最後の要素**(＝行き先)だけを見る。
    """
    srcs = cfg.get("figure_sources", [])
    if not srcs:
        srcs = [p for p in ("make_flowcharts.R", "make_channel.py") if os.path.exists(p)]
    if not srcs:
        return ["(図の生成元が見つからない。config.json の figure_sources に書く)"]
    body = re.sub(r"\s", "", "".join(io.open(f, encoding="utf-8").read() for f in files))
    hits, seen = [], set()
    for src in srcs:
        if not os.path.exists(src):
            continue
        text = io.open(src, encoding="utf-8").read()
        for path in re.findall(r"c\((.*?)\)\)?,?\n", text):
            items = re.findall(r'"([^"]*)"', path)
            if not items:
                continue
            leaf = items[-1]
            if not re.search(r"[ぁ-んァ-ヶ一-龥]", leaf):
                continue
            # 「ヒストグラム，密度\n箱ひげ」のように複数の図名を並べた行き先は、
            # 語ごとに分けて照合する(つないだままだと本文に無くて当然)
            raw = re.sub(r"\(\d+章\)", "", leaf)
            # BS + "n" をそのまま正規表現に入れると改行の意味になるので必ずエスケープする
            for part in re.split(r"[，、]|" + re.escape(BS) + "n", raw):
                t = part.strip()
                if len(t) < 4 or t in seen:
                    continue
                seen.add(t)
                if re.sub(r"\s", "", t) not in body:
                    hits.append("%s 図の行き先「%s」が本文に無い" % (os.path.basename(src), t))
    return hits


def t_manual(files, cfg):
    """機械照合できない型。ここに挙げて「照合済み」と誤解しないようにする。"""
    return [
        "主述のねじれ・係り受けの崩れ … レビューに頼る",
        "括弧による補足の可否 … レビューに頼る",
        "論理の飛躍・重複説明 … レビューに頼る",
        "数値が実データと合うか … レビュアにコードを実行させて裏を取る",
        "参照先が内容として妥当か … 参照先の章を読んで確かめる",
    ]


TYPES = [
    ("next", "「次の」で複数を指していないか", t_next),
    ("plain", "地の文の常体", t_plain),
    ("becomes", "変化でない「〜になります」", t_becomes),
    ("donoun", "「Xを行う」", t_donoun),
    ("terms", "用語のゆれ", t_terms),
    ("forbidden", "禁止文字", t_forbidden),
    ("heading", "見出しの節番号のあとの空白", t_heading),
    ("selfref", "自分の章を指す参照", t_selfref),
    ("exercises", "練習問題と解答の数", t_exercises),
    ("axis", "図の軸に出たコードの内部名", t_axis),
    ("lablang", "RとPythonで図の中の言語が違う", t_lablang),
    ("fig-leaf", "図の中の語が本文に無い", t_figleaf),
    ("manual", "機械照合できない型(一覧のみ)", t_manual),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", nargs="*", help="型を指定(既定は manual 以外の全部)")
    ap.add_argument("--glob", help="原稿の glob(既定は config か chapter_*.md)")
    ap.add_argument("--list", action="store_true", help="型の一覧だけ出す")
    args = ap.parse_args()

    if args.list:
        for key, desc, _ in TYPES:
            print("  %-10s %s" % (key, desc))
        return 0

    cfg = load_config()
    pattern = args.glob or cfg.get("manuscript") or "chapter_*.md"
    files = sorted(globmod.glob(pattern))
    if not files:
        print("原稿が見つからない: %s" % pattern)
        return 1

    want = args.type or [k for k, _, _ in TYPES if k != "manual"]
    print("原稿 %d ファイル / 型 %d" % (len(files), len(want)))
    total = 0
    for key, desc, fn in TYPES:
        if key not in want:
            continue
        hits = fn(files, cfg)
        mark = "" if key == "manual" else ("  ★" if hits else "")
        print("\n[%s] %s … %d 件%s" % (key, desc, len(hits), mark))
        for h in hits[:20]:
            print("   " + h)
        if len(hits) > 20:
            print("   …ほか %d 件" % (len(hits) - 20))
        if key != "manual":
            total += len(hits)
    print("\n照合おわり。要確認 %d 件" % total)
    print("(誤検出が混じる。図・数値・API の主張は現物で裏を取ってから直す)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
