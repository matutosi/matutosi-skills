"""転記表 (画像と同じ形に書き写した TSV) から，縦持ちの 2 つの CSV を作る．

    python scripts/to_csv.py <置き場>

<置き場>/transcripts/<表>/ の次のファイルを読み，<置き場>/sites.csv・composition.csv を書く．
書き方は references/transcript-format.md．

    meta.tsv    key<TAB>value (file・table・title_ja・title_raw)
    header.tsv  表頭．item_ja item_de unit <地点1> <地点2> …  (セルは印字のまま)
    body.tsv    本体．kind group_ja group_de s_name j_name layer <地点1> … note [status]
    once.tsv    1 回出現の種．plot s_name j_name layer value note [status]
    notes.tsv   注記．plot item_ja item_de value unit value_raw status note

値の分解 (`+・2` → 被度 `+`・群度 `2`，`+` → 群度 `1` を補う，`IV(+-3)` → 常在度) は
ここで行う．群度の印字が無いときの補い方は `--soc-default` で選ぶ
(`one` = 常に 1 (既定)．`cover` = 被度が 2〜5 なら被度と同じ値，`+`・`r`・`1` は 1)．階層が `S;K` の行は，note の `(K に下線)` と値の下線 (`2: 下線` か `±`) で 1 つに決める．
読めない値・末尾に `?` を付けた値は status=check，階層が `S;K` のように
1 つに決まらない行は status=multi にする．
"""
import argparse
import csv
import os
import re
import sys

SEP = r'\s*[・･·•∙.,;:-]\s*'
COV = r'[54321+r]'
UNDER_PART = re.compile(r'[(（]\s*([^()（）]*?)\s*に下線')
NO_UNDER = re.compile(r'階層の字に下線なし|[(（]\s*下線なし\s*[)）]')
ABSENT = {'', '・', '･', '·', '•', '∙', '.', '-', '—', '–'}
ROMAN = r'(?:V|IV|III|II|I)'
FIX = str.maketrans({'＋': '+', '十': '+', '，': ',', '．': '.', '－': '-', '―': '-', '—': '-',
                     '（': '(', '）': ')', '　': ' '})
MONTHS = {'jan': 1, 'feb': 2, 'mär': 3, 'mar': 3, 'märz': 3, 'apr': 4, 'mai': 5, 'may': 5,
          'jun': 6, 'juni': 6, 'jul': 7, 'juli': 7, 'aug': 8, 'sep': 9, 'sept': 9,
          'okt': 10, 'oct': 10, 'nov': 11, 'dez': 12, 'dec': 12}

SITE_COLS = ['file', 'region', 'table', 'plot', 'item_ja', 'item_de', 'value', 'unit',
             'value_raw', 'source', 'status', 'note']
COMP_COLS = ['file', 'region', 'table', 'plot', 'group_ja', 'group_de', 's_name', 'j_name',
             'layer', 'cover', 'sociability', 'constancy', 'value_raw', 'source',
             'status', 'note']


