"""固定した転記から，決定の CSV (sites.csv・composition.csv) を作る．何度でも作り直せる．

    python scripts/decide.py <置き場> [--out <出力先>] [--settings rule_settings.tsv] [--soc-default cover]
    python scripts/decide.py --list-rules            # 決定の決まりの一覧
    python scripts/decide.py <置き場> --init-settings # rule_settings.tsv のひな形を書く (全部 yes)

決定 = 転記 (固定) + 読み (readings.tsv) + 規則 (rules/．採否は rule_settings.tsv) + 個別の判断 (judgments.tsv)．
当てる順もこの順．転記のファイルは書き換えない (写しに当てて，今のスキルの to_csv.py で CSV の形にする)．

- readings.tsv (列: cell_id value reader date note): ユーザが読んだ値．AI の読みは note_read に残る．
- judgments.tsv (列: cell_id value id date note): 規則で決まらないセルの判断．id (J001 など) が note_judge に入る．
- rule_settings.tsv (列: rule use param note): use が no の規則は当てない．無ければ全部当てる．
  置き場のものが無ければ 1 つ上のフォルダのもの (全地方で共通) を使う．

出力の列 (今の CSV の note の代わりに，以下の列を持つ):
  cell_id       転記のセルの ID (common.py)．規則で足した行は <表>/d/…
  value_raw     転記 (印字のまま．ユーザの読みがあればその値)
  value_decided 決定の値 (composition だけ．表頭は value)
  source_read   ai / user
  note_read     読みの注 (転記の note．ユーザが読んだセルは AI の読みも)
  note_conflict 矛盾の区分 (conflicts.py が入れる．まだ空)
  note_judge    当てた規則の番号 (D03) と個別の判断の番号 (J001)
  note_modify   何をどう直したか (印字 → 決定．理由)

<出力先>/decisions.tsv に，直したセルの一覧 (cell_id raw decided judge modify) も書く．
"""
import argparse
import collections
import csv
import os
import shutil
import sys
import tempfile

import common
from common import TOKEN, Table, parse_id, read_side, table_dirs, to_csv
import freeze
import rules as rules_pkg

SITE_COLS = ['file', 'region', 'table', 'plot', 'item_ja', 'item_de', 'value', 'unit', 'value_raw', 'source', 'status',
             'cell_id', 'source_read', 'note_read', 'note_conflict', 'note_judge', 'note_modify']
COMP_COLS = ['file', 'region', 'table', 'plot', 'group_ja', 'group_de', 's_name', 'j_name', 'layer', 'cover',
             'sociability', 'constancy', 'value_raw', 'value_decided', 'source', 'status',
             'cell_id', 'source_read', 'note_read', 'note_conflict', 'note_judge', 'note_modify']
OFF = {'no', 'n', '0', 'off', 'false', 'x'}


def load_settings(path):
    """{規則の番号: (使うか, param)}．ファイルが無ければ {} (全部使う)"""
    out = {}
    for rid, d in read_side(path, key='rule').items():
        out[rid] = (d.get('use', 'yes').strip().lower() not in OFF, d.get('param', '').strip())
    return out


def find_settings(root, given):
    if given:
        return given
    for p in (os.path.join(root, 'rule_settings.tsv'), os.path.join(os.path.dirname(os.path.abspath(root)), 'rule_settings.tsv')):
        if os.path.exists(p):
            return p
    return ''


class Trace:
    """セルごとの「誰が読んだか・どの規則や判断で・どう直したか」"""

    def __init__(self):
        self.read = {}                                   # (kind, row, col) -> AI の読み
        self.judge = collections.defaultdict(list)       # (kind, row, col) -> [番号]
        self.modify = collections.defaultdict(list)      # (kind, row, col) -> [説明]

    def keys_for(self, kind, row, col):
        """出力の 1 行に掛かるセル: そのセルと，同じ行の行の項目 (@layer など)"""
        return [k for k in set(self.read) | set(self.judge) | set(self.modify)
                if k[0] == kind and k[1] == row and (k[2] == col or k[2].startswith('@'))]


def apply_side(t, side, trace, kind_of, redundant=None):
    """readings / judgments をこの表に当てる．kind_of は 'read' か 'judge'．当てた数と誤りの一覧を返す．
    判断の値が，規則を当てたあとの値とすでに同じなら「規則と同じ結果の判断」として redundant に入れ，記録には足さない"""
    n, errors = 0, []
    for cid, d in side.items():
        try:
            table, kind, row, col = parse_id(cid)
        except ValueError as e:
            errors.append(str(e))
            continue
        if table != t.name:
            continue
        try:
            old = t.get(kind, row, col)
        except (IndexError, KeyError) as e:
            errors.append(f'{cid}: 転記に無いセル ({e})')
            continue
        new = d.get('value', '')
        key = (kind, row, col)
        if kind_of == 'read':
            trace.read[key] = old
        elif old == new:                                  # 規則がもう同じ値にしている (この判断は要らない)
            if redundant is not None:
                redundant.append([cid, new, d.get('id', ''), ';'.join(trace.judge.get(key, []))])
            continue
        else:
            trace.judge[key].append(d.get('id', '').strip() or 'J?')
            why = d.get('note', '').strip()
            trace.modify[key].append(f'{old or "(空)"} → {new or "(空)"}' + (f'．{why}' if why else ''))
        t.set(kind, row, col, new)
        n += 1
    return n, errors


