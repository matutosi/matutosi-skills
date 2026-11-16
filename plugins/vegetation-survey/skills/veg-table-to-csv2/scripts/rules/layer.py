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


@rule('D16', '1 回出現で階層の印字が無い草本は K 層にする (ほかの行に階層がある表だけ)', '階層', old='X51')
def once_herb_layer(t, param):
    """学名が草本の一覧 (今のスキルの references/herb_species.tsv) にある種だけ．1 回出現の半分以上の行に階層がある表に限る
    (階層を書かない表では当てない)．和名優先 (D10) のあとで当てるので，学名はチェックリストの名で引ける"""
    from common import to_csv
    if 'layer' not in t.head['once']:
        return
    rows = [d for d in t.dicts('once') if d.get('s_name', '').strip() or d.get('j_name', '').strip()]
    with_layer = sum(1 for d in rows if d.get('layer', '').strip())
    if not rows or with_layer * 2 < len(rows):
        return
    for d in rows:
        if not d.get('layer', '').strip() and d.get('s_name', '').strip() in to_csv.HERBS:
            yield Change('once', d['_row'], '@layer', 'K', '階層の印字なし．草本なので K とした')
