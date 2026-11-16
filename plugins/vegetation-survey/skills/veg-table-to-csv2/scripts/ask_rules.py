"""規則ごとの件数と例を 1 枚の HTML にして，規則の採否をまとめて聞く．答えは rule_settings.tsv などに当てる．

    python scripts/ask_rules.py <置き場> <出力.html> [--out <decide.py の出力先>] [--examples 8]
    python scripts/ask_rules.py <置き場> --apply <回答.json>

先に decide.py を回しておく (decisions.tsv・conflicts.tsv を読む)．個別のセルではなく，規則の単位で聞く:

- 決定の決まり (D 規則): 当てたセルの数・表の数と例 (印字 → 決定)．「採用 / 不採用 / 条件を変える (メモに)」
- 引き継ぎの判断 (L:<今の規則>): まだ関数になっていない今のスキルの規則で直したセル．
  「このセルだけ引き継ぐ / 引き継がない (印字のまま) / 個別に見直す / 規則にする」
- 前回のユーザ確認 (U): 決定に引き継いでいない前回の答え．「引き継がない (今のまま) / このセルだけ引き継ぐ / 個別に見直す / 規則にする」

**「引き継ぐ」は規則にはならない**．そのセルの値を judgments.tsv に持ち続けるだけで，ほかの表・これから読む表には効かない．
規則にするには，条件を関数に書く (rules/) か，対応の表 (name_fixes.tsv のようなもの) を作る．

--apply は回答 ({id: {choice, memo}}) を当てる:
- D 規則: rule_settings.tsv の use を yes (採用) / no (不採用) にする (条件を変えるは yes のまま．メモを書き出す)．
  --global を付けると 1 つ上のフォルダ (全地方で共通) に書く
- 引き継ぎの判断: 「引き継がない」の規則の行を judgments.tsv から外す
- 前回のユーザ確認: 「引き継ぐ」なら old_user_judgments.tsv の行を judgments.tsv に足す
「条件を変える」「個別に見直す」「規則にする」とメモは rule_answers_todo.tsv に書き出す (あとで規則の直しや確認の対象にする)．
"""
import argparse
import collections
import html
import json
import os
import sys

import common
from common import Table, parse_id, read_side, read_tsv_raw, write_tsv_raw
import rules as rules_pkg

CSS = """
:root{--bg:#fafafa;--fg:#222;--card:#fff;--line:#ccc;--acc:#0a5}
@media (prefers-color-scheme:dark){:root{--bg:#1c1c1c;--fg:#eee;--card:#262626;--line:#555;--acc:#4c8}}
body{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,'Yu Gothic',sans-serif;margin:0 auto;padding:16px;max-width:1100px}
#bar{position:sticky;top:0;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);z-index:2}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:16px 0}
h2{font-size:17px;margin:0 0 4px}h3{margin:28px 0 0;padding:4px 8px;border-left:5px solid var(--acc);font-size:16px}
.n{font-size:13px;opacity:.8;margin:0 0 6px}.tw{overflow-x:auto}
table{border-collapse:collapse;font-size:13px}th,td{border:1px solid var(--line);padding:2px 8px;text-align:left;white-space:nowrap}
td.w{white-space:normal;min-width:16em}
.ans{margin-top:8px;display:flex;flex-direction:column;gap:4px}
input[type=text]{padding:3px 6px;border:1px solid var(--line);border-radius:4px;background:var(--bg);color:var(--fg);width:32em;max-width:100%}
button{padding:8px 16px;border:0;border-radius:6px;background:var(--acc);color:#fff;font-size:15px;cursor:pointer}
"""
JS = """
const KEY='ask_rules:'+document.title;
let st={};try{st=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function save(){localStorage.setItem(KEY,JSON.stringify(st));
 document.getElementById('n').textContent=Object.values(st).filter(v=>v.choice).length}
document.querySelectorAll('section.card').forEach(c=>{const id=c.dataset.id;const v=st[id]||{};
 c.querySelectorAll('input[type=radio]').forEach(r=>{if(v.choice===r.value)r.checked=true;
  r.addEventListener('change',()=>{st[id]=Object.assign(st[id]||{},{choice:r.value});save()})});
 const m=c.querySelector('input.m');m.value=v.memo||'';
 m.addEventListener('input',()=>{st[id]=Object.assign(st[id]||{},{memo:m.value});save()})});
document.getElementById('dl').addEventListener('click',()=>{const out={};
 document.querySelectorAll('section.card').forEach(c=>{const v=st[c.dataset.id]||{};
  out[c.dataset.id]={choice:v.choice||'',memo:v.memo||''}});
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,1)],{type:'application/json'}));
 a.download=FNAME;a.click()});
save();
"""
OPTIONS = {
    'D': [('a', '採用 (規則どおり直す)'), ('b', '不採用 (印字のままにする)'), ('c', '条件を変える (どう変えるかをメモに)')],
    # 引き継ぎ: a は「このセルだけ」の判断として残る (規則にはならない．ほかの表・これから読む表には効かない)．
    # 規則にしたいときは d (条件や対応の表を作る作業が要る)
    'L': [('a', 'このセルだけ今の判断を引き継ぐ (規則にはならない．ほかの表には効かない)'),
          ('b', '引き継がない (印字のままにする)'),
          ('c', '個別に見直す (確認の対象にする)'),
          ('d', '規則にする (どういう条件で直すかをメモに．関数か対応の表を作る)')],
    'U': [('a', '引き継がない (今のまま．印字のままにする)'),
          ('b', 'このセルだけ前回の答えを引き継ぐ (規則にはならない)'),
          ('c', '個別に見直す (確認の対象にする)'),
          ('d', '規則にする (どういう条件で直すかをメモに)')],
}


