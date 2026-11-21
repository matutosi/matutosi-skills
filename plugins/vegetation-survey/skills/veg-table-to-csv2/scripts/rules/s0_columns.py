"""段 0: 列の種類を決める (調査区数の印字の無い常在度の列・調査区数 1 の地点の列)

ほかの規則と to_csv.py は，表頭の調査区数の行で常在度の列を見分ける (Table.n_plots)．
その行の印字が無い・1 と印字された列は見分けを誤るので，ここで列の調査区数を決め直す．
転記には行も値も足さない．Change(kind='n_plots', row=0, col=列, new=…) を返し，decide.py が列の調査区数として持つ．
new が '<5' は「5 未満の常在度の列 (算用数字の出現地点数)」，'' は「地点の列 (常在度の列ではない)」．
"""
import re

from common import to_csv
from rules import Change, rule
from rules._lib import COV, body_cells


ARABIC_CONST = re.compile(rf'^([1-9]\d*)(?:\s*\(\s*{COV}(?:\s*-\s*{COV})?\s*\))?\??$')


CONST_SHAPE = re.compile(rf'^(?:[1-9]\d*|V|IV|III|II|I)\s*\(\s*{COV}(?:\s*-\s*{COV})?\s*\)\??$|^(?:V|IV|III|II|I)\??$')


PAREN_NUM = re.compile(r'^\(\s*\d+(?:\.\d+)?\s*\)$')


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


def column_values(t):
    """本体の {列: [値]} (値のあるセルだけ．字の乱れは to_csv の FIX でそろえる)"""
    out = {}
    for _, p, v in body_cells(t):
        out.setdefault(p, []).append(v.translate(to_csv.FIX).strip())
    return out


@rule('D41', '調査区数の印字が無い列でも，出現種数が括弧つき (平均出現種数) か平均出現種数の行に値があり，'
             '本体の値の半分以上が算用数字の常在度 (3(2-3)・2) で最大 4 以下なら，常在度の列 (調査区数 5 未満) とみる', 0,
      old='(規則の番号なし．中部 Tab.021・044・054・関東 Tab.085・東北ページ内 Tab.086．2026-11-20 ユーザ決定 a)')
def count_missing(t, param):
    """ローマ数字の列は今でも to_csv.py が常在度の列とみるので当てない．最大が 5 以上の列は調査区数が決まらないので当てない"""
    n = t.n_plots()
    vals = column_values(t)
    for p, why in summary_evidence(t).items():
        if n.get(p, 0) > 0 or not vals.get(p):
            continue
        arabic = [int(m.group(1)) for m in (ARABIC_CONST.match(v) for v in vals[p]) if m]
        if not arabic or len(arabic) * 2 < len(vals[p]) or max(arabic) > 4:
            continue
        yield Change('n_plots', 0, p, '<5',
                     f'調査区数の印字なし．{why}，算用数字の常在度 {len(arabic)}/{len(vals[p])} セル (最大 {max(arabic)})'
                     '．調査区数 5 未満の常在度の列とみた')


@rule('D42', '調査区数が 1 と印字された列は，本体の値のうち常在度の形 (2(+)・III・V(+-1)) が半分未満なら地点の列とみる', 0,
      old='(規則の番号なし．中部 Tab.057・058・関東 Tab.070．2026-11-20 ユーザ決定 a)')
def count_one(t, param):
    """地点の列に紛れた常在度の形の値 (中部 Tab.058 列 12 の 3(+-1)) は，地点の列の値として読めずに check で残る"""
    vals = column_values(t)
    for p, k in t.n_plots().items():
        if k != 1:
            continue
        v = vals.get(p, [])
        const = sum(1 for x in v if CONST_SHAPE.match(x))
        if v and const * 2 >= len(v):
            continue
        yield Change('n_plots', 0, p, '', f'調査区数の印字は 1．常在度の形の値は {const}/{len(v)} セルなので，1 地点の列 (地点の列) とみた')
