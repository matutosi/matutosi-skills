"""並行して読んだ表の結果 (表ごとの作業場所 <出力>/scratch/tNNN/) を，共有のファイルへ取り込む．

並行して読むエージェントは共有のファイルに書かず，作業場所に次を書く (SKILL.md 0 節「サブエージェントで読むとき」)．
    out/transcripts/Tab.NNN/   転記 (meta・header・body・once・notes.tsv)
    status.tsv                 1 行: Tab.NNN<TAB>done|reading<TAB>印字の表題<TAB>note
    log.md                     reading_log.md に載せる表の節
    user_review.tsv            確認事項 (見出しつき．列は名前で合わせる)
    auto_list_kasure.tsv・auto_list_paren.tsv・improve.txt   (あれば)

使い方:
    python scripts/merge_tables.py <出力> Tab.038 Tab.054 ...
    python scripts/merge_tables.py <出力> Tab.038 --again      # 取り込み済みの表を取り込み直す

取り込み済みの表は <出力>/scratch/merged.txt に記録し，二度取り込まない (--again で取り込み直す．確認事項と記録は足し直すので重なる)．
done の表は tables.tsv の note (見渡しの範囲・地点の数) を残し，reading の表だけ note を書き換える．
"""
import argparse
import os
import shutil
import subprocess
import sys

RCOLS = ['table', 'plot', 'j_name', 'kind', 'what', 'page', 'x0', 'y0', 'x1', 'y1',
         'current', 'names_x0', 'names_x1', 'layer_x0', 'layer_x1']
HERE = os.path.dirname(os.path.abspath(__file__))


def data_rows(p):
    if not os.path.exists(p):
        return []
    with open(p, encoding='utf-8') as f:
        return [l for l in f.read().splitlines()[1:] if l.strip()]


def append(p, lines, head=None):
    if not lines:
        return
    new = not os.path.exists(p)
    with open(p, 'a', encoding='utf-8', newline='\n') as f:
        if new and head:
            f.write(head + '\n')
        f.write(''.join(l + '\n' for l in lines))


def merge_review(out, src):
    """作業場所の user_review.tsv を列名で合わせて <出力>/user_review.tsv に足す．共有の見出しは RCOLS にそろえる
    (ほかの列は捨てて警告する)．足した件数を返す"""
    dst = os.path.join(out, 'user_review.tsv')
    old = []
    if os.path.exists(dst):
        with open(dst, encoding='utf-8') as f:
            old = [l.rstrip('\r\n').split('\t') for l in f]
    oh = old[0] if old else RCOLS
    rows = [dict(zip(oh, r)) for r in old[1:] if any(x.strip() for x in r)]
    n = 0
    if os.path.exists(src):
        with open(src, encoding='utf-8') as f:
            sl = [l.rstrip('\r\n').split('\t') for l in f]
        if sl:
            sh = sl[0]
            for c in sh:
                if c not in RCOLS:
                    print(f'  !! user_review の未知の列 {c} ({src})')
            new = [dict(zip(sh, r)) for r in sl[1:] if any(x.strip() for x in r)]
            rows += new
            n = len(new)
    with open(dst, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\t'.join(RCOLS) + '\n')
        for d in rows:
            f.write('\t'.join(d.get(c, '') for c in RCOLS) + '\n')
    return n


def merge_one(out, tab, again=False, run_tables=True):
    """1 表を取り込む．取り込んだら (status, 確認事項の件数)，取り込まなければ None を返す"""
    merged = os.path.join(out, 'scratch', 'merged.txt')
    done = set()
    if os.path.exists(merged):
        with open(merged, encoding='utf-8') as f:
            done = set(f.read().split())
    num = tab.split('.')[1]
    w = os.path.join(out, 'scratch', 't' + num)
    st = os.path.join(w, 'status.tsv')
    if tab in done and not again:
        print(tab, 'すでに取り込み済み (取り込み直すなら --again)')
        return None
    if not os.path.exists(st):
        print(tab, 'status.tsv が無い')
        return None
    with open(st, encoding='utf-8') as f:
        s = f.read().strip().split('\t')
    status = s[1] if len(s) > 1 and s[1] else 'reading'
    title = s[2] if len(s) > 2 and s[2] else None
    note = s[3] if len(s) > 3 and s[3] else None
    src = os.path.join(w, 'out', 'transcripts', tab)
    if not os.path.isdir(src):
        print(tab, '転記が無い', src)
        return None
    dst = os.path.join(out, 'transcripts', tab)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    log = os.path.join(w, 'log.md')
    if os.path.exists(log):
        with open(log, encoding='utf-8') as f:
            body = f.read().strip()
        with open(os.path.join(out, 'reading_log.md'), 'a', encoding='utf-8', newline='\n') as f:
            f.write('\n' + body + '\n')
    nrev = merge_review(out, os.path.join(w, 'user_review.tsv'))
    for k in ('auto_list_kasure.tsv', 'auto_list_paren.tsv'):
        r = data_rows(os.path.join(w, k))
        if r:
            with open(os.path.join(w, k), encoding='utf-8') as f:
                head = f.readline().rstrip('\r\n')
            append(os.path.join(out, k), r, head)
    imp = os.path.join(w, 'improve.txt')
    if os.path.exists(imp):
        with open(imp, encoding='utf-8') as f:
            lines = [tab + '\t' + l for l in f.read().splitlines() if l.strip()]
        append(os.path.join(out, 'improve_notes.txt'), lines)
    if run_tables:
        cmd = [sys.executable, '-I', os.path.join(HERE, 'tables.py'), 'set', out, tab, status]
        if title:
            cmd += ['--title', title]
        if note and status != 'done':
            cmd += ['--note', note]
        subprocess.run(cmd, check=True)
    if tab not in done:
        os.makedirs(os.path.dirname(merged), exist_ok=True)
        with open(merged, 'a', encoding='utf-8') as f:
            f.write(tab + '\n')
    print(tab, status, f'取り込んだ (確認事項 {nrev} 件)')
    return status, nrev


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    ap = argparse.ArgumentParser(description='表ごとの作業場所 scratch/tNNN/ の結果を共有のファイルへ取り込む')
    ap.add_argument('out', help='出力 (地方の置き場)')
    ap.add_argument('tables', nargs='+', help='Tab.038 の形')
    ap.add_argument('--again', action='store_true', help='取り込み済みの表を取り込み直す')
    a = ap.parse_args(argv)
    for t in a.tables:
        merge_one(a.out, t, again=a.again)


if __name__ == '__main__':
    sys.exit(main())
