#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校正の採否の「決定の記録」(decisions.json) を作る・読む・更新する。

記録の置き場の既定は _review/marks/decisions.json (--file で変えられる)。
形式:
  {"decisions": [
    {"id": "K18", "tag": "flow", "label": "「フロー」を「流れ」にする",
     "status": "pending", "files": ["figures/a.png"],
     "items": [{"file": "chapter_08.md", "old": "フローの", "new": "流れの", "count": 1}]}
  ]}
status は pending (採否待ち)・approved (承認済み。未反映)・applied (反映済み)・rejected (直さない)。
files は、本文の置換ではなく丸ごと差し替わるファイル (図の PNG/PDF など。任意)。

使い方:
  python decisions.py add --id K18 --tag flow --label "「フロー」を「流れ」にする" \\
      --items-json '[{"file":"chapter_08.md","old":"フローの","new":"流れの"}]' [--files a.png,b.pdf] [--status approved]
  python decisions.py status K18 approved
  python decisions.py list [--status approved]
  python decisions.py to-fixes --ids K18,K19 [--out fixes.json]   # 承認済みだけを apply_fixes.py の置換リストにする
  python decisions.py mark-applied --ids K18,K19

--file は、サブコマンドの前に置く (例: python decisions.py --file d.json list)。
"""
import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

DEFAULT_FILE = "_review/marks/decisions.json"
STATUSES = ("pending", "approved", "applied", "rejected")
BOM = b"\xef\xbb\xbf"


def load(path):
    """(決定のリスト, BOM の有無) を返す。ファイルが無ければ空。"""
    p = Path(path)
    if not p.exists():
        return [], False
    raw = p.read_bytes()
    bom = raw.startswith(BOM)
    data = json.loads((raw[len(BOM):] if bom else raw).decode("utf-8"))
    decs = data.get("decisions") if isinstance(data, dict) else None
    if not isinstance(decs, list):
        raise ValueError('%s: {"decisions": [...]} の形でない' % path)
    return decs, bom


def save(path, decs, bom=False):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"decisions": decs}, ensure_ascii=False, indent=2) + "\n"
    p.write_bytes((BOM if bom else b"") + text.encode("utf-8"))


def split_ids(s):
    return [x.strip() for x in s.split(",") if x.strip()]


def parse_items(arg):
    p = Path(arg)
    text = p.read_text(encoding="utf-8-sig") if len(arg) < 260 and p.is_file() else arg
    items = json.loads(text)
    if not isinstance(items, list):
        raise ValueError("--items-json は配列にする")
    out = []
    for n, r in enumerate(items, 1):
        if not isinstance(r, dict) or "file" not in r:
            raise ValueError("items #%d: file が無い" % n)
        old = r["old"] if "old" in r else r.get("before")
        new = r["new"] if "new" in r else r.get("after")
        if old is None or new is None:
            raise ValueError("items #%d: old と new (または before と after) が要る" % n)
        cnt = r.get("count", 1)
        if not isinstance(cnt, int) or isinstance(cnt, bool) or cnt < 1:
            raise ValueError("items #%d: count は 1 以上の整数にする" % n)
        out.append({"file": r["file"], "old": old, "new": new, "count": cnt})
    return out


def find(decs, did):
    for d in decs:
        if d.get("id") == did:
            return d
    return None


def cmd_add(a):
    decs, bom = load(a.file)
    items = parse_items(a.items_json) if a.items_json else []
    entry = {"id": a.id, "tag": a.tag or "", "label": a.label, "status": a.status,
             "files": split_ids(a.files) if a.files else [], "items": items}
    for i, d in enumerate(decs):
        if d.get("id") == a.id:
            decs[i] = entry
            print("上書き: %s" % a.id)
            break
    else:
        decs.append(entry)
        print("追加: %s" % a.id)
    save(a.file, decs, bom)


def cmd_status(a):
    decs, bom = load(a.file)
    d = find(decs, a.id)
    if d is None:
        sys.exit("id が無い: %s" % a.id)
    d["status"] = a.state
    save(a.file, decs, bom)
    print("%s: %s" % (a.id, a.state))


def cmd_list(a):
    decs, _ = load(a.file)
    rows = [d for d in decs if not a.status or d.get("status") == a.status]
    print("id | tag | status | 項目 | files | label")
    for d in rows:
        print("%s | %s | %s | %d | %d | %s" % (
            d.get("id", ""), d.get("tag", ""), d.get("status", ""),
            len(d.get("items", [])), len(d.get("files", [])), d.get("label", "")))
    print("(%d 件)" % len(rows))


def cmd_to_fixes(a):
    decs, _ = load(a.file)
    ids = split_ids(a.ids) if a.ids else [d["id"] for d in decs if d.get("status") == "approved"]
    rows = []
    for did in ids:
        d = find(decs, did)
        if d is None:
            sys.exit("id が無い: %s" % did)
        if d.get("status") != "approved":
            print("飛ばす: %s は %s (承認済みだけを出す)" % (did, d.get("status")), file=sys.stderr)
            continue
        for it in d.get("items", []):
            row = {"file": it["file"], "old": it["old"], "new": it["new"]}
            if it.get("count", 1) != 1:
                row["count"] = it["count"]
            rows.append(row)
    text = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    if a.out:
        Path(a.out).write_bytes(text.encode("utf-8"))
        print("%d 件を書いた: %s" % (len(rows), a.out))
    else:
        sys.stdout.write(text)


def cmd_mark_applied(a):
    decs, bom = load(a.file)
    for did in split_ids(a.ids):
        d = find(decs, did)
        if d is None:
            sys.exit("id が無い: %s" % did)
        d["status"] = "applied"
    save(a.file, decs, bom)
    print("反映済みにした: %s" % a.ids)


def main(argv=None):
    ap = argparse.ArgumentParser(description="校正の採否の記録 (decisions.json)")
    ap.add_argument("--file", default=DEFAULT_FILE, help="記録の場所 (既定 %s)" % DEFAULT_FILE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add", help="決定を追加 (同じ id は上書き)")
    s.add_argument("--id", required=True)
    s.add_argument("--tag", default="")
    s.add_argument("--label", required=True)
    s.add_argument("--items-json", help="JSON 文字列またはファイル")
    s.add_argument("--files", help="丸ごと差し替わるファイル (カンマ区切り)")
    s.add_argument("--status", default="pending", choices=STATUSES)
    s.set_defaults(fn=cmd_add)
    s = sub.add_parser("status", help="状態を変える")
    s.add_argument("id")
    s.add_argument("state", choices=STATUSES)
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("list", help="一覧")
    s.add_argument("--status", choices=STATUSES)
    s.set_defaults(fn=cmd_list)
    s = sub.add_parser("to-fixes", help="承認済みを apply_fixes.py の置換リストにする")
    s.add_argument("--ids", help="カンマ区切り (省略なら承認済みすべて)")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_to_fixes)
    s = sub.add_parser("mark-applied", help="反映済みにする")
    s.add_argument("--ids", required=True)
    s.set_defaults(fn=cmd_mark_applied)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (ValueError, json.JSONDecodeError) as e:
        sys.exit("エラー: %s" % e)


if __name__ == "__main__":
    main()
