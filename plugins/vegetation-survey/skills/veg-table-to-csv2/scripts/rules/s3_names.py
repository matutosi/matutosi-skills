"""段 3: 名前を直す (誤植の訂正の表・和名優先)．段 5・6 はこの後 (学名で引く・種を数える)"""
import os
import re
import sys

from common import OLD_SCRIPTS
from rules import Change, rule


SHEET_SCRIPTS = os.path.normpath(os.path.join(OLD_SCRIPTS, '..', '..', 'veg-sheet-to-csv', 'scripts'))


_STATE = {'idx': None, 'tried': False, 'why': ''}


MISSING = []                                              # チェックリストが使えなかった理由 (decide.py が知らせる)


def _index():
    """維管束植物和名チェックリストの索引 (veg-sheet-to-csv の check_names.py)．使えなければ None"""
    if not _STATE['tried']:
        _STATE['tried'] = True
        try:
            if SHEET_SCRIPTS not in sys.path:
                sys.path.insert(0, SHEET_SCRIPTS)
            import check_names as cn
            if not os.path.exists(cn.DEFAULT_XLSX):
                raise FileNotFoundError(f'チェックリストが無い: {cn.DEFAULT_XLSX} (check_species.py --download で取得する)')
            _STATE['idx'] = (cn, cn.load_index(cn.DEFAULT_XLSX))
        except Exception as e:                            # openpyxl が無い・xlsx が無い など
            _STATE['why'] = str(e)
            MISSING.append(f'D10 (和名優先) は当てていない: {e}')
    return _STATE['idx']


def lookup(j_name):
    """和名 → (照合の結果, チェックリストの学名)．チェックリストが使えなければ None"""
    got = _index()
    if not got:
        return None
    cn, idx = got
    r = cn.check_name(idx, j_name)
    return r['status'], (r['latin'] or '').strip()


def genus(name):
    w = (name or '').split()
    return w[0].lower() if w else ''


def binomial(name):
    return ' '.join((name or '').lower().split()[:2])


_FIXES = {}


def name_fixes(t):
    """誤植の訂正の表 name_fixes.tsv (列: field raw fixed rule first_cell) を {(field, 印字): 正しい名} で．
    置き場のものと 1 つ上のフォルダのもの (全地方で共通) を重ねる (置き場のものが勝つ)．無ければ {}"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(t.dir)))
    if root not in _FIXES:
        from common import read_tsv_raw
        out = {}
        for p in (os.path.join(os.path.dirname(root), 'name_fixes.tsv'), os.path.join(root, 'name_fixes.tsv')):
            if os.path.exists(p):
                h, rows, _, _ = read_tsv_raw(p)
                for r in rows:
                    d = dict(zip(h, r + [''] * (len(h) - len(r))))
                    if d.get('field') in ('j_name', 's_name', 'place') and d.get('raw') and d.get('fixed'):
                        out[(d['field'], d['raw'])] = d['fixed']
        _FIXES[root] = out
    return _FIXES[root]


def _fix_names(t, field, label):
    fixes = name_fixes(t)
    if not fixes:
        return
    for kind in ('body', 'once'):
        if field not in t.head[kind]:
            continue
        for d in t.dicts(kind):
            raw = d.get(field, '').strip()
            new = fixes.get((field, raw))
            if raw and new and new != raw:
                yield Change(kind, d['_row'], '@' + field, new, f'{label}の印字は「{raw}」．誤植の訂正の表 (name_fixes.tsv) で直した')


@rule('D08', '和名の明らかな誤植を，訂正の表 (name_fixes.tsv) で直す', 3, old='X20')
def fix_j_name(t, param):
    yield from _fix_names(t, 'j_name', '和名')


@rule('D09', '学名の明らかな誤植を，訂正の表 (name_fixes.tsv) で直す', 3, old='X22')
def fix_s_name(t, param):
    yield from _fix_names(t, 's_name', '学名')


@rule('D10', '学名と和名の属が合わない行は，和名を優先してチェックリストの学名にする', 3, old='和名優先')
def prefer_ja_name(t, param):
    """param が species なら，属は同じで種 (先頭の 2 語) が合わない行も直す (既定は属が合わない行だけ)．
    照合の結果が ok・alias の和名だけ (似た名・あいまいな名は直さない)"""
    also_species = str(param).strip().lower() == 'species'
    cache = {}
    for kind in ('body', 'once'):
        h = t.head[kind]
        if 's_name' not in h or 'j_name' not in h:
            continue
        for d in t.dicts(kind):
            s, j = d.get('s_name', '').strip(), d.get('j_name', '').strip()
            if not s or not j:
                continue
            if j not in cache:
                cache[j] = lookup(j)
            got = cache[j]
            if not got:
                continue
            status, latin = got
            if status not in ('ok', 'alias') or not latin or latin == s:
                continue
            other_genus = genus(s) != genus(latin)
            other_species = not other_genus and binomial(s) != binomial(latin)
            if other_genus or (also_species and other_species):
                yield Change(kind, d['_row'], '@s_name', latin, f'学名の印字は「{s}」．和名を優先し，チェックリストの学名にした')



def _fix_place(t):
    """訂正の表 name_fixes.tsv の field=place の行で，注記の調査地の値の中の地名を直す (印字 → 正しい名)"""
    fixes = {raw: new for (field, raw), new in name_fixes(t).items() if field == 'place'}
    if not fixes:
        return
    for d in t.dicts('notes'):
        if not d.get('item_ja', '').startswith('調査地'):
            continue
        v = d.get('value', '')
        new = v
        for raw in sorted(fixes, key=len, reverse=True):   # 長い地名を先に
            if raw in new:
                new = new.replace(raw, fixes[raw])
        if new != v:
            yield Change('notes', d['_row'], '@value', new, f'地名の印字は「{v}」．誤植の訂正の表 (name_fixes.tsv の place) で直した')


@rule('D30', '注記の調査地の地名の誤植を，訂正の表 (name_fixes.tsv の field=place) で直す', 3, old='X2・X21・X54')
def fix_place(t, param):
    yield from _fix_place(t)


JA_PAREN = re.compile(r'^(?P<name>[^()（）]+?)\s*\+?\s*[(（](?P<inner>[^()（）]+)[)）]\s*$')


@rule('D31', '和名の末尾の括弧書き (イブキシモツケ (イワガサ)・ウツギ(含コウツギ)) を外す．中身は直しの記録に残す', 3,
      old='(規則の番号なし．2026-11-17 ユーザ決定 1a)', order=9.5)
def ja_paren(t, param):
    """和名優先 (D10) がチェックリストで引けるよう，D10 の前に当てる (order=9.5)．
    括弧書きの種に下線があり，値と対応するときは，読む段で別の行に分けてある (読み方の手引き)．ここで外すのは，分けなかった括弧書き"""
    for kind in ('body', 'once'):
        if 'j_name' not in t.head[kind]:
            continue
        for d in t.dicts(kind):
            raw = d.get('j_name', '').strip()
            m = JA_PAREN.match(raw)
            if m and m.group('name').strip():
                yield Change(kind, d['_row'], '@j_name', m.group('name').strip(),
                             f"和名の印字は「{raw}」．括弧書き ({m.group('inner').strip()}) を外した")
