#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI の推敲指摘と、人の朱書きを突き合わせて、拾えた/見逃した/空振りを数える。

推敲ループは指摘の「件数」を追っているが、その指摘が**当たっていたか**は測っていない。
一方 apply-proof-marks が扱う朱書きは、ユーザ自身が下した評価の記録そのもの。
同じ章について両者を突き合わせれば、レビューの見逃しと空振りが分かる。

使い方:
  python calibrate.py --ai fixes_r3.json --human marks_fixes.json --baseline .
  python calibrate.py --ai fixes_r3.json --human marks_fixes.json --tsv _polish/calibration.tsv

入力はどちらも apply_fixes.py に渡す JSON。キー名は両スキルで違うが、両方受ける。
  polish-loop      : [{"file": ..., "before": ..., "after": ...}, ...]
  apply-proof-marks: [{"file": ..., "old": ...,    "new": ...},   ...]

突き合わせの考え方:
  - 各指摘の対象文字列を **baseline の原稿の中で探し**、文字位置 [start, end) を得る。
  - AI と人の区間が**重なれば同じ箇所**とみなす(--slack で近接も許す)。
  - baseline に無い / 複数回現れる文字列は「照合不能」にして、当たり外れに数えない。
    (apply_fixes.py が「ちょうど1回現れるものだけ当てる」のと同じ考え方)

baseline は「**両者が見ていた時点の原稿**」を指す。朱書きは古いビルドのことが多く、
AI の指摘はその巡の開始時点なので、ここがずれると照合不能ばかりになる。
過去分で測るなら、朱書きを反映する**直前のコミット**を worktree に出して指す。
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def load_fixes(path):
    """polish-loop 形式(before/after)と apply-proof-marks 形式(old/new)の両方を読む。"""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for i, r in enumerate(rows):
        target = r.get("before", r.get("old"))
        if target is None:
            raise SystemExit(f"{path} の {i} 件目に before も old も無い")
        out.append({
            "no": i + 1,
            "file": r["file"],
            "target": target,
            "why": r.get("why", ""),
        })
    return out


def locate(fixes, baseline):
    """対象文字列を baseline の原稿から探して [start, end) を付ける。"""
    cache = {}
    located, unmatched = [], []
    for fx in fixes:
        p = Path(baseline) / fx["file"]
        if p not in cache:
            cache[p] = p.read_text(encoding="utf-8") if p.exists() else None
        text = cache[p]
        if text is None:
            fx["reason"] = "ファイルが baseline に無い"
            unmatched.append(fx)
            continue
        n = text.count(fx["target"])
        if n != 1:
            fx["reason"] = "baseline に 0 回" if n == 0 else f"baseline に {n} 回"
            unmatched.append(fx)
            continue
        fx["start"] = text.index(fx["target"])
        fx["end"] = fx["start"] + len(fx["target"])
        located.append(fx)
    return located, unmatched


def overlaps(a, b, slack):
    return (a["file"] == b["file"]
            and a["start"] - slack < b["end"]
            and b["start"] - slack < a["end"])


def match(ai, human, slack):
    """人の朱書きを基準に、AI が拾えたか(hit)・見逃したか(miss)を分ける。"""
    hits, misses = [], []
    used = set()
    for h in human:
        found = [a for a in ai if overlaps(a, h, slack)]
        if found:
            for a in found:
                used.add(a["no"])
            hits.append((h, found))
        else:
            misses.append(h)
    false_alarms = [a for a in ai if a["no"] not in used]
    return hits, misses, false_alarms


def pct(num, den):
    return "—" if den == 0 else f"{num / den * 100:.0f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", required=True, action="append",
                    help="推敲ループの fixes.json。複数の巡をまとめるなら繰り返す")
    ap.add_argument("--human", required=True, help="朱書きから起こした fixes.json")
    ap.add_argument("--baseline", default=".", help="両者が見ていた時点の原稿があるディレクトリ")
    ap.add_argument("--slack", type=int, default=0,
                    help="この文字数だけ離れていても同じ箇所とみなす(既定 0 = 重なりのみ)")
    ap.add_argument("--tsv", help="明細の書き出し先(既定 _polish/calibration.tsv)")
    args = ap.parse_args()

    ai_raw = []
    for path in args.ai:
        ai_raw.extend(load_fixes(path))
    for i, fx in enumerate(ai_raw):
        fx["no"] = i + 1
    human_raw = load_fixes(args.human)

    ai, ai_bad = locate(ai_raw, args.baseline)
    human, human_bad = locate(human_raw, args.baseline)
    hits, misses, false_alarms = match(ai, human, args.slack)

    n_hit, n_miss, n_fa = len(hits), len(misses), len(false_alarms)
    print(f"baseline: {Path(args.baseline).resolve()}")
    print(f"AI の指摘 : {len(ai_raw)} 件 (照合できた {len(ai)} / 不能 {len(ai_bad)})")
    print(f"朱書き    : {len(human_raw)} 件 (照合できた {len(human)} / 不能 {len(human_bad)})")
    print()
    print(f"拾えた   : {n_hit}")
    print(f"見逃し   : {n_miss}    ← レビューの観点に足すもの")
    print(f"空振り   : {n_fa}    ← 観点から外すか、除外リストに回すもの")
    print()
    print(f"拾えた割合 (拾えた / 朱書き)     : {pct(n_hit, n_hit + n_miss)}")
    print(f"当たった割合 (拾えた / AI の指摘) : {pct(n_hit, n_hit + n_fa)}")

    if ai_bad or human_bad:
        print()
        print("照合不能(baseline がずれている可能性がある):")
        for fx in (ai_bad + human_bad)[:10]:
            print(f"  {fx['file']}\t{fx['reason']}\t{fx['target'][:40]}")
        if len(ai_bad) + len(human_bad) > 10:
            print(f"  ... 他 {len(ai_bad) + len(human_bad) - 10} 件")

    out = Path(args.tsv) if args.tsv else Path("_polish/calibration.tsv")
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["分類\tfile\t位置\t対象\t備考"]
    for h, found in hits:
        lines.append(f"拾えた\t{h['file']}\t{h['start']}\t{h['target'][:60]}\t"
                     f"AI {len(found)} 件が同じ箇所")
    for h in misses:
        lines.append(f"見逃し\t{h['file']}\t{h['start']}\t{h['target'][:60]}\t")
    for a in false_alarms:
        lines.append(f"空振り\t{a['file']}\t{a['start']}\t{a['target'][:60]}\t{a['why'][:60]}")
    for fx in ai_bad + human_bad:
        lines.append(f"照合不能\t{fx['file']}\t-\t{fx['target'][:60]}\t{fx['reason']}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print(f"明細: {out}")


if __name__ == "__main__":
    main()
