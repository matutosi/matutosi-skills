"""段 0: 列の種類を決める (調査区数の印字の無い常在度の列・調査区数 1 の地点の列)

ほかの規則と to_csv.py は，表頭の調査区数の行で常在度の列を見分ける (Table.n_plots)．
その行の印字が無い・1 と印字された列は見分けを誤るので，ここで列の調査区数を決め直す．
転記には行も値も足さない．Change(kind='n_plots', row=0, col=列, new=…) を返し，decide.py が列の調査区数として持つ．
new が '<5' は「5 未満の常在度の列 (算用数字の出現地点数)」，'5+' (N+) は「N 以上の常在度の列 (ローマ数字の常在度)」，
数はその調査区数，'' は「地点の列 (常在度の列ではない)」．
"""
import re

from common import to_csv
from rules import Change, rule
from rules._lib import COV, body_cells


ARABIC_CONST = re.compile(rf'^([1-9]\d*)(?:\s*\(\s*{COV}(?:\s*-\s*{COV})?\s*\))?\??$')


CONST_SHAPE = re.compile(rf'^(?:[1-9]\d*|V|IV|III|II|I)\s*\(\s*{COV}(?:\s*-\s*{COV})?\s*\)\??$|^(?:V|IV|III|II|I)\??$')


ROMAN_CONST = re.compile(rf'^(?:V|IV|III|II|I)(?:\s*\(\s*{COV}(?:\s*-\s*{COV})?\s*\))?\??$')


PAREN_NUM = re.compile(r'^\(\s*\d+(?:\.\d+)?\s*\)$')


STAR_VALUE = re.compile(r'^(\d+)\s*[*＊]$')


# 「* は調査区数」の注 (*調査区数・* 調査区数・* Zahl d. Aufnahmen 調査区数・* 付きの数は調査区数)
STAR_NOTE = re.compile(r'[*＊][^;；．。]{0,30}?(?:調査区数|Zahl\s*d\.?\s*Aufn)', re.I)


def summary_evidence(t):
    """常在度の列の印 {列: 根拠}．出現種数の値が括弧つき ((25)．平均出現種数の印字) か，平均出現種数の行に値がある列"""
    out = {}
    plots = t.plots('header')
    for d in t.dicts('header'):
        ja, de = d.get('item_ja', ''), d.get('item_de', '').lower()
        mean = ja.startswith('平均出現種数') or de.startswith('mittlere artenzahl')
        count = not mean and (ja.startswith('出現種数') or de.startswith('artenzahl'))
        for p in plots:
            v = (d.get(p) or '').strip()
            if count and PAREN_NUM.match(v):
                out.setdefault(p, f'出現種数の印字が括弧つき ({v})')
            elif mean and v and v not in ('-', '—'):
                out.setdefault(p, f'平均出現種数の行に値 ({v})')
    return out


def star_note(t):
    """表頭の行の note・注記・meta.tsv に「* は調査区数」の注があれば，その文 (無ければ '')"""
    texts = [d.get('note', '') for d in t.dicts('header')]
    texts += [' '.join(v for k, v in d.items() if k != '_row' and isinstance(v, str)) for d in t.dicts('notes')]
    texts += list(t.meta.values())
    for s in texts:
        m = STAR_NOTE.search(s or '')
        if m:
            return m.group(0)
    return ''


def star_counts(t):
    """表頭の値の `5*`・`16*` (* は調査区数の注) から {列: (調査区数, 行の項目名)}．
    注が無い表・同じ列に違う数があるときは出さない (2026-11-22 ユーザ決定．九州ページ内 Tab.030・031・037・063・065)"""
    if not star_note(t):
        return {}
    found = {}
    for d in t.dicts('header'):
        for p in t.plots('header'):
            m = STAR_VALUE.match((d.get(p) or '').strip())
            if m:
                found.setdefault(p, set()).add((int(m.group(1)), d.get('item_ja', '') or d.get('item_de', '')))
    out = {}
    for p, got in found.items():
        nums = {n for n, _ in got}
        if len(nums) == 1:
            out[p] = (nums.pop(), sorted(i for _, i in got)[0])
    return out


def column_values(t):
    """本体の {列: [値]} (値のあるセルだけ．字の乱れは to_csv の FIX でそろえる)"""
    out = {}
    for _, p, v in body_cells(t):
        out.setdefault(p, []).append(v.translate(to_csv.FIX).strip())
    return out


