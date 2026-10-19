#!/usr/bin/env python3
"""朱書きの採否・修正案の項目が，原稿にもう反映されているかを判定する．

    python check_applied.py ITEMS.json [--root DIR] [--json]

ITEMS.json は次のどちらでもよい．
  [{"id","file","old","new"}, ...]
  {"decisions":[{"id","items":[{"file","old","new"}, ...]}, ...]}

判定:
  applied  new が原稿にあり，old は無い (new が空なら old が無い)
  pending  old があり，new は無い
  both     両方ある (一部だけ反映された可能性)
  moot     どちらも無い (別の直しで文が変わった．対象が消えた)
  nofile   file が読めない (参考)
空白 (半角・全角・改行) の違いは無視して照合する．終了コードは常に 0．
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

LABEL = {"applied": "反映済み", "pending": "未反映", "both": "両方あり",
         "moot": "対象なし", "nofile": "ファイル不明"}


def read_text(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8-sig", "replace")


def norm(s):
    return re.sub(r"\s+", "", s or "")


def judge(text_n, old, new):
    """正規化済みの原稿に対する判定を返す."""
    old_n, new_n = norm(old), norm(new)
    has_old = bool(old_n) and old_n in text_n
    has_new = bool(new_n) and new_n in text_n
    if not new_n:
        return "pending" if has_old else "applied"
    if old_n and old_n in new_n:      # 追記型: old は new の一部なので手がかりにならない
        return "applied" if has_new else ("pending" if has_old else "moot")
    if has_new and has_old:
        return "both"
    if has_new:
        return "applied"
    if has_old:
        return "pending"
    return "moot"


def flatten(data):
    if isinstance(data, dict):
        data = data.get("decisions", [])
    out = []
    for d in data:
        if "items" in d:
            n = len(d["items"])
            for k, it in enumerate(d["items"]):
                out.append({"id": d.get("id", "") if n == 1 else "%s-%d" % (d.get("id", ""), k + 1),
                            "file": it.get("file", ""), "old": it.get("old", ""),
                            "new": it.get("new", "")})
        else:
            out.append({"id": d.get("id", ""), "file": d.get("file", ""),
                        "old": d.get("old", ""), "new": d.get("new", "")})
    return out


def check(items, root):
    cache, all_md = {}, None
    results = []
    for it in items:
        f = it["file"]
        if f:
            p = os.path.join(root, f)
            if p not in cache:
                cache[p] = norm(read_text(p)) if os.path.isfile(p) else None
            t = cache[p]
        else:   # file 指定なし: root 直下の *.md を連結
            if all_md is None:
                all_md = norm("".join(read_text(os.path.join(root, n))
                                      for n in sorted(os.listdir(root)) if n.endswith(".md")))
            t = all_md
        j = "nofile" if t is None else judge(t, it["old"], it["new"])
        results.append({"id": it["id"], "file": f, "judgement": j})
    return results


def main():
    ap = argparse.ArgumentParser(description="朱書きの項目が原稿に反映済みかを判定する")
    ap.add_argument("items")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    with open(a.items, "rb") as fh:
        data = json.loads(fh.read().decode("utf-8-sig"))
    results = check(flatten(data), a.root)
    counts = {}
    for r in results:
        counts[r["judgement"]] = counts.get(r["judgement"], 0) + 1
    if a.json:
        print(json.dumps({"results": results, "counts": counts}, ensure_ascii=False, indent=2))
        return
    for r in results:
        print("%s\t%s\t%s (%s)" % (r["id"], r["file"], r["judgement"], LABEL[r["judgement"]]))
    print("--- 件数 ---")
    for k in ("applied", "pending", "both", "moot", "nofile"):
        if counts.get(k):
            print("%s (%s): %d" % (k, LABEL[k], counts[k]))
    print("合計: %d" % len(results))


if __name__ == "__main__":
    main()
