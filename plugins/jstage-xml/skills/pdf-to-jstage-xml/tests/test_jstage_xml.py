#!/usr/bin/env python3
"""pdf-to-jstage-xml のスクリプトの自己テスト (ネットに出ない範囲).

    python tests/test_jstage_xml.py

- すべてのスクリプトが構文として正しいこと
- 和欧間の空白 (ja_space.py) の決めごと
- 記事識別子の対応表と体裁の調査の置き場が，作業の根 (JSTAGE_ROOT) に向くこと
- 雑誌の設定 (journals/*.yaml) が読め，必須の項目があること (PyYAML が無ければ飛ばす)
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCompile(unittest.TestCase):
    def test_all_scripts_compile(self):
        for p in sorted(SCRIPTS.rglob("*.py")):
            with self.subTest(script=p.name):
                compile(p.read_text(encoding="utf-8"), str(p), "exec")


class TestJaSpace(unittest.TestCase):
    def setUp(self):
        self.js = load("ja_space")

    def test_space_between_japanese_and_digits(self):
        self.assertEqual(self.js.fix_text("3月から5月"), "3 月から 5 月")

    def test_idempotent(self):
        once = self.js.fix_text("舘脇1948によると16.2%に増えた")
        self.assertEqual(self.js.fix_text(once), once)


class TestWorkRoot(unittest.TestCase):
    """対応表と調査の PDF は，プラグインの中ではなく作業の根に置く．"""

    def test_article_ids_csv_in_work_root(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["JSTAGE_ROOT"] = d
            try:
                mod = load("article_ids")
            finally:
                del os.environ["JSTAGE_ROOT"]
            self.assertEqual(mod.CSV, Path(d).resolve() / "article_ids.csv")

    @unittest.skipUnless(importlib.util.find_spec("pymupdf"), "PyMuPDF が要る")
    def test_fingerprint_cache_in_work_root(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["JSTAGE_ROOT"] = d
            try:
                mod = load("pdf_fingerprint")
            finally:
                del os.environ["JSTAGE_ROOT"]
            self.assertEqual(mod.CACHE, Path(d).resolve() / "_fingerprint")


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestJournals(unittest.TestCase):
    def test_journal_settings_have_required_keys(self):
        for p in sorted((SKILL / "journals").glob("*.yaml")):
            if p.name.startswith("_"):
                continue
            with self.subTest(journal=p.name):
                prof = yaml.safe_load(p.read_text(encoding="utf-8"))
                for key in ("journal_id", "issn", "title"):
                    self.assertIn(key, prof)
                self.assertEqual(prof["journal_id"], p.stem)


if __name__ == "__main__":
    unittest.main()
