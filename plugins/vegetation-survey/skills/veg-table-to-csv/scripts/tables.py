"""表ごとの進み具合を <置き場>/tables.tsv に記録する (途中から再開するため)．

    python scripts/tables.py init <置き場> --index index.tsv [--prefix kinki]   # 一覧から作る
    python scripts/tables.py add  <置き場> Tab.34 --page p010 --title 表題 [--kind small]
    python scripts/tables.py next <置き場> [-n 3]                              # 次に読む表
    python scripts/tables.py set  <置き場> Tab.34 done [--note メモ]
    python scripts/tables.py show <置き場>                                     # 件数と番号の抜け

状態は todo (未着手)・reading (読んでいる途中)・done (検算まで済み)・skip (読まない)．
index.tsv は 1 行 1 ページで，`file`・`tab_numbers` (`26;28`)・`titles` (`26:表題;28:表題`) の列を読む．
`status` 列があれば keep の行だけを使う．
"""
import argparse
import csv
import os
import re
import sys

COLS = ['table', 'page', 'title', 'kind', 'status', 'note']
STATES = ('todo', 'reading', 'done', 'skip')


def path_of(d):
    return os.path.join(d, 'tables.tsv')


def load(d):
    if not os.path.exists(path_of(d)):
        return []
    with open(path_of(d), encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def save(d, rows):
    os.makedirs(d, exist_ok=True)
    tmp = path_of(d) + '.tmp'                         # 途中で止まっても記録を壊さない
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter='\t', lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path_of(d))


def number(table):
    m = re.search(r'\d+', table)
    return int(m.group()) if m else 10 ** 6


def from_index(index, prefix=''):
    """index.tsv の 1 行 1 ページを，1 行 1 表にする．同じ表番号は最初のページを採る"""
    with open(index, encoding='utf-8-sig', newline='') as f:
        src = list(csv.DictReader(f, delimiter='\t'))
    rows, seen = [], set()
    for r in src:
        if r.get('status', 'keep') != 'keep' or not r['file'].startswith(prefix):
            continue
        titles = {}
        for part in re.split(r';(?=\d+:)', r.get('titles', '')):
            n, sep, t = part.partition(':')
            if sep:
                titles[n] = t
        page = os.path.splitext(r['file'])[0]
        for n in filter(None, r.get('tab_numbers', '').split(';')):
            key = (prefix or page.rsplit('_', 1)[0], n)
            if key in seen:
                continue
            seen.add(key)
            table = f'Tab.{n}' if prefix else f'{key[0]}_Tab.{n}'
            rows.append(dict(table=table, page=page, title=titles.get(n, ''), kind='',
                             status='todo', note=''))
    return rows


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init')
    p.add_argument('dir')
    p.add_argument('--index', required=True)
    p.add_argument('--prefix', default='', help='file がこの語で始まる行だけ (例: kinki)')
    p.add_argument('--force', action='store_true', help='今の記録を捨てて作り直す')
    p = sub.add_parser('add')
    p.add_argument('dir')
    p.add_argument('table')
    p.add_argument('--page', default='')
    p.add_argument('--title', default='')
    p.add_argument('--kind', default='', help='紙面の型 (fold・small・rotated など)')
    p = sub.add_parser('next')
    p.add_argument('dir')
    p.add_argument('-n', type=int, default=1)
    p = sub.add_parser('set')
    p.add_argument('dir')
    p.add_argument('table')
    p.add_argument('status', choices=STATES)
    p.add_argument('--note', default=None)
    p = sub.add_parser('show')
    p.add_argument('dir')
    a = ap.parse_args(argv)

    rows = load(a.dir)
    if a.cmd == 'init':
        if rows and not a.force:
            sys.exit(f'記録がすでにある ({len(rows)} 表)．作り直すなら --force')
        rows = from_index(a.index, a.prefix)
        save(a.dir, rows)
        print(f'{len(rows)} 表を {path_of(a.dir)} に書いた')
    elif a.cmd == 'add':
        if any(r['table'] == a.table for r in rows):
            sys.exit(f'{a.table} はすでにある')
        rows.append(dict(table=a.table, page=a.page, title=a.title, kind=a.kind,
                         status='todo', note=''))
        save(a.dir, rows)
    elif a.cmd == 'next':
        todo = [r for r in rows if r['status'] == 'reading'] + [r for r in rows if r['status'] == 'todo']
        for r in todo[:a.n]:
            print('\t'.join((r['table'], r['page'], r['status'], r['title'])))
        if not todo:
            print('残り 0 表')
    elif a.cmd == 'set':
        hit = [r for r in rows if r['table'] == a.table]
        if not hit:
            sys.exit(f'{a.table} が tables.tsv に無い')
        hit[0]['status'] = a.status
        if a.note is not None:
            hit[0]['note'] = a.note
        save(a.dir, rows)
    else:
        print('  '.join(f'{s} {sum(r["status"] == s for r in rows)}' for s in STATES))
        nums = sorted({number(r['table']) for r in rows} - {10 ** 6})
        gaps = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums)) if nums else []
        if gaps:                                      # 番号の抜けは読み落としの手がかり
            print('番号の抜け:', ' '.join(map(str, gaps)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
