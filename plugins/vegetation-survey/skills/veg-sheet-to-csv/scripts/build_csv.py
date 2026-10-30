#!/usr/bin/env python3
"""植生調査票の読み取り結果 (JSON) から，植生調査資料DB形式の CSV を作る.

    python build_csv.py data.json -o out/調査表 [--layout single|two] [--kana half|full]
                        [--missing blank|na] [--encoding cp932|utf-8-sig|utf-8]
                        [--eol crlf|lf] [--unknown-code 0|blank] [--key-col NAME]

入力 JSON は {"sheets": [{"site": {列名: 値}, "species": [{列名: 値}, ...]}, ...]}.
1枚だけなら {"site": ..., "species": [...]} でもよい.
列名は CSV の列名そのまま (資料調査番号，調査年月日，階層，種名，学名 など).
species には「被度・群度」("3,4" や "+") を書くと，被度階級値と群度に分ける (+ や r だけのときは群度 1).
site の「出現種数」は列ではなく，種名の数との照合に使う.
"""

import argparse
import csv
import io
import json
import re
import sys
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SITE_COLS = [
    "資料調査番号", "調査票No", "調査地点No", "調査年月日", "調査者名", "データ公開レベル",
    "国コード", "都道府県", "市郡町村区名", "以下", "緯度", "経度", "地点精度", "３次メッシュコード",
    "地形条件", "斜面方位", "傾斜角度", "標高", "面積1", "面積2", "面積測定方法", "被度の評価方法",
    "群落名", "備考",
    "高木層階層高", "高木層植被率", "亜高木層階層高", "亜高木層植被率",
    "第1低木層階層高", "第1低木層植被率", "第2低木層階層高", "第2低木層植被率",
    "第1草本層階層高", "第1草本層植被率", "第2草本層階層高", "第2草本層植被率", "コケ層植被率",
]
SPECIES_COLS = [
    "行番号", "階層", "種名", "種名（公開用）", "科名", "学名", "被度階級値", "群度", "被度百分率",
    "絶滅危惧種フラグ",
]
ALL_COLS = SITE_COLS + SPECIES_COLS
LAYERS = ["T1", "T2", "S1", "S2", "H1", "H2", "M"]
# 値が無いとき空欄／NA にせず，既定の符号を入れる列
SITE_DEFAULTS = {"データ公開レベル": "公開", "国コード": "日本国"}
UNKNOWN_CODE_COLS = ["面積測定方法", "被度の評価方法"]

# 半角カナ <-> 全角カナ
_F2H = {}
for _c in range(0xFF61, 0xFFA0):
    _h = chr(_c)
    _f = unicodedata.normalize("NFKC", _h)
    if _f != _h:
        _F2H[_f] = _h
for _f in "ガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポヴ":
    _d = unicodedata.normalize("NFD", _f)
    _F2H[_f] = _F2H[_d[0]] + ("ﾞ" if _d[1] == "゙" else "ﾟ")


def to_full(s):
    s = unicodedata.normalize("NFKC", s)  # 半角カナ (濁点つき) を全角に寄せる
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def to_half(s):
    return "".join(_F2H.get(c, c) for c in to_full(s))


def convert_kana(s, mode):
    return to_half(s) if mode == "half" else to_full(s)


def split_cover(sp):
    """「3,4」「3・4」のような「被度・群度」を 被度階級値と群度に分ける。+ や r だけのときは群度を 1 とする."""
    cg = sp.pop("被度・群度", None)
    if cg is None or str(cg).strip() == "":
        return
    parts = [p for p in re.split(r"[,，・.．\s]+", str(cg).strip()) if p]
    sp["被度階級値"] = parts[0]
    if len(parts) > 1:
        sp["群度"] = parts[1]
    elif parts[0] in ("+", "r"):
        sp["群度"] = "1"


EXTRA_SITE_KEYS = {"出現種数"}
EXTRA_SPECIES_KEYS = {"被度・群度"}


def check_sheet(i, sheet, warnings):
    site, species = sheet["site"], sheet["species"]
    for k in site:
        if k not in SITE_COLS and k not in EXTRA_SITE_KEYS:
            warnings.append("sheet %d: site の列名 %r は CSV に無いので捨てる (綴りの誤りか)" % (i, k))
    seen = set()
    for sp in species:
        for k in sp:
            if k not in SPECIES_COLS and k not in EXTRA_SPECIES_KEYS:
                warnings.append("sheet %d: species の列名 %r は CSV に無いので捨てる (綴りの誤りか)" % (i, k))
        lay = str(sp.get("階層", ""))
        if lay not in LAYERS:
            warnings.append("sheet %d: 階層 %r は %s のどれでもない (%s)" % (i, lay, "/".join(LAYERS), sp.get("種名")))
        key = (lay, to_full(str(sp.get("種名") or "")))  # カナの全角・半角の違いは同じ名前とみる
        if key in seen:
            warnings.append("sheet %d: 同じ階層に同じ種名が2回ある: %s %s" % (i, lay, sp.get("種名")))
        seen.add(key)
        if not sp.get("学名"):
            warnings.append("sheet %d: 学名が空: %s" % (i, sp.get("種名")))
        if not str(sp.get("被度階級値", "")).strip():
            warnings.append("sheet %d: 被度階級値が空: %s %s" % (i, lay, sp.get("種名")))
    expected = site.get("出現種数")
    if expected not in (None, ""):
        n = len({to_full(str(sp.get("種名") or "")) for sp in species})
        if str(expected) != str(n):
            warnings.append("sheet %d: 出現種数 %s と種名の数 %d が違う" % (i, expected, n))


