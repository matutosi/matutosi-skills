"""値のある地点だけを書いた転記 (疎な転記) を body.tsv に展開する．

    python scripts/sparse.py <疎な転記> <置き場>

地点が多く非出現の多い表は，全地点の `・` を書くより出力が大きく減る．書き方:

    #table Tab.6 10                         表の名前と地点の数
    g|和文の見出し|独文の見出し
    学名|和名|階層|1:+ 3:1・2               値のある地点だけ (地点:値)
    ||S|2:+                                 学名と和名が空なら，上の種の別の階層
    学名|和名|階層|*+ ・ 1・2 ・ …          * なら全地点を左から順に書く
    学名|和名|S;K|2:+ 4:1・2|4: 下線; 印字は S,K (K に下線)     5 列目は note
    # 帯 3 (y 5200-6400)                    #table 以外の # で始まる行はコメント (読み飛ばす)
"""
import os
import re
import sys


def table_dir(table):
    return re.sub(r'\d+', lambda m: '%03d' % int(m.group()), table)


def expand(line, n):
    p = [x.strip() for x in line.split('|')]
    if p[0] == 'g':
        return ['group', p[1], p[2] if len(p) > 2 else '']
    cells = ['・'] * n
    vals = p[3]
    if vals.startswith('*'):
        cells = vals[1:].split()
        if len(cells) != n:
            sys.exit(f'値が {len(cells)} 個で，地点の数 {n} と合わない: {line}')
    else:
        for tok in vals.split():
            i, _, x = tok.partition(':')
            cells[int(i) - 1] = x
    return ['sp', '', '', p[0], p[1], p[2]] + cells + [p[4] if len(p) > 4 else '']


def write(root, table, n, rows):
    top = root if os.path.basename(os.path.normpath(root)) == 'transcripts' else os.path.join(root, 'transcripts')
    d = os.path.join(top, table_dir(table))
    os.makedirs(d, exist_ok=True)
    head = ['kind', 'group_ja', 'group_de', 's_name', 'j_name', 'layer']
    head += [str(i) for i in range(1, n + 1)] + ['note']
    with open(os.path.join(d, 'body.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for r in [head] + rows:
            f.write('\t'.join(r) + '\n')


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    argv = sys.argv[1:] if argv is None else argv
    table, n, rows = None, 0, []
    with open(argv[0], encoding='utf-8-sig') as f:
        for line in f:
            line = line.rstrip('\r\n')
            if not line.strip():
                continue
            if line.startswith('#table'):
                if table:
                    write(argv[1], table, n, rows)
                _, table, n = line.split()
                n, rows = int(n), []
            elif line.lstrip().startswith('#'):        # #table 以外の # で始まる行はコメント
                continue
            else:
                rows.append(expand(line, n))
    if table:
        write(argv[1], table, n, rows)


if __name__ == '__main__':
    main()