def parse_value(raw, n_plots=0):
    """印字の値を (cover, sociability, constancy, status, note) に分ける．非出現は None

    n_plots は列の調査区数．調査区の少ない列は常在度を出現地点数で印字する (`2(3)`・`1`)"""
    s = raw.translate(FIX).strip()
    underlined = '±' in s                             # ± は下線付きの +
    s = s.replace('±', '+')
    unsure = s.endswith('?')
    s = s.rstrip('?').strip()
    if s in ABSENT:
        if unsure:                                    # ? だけ (読めない) か ・? (非出現か怪しい)
            return ('', '', '', 'check', '読めない' if not s else '非出現か自信なし')
        return None
    notes = ['下線'] if underlined else []
    if s in ('O', '○', '◯'):                          # コケ層などの出現の印 (被度なし)
        return ('O', '', '', 'check' if unsure else 'ok', ';'.join(notes + (['読みに自信なし'] if unsure else [])))
    if s == 'v':                                      # 小文字の v: 極めて微小 (規則 X16．地点の列にも常在度の列にも当てる)
        return ('v', '', '', 'check' if unsure else 'ok', ';'.join(notes + ['v は極めて微小の意味 (規則 X16)']))
    m = re.fullmatch(r'\((.+)\)', s)
    if m:                                             # (+) 括弧付き
        s = m.group(1).strip()
        notes.append('括弧付き')
    out = None
    m = re.fullmatch(rf'([1-9]\d*)(?:\s*\(\s*({COV})(?:\s*-\s*({COV}))?\s*\))?', s) if n_plots else None
    if m and int(m.group(1)) <= n_plots:              # 出現地点数 2(3-4)
        out = ((m.group(2) or '') + ('-' + m.group(3) if m.group(3) else ''), '', m.group(1))
    m = None if out else re.fullmatch(rf'({ROMAN})(?:\s*\(\s*({COV})(?:\s*-\s*({COV}))?\s*\))?', s)
    if m:                                             # 常在度 IV(+-3)
        cov = m.group(2) or ''
        if m.group(3):
            cov += '-' + m.group(3)
        out = (cov, '', m.group(1))
    m = None if (out or not n_plots) else re.fullmatch(rf'([+r])\s*\(\s*({COV})(?:\s*-\s*({COV}))?\s*\)', s)
    if m:                                             # 常在度の列の +(4-5)・r(+) は常在度 (群度の範囲と読まない)
        out = (m.group(2) + ('-' + m.group(3) if m.group(3) else ''), '', m.group(1))
    m = None if out else re.fullmatch(rf'({COV})\s*\(\s*([1-5])\s*-\s*([1-5])\s*\)', s)
    if m:                                             # 2(3-4) 単独地点の群度の範囲
        out = (m.group(1), f'{m.group(2)}-{m.group(3)}', '')
    m = None if out else re.fullmatch(rf'([+r])\s*\(\s*({COV})(?:\s*-\s*({COV}))?\s*\)', s)
    if m:                                             # 常在度が + や r: +(+) / +(1)
        out = (m.group(2) + ('-' + m.group(3) if m.group(3) else ''), '', m.group(1))
    if out is None and n_plots and s in ('+', 'r'):  # 常在度の列の + / r だけ: I より低い常在度の印 (被度ではない)
        out = ('', '', s)
    m = None if out else re.fullmatch(rf'({COV})(?:{SEP}([1-5]))?', s)
    if m:                                             # 4・2 / + / r
        soc = m.group(2)
        if not soc:
            soc = m.group(1) if SOC_DEFAULT == 'cover' and m.group(1) in '2345' else '1'
        out = (m.group(1), soc, '')
    if out is None:
        return ('', '', '', 'check', ';'.join(notes + [f'値として読めない: {raw}']))
    return out + ('check' if unsure else 'ok', ';'.join(notes + (['読みに自信なし'] if unsure else [])))


SOC_DEFAULT = 'one'                                   # 群度の印字が無いときの補い方: one | cover
PLOTS_SEEN = set()


def cell_note(note, plot):
    """行の note のうち，その地点に掛かるものだけを返す．`2: 下線` は地点 2 だけ"""
    out = []
    for part in (x.strip() for x in note.split(';')):
        m = re.match(r'^([^:：\s]+)\s*[:：]\s*(.*)$', part)
        if m and m.group(1) in PLOTS_SEEN:
            if m.group(1) == plot:
                out.append(m.group(2))
        elif part:
            out.append(part)
    return ';'.join(out)


def merge(status, note, row, plot=None):
    """行の status 列・note (地点の指定つき)・複数の階層を，セルの status と note に重ねる"""
    extra = cell_note(row.get('note', ''), plot) if plot is not None else row.get('note', '')
    notes = [x for x in (note, extra) if x]
    if row.get('status', '').strip() == 'check' or any(x.strip().startswith('check') for x in extra.split(';')):
        status = 'check'
    if ';' in row.get('layer', '') and status == 'ok':
        status = 'multi'                              # 値はあるが階層が 1 つに決まらない
    return status, ';'.join(notes)


HERB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'references', 'herb_species.tsv')


def load_herbs(path=HERB_FILE):
    """references/herb_species.tsv の学名 (草本で着生植物でない種) の集合"""
    if not os.path.exists(path):
        return set()
    with open(path, encoding='utf-8-sig') as f:
        return {r['s_name'].strip() for r in csv.DictReader(f, delimiter='	') if r.get('s_name')}


HERBS = load_herbs()


def herb_layer(s_name, layer):
    """階層が複数のまま (multi) で，種が草本 (着生植物でない) のときは K 層とする．K が候補にあるときだけ"""
    layers = layer.split(';')
    if len(layers) > 1 and 'K' in layers and s_name.strip() in HERBS:
        return 'K'
    return layer


