"""矛盾 (文脈からおかしい箇所) を洗い出す．decide.py が決定を作るときに呼び，conflicts.tsv に書く．

    python scripts/conflicts.py <置き場> [--out <出力先>]    # conflicts.tsv のまとめを出す (decide.py を回したあと)

矛盾は機械が作り直す (ユーザに 1 件ずつ聞く一覧ではない)．規則で決まるものは規則 (rules/) にし，
規則で決まらないものだけを個別の判断 (judgments.tsv) に回す．その材料．

区分 (CSV の note_conflict にはこの記号が入る):
  N  出現種数が印字と合わない地点 (常在度の列は比べない)
  V  値が読めない・読みに自信が無いセル (status=check の組成)
  L  階層が 1 つに決まらないセル (status=multi)
  S  表頭・注記の check (日付として読めない・調査区数の疑い など)
  J  引き継ぎの判断が残るセル (今のスキルの規則で直したが，まだ関数になっていないもの)
  U  前回のユーザ確認があったセル (決定には引き継いでいない．規則を決めるときの例)
  Y  調査年が出典の年より後 (調査より前に発行されたことになる)．転記は直さず status=check にする
     (出典の翌年の 1-3 月は年度の報告書とみて出さない．今のスキルの規則 X55 と同じ．2026-11-16 ユーザ決定)
  R  範囲外の値 (植被率が 100 を超える・傾斜が 90 を超える．今の規則 X6)
  H  層の高さの順が逆 (下の層が上の層より高い．今の規則 K2・X4)
  D  存在しない日付 (月が 13 以上・日が 32 以上・その月に無い日．今の規則 X5)
  G  調査地の県と表頭の県名の記号が食い違う (D25 で直せなかったもの．今の規則 X41)
  P  注記に調査地の無い地点 (ほかの地点には調査地がある表だけ．今の規則 X3)
Y・R・H・D・G は転記を直さず，その行の status を check にする (要確認．2026-11-16・17 ユーザ決定)．
P は結び付く行が無いので conflicts.tsv だけに出す．
今の規則 X19 (近い表の同じ調査地の日付)・X39 (群落区分の境) は転記だけでは決められないので出さない．
"""
import argparse
import collections
import os
import sys

from common import read_side, read_tsv_raw

KINDS = collections.OrderedDict([
    ('N', '出現種数が印字と合わない'), ('V', '値が読めない・自信なし'), ('L', '階層が決まらない'),
    ('S', '表頭・注記の check'), ('J', '引き継ぎの判断が残る'), ('U', '前回のユーザ確認'),
    ('Y', '調査年が出典の年より後'), ('R', '範囲外の値'), ('H', '層の高さの順が逆'), ('D', '存在しない日付'),
    ('G', '調査地の県と県名の記号が食い違う'), ('P', '注記に調査地の無い地点')])
CHECK_KINDS = {'Y', 'R', 'H', 'D', 'G'}                                       # 出力の行の status を check にする区分 (to_csv.py の check と同じ扱い)


def later_than_source(t):
    """調査年が出典の年より後のセル [(行番号, 地点, 調査年, 出典の年)]．出典の年が 1 つに決まる地点だけ．
    出典の翌年の 1-3 月は年度の報告書とみて出さない (今のスキルの規則 X55)"""
    from rules._lib import YEAR4, YEAR_HEAD, plot_notes
    src = plot_notes(t, '出典')
    out = []
    for d in t.dicts('header'):
        key = d.get('item_ja', '') + ' ' + d.get('item_de', '').lower()
        if not ('年月日' in key or 'datum' in key):
            continue
        for p in t.plots('header'):
            v = (d.get(p) or '').strip()
            m = YEAR_HEAD.match(v)
            years = {int(y) for text in src.get(p, []) for y in YEAR4.findall(text)}
            if not m or len(years) != 1:
                continue
            y = int(m.group(2))
            y = y + 1900 if y < 100 else y
            s = next(iter(years))
            if y <= s:
                continue
            rest = v[m.end():].split()
            if y - s == 1 and rest and rest[0].isdigit() and 1 <= int(rest[0]) <= 3:
                continue
            out.append((d['_row'], p, y, s))
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