def apply_rules(t, rule_list, settings, trace, counts):
    for r in rule_list:
        use, param = settings.get(r.id, (True, ''))
        if not use:
            continue
        for ch in list(r.fn(t, param)):
            old = t.get(ch.kind, ch.row, ch.col)
            if old == ch.new:
                continue
            key = (ch.kind, ch.row, ch.col)
            if trace.judge[key]:                          # 2 つ目の規則が同じセルに当たった (順序で結果が変わる)
                counts['!重なり'] += 1
            trace.judge[key].append(r.id)
            trace.modify[key].append(f'{old or "(空)"} → {ch.new or "(空)"}．{ch.why}')
            t.set(ch.kind, ch.row, ch.col, ch.new)
            counts[r.id] += 1


def keep_arabic_parse(raw, n_plots=0, keep_arabic=False):
    """to_csv.parse_value の中の規則 X8 (算用数字 → ローマ数字) を止める．規則 D03 が先に当てている"""
    return _PARSE(raw, n_plots, True)


_PARSE = to_csv.parse_value


def to_rows(t, t_read, trace, soc_default):
    """決定の表 t を to_csv.py に通し，行をセルの ID に結び付けて列を足す"""
    tmp = tempfile.mkdtemp(prefix='csv2_')
    try:
        tdir = os.path.join(tmp, t.name)
        t.write_to(tdir, note_token=True)
        to_csv.SOC_DEFAULT = soc_default
        to_csv.parse_value = keep_arabic_parse
        try:
            sites, comp = to_csv.build(tdir)
        finally:
            to_csv.parse_value = _PARSE
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for rows, is_comp in ((sites, False), (comp, True)):
        for r in rows:
            note = r.pop('note', '') or ''
            m = TOKEN.search(note)
            note = TOKEN.sub('', note).strip('; ')
            r.update(source_read='ai', note_read=note, note_conflict='', note_judge='', note_modify='')
            if not m:                                     # 表題・列の種類など，行に結び付かない行
                r['cell_id'] = f"{t.name}/d/{r.get('item_ja', '')}/{r.get('plot', '')}".rstrip('/')
                if is_comp:
                    r['value_decided'] = r.get('value_raw', '')
                continue
            kind, row = common.LETTER[m.group(1)], int(m.group(2))
            if kind in ('body', 'header'):
                col = r.get('plot', '')
            elif kind == 'once':
                col = '@value'
            else:
                col = r.get('plot', '') or '@value'
            r['cell_id'] = t.cid(kind, row, col)
            if kind in ('body', 'header', 'once'):
                r['value_raw'] = t_read.get(kind, row, col)
                if is_comp:
                    r['value_decided'] = t.get(kind, row, col)
            elif is_comp:
                r['value_decided'] = r.get('value_raw', '')
            cell_col = '@value' if kind == 'notes' else col
            keys = sorted(trace.keys_for(kind, row, cell_col))
            if any(k in trace.read for k in keys):
                r['source_read'] = 'user'
                ai = '; '.join(f'AI の読み: {trace.read[k] or "(空)"}' for k in keys if k in trace.read)
                r['note_read'] = '; '.join(x for x in (note, ai) if x)
            r['note_judge'] = ';'.join(j for k in keys for j in trace.judge.get(k, []))
            r['note_modify'] = '; '.join(x for k in keys for x in trace.modify.get(k, []))
    return sites, comp


