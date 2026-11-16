"""1 回出現の段落の決まり"""
import re

from common import to_csv
from rules import Change, rule

import check as old_check          # 今のスキルの check.py (種の数え方・見出しのずれの試し方を使う)

NO_MOSS = re.compile(r'ohne\s+Moos|蘚苔類を除く|コケを除く', re.I)


def species_sets(t):
    """(本体の {地点: 種の集合}, 1 回出現の {地点: 種の集合}, 印字の {地点: 出現種数})．地点は int．
    種の数え方は今の check.py と同じ (学名を鍵に．出現種数の項目名に「蘚苔類を除く」とある表は蘚苔類・地衣類を外す)"""
    want, no_moss = {}, False
    for d in t.dicts('header'):
        if d.get('item_ja', '').startswith('出現種数') or 'artenzahl' in d.get('item_de', '').lower():
            no_moss = bool(NO_MOSS.search(d.get('item_ja', '') + ' ' + d.get('item_de', '')))
            for p in t.plots('header'):
                v = (d.get(p) or '').strip().rstrip('?')
                if v.isdigit():
                    want[int(p)] = want.get(int(p), 0) + int(v)
    body, once = {}, {}
    g_ja = g_de = s_prev = j_prev = ''
    plots = t.plots('body')
    for d in t.dicts('body'):
        if d.get('kind') == 'group':
            g_ja, g_de = d.get('group_ja', ''), d.get('group_de', '')
            continue
        s, j = d.get('s_name', '').strip(), d.get('j_name', '').strip()
        if not s and not j:
            s, j = s_prev, j_prev
        s_prev, j_prev = s, j
        r = dict(s_name=s, j_name=j, layer=d.get('layer', ''), group_ja=g_ja, group_de=g_de, note=d.get('note', ''))
        if no_moss and old_check.is_moss(r):
            continue
        for p in plots:
            v = (d.get(p) or '').strip().rstrip('?').strip()
            if v and v not in to_csv.ABSENT:
                body.setdefault(int(p), set()).add(old_check.spkey(r))
    for d in t.dicts('once'):
        p = d.get('plot', '').strip()
        s, j = d.get('s_name', '').strip(), d.get('j_name', '').strip()
        if not p.isdigit() or not (s or j):               # 名前の無い値 (規則 X53) は種に数えない
            continue
        r = dict(s_name=s, j_name=j, layer=d.get('layer', ''), group_ja=d.get('group', ''), group_de='', note=d.get('note', ''))
        if no_moss and old_check.is_moss(r):
            continue
        once.setdefault(int(p), set()).add(old_check.spkey(r))
    return body, once, want


def shift_candidates(body, once, want, max_len=15):
    """1 回出現の段落 s〜e を d (±1) 地点ずらすと，関わる地点の種数がすべて印字と合い，今より合う地点が 2 つ以上増える組を
    すべて返す [(s, e, d, 合う地点, 増える数)]．今のスキルの check.py の heading_shifts と同じ条件だが，同じ向きの候補を
    1 つに絞らない (絞ると，離れた別のずれが捨てられる．九州 Tab.011 の in 17〜19 が in 40 に負けて見送られた)"""
    plots = sorted(once)
    if not plots:
        return []

    def n_ok(q, src):
        return len(body.get(q, set()) | src.get(q, set())) == want[q]
    out = []
    lo, hi = plots[0], plots[-1]
    for d in (-1, 1):
        for s in range(lo, hi + 1):
            for e in range(s, min(hi, s + max_len - 1) + 1):
                if s not in once or e not in once:
                    continue
                moved = {q: v for q, v in once.items() if not s <= q <= e}
                for q in range(s, e + 1):
                    if q in once:
                        moved[q + d] = moved.get(q + d, set()) | once[q]
                touched = set(range(s, e + 1)) | set(range(s + d, e + d + 1))
                if any(q not in want and moved.get(q) for q in touched):
                    continue
                checked = [q for q in touched if q in want]
                if not checked or not all(n_ok(q, moved) for q in checked):
                    continue
                gain = sum(1 for q in checked if not n_ok(q, once))
                if gain >= 2:
                    out.append((s, e, d, tuple(sorted(checked)), gain))
    return out


