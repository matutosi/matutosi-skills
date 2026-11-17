"""値のある地点だけを書いた転記 (疎な転記) を body.tsv に展開する．

    python scripts/sparse.py <疎な転記> <置き場>

地点が多く非出現の多い表は，全地点の `・` を書くより出力が大きく減る．書き方:

    #table Tab.6 10                         表の名前と地点の数
    g|和文の見出し|独文の見出し
    学名|和名|階層|1:+ 3:1・2               値のある地点だけ (地点:値)
    ||S|2:+                                 学名と和名が空なら，上の種の別の階層
    学名|和名|階層|*+ ・ 1・2 ・ …          * なら全地点を左から順に書く
    学名|和名|階層|2:"+ 2" 5:'1 2'          値に空白を含めるときは引用符 (" か ') で囲む (囲まないと 2 つの値になる．
                                            番号の無い値・範囲外や重複の番号は，黙って消さずに止めて知らせる)
    学名|和名|S;K|2:+ 4:1・2|4: 下線; 印字は S,K (K に下線)     5 列目は note
    # 帯 3 (y 5200-6400)                    #table 以外の # で始まる行はコメント (読み飛ばす)
"""
import os
import re
import sys


def table_dir(table):
    return re.sub(r'\d+', lambda m: '%03d' % int(m.group()), table)


TOKEN = re.compile(r'''\s*(?:(\d+):)?("[^"]*"|'[^']*'|\S+)''')


def tokens(vals, line=''):
    """値の列を (地点の番号か None, 値) に分ける．空白を含む値は引用符で囲む: `3:"+ 2"`・`'+ 2'`．
    引用符の外の空白で区切る (従来どおり)．`+ 2` のように引用符なしで空白を含めると 2 つの値になり，
    番号の無い `2` は値と読まず止めて知らせる (次の地点の値を黙って消さない)"""
    out, pos = [], 0
    vals = vals.strip()
    while pos < len(vals):
        m = TOKEN.match(vals, pos)
        if not m:
            break
        i, x = m.group(1), m.group(2)
        if i is None and re.fullmatch(r'\d+:', x):         # `3:` だけ (空の値)
            i, x = x[:-1], ''
        if len(x) >= 2 and x[0] == x[-1] and x[0] in '"\'':
            x = x[1:-1]
        out.append((int(i) if i else None, x))
        pos = m.end()
    return out


def expand(line, n):
    p = [x.strip() for x in line.split('|')]
    if p[0] == 'g':
        return ['group', p[1], p[2] if len(p) > 2 else '']
    cells = ['・'] * n
    vals = p[3]
    if vals.startswith('*'):
        cells = [x for _, x in tokens(vals[1:], line)]
        if len(cells) != n:
            sys.exit(f'値が {len(cells)} 個で，地点の数 {n} と合わない'
                     '(空白を含む値は "+ 2" のように引用符で囲む): ' + line)
    else:
        seen = set()
        for i, x in tokens(vals, line):
            if i is None:
                sys.exit(f'番号の無い値 {x!r} がある (`+ 2` のように空白を含む値は `3:"+ 2"` と引用符で囲む．'
                         f'囲まないと 2 つの値になり，番号の無い値は読めない): {line}')
            if not 1 <= i <= n:
                sys.exit(f'地点の番号 {i} が範囲 (1〜{n}) の外: {line}')
            if i in seen:
                sys.exit(f'地点 {i} の値が 2 回ある: {line}')
            seen.add(i)
            cells[i - 1] = x
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
