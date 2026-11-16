"""表頭の値の決まり (県名・日付・単位など)"""
import re

from rules import Change, rule


def is_pref_row(d):
    return '県名' in d.get('item_ja', '') or 'präf' in d.get('item_de', '').lower()


@rule('D01', '県名の記号の数字 0 を O (大分など) に直す', '県名・地名', old='X44')
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


@rule('D06', '方位の字の重なり・逆順・3 字の順・F を直す (SSS → S・EN → NE・NWN → NNW)', '表頭の値', old='X31・X45・X46・X47')
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
DASHES = {'-', '—', '–', '−', '―'}


DITTO_PLUS = re.compile(r'^(同\s*左|左\s*同)\s+(\S.*)$')


def common_head(a, b):
    """2 つの値に共通する頭の部分 (2 字以上．無ければ '')"""
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return a[:n] if n >= 2 else ''


@rule('D17', '表頭の「同左」「左同」を左の地点の値にする．「同左 X」は左の値どうしに共通する頭の地名 + X にする', '表頭の値',
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


@rule('D18', '表頭の横棒の重なり (- -) を - にする (日付・調査番号の行は除く)', '表頭の値', old='(規則の番号なし)')
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


def _num(v):
    try:
        return float(v)
    except ValueError:
        return None


@rule('D19', '低木層・草本層の高さが上の層より高いときは小数点の落ちとみて 1 桁下げる (15 → 1.5)', '表頭の値', old='X32')
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
