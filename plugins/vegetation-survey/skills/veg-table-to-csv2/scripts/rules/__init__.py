"""決定の決まり (D 規則)．転記は印字のまま固定し，決定を作るときにここの規則を当てる．

1 つの規則は 1 つの関数．`@rule('D03', ...)` で登録する．
関数は表 (common.Table) と設定の値 (rule_settings.tsv の param) を受け取り，直すセルを Change で返す (表は書き換えない)．
当てる順は番号の順 (`order` を付けた規則はその位置．例: D26 は order=10.5 で D11 の前)．
採否は rule_settings.tsv (列: rule use param note) で決め，全地方で 1 つ．
"""
import collections
import importlib
import os
import re

Change = collections.namedtuple('Change', 'kind row col new why')
Rule = collections.namedtuple('Rule', 'id title group old fn order')
RULES = []


def rule(rid, title, group, old='', order=None):
    """規則を登録する．old は今のスキル (veg-table-to-csv) の規則の番号 (X8 など)．
    order は当てる順 (省くと番号の数字．ほかの規則より先に当てたいときに小数で指定する)"""
    def deco(fn):
        if any(r.id == rid for r in RULES):
            raise ValueError(f'規則の番号が重なる: {rid}')
        num = float(re.sub(r'\D', '', rid) or 0) if order is None else float(order)
        RULES.append(Rule(rid, title, group, old, fn, num))
        RULES.sort(key=lambda r: (r.order, r.id))
        return fn
    return deco


def load_all():
    """rules/ の規則のファイルを全部読み込み，登録済みの規則を返す"""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in sorted(os.listdir(here)):
        if name.endswith('.py') and not name.startswith('_'):
            importlib.import_module(f'rules.{name[:-3]}')
    return RULES
