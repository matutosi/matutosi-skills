"""雑誌ごとの設定 (journals/<資料コード>.yaml) を読む．

build.py・extract.py・extract_scan.py・fetch_jstage.py・from_backup.py が共通で使う．
PyMuPDF などの重い道具に頼らないので，どのスクリプトからも読み込める．
"""
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parent.parent


def load_profile(name):
    """資料コード (vegsci など) の設定を辞書で返す．"""
    path = SKILL_DIR / "journals" / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def as_list(v):
    """設定の節の見出しは，文字列でも並びでも書ける (「引用文献」と「文献」)．並びにそろえる．"""
    return [v] if isinstance(v, str) else list(v)
