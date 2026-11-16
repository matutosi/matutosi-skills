"""段 2: 書式をそろえる (常在度の書き方)"""
import re

from common import to_csv
from rules import Change, rule
from rules._lib import COV, ORDER, ROMAN10, ROMAN5, body_cells


RANGE = re.compile(rf'^(?P<head>[^()]*)\(\s*(?P<a>{COV})\s*-\s*(?P<b>{COV})\s*\)(?P<q>\??)$')


ARABIC = re.compile(rf'^(?P<n>[1-5])(?P<rest>\(\s*{COV}(?:\s*-\s*{COV})?\s*\))(?P<q>\??)$')


TEN = re.compile(r'^(?P<r>X|IX|VIII|VII|VI|V|IV|III|II|I)(?P<rest>\(.*\))?(?P<q>\??)$')


ROMAN_CELL = re.compile(rf'^(?P<r>V|IV|III|II|I)(?P<rest>\(\s*{COV}(?:\s*-\s*{COV})?\s*\))?(?P<q>\??)$')


ARABIC_ANY = re.compile(rf'^(?P<n>[1-9]\d*)(?P<rest>\(\s*{COV}(?:\s*-\s*{COV})?\s*\))?(?P<q>\??)$')


def arabic_columns(t):
    """算用数字 (出現地点数) で書く常在度の列: 調査区数 4 以下の列と，規則 D03 の例外の列 (算用数字が多数)"""
    n = t.n_plots()
    keep = to_csv.arabic_major_columns(t.dicts('body'), n)
    return {p: n[p] for p in n if 0 < n[p] < 5 or p in keep}


@rule('D02', '常在度の範囲の逆順を並べ替える (III(+-r) → III(r-+))', 2, old='X25')
def range_order(t, param):
    for row, p, v in body_cells(t):
        m = RANGE.match(v.translate(to_csv.FIX))
        if m and ORDER[m.group('a')] > ORDER[m.group('b')]:
            new = f"{m.group('head')}({m.group('b')}-{m.group('a')}){m.group('q')}"
            yield Change('body', row, p, new, '範囲が大きい印から小さい印の順．逆順とみて並べ替えた')


@rule('D03', '調査区数 5 以上の列の算用数字の常在度をローマ数字に直す (1(+) → I(+))', 2, old='X8')
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


@rule('D04', '10 階級の常在度 (VI-X が何度も出る列) を 5 階級に直す', 2, old='X57')
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


@rule('D12', '算用数字の常在度の列に混じるローマ数字を算用数字に直す (I(+) → 1(+))', 2, old='X8 (i)')
def roman_to_arabic(t, param):
    cols = arabic_columns(t)
    by_col = {}
    for row, p, v in body_cells(t):
        if p in cols:
            by_col.setdefault(p, []).append((row, v.translate(to_csv.FIX)))
    for p, items in by_col.items():
        roman = [(row, ROMAN_CELL.match(v)) for row, v in items if ROMAN_CELL.match(v)]
        arabic = [v for _, v in items if ARABIC_ANY.match(v)]
        if not roman or len(arabic) < 3 * len(roman):      # ローマ数字が少数のときだけ (列の種類の読み違いでない)
            continue
        for row, m in roman:
            k = ROMAN5.index(m.group('r')) + 1
            if k <= cols[p]:
                yield Change('body', row, p, f"{k}{m.group('rest') or ''}{m.group('q')}",
                             f'調査区数 {cols[p]} の算用数字の列に混じるローマ数字．算用数字に直した')


@rule('D14', '出現地点数が調査区数を超える常在度を調査区数に直す (調査区数 2 の列の 3 → 2)', 2, old='自動 (出現地点数 > 調査区数)')
def count_over_plots(t, param):
    cols = arabic_columns(t)
    for row, p, v in body_cells(t):
        if p not in cols:
            continue
        m = ARABIC_ANY.match(v.translate(to_csv.FIX))
        if m and int(m.group('n')) > cols[p]:
            yield Change('body', row, p, f"{cols[p]}{m.group('rest') or ''}{m.group('q')}",
                         f"出現地点数 {m.group('n')} が調査区数 {cols[p]} を超える．調査区数に直した")
