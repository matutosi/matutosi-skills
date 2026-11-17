"""段 1: 字の乱れを整える (値の意味は変えない．ほかの規則が値を読む前に当てる)"""
import re

from common import to_csv
from rules import Change, rule
from rules._lib import COV, DASHES, ORDER, body_cells, header_layers, is_height_row


NO_DOT = re.compile(r'^(?P<c>[1-5+r])\s*(?P<s>[1-5])(?P<q>\??)$')     # 1 2 と，空白の無い 12・+2 (2026-11-17 ユーザ決定 3a)


COLON = re.compile(r'^(\d+)\s*[:：]\s*(\d+)$')


OPEN_PAREN = re.compile(rf'^(?P<head>(?:V|IV|III|II|I|[1-9]\d*|[+r]))\((?P<a>{COV})(?:\s*-\s*(?P<b>{COV}))?(?P<q>\??)$')


NO_DASH = re.compile(rf'^(?P<head>(?:V|IV|III|II|I|[1-9]\d*|[+r]))\((?P<a>{COV})\s+(?P<b>{COV})\)(?P<q>\??)$')


@rule('D13', '常在度の範囲の閉じ括弧の欠け・- の欠けを補う (I(+ → I(+)・III(+ 1) → III(+-1))', 1, old='X8 (ii)')
def range_marks(t, param):
    for row, p, v in body_cells(t):
        s = v.translate(to_csv.FIX)
        m = OPEN_PAREN.match(s)
        if m:
            rng = m.group('a') + ('-' + m.group('b') if m.group('b') else '')
            yield Change('body', row, p, f"{m.group('head')}({rng}){m.group('q')}", '閉じ括弧の欠けを補った')
            continue
        m = NO_DASH.match(s)
        if m and ORDER[m.group('a')] < ORDER[m.group('b')]:
            yield Change('body', row, p, f"{m.group('head')}({m.group('a')}-{m.group('b')}){m.group('q')}", '範囲の - の欠けを補った')


@rule('D18', '表頭の横棒の重なり (- -) を - にする (日付・調査番号の行は除く)', 1, old='(規則の番号なし)')
def dashes(t, param):
    plots = t.plots('header')
    for d in t.dicts('header'):
        key = d.get('item_ja', '') + ' ' + d.get('item_de', '').lower()
        if '年月日' in key or '月日' in key or 'datum' in key:      # 日付の - - - は年・月・日の 3 つの欄
            continue
        if '調査番号' in key or 'feld' in key or 'nr. d. aufn' in key:   # 調査番号の - - は記号と番号の 2 つの欄
            continue
        for p in plots:
            parts = (d.get(p) or '').split()
            if len(parts) >= 2 and all(x in DASHES for x in parts):
                yield Change('header', d['_row'], p, '-', f'印字は {" ".join(parts)} (横棒が {len(parts)} つ)．- とした')


@rule('D20', '地点の列の「被度 空白 群度」「被度群度」は中黒の落ちとみて「被度・群度」に直す (1 2・12・+2 → 1・2．常在度の列は除く)', 1,
      old='(規則の番号なし．中黒の落ち．2026-11-04 の聞かずに直す印字の誤り)')
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


@rule('D21', '組成の値の「÷」は「+」の印字の乱れとみて「+」に直す', 1, old='(規則の番号なし．字の乱れ)')
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


@rule('D22', '高さの行の「数字:数字」は小数点の印字の乱れとみて「数字.数字」に直す (0:2 → 0.2)', 1,
      old='(規則の番号なし．小数点の乱れ)')
def colon_point(t, param):
    plots = t.plots('header')
    for d in t.dicts('header'):
        if not is_height_row(d):
            continue
        for p in plots:
            m = COLON.match((d.get(p) or '').strip())
            if m:
                yield Change('header', d['_row'], p, f'{m.group(1)}.{m.group(2)}', '小数点が縦に 2 つ見える印字の乱れとみた')


@rule('D23', '表頭の値の末尾の「*」(脚注の印) を外す (Y* → Y)', 1, old='(規則の番号なし．脚注の印)')
def footnote_mark(t, param):
    plots = t.plots('header')
    for d in t.dicts('header'):
        for p in plots:
            v = (d.get(p) or '').strip()
            core = v.rstrip('*＊').rstrip()
            if core and core != v:
                yield Change('header', d['_row'], p, core, f'印字は {v}．末尾の * は脚注の印とみて外した')


LOWER = {'k': 'K', 's': 'S', 'b': 'B', 'b1': 'B1', 'b2': 'B2', 's1': 'S1', 's2': 'S2', 'k1': 'K1', 'k2': 'K2'}