def underlined_layers(note, layers):
    """行の note「印字は B2,S (S に下線．…)」から，階層の字に下線がある階層を返す．
    `(B2 と S に下線)`・`(B1,S に下線)` のように複数もよい．「両方に下線」「対象は読み取れず」
    「階層の字に下線なし」など，階層名が読み取れないときは空"""
    out = []
    for m in UNDER_PART.finditer(note):
        names = re.findall(r'[A-Za-z]+\d?', m.group(1))
        if names and all(n in layers for n in names):
            out += [n for n in names if n not in out]
    if not out and len(layers) > 1 and NO_UNDER.search(note):
        out = [layers[-1]]                            # どの階層の字にも下線が無いときは，後ろの階層を下線つきとみる
    return out


def cell_layer(row, plot):
    """複数の階層の行で，そのセルの階層を返す．下線の階層が分かれば，下線の値はその階層，
    下線の無い値は残りの階層 (残りが 1 つに決まるときだけ)．決まらなければ複数のまま (status=multi)"""
    layers = row.get('layer', '').split(';')
    under = underlined_layers(row.get('note', ''), layers)
    if len(layers) < 2 or not under or len(under) == len(layers):
        return row.get('layer', '')
    marked = '±' in row.get(plot, '') or '下線' in cell_note(row.get('note', ''), plot).split(';')
    rest = [x for x in layers if x not in under]
    if marked:
        return under[0] if len(under) == 1 else row.get('layer', '')
    return rest[0] if len(rest) == 1 else ';'.join(rest)


DASH_LAYER = re.compile(r'階層の印字は\s*[-−―ー]')
NO_LAYER_NOTE = '階層の印字なし (つる・着生などで意図的に省いたとみる)'


def layer_from_below(body):
    """階層の印字が無い行 (note に「階層の印字」とある) の階層を決める (2026-11-05 ユーザ指示)．
    1. すぐ下の行が階層を 1 つ持つときは，その階層とみる．ブロック (空き行・見出しで区切られる) では
       上の階層から順に書くので，階層の字が 1 行下にずれて印字されたとみる (層の位置の誤り)
    2. 階層の無い行が続くとき・すぐ下が見出しや表の終わりのときは，空欄のまま，確認にも出さない
       (つる植物・着生植物が大半で，わざと階層を書いていないとみる)．check を外し，note を簡潔にする"""
    out = list(body)
    for i, r in enumerate(body):
        if (r.get('kind') == 'group' or (r.get('layer') or '').strip()
                or '階層の印字' not in (r.get('note') or '') or not (r.get('s_name') or r.get('j_name'))):
            continue
        if DASH_LAYER.search(r.get('note') or ''):        # 階層の欄に「-」と明記された行は，変更せず確認にも出さない
            parts = [x.strip() for x in (r.get('note') or '').split(';')]
            parts = [x for x in parts if x and not (x.startswith('check') and '階層の印字' in x)]
            if not any(DASH_LAYER.search(x) for x in parts):
                parts.append('階層の印字は - (明記)')
            out[i] = dict(r, note=';'.join(parts))
            continue
        nxt = body[i + 1] if i + 1 < len(body) else {'kind': 'group'}
        below = (nxt.get('layer') or '').strip() if nxt.get('kind') != 'group' else ''
        parts = [x.strip() for x in (r.get('note') or '').split(';')]
        parts = [x for x in parts if x and not (x.startswith('check') and '階層の印字' in x)]
        if below and ';' not in below:
            parts.append(f'階層の印字が無いので，下の行の階層 {below} とした (層の位置の誤りとみる)')
            out[i] = dict(r, layer=below, note=';'.join(parts))
        else:
            parts = [x for x in parts if not ('階層の印字' in x and len(x) <= 40 and '．' not in x)]
            parts.append(NO_LAYER_NOTE)
            out[i] = dict(r, note=';'.join(parts))
    return out


def plot_list(spec):
    """注記の地点の指定 `1,7-9` を ['1', '7', '8', '9'] にする．形が違えばそのまま"""
    if not re.fullmatch(r'\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*', spec):
        return [spec]
    out = []
    for part in spec.split(','):
        lo, _, hi = part.partition('-')
        out += [str(i) for i in range(int(lo), int(hi or lo) + 1)]
    return out