def write_csv(path, cols, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator='\n', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def decide(root, out=None, settings_path='', soc_default='one', allow_unfrozen=False, tables=None):
    """決定を作る．(sites, comp, 件数の表, 誤りの一覧) を返す"""
    rule_list = rules_pkg.load_all()
    settings = load_settings(find_settings(root, settings_path))
    readings = read_side(os.path.join(root, 'readings.tsv'))
    judgments = read_side(os.path.join(root, 'judgments.tsv'))
    changed, loose = freeze.check(root)
    errors = [f'固定後に書き換えられた表: {n} (freeze.py --check．読みの直しは readings.tsv に書く)' for n in changed]
    if loose and not allow_unfrozen:
        errors.append(f'固定していない表が {len(loose)} ある ({", ".join(loose[:5])}…)．freeze.py で固定するか --allow-unfrozen')
    known = {os.path.basename(d) for d in table_dirs(root)}
    for name, side in (('readings.tsv', readings), ('judgments.tsv', judgments)):
        for cid in side:
            try:
                if parse_id(cid)[0] not in known:
                    errors.append(f'{name}: {cid} の表が無い')
            except ValueError as e:
                errors.append(f'{name}: {e}')
    counts = collections.Counter()
    sites, comp, log, redundant = [], [], [], []
    if errors:
        return sites, comp, counts, errors
    to_csv.NAMELESS.clear()
    for tdir in table_dirs(root):
        if tables and os.path.basename(tdir) not in tables:
            continue
        t = Table(tdir)
        trace = Trace()
        n, err = apply_side(t, readings, trace, 'read')
        counts['読み (readings)'] += n
        errors += err
        t_read = t.copy()
        apply_rules(t, rule_list, settings, trace, counts)
        n, err = apply_side(t, judgments, trace, 'judge', redundant)
        counts['個別の判断 (judgments)'] += n
        errors += err
        s, c = to_rows(t, t_read, trace, soc_default)
        sites += s
        comp += c
        for key in sorted(set(trace.judge) | set(trace.read)):
            if not trace.judge.get(key) and key not in trace.read:
                continue
            log.append([t.cid(*key), t_read.get(*key), t.get(*key), ';'.join(trace.judge.get(key, [])),
                        '; '.join(trace.modify.get(key, [])) or ('ユーザの読み' if key in trace.read else '')])
    if errors:
        return sites, comp, counts, errors
    out = out or root
    os.makedirs(out, exist_ok=True)
    write_csv(os.path.join(out, 'sites.csv'), SITE_COLS, sites)
    write_csv(os.path.join(out, 'composition.csv'), COMP_COLS, comp)
    common.write_tsv_raw(os.path.join(out, 'decisions.tsv'), ['cell_id', 'raw', 'decided', 'judge', 'modify'], log)
    # 規則がもう同じ値にしている判断 (消せる)．規則を関数に移した進み具合の目安
    common.write_tsv_raw(os.path.join(out, 'judgments_redundant.tsv'), ['cell_id', 'value', 'id', 'rule'], redundant)
    counts['判断のうち規則と同じ結果 (消せる)'] = len(redundant)
    left =collections.Counter(d.get('id', '') for cid, d in judgments.items()) - collections.Counter(r[2] for r in redundant)
    for jid, n in sorted(left.items()):
        if n:
            counts[f'  残る判断 {jid}'] = n
    return sites, comp, counts, errors


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir', nargs='?')
    ap.add_argument('--out', default=None, help='出力先 (既定: 置き場)')
    ap.add_argument('--settings', default='', help='rule_settings.tsv (既定: 置き場か 1 つ上のフォルダ)')
    ap.add_argument('--soc-default', choices=('one', 'cover'), default='one', help='群度の印字が無いときの補い方 (to_csv.py と同じ)')
    ap.add_argument('--allow-unfrozen', action='store_true', help='固定していない表があっても作る (試すとき)')
    ap.add_argument('--table', action='append', default=[], help='この表だけ (何度でも)')
    ap.add_argument('--prune-judgments', action='store_true',
                    help='規則と同じ結果になった引き継ぎの判断 (id が L: で始まる行) を judgments.tsv から外す')
    ap.add_argument('--list-rules', action='store_true', help='決定の決まりの一覧を出して終わる')
    ap.add_argument('--init-settings', action='store_true', help='置き場に rule_settings.tsv のひな形を書く')
    a = ap.parse_args(argv)
    rule_list = rules_pkg.load_all()
    if a.list_rules:
        for r in rule_list:
            print(f'{r.id}  [{r.group}] {r.title}' + (f' (今の規則 {r.old})' if r.old else ''))
        return 0
    if not a.dir:
        ap.error('置き場が要る')
    if a.init_settings:
        p = os.path.join(a.dir, 'rule_settings.tsv')
        if os.path.exists(p):
            sys.exit(f'すでにある: {p}')
        common.write_tsv_raw(p, ['rule', 'use', 'param', 'note'], [[r.id, 'yes', '', r.title] for r in rule_list])
        print(f'書いた: {p}')
        return 0
    sites, comp, counts, errors = decide(a.dir, a.out, a.settings, a.soc_default, a.allow_unfrozen, a.table)
    for e in errors:
        print('!! ' + e)
    if errors:
        print(f'!! {len(errors)} 件の誤り．CSV は書いていない')
        return 2
    print(f'決定: sites {len(sites)} 行・composition {len(comp)} 行 → {a.out or a.dir}')
    for k in sorted(counts):
        title = next((r.title for r in rule_list if r.id == k), '')
        print(f'  {k}: {counts[k]} セル' + (f'  {title}' if title else ''))
    if a.prune_judgments:
        out_dir = a.out or a.dir
        gone = {r['cell_id'] for r in read_side(os.path.join(out_dir, 'judgments_redundant.tsv')).values()
                if r.get('id', '').startswith('L:')}
        p = os.path.join(a.dir, 'judgments.tsv')
        h, rows, nl, trail = common.read_tsv_raw(p)
        keep = [r for r in rows if r and r[0] not in gone]
        common.write_tsv_raw(p, h, keep, nl, trail)
        print(f'judgments.tsv から，規則と同じ結果の引き継ぎの判断 (L:) {len(rows) - len(keep)} 行を外した (残り {len(keep)} 行)')
    if counts.get('!重なり'):
        print(f'[注意] 1 つのセルに 2 つ以上の規則が当たった: {counts["!重なり"]} 件 (decisions.tsv の judge に番号が並ぶ)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