def build(data, kana="half", missing="blank", layout="single", unknown_code="0"):
    sheets = data["sheets"] if "sheets" in data else [data]
    warnings = []
    na = "NA" if missing == "na" else ""
    site_rows, spec_rows, single_rows = [], [], []
    used_ids = set()

    def fill(v):
        return na if v is None or str(v).strip() == "" else str(v)

    for i, sheet in enumerate(sheets, 1):
        sheet = {"site": dict(sheet["site"]), "species": [dict(s) for s in sheet["species"]]}
        for sp in sheet["species"]:
            split_cover(sp)
        check_sheet(i, sheet, warnings)
        site = sheet["site"]
        if unknown_code == "0":
            for c in UNKNOWN_CODE_COLS:
                if not str(site.get(c, "")).strip():
                    site[c] = "0"
        for c, v in SITE_DEFAULTS.items():
            if not str(site.get(c, "")).strip():
                site[c] = v
        sid = str(site.get("資料調査番号") or "").strip() or "S%03d" % i
        if sid in used_ids:
            warnings.append("sheet %d: 資料調査番号 %s が前の調査票と重なる (2ファイルのとき別の地点が結び付く)" % (i, sid))
        used_ids.add(sid)
        srow = [fill(site.get(c)) for c in SITE_COLS]
        for sp in sheet["species"]:
            if not str(sp.get("絶滅危惧種フラグ", "")).strip():
                sp["絶滅危惧種フラグ"] = "0"
            sp["種名"] = convert_kana(str(sp.get("種名", "")), kana)
            pub = str(sp.get("種名（公開用）") or sp["種名"])
            sp["種名（公開用）"] = convert_kana(pub, kana)
            prow = [fill(sp.get(c)) for c in SPECIES_COLS]
            if layout == "single":
                single_rows.append(srow + prow)
            else:
                spec_rows.append([sid] + prow)
        site_rows.append([sid] + srow)
    return warnings, site_rows, spec_rows, single_rows


def render_csv(header, rows, encoding, eol):
    """CSV を先に全部エンコードする (書けない文字があっても，既存のファイルを壊さない)."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n" if eol == "crlf" else "\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode(encoding)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json")
    ap.add_argument("-o", "--out", required=True, help="出力の接頭辞 (拡張子なし)")
    ap.add_argument("--layout", choices=["single", "two"], default="single")
    ap.add_argument("--kana", choices=["half", "full"], default="half")
    ap.add_argument("--missing", choices=["blank", "na"], default="blank")
    ap.add_argument("--encoding", choices=["cp932", "utf-8-sig", "utf-8"], default="cp932")
    ap.add_argument("--eol", choices=["crlf", "lf"], default="crlf")
    ap.add_argument("--unknown-code", choices=["0", "blank"], default="0",
                    help="面積測定方法・被度の評価方法が不明なときの値 (既定は見本と同じ 0)")
    ap.add_argument("--key-col", default="調査ID", help="2ファイルのときの結合キー列の名前")
    a = ap.parse_args(argv)

    with open(a.json, encoding="utf-8-sig") as f:
        data = json.load(f)
    warnings, site_rows, spec_rows, single_rows = build(data, a.kana, a.missing, a.layout, a.unknown_code)
    try:
        write_all(a, site_rows, spec_rows, single_rows)
    except UnicodeEncodeError as e:
        print("エラー: %s で書けない文字がある (%r)．--encoding utf-8-sig にするか，文字を直す" % (a.encoding, e.object[e.start:e.end]), file=sys.stderr)
        return 1
    for w in warnings:
        print("警告:", w, file=sys.stderr)
    return 0


def write_all(a, site_rows, spec_rows, single_rows):
    if a.layout == "single":
        outs = [(a.out + ".csv", ALL_COLS, single_rows)]
    else:
        outs = [(a.out + "_地点.csv", [a.key_col] + SITE_COLS, site_rows),
                (a.out + "_組成.csv", [a.key_col] + SPECIES_COLS, spec_rows)]
    rendered = [(p, h, r, render_csv(h, r, a.encoding, a.eol)) for p, h, r in outs]  # 全部できてから書く
    for path, header, rows, blob in rendered:
        with open(path, "wb") as f:
            f.write(blob)
        print("%s: %d 行 x %d 列" % (path, len(rows), len(header)))


if __name__ == "__main__":
    sys.exit(main())