def cell_label(tables, root, cid):
    """セルの ID を人が読める場所の名前にする (表・種名や項目名・地点)"""
    name, kind, row, col = parse_id(cid)
    if name not in tables:
        tables[name] = Table(os.path.join(root, 'transcripts', name))
    t = tables[name]
    try:
        if kind in ('body', 'once'):
            who = t.get(kind, row, '@j_name') or t.get(kind, row, '@s_name')
            layer = t.get(kind, row, '@layer') if 'layer' in t.head[kind] else ''
            where = f'地点 {col}' if not col.startswith('@') else {'@layer': '階層', '@s_name': '学名', '@j_name': '和名',
                                                                 '@plot': '1 回出現の地点', '@note': 'note'}.get(col, col)
            return name, f"{who}{(' ' + layer) if layer else ''}", where
        if kind == 'header':
            return name, t.get(kind, row, '@item_ja'), f'地点 {col}' if not col.startswith('@') else col
        return name, t.get(kind, row, '@item_ja'), f"地点 {t.get(kind, row, '@plot')}"
    except (IndexError, KeyError):
        return name, '', col


def build(root, out_dir, n_examples):
    """[(id, 種類, 題, 件数の文, [例の行])]"""
    _, rows, _, _ = read_tsv_raw(os.path.join(out_dir, 'decisions.tsv'))
    rule_list = {r.id: r for r in rules_pkg.load_all()}
    by = collections.defaultdict(list)
    for cid, raw, decided, judge, modify in ((r + [''] * 5)[:5] for r in rows):
        for j in judge.split(';'):
            if j:
                by[j].append((cid, raw, decided, modify))
    tables, items = {}, []

    def examples(cells, every=False):
        """every なら同じ直し方もまとめず，全部のセルを並べる (引き継ぎの判断・前回のユーザ確認は 1 件ずつ見るため)"""
        seen, out = set(), []
        for cid, raw, decided, modify in cells:           # 例は表をばらして，同じ直し方の重なりを避ける
            name, who, where = cell_label(tables, root, cid)
            key = (name, raw, decided)
            if (key in seen and not every) or cid.endswith('/@note'):
                continue
            seen.add(key)
            out.append([name, who, where, raw or '(空)', decided or '(空)'])
            if len(out) >= n_examples and not every:
                break
        return out

    def count(cells):
        cells = [c for c in cells if not c[0].endswith('/@note')]
        return f'{len(cells)} セル・{len({c[0].split("/", 1)[0] for c in cells})} 表'

    for rid in sorted(k for k in by if k in rule_list):
        r = rule_list[rid]
        items.append((rid, 'D', f'{rid}　{r.title}', f'[{r.group}] 今の規則 {r.old or "-"}．{count(by[rid])}', examples(by[rid])))
    for rid in sorted(k for k in rule_list if k not in by):
        r = rule_list[rid]
        items.append((rid, 'D', f'{rid}　{r.title}', f'[{r.group}] 今の規則 {r.old or "-"}．この置き場では当たったセルが無い', []))
    for jid in sorted(k for k in by if k.startswith('L:')):
        items.append((jid, 'L', f'今のスキルの規則 {jid[2:]} で直したセル (関数になっていない)', count(by[jid]), examples(by[jid], every=True)))
    old = read_side(os.path.join(root, 'old_user_judgments.tsv'))
    if old:
        cells = []
        for cid, d in old.items():
            try:
                raw = cell_label(tables, root, cid) and tables[parse_id(cid)[0]].get_id(cid)
            except (IndexError, KeyError):
                raw = ''
            cells.append((cid, raw, d.get('value', ''), d.get('note', '')))
        items.append(('U', 'U', '前回のユーザ確認 (決定に引き継いでいない)', count(cells) + '．「決定」の欄は前回の答え', examples(cells, every=True)))
    return items


