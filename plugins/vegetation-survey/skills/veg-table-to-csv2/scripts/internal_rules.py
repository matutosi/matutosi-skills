"""今のスキルの to_csv.py の中の決まり (T 規則) に番号を付ける (2026-11-17 ユーザ決定 5a)．

to_csv.py は CSV を組むときに，階層を下線で決める・草本を K にする・群度を補う などの判断をする．
中身は書き直さず，出力の行 (note・値の形) から当たった決まりを見分けて，note_judge に番号を足す．
D 規則 (rules/) と違い，採否 (rule_settings.tsv) では止められない (to_csv.py の動きそのもの)．
"""
import re

# (番号, 中身, 今のスキルの規則)
INTERNAL = [
    ('T01', '複数の階層の行のセルの階層を，下線 (と下線の種類) で決める', '下線の決まり (5.3)'),
    ('T02', '階層が複数のまま決まらない草本 (草本の一覧の種) は K 層にする．候補に K があるときだけ', '草本の一覧 (herb_species.tsv)'),
    ('T03', '階層の印字が無い行は，すぐ下の行の階層 (1 つ) とみる (層の位置の誤り)', 'layer_from_below (2026-11-05)'),
    ('T04', '階層の印字の無い行が続く・下が見出しのときは空欄のまま，確認に出さない (つる・着生)', 'layer_from_below (0.5.14)'),
    ('T05', '群度の印字が無い 1 桁の被度 (1-5) の群度を補う (--soc-default．+・r の群度 1 は数えない)', 'X50'),
    ('T06', '小文字の v は「極めて微小」の印 (被度 v)', 'X16'),
    ('T07', '白抜きの丸 ○ は存在の印 (被度 O・群度なし)', 'X56'),
    ('T08', '方位・傾斜の L はレベル (方位 -・傾斜 0)', 'K1'),
    ('T09', '月・日が - の日付・月の範囲の日付は，分かる所までにする (1980・1980-06)', '(0.5.10)'),
    ('T10', '表頭の数の中黒・点の後ろの空白は小数点とみる (0. 5・1・8 → 0.5・1.8)', '(規則の番号なし)'),
    ('T11', '列の種類 (調査区・常在度・混在) を値の形で決める', 'X9'),
]
TITLES = {rid: title for rid, title, _ in INTERNAL}

SEP = re.compile(r'[・･·.]')
DOT_NUM = re.compile(r'^\d+\s*[.・･·•]\s*\d+$')


def tags(r, is_comp):
    """出力の 1 行に当たった T 規則の番号の並び"""
    note = r.get('note_read', '') or ''
    out = []
    if is_comp:
        if '下線の規則で階層を' in note:
            out.append('T01')
        if '草本のため K 層とした' in note:
            out.append('T02')
        if '下の行の階層' in note:
            out.append('T03')
        if '階層の印字なし (つる・着生' in note:
            out.append('T04')
        raw = (r.get('value_decided') or r.get('value_raw') or '').strip().rstrip('?').strip()
        if r.get('sociability') and not r.get('constancy') and re.fullmatch(r'[1-5]', raw):
            out.append('T05')
        if r.get('cover') == 'v':
            out.append('T06')
        if r.get('cover') == 'O':
            out.append('T07')
        return out
    item = r.get('item_ja', '')
    if 'L (レベル)' in note:
        out.append('T08')
    if any(x in note for x in ('月日の印字は -', '日の印字は -', '月の範囲')):
        out.append('T09')
    if DOT_NUM.match((r.get('value_raw') or '').strip()) and r.get('value', '') != (r.get('value_raw') or '').strip():
        out.append('T10')
    if item == '列の種類' and r.get('source') == 'derived':
        out.append('T11')
    return out


def add(rows, is_comp):
    """行の note_judge に T 規則の番号を足す (D 規則・個別の判断の後ろに)"""
    for r in rows:
        got = tags(r, is_comp)
        if got:
            r['note_judge'] = ';'.join(x for x in [r.get('note_judge', '')] + got if x)
