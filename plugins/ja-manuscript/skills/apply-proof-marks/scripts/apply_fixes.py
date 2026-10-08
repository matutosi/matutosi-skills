# -*- coding: utf-8 -*-
"""朱書きの反映を、置換リストからまとめて適用する。

1件ずつ Edit を呼ぶ代わりに、置換の表を1つ渡して一括で当てる。
**それぞれの検索文字列がちょうど1回だけ現れることを確かめてから**書き換えるので、
数が合わなければ何も書かずに止まる(部分適用にならない)。

置換リスト(JSON)の形:
[
  {"file": "chapter_05_amount_proportion.md",
   "old": "よく使うグラフほど，正しく",
   "new": "よく使うグラフほど正しく"},
  {"file": "chapter_05_amount_proportion.md",
   "old": "この行はまるごと消す．\n",
   "new": ""}
]

使い方:
    python apply_fixes.py fixes.json              # 確認だけ(何も書かない)
    python apply_fixes.py fixes.json --apply      # 適用する
    python apply_fixes.py fixes.json --apply --post   # 適用して後処理も走らせる

--post は sentence-per-line / markdown-table-pad / check_manuscript.py を順に呼ぶ。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# 整形のスキルは同じ置き場 (プラグインなら同じプラグイン) の兄弟にある
SKILLS = Path(__file__).resolve().parents[2]
SPL = SKILLS / "sentence-per-line" / "scripts" / "sentence_per_line.py"
PAD = SKILLS / "markdown-table-pad" / "scripts" / "pad_tables.py"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fixes", help="置換リストの JSON")
    ap.add_argument("--apply", action="store_true", help="実際に書き換える")
    ap.add_argument("--post", action="store_true", help="適用後に整形と点検を走らせる")
    args = ap.parse_args()

    fixes = json.loads(Path(args.fixes).read_text(encoding="utf-8"))
    by_file = {}
    for i, fx in enumerate(fixes, start=1):
        by_file.setdefault(fx["file"], []).append((i, fx["old"], fx["new"]))

    ng = []
    staged = {}
    for f, items in by_file.items():
        p = Path(f)
        if not p.exists():
            ng.append("%s が無い" % f)
            continue
        t = p.read_text(encoding="utf-8")
        for i, old, new in items:
            c = t.count(old)
            if c != 1:
                ng.append("#%d %s: %d 件ヒット — %s" % (i, f, c, old[:40].replace("\n", "/")))
                continue
            t = t.replace(old, new)
        staged[f] = t

    if ng:
        print("止めました。次を直してから再実行してください。")
        for x in ng:
            print("  -", x)
        return 1

    print("%d 件、%d ファイル。すべて1件ヒットで一致しました。" % (len(fixes), len(staged)))
    if not args.apply:
        print("(確認のみ。--apply で書き換えます)")
        return 0

    for f, t in staged.items():
        Path(f).write_text(t, encoding="utf-8", newline="\n")
        print("  書き換え:", f)

    if args.post:
        files = sorted(staged)
        for script in (SPL, PAD):
            if script.exists():
                subprocess.run([sys.executable, str(script)] + files)
        if Path("check_manuscript.py").exists():
            subprocess.run([sys.executable, "check_manuscript.py"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
