#!/usr/bin/env python3
"""build-index のスクリプトの自己テスト.

    python tests/test_build_index.py

並べ方・ページ範囲の書式・主要ページ・点検は，標準ライブラリだけで試せる．
PDF の検索と，索引を組むところまでの試験は pypdfium2 と pyyaml が要る (無ければ飛ばす)．
よみの補助の試験のうち，pykakasi 本体を使うものは pykakasi が無ければ飛ばす．
試験用の PDF は ../../../examples/index/sample_book.pdf を使う．
"""

import importlib.util
import os
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "scripts"))
EXAMPLE = os.path.normpath(os.path.join(HERE, "..", "..", "..", "examples", "index"))

try:
    import pypdfium2  # noqa: F401
    HAVE_PDFIUM = True
except ImportError:
    HAVE_PDFIUM = False
try:
    import yaml  # noqa: F401
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False
try:
    import pykakasi  # noqa: F401
    HAVE_KAKASI = True
except ImportError:
    HAVE_KAKASI = False


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bi = load("build_index")
sy = load("suggest_yomi")


def run(script, args, cwd=None):
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args,
                       cwd=cwd, capture_output=True)
    return (r.returncode, r.stdout.decode("utf-8").replace("\r\n", "\n"),
            r.stderr.decode("utf-8").replace("\r\n", "\n"))


def order(yomis):
    return sorted(yomis, key=bi.sort_key)


class TestSortKey(unittest.TestCase):
    def test_seion_dakuon_handakuon(self):
        # 清音 → 濁音 → 半濁音
        self.assertEqual(order(["ぴょう", "びょう", "ひょう"]), ["ひょう", "びょう", "ぴょう"])
        self.assertEqual(order(["がん", "かん", "かな"]), ["かな", "かん", "がん"])

    def test_dakuten_compared_left_to_right(self):
        # 基本の仮名が同じなら，左の文字の清濁から比べる
        self.assertEqual(order(["ばんは", "はんぱ"]), ["はんぱ", "ばんは"])

    def test_primary_before_dakuten(self):
        # 濁音でも，基本の仮名が先の語が前 (がす < かた)
        self.assertEqual(order(["かた", "がす"]), ["がす", "かた"])

    def test_long_mark_counts_as_previous_vowel(self):
        # 長音符は直前の母音と同じ．同じ母音が並ぶ語どうしでは長音符のある語が先
        self.assertEqual(order(["ゆうくりっど", "ゆーくりっど"]), ["ゆーくりっど", "ゆうくりっど"])
        # 長音符は「あ」として数えるので，「い」より先
        self.assertEqual(order(["ゆえくりっど", "ゆーくりっど"]), ["ゆーくりっど", "ゆえくりっど"])
        # 母音は直前の仮名で決まる (き → い)
        self.assertEqual(order(["きいろ", "きーろ", "きうろ"]), ["きーろ", "きいろ", "きうろ"])

    def test_long_mark_without_long_mark_prefix(self):
        # 長音符の語が長く続くとき，音が違えば音順
        self.assertEqual(order(["おーぶん", "おかし", "おおかみ"]), ["おおかみ", "おーぶん", "おかし"])

    def test_small_kana_sound_order(self):
        # 小書きの仮名・促音・拗音は，大きい仮名として音順に数える
        self.assertEqual(order(["じょれっか", "じょれつか", "じょれき"]), ["じょれき", "じょれつか", "じょれっか"])
        # 同じ音なら大きい仮名が先
        self.assertEqual(order(["しょくせい", "しよくせい"]), ["しよくせい", "しょくせい"])

    def test_katakana_yomi_same_as_hiragana(self):
        self.assertEqual(bi.sort_key("ユークリッド"), bi.sort_key("ゆーくりっど"))
        self.assertEqual(order(["ベータ", "へいや", "へあ"]), ["へあ", "へいや", "ベータ"])  # ー は え 段 (べ) の「え」

    def test_nakaguro_after_plain(self):
        self.assertEqual(order(["ぶれい・かーていす", "ぶれいかーていす"]), ["ぶれいかーていす", "ぶれい・かーていす"])

    def test_latin_after_kana_case_insensitive(self):
        self.assertEqual(order(["PCA", "ecan", "わに", "あか", "NMDS"]),
                         ["あか", "わに", "ecan", "NMDS", "PCA"])

    def test_row_of(self):
        self.assertEqual(bi.row_of("じゅけいず"), "さ")
        self.assertEqual(bi.row_of("ひど"), "は")
        self.assertEqual(bi.row_of("おーでぃねーしょん"), "あ")
        self.assertEqual(bi.row_of("しょくせい"), "さ")
        self.assertEqual(bi.row_of("ヴぁいおりん"), "あ")  # ヴ → う (濁音)
        self.assertEqual(bi.row_of("ゐど"), "わ")
        self.assertEqual(bi.row_of("pH"), "英字")
        self.assertEqual(bi.row_of(""), "英字")

    def test_to_hira(self):
        self.assertEqual(bi.to_hira("ユークリッド"), "ゆーくりっど")
        self.assertEqual(bi.to_hira("ヶ"), "け")


