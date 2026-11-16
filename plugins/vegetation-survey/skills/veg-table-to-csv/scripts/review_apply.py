"""確認の HTML の回答 (JSON) を，選択肢に書いた操作 (actions) のとおりに転記へ当てる．

    python scripts/review_apply.py <置き場> <項目.items.json> <回答.json> [<回答.json> ...] [--date 2026-11-16] [--dry-run]

`review_html.py` は HTML と一緒に項目の一覧 (`<出力>.items.json`．`--split` なら `<置き場>/review_items.json`) を書く．
項目の選択肢に `actions` があれば，選ばれた選択肢の操作を順に行い，項目の `target` の行に
「ユーザ確認 <日付>: <選択肢の文>」を書き，その行の check を外す (actions が無い選択肢は書くだけ．「今の転記でよい」など)．
「判断できない」(skip)・未回答は何もしない (`review_html.py --carry` で次の確認に回す)．

項目の `target` と操作の `table`・`file`・`match` で行を指す．`match` は列名と値 (例 `{"j_name": "マメヅタ"}`) で，
1 行だけに当たらなければ止める (`"all": true` なら当たった行すべて)．値を入力する選択肢 (`val`) の操作は `{value}` が入力に置き換わる．

操作 (op):
- `set`: `{"op": "set", "col": "8", "from": "+", "to": "・"}` セルを書き換える (`from` が今の値と違えば止める)
- `note`: `{"op": "note", "plot": "8", "text": "…"}` note に「ユーザ確認 <日付>: …」を足す (plot があれば「8: …」)
- `uncheck`: `{"op": "uncheck", "plot": "8"}` note の「8: check」を外し，status 列があれば ok にする
- `layer`: `{"op": "layer", "plot": "13", "layer": "B1"}` セルごとの階層「13: 層 B1」を note に足す (to_csv.py 0.5.43)
- `move`: `{"op": "move", "to": "18"}` 1 回出現の行 (once.tsv) の地点を変える
- `drop_plot`: `{"op": "drop_plot", "plot": "31", "note": "…"}` meta.tsv の drop_plots に足す (列は残し，CSV から外す)
- `add_row`: `{"op": "add_row", "row": {"plot": "7", "item_ja": "調査地", …}}` 行を末尾に足す (notes.tsv など)
- `delete_row`: 当たった行を消す

直す前の転記を `<置き場>/review_backup_<日時>_answers/` に写す．直したあとは `to_csv.py` と `check.py` を流す．
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys


class Tsv:
    """転記の TSV．改行 (CRLF/LF) と末尾の改行を保ったまま書き戻す"""

    def __init__(self, path):
        self.path = path
        raw = open(path, encoding='utf-8-sig', newline='').read()
        self.nl = '\r\n' if '\r\n' in raw else '\n'
        self.trail = raw.endswith(('\n', '\r\n'))
        lines = raw.replace('\r\n', '\n').rstrip('\n').split('\n')
        self.h = lines[0].split('\t')
        self.rows = [l.split('\t') for l in lines[1:]]
        self.dirty = False

    def save(self):
        text = self.nl.join(['\t'.join(self.h)] + ['\t'.join(r) for r in self.rows]) + (self.nl if self.trail else '')
        with open(self.path, 'w', encoding='utf-8', newline='') as f:
            f.write(text)

    def col(self, name):
        if name not in self.h:
            raise KeyError(f'{self.path}: 列 {name} が無い')
        return self.h.index(name)

    def get(self, r, name):
        k = self.col(name)
        return r[k] if k < len(r) else ''

    def put(self, r, name, v):
        k = self.col(name)
        while len(r) <= k:
            r.append('')
        r[k] = v
        self.dirty = True

    def find(self, match, many=False):
        hit = [r for r in self.rows if all(self.get(r, k) == str(v) for k, v in match.items())]
        if not hit or (len(hit) > 1 and not many):
            raise LookupError(f'{self.path}: {match} に当たる行が {len(hit)} 行')
        return hit


class Applier:
    def __init__(self, root, date, dry=False):
        self.root, self.date, self.dry = root, date, dry
        self.files = {}
        self.log = []

    def tsv(self, table, kind):
        key = (table, kind)
        if key not in self.files:
            self.files[key] = Tsv(os.path.join(self.root, 'transcripts', table, kind + '.tsv'))
        return self.files[key]

    def rows(self, spec, base=None):
        spec = dict(base or {}, **spec)
        t = self.tsv(spec['table'], spec.get('file', 'body'))
        return t, t.find(spec.get('match', {}), spec.get('all', False))

    def add_note(self, t, r, text, plot=None):
        part = f'{plot}: ユーザ確認 {self.date}: {text}' if plot else f'ユーザ確認 {self.date}: {text}'
        n = t.get(r, 'note')
        t.put(r, 'note', (n + '; ' + part) if n else part)

    @staticmethod
    def uncheck(t, r, plot=None):
        n = t.get(r, 'note')
        if plot:
            n = re.sub(r'(^|;\s*)(%s\s*[:：]\s*)check[\s:：．]*' % re.escape(str(plot)), r'\1\2', n)
        else:
            n = re.sub(r'(^|;\s*)check[\s:：．]*', r'\1', n)
        n = re.sub(r'\s*[(（]\s*check\s*[)）]', '', n).replace('(check．', '(')
        t.put(r, 'note', n)
        if 'status' in t.h and t.get(r, 'status') == 'check':
            t.put(r, 'status', 'ok')

    def run(self, op, target, value):
        op = json.loads(json.dumps(op).replace('{value}', value.replace('\\', '\\\\').replace('"', '\\"')))
        kind = op['op']
        if kind == 'drop_plot':
            self.drop_plot(op.get('table') or target['table'], str(op['plot']), op.get('note', ''))
            return
        if kind == 'add_row':
            t = self.tsv(op.get('table') or target['table'], op.get('file', 'notes'))
            row = [''] * len(t.h)
            for k, v in op['row'].items():
                row[t.col(k)] = str(v)
            t.rows.append(row)
            t.dirty = True
            self.log.append(f'{t.path}: 行を足した {op["row"]}')
            return
        t, hit = self.rows({k: v for k, v in op.items() if k in ('table', 'file', 'match', 'all')}, target)
        for r in hit:
            if kind == 'set':
                cur = t.get(r, op['col'])
                if 'from' in op and cur != op['from']:
                    raise ValueError(f'{t.path}: {op["col"]} の今の値 {cur!r} が {op["from"]!r} と違う')
                t.put(r, op['col'], op['to'])
                self.log.append(f'{t.path}: [{op["col"]}] {cur!r} -> {op["to"]!r}')
            elif kind == 'note':
                self.add_note(t, r, op['text'], op.get('plot'))
            elif kind == 'uncheck':
                self.uncheck(t, r, op.get('plot'))
            elif kind == 'layer':
                n = t.get(r, 'note')
                part = f'{op["plot"]}: 層 {op["layer"]}'
                t.put(r, 'note', (n + '; ' + part) if n else part)
                self.log.append(f'{t.path}: 地点 {op["plot"]} の階層を {op["layer"]} に')
            elif kind == 'move':
                old = t.get(r, 'plot')
                t.put(r, 'plot', str(op['to']))
                self.log.append(f'{t.path}: 地点 {old} -> {op["to"]}')
            elif kind == 'delete_row':
                t.rows.remove(r)
                t.dirty = True
                self.log.append(f'{t.path}: 行を消した')
            else:
                raise ValueError(f'知らない操作: {kind}')

    def drop_plot(self, table, plot, note):
        t = self.tsv(table, 'meta')
        kv = {t.get(r, 'key'): r for r in t.rows}
        if 'drop_plots' in kv:
            cur = [x for x in t.get(kv['drop_plots'], 'value').split(',') if x]
            t.put(kv['drop_plots'], 'value', ','.join(sorted(set(cur) | {plot}, key=lambda x: int(x) if x.isdigit() else 0)))
        else:
            t.rows.append(['drop_plots', plot])
            t.dirty = True
        if note:
            if 'drop_plots_note' in kv:
                t.put(kv['drop_plots_note'], 'value', note)
            else:
                t.rows.append(['drop_plots_note', note])
                t.dirty = True
        self.log.append(f'{table}: 地点 {plot} を drop_plots に足した')

    def apply_item(self, item, ans):
        choice = (ans or {}).get('choice', '')
        if choice in ('', 'skip'):
            return 'skip'
        opt = next((o for o in item.get('options', []) if o.get('value') == choice), None)
        if opt is None:
            raise LookupError(f'{item["id"]}: 選択肢 {choice} が項目に無い')
        value = (ans.get('value') or '').strip()
        label = value if opt.get('input') and value else re.sub(r'\s+', ' ', opt.get('label', choice))
        target = item.get('target')
        for op in opt.get('actions', []):
            self.run(op, target or {}, value)
        if target and target.get('match'):
            t, hit = self.rows({}, target)
            memo = (ans.get('memo') or '').strip()
            for r in hit:
                self.uncheck(t, r, target.get('plot'))
                self.add_note(t, r, label + (f' (メモ: {memo})' if memo else ''), target.get('plot'))
        return 'done' if (opt.get('actions') or target) else 'no-op'

    def backup_and_save(self):
        dirty = [t for t in self.files.values() if t.dirty]
        if self.dry or not dirty:
            return None
        bk = os.path.join(self.root, 'review_backup_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S') + '_answers')
        for t in dirty:
            rel = os.path.relpath(t.path, os.path.join(self.root, 'transcripts'))
            os.makedirs(os.path.dirname(os.path.join(bk, rel)), exist_ok=True)
            shutil.copy2(t.path, os.path.join(bk, rel))
        for t in dirty:
            t.save()
        return bk


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir', help='置き場 (transcripts/ のあるフォルダ)')
    ap.add_argument('items', help='review_html.py が書いた項目の一覧 (*.items.json)')
    ap.add_argument('answers', nargs='+', help='回答の JSON (いくつでも．後のファイルの回答が勝つ)')
    ap.add_argument('--date', default=datetime.date.today().isoformat(), help='note に書く日付 (既定: 今日)')
    ap.add_argument('--dry-run', action='store_true', help='書かずに，当たるかだけを確かめる')
    a = ap.parse_args(argv)
    with open(a.items, encoding='utf-8-sig') as f:
        items = {it['id']: it for it in json.load(f)}
    answers = {}
    for p in a.answers:
        with open(p, encoding='utf-8-sig') as f:
            answers.update(json.load(f))
    ap_ = Applier(a.dir, a.date, a.dry_run)
    count = {'done': 0, 'no-op': 0, 'skip': 0}
    errors, missing = [], []
    for uid, ans in answers.items():
        if uid not in items:
            missing.append(uid)
            continue
        try:
            count[ap_.apply_item(items[uid], ans)] += 1
        except (LookupError, ValueError, KeyError) as e:
            errors.append(f'{uid}: {e}')
    for e in errors:
        print('!! ' + e)
    if errors:
        print(f'!! 当てられない回答が {len(errors)} 件．何も書かずに止めた (項目の match・from を直す)')
        return 2
    bk = ap_.backup_and_save()
    for m in ap_.log:
        print('  ' + m)
    print(f'反映 {count["done"]} 件・書くことの無い選択肢 {count["no-op"]} 件・判断できない/未回答 {count["skip"]} 件'
          + (f'・項目に無い id {len(missing)} 件 ({", ".join(missing[:5])})' if missing else '')
          + (f'．写し: {bk}' if bk else '．(書いていない)' if a.dry_run else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
