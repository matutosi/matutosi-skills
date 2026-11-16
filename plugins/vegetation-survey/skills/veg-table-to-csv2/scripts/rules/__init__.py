"""決定の決まり (D 規則)．転記は印字のまま固定し，決定を作るときにここの規則を当てる．

1 つの規則は 1 つの関数．`@rule('D03', '題', 段, old='X8')` で登録する．
関数は表 (common.Table) と設定の値 (rule_settings.tsv の param) を受け取り，直すセルを Change で返す (表は書き換えない)．

**当てる順は段の順**．段の中は番号の順 (`order` を付けた規則はその位置)．番号の順には頼らない．
段とファイル (2026-11-17 ユーザ決定 1a・2a):

    段 1 s1_glyph.py   字の乱れを整える   値の意味は変えない．ほかの規則が値を読む前に当てる
    段 2 s2_format.py  書式をそろえる     常在度の書き方
    段 3 s3_names.py   名前を直す         段 5・6 はこの後 (学名で引く・種を数える)
    段 4 s4_header.py  表頭を直す         県名・方位・同左・高さ・年
    段 5 s5_layer.py   階層を直す
    段 6 s6_move.py    行を移す           1 回出現の段落の地点

**番号は振り直さない** (CSV の note_judge・decisions.tsv に残っているため)．抜けた番号・不採用の番号も再利用しない．
共通の部品は _lib.py．採否は rule_settings.tsv (列: rule use param note) で決め，全地方で 1 つ．
"""
import collections
import importlib
import os
import re

Change = collections.namedtuple('Change', 'kind row col new why')
Rule = collections.namedtuple('Rule', 'id title group old fn order stage')
RULES = []
STAGES = collections.OrderedDict([
    (1, '字の乱れを整える'), (2, '書式をそろえる'), (3, '名前を直す'),
    (4, '表頭を直す'), (5, '階層を直す'), (6, '行を移す')])


def rule(rid, title, stage, old='', order=None):
    """規則を登録する．stage は段 (1-6)．old は今のスキル (veg-table-to-csv) の規則の番号 (X8 など)．
    order は段の中の順 (省くと番号の数字．段の中で先に当てたいときに小数で指定する)"""
    if stage not in STAGES:
        raise ValueError(f'{rid}: 段 {stage} は無い (1-6)')

    def deco(fn):
        if any(r.id == rid for r in RULES):
            raise ValueError(f'規則の番号が重なる: {rid}')
        num = float(re.sub(r'\D', '', rid) or 0) if order is None else float(order)
        RULES.append(Rule(rid, title, STAGES[stage], old, fn, num, stage))
        RULES.sort(key=lambda r: (r.stage, r.order, r.id))
        return fn
    return deco


def load_all():
    """rules/ の段のファイル (s1_…-s6_…) を全部読み込み，登録済みの規則を当てる順で返す"""
    here = os.path.dirname(os.path.abspath(__file__))
    for name in sorted(os.listdir(here)):
        if re.match(r's\d_.*\.py$', name):
            importlib.import_module(f'rules.{name[:-3]}')
    return RULES