def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig', newline='') as f:
        rows = [r for r in csv.reader(f, delimiter='\t') if r and not r[0].startswith('#')]
    if not rows:
        return []
    head = [h.strip() for h in rows[0]]
    return [dict(zip(head, [c.strip() for c in r] + [''] * (len(head) - len(r)))) for r in rows[1:]]


def plots_of(head, fixed):
    return [h for h in head if h not in fixed and h]


def plots_per_column(header):
    """表頭の「調査区数」の行から，常在度の列の調査区数を返す．{列: 数}

    `<5` は「調査区数の印字は無いが 5 未満の列」(値が全部 算用数字の出現地点数)．上限の 4 として扱う．"""
    for r in header:
        if r.get('item_ja') == '調査区数' or r.get('item_de', '').lower().startswith('zahl d. aufn'):
            return {p: (4 if v.strip() == '<5' else int(v)) for p, v in r.items()
                    if p.isdigit() and (v.isdigit() or v.strip() == '<5')}
    return {}


def norm_site(item_ja, item_de, raw, year=None):
    """表頭の値を整える．(value, status, note)"""
    s = raw.translate(FIX).strip()
    unsure = s.endswith('?')
    s = s.rstrip('?').strip()
    st = 'check' if unsure else 'ok'
    note = '読みに自信なし' if unsure else ''
    if s in ('-', '—', '–'):
        return '-', st, note
    key = item_ja + ' ' + item_de.lower()
    if s == 'L':                                      # L はレベル (傾斜 0 度で方位なし)．方位は -，傾斜は 0
        aspect = '方位' in item_ja or 'expos' in key
        slope = '傾斜' in item_ja or 'neig' in key or 'inclin' in key or 'inklin' in key
        if aspect != slope:
            note = ';'.join(x for x in (note, f"L (レベル) を{'方位なし' if aspect else '傾斜 0'}に自動変換") if x)
            return ('-' if aspect else '0'), st, note
    if '年月日' in key or '月日' in key or 'datum' in key:
        d = norm_date(s, year)
        if d:
            return d, st, note
        return s, 'check', '日付として読めない'
    if '調査番号' in key or 'feld' in key:
        return re.sub(r'\s+', '-', s), st, note
    if re.fullmatch(r'\d+\s*[.・･·•]\s*\d+', s):     # 0. 5 / 1・8 (小数点が中黒の印字)
        return re.sub(r'\s*[.・･·•]\s*', '.', s), st, note
    return s, st, note


def norm_date(s, year=None):
    s = s.strip().rstrip('.')
    m = re.search(r'(\d{1,2})\.?\s*([A-Za-zäÄ]+)\.?\s*(\d{4})', s)           # 6. Juli 1983
    if m:
        w = m.group(2).lower()
        mon = MONTHS.get(w) or MONTHS.get(w[:4]) or MONTHS.get(w[:3])
        if mon:
            return f'{int(m.group(3)):04d}-{mon:02d}-{int(m.group(1)):02d}'
    m = re.search(r'(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})', s)
    if m:
        return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    nums = re.findall(r"'?\d+", s)
    if len(nums) == 3:                                # '83 8 3
        y, mo, d = nums
        y = int(y.lstrip("'"))
        y = y + 1900 if y < 100 else y
        return f'{y:04d}-{int(mo):02d}-{int(d):02d}'
    if len(nums) == 2 and year:                       # 年は見出しにある (Datum d. Aufn. (1983))
        return f'{int(year):04d}-{int(nums[0]):02d}-{int(nums[1]):02d}'
    return None


