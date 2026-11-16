"""1 回出現の段落の決まり"""
import re

from common import to_csv
from rules import Change, rule

import check as old_check          # 今のスキルの check.py (種の数え方・見出しのずれの試し方を使う)

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


@rule('D11', '1 回出現の見出しのずれ: 1 地点ずらすと関わる地点の出現種数がすべて印字と合うときだけ移す', '1 回出現', old='X35')
def heading_shift(t, param):
    """1 つ移しては数え直し，次のずれを探す (今の手順と同じ)．前後どちらへずらしても合う (範囲の重なる 2 つの候補が出る)
    ときは，どちらとも決められないので移さない．同じ行は 2 回動かさない"""
    work = t.copy()
    moved = {}                                             # 行番号 -> (印字の地点, 理由)
    for _ in range(20):
        body, once, want = species_sets(work)
        if not once or len(want) < 2:
            break
        cands = old_check.heading_shifts(body, once, want)
        if len(cands) == 2 and not (cands[0][1] < cands[1][0] or cands[1][1] < cands[0][0]):
            break                                          # 前後どちらでも合う: 決めない (確認に出す対象)
        cands = [c for c in cands if not any(row['_row'] in moved and c[0] <= int(row['plot']) <= c[1]
                                             for row in work.dicts('once') if row.get('plot', '').strip().isdigit())]
        if not cands:
            break
        s, e, d, ok = max(cands, key=lambda c: (len(c[3]), -(c[1] - c[0])))
        for row in work.dicts('once'):
            p = row.get('plot', '').strip()
            if p.isdigit() and s <= int(p) <= e:
                moved[row['_row']] = (p, f'地点 {" ".join(map(str, ok))} の出現種数がすべて印字と合う')
                work.set('once', row['_row'], '@plot', str(int(p) + d))
    for row, (p, why) in sorted(moved.items()):
        new = work.get('once', row, '@plot')
        yield Change('once', row, '@plot', new, f'印字は in {p}．見出しのずれとみて地点 {new} へ移した ({why})')
