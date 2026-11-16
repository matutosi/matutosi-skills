"""表頭の決まり (字の乱れ・脚注の印・年・県名を地名に合わせる)"""
import os
import re

from common import read_tsv_raw, to_csv
from rules import Change, rule
from rules.site import is_pref_row

COLON = re.compile(r'^(\d+)\s*[:：]\s*(\d+)$')


def is_height_row(d):
    ja, de = d.get('item_ja', ''), d.get('item_de', '').lower()
    return '高さ' in ja or '植生高' in ja or '群落高' in ja or de.startswith('höhe d.')


@rule('D22', '高さの行の「数字:数字」は小数点の印字の乱れとみて「数字.数字」に直す (0:2 → 0.2)', '表頭の値',
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


@rule('D23', '表頭の値の末尾の「*」(脚注の印) を外す (Y* → Y)', '表頭の値', old='(規則の番号なし．脚注の印)')
def footnote_mark(t, param):
    plots = t.plots('header')
    for d in t.dicts('header'):
        for p in plots:
            v = (d.get(p) or '').strip()
            core = v.rstrip('*＊').rstrip()
            if core and core != v:
                yield Change('header', d['_row'], p, core, f'印字は {v}．末尾の * は脚注の印とみて外した')


YEAR_HEAD = re.compile(r"^('?)(\d{2}|\d{4})(?=\s|$)")
YEAR4 = re.compile(r'(?:19|20)\d\d')


def plot_notes(t, item):
    """注記の {地点: [値と印字をつないだ文]}．item は item_ja の頭 (調査地・出典)"""
    out = {}
    for d in t.dicts('notes'):
        if not d.get('item_ja', '').startswith(item):
            continue
        text = d.get('value', '') + ' ' + d.get('value_raw', '')
        for p in to_csv.plot_list(d.get('plot', '').replace(' ', '')):
            out.setdefault(p, []).append(text)
    return out


@rule('D24', '調査年が出典の年より後で，1 字違いのときだけ出典の年に合わせる (翌年 1-3 月は年度の報告書とみて直さない)', '日付・番号',
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


_TABLES = {}
PREF = re.compile(r'([一-龥]{2,3}県)')


def _load(t, name):
    """置き場と 1 つ上のフォルダの対応の表を重ねて読む (置き場のものが勝つ)．[{列: 値}]"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(t.dir)))
    key = (root, name)
    if key not in _TABLES:
        rows = []
        for p in (os.path.join(os.path.dirname(root), name), os.path.join(root, name)):
            if os.path.exists(p):
                h, body, _, _ = read_tsv_raw(p)
                rows += [dict(zip(h, r + [''] * (len(h) - len(r)))) for r in body if r and r[0] and not r[0].startswith('#')]
        _TABLES[key] = rows
    return _TABLES[key]


def pref_of(text, places):
    """注記の調査地の文から県を決める．県名が書いてあればそれ，無ければ地名の表 (長い地名を先に)．決まらなければ ''"""
    found = set(PREF.findall(text))
    if not found:
        for place in sorted(places, key=len, reverse=True):
            if place in text:
                found.add(places[place])
                break
    return found.pop() if len(found) == 1 else ''


@rule('D25', '表頭の県名の記号を，注記の調査地の県 (県名の記載か，地名 → 県の対応の表) に合わせる', '県名・地名', old='X1・X33')
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
