"""段 4: 表頭を直す (県名・方位・同左・高さ・年)"""
import re

from rules import Change, rule
from rules._lib import YEAR4, YEAR_HEAD, _load, is_pref_row, plot_notes


@rule('D01', '県名の記号の数字 0 を O (大分など) に直す', 4, old='X44')
def pref_zero(t, param):
    plots = t.plots('header')
    for d in t.dicts('header'):
        if not is_pref_row(d):
            continue
        for p in plots:
            if (d.get(p) or '').strip() == '0':
                yield Change('header', d['_row'], p, 'O', '県名の記号の印字は数字の 0．O の字形の取り違えとみた')


ASPECTS = {'N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'}


THREE = {'NEE': 'ENE', 'NWN': 'NNW', 'SES': 'SSE', 'SWW': 'WSW', 'NWW': 'WNW',
         'NEN': 'NNE', 'SEE': 'ESE', 'SWS': 'SSW'}


OPPOSITE = {'SN', 'NS', 'EW', 'WE'}


def fix_aspect(v):
    """方位の字の誤りを直す．(直した値, 理由) か None"""
    s = v.strip()
    if not s or s in ASPECTS or not s.isalpha() or not s.isupper():
        return None
    if 'F' in s and s.replace('F', 'E') in ASPECTS:            # X47: E の横棒の欠け
        return s.replace('F', 'E'), '方位の F は E の横棒の欠けとみた'
    for n in (1, 2, 3):                                        # X31: 同じ字の重なり (SSS・SWSW・NN)
        unit = s[:n]
        if len(s) > n and len(s) % n == 0 and unit * (len(s) // n) == s and unit in ASPECTS:
            return unit, f'方位の印字は {s}．字の重なりとみた'
    if s in OPPOSITE:                                          # X46: 逆向きの 2 字
        return '-', f'方位の印字は {s}．逆向きの 2 字なので方位なしとした'
    if len(s) == 2 and s[::-1] in ASPECTS:                     # X31: 逆順 (EN・WS)
        return s[::-1], f'方位の印字は {s}．字の順が逆とみた'
    if s in THREE:                                             # X45: 3 字の方位の字の順
        return THREE[s], f'方位の印字は {s}．字の順の誤りとみた'
    return None


@rule('D06', '方位の字の重なり・逆順・3 字の順・F を直す (SSS → S・EN → NE・NWN → NNW)', 4, old='X31・X45・X46・X47')
def aspect_letters(t, param):
    plots = t.plots('header')
    for d in t.dicts('header'):
        if '方位' not in d.get('item_ja', '') and not d.get('item_de', '').lower().startswith('expos'):
            continue
        if '傾斜' in d.get('item_ja', ''):                      # 「方位・傾斜」を 1 行に書いた表は当てない
            continue
        for p in plots:
            got = fix_aspect(d.get(p) or '')
            if got:
                yield Change('header', d['_row'], p, got[0], got[1])


DITTO = {'同左', '左同', '同 左', '左 同'}


DITTO_PLUS = re.compile(r'^(同\s*左|左\s*同)\s+(\S.*)$')


def common_head(a, b):
    """2 つの値に共通する頭の部分 (2 字以上．無ければ '')"""
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return a[:n] if n >= 2 else ''


@rule('D17', '表頭の「同左」「左同」を左の地点の値にする．「同左 X」は左の値どうしに共通する頭の地名 + X にする', 4,
      old='(規則の番号なし．同左)')
def ditto_left(t, param):
    """「同左 X」(同左のあとに語が続く) は，左の 2 地点の値 (直したあとの値) に共通する頭 + X (阿蘇外輪山 + 北西部)．
    左の値が 1 つしか無い・共通する頭が無いときは直さない"""
    plots = t.plots('header')
    for d in t.dicts('header'):
        prev = []                                          # 左の地点の値 (同左を直したあとの値)
        for p in plots:
            v = (d.get(p) or '').strip()
            m = DITTO_PLUS.match(v)
            if v in DITTO and prev:
                yield Change('header', d['_row'], p, prev[-1], f'印字は {v}．左の地点の値にした')
                prev.append(prev[-1])
            elif m and len(prev) >= 2 and common_head(prev[-1], prev[-2]):
                new = common_head(prev[-1], prev[-2]) + m.group(2)
                yield Change('header', d['_row'], p, new, f'印字は {v}．左の地点の値に共通する頭の地名に続けた')
                prev.append(new)
            elif v:
                prev.append(v)


def _num(v):
    try:
        return float(v)
    except ValueError:
        return None


@rule('D19', '低木層・草本層の高さが上の層より高いときは小数点の落ちとみて 1 桁下げる (15 → 1.5)', 4, old='X32')
def height_point(t, param):
    """上の層の高さ (同じ地点で，表頭の上にある直近の「…層の高さ」の数) より大きい整数だけ．直しても上の層より高ければ直さない"""
    plots = t.plots('header')
    rows = [d for d in t.dicts('header') if '高さ' in d.get('item_ja', '') and '層' in d.get('item_ja', '')]
    for i, d in enumerate(rows):
        if not ('低木' in d['item_ja'] or '草本' in d['item_ja']):
            continue
        for p in plots:
            v = (d.get(p) or '').strip()
            if not v.isdigit() or int(v) < 10:
                continue
            upper = next((u for u in (_num((r.get(p) or '').strip()) for r in reversed(rows[:i])) if u is not None), None)
            if upper is None or int(v) <= upper:
                continue
            new = f'{v[:-1]}.{v[-1]}'
            if float(new) <= upper:
                yield Change('header', d['_row'], p, new, f'高さの印字は {v}．上の層 ({upper:g} m) より高いので小数点の落ちとみた')


@rule('D24', '調査年が出典の年より後で，1 字違いのときだけ出典の年に合わせる (翌年 1-3 月は年度の報告書とみて直さない)', 4,
      old='X34・X55')
def year_by_source(t, param):
    src = plot_notes(t, '出典')
    plots = t.plots('header')
    for d in t.dicts('header'):
        key = d.get('item_ja', '') + ' ' + d.get('item_de', '').lower()
        if not ('年月日' in key or 'datum' in key):
            continue
        for p in plots:
            v = (d.get(p) or '').strip()
            m = YEAR_HEAD.match(v)
            years = {int(y) for text in src.get(p, []) for y in YEAR4.findall(text)}
            if not m or len(years) != 1:
                continue
            y = int(m.group(2))
            y = y + 1900 if y < 100 else y
            s = years.pop()
            if y <= s or sum(a != b for a, b in zip(f'{y:04d}', f'{s:04d}')) != 1:
                continue
            rest = v[m.end():].split()
            if y - s == 1 and rest and rest[0].isdigit() and 1 <= int(rest[0]) <= 3:
                continue                                    # 翌年の 1-3 月: 年度の報告書 (規則 X55)
            new = m.group(1) + (f'{s:04d}'[-len(m.group(2)):]) + v[m.end():]
            yield Change('header', d['_row'], p, new, f'年の印字は {m.group(2)}．出典 ({s}) より後で 1 字違いなので，出典の年の誤植とみた')


PREF = re.compile(r'([一-龥]{2,3}県)')


def pref_of(text, places):
    """注記の調査地の文から県を決める．県名が書いてあればそれ，無ければ地名の表 (長い地名を先に)．決まらなければ ''"""
    found = set(PREF.findall(text))
    if not found:
        for place in sorted(places, key=len, reverse=True):
            if place in text:
                found.add(places[place])
                break
    return found.pop() if len(found) == 1 else ''


@rule('D25', '表頭の県名の記号を，注記の調査地の県 (県名の記載か，地名 → 県の対応の表) に合わせる', 4, old='X1・X33')
def pref_by_place(t, param):
    """対応の表: place_pref.tsv (列: place pref．地名 → 県)・pref_symbols.tsv (列: symbol pref．その地方の県名の記号)．
    記号の表が無ければ当てない．注記の調査地から県が 1 つに決まり，表頭の記号の県と違うときだけ直す"""
    symbols = _load(t, 'pref_symbols.tsv')
    if not symbols:
        return
    sym_pref = {r['symbol']: r['pref'] for r in symbols}
    places = {r['place']: r['pref'] for r in _load(t, 'place_pref.tsv') if r.get('place') and r.get('pref')}
    sites = plot_notes(t, '調査地')
    plots = t.plots('header')
    for d in t.dicts('header'):
        if not is_pref_row(d):
            continue
        used = {(d.get(p) or '').strip() for p in plots}
        for p in plots:
            cur = (d.get(p) or '').strip()
            if not cur or cur in ('-', '—') or p not in sites:
                continue
            if len(re.split(r'[\s/,・]+', cur)) > 1:        # 記号が 2 つあるセル (複数の県をまとめた列．N/F・Ka M) は直さない
                continue
            prefs = {pref_of(text, places) for text in sites[p]}
            if len(prefs) != 1 or '' in prefs:              # 県が決まらない・注記が食い違う地点は直さない
                continue
            pref = prefs.pop()
            if sym_pref.get(cur) == pref:
                continue
            cands = [s for s, pr in sym_pref.items() if pr == pref]
            if not cands:
                continue
            new = next((s for s in cands if s in used), cands[0])    # その表で使っている記号を選ぶ (K と Ku など)
            if new != cur:
                yield Change('header', d['_row'], p, new, f'県名の印字は {cur}．注記の調査地は{pref}なので {new} とした')