def write_html(items, path, title):
    e = html.escape
    parts, prev = [], None
    heads = {'D': '決定の決まり (規則)', 'L': '引き継ぎの判断 (規則になっていない今の直し)', 'U': '前回のユーザ確認'}
    for iid, kind, name, n, ex in items:
        if kind != prev:
            parts.append(f'<h3>{e(heads[kind])}</h3>')
            prev = kind
        tr = ''.join('<tr>' + ''.join(f'<td>{e(str(c))}</td>' for c in row) + '</tr>' for row in ex)
        table = (f'<div class="tw"><table><tr><th>表</th><th>種名・項目</th><th>場所</th><th>印字</th><th>決定</th></tr>{tr}</table></div>'
                 if ex else '')
        radios = ''.join(f'<label><input type="radio" name="{e(iid)}" value="{v}"> {e(label)}</label>' for v, label in OPTIONS[kind])
        parts.append(f'<section class="card" data-id="{e(iid)}"><h2>{e(name)}</h2><p class="n">{e(n)}</p>{table}'
                     f'<div class="ans">{radios}<input type="text" class="m" placeholder="メモ (任意)"></div></section>')
    fname = 'rule_answers.json'
    page = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body>'
            f'<div id="bar"><b>{e(title)} ({len(items)} 件)</b>　回答済み <span id="n">0</span> / {len(items)}　'
            f'<button id="dl">回答を JSON で保存</button></div>'
            f'<p>規則ごとに，当てたセルの数と例 (印字 → 決定) を並べています．個別のセルではなく，規則として採るかを選んでください．'
            f'入力は自動で保存されます．回答は「回答を JSON で保存」で {fname} として落ちます．</p>'
            f'{"".join(parts)}<script>const FNAME={json.dumps(fname)};{JS}</script></body></html>')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(page)


