"""veg-table-to-csv2 の共通の部品: 転記の読み書き・セルの ID・今のスキル (veg-table-to-csv) の道具の場所．

転記 (transcripts/Tab.NNN/ の header・body・once・notes) は固定したら書き換えない．
セルには変わらない ID を付ける:

    <表のフォルダ名>/<h|b|o|n><行番号>/<列>

- 行番号は TSV のデータ行の番号 (見出しの次の行が 1)．
- 列は地点の番号 (`8`)，または行の項目 `@名前` (`@layer`・`@s_name`・`@value`・`@plot` など)．
- 例: `Tab.038/b64/8` (本体の 64 行目・地点 8)，`Tab.141/o65/@layer` (1 回出現の 65 行目の階層)．
"""
import copy
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OLD_SCRIPTS = os.path.normpath(os.path.join(HERE, '..', '..', 'veg-table-to-csv', 'scripts'))
if OLD_SCRIPTS not in sys.path:
    sys.path.insert(0, OLD_SCRIPTS)          # 読む道具と値の分解は今のスキルのものを使う (写しを作らない)

import to_csv  # noqa: E402

KINDS = {'header': 'h', 'body': 'b', 'once': 'o', 'notes': 'n'}
LETTER = {v: k for k, v in KINDS.items()}
CELL_ID = re.compile(r'^(?P<table>[^/]+)/(?P<letter>[hbon])(?P<row>\d+)/(?P<col>.+)$')
TAB = chr(9)
NL = chr(10)
CR = chr(13)


def read_tsv_raw(path):
    """(見出し, 行のリスト, 改行, 末尾の改行の有無)．行は文字列のリスト (見出しより短い行もある)"""
    with open(path, encoding='utf-8-sig', newline='') as f:
        raw = f.read()
    nl = CR + NL if (CR + NL) in raw else NL
    text = raw.replace(CR + NL, NL)
    trail = text.endswith(NL)
    lines = text.rstrip(NL).split(NL) if text.strip() else []
    if not lines:
        return [], [], nl, trail
    return lines[0].split(TAB), [l.split(TAB) for l in lines[1:]], nl, trail


def write_tsv_raw(path, head, rows, nl=NL, trail=True):
    text = nl.join([TAB.join(head)] + [TAB.join(r) for r in rows]) + (nl if trail else '')
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


