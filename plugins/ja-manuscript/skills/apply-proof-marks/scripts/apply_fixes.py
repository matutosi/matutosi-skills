#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""朱書きの反映を、置換リストからまとめて適用する (入口)。

本体は同じ置き場 (プラグインなら同じプラグイン) の polish-loop/scripts/apply_fixes.py。
引数はそのまま渡す。使い方・置換リストの形・警告の中身は本体の説明を見る。

    python apply_fixes.py fixes.json              # 確認だけ(何も書かない)
    python apply_fixes.py fixes.json --apply      # 適用する
"""
import runpy
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "polish-loop" / "scripts" / "apply_fixes.py"

if __name__ == "__main__":
    if not CORE.exists():
        sys.exit("本体が見つからない: %s (polish-loop のスキルが要る)" % CORE)
    sys.argv[0] = str(CORE)
    runpy.run_path(str(CORE), run_name="__main__")
