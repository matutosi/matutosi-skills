"""composition.csv の和名を「維管束植物和名チェックリスト」と照合し，names.tsv に書く．

    python scripts/check_species.py <置き場> [--checklist FILE.xlsx | --download]

照合の本体は，同じプラグインの veg-sheet-to-csv の check_names.py を使う．
CSV は**書き換えない** (印字のまま残す)．読み違いの手がかりとして見る:

- `none`・`similar` の和名は，画像に戻って読み直す
- `same_genus` が 0 の行は，学名か和名のどちらかの読み違い，または行のずれを疑う
- 画像で印字どおりと確かめた行は，names.tsv の `checked` 列に書いておく (例: `印字どおり`)．
  次に回したときも (和名・学名) が同じ行には引き継ぎ，件数の表示で「確かめ済み」として分けて数える
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, '..', '..', 'veg-sheet-to-csv', 'scripts')))
import check_names as cn  # noqa: E402

COLS = ['status', 'j_name', 's_name', 'count', 'hub', 'latin', 'family', 'same_genus', 'candidates', 'note', 'checked']
ORDER = {'none': 0, 'similar': 1, 'ambiguous': 2, 'alias': 3, 'ok': 4, 'skip': 5}


def genus(name):
    words = (name or '').split()
    return words[0].lower() if words else ''


def check(rows, idx):
    """composition の行から，(和名, 学名) ごとの照合結果を返す"""
    count = {}
    for r in rows:
        k = (r.get('j_name', '').strip(), r.get('s_name', '').strip())
        count[k] = count.get(k, 0) + 1
    out = []
    for (j, s), n in count.items():
        if not j:
            continue
        r = cn.check_name(idx, j)
        same = ''
        if s and r['latin']:
            same = '1' if genus(s) == genus(r['latin']) else '0'
        out.append(dict(status=r['status'], j_name=j, s_name=s, count=n, hub=r['hub'], latin=r['latin'],
                        family=r['family'], same_genus=same, candidates='，'.join(r['candidates']), note=r['note']))
    return sorted(out, key=lambda r: (ORDER[r['status']], r['j_name']))


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir')
    ap.add_argument('--checklist', help='チェックリストの xlsx')
    ap.add_argument('--download', action='store_true', help='xlsx が無ければ取得する')
    a = ap.parse_args(argv)
    with open(os.path.join(a.dir, 'composition.csv'), encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    res = check(rows, cn.load_index(cn.resolve_xlsx(a)))
    path = os.path.join(a.dir, 'names.tsv')
    done = {}                                         # 前回の names.tsv の「確かめ済み」を引き継ぐ
    if os.path.exists(path):
        with open(path, encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f, delimiter='	'):
                if (r.get('checked') or '').strip():
                    done[(r.get('j_name', ''), r.get('s_name', ''))] = r['checked'].strip()
    for r in res:
        r['checked'] = done.get((r['j_name'], r['s_name']), '')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter='\t', lineterminator='\n')
        w.writeheader()
        w.writerows(res)
    counts = {}
    for r in res:
        counts[r['status']] = counts.get(r['status'], 0) + 1
    print('照合:', '，'.join(f'{k} {v}' for k, v in sorted(counts.items())))
    print(f'属が合わない行: {sum(r["same_genus"] == "0" for r in res)} → {path}')
    kept = [r for r in res if r['checked']]
    if kept:
        left = sum(1 for r in res if not r['checked'] and r['status'] in ('none', 'similar'))
        print(f'確かめ済み (checked 列を引き継いだ) {len(kept)} 行．none・similar のうち未確認 {left} 行')
    return 0


if __name__ == '__main__':
    sys.exit(main())