@rule('D11', '1 回出現の見出しのずれ: 1 地点ずらすと関わる地点の出現種数がすべて印字と合うときだけ移す', '1 回出現', old='X35')
def heading_shift(t, param):
    """1 つ移しては数え直し，次のずれを探す (今の手順と同じ)．候補はすべて見て，前後どちらへずらしても合う (関わる地点の
    重なる逆向きの候補がある) 候補だけを見送る．離れた別のずれは別々に移す (2026-11-16 ユーザ決定 1a)．同じ行は 2 回動かさない"""
    work = t.copy()
    moved = {}                                             # 行番号 -> (印字の地点, 理由)
    for _ in range(20):
        body, once, want = species_sets(work)
        if not once or len(want) < 2:
            break
        cands = shift_candidates(body, once, want)
        touched = {c: set(range(c[0], c[1] + 1)) | set(range(c[0] + c[2], c[1] + c[2] + 1)) for c in cands}
        cands = [c for c in cands if not any(c2[2] != c[2] and touched[c] & touched[c2] for c2 in cands)]   # 前後どちらでも合う
        cands = [c for c in cands if not any(row['_row'] in moved and c[0] <= int(row['plot']) <= c[1]
                                             for row in work.dicts('once') if row.get('plot', '').strip().isdigit())]
        if not cands:
            break
        s, e, d, ok, _ = max(cands, key=lambda c: (c[4], len(c[3]), -(c[1] - c[0])))
        for row in work.dicts('once'):
            p = row.get('plot', '').strip()
            if p.isdigit() and s <= int(p) <= e:
                moved[row['_row']] = (p, f'地点 {" ".join(map(str, ok))} の出現種数がすべて印字と合う')
                work.set('once', row['_row'], '@plot', str(int(p) + d))
    # 段落の途中からのずれ (2026-11-16 ユーザ決定): 段落の先頭から k 行だけを前の地点へ移すと，両方の地点の出現種数が
    # 印字と合うときも移す．合う k が 1 つだけのときに限る (偶然の一致を減らす)．まるごとのずれを当てたあとで見る
    for _ in range(20):
        body, once, want = species_sets(work)
        found = None
        for p in sorted(once):
            q = p - 1
            if q not in want or p not in want:
                continue

            def n(plot, sets):
                return len(body.get(plot, set()) | sets.get(plot, set()))
            if n(p, once) == want[p] or n(q, once) == want[q]:
                continue                                    # どちらかがもう合っている地点は触らない
            rows = [r for r in work.dicts('once') if r.get('plot', '').strip() == str(p) and r['_row'] not in moved
                    and (r.get('s_name', '').strip() or r.get('j_name', '').strip())]
            hits = []
            for k in range(1, len(rows)):
                head = {old_check.spkey(dict(s_name=r.get('s_name', '').strip(), j_name=r.get('j_name', '').strip())) for r in rows[:k]}
                rest = {old_check.spkey(dict(s_name=r.get('s_name', '').strip(), j_name=r.get('j_name', '').strip())) for r in rows[k:]}
                keep_p = (once.get(p, set()) - head) | rest
                if len(body.get(p, set()) | keep_p) == want[p] and len(body.get(q, set()) | once.get(q, set()) | head) == want[q]:
                    hits.append(k)
            if len(hits) == 1:
                found = (p, q, rows[:hits[0]])
                break
        if not found:
            break
        p, q, rows = found
        for r in rows:
            moved[r['_row']] = (str(p), f'段落の先頭の {len(rows)} 行を移すと地点 {q} {p} の出現種数が印字と合う')
            work.set('once', r['_row'], '@plot', str(q))
    for row, (p, why) in sorted(moved.items()):
        new = work.get('once', row, '@plot')
        yield Change('once', row, '@plot', new, f'印字は in {p}．見出しのずれとみて地点 {new} へ移した ({why})')


LAYER_ROWS = {'B': ('高木層',), 'B1': ('高木第1層', '高木第一層', '高木層1'), 'B2': ('高木第2層', '高木第二層', '高木層2'),
              'S': ('低木層',), 'K': ('草本層',)}
DASH = {'', '-', '—', '–', '−', '―'}


def layer_absent(t):
    """表頭で「その階層が無い」と分かる (階層, 地点) の集合．その階層の行 (高さ・植被率) があり，その地点の値が全部 - のとき"""
    out = set()
    plots = t.plots('header')
    for layer, names in LAYER_ROWS.items():
        rows = [d for d in t.dicts('header') if any(d.get('item_ja', '').replace(' ', '').startswith(n) for n in names)]
        for p in plots:
            if rows and all((d.get(p) or '').strip() in DASH for d in rows):
                out.add((layer, p))
    return out


@rule('D26', '1 回出現の値の階層が表頭に無い地点の段落は，種数が合うときだけ，その階層のある隣の地点へ移す', '1 回出現',
      old='(前回のユーザ確認から)', order=10.5)
def paragraph_to_layer_plot(t, param):
    """段落の中に，表頭でその地点に無いとされた階層 (B など) の値がある → 見出しの番号の印字ミスを疑う．
    隣の地点 (片方だけ) にその階層があり，段落をまるごと移すと両方の地点の出現種数が印字と合うときだけ移す
    (2026-11-16 ユーザ決定．前回のユーザ確認の 2 つの型を合わせた条件)．
    D11 (種数だけで見る見出しのずれ) より先に当てる (order=10.5)．D11 は前後どちらへずらしても種数が合うときに
    決められず見送るので，階層の手がかりで向きが決まるこの規則を先にする"""
    absent = layer_absent(t)
    if not absent:
        return
    body, once, want = species_sets(t)
    rows_of = {}
    for r in t.dicts('once'):
        p = r.get('plot', '').strip()
        if p.isdigit():
            rows_of.setdefault(int(p), []).append(r)
    for p, rows in sorted(rows_of.items()):
        bad = {r.get('layer', '').strip() for r in rows if (r.get('layer', '').strip(), str(p)) in absent}
        if not bad or p not in want:
            continue
        ok_q = [q for q in (p - 1, p + 1) if q in want and all((layer, str(q)) not in absent for layer in bad)]
        if len(ok_q) != 1:
            continue
        q = ok_q[0]
        sp = once.get(p, set())
        if len(body.get(p, set())) == want[p] and len(body.get(q, set()) | once.get(q, set()) | sp) == want[q]:
            for r in rows:
                yield Change('once', r['_row'], '@plot', str(q),
                             f'印字は in {p}．地点 {p} の表頭に無い階層 ({"・".join(sorted(bad))}) の値がある．'
                             f'地点 {q} へ移すと両方の出現種数が印字と合う')