def apply(root, answers_path, to_parent=False):
    with open(answers_path, encoding='utf-8-sig') as f:
        ans = json.load(f)
    rule_list = rules_pkg.load_all()
    sp = os.path.join(os.path.dirname(os.path.abspath(root)) if to_parent else root, 'rule_settings.tsv')
    cur = {rid: d for rid, d in read_side(sp, key='rule').items()}
    todo, log = [], []
    rows = []
    for r in rule_list:
        d = cur.get(r.id, {'rule': r.id, 'use': 'yes', 'param': '', 'note': r.title})
        a = ans.get(r.id) or {}
        if a.get('choice') == 'a':
            d['use'] = 'yes'
        elif a.get('choice') == 'b':
            d['use'] = 'no'
            log.append(f'{r.id}: 不採用')
        elif a.get('choice') == 'c':
            todo.append([r.id, '条件を変える', a.get('memo', '')])
        if a.get('memo') and a.get('choice') != 'c':
            todo.append([r.id, 'メモ', a['memo']])
        rows.append([d.get('rule', r.id), d.get('use', 'yes'), d.get('param', ''), d.get('note', '')])
    write_tsv_raw(sp, ['rule', 'use', 'param', 'note'], rows)
    jp = os.path.join(root, 'judgments.tsv')
    if os.path.exists(jp):
        h, jrows, nl, trail = read_tsv_raw(jp)
        drop = {k for k, a in ans.items() if k.startswith('L:') and (a or {}).get('choice') == 'b'}
        keep = [r for r in jrows if not (len(r) > 2 and r[2] in drop)]
        if len(keep) != len(jrows):
            log.append(f'引き継がない旧規則 {sorted(drop)}: judgments.tsv から {len(jrows) - len(keep)} 行を外した')
        user = ans.get('U') or {}
        if user.get('choice') == 'b':
            _, urows, _, _ = read_tsv_raw(os.path.join(root, 'old_user_judgments.tsv'))
            have = {r[0] for r in keep}
            add = [r for r in urows if r and r[0] not in have]
            keep += add
            log.append(f'前回のユーザ確認 {len(add)} 行を judgments.tsv に足した')
        write_tsv_raw(jp, h, keep, nl, trail)
    for k, a in ans.items():
        if (k.startswith('L:') or k == 'U') and (a or {}).get('choice') == 'c':
            todo.append([k, '個別に見直す', a.get('memo', '')])
        elif (k.startswith('L:') or k == 'U') and (a or {}).get('choice') == 'd':
            todo.append([k, '規則にする', a.get('memo', '')])
        elif (k.startswith('L:') or k == 'U') and (a or {}).get('memo'):
            todo.append([k, 'メモ', a['memo']])
    if todo:
        write_tsv_raw(os.path.join(root, 'rule_answers_todo.tsv'), ['id', 'what', 'memo'], todo)
    return log, todo


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir')
    ap.add_argument('html', nargs='?')
    ap.add_argument('--out', default=None, help='decide.py の出力先 (既定: 置き場)')
    ap.add_argument('--examples', type=int, default=8, help='規則ごとの例の数')
    ap.add_argument('--title', default=None)
    ap.add_argument('--apply', default=None, metavar='回答.json', help='回答を rule_settings.tsv などに当てる')
    ap.add_argument('--carry', default=None, metavar='回答.json', help='答え済みの項目を外し，未回答だけの HTML を作る')
    ap.add_argument('--global', dest='to_parent', action='store_true',
                    help='--apply のとき，rule_settings.tsv を 1 つ上のフォルダ (全地方で共通) に書く')
    a = ap.parse_args(argv)
    if a.apply:
        log, todo = apply(a.dir, a.apply, a.to_parent)
        for m in log:
            print('  ' + m)
        print(f'rule_settings.tsv を書いた (決定は decide.py で作り直す)．あとで見るもの {len(todo)} 件'
              + (' → rule_answers_todo.tsv' if todo else ''))
        return 0
    if not a.html:
        ap.error('出力の HTML が要る')
    out_dir = a.out or a.dir
    if not os.path.exists(os.path.join(out_dir, 'decisions.tsv')):
        sys.exit(f'無い: {out_dir}/decisions.tsv (先に decide.py を回す)')
    items = build(a.dir, out_dir, a.examples)
    if a.carry:                                           # 答え済みの項目を外し，未回答だけを残す
        with open(a.carry, encoding='utf-8-sig') as f:
            done = {k for k, v in json.load(f).items() if (v or {}).get('choice')}
        items = [it for it in items if it[0] not in done]
        print(f'--carry: 答え済み {len(done)} 件を外した')
    title =a.title or f'規則の確認 ({os.path.basename(os.path.normpath(a.dir))})'
    write_html(items, a.html, title)
    print(f'{len(items)} 件 → {a.html} (回答の保存名 rule_answers.json)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
