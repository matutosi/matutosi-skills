#!/usr/bin/env python3
"""すべてのスキルのテストを順に走らせる.

    python run_tests.py

plugins/*/skills/*/tests/test_*.py を1つずつ別のプロセスで実行し，
最後に通った数と落ちた数を出す．1つでも落ちたら終了コード 1 を返す．
"""

import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    tests = sorted(glob.glob(os.path.join(ROOT, "plugins", "*", "skills", "*", "tests", "test_*.py")))
    if not tests:
        print("テストが見つからない")
        return 1
    failed = []
    for path in tests:
        name = os.path.relpath(path, ROOT).replace(os.sep, "/")
        print("==", name, flush=True)
        r = subprocess.run([sys.executable, path], cwd=os.path.dirname(os.path.dirname(path)))
        if r.returncode != 0:
            failed.append(name)
    print()
    print("通った: %d / 落ちた: %d" % (len(tests) - len(failed), len(failed)))
    for name in failed:
        print("  落ちた:", name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
