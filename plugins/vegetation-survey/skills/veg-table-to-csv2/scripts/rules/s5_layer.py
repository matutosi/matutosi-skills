"""段 5: 階層を直す"""
import re

from rules import Change, rule
from rules._lib import header_layers


TWO = re.compile(r'第\s*[12１２]|schicht\s*-?\s*[12]|B\s*[12]\b', re.I)


def tree_layers(t):
    """表頭の高木層の数: 0 (高木層の行が無い・全地点が - で高木層の無い表)・1 (高木層が 1 つ)・2 (第 1・第 2 に分かれる)"""
    rows = [d for d in t.dicts('header') if '高木' in d.get('item_ja', '') or 'baumschicht' in d.get('item_de', '').lower()]
    if not rows:
        return 0
    if any(TWO.search(d.get('item_ja', '') + ' ' + d.get('item_de', '')) for d in rows):
        return 2
    plots = t.plots('header')
    has_value = any((d.get(p) or '').strip() not in ('', '-', '—', '–') for d in rows for p in plots)
    return 1 if has_value else 0                          # 全地点が - の表は「高木層が 1 つ」とみない (九州 Tab.141)


@rule('D05', '表頭の高木層が 1 つだけの表の階層 B2 を B に直す', 5, old='X24')
def single_tree_layer(t, param):
    if tree_layers(t) != 1:
        return
    for kind in ('body', 'once'):
        if 'layer' not in t.head[kind]:
            continue
        for d in t.dicts(kind):
            layers = [x.strip() for x in d.get('layer', '').split(';')]
            if 'B2' not in layers:
                continue
            new = ';'.join('B' if x == 'B2' else x for x in layers)
            yield Change(kind, d['_row'], '@layer', new, '表頭の高木層は 1 つ (B) だけ．B2 の印字を B に直した')
            note = d.get('note', '')
            if 'B2 に' in note:                              # 下線の対応の書き方 (B2 に下線) も合わせる
                yield Change(kind, d['_row'], '@note', note.replace('B2 に', 'B に'), '階層の直しに合わせた')


WOODY_LAYERS = {'B', 'B1', 'B2', 'T', 'T1', 'T2', 'S', 'S1', 'S2'}


_WOODY = {}


def woody_names(t):
    """木本と分かる種: 同じ置き場のどこかの表で，高木層・低木層 (B・B1・B2・S など) の値がある種の和名と学名 (先頭 2 語)．
    `S;K` のような複数の階層の行は，セルごとに下線の規則 (今のスキルの to_csv.cell_layer) で決まる階層を見て，
    木本の層に決まる値があるときだけ数える．どちらの層か決まらない値は手がかりにしない
    (2026-11-16 ユーザ決定 4a．九州 Tab.150 のノササゲが S;K の行の決まらない値だけで木本とされていた．
    行ごと外すと，S;K の行で S に決まるアリドウシまで外れた)．置き場ごとに 1 回だけ数える"""
    import os
    from common import Table, table_dirs, to_csv
    root = os.path.dirname(os.path.dirname(os.path.abspath(t.dir)))
    if root not in _WOODY:
        names = set()
        for tdir in table_dirs(root):
            x = Table(tdir)
            for kind in ('body', 'once'):
                if 'layer' not in x.head[kind]:
                    continue
                plots = x.plots('body') if kind == 'body' else []
                to_csv.PLOTS_SEEN.clear()
                to_csv.PLOTS_SEEN.update(plots)
                s_prev = j_prev = ''
                for d in x.dicts(kind):
                    if d.get('kind') == 'group':
                        continue
                    s, j = d.get('s_name', '').strip(), d.get('j_name', '').strip()
                    if kind == 'body' and not s and not j:    # 階層ごとの続きの行は上の種
                        s, j = s_prev, j_prev
                    s_prev, j_prev = s, j
                    layers = d.get('layer', '').replace(' ', '').split(';')
                    if len(layers) == 1:
                        woody = layers[0] in WOODY_LAYERS
                    elif kind == 'body':                      # 複数の階層の行: 値ごとに決まる階層を見る
                        row = {k: v for k, v in d.items() if k != '_row'}
                        woody = any(to_csv.cell_layer(row, p) in WOODY_LAYERS for p in plots
                                    if (d.get(p) or '').strip() not in to_csv.ABSENT)
                    else:
                        woody = False
                    if woody:
                        names.update(n for n in (j, ' '.join(s.lower().split()[:2])) if n)
                to_csv.PLOTS_SEEN.clear()
        _WOODY[root] = names
    return _WOODY[root]