@rule('D41', '調査区数の印字が無い列を常在度の列とみる．(a) 表頭の値が `5*` の形で「* は調査区数」の注があれば，その数を調査区数に．'
             '(b) 出現種数が括弧つき (平均出現種数) か平均出現種数の行に値があり，本体の値の半分以上が算用数字の常在度 (3(2-3)・2) で'
             '最大 4 以下なら調査区数 5 未満，半分以上がローマ数字の常在度 (V・V(3-5)) なら調査区数 5 以上 (算用数字の最大がそれより大きければその数以上)', 0,
      old='(規則の番号なし．中部 Tab.021・044・054・関東 Tab.085・東北ページ内 Tab.086・九州ページ内 Tab.030・063．2026-11-20・22 ユーザ決定)')
def count_missing(t, param):
    """調査区数を補ったことは，その列のセルと「列の種類」の行の note_modify に出る (decide.py の mark_columns)"""
    n = t.n_plots()
    vals = column_values(t)
    stars = star_counts(t)
    evidence = summary_evidence(t)
    for p in t.plots('header'):
        if n.get(p, 0) > 0:
            continue
        if p in stars:
            k, item = stars[p]
            yield Change('n_plots', 0, p, str(k),
                         f'調査区数の印字なし．{item}の行の印字 {k}* と，* は調査区数という注から，調査区数 {k} とみた')
            continue
        if p not in evidence or not vals.get(p):
            continue
        why, v = evidence[p], vals[p]
        arabic = [int(m.group(1)) for m in (ARABIC_CONST.match(x) for x in v) if m]
        roman = sum(1 for x in v if ROMAN_CONST.match(x))
        if arabic and len(arabic) * 2 >= len(v) and max(arabic) <= 4:
            yield Change('n_plots', 0, p, '<5',
                         f'調査区数の印字なし．{why}，算用数字の常在度 {len(arabic)}/{len(v)} セル (最大 {max(arabic)})'
                         '．調査区数 5 未満の常在度の列とみた')
        elif roman and roman * 2 >= len(v):
            low = max([5] + arabic)
            yield Change('n_plots', 0, p, f'{low}+',
                         f'調査区数の印字なし．{why}，ローマ数字の常在度 {roman}/{len(v)} セル'
                         f'．調査区数 {low} 以上の常在度の列とみた')


SUB_SOC = re.compile(rf'^(?P<c>{COV})\s*\(\s*(?P<s>[1-5])\s*\)(?P<q>\??)$')     # 3(5): 群度が右下の小さい字 (3₅)
SUB_SOC_SURE = re.compile(r'^[2-5]\s*\(\s*[1-5]\s*\)\??$')                         # 調査区数 1 の列では常在度になりえない形


def subscript_columns(t):
    """調査区数が 1 と印字された列のうち，`3(5)` (群度が右下の小さい字) の形の値を書いた列．
    出現地点数は 1 を超えないので，`2(…)`〜`5(…)` が 1 つでもあれば，その列の `c(s)` は被度と群度とみる．
    ほかの常在度の形 (`2(+)`・`II`) が同じ列にあるときは決めない (屋久島ページ内 Tab.041 列 10 の 3(5)・2(+)・3(+))"""
    printed = to_csv.plots_per_column(t.dicts('header'))
    vals = column_values(t)
    out = set()
    for p, k in printed.items():
        v = vals.get(p, [])
        if (k == 1 and any(SUB_SOC_SURE.match(x) for x in v)
                and not any(CONST_SHAPE.match(x) and not SUB_SOC.match(x) for x in v)):
            out.add(p)
    return out


@rule('D42', '調査区数が 1 と印字された列は，本体の値のうち常在度の形 (2(+)・III・V(+-1)) が半分未満なら地点の列とみる．'
             '3(5) (群度が右下の小さい字) の形の値は常在度の形に数えない', 0,
      old='(規則の番号なし．中部 Tab.057・058・関東 Tab.070．2026-11-20・22 ユーザ決定)')
def count_one(t, param):
    """地点の列に紛れた常在度の形の値 (中部 Tab.058 列 12 の 3(+-1)) は，地点の列の値として読めずに check で残る．
    `3(5)` の形の列 (subscript_columns) は D45 が被度・群度 (3・5) に直す"""
    vals = column_values(t)
    sub = subscript_columns(t)
    for p, k in t.n_plots().items():
        if k != 1:
            continue
        v = vals.get(p, [])
        const = sum(1 for x in v if CONST_SHAPE.match(x) and not (p in sub and SUB_SOC.match(x)))
        if v and const * 2 >= len(v):
            continue
        yield Change('n_plots', 0, p, '', f'調査区数の印字は 1．常在度の形の値は {const}/{len(v)} セルなので，1 地点の列 (地点の列) とみた')
