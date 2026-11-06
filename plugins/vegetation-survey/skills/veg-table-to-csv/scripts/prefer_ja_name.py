"""学名と和名の属が合わない行 (names.tsv の same_genus=0) と，属は同じで種が合わない行を，和名を優先して学名に直す．

    python scripts/prefer_ja_name.py <置き場> [--apply] [--skip 和名,和名] [--status ok,alias]

方針は利用者が選ぶ (和名を優先するか，印字のまま残すか)．和名を優先すると決まったときに使う．

- 直し先はチェックリストの学名 (names.tsv の `latin`)．既定は `--dry-run` 相当で，`--apply` を付けたときだけ書く．
- 転記 (transcripts/Tab.*/body.tsv・once.tsv) の，学名が `s_name` と一致する行のうち和名も一致するものを直す．
- 備考には「学名の印字は「X」．和名を優先し，チェックリストの学名に修正した」と残す (接頭辞なし = その行の全セル)．
- 直す前の転記を `review_backup_<日時>/` に写す．`--skip` の和名は直さない (階層や本文から和名のほうが誤りと
  判断できる行は，ここから外して手で直し，備考にその理由を書く)．
- 直したあとは `to_csv.py` と `check_species.py` を流す．
"""
import argparse
import csv
import datetime
import glob
import io
import os
import shutil
import sys


def rd(p):
    raw = open(p, encoding='utf-8-sig', newline='').read()
    return list(csv.reader(io.StringIO(raw), delimiter='\t')), '\r\n' in raw


def wr(p, rows, crlf):
    with open(p, 'w', encoding='utf-8', newline='') as f:
        csv.writer(f, delimiter='\t', lineterminator='\r\n' if crlf else '\n').writerows(rows)


def binomial(name):
    """属名と種小名 (先頭の 2 語) を小文字で．var.・f. などの下の階級と著者名は見ない"""
    return ' '.join(name.lower().split()[:2])


def targets(root, status, skip, genus_only=False):
    """直す行 {(学名, 和名): チェックリストの学名}．属が合わない行と，属は同じで種 (先頭の 2 語) が合わない行
    (0.5.13．2026-11-06 ユーザ指示．近畿 Tab.052 の Erigeron canadensis ヒメジョオン)．genus_only で属だけにする"""
    out = {}
    with open(os.path.join(root, 'names.tsv'), encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            s, latin = r['s_name'].strip(), (r['latin'] or '').strip()
            if not latin or r['status'] not in status or r['j_name'] in skip:
                continue
            other_species = r['same_genus'] == '1' and binomial(s) != binomial(latin)
            if r['same_genus'] == '0' or (other_species and not genus_only):
                out[(s, r['j_name'].strip())] = latin
    return out


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir')
    ap.add_argument('--apply', action='store_true', help='書き込む (無ければ件数だけ出す)')
    ap.add_argument('--skip', default='', help='直さない和名 (カンマ区切り)')
    ap.add_argument('--status', default='ok,alias', help='直す照合結果 (既定 ok,alias)')
    ap.add_argument('--genus-only', action='store_true',
                    help='属が合わない行だけを直す (0.5.12 までの動き．既定は種が合わない行も直す)')
    a = ap.parse_args(argv)
    tg = targets(a.dir, set(a.status.split(',')), {x for x in a.skip.split(',') if x}, a.genus_only)
    bk = os.path.join(a.dir, 'review_backup_' + datetime.datetime.now().strftime('%Y%m%d_%H%M') + '_name')
    total = 0
    for p in sorted(glob.glob(os.path.join(a.dir, 'transcripts', 'Tab.*', '*.tsv'))):
        base = os.path.basename(p)
        if base not in ('body.tsv', 'once.tsv'):
            continue
        rows, crlf = rd(p)
        h = rows[0]
        si, ji, ni = h.index('s_name'), h.index('j_name'), h.index('note')
        n = 0
        for r in rows[1:]:
            if len(r) <= max(si, ji):
                continue
            new = tg.get((r[si].strip(), r[ji].strip()))
            if not new:
                continue
            if len(r) <= ni:
                r += [''] * (ni + 1 - len(r))
            msg = f'学名の印字は「{r[si].strip()}」．和名を優先し，チェックリストの学名に修正した'
            r[ni] = (r[ni] + ';' if r[ni] else '') + msg
            r[si] = new
            n += 1
        if n and a.apply:
            d = os.path.join(bk, os.path.basename(os.path.dirname(p)))
            os.makedirs(d, exist_ok=True)
            shutil.copy2(p, os.path.join(d, base))
            wr(p, rows, crlf)
        total += n
    print(f'対象の (学名, 和名) {len(tg)} 組，直す行 {total}' + (f'．写し: {bk}' if a.apply and total else '．(書いていない: --apply で書く)'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
