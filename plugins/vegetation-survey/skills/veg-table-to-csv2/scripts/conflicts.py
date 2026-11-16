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
"""
import argparse
import collections
import os
import sys

from common import read_side, read_tsv_raw

KINDS = collections.OrderedDict([
    ('N', '出現種数が印字と合わない'), ('V', '値が読めない・自信なし'), ('L', '階層が決まらない'),
    ('S', '表頭・注記の check'), ('J', '引き継ぎの判断が残る'), ('U', '前回のユーザ確認')])


def collect(t, sites, comp, trace, old_user):
    """1 つの表の矛盾を [cell_id, 区分, 説明] で返す．t は決定の表，sites・comp はその表の出力の行"""
    from rules.once import species_sets
    out = []
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
    for r in sites:
        if r.get('status') == 'check':
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
    """出力の行の note_conflict に区分の記号を入れる"""
    cells, rows = by_cell(conf)
    for r in rows_out:
        cid = r.get('cell_id', '')
        kinds = list(cells.get(cid, [])) + list(rows.get(cid.rsplit('/', 1)[0], []))
        if kinds:
            r['note_conflict'] = ';'.join(dict.fromkeys(kinds))


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
