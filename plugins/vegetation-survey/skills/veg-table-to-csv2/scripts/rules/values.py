"""組成の値の決まり (字の乱れ・中黒の落ち)"""
import re

from common import to_csv
from rules import Change, rule

NO_DOT = re.compile(r'^(?P<c>[1-5+r])\s+(?P<s>[1-5])(?P<q>\??)$')


@rule('D20', '地点の列の「被度 空白 群度」は中黒の落ちとみて「被度・群度」に直す (1 2 → 1・2．常在度の列は除く)', '値の解釈',
      old='(規則の番号なし．中黒の落ち)')
def missing_dot(t, param):
    n = t.n_plots()
    plots = t.plots('body')
    for d in t.dicts('body'):
        if d.get('kind') == 'group':
            continue
        for p in plots:
            if n.get(p, 0) > 0:                             # 常在度の列の「2 3」は別の意味がありうる
                continue
            m = NO_DOT.match((d.get(p) or '').strip().translate(to_csv.FIX))
            if m:
                yield Change('body', d['_row'], p, f"{m.group('c')}・{m.group('s')}{m.group('q')}", '中黒の落ちとみて補った')
    for d in t.dicts('once'):
        if n.get(d.get('plot', '').strip(), 0) > 0:
            continue
        m = NO_DOT.match((d.get('value') or '').strip().translate(to_csv.FIX))
        if m:
            yield Change('once', d['_row'], '@value', f"{m.group('c')}・{m.group('s')}{m.group('q')}", '中黒の落ちとみて補った')


@rule('D21', '組成の値の「÷」は「+」の印字の乱れとみて「+」に直す', '値の解釈', old='(規則の番号なし．字の乱れ)')
def divide_sign(t, param):
    plots = t.plots('body')
    for d in t.dicts('body'):
        if d.get('kind') == 'group':
            continue
        for p in plots:
            v = d.get(p) or ''
            if '÷' in v:
                yield Change('body', d['_row'], p, v.replace('÷', '+'), '÷ は + の印字の乱れとみた')
    for d in t.dicts('once'):
        v = d.get('value') or ''
        if '÷' in v:
            yield Change('once', d['_row'], '@value', v.replace('÷', '+'), '÷ は + の印字の乱れとみた')
