"""表頭の値の決まり (県名・日付・単位など)"""
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
