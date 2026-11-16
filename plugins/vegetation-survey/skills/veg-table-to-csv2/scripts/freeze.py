"""転記を固定する．固定した表は書き換えない (読み違いは readings.tsv で直す)．

    python scripts/freeze.py <置き場>                 # まだ固定していない表を固定する
    python scripts/freeze.py <置き場> --table Tab.038 # その表だけ
    python scripts/freeze.py <置き場> --check         # 固定後に書き換えられた表が無いかを確かめる (あれば終了コード 2)
    python scripts/freeze.py <置き場> --refreeze Tab.038   # 固定をやり直す (読みの検算で直したとき．理由を --why に)

<置き場>/frozen.tsv (列: table sha256 frozen_at why) に，表ごとのハッシュを書く．
ハッシュは meta・header・body・once・notes の 5 ファイルの中身から取る (改行の違いは無視する)．
"""
import argparse
import datetime
import hashlib
import os
import sys

from common import CR, NL, read_tsv_raw, table_dirs, write_tsv_raw

FILES = ('meta', 'header', 'body', 'once', 'notes')
HEAD = ['table', 'sha256', 'frozen_at', 'why']


def table_hash(tdir):
    h = hashlib.sha256()
    for name in FILES:
        p = os.path.join(tdir, name + '.tsv')
        h.update(name.encode('utf-8') + b'=')
        if os.path.exists(p):
            with open(p, 'rb') as f:
                h.update(f.read().replace((CR + NL).encode(), NL.encode()))
        h.update(b';')
    return h.hexdigest()


def load(root):
    p = os.path.join(root, 'frozen.tsv')
    if not os.path.exists(p):
        return {}
    _, rows, _, _ = read_tsv_raw(p)
    return {r[0]: (r + [''] * 4)[:4] for r in rows if r and r[0]}


def save(root, frozen):
    write_tsv_raw(os.path.join(root, 'frozen.tsv'), HEAD, [frozen[k] for k in sorted(frozen)])


def check(root):
    """(固定後に変わった表, 固定していない表) を返す"""
    frozen = load(root)
    changed, loose = [], []
    for tdir in table_dirs(root):
        name = os.path.basename(tdir)
        if name not in frozen:
            loose.append(name)
        elif frozen[name][1] != table_hash(tdir):
            changed.append(name)
    return changed, loose


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('dir')
    ap.add_argument('--table', action='append', default=[], help='固定する表 (何度でも．省くと未固定の全部)')
    ap.add_argument('--check', action='store_true', help='固定後の書き換えを確かめるだけ')
    ap.add_argument('--refreeze', action='append', default=[], help='固定をやり直す表 (--why が要る)')
    ap.add_argument('--why', default='', help='固定・やり直しの理由 (frozen.tsv に残す)')
    a = ap.parse_args(argv)
    if a.check:
        changed, loose = check(a.dir)
        for n in changed:
            print(f'!! 固定後に書き換えられた: {n}')
        print(f'固定済み {len(load(a.dir)) - len(changed)}・書き換えあり {len(changed)}・未固定 {len(loose)}'
              + (f' ({", ".join(loose[:8])}{" …" if len(loose) > 8 else ""})' if loose else ''))
        return 2 if changed else 0
    if a.refreeze and not a.why:
        sys.exit('--refreeze には --why (理由) が要る')
    frozen = load(a.dir)
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    done = []
    for tdir in table_dirs(a.dir):
        name = os.path.basename(tdir)
        if a.table and name not in a.table and name not in a.refreeze:
            continue
        if name in frozen and name not in a.refreeze:
            continue
        frozen[name] = [name, table_hash(tdir), now, a.why]
        done.append(name)
    save(a.dir, frozen)
    print(f'固定した表 {len(done)} (計 {len(frozen)})' + (f': {", ".join(done[:8])}{" …" if len(done) > 8 else ""}' if done else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
