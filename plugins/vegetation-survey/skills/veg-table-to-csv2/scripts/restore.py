"""今のスキル (veg-table-to-csv) の転記を，元の印字に戻す (やり直し用)．

    python scripts/restore.py <置き場>                       # 測るだけ (何も書かない)．戻せる割合と一覧を出す
    python scripts/restore.py <置き場> --report r.tsv        # 断片ごとの判定を TSV に書く
    python scripts/restore.py <置き場> --out <新しい置き場>   # 戻した転記を別の置き場に書く (元は触らない)

今の転記には，規則で直した値と，note に元の印字 (「印字は X」) が入っている．note の断片を型で読み，
決定の決まり (D 規則に移すもの) で直したセルだけを印字に戻す．読み方の決まり (書き写し方) の断片は戻さない．

断片の判定:
  戻せる        note から元の印字が取れ，直した先が今の値と合う (または行の項目で確かめようが無い)
  要確認        元の印字は取れたが，note の「X とした」が今の値と合わない (あとで別の直しが重なったなど)
  個別に見る    注記の地名など，値の一部だけを直したもの (機械では戻さない)
  戻せない      直したと書いてあるが，元の印字が note に無い
  判断          ユーザ確認 (judgments.tsv へ移す対象．元の印字が note にあれば戻せる側に数える)
  読み方        読み方の決まりの断片 (戻す対象でない)
  対象外        直しではない断片 (出現種数の食い違いの記録など)
"""
import argparse
import collections
import os
import re
import shutil
import sys

from common import KINDS, TAB, Table, table_dirs, write_tsv_raw

READ_RULES = {'X7', 'X10', 'X11', 'X12', 'X16', 'X26', 'X27', 'X29', 'X36', 'X48', 'X49', 'X52', 'X53', 'X56'}
MOD = re.compile(r'直し|とした|に直す|へ移|修正した|置き直|入れ替|そろえ')
NOT_MOD = re.compile(r'印字ミスか|印字のまま|読み直しても|今の転記')
PLOT = re.compile(r'^(\d+)\s*[:：]\s*(.*)$', re.S)
RULE = re.compile(r'規則\s*((?:X|K)\d+)')
END = r'(?=\s*[(（]|．|。|$)'
S_NAME = re.compile(r'学名の印字は\s*(?:「(.+?)」|(.+?)' + END + ')')
J_NAME = re.compile(r'和名の印字は\s*(?:「(.+?)」|(.+?)' + END + ')')
LAYER = re.compile(r'階層の印字は\s*([A-Za-z]+\d?(?:[,;・][A-Za-z]+\d?)*)')
ONCE_PLOT = re.compile(r'印字(?:の見出し)?は\s*in\s*(\d+)')
# セルの値は括弧を含む (`I(+)`・`2(1-2)`) ので，値の終わりは「空白のあとの括弧」か句点
CELL = re.compile(r'印字は\s*(.+?)(?=\s+[(（]|．|。|$)')
YEAR = re.compile(r"年の印字は\s*'?(\d{2,4})")
YEAR_HEAD = re.compile(r"^('?)(\d{2,4})(?=\s|$)")
PLACE = re.compile(r'(和文|地名|調査地)の印字は')
DECIDED = re.compile(r'(?:とみて|なので|直して|ので，?)?\s*([^\s．，()（）]+)\s*(?:とした|に直した|に直す|とする)')

Found = collections.namedtuple('Found', 'status kind row col raw rule part')