def build(tdir):
    meta = {r['key']: r['value'] for r in read_tsv(os.path.join(tdir, 'meta.tsv'))}
    file, table = meta.get('file', ''), meta.get('table', os.path.basename(tdir))
    sites, comp = [], []
    if meta.get('title_ja') or meta.get('title_raw'):
        sites.append(dict(file=file, table=table, plot='', item_ja='表題', item_de='Titel',
                          value=meta.get('title_ja', ''), unit='', value_raw=meta.get('title_raw', ''),
                          source='title', status='ok', note=''))

    header = read_tsv(os.path.join(tdir, 'header.tsv'))
    body = layer_from_below(read_tsv(os.path.join(tdir, 'body.tsv')))
    fixed_head = {'item_ja', 'item_de', 'unit', 'note', 'status'}
    fixed_body = {'kind', 'group_ja', 'group_de', 's_name', 'j_name', 'layer', 'note', 'status'}
    all_plots = []
    for rows, fixed in ((header, fixed_head), (body, fixed_body)):
        if rows:
            all_plots += [p for p in plots_of(list(rows[0].keys()), fixed) if p not in all_plots]
    PLOTS_SEEN.clear()
    PLOTS_SEEN.update(all_plots)
    if header:
        plots = plots_of(list(header[0].keys()), fixed_head)
        for r in header:
            ym = re.search(r'(19|20)\d\d', r.get('item_de', '') + r.get('item_ja', ''))
            for p in plots:
                raw = r.get(p, '')
                if raw == '':
                    continue
                v, st, note = norm_site(r['item_ja'], r['item_de'], raw, ym and ym.group(0))
                st, note = merge(st, note, r, p)
                sites.append(dict(file=file, table=table, plot=p, item_ja=r['item_ja'],
                                  item_de=r['item_de'], value=v, unit=r.get('unit', ''),
                                  value_raw=raw, source='header', status=st, note=note))

    for r in read_tsv(os.path.join(tdir, 'notes.tsv')):
        # plot が空 = 全地点に共通．地点ごとに展開する (地点が分からなければ空のまま)
        for p in (plot_list(r.get('plot', '')) if r.get('plot', '') or not all_plots else all_plots):
            sites.append(dict(file=file, table=table, plot=p, item_ja=r.get('item_ja', ''),
                              item_de=r.get('item_de', ''), value=r.get('value', ''),
                              unit=r.get('unit', ''), value_raw=r.get('value_raw', ''),
                              source='note', status=r.get('status') or 'ok', note=r.get('note', '')))

    n_plots = plots_per_column(header)                 # 常在度の列の調査区数 {列: 数} (1 回出現でも使う)
    if body:
        plots = plots_of(list(body[0].keys()), fixed_body)
        g_ja = g_de = s_prev = j_prev = ''
        for r in body:
            if r.get('kind') == 'group':
                g_ja, g_de = r.get('group_ja', ''), r.get('group_de', '')
                continue
            s, j = r.get('s_name', ''), r.get('j_name', '')
            if not s and not j:                       # 階層ごとの続きの行
                s, j = s_prev, j_prev
            s_prev, j_prev = s, j
            for p in plots:
                pv = parse_value(r.get(p, ''), n_plots.get(p, 0))
                if pv is None:
                    continue
                cov, soc, const, st, note = pv
                layer = cell_layer(r, p)
                by_herb = herb_layer(s, layer)
                st, note = merge(st, note, dict(r, layer=by_herb), p)
                if layer != r.get('layer', ''):         # 規則で階層を決めたものは note に残す
                    note = ';'.join(x for x in (note, f"下線の規則で階層を {layer} に決めた (印字は {r.get('layer', '').replace(';', ',')})") if x)
                if by_herb != layer:
                    note = ';'.join(x for x in (note, '草本のため K 層とした') if x)
                layer = by_herb
                comp.append(dict(file=file, table=table, plot=p, group_ja=g_ja, group_de=g_de,
                                 s_name=s, j_name=j, layer=layer, cover=cov,
                                 sociability=soc, constancy=const, value_raw=r.get(p, ''),
                                 source='body', status=st, note=note))

    for r in read_tsv(os.path.join(tdir, 'once.tsv')):
        pv = parse_value(r.get('value', ''), n_plots.get(r.get('plot', ''), 0)) or ('', '', '', 'check', '値が空')
        cov, soc, const, st, note = pv
        once_layer = herb_layer(r.get('s_name', ''), r.get('layer', ''))
        st, note = merge(st, note, dict(r, layer=once_layer))
        if once_layer != r.get('layer', ''):
            note = ';'.join(x for x in (note, '草本のため K 層とした') if x)
        comp.append(dict(file=file, table=table, plot=r.get('plot', ''), group_ja='', group_de='',
                         s_name=r.get('s_name', ''), j_name=r.get('j_name', ''),
                         layer=once_layer, cover=cov, sociability=soc, constancy=const,
                         value_raw=r.get('value', ''), source='once', status=st, note=note))
    add_column_kind(file, table, sorted(set(all_plots) | {c['plot'] for c in comp}), n_plots, comp, sites)
    region = re.sub(r'_\d+$', '', file)
    for row in sites + comp:
        row['region'] = region
    return sites, comp


