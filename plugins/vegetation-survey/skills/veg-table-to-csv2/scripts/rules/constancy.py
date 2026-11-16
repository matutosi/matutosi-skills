"""常在度の書式の決まり"""
import re

from common import to_csv
from rules import Change, rule

COV = r'[54321+r]'
ORDER = {c: i for i, c in enumerate('r+12345')}
ROMAN5 = ['I', 'II', 'III', 'IV', 'V']
ROMAN10 = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
RANGE = re.compile(rf'^(?P<head>[^()]*)\(\s*(?P<a>{COV})\s*-\s*(?P<b>{COV})\s*\)(?P<q>\??)$')
ARABIC = re.compile(rf'^(?P<n>[1-5])(?P<rest>\(\s*{COV}(?:\s*-\s*{COV})?\s*\))(?P<q>\??)$')
TEN = re.compile(r'^(?P<r>X|IX|VIII|VII|VI|V|IV|III|II|I)(?P<rest>\(.*\))?(?P<q>\??)$')


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


@rule('D02', '常在度の範囲の逆順を並べ替える (III(+-r) → III(r-+))', '常在度の書式', old='X25')
def range_order(t, param):
    for row, p, v in body_cells(t):
        m = RANGE.match(v.translate(to_csv.FIX))
        if m and ORDER[m.group('a')] > ORDER[m.group('b')]:
            new = f"{m.group('head')}({m.group('b')}-{m.group('a')}){m.group('q')}"
            yield Change('body', row, p, new, '範囲が大きい印から小さい印の順．逆順とみて並べ替えた')


@rule('D03', '調査区数 5 以上の列の算用数字の常在度をローマ数字に直す (1(+) → I(+))', '常在度の書式', old='X8')
def arabic_to_roman(t, param):
    n = t.n_plots()
    keep = to_csv.arabic_major_columns(t.dicts('body'), n)     # 算用数字が多数の列は例外 (調査区数の印字を疑う)
    for row, p, v in body_cells(t):
        if n.get(p, 0) < 5 or p in keep:
            continue
        m = ARABIC.match(v.translate(to_csv.FIX))
        if m:
            new = ROMAN5[int(m.group('n')) - 1] + m.group('rest') + m.group('q')
            yield Change('body', row, p, new, f'調査区数 {n[p]} の列の算用数字．ローマ数字の誤植とみた')
    for d in t.dicts('once'):                               # 1 回出現も，本体と同じ列の条件で
        p = d.get('plot', '').strip()
        if n.get(p, 0) < 5 or p in keep:
            continue
        m = ARABIC.match((d.get('value') or '').strip().translate(to_csv.FIX))
        if m:
            new = ROMAN5[int(m.group('n')) - 1] + m.group('rest') + m.group('q')
            yield Change('once', d['_row'], '@value', new, f'調査区数 {n[p]} の列の算用数字．ローマ数字の誤植とみた')


@rule('D04', '10 階級の常在度 (VI-X が何度も出る列) を 5 階級に直す', '常在度の書式', old='X57')
def ten_classes(t, param):
    need = int(param) if str(param).strip().isdigit() else 2          # VI-X がこの数以上ある列だけ
    cells = {}
    for row, p, v in body_cells(t):
        m = TEN.match(v.translate(to_csv.FIX))
        if m:
            cells.setdefault(p, []).append((row, m))
    for p, items in cells.items():
        if sum(1 for _, m in items if ROMAN10.index(m.group('r')) >= 5) < need:
            continue
        for row, m in items:
            k = ROMAN10.index(m.group('r'))
            new = ROMAN5[k // 2] + (m.group('rest') or '') + m.group('q')
            if new != t.get('body', row, p).strip():
                yield Change('body', row, p, new, f"印字は {m.group('r')}．10 階級の列とみて 5 階級に直した")
