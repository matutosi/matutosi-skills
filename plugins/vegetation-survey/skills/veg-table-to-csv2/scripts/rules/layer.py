"""階層の決まり"""
import re

from rules import Change, rule

TWO = re.compile(r'第\s*[12１２]|schicht\s*-?\s*[12]|B\s*[12]\b', re.I)


def tree_layers(t):
    """表頭の高木層の数: 0 (高木層の行が無い・全地点が - で高木層の無い表)・1 (高木層が 1 つ)・2 (第 1・第 2 に分かれる)"""
    rows = [d for d in t.dicts('header') if '高木' in d.get('item_ja', '') or 'baumschicht' in d.get('item_de', '').lower()]
    if not rows:
        return 0
    if any(TWO.search(d.get('item_ja', '') + ' ' + d.get('item_de', '')) for d in rows):
        return 2
    plots = t.plots('header')
    has_value = any((d.get(p) or '').strip() not in ('', '-', '—', '–') for d in rows for p in plots)
    return 1 if has_value else 0                          # 全地点が - の表は「高木層が 1 つ」とみない (九州 Tab.141)


@rule('D05', '表頭の高木層が 1 つだけの表の階層 B2 を B に直す', '階層', old='X24')
def single_tree_layer(t, param):
    if tree_layers(t) != 1:
        return
    for kind in ('body', 'once'):
        if 'layer' not in t.head[kind]:
            continue
        for d in t.dicts(kind):
            layers = [x.strip() for x in d.get('layer', '').split(';')]
            if 'B2' not in layers:
                continue
            new = ';'.join('B' if x == 'B2' else x for x in layers)
            yield Change(kind, d['_row'], '@layer', new, '表頭の高木層は 1 つ (B) だけ．B2 の印字を B に直した')
            note = d.get('note', '')
            if 'B2 に' in note:                              # 下線の対応の書き方 (B2 に下線) も合わせる
                yield Change(kind, d['_row'], '@note', note.replace('B2 に', 'B に'), '階層の直しに合わせた')


WOODY_LAYERS = {'B', 'B1', 'B2', 'T', 'T1', 'T2', 'S', 'S1', 'S2'}
_WOODY = {}


def woody_names(t):
    """木本と分かる種: 同じ置き場のどこかの表で，高木層・低木層 (B・B1・B2・S など) に出ている種の和名と学名 (先頭 2 語)．
    置き場ごとに 1 回だけ数える"""
    import os
    from common import Table, table_dirs
    root = os.path.dirname(os.path.dirname(os.path.abspath(t.dir)))
    if root not in _WOODY:
        names = set()
        for tdir in table_dirs(root):
            x = Table(tdir)
            for kind in ('body', 'once'):
                if 'layer' not in x.head[kind]:
                    continue
                s_prev = j_prev = ''
                for d in x.dicts(kind):
                    if d.get('kind') == 'group':
                        continue
                    s, j = d.get('s_name', '').strip(), d.get('j_name', '').strip()
                    if kind == 'body' and not s and not j:    # 階層ごとの続きの行は上の種
                        s, j = s_prev, j_prev
                    s_prev, j_prev = s, j
                    if set(d.get('layer', '').replace(' ', '').split(';')) & WOODY_LAYERS:
                        names.update(n for n in (j, ' '.join(s.lower().split()[:2])) if n)
        _WOODY[root] = names
    return _WOODY[root]


@rule('D16', '1 回出現で階層の印字が無い種は，木本と分かる種を除いて K 層にする (階層を書く表だけ)', '階層', old='X51')
def once_herb_layer(t, param):
    """1 回出現の半分以上の行に階層がある表に限る (階層を書かない表では当てない)．
    木本と分かる種 (同じ置き場のどこかで高木層・低木層に出ている種) は直さない．
    草本の一覧 (今のスキルの references/herb_species.tsv) にある種は，木本の判定より先に K とする
    (2026-11-16 ユーザ決定．はじめは草本の一覧にある種だけだった)"""
    from common import to_csv
    if 'layer' not in t.head['once']:
        return
    rows = [d for d in t.dicts('once') if d.get('s_name', '').strip() or d.get('j_name', '').strip()]
    with_layer = sum(1 for d in rows if d.get('layer', '').strip())
    if not rows or with_layer * 2 < len(rows):
        return
    woody = None
    for d in rows:
        if d.get('layer', '').strip():
            continue
        s, j = d.get('s_name', '').strip(), d.get('j_name', '').strip()
        if s in to_csv.HERBS:
            yield Change('once', d['_row'], '@layer', 'K', '階層の印字なし．草本なので K とした')
            continue
        if woody is None:
            woody = woody_names(t)
        if j in woody or ' '.join(s.lower().split()[:2]) in woody:
            continue                                        # 木本と分かる種は階層を補わない
        yield Change('once', d['_row'], '@layer', 'K', '階層の印字なし．木本と分かる種でないので K とした')