def add_column_kind(file, table, plots, n_plots, comp, sites):
    """列ごとに「列の種類」の行を sites に足す．調査区 / 常在度 / 混在 (混在は check)．
    常在度 = 調査区数が 1 以上と書かれた列，または constancy の入ったセルがある列．
    constancy の入ったセルと入っていないセルが同じ列にあれば混在 (印字の読み違いを疑う)"""
    for p in plots:
        cells = [c for c in comp if c['plot'] == p and c['cover'] != 'v']   # v (極めて微小．X16) はどの列にも入る
        body = [c for c in cells if c.get('source') != 'once']
        with_c = sum(1 for c in cells if c['constancy'])
        body_c = sum(1 for c in body if c['constancy'])
        if body and body_c * 2 >= len(body):             # 本体の半分以上が常在度のセル = 常在度の列
            for c in body:                               # 常在度の列の + / r だけのセルは常在度の低い印 (被度ではない)
                if not c['constancy'] and c['value_raw'].strip() in ('+', 'r'):
                    c['constancy'], c['cover'], c['sociability'] = c['value_raw'].strip(), '', ''
                    c['note'] = (c['note'] + ';' if c['note'] else '') + '常在度の列の + は常在度の低い印とした'
            cells = [c for c in cells if c.get('source') != 'once']   # 1 回出現のセル (被度・群度の形) は列の種類に数えない
            with_c = sum(1 for c in cells if c['constancy'])
        kind = '常在度' if (n_plots.get(p, 0) > 0 or with_c) else '調査区'
        st, note = 'ok', ''
        if with_c and with_c < len(cells):
            n_plot = len(cells) - with_c
            if with_c == n_plot:                         # 同数なら決められないので混在のまま
                kind, st = '混在', 'check'
                note = f'常在度のセル {with_c} 個・調査区のセル {n_plot} 個が同じ列にある'
            else:                                        # 多数決で列の種類を決め，少ないほうのセルに印を付ける (0.5.9)
                kind = '常在度' if with_c > n_plot else '調査区'
                odd = [c for c in cells if bool(c['constancy']) != (kind == '常在度')]
                for c in odd:
                    if 'ユーザ確認' not in c['note']:     # 回答済みのセルは ok のまま
                        c['status'] = 'check'
                    c['note'] = (c['note'] + ';' if c['note'] else '') + f'列の種類 ({kind}) と違う形のセル'
                note = (f'常在度のセル {with_c} 個・調査区のセル {n_plot} 個．多数決で{kind}の列とし，'
                        f'少ないほうの {len(odd)} 個はセルに印を付けた')
        elif n_plots.get(p, 0) > 0 and not with_c and cells:
            st, note = 'check', '調査区数があるが常在度のセルが無い'
        elif kind == '常在度' and not n_plots.get(p, 0):
            note = '調査区数の印字が無い'
        sites.append(dict(file=file, table=table, plot=p, item_ja='列の種類', item_de='',
                          value=kind, unit='', value_raw='', source='derived', status=st, note=note))


def write(path, cols, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir')
    ap.add_argument('--soc-default', choices=('one', 'cover'), default='one',
                    help='群度の印字が無いときの補い方．one=常に 1 (既定)．cover=被度 2〜5 なら被度と同じ値')
    a = ap.parse_args(argv)
    global SOC_DEFAULT
    SOC_DEFAULT = a.soc_default
    root = os.path.join(a.dir, 'transcripts')
    if not os.path.isdir(root):
        sys.exit(f'転記表が無い: {root}')
    sites, comp = [], []
    for name in sorted(os.listdir(root)):
        tdir = os.path.join(root, name)
        if os.path.isdir(tdir):
            s, c = build(tdir)
            sites += s
            comp += c
            print(f'{name}: sites {len(s)} 行・composition {len(c)} 行')
    write(os.path.join(a.dir, 'sites.csv'), SITE_COLS, sites)
    write(os.path.join(a.dir, 'composition.csv'), COMP_COLS, comp)
    print(f'計: sites {len(sites)} 行・composition {len(comp)} 行 → {a.dir}')


if __name__ == '__main__':
    main()
