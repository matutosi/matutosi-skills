"""決定の決まり (D 規則)．転記は印字のまま固定し，決定を作るときにここの規則を当てる．

1 つの規則は 1 つの関数．`@rule('D03', ...)` で登録する．
関数は表 (common.Table) と設定の値 (rule_settings.tsv の param) を受け取り，直すセルを Change で返す (表は書き換えない)．
当てる順は番号の順．採否は rule_settings.tsv (列: rule use param note) で決め，全地方で 1 つ．
"""
import collections
import importlib
import os

Change = collections.namedtuple('Change', 'kind row col new why')
Rule = collections.namedtuple('Rule', 'id title group old fn')
RULES = []


def rule(rid, title, group, old=''):
    """規則を登録する．old は今のスキル (veg-table-to-csv) の規則の番号 (X8 など)"""
    def deco(fn):
        if any(r.id == rid for r in RULES):
            raise ValueError(f'規則の番号が重なる: {rid}')
        RULES.append(Rule(rid, title, group, old, fn))
        RULES.sort(key=lambda r: r.id)
        return fn
    return deco


def load_all():
    """rules/ の規則のファイルを全部読み込み，登録済みの規則を返す"""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in sorted(os.listdir(here)):
        if name.endswith('.py') and not name.startswith('_'):
            importlib.import_module(f'rules.{name[:-3]}')
    return RULES
