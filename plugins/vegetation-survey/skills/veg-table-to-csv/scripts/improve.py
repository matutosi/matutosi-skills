"""実行中の気づきを <置き場>/improvements.tsv に貯め，スキルを直す案にする．

    python scripts/improve.py add  <置き場> --kind pattern --text 気づいた内容 [--where references/…]
    python scripts/improve.py scan <置き場>     # CSV から，規則で読めなかった型を拾って足す
    python scripts/improve.py list <置き場>     # 番号つきの案を出す (ユーザに示す形)
    python scripts/improve.py set  <置き場> 3 applied    # applied・rejected・open

kind は pattern (紙面・書き方の型)・rule (値の変換の規則)・step (手順)・
option (選ぶ項目)・script (スクリプトの不具合)．
**実データ (地名・表の中身) を text に書かない**．型だけを一般化して書く．
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter

COLS = ['no', 'kind', 'where', 'text', 'count', 'status']
KINDS = {'pattern': 'references/table-structure.md', 'rule': 'scripts/to_csv.py',
         'step': 'SKILL.md', 'option': 'SKILL.md', 'script': 'scripts/'}
STATES = ('open', 'applied', 'rejected')
SCAN_MIN = 2                                          # 2 回以上出た型だけを案にする


def path_of(d):
    return os.path.join(d, 'improvements.tsv')


def load(d):
    if not os.path.exists(path_of(d)):
        return []
    with open(path_of(d), encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def save(d, rows):
    os.makedirs(d, exist_ok=True)
    with open(path_of(d), 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter='\t', lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def add(rows, kind, text, where='', count=1):
    """同じ text があれば数を足す．無ければ新しい行にする"""
    for r in rows:
        if r['kind'] == kind and r['text'] == text:
            r['count'] = max(int(r['count']), count)
            return r
    no = max((int(r['no']) for r in rows), default=0) + 1
    r = dict(no=no, kind=kind, where=where or KINDS[kind], text=text, count=count, status='open')
    rows.append(r)
    return r


def shape(s):
    """実データを出さないよう，値を型にする (数字は 9，英字は a)"""
    return re.sub(r'[A-Za-z]', 'a', re.sub(r'\d', '9', s))


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def scan(d):
    """CSV の status=check の理由を数える．読めなかった値は型にして返す"""
    comp, sites = read_csv(os.path.join(d, 'composition.csv')), read_csv(os.path.join(d, 'sites.csv'))
    values, dates = Counter(), Counter()
    for r in comp:
        if '値として読めない' in r.get('note', ''):
            values[shape(r.get('value_raw', ''))] += 1
    for r in sites:
        if '日付として読めない' in r.get('note', ''):
            dates[shape(r.get('value_raw', r.get('value', '')))] += 1
    out = [('rule', f'値の型 `{k}` を分解できない', n) for k, n in values.items() if n >= SCAN_MIN]
    out += [('rule', f'日付の型 `{k}` を読めない', n) for k, n in dates.items() if n >= SCAN_MIN]
    return out


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('add')
    p.add_argument('dir')
    p.add_argument('--kind', required=True, choices=sorted(KINDS))
    p.add_argument('--text', required=True)
    p.add_argument('--where', default='')
    for name in ('scan', 'list'):
        sub.add_parser(name).add_argument('dir')
    p = sub.add_parser('set')
    p.add_argument('dir')
    p.add_argument('no', type=int)
    p.add_argument('status', choices=STATES)
    a = ap.parse_args(argv)

    rows = load(a.dir)
    if a.cmd == 'add':
        print('no', add(rows, a.kind, a.text, a.where)['no'])
        save(a.dir, rows)
    elif a.cmd == 'scan':
        found = scan(a.dir)
        for kind, text, n in found:
            add(rows, kind, text, count=n)
        save(a.dir, rows)
        print(f'拾った型 {len(found)} 件')
    elif a.cmd == 'set':
        hit = [r for r in rows if int(r['no']) == a.no]
        if not hit:
            sys.exit(f'{a.no} 番が無い')
        hit[0]['status'] = a.status
        save(a.dir, rows)
    else:
        opened = [r for r in rows if r['status'] == 'open']
        for r in opened:
            print(f"{r['no']}. [{r['kind']}] {r['text']} ({r['count']} 回) → {r['where']}")
        if not opened:
            print('直す案は 0 件')
    return 0


if __name__ == '__main__':
    sys.exit(main())
