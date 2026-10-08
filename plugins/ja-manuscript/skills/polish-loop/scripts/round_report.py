#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""巡ごとの指摘数(高・中・低)と、指摘の型の出現回数を記録する。

使い方:
  python round_report.py --add 5 1 15 11      # 巡5: 高1 中15 低11 を記録
  python round_report.py                      # 推移表を出す
  python round_report.py --type terms         # 型「terms」の出現を1回加算
  python round_report.py --types              # 型の出現回数(2回以上に印)

記録先は _polish/rounds.tsv と _polish/recurring.tsv(どちらも git 管理外)。
収束の目安は「高が2巡続けて0〜1件」かつ「残りが読み比べないと気づかない食い違いだけ」。
"""
import argparse
import io
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DIR = "_polish"
ROUNDS = os.path.join(DIR, "rounds.tsv")
RECUR = os.path.join(DIR, "recurring.tsv")


def ensure():
    if not os.path.isdir(DIR):
        os.makedirs(DIR)


def read_rounds():
    if not os.path.exists(ROUNDS):
        return []
    out = []
    for ln in io.open(ROUNDS, encoding="utf-8"):
        c = ln.strip().split("\t")
        if len(c) == 4 and c[0].isdigit():
            out.append(tuple(int(x) for x in c))
    return sorted(out)


def read_types():
    if not os.path.exists(RECUR):
        return {}
    d = {}
    for ln in io.open(RECUR, encoding="utf-8"):
        c = ln.strip().split("\t")
        if len(c) == 2 and c[1].isdigit():
            d[c[0]] = int(c[1])
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", nargs=4, metavar=("巡", "高", "中", "低"), type=int)
    ap.add_argument("--type", help="この型の出現を1回加算する")
    ap.add_argument("--types", action="store_true", help="型の出現回数を出す")
    args = ap.parse_args()

    if args.add:
        ensure()
        rows = [r for r in read_rounds() if r[0] != args.add[0]] + [tuple(args.add)]
        with io.open(ROUNDS, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("巡\t高\t中\t低\n")
            for r in sorted(rows):
                fh.write("%d\t%d\t%d\t%d\n" % r)
        print("巡 %d を記録した(高 %d / 中 %d / 低 %d)" % tuple(args.add))
        return 0

    if args.type:
        ensure()
        d = read_types()
        d[args.type] = d.get(args.type, 0) + 1
        with io.open(RECUR, "w", encoding="utf-8", newline="\n") as fh:
            for k, v in sorted(d.items(), key=lambda x: -x[1]):
                fh.write("%s\t%d\n" % (k, v))
        n = d[args.type]
        print("型「%s」の出現: %d 回" % (args.type, n))
        if n == 2:
            print("★ 2回目。この型は原稿全体で洗うこと:")
            print("   python %s/scan_recurring.py --type %s" % (os.path.dirname(os.path.abspath(__file__)), args.type))
        return 0

    if args.types:
        d = read_types()
        if not d:
            print("型の記録がまだ無い")
            return 0
        print("型\t回数")
        for k, v in sorted(d.items(), key=lambda x: -x[1]):
            print("%-12s %d%s" % (k, v, "   ★全数照合の対象" if v >= 2 else ""))
        return 0

    rows = read_rounds()
    if not rows:
        print("記録がまだ無い(--add 巡 高 中 低 で足す)")
        return 0
    print("巡 |  高 |   中 |   低 |   計")
    print("---+-----+------+------+------")
    th = tm = tl = 0
    for r, h, m, l in rows:
        th += h; tm += m; tl += l
        print("%2d | %3d | %4d | %4d | %5d" % (r, h, m, l, h + m + l))
    print("---+-----+------+------+------")
    print("計 | %3d | %4d | %4d | %5d" % (th, tm, tl, th + tm + tl))

    highs = [h for _r, h, _m, _l in rows]
    if len(highs) >= 2 and max(highs[-2:]) <= 1:
        print("\n収束の目安を満たしている(「高」が2巡続けて0〜1件)。")
        print("残りが読み比べないと気づかない食い違いだけなら、止めてよい。")
    else:
        print("\nまだ収束していない(「高」が2巡続けて0〜1件になるまで回す)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