@rule('D27', '階層の小文字 k は K に直す．s・b などは表頭にその大文字の層があるときだけ大文字に直す', 1, old='X43')
def lower_layer(t, param):
    have = header_layers(t)
    for kind in ('body', 'once'):
        if 'layer' not in t.head[kind]:
            continue
        for d in t.dicts(kind):
            layers = [x.strip() for x in d.get('layer', '').split(';')]
            new = []
            for x in layers:
                up = LOWER.get(x)
                new.append(up if up and (x == 'k' or up in have) else x)
            if new != layers:
                yield Change(kind, d['_row'], '@layer', ';'.join(new),
                             f"階層の印字は {','.join(layers)}．小文字は大文字の字形の誤植とみた")


# 項目名の書き方の揺れ (意味は同じ．2026-11-17 ユーザ決定 2a)
ITEM_FORM = [(re.compile(r'拔'), lambda m: '抜'),                    # 字の置き換えを先に (後の「の」の決まりが当たるように)
             (re.compile(r'蘇苔|コケ層'), lambda m: '蘚苔' if m.group(0) == '蘇苔' else '蘚苔層'),
             (re.compile(r'第\s*([0-9０-９一二])\s*層'), lambda m: '第' + {'一': '1', '二': '2', '１': '1', '２': '2'}.get(m.group(1), m.group(1)) + '層'),
             (re.compile(r'([木本]層|第[12]層|苔層)植被率'), lambda m: m.group(1) + 'の植被率'),
             (re.compile(r'(\S)\('), lambda m: m.group(1) + ' (')]


def item_form(name):
    """項目名の書き方をそろえる (高木第 1 層 → 高木第1層・低木層植被率 → 低木層の植被率・調査地(県名) → 調査地 (県名))"""
    s = name.strip()
    for pat, fn in ITEM_FORM:
        s = pat.sub(fn, s)
    return s


@rule('D32', '表頭・注記の項目名をそろえる (書き方の揺れと，対応表 item_names.tsv の別名 → 決まった名)', 1,
      old='(規則の番号なし．2026-11-17 ユーザ決定)')
def item_names(t, param):
    """対応表 item_names.tsv (列: alias name) は置き場と 1 つ上のフォルダのものを重ねる．
    同じ表にもう決まった名の行があるときは，別名の行を直さない (別の行の取り違えを避ける．群落記号と群落区分が別の行の表がある)"""
    from rules._lib import _load
    alias = {item_form(r['alias']): item_form(r['name']) for r in _load(t, 'item_names.tsv') if r.get('alias') and r.get('name')}
    for kind in ('header', 'notes'):
        if 'item_ja' not in t.head[kind]:
            continue
        rows = t.dicts(kind)
        have = {item_form(d.get('item_ja', '')) for d in rows}
        for d in rows:
            raw = d.get('item_ja', '')
            new = item_form(raw)
            why = '書き方をそろえた'
            if new in alias and alias[new] not in have:
                new, why = alias[new], '別名を決まった名にした (item_names.tsv)'
            if new and new != raw.strip():
                yield Change(kind, d['_row'], '@item_ja', new, f'項目名の印字は「{raw.strip()}」．{why}')


@rule('D33', '階層の欄の横棒 (-) は階層なし (空欄) とする', 1, old='(規則の番号なし．2026-11-17 ユーザ決定)')
def dash_layer(t, param):
    for kind in ('body', 'once'):
        if 'layer' not in t.head[kind]:
            continue
        for d in t.dicts(kind):
            v = d.get('layer', '').strip()
            if v and v in DASHES:
                yield Change(kind, d['_row'], '@layer', '', f'階層の印字は {v}．階層なしとした')


HYPHEN_LAYER = re.compile(r'^([A-Z])\s*[-−–]\s*(\d)$')


@rule('D34', '階層の記号の数字の前の横棒を外す (B-1 → B1)', 1, old='(規則の番号なし．2026-11-17 ユーザ決定)')
def hyphen_layer(t, param):
    for kind in ('body', 'once'):
        if 'layer' not in t.head[kind]:
            continue
        for d in t.dicts(kind):
            layers = [x.strip() for x in d.get('layer', '').split(';')]
            new = [HYPHEN_LAYER.sub(r'\1\2', x) for x in layers]
            if new != layers:
                yield Change(kind, d['_row'], '@layer', ';'.join(new), f"階層の印字は {','.join(layers)}．横棒を外した")