class Table:
    """1 つの表の転記．cells は書き換えられるが，ファイルへは write_to (別の場所) でしか書かない"""

    def __init__(self, tdir):
        self.dir = tdir
        self.name = os.path.basename(os.path.normpath(tdir))
        self.head, self.rows, self.fmt = {}, {}, {}
        for kind in KINDS:
            p = os.path.join(tdir, kind + '.tsv')
            if os.path.exists(p):
                h, rows, nl, trail = read_tsv_raw(p)
            else:
                h, rows, nl, trail = [], [], NL, True
            self.head[kind], self.rows[kind], self.fmt[kind] = h, rows, (nl, trail)
        mh, mrows, _, _ = read_tsv_raw(os.path.join(tdir, 'meta.tsv')) if os.path.exists(os.path.join(tdir, 'meta.tsv')) else ([], [], NL, True)
        self.meta_head, self.meta_rows = mh, mrows
        self.meta = {r[0]: (r[1] if len(r) > 1 else '') for r in mrows if r}

    def copy(self):
        return copy.deepcopy(self)

    # ---- 列と行 ----
    def plots(self, kind):
        """地点の列の名前 (数字の見出し) を並びの順に"""
        return [h for h in self.head.get(kind, []) if h.strip().isdigit()]

    def col_index(self, kind, col):
        name = col[1:] if col.startswith('@') else col
        if name not in self.head[kind]:
            raise KeyError(f'{self.name} {kind}.tsv に列 {name} が無い')
        return self.head[kind].index(name)

    def get(self, kind, row, col):
        r = self.rows[kind][row - 1]
        k = self.col_index(kind, col)
        return r[k] if k < len(r) else ''

    def set(self, kind, row, col, value):
        r = self.rows[kind][row - 1]
        k = self.col_index(kind, col)
        while len(r) <= k:
            r.append('')
        r[k] = value

    def dicts(self, kind):
        """行を {列名: 値} のリストで (読むだけ．_row に行番号)"""
        h = self.head.get(kind, [])
        out = []
        for i, r in enumerate(self.rows.get(kind, []), 1):
            d = dict(zip(h, r + [''] * (len(h) - len(r))))
            d['_row'] = i
            out.append(d)
        return out

    def n_plots(self):
        """常在度の列の調査区数 {列: 数} (表頭の調査区数の行から)"""
        return to_csv.plots_per_column(self.dicts('header'))

    # ---- セルの ID ----
    def cid(self, kind, row, col):
        return f'{self.name}/{KINDS[kind]}{row}/{col}'

    def get_id(self, cell_id):
        kind, row, col = parse_id(cell_id)[1:]
        return self.get(kind, row, col)

    def set_id(self, cell_id, value):
        kind, row, col = parse_id(cell_id)[1:]
        self.set(kind, row, col, value)

    # ---- 書き出し (転記の置き場には書かない) ----
    def write_to(self, out_dir, note_token=False):
        """out_dir に 5 つのファイルを書く．note_token なら各行の note の末尾に行の印 `⟦b12⟧` を付ける
        (to_csv.py を通したあと，出力の行を転記の行に結び付けるため)"""
        os.makedirs(out_dir, exist_ok=True)
        write_tsv_raw(os.path.join(out_dir, 'meta.tsv'), self.meta_head, self.meta_rows)
        for kind, letter in KINDS.items():
            h = self.head[kind]
            if not h:
                continue
            rows = [list(r) for r in self.rows[kind]]
            if note_token:
                if 'note' not in h:                       # note の列が無い転記にも行の印を付ける (書き出す写しだけ)
                    h = h + ['note']
                k = h.index('note')
                for i, r in enumerate(rows, 1):
                    while len(r) <= k:
                        r.append('')
                    tok = f'{TOKEN_L}{letter}{i}{TOKEN_R}'
                    r[k] = (r[k] + '; ' + tok) if r[k].strip() else tok
            write_tsv_raw(os.path.join(out_dir, kind + '.tsv'), h, rows)


TOKEN_L, TOKEN_R = chr(0x27E6), chr(0x27E7)          # ⟦ ⟧ (転記の note には出ない字)
TOKEN = re.compile(r'[;\s]*' + TOKEN_L + r'([hbon])(\d+)' + TOKEN_R)


def parse_id(cell_id):
    """セルの ID を (表のフォルダ名, 種類, 行番号, 列) に分ける"""
    m = CELL_ID.match(cell_id.strip())
    if not m:
        raise ValueError(f'セルの ID の形でない: {cell_id}')
    return m.group('table'), LETTER[m.group('letter')], int(m.group('row')), m.group('col')


def table_dirs(root):
    """置き場の transcripts/ の表のフォルダ (名前の順)"""
    base = os.path.join(root, 'transcripts')
    if not os.path.isdir(base):
        sys.exit(f'転記表が無い: {base}')
    return [os.path.join(base, n) for n in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, n))]


def read_side(path, key='cell_id'):
    """readings.tsv・judgments.tsv など，セルの ID を鍵にした TSV を {ID: 行} で読む (無ければ {})．
    同じ ID が 2 回あれば後の行が勝つ"""
    if not os.path.exists(path):
        return {}
    h, rows, _, _ = read_tsv_raw(path)
    out = {}
    for r in rows:
        if not r or not r[0].strip() or r[0].startswith('#'):
            continue
        d = dict(zip(h, r + [''] * (len(h) - len(r))))
        out[d[key].strip()] = d
    return out