HEIGHT_ORDER = [('高木第1層', '高木第一層', '高木層'), ('高木第2層', '高木第二層'), ('低木第1層', '第1低木層', '低木層'),
                ('低木第2層', '第2低木層'), ('草本第1層', '第1草本層', '草本層'), ('草本第2層', '第2草本層')]


def header_checks(t, sites):
    """R・H・D の矛盾 [(cell_id, 区分, 説明)]．sites はその表の sites.csv の行 (決定のあとの値)"""
    out = []
    val = {(r['cell_id']): r for r in sites if r.get('source') == 'header'}
    heights = {}                                           # 地点 -> [(順位, 高さ, cell_id)]
    for r in val.values():
        ja = r.get('item_ja', '').replace(' ', '')
        v = _num(r.get('value', ''))
        if '植被率' in ja and v is not None and v > 100:
            out.append([r['cell_id'], 'R', f'{r["item_ja"]} {r["value"]} が 100 を超える'])
        elif '傾斜' in ja and '方位' not in ja and v is not None and v > 90:
            out.append([r['cell_id'], 'R', f'{r["item_ja"]} {r["value"]} が 90 を超える'])
        if '高さ' in ja and v is not None:
            for k, names in enumerate(HEIGHT_ORDER):
                if any(ja.startswith(n) for n in names):
                    heights.setdefault(r.get('plot', ''), []).append((k, v, r['cell_id'], r['item_ja']))
                    break
        if ('年月日' in ja or 'datum' in r.get('item_de', '').lower()) and r.get('value', ''):
            parts = r['value'].split('-')
            if len(parts) >= 2 and all(x.isdigit() for x in parts):
                import calendar
                y, m = int(parts[0]), int(parts[1])
                d = int(parts[2]) if len(parts) >= 3 else 1
                if not 1 <= m <= 12 or not 1 <= d <= (calendar.monthrange(y, m)[1] if 1 <= m <= 12 else 31):
                    out.append([r['cell_id'], 'D', f'{r["value"]} は存在しない日付'])
    for p, hs in heights.items():
        hs.sort()
        for (k1, v1, c1, n1), (k2, v2, c2, n2) in zip(hs, hs[1:]):
            if k2 > k1 and v2 > v1:
                out.append([c2, 'H', f'{n2} {v2:g} が上の層 ({n1} {v1:g}) より高い'])
    return out


def pref_checks(t, sites):
    """G・P の矛盾．県名の記号の表 (pref_symbols.tsv) が無い置き場では G を出さない"""
    from rules._lib import _load, drop_plots, is_pref_row, plot_notes
    from rules.s4_header import pref_of
    out = []
    notes = plot_notes(t, '調査地')
    drop = drop_plots(t)
    plots = [p for p in t.plots('header') if p not in drop]
    if notes:
        for p in plots:
            if p not in notes and t.n_plots().get(p, 0) == 0:
                out.append([f'{t.name}/d/調査地/{p}', 'P', f'地点 {p} の調査地が注記に無い'])
    symbols = _load(t, 'pref_symbols.tsv')
    if not symbols:
        return out
    sym_pref = {r['symbol']: r['pref'] for r in symbols}
    places = {r['place']: r['pref'] for r in _load(t, 'place_pref.tsv') if r.get('place') and r.get('pref')}
    for d in t.dicts('header'):
        if not is_pref_row(d):
            continue
        for p in plots:
            cur = (d.get(p) or '').strip()
            if not cur or cur in ('-', '—') or p not in notes or cur not in sym_pref:
                continue
            prefs = {pref_of(text, places) for text in notes[p]} - {''}
            if len(prefs) > 1:
                out.append([t.cid('header', d['_row'], p), 'G', f'注記の調査地の県が食い違う ({"・".join(sorted(prefs))})'])
            elif prefs and sym_pref[cur] not in prefs:
                out.append([t.cid('header', d['_row'], p), 'G', f'県名の記号 {cur} ({sym_pref[cur]}) と注記の調査地の県 ({prefs.pop()}) が違う'])
    return out