class TestFmtPages(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(bi.fmt_pages([1, 2, 3, 7, 9, 10]), "1-3, 7, 9-10")

    def test_range_min(self):
        self.assertEqual(bi.fmt_pages([1, 2, 5], range_min=3), "1, 2, 5")
        self.assertEqual(bi.fmt_pages([1, 2, 3], range_min=3), "1-3")

    def test_unsorted_and_duplicates(self):
        self.assertEqual(bi.fmt_pages([5, 3, 4, 3]), "3-5")

    def test_main_is_bold(self):
        self.assertEqual(bi.fmt_pages([3, 8, 20], main=[8]), "3, **8**, 20")

    def test_main_breaks_range(self):
        # 主要ページを含む範囲は崩す
        self.assertEqual(bi.fmt_pages([12, 13, 14], main=[13]), "12, **13**, 14")
        self.assertEqual(bi.fmt_pages([20, 21, 22, 23, 24, 25], main=[22]), "20-21, **22**, 23-25")
        self.assertEqual(bi.fmt_pages([5, 6, 7], main=[5]), "**5**, 6-7")
        self.assertEqual(bi.fmt_pages([5, 6, 7], main=[7]), "5-6, **7**")

    def test_main_not_in_pages_is_ignored(self):
        self.assertEqual(bi.fmt_pages([3, 4], main=[10]), "3-4")


class FakeBook:
    def __init__(self, labels, found=None):
        self.labels = labels
        self.skip = set()
        self._found = found or {}

    def find(self, words, chapters):
        out = []
        for w in words:
            out += self._found.get(w, [])
        return sorted(set(out))


def entry(name, yomi="あ", **kw):
    d = {"見出し": name, "よみ": yomi, "_pages": [1], "_main": []}
    d.update(kw)
    return d


class TestResolveAndRender(unittest.TestCase):
    def test_main_pages_are_added_and_bold(self):
        book = FakeBook(list(range(1, 100)), {"方形区": [10, 11]})
        entries = [{"見出し": "方形区", "よみ": "ほうけいく", "主": [12, 40]}]
        bi.resolve(entries, book)
        self.assertEqual(entries[0]["_pages"], [10, 11, 12, 40])
        self.assertEqual(entries[0]["_main"], [12, 40])
        text, lines = bi.render(entries, "索引", 2)
        self.assertIn("方形区  10-11, **12**, **40**", text)
        self.assertEqual(lines, 1)

    def test_main_as_single_int(self):
        book = FakeBook(list(range(1, 100)), {"x": [3]})
        entries = [{"見出し": "x", "よみ": "えっくす", "主": 7}]
        bi.resolve(entries, book)
        self.assertEqual(entries[0]["_pages"], [3, 7])

    def test_manual_pages_replace_search(self):
        book = FakeBook(list(range(1, 100)), {"a": [1, 2, 3]})
        entries = [{"見出し": "a", "よみ": "あ", "ページ": [45, 88]}]
        bi.resolve(entries, book)
        self.assertEqual(entries[0]["_pages"], [45, 88])

    def test_sub_entries_inherit_chapters(self):
        seen = []

        class B(FakeBook):
            def find(self, words, chapters):
                seen.append(chapters)
                return [1]
        entries = [{"見出し": "a", "よみ": "あ", "章": [2], "副": [{"見出し": "b", "よみ": "い"}]}]
        bi.resolve(entries, B([1]))
        self.assertEqual(seen, [[2], [2]])

    def test_render_order_rows_refs_and_subs(self):
        entries = [
            entry("ユークリッド", "ゆーくりっど", _pages=[3, 5]),
            entry("被度", "ひど", _pages=[6]),
            entry("序列化", "じょれつか", _pages=[2, 5, 6], _main=[5],
                  副=[entry("対応分析", "たいおうぶんせき", _pages=[6]),
                      entry("主成分分析", "しゅせいぶんぶんせき", _pages=[5])],
                  も見よ=["被度"]),
            entry("コドラート", "こどらーと", 参照="方形区"),
            entry("方形区", "ほうけいく", _pages=[1]),
            entry("pH", "pH", _pages=[8]),
        ]
        text, lines = bi.render(entries, "索引", 2)
        self.assertEqual(lines, 8)
        want = ["## か", "コドラート → 方形区", "## さ", "序列化  2, **5**, 6  被度 も見よ",
                "    主成分分析  5", "    対応分析  6", "## は", "被度  6", "方形区  1",
                "## や", "ユークリッド  3, 5", "## 英字", "pH  8"]
        got = [ln for ln in text.splitlines() if ln]
        self.assertEqual(got[1:], want)  # 先頭は見出し
        self.assertTrue(got[0].startswith("# 索引"))


class TestCheck(unittest.TestCase):
    def setUp(self):
        self.book = FakeBook(list(range(1, 101)))
        self.meta = {"1ページの行数": 45}

    def errs(self, entries, lines=2):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            return bi.check(entries, self.meta, self.book, lines)

    def test_clean(self):
        errors, _ = self.errs([entry("a", "あ"), entry("b", "い")])
        self.assertEqual(errors, [])

    def test_cycle(self):
        errors, _ = self.errs([entry("A", "あ", 参照="B"), entry("B", "い", 参照="C"), entry("C", "う")])
        self.assertTrue(any("循環" in e and "A → B → C" in e for e in errors), errors)

    def test_self_and_missing_reference(self):
        errors, _ = self.errs([entry("A", "あ", 参照="A"), entry("B", "い", 参照="Z")])
        self.assertTrue(any("自分自身への参照" in e for e in errors))
        self.assertTrue(any("参照先が索引に無い" in e for e in errors))

    def test_see_also_missing_and_self(self):
        errors, _ = self.errs([entry("A", "あ", も見よ=["A", "Z"])])
        self.assertTrue(any("自分自身を" in e for e in errors))
        self.assertTrue(any("「も見よ」の先が索引に無い" in e for e in errors))

    def test_missing_yomi(self):
        errors, _ = self.errs([entry("A", ""), entry("B", "い", 副=[entry("C", "")])])
        self.assertTrue(any(e.startswith("よみが無い: A") for e in errors))
        self.assertTrue(any("副見出しのよみが無い" in e for e in errors))

    def test_yomi_must_be_kana_or_latin(self):
        errors, _ = self.errs([entry("方形区", "方形区")])
        self.assertTrue(any("ひらがな" in e for e in errors))

    def test_duplicate_headings(self):
        errors, _ = self.errs([entry("A", "あ"), entry("A", "い")])
        self.assertTrue(any("重複" in e for e in errors))

    def test_main_out_of_range_is_error(self):
        errors, _ = self.errs([entry("A", "あ", 主=[500])])
        self.assertTrue(any("主要ページ" in e and "500" in e for e in errors), errors)
        errors, _ = self.errs([entry("A", "あ", 副=[entry("B", "い", 主=[0])])])
        self.assertTrue(any("A > B" in e for e in errors), errors)

    def test_main_in_range_is_ok(self):
        errors, _ = self.errs([entry("A", "あ", 主=[1, 100])])
        self.assertEqual(errors, [])

    def test_volume_warning(self):
        # 本文 100 ページの 2-3% = 2-3 ページ = 90-135 行
        _, warns = self.errs([entry("a", "あ")], lines=10)
        self.assertTrue(any("少ない" in w for w in warns), warns)
        _, warns = self.errs([entry("a", "あ")], lines=300)
        self.assertTrue(any("多い" in w for w in warns), warns)
        _, warns = self.errs([entry("a", "あ")], lines=100)
        self.assertFalse(any("分量" in w for w in warns), warns)

    def test_many_pages_without_subs_warns(self):
        _, warns = self.errs([entry("a", "あ", _pages=[1, 2, 3, 4, 5, 6])], lines=100)
        self.assertTrue(any("副見出し" in w for w in warns))

    def test_not_found_warns(self):
        _, warns = self.errs([entry("a", "あ", _pages=[])], lines=100)
        self.assertTrue(any("PDF に見つからない" in w for w in warns))


@unittest.skipUnless(HAVE_PDFIUM, "pypdfium2 が無い")
class TestBook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book = bi.Book(os.path.join(EXAMPLE, "sample_book.pdf"))

    def test_offset_by_majority(self):
        # 1ページ目は目次 (ノンブル無し)．本文は2ページ目から 1
        self.assertEqual(self.book.labels[0], 0)
        self.assertEqual(self.book.labels[1], 1)
        self.assertEqual(self.book.labels[-1], len(self.book.labels) - 1)

    def test_explicit_offset(self):
        b = bi.Book(os.path.join(EXAMPLE, "sample_book.pdf"), offset=10)
        self.assertEqual(b.labels[0], 11)

    def test_toc_and_chapters(self):
        self.assertEqual(sorted(self.book.chapter_ranges()), ["1", "2", "3"])
        r1 = self.book.chapter_ranges()["1"]
        self.assertEqual(r1[0], 1)
        self.assertTrue(self.book.section_of(1).startswith("1."))  # 一番近い見出し (節)

    def test_front_matter_is_skipped(self):
        self.assertEqual(self.book.skip, {0})
        # 目次ページにしか無い語 (本のタイトル) は見つからない
        self.assertEqual(self.book.find(["植生解析入門"], None), [])

    def test_find_and_chapter_filter(self):
        everywhere = self.book.find(["群集"], None)
        self.assertIn(2, everywhere)
        in_ch3 = self.book.find(["群集"], [3])
        self.assertTrue(in_ch3)
        self.assertTrue(set(in_ch3) < set(everywhere))
        self.assertTrue(min(in_ch3) > 6)

    def test_find_across_line_breaks(self):
        # 行の折り返しをまたぐ語も，空白を落として探すので見つかる
        self.assertTrue(self.book.find(["ブレイ・カーティス距離"], None))

    def test_exclude_section(self):
        b = bi.Book(os.path.join(EXAMPLE, "sample_book.pdf"))
        before = b.find(["群集"], None)
        b.exclude_section("第3章")
        after = b.find(["群集"], None)
        self.assertTrue(set(after) < set(before))


@unittest.skipUnless(HAVE_PDFIUM and HAVE_YAML, "pypdfium2 または pyyaml が無い")
class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_example_matches_expected(self):
        out = os.path.join(self.tmp.name, "index.md")
        rc, so, se = run("build_index.py", [os.path.join(EXAMPLE, "terms.yaml"), "-o", out], cwd=self.tmp.name)
        self.assertEqual(rc, 0, se)
        with open(out, encoding="utf-8") as f:
            got = f.read()
        with open(os.path.join(EXAMPLE, "index.md"), encoding="utf-8") as f:
            want = f.read()
        self.assertEqual(got.replace("\r\n", "\n"), want.replace("\r\n", "\n"))
        self.assertIn("見出し", so)  # 日本語が UTF-8 で出る
        self.assertIn("**10**", got)

    def test_report_marks_main(self):
        rc, so, _ = run("build_index.py", [os.path.join(EXAMPLE, "terms.yaml"), "--check-only", "--report"])
        self.assertEqual(rc, 0)
        self.assertIn("(主)", so)

    def test_main_out_of_range_fails(self):
        terms = os.path.join(self.tmp.name, "terms.yaml")
        with open(terms, "w", encoding="utf-8") as f:
            f.write("meta:\n  pdf: %s\nentries:\n  - 見出し: 方形区\n    よみ: ほうけいく\n    主: [99]\n"
                    % os.path.join(EXAMPLE, "sample_book.pdf").replace("\\", "/"))
        rc, _, se = run("build_index.py", [terms, "--check-only"])
        self.assertEqual(rc, 1)
        self.assertIn("主要ページ", se)

    def test_missing_yomi_fails_with_hint(self):
        terms = os.path.join(self.tmp.name, "terms.yaml")
        with open(terms, "w", encoding="utf-8") as f:
            f.write("entries:\n  - 見出し: 方形区\n")
        rc, so, se = run("build_index.py", [terms, "-p", os.path.join(EXAMPLE, "sample_book.pdf"), "--check-only"])
        self.assertEqual(rc, 1)
        self.assertIn("よみが無い", se)
        self.assertIn("suggest_yomi.py", so)

    def test_missing_pdf(self):
        terms = os.path.join(self.tmp.name, "terms.yaml")
        with open(terms, "w", encoding="utf-8") as f:
            f.write("meta:\n  pdf: no_such.pdf\nentries: []\n")
        rc, _, se = run("build_index.py", [terms])
        self.assertEqual(rc, 2)
        self.assertIn("PDF が見つかりません", se)


@unittest.skipUnless(HAVE_YAML, "pyyaml が無い")
class TestHelpers(unittest.TestCase):
    def test_extract_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = [os.path.join(EXAMPLE, "chapter_0%d.md" % i) for i in (1, 2, 3)]
            rc, so, se = run("extract_candidates.py", files + ["-o", tmp])
            self.assertEqual(rc, 0, se)
            with open(os.path.join(tmp, "candidates_chapter_01.md"), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("| 組成表 |", text)
            self.assertIn("被度", text)
            self.assertTrue(os.path.exists(os.path.join(tmp, "candidates_all.md")))
            # 複数の章に出る語は，全章の表に章を並べて載る
            with open(os.path.join(tmp, "candidates_all.md"), encoding="utf-8") as f:
                allt = f.read()
            self.assertRegex(allt, r"\| 群集 \| 01, 02, 03 \|")

    def test_sample_paragraphs(self):
        files = [os.path.join(EXAMPLE, "chapter_0%d.md" % i) for i in (1, 2, 3)]
        rc, so, se = run("sample_paragraphs.py", files + ["-n", "3", "-t", os.path.join(EXAMPLE, "terms.yaml")])
        self.assertEqual(rc, 0, se)
        self.assertIn("索引で引ける見出し", so)


class TestSuggestYomi(unittest.TestCase):
    class Fake:
        TABLE = {"方形区": "ほうけいく", "序列化": "じょれつか", "主成分分析": "しゅせいぶんぶんせき", "ユークリッド": "ユークリッド"}

        def convert(self, text):
            return [{"orig": text, "hira": self.TABLE.get(text, text)}]

    def test_suggest_only_missing(self):
        entries = [
            {"見出し": "方形区"},
            {"見出し": "ユークリッド", "よみ": "ゆーくりっど"},
            {"見出し": "pH"},
            {"見出し": "序列化", "副": [{"見出し": "主成分分析"}]},
        ]
        rows = sy.suggest(entries, self.Fake())
        self.assertEqual([(r[1], r[3]) for r in rows],
                         [("方形区", "ほうけいく"), ("序列化", "じょれつか"), ("主成分分析", "しゅせいぶんぶんせき")])

    def test_all_shows_only_mismatch(self):
        entries = [{"見出し": "方形区", "よみ": "ほうけいく"}, {"見出し": "序列化", "よみ": "じょれっか"}]
        rows = sy.suggest(entries, self.Fake(), show_all=True)
        self.assertEqual([(r[1], r[2], r[3]) for r in rows], [("序列化", "じょれっか", "じょれつか")])

    def test_cli_without_pykakasi_exits_zero(self):
        if HAVE_KAKASI:
            self.skipTest("pykakasi が入っている")
        with tempfile.TemporaryDirectory() as tmp:
            terms = os.path.join(tmp, "t.yaml")
            with open(terms, "w", encoding="utf-8") as f:
                f.write("entries:\n  - 見出し: 方形区\n")
            rc, so, _ = run("suggest_yomi.py", [terms])
            self.assertEqual(rc, 0)
            self.assertIn("pip install pykakasi", so)

    @unittest.skipUnless(HAVE_KAKASI and HAVE_YAML, "pykakasi または pyyaml が無い")
    def test_cli_with_pykakasi_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            terms = os.path.join(tmp, "t.yaml")
            body = "entries:\n  - 見出し: 方形区\n"
            with open(terms, "w", encoding="utf-8") as f:
                f.write(body)
            rc, so, _ = run("suggest_yomi.py", [terms])
            self.assertEqual(rc, 0)
            self.assertIn("要確認", so)
            with open(terms, encoding="utf-8") as f:
                self.assertEqual(f.read(), body)


if __name__ == "__main__":
    unittest.main(verbosity=1)
