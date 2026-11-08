"""和名の括弧書きを備考へ移し，j_name から外す．

    python scripts/move_paren.py <置き場> [--apply]

`マメヅタ (Ep)` のように和名の後ろに括弧で付いた語を備考へ移す．照合 (check_species.py) は括弧つきの和名を
対象にしないので，括弧を外してから照合する．

- `(Ep)`・`(EP)` は着生の意味なので，備考は「着生」．そのほかは括弧の中身をそのまま備考に残す
  (「和名の印字に括弧書き「…」があった」)．
- 対象は transcripts/Tab.*/body.tsv・once.tsv の j_name．全角・半角の括弧のどちらも拾う．
- 既定は件数と例だけを出す．`--apply` で書き，直す前の転記を `review_backup_<日時>_paren/` に写す．
- 直したあとは `to_csv.py` と `check_species.py` を流す．
"""
import argparse
import csv
import datetime
import glob
import io
import os
import re
import shutil
import sys

PAREN = re.compile(r'\s*[(（]([^()（）]+)[)）]\s*$')
EPI = {'ep', 'epi'}


def rd(p):
    raw = open(p, encoding='utf-8-sig', newline='').read()
    return list(csv.reader(io.StringIO(raw), delimiter='\t')), '\r\n' in raw


def wr(p, rows, crlf):
    with open(p, 'w', encoding='utf-8', newline='') as f:
        csv.writer(f, delimiter='\t', lineterminator='\r\n' if crlf else '\n').writerows(rows)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args(argv)
    bk = os.path.join(a.dir, 'review_backup_' + datetime.datetime.now().strftime('%Y%m%d_%H%M') + '_paren')
    total, shown = 0, 0
    for p in sorted(glob.glob(os.path.join(a.dir, 'transcripts', 'Tab.*', '*.tsv'))):
        base = os.path.basename(p)
        if base not in ('body.tsv', 'once.tsv'):
            continue
        rows, crlf = rd(p)
        h = rows[0]
        ji, ni = h.index('j_name'), h.index('note')
        n = 0
        for r in rows[1:]:
            if len(r) <= ji:
                continue
            m = PAREN.search(r[ji])
            if not m:
                continue
            word = m.group(1).strip()
            msg = '着生' if word.lower() in EPI else f'和名の印字に括弧書き「{word}」があった'
            if shown < 8:
                print(f'  {os.path.basename(os.path.dirname(p))} {r[ji]} → {r[ji][:m.start()]} / 備考: {msg}')
                shown += 1
            if len(r) <= ni:
                r += [''] * (ni + 1 - len(r))
            r[ni] = (r[ni] + ';' if r[ni] else '') + msg
            r[ji] = r[ji][:m.start()]
            n += 1
        if n and a.apply:
            d = os.path.join(bk, os.path.basename(os.path.dirname(p)))
            os.makedirs(d, exist_ok=True)
            shutil.copy2(p, os.path.join(d, base))
            wr(p, rows, crlf)
        total += n
    print(f'括弧書きのある行 {total}' + (f'．写し: {bk}' if a.apply and total else '．(書いていない: --apply で書く)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