def collect(t, sites, comp, trace, old_user):
    """1 つの表の矛盾を [cell_id, 区分, 説明] で返す．t は決定の表，sites・comp はその表の出力の行"""
    from rules._lib import species_sets
    out = []
    for row, p, y, s in later_than_source(t):
        out.append([t.cid('header', row, p), 'Y', f'調査年 {y} が出典の年 {s} より後'])
    out += header_checks(t, sites)
    out += pref_checks(t, sites)
    body, once, want = species_sets(t)
    n = t.n_plots()
    row = next((d['_row'] for d in t.dicts('header')
                if d.get('item_ja', '').startswith('出現種数') or 'artenzahl' in d.get('item_de', '').lower()), None)
    for q in sorted(want):
        if n.get(str(q), 0) > 0 or row is None:        # 常在度の列の出現種数は平均などで，比べない
            continue
        got = len(body.get(q, set()) | once.get(q, set()))
        if got != want[q]:
            out.append([t.cid('header', row, str(q)), 'N', f'印字 {want[q]}・読んだ種 {got} ({got - want[q]:+d})'])
    for r in comp:
        if r.get('status') == 'check':
            out.append([r['cell_id'], 'V', r.get('note_read', '')[:120]])
        elif r.get('status') == 'multi':
            out.append([r['cell_id'], 'L', f"階層 {r.get('layer', '')}"])
    later = {c[0] for c in out if c[1] in CHECK_KINDS}
    for r in sites:
        if r.get('status') == 'check' and r['cell_id'] not in later:
            out.append([r['cell_id'], 'S', f"{r.get('item_ja', '')}: {r.get('note_read', '')[:100]}"])
    for key, ids in sorted(trace.judge.items()):
        left = [i for i in ids if i.startswith('L:')]
        if left:
            out.append([t.cid(*key), 'J', ';'.join(left)])
    for cid, d in old_user.items():
        if cid.split('/', 1)[0] == t.name:
            out.append([cid, 'U', f"前回の答え: {d.get('value', '')}"])
    return out


def by_cell(conf):
    """{cell_id の行までの部分: 区分の並び}．行の項目 (@layer など) の矛盾は，その行の全セルに付ける"""
    cells, rows = collections.defaultdict(list), collections.defaultdict(list)
    for cid, kind, _ in conf:
        head, col = cid.rsplit('/', 1)
        (rows if col.startswith('@') and col != '@value' else cells)[head if col.startswith('@') and col != '@value' else cid].append(kind)
    return cells, rows


def fill(rows_out, conf):
    """出力の行の note_conflict に区分の記号を入れる．要確認の区分 (CHECK_KINDS) の行は status を check にする"""
    cells, rows = by_cell(conf)
    for r in rows_out:
        cid = r.get('cell_id', '')
        kinds = list(cells.get(cid, [])) + list(rows.get(cid.rsplit('/', 1)[0], []))
        if kinds:
            r['note_conflict'] = ';'.join(dict.fromkeys(kinds))
            if CHECK_KINDS & set(kinds) and r.get('status') == 'ok':
                r['status'] = 'check'


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir')
    ap.add_argument('--out', default=None, help='decide.py の出力先 (既定: 置き場)')
    a = ap.parse_args(argv)
    path = os.path.join(a.out or a.dir, 'conflicts.tsv')
    if not os.path.exists(path):
        sys.exit(f'無い: {path} (先に decide.py を回す)')
    h, rows, _, _ = read_tsv_raw(path)
    kinds = collections.Counter(r[1] for r in rows)
    tables = collections.defaultdict(collections.Counter)
    for r in rows:
        tables[r[1]][r[0].split('/', 1)[0]] += 1
    print(f'矛盾 {len(rows)} 件 ({path})')
    for k, title in KINDS.items():
        if kinds.get(k):
            top = ', '.join(f'{t} {n}' for t, n in tables[k].most_common(5))
            print(f'  {k} {title}: {kinds[k]} 件 (多い表: {top})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