@rule('D16', '1 回出現で階層の印字が無い種は，木本と分かる種を除いて K 層にする (階層を書く表だけ)', 5, old='X51')
def once_herb_layer(t, param):
    """1 回出現の半分以上の行に階層がある表に限る (階層を書かない表では当てない)．
    木本と分かる種 (同じ置き場のどこかで高木層・低木層に出ている種) は直さない．
    草本の一覧 (今のスキルの references/herb_species.tsv) にある種は，木本の判定より先に K とする
    (2026-11-16 ユーザ決定．はじめは草本の一覧にある種だけだった)"""
    from common import to_csv
    if 'layer' not in t.head['once']:
        return
    rows = [d for d in t.dicts('once') if d.get('s_name', '').strip() or d.get('j_name', '').strip()]
    with_layer = sum(1 for d in rows if d.get('layer', '').strip())
    if not rows or with_layer * 2 < len(rows):
        return
    woody = None
    for d in rows:
        if d.get('layer', '').strip():
            continue
        s, j = d.get('s_name', '').strip(), d.get('j_name', '').strip()
        if s in to_csv.HERBS:
            yield Change('once', d['_row'], '@layer', 'K', '階層の印字なし．草本なので K とした')
            continue
        if woody is None:
            woody = woody_names(t)
        if j in woody or ' '.join(s.lower().split()[:2]) in woody:
            continue                                        # 木本と分かる種は階層を補わない
        yield Change('once', d['_row'], '@layer', 'K', '階層の印字なし．木本と分かる種でないので K とした')


ODD = {'F': 'K', 'H': 'K', 'BB2': 'B2', 'A': ''}


@rule('D28', '表頭に無い階層の記号を直す (F・H → K，草本層が 1 つの表の K1・K2 → K，BB2 → B2，A → 空欄)', 5, old='X37')
def odd_layer(t, param):
    """表頭にその記号の層があるときは直さない．草本層が 1 つの表 = 表頭に K1・K2 の行が無い"""
    have = header_layers(t)
    for kind in ('body', 'once'):
        if 'layer' not in t.head[kind]:
            continue
        for d in t.dicts(kind):
            layers = [x.strip() for x in d.get('layer', '').split(';')]
            new = []
            for x in layers:
                if x in have or not x:
                    new.append(x)
                elif x in ODD:
                    new.append(ODD[x])
                elif x in ('K1', 'K2') and not ({'K1', 'K2'} & have):
                    new.append('K')
                else:
                    new.append(x)
            new = [x for i, x in enumerate(new) if x or len(new) == 1]
            if new != layers:
                yield Change(kind, d['_row'], '@layer', ';'.join(new),
                             f"階層の印字は {','.join(layers)}．表頭に無い記号なので {','.join(new) or '空欄'} とした")


_FERNS = {}


def fern_lists():
    """references/fern_genera.tsv を (当てる属, 除く属, 除く種) で．種は「属 種小名」の 2 語"""
    if not _FERNS:
        import os
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'references', 'fern_genera.tsv')
        yes, no_g, no_s = set(), set(), set()
        with open(p, encoding='utf-8') as f:
            for line in f.read().splitlines()[1:]:
                parts = line.split(chr(9))
                if len(parts) < 2 or not parts[0].strip():
                    continue
                name, use = parts[0].strip().lower(), parts[1].strip()
                if ' ' in name:
                    no_s.add(name)
                elif use == 'yes':
                    yes.add(name)
                else:
                    no_g.add(name)
        _FERNS.update(yes=yes, no_g=no_g, no_s=no_s)
    return _FERNS['yes'], _FERNS['no_g'], _FERNS['no_s']


@rule('D35', '階層の印字の無いシダ (トクサ類・ヒカゲノカズラ類を含む) は K 層にする．着生シダ・木生シダは除く (階層の欄のある表だけ)', 5,
      old='X14・X42')
def fern_herb_layer(t, param):
    """シダの属と除く属・種は references/fern_genera.tsv (今のスキルの X14 の文面から)．
    今のスキルの X14 は階層の欄の無い表 (総合常在度表など) にも当てるが，ここでは欄のある表だけ (欄を足せないため)．
    1 回出現は D16 (木本と分かる種を除いて K) も当たる．続きの行 (名の無い行) は上の種の階層ごとの行なので当てない"""
    yes, no_g, no_s = fern_lists()
    for kind in ('body', 'once'):
        if 'layer' not in t.head[kind] or 's_name' not in t.head[kind]:
            continue
        for d in t.dicts(kind):
            if d.get('kind') == 'group' or d.get('layer', '').strip():
                continue
            words = d.get('s_name', '').lower().split()
            if not words:
                continue
            g, sp = words[0], ' '.join(words[:2])
            if g in yes and g not in no_g and sp not in no_s:
                yield Change(kind, d['_row'], '@layer', 'K', '階層の印字なし．シダ植物なので K とした')
