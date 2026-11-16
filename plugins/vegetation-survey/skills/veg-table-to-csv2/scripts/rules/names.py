"""種名の決まり (和名優先・誤植)"""
import os
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


@rule('D10', '学名と和名の属が合わない行は，和名を優先してチェックリストの学名にする', '種名', old='和名優先')
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