def classify(kind, row, part, cur):
    """note の断片 1 つを判定する．cur(col) はその行の今の値を返す関数"""
    m = PLOT.match(part)
    plot, text = (m.group(1), m.group(2)) if m else ('', part)
    if not MOD.search(text):
        return None
    rm = RULE.search(text)
    rule = rm.group(1) if rm else ''
    user = 'ユーザ確認' in text
    if rule in READ_RULES:
        return Found('読み方', kind, row, plot or '', '', rule, part)
    if NOT_MOD.search(text) and not user and not rule:
        return Found('対象外', kind, row, '', '', rule, part)
    label = '判断' if user else ''

    def out(status, col, raw):
        return Found((label + ':' if label else '') + status, kind, row, col, raw, rule or ('ユーザ確認' if user else ''), part)

    m = S_NAME.search(text)
    if m and kind in ('body', 'once'):
        return out('戻せる', '@s_name', (m.group(1) or m.group(2)).strip())
    m = J_NAME.search(text)
    if m and kind in ('body', 'once'):
        return out('戻せる', '@j_name', (m.group(1) or m.group(2)).strip())
    m = ONCE_PLOT.search(text)
    if m and kind == 'once':
        return out('戻せる', '@plot', m.group(1))
    if rule == 'X51' and kind in ('body', 'once') and not plot and re.search(r'階層の印字なし|階層 \S+ の欠け', text):
        return out('戻せる', '@layer', '')            # 階層の印字が無いのを規則で補ったもの: 元は空欄
    m = LAYER.search(text)
    if m and kind in ('body', 'once') and not plot:
        return out('戻せる', '@layer', m.group(1).replace(',', ';').replace('・', ';'))
    if PLACE.search(text) or kind == 'notes':
        return out('個別に見る', '@value' if kind == 'notes' else plot, '')
    m = YEAR.search(text)
    if m and plot and kind == 'header':             # 年だけを直した日付: 今の値の年の所だけを印字の年に戻す
        now = cur(plot)
        h = YEAR_HEAD.match(now)
        if not h:
            return out('個別に見る', plot, '')
        return out('戻せる', plot, h.group(1) + m.group(1)[-len(h.group(2)):] + now[h.end():])
    m = CELL.search(text)
    if m and plot and kind in ('body', 'header'):
        raw = m.group(1).strip()
        d = DECIDED.search(text[m.end():])
        now = cur(plot)
        if d and now and d.group(1) != now and d.group(1) not in now:
            return out('要確認', plot, raw)
        return out('戻せる', plot, raw)
    if user:
        return Found('判断:控えから', kind, row, plot, '', 'ユーザ確認', part)
    return out('戻せない', plot, '')


def scan(root):
    found = []
    for tdir in table_dirs(root):
        t = Table(tdir)
        for kind in KINDS:
            h = t.head[kind]
            if 'note' not in h:
                continue
            k = h.index('note')
            for i, r in enumerate(t.rows[kind], 1):
                if len(r) <= k or not r[k].strip():
                    continue

                def cur(col, kind=kind, i=i):
                    try:
                        return t.get(kind, i, col).strip()
                    except KeyError:
                        return ''
                for part in r[k].split(';'):
                    part = part.strip()
                    if part:
                        f = classify(kind, i, part, cur)
                        if f:
                            found.append((t.name, f))
    return found


def scan_list(root, found):
    """<置き場>/auto_list_paren.tsv (note に書かず一覧にだけ記した直し．value が `印字->直した値`) を読む．
    種名 (学名か和名) と階層で本体の行を探し，その地点のセルに結び付ける．note から拾ったセルと重なれば足さない"""
    path = os.path.join(root, 'auto_list_paren.tsv')
    if not os.path.exists(path):
        return []
    from common import read_side
    have = {(name, f.kind, f.row, f.col) for name, f in found}
    tables = {os.path.basename(d): d for d in table_dirs(root)}
    cache, out = {}, []
    for rid, d in read_side(path, key='id').items():
        val = d.get('value', '')
        if '->' not in val:
            continue
        raw, new = [x.strip() for x in val.split('->', 1)]
        name = d.get('table', '').strip()
        part = f"一覧 {rid}: {val} ({d.get('rule', '')}) {d.get('note', '')}"
        if name not in tables:
            out.append((name, Found('戻せない', 'body', 0, d.get('plot', ''), raw, d.get('rule', ''), part)))
            continue
        t = cache.setdefault(name, Table(tables[name]))
        plot, sp, layer = d.get('plot', '').strip(), d.get('species', '').strip(), d.get('layer', '').strip()
        rows = [r for r in t.dicts('body') if sp and sp in (r.get('s_name', ''), r.get('j_name', ''))
                and (not layer or r.get('layer', '') == layer)]
        hit = [r for r in rows if plot in r and r[plot].strip() == new]
        if len(hit) == 1:
            key = (name, 'body', hit[0]['_row'], plot)
            if key not in have:
                out.append((name, Found('戻せる', 'body', hit[0]['_row'], plot, raw, d.get('rule', ''), part)))
        elif any(plot in r and r[plot].strip() == raw for r in rows):
            continue                                  # すでに印字に戻っている (あとで直し直した)
        else:
            out.append((name, Found('要確認', 'body', rows[0]['_row'] if rows else 0, plot, raw, d.get('rule', ''), part)))
    return out


