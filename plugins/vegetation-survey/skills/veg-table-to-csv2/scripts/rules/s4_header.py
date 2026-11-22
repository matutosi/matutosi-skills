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


ITEM_YM = re.compile(r'((?:19|20)\d\d)\s*[.．/年]\s*(\d{1,2})(?!\d)')
ITEM_Y2 = re.compile(r"['’‘](\d{2})(?!\d)")
DAY_ONLY = re.compile(r'^(\d{1,2})(\??)$')
MONTH_DAY = re.compile(r'^(\d{1,2})\s*[\s/.]\s*(\d{1,2})(\??)$')


def is_date_item(d):
    key = (d.get('item_ja', '') + ' ' + d.get('item_de', '')).lower()
    return '年月日' in key or '月日' in key or '調査日' in key or 'datum' in key


@rule('D37', '調査年月日の値が日だけで年月が項目名 (の括弧) にあるときは項目名の年月を補う (Datum (1988.3) の 19 → 1988 3 19)．'
             '項目名の年が 2 桁 (調査年月日 (\'78)) で値が月日だけのときは，年を 19xx として補う (8 2 → 1978 8 2)', 4,
      old='(規則の番号なし．屋久島ページ内 Tab.024・025・030・北海道 Tab.049．2026-11-17・22 ユーザ決定)')
def day_with_item_ym(t, param):
    """項目名 (和文と独文) から「年 . 月」を探す．値が 1-31 の日の数だけ (? つきも) のセルに当てる．
    年だけの項目名 (Datum d. Aufn. (1982)) は今の to_csv.py が月日の値に年を補うので，ここでは当てない (沖縄 Tab.096・100)．
    年が引用符つきの 2 桁 ('78) なら to_csv.py は年を拾えないので，月日 (8 2・8/2) の値に 19xx を補う"""
    plots = t.plots('header')
    for d in t.dicts('header'):
        if not is_date_item(d):
            continue
        name = d.get('item_ja', '') + ' ' + d.get('item_de', '')
        m = ITEM_YM.search(name)
        y2 = ITEM_Y2.search(name)
        if not m and y2 and not YEAR4.search(name):
            y = 1900 + int(y2.group(1))
            for p in plots:
                v = (d.get(p) or '').strip()
                md = MONTH_DAY.match(v)
                if md and 1 <= int(md.group(1)) <= 12 and 1 <= int(md.group(2)) <= 31:
                    yield Change('header', d['_row'], p, f'{y} {int(md.group(1))} {int(md.group(2))}{md.group(3)}',
                                 f"値の印字は月日だけ ({v})．年は項目名の '{y2.group(1)} を {y} として補った")
            continue
        if not m:
            continue
        y, mo = m.group(1), int(m.group(2))
        if not 1 <= mo <= 12:
            continue
        for p in plots:
            v = (d.get(p) or '').strip()
            dm = DAY_ONLY.match(v)
            if dm and 1 <= int(dm.group(1)) <= 31:
                yield Change('header', d['_row'], p, f'{y} {mo} {int(dm.group(1))}{dm.group(2)}',
                             f'値の印字は日だけ ({v})．年月は項目名の {y}.{mo} を補った')


ISO_DATE = re.compile(r'^\d{4}(?:-\d{2}(?:-\d{2})?)?(?:/\d{4}(?:-\d{2}(?:-\d{2})?)?)?$')


@rule('D43', '注記の調査年月日の値を日付の形にそろえる (2. Aug. 1977 → 1977-08-02・1976-12-24～26 → 1976-12-24/1976-12-26)', 4,
      old='(規則の番号なし．日の範囲の書き方の不ぞろい．九州ページ内 Tab.040・067・096．2026-11-22 ユーザ決定)')
