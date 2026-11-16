"""決定の決まりの一覧 (references/rules.md) を規則の登録から作る (2026-11-17 ユーザ決定 3a)．

    python scripts/rule_list.py                  # references/rules.md を書き直す
    python scripts/rule_list.py --check          # 一覧が古くないかだけ見る (古ければ終了コード 1)
    python scripts/rule_list.py --settings <rule_settings.tsv>   # 採否の列を足して画面に出す (ファイルは書かない)

一覧は手で直さない．規則を足したり変えたりしたら，これで作り直す (テストが古い一覧を見つける)．
採否は置き場のデータ (rule_settings.tsv) なので，リポジトリの一覧には入れない．
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
OUT = os.path.join(SKILL, 'references', 'rules.md')
TESTS = os.path.join(SKILL, 'tests', 'test_csv2.py')
NL = chr(10)


def tested_ids():
    """テストに出てくる規則の番号 (D03 など)"""
    if not os.path.exists(TESTS):
        return set()
    with open(TESTS, encoding='utf-8') as f:
        return set(re.findall(r'\b([DT]\d\d)\b', f.read()))


def cell(s):
    return (s or '').replace('|', '\\|').replace(NL, ' ')


def markdown(rule_list, settings=None, internal=None):
    """一覧の Markdown．settings は {番号: (使うか, param)} (渡したときだけ採否の列を出す)．
    internal は to_csv.py の中の決まり [(番号, 題, 今の規則)]"""
    import rules as rules_pkg
    tested = tested_ids()
    out = ['# 決定の決まりの一覧', '',
           '`scripts/rule_list.py` が規則の登録 (`scripts/rules/`) から作る．**手で直さない**．', '',
           '当てる順は**段の順**．段の中は番号の順 (D26 は段 6 の中で D11 より先)．番号は振り直さない (抜けた番号も再利用しない)．',
           '採否は置き場の `rule_settings.tsv` で決める (この一覧には入れない)．', '']
    for st, name in rules_pkg.STAGES.items():
        rs = [r for r in rule_list if r.stage == st]
        if not rs:
            continue
        out += [f'## 段 {st}: {name}', '']
        head = '| 番号 | 中身 | 今のスキルの規則 | テスト |'
        line = '|---|---|---|---|'
        if settings is not None:
            head += ' 採否 |'
            line += '---|'
        out += [head, line]
        for r in rs:
            row = f'| {r.id} | {cell(r.title)} | {cell(r.old) or "-"} | {"あり" if r.id in tested else "なし"} |'
            if settings is not None:
                use, param = settings.get(r.id, (True, ''))
                row += f' {"採用" if use else "不採用"}{" (" + cell(param) + ")" if param else ""} |'
            out.append(row)
        out.append('')
    if internal:
        out += ['## to_csv.py の中の決まり (T 規則)', '',
                '今のスキルの `to_csv.py` が CSV を組むときに当てる決まり．中身は書き直さず，当たったセルの `note_judge` に番号を出す．', '',
                '| 番号 | 中身 | 今のスキルの規則 | テスト |', '|---|---|---|---|']
        for rid, title, old in internal:
            out.append(f'| {rid} | {cell(title)} | {cell(old) or "-"} | {"あり" if rid in tested else "なし"} |')
        out.append('')
    return NL.join(out)


def build(settings=None):
    sys.path.insert(0, HERE)
    import rules as rules_pkg
    import internal_rules
    return markdown(rules_pkg.load_all(), settings, internal_rules.INTERNAL)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--check', action='store_true', help='一覧が古くないかだけ見る')
    ap.add_argument('--settings', default='', help='rule_settings.tsv (採否の列を足して画面に出す)')
    a = ap.parse_args(argv)
    if a.settings:
        sys.path.insert(0, HERE)
        import decide
        print(build(decide.load_settings(a.settings)))
        return 0
    text = build()
    old = open(OUT, encoding='utf-8').read() if os.path.exists(OUT) else ''
    if a.check:
        if old.replace('\r\n', NL) != text:
            print(f'一覧が古い: {OUT}．python scripts/rule_list.py で作り直す')
            return 1
        print('一覧は新しい')
        return 0
    with open(OUT, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    print(f'書いた: {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