def apply(root, out, found):
    """戻せる断片だけを，out の写しに当てる．(当てた数, 同じセルへ 2 つ目で飛ばした数)"""
    shutil.copytree(os.path.join(root, 'transcripts'), os.path.join(out, 'transcripts'))
    by_table = collections.defaultdict(list)
    for name, f in found:
        if f.status.endswith('戻せる') and not f.status.startswith('判断'):
            by_table[name].append(f)
    done = skipped = 0
    log = []
    for name, items in by_table.items():
        tdir = os.path.join(out, 'transcripts', name)
        t = Table(tdir)
        seen = set()
        for f in items:
            key = (f.kind, f.row, f.col)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            old = t.get(f.kind, f.row, f.col)
            t.set(f.kind, f.row, f.col, f.raw)
            log.append([t.cid(f.kind, f.row, f.col), old, f.raw, f.rule, f.part])
            done += 1
        for kind in KINDS:
            if t.head[kind]:
                nl, trail = t.fmt[kind]
                write_tsv_raw(os.path.join(tdir, kind + '.tsv'), t.head[kind], t.rows[kind], nl, trail)
    write_tsv_raw(os.path.join(out, 'restore_log.tsv'), ['cell_id', 'decided', 'raw', 'rule', 'note'], log)
    return done, skipped


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir')
    ap.add_argument('--out', default=None, help='戻した転記を書く新しい置き場 (無ければ測るだけ)')
    ap.add_argument('--report', default=None, help='断片ごとの判定を書く TSV')
    ap.add_argument('--examples', type=int, default=3, help='判定ごとに出す例の数')
    a = ap.parse_args(argv)
    found = scan(a.dir)
    listed = scan_list(a.dir, found)
    if listed:
        print(f'一覧 (auto_list_paren.tsv) だけに記した直し: {len(listed)} 件を足した')
    found += listed
    by = collections.Counter(f.status for _, f in found)
    rules = collections.defaultdict(collections.Counter)
    ex = collections.defaultdict(list)
    for name, f in found:
        rules[f.status][f.rule or '(規則の番号なし)'] += 1
        if len(ex[f.status]) < a.examples:
            ex[f.status].append(f'{name} {f.kind} 行 {f.row}: {f.part[:110]}')
    total = len(found)
    target = sum(n for s, n in by.items() if s not in ('読み方', '対象外'))
    ok = sum(n for s, n in by.items() if s.endswith('戻せる'))
    print(f'直したことを言う断片 {total}．うち戻す対象 {target} (読み方 {by["読み方"]}・対象外 {by["対象外"]} を除く)')
    for s, n in sorted(by.items(), key=lambda x: -x[1]):
        top = ', '.join(f'{k} {v}' for k, v in rules[s].most_common(6))
        print(f'  {s}: {n}  [{top}]')
        for e in ex[s]:
            print(f'      例: {e}')
    if target:
        print(f'戻せる割合: {ok} / {target} = {100 * ok / target:.1f}% (判断の分を含む)')
    if a.report:
        write_tsv_raw(a.report, ['table', 'status', 'kind', 'row', 'col', 'raw', 'rule', 'note'],
                      [[name, f.status, f.kind, str(f.row), f.col, f.raw, f.rule, f.part] for name, f in found])
        print(f'判定の一覧: {a.report}')
    if a.out:
        if os.path.exists(os.path.join(a.out, 'transcripts')):
            sys.exit(f'すでにある: {a.out}/transcripts (別の置き場を指定する)')
        done, skipped = apply(a.dir, a.out, found)
        print(f'戻した転記: {a.out} (当てたセル {done}・同じセルへの 2 つ目で飛ばした {skipped})．一覧は restore_log.tsv')
    return 0


if __name__ == '__main__':
    sys.exit(main())