def note_dates(t, param):
    """表頭の日付は to_csv.py が読む (T 規則) が，注記の値は転記のまま CSV に出るので，同じ読み方 (to_csv.norm_date) でそろえる．
    日の範囲は 1979-10-19/1979-10-23 の形 (始め/終わり)．読めない値・日付が 2 つ以上ある値は直さない"""
    from common import to_csv
    for d in t.dicts('notes'):
        if not is_date_item(d):
            continue
        v = (d.get('value') or '').strip()
        if not v or ISO_DATE.match(v):
            continue
        q = '?' if v.endswith('?') else ''
        s = v.rstrip('?').strip().translate(to_csv.FIX)
        part = to_csv.partial_date(s)
        new = part[0] if part and part[0] != '-' else to_csv.norm_date(s)
        if new and ISO_DATE.match(new) and new != v:
            yield Change('notes', d['_row'], '@value', new + q, f'値の印字は {v}．日付の形にそろえた')


FELD_ID = re.compile(r'^(?:in\s+)?([A-Za-z]+)\s*[-‐ー−\s]?\s*(\d+[A-Za-z]?)\s*:?$', re.I)
FELD_SYMBOLS = re.compile(r'^[A-Za-z]+\*?(?:\s*[,，・]\s*[A-Za-z]+\*?)*:?$')


def feld_numbers(t):
    """表頭の調査番号の行から {調査番号 (空白・ハイフンを除いた大文字): 地点} と {記号: [地点]}"""
    ids, syms = {}, {}
    for d in t.dicts('header'):
        ja, de = d.get('item_ja', ''), d.get('item_de', '').lower()
        if not (ja.startswith('調査番号') or de.startswith('feld')):
            continue
        for p in t.plots('header'):
            m = FELD_ID.match((d.get(p) or '').strip())
            if m:
                ids.setdefault((m.group(1) + m.group(2)).upper(), p)
                syms.setdefault(m.group(1).upper(), []).append(p)
        break
    return ids, syms


@rule('D44', '1 回出現の見出しと注記の地点が調査番号 (in OK-1・OK: 大島) で印字された表は，表頭の調査番号の行から地点の番号を引く', 4, order=0.5,
      old='(規則の番号なし．関東 Tab.068．2026-11-22 ユーザ決定)')
def plot_by_feld_number(t, param):
    """1 回出現の plot の `OK-1`・`OK 1`・`in OK-1:` は，表頭の調査番号が OK 1 の地点へ．
    注記の plot の記号 (`OK`・`MM,MK`・`OK*`) は，調査番号がその記号で始まる地点すべてへ．
    表頭に無い調査番号・地点の決まらない記号は直さない (印字のまま残り，地点に割り当たらない)"""
    ids, syms = feld_numbers(t)
    if not ids:
        return
    for d in t.dicts('once'):
        v = (d.get('plot') or '').strip()
        m = FELD_ID.match(v)
        if v and not v.isdigit() and m:
            p = ids.get((m.group(1) + m.group(2)).upper())
            if p:
                yield Change('once', d['_row'], '@plot', p, f'地点の印字は調査番号 {v}．表頭の調査番号から地点 {p} とした')
    for d in t.dicts('notes'):
        v = (d.get('plot') or '').strip()
        if not v or v[0].isdigit():
            continue
        m = FELD_ID.match(v)
        if not (m or FELD_SYMBOLS.match(v)):
            continue
        if m and (m.group(1) + m.group(2)).upper() in ids:          # 1 つの調査番号 (OK-1)
            p = ids[(m.group(1) + m.group(2)).upper()]
            yield Change('notes', d['_row'], '@plot', p, f'地点の印字は調査番号 {v}．表頭の調査番号から地点 {p} とした')
            continue
        want = [s.strip().rstrip('*').upper() for s in re.split(r'[,，・]', v.rstrip(':'))]
        if not any(s in syms for s in want):                      # 記号のどれも表頭に無い
            continue
        plots = sorted({p for s in want if s in syms for p in syms[s]}, key=int)
        yield Change('notes', d['_row'], '@plot', ','.join(plots),
                     f'地点の印字は調査番号の記号 {v}．表頭の調査番号がその記号の地点 ({len(plots)} 地点) とした')
