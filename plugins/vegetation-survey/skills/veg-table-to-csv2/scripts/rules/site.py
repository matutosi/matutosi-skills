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
