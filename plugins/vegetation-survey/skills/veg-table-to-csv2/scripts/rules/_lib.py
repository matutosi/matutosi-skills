"""規則の共通の部品 (定数・セルの読み出し・注記・種の数え方・対応の表の読み込み)"""
import os
import re

from common import read_tsv_raw, to_csv

import check as old_check          # 今のスキルの check.py (種の数え方を使う)


COV = r'[54321+r]'


ORDER = {c: i for i, c in enumerate('r+12345')}


ROMAN5 = ['I', 'II', 'III', 'IV', 'V']


ROMAN10 = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']


def body_cells(t):
    """本体の (行番号, 列, 値) を，値のあるセルだけ"""
    plots = t.plots('body')
    for d in t.dicts('body'):
        if d.get('kind') == 'group':
            continue
        for p in plots:
            v = (d.get(p) or '').strip()
            if v and v not in to_csv.ABSENT:
                yield d['_row'], p, v


DASHES = {'-', '—', '–', '−', '―'}


def is_pref_row(d):
    return '県名' in d.get('item_ja', '') or 'präf' in d.get('item_de', '').lower()


def is_height_row(d):
    ja, de = d.get('item_ja', ''), d.get('item_de', '').lower()
    return '高さ' in ja or '植生高' in ja or '群落高' in ja or de.startswith('höhe d.')


YEAR_HEAD = re.compile(r"^('?)(\d{2}|\d{4})(?=\s|$)")


YEAR4 = re.compile(r'(?:19|20)\d\d')


def plot_notes(t, item):
    """注記の {地点: [値と印字をつないだ文]}．item は item_ja の頭 (調査地・出典)．
    地点が空欄の注記は全地点に共通 (to_csv.py と同じ扱い．2026-11-17 に直した．それまでは拾っていなかった)．
    meta.tsv の drop_plots の地点は出さない"""
    out = {}
    drop = set(to_csv.plot_list(t.meta.get('drop_plots', '').replace(' ', ''))) if t.meta.get('drop_plots', '').strip() else set()
    every = [p for p in t.plots('header') if p not in drop]
    for d in t.dicts('notes'):
        if not d.get('item_ja', '').startswith(item):
            continue
        text = d.get('value', '') + ' ' + d.get('value_raw', '')
        spec = d.get('plot', '').replace(' ', '')
        for p in (to_csv.plot_list(spec) if spec else every):
            if p not in drop:
                out.setdefault(p, []).append(text)
    return out


def drop_plots(t):
    """meta.tsv の drop_plots の地点の集合"""
    spec = t.meta.get('drop_plots', '').replace(' ', '')
    return set(to_csv.plot_list(spec)) if spec else set()


NO_MOSS = re.compile(r'ohne\s+Moos|蘚苔類を除く|コケを除く', re.I)


def species_sets(t):
    """(本体の {地点: 種の集合}, 1 回出現の {地点: 種の集合}, 印字の {地点: 出現種数})．地点は int．
    種の数え方は今の check.py と同じ (学名を鍵に．出現種数の項目名に「蘚苔類を除く」とある表は蘚苔類・地衣類を外す)"""
    want, no_moss = {}, False
    for d in t.dicts('header'):
        if d.get('item_ja', '').startswith('出現種数') or 'artenzahl' in d.get('item_de', '').lower():
            no_moss = bool(NO_MOSS.search(d.get('item_ja', '') + ' ' + d.get('item_de', '')))
            for p in t.plots('header'):
                v = (d.get(p) or '').strip().rstrip('?')
                if v.isdigit():
                    want[int(p)] = want.get(int(p), 0) + int(v)
    body, once = {}, {}
    g_ja = g_de = s_prev = j_prev = ''
    plots = t.plots('body')
    for d in t.dicts('body'):
        if d.get('kind') == 'group':
            g_ja, g_de = d.get('group_ja', ''), d.get('group_de', '')
            continue
        s, j = d.get('s_name', '').strip(), d.get('j_name', '').strip()
        if not s and not j:
            s, j = s_prev, j_prev
        s_prev, j_prev = s, j
        r = dict(s_name=s, j_name=j, layer=d.get('layer', ''), group_ja=g_ja, group_de=g_de, note=d.get('note', ''))
        if no_moss and old_check.is_moss(r):
            continue
        for p in plots:
            v = (d.get(p) or '').strip().rstrip('?').strip()
            if v and v not in to_csv.ABSENT:
                body.setdefault(int(p), set()).add(old_check.spkey(r))
    for d in t.dicts('once'):
        p = d.get('plot', '').strip()
        s, j = d.get('s_name', '').strip(), d.get('j_name', '').strip()
        if not p.isdigit() or not (s or j):               # 名前の無い値 (規則 X53) は種に数えない
            continue
        r = dict(s_name=s, j_name=j, layer=d.get('layer', ''), group_ja=d.get('group', ''), group_de='', note=d.get('note', ''))
        if no_moss and old_check.is_moss(r):
            continue
        once.setdefault(int(p), set()).add(old_check.spkey(r))
    return body, once, want


_TABLES = {}


def _load(t, name):
    """置き場と 1 つ上のフォルダの対応の表を重ねて読む (置き場のものが勝つ)．[{列: 値}]"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(t.dir)))
    key = (root, name)
    if key not in _TABLES:
        rows = []
        for p in (os.path.join(os.path.dirname(root), name), os.path.join(root, name)):
            if os.path.exists(p):
                h, body, _, _ = read_tsv_raw(p)
                rows += [dict(zip(h, r + [''] * (len(h) - len(r)))) for r in body if r and r[0] and not r[0].startswith('#')]
        _TABLES[key] = rows
    return _TABLES[key]


LAYER_NAMES = [('B1', ('高木第1層', '高木第一層', '高木層1')), ('B2', ('高木第2層', '高木第二層', '高木層2')),
               ('S1', ('低木第1層', '第1低木層', '低木第一層')), ('S2', ('低木第2層', '第2低木層', '低木第二層')),
               ('K1', ('草本第1層', '第1草本層', '草本第一層')), ('K2', ('草本第2層', '第2草本層', '草本第二層')),
               ('B', ('高木層',)), ('S', ('低木層',)), ('K', ('草本層',)), ('M', ('蘚苔層', 'コケ層'))]


def header_layers(t):
    """表頭の項目名 (高さ・植被率の行) に出てくる階層の記号の集合．「高木第1層」は B1，「高木層」だけなら B"""
    out = set()
    for d in t.dicts('header'):
        ja = d.get('item_ja', '').replace(' ', '')
        for sym, names in LAYER_NAMES:
            if any(ja.startswith(n) for n in names):
                out.add(sym)
                break
    return out
