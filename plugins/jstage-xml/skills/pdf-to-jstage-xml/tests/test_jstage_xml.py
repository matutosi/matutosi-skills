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


@unittest.skipUnless(importlib.util.find_spec("pymupdf"), "PyMuPDF が要る")
class TestPdfOpen(unittest.TestCase):
    """パスワード付き PDF を開く (pdfopen.open_pdf)．環境変数 PDF_PASSWORD か --password で渡す．"""

    @classmethod
    def setUpClass(cls):
        import pymupdf
        cls.tmp = tempfile.mkdtemp(prefix="pdfopen_")
        cls.path = os.path.join(cls.tmp, "locked.pdf")
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 72), "abc")
        doc.save(cls.path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="dummy-pw", owner_pw="dummy-pw")
        doc.close()
        cls.mod = load("pdfopen")

    def setUp(self):
        self._saved = os.environ.pop("PDF_PASSWORD", None)

    def tearDown(self):
        os.environ.pop("PDF_PASSWORD", None)
        if self._saved is not None:
            os.environ["PDF_PASSWORD"] = self._saved

    def test_no_password_stops_with_message(self):
        with self.assertRaises(SystemExit) as cm:
            self.mod.open_pdf(self.path)
        self.assertIn("パスワード付き", str(cm.exception))

    def test_wrong_password(self):
        os.environ["PDF_PASSWORD"] = "wrong"
        with self.assertRaises(SystemExit) as cm:
            self.mod.open_pdf(self.path)
        self.assertIn("パスワードが違い", str(cm.exception))

    def test_env_password_opens(self):
        os.environ["PDF_PASSWORD"] = "dummy-pw"
        self.assertIn("abc", self.mod.open_pdf(self.path)[0].get_text())

    def test_password_arg_is_copied_to_env(self):
        import argparse
        ap = argparse.ArgumentParser()
        self.mod.add_arg(ap)
        self.mod.apply(ap.parse_args(["--password", "dummy-pw"]))
        self.assertIn("abc", self.mod.open_pdf(self.path)[0].get_text())

    def test_plain_pdf_still_opens(self):
        import pymupdf
        p = os.path.join(self.tmp, "plain.pdf")
        d = pymupdf.open(); d.new_page().insert_text((72, 72), "xyz"); d.save(p); d.close()
        self.assertIn("xyz", self.mod.open_pdf(p)[0].get_text())


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
class TestBuildInline(unittest.TestCase):
    """build.py の文中の印・図表の参照が，整形式の XML になること．"""

    @classmethod
    def setUpClass(cls):
        cls.b = load("build")

    def wellformed(self, fragment):
        import xml.etree.ElementTree as ET
        ET.fromstring('<p xmlns:xlink="http://www.w3.org/1999/xlink">' + fragment + "</p>")

    def test_angle_bracket_url_is_wellformed(self):
        s = self.b.inline(self.b.esc("詳しくは <http://example.org> を見る．"))
        self.wellformed(s)
        self.assertIn('xlink:href="http://example.org"', s)
        self.assertNotIn('&gt"', s)

    def test_tilde_inside_url_is_not_subscript(self):
        text = "http://a.jp/~x/ と http://b.jp/~y/ を見る．"
        s = self.b.inline(self.b.esc(text))
        self.wellformed(s)
        self.assertNotIn("<sub>", s)
        self.assertIn("http://a.jp/~x/", s)
        self.assertIn("http://b.jp/~y/", s)

    def test_url_with_ampersand_query(self):
        s = self.b.inline(self.b.esc("http://a.jp/?x=1&y=2 を見る"))
        self.wellformed(s)
        self.assertIn("http://a.jp/?x=1&amp;y=2", s)

    def test_appendix_figure_reference_has_no_control_chars(self):
        # 付図 (FA1) の参照が，制御文字のまま残って XML を壊してはいけない
        s = self.b.para_xml("付図1 を見よ．", [], {"FA1": "付図1"}, "body")
        self.assertFalse(any(ord(c) < 32 for c in s), repr(s))
        self.assertIn('ref-type="fig" rid="FA1"', s)

    def test_appendix_figure_reference_in_title(self):
        s = self.b.title_xml("付図1 の説明", {"FA1": "付図1"})
        self.assertFalse(any(ord(c) < 32 for c in s), repr(s))


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestBuildFront(unittest.TestCase):
    """<front> の組み立て (誌・著者・所属・脚注・日付・著作権・認証・要旨・キーワード)．"""

    @classmethod
    def setUpClass(cls):
        cls.b = load("build")
        cls.prof = yaml.safe_load((SKILL / "journals" / "vegsci.yaml").read_text(encoding="utf-8"))

    def front(self, **extra):
        meta = {
            "title": {"ja": "題", "en": "Title"},
            "authors": [{"name": {"ja": ["山田", "太郎"], "en": ["Yamada", "Taro"]}, "aff": [1],
                         "ids": [{"type": "orcid", "value": "0000-0001"}], "email": "a@example.org",
                         "corresp": True}],
            "affiliations": [{"id": 1, "ja": "架空大学", "en": "Example University", "country": "JP",
                              "addr": {"ja": "架空市", "en": "Example City"}}],
            "volume": "1", "issue": "2", "fpage": "3",
            "author_notes": [{"type": "present-address", "ja": "現所属: 別大学", "en": "Present address: X"}],
            "registered": {"license": "CC-BY", "approved": "", "kana": [["ヤマダ", "タロウ"]]},
            "copyright": {"statement": {"ja": "© 2026 植生学会", "en": "© 2026 Society"},
                          "holder": {"ja": "植生学会", "en": "Society"}},
            "keywords": {"ja": ["植生"], "en": ["vegetation"]},
            "abstract": {"ja": None, "en": "English abstract."},
        }
        meta.update(extra)
        return self.b.build_front(meta, self.prof, ["和文の要旨．"])

    def test_front_is_wellformed_and_complete(self):
        import xml.etree.ElementTree as ET
        s = self.front()
        ET.fromstring('<r xmlns:xlink="http://www.w3.org/1999/xlink">' + s.replace("<?xml", "<x") + "</r>")
        for piece in ('<contrib-id contrib-id-type="orcid">0000-0001</contrib-id>',
                      'xml:lang="ja-Kana"><surname>ヤマダ</surname>',
                      "<addr-line>架空市</addr-line>",
                      "<author-notes>", '<fn fn-type="present-address">',
                      '<license license-type="CC-BY">',
                      "<copyright-year>2026</copyright-year>",
                      '<date date-type="approved"><day></day>',
                      '<abstract xml:lang="ja"><p>和文の要旨．</p></abstract>',
                      '<trans-abstract xml:lang="en"><p>English abstract.</p></trans-abstract>',
                      '<kwd-group kwd-group-type="author" xml:lang="ja">'):
            self.assertIn(piece, s)
        self.assertIn("<lpage>3</lpage>", s)            # lpage が無いときは fpage と同じ

    def test_no_contrib_group_without_authors(self):
        s = self.front(authors=[], affiliations=[])
        self.assertNotIn("<contrib-group>", s)

    def test_no_permissions_without_copyright_or_license(self):
        s = self.front(copyright={}, registered={})
        self.assertNotIn("<permissions>", s)


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestBuildFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load("build")

    def test_continued_follows_the_extension(self):
        with tempfile.TemporaryDirectory() as d:
            dd = Path(d)
            for n in ("fig1.jpg", "fig1_2.jpg", "fig1.png"):
                (dd / n).write_bytes(b"x")
            self.assertEqual([p.name for p in self.b.continued(dd, "fig1", ".jpg")],
                             ["fig1.jpg", "fig1_2.jpg"])
            self.assertEqual([p.name for p in self.b.continued(dd, "fig1")], ["fig1.png"])

    def test_jpg_figure_gets_a_graphic(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            (work / "figs").mkdir()
            (work / "figs" / "fig1.jpg").write_bytes(b"x")
            names = self.b.GraphicNames("1_1")
            blocks = [("fig", "F1", "図1", "fig1.jpg", ["説明です．"])]
            self.b.REPORT.clear()
            out = self.b.build_body(blocks, [], {"F1": "図1"}, work, names)
            self.assertIn("<graphic ", out)
            self.assertEqual([r for r in self.b.REPORT if "画像が無い" in r], [])

    def test_fig_without_file_name_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            (work / "figs").mkdir()
            (work / "figs" / "fig1.png").write_bytes(b"x")
            names = self.b.GraphicNames("1_1")
            blocks = [("fig", "F1", "図1", None, ["説明です．"])]
            out = self.b.build_body(blocks, [], {"F1": "図1"}, work, names)
            self.assertIn("<graphic ", out)

    def test_missing_figure_number_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "body.md"
            path.write_text(":::fig F1 fig1.png\n説明\n:::\n", encoding="utf-8")
            self.b.REPORT.clear()
            self.b.parse_body(path)
            self.assertTrue([r for r in self.b.REPORT if "番号" in r], self.b.REPORT)


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestBuildGolden(unittest.TestCase):
    """最小の meta.yaml・body.md から build.py が組む XML を，固定した結果と比べる．

    build.py の中身を整理・分割するときに，出力が変わっていないことを確かめるためのもの．
    意図して出力を変えたときは，UPDATE_GOLDEN=1 で組み直して tests/golden/minimal.xml を更新する．
    """

    GOLD = HERE / "golden"

    def build(self, d):
        import subprocess
        work = Path(d)
        (work / "figs").mkdir()
        (work / "figs" / "fig1.png").write_bytes(b"x")
        (work / "figs" / "fa1.jpg").write_bytes(b"x")
        (work / "meta.yaml").write_bytes((self.GOLD / "minimal_meta.yaml").read_bytes())
        (work / "body.md").write_bytes((self.GOLD / "minimal_body.md").read_bytes())
        r = subprocess.run([sys.executable, str(SCRIPTS / "build.py"), str(work)],
                           capture_output=True, cwd=d)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        return work

    def test_minimal_article_matches_golden(self):
        with tempfile.TemporaryDirectory() as d:
            work = self.build(d)
            xml = (work / "out" / "99_001.xml").read_bytes().replace(b"\r\n", b"\n")
            golden = self.GOLD / "minimal.xml"
            if os.environ.get("UPDATE_GOLDEN"):
                golden.write_bytes(xml)
            # 取り出しのとき改行が CRLF に変わっていても (Windows の autocrlf) 同じと見る
            self.assertEqual(xml.decode("utf-8"),
                             golden.read_bytes().decode("utf-8").replace("\r\n", "\n"))

    def test_zip_has_xml_and_graphics(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            work = self.build(d)
            with zipfile.ZipFile(work / "99_001.zip") as z:
                names = z.namelist()
            self.assertTrue(any(n.endswith("99_001.xml") for n in names), names)
            self.assertTrue(any(n.endswith("99_001_01.png") for n in names), names)
            self.assertTrue(any(n.endswith("99_001_02.jpg") for n in names), names)

    def test_report_lists_only_the_missing_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            work = self.build(d)
            report = (work / "build_report.txt").read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(report), 1, report)
            self.assertIn("全文 PDF が無い", report[0])


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestRefGolden(unittest.TestCase):
    """引用文献 1 件の分解 (Ref.parse) の結果を固定する．整理の前後で変わらないことを見る．

    入力は tests/golden/refs_inputs.txt (1 行 1 件)，期待は refs.json．
    意図して変えたときは UPDATE_GOLDEN=1 で組み直す．
    """

    def test_references_match_golden(self):
        import json
        b = load("build")
        lines = (HERE / "golden" / "refs_inputs.txt").read_text(encoding="utf-8").splitlines()
        got = {}
        for i, line in enumerate(lines, 1):
            b.REPORT.clear()
            r = b.Ref(i, line)
            got[str(i)] = {"text": line, "kind": r.kind, "year": r.year, "names": r.names,
                           "xml": r.xml, "report": list(b.REPORT)}
        path = HERE / "golden" / "refs.json"
        if os.environ.get("UPDATE_GOLDEN"):
            path.write_text(json.dumps(got, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
        want = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(sorted(got), sorted(want))
        for k in want:
            with self.subTest(ref=want[k]["text"][:30]):
                self.assertEqual(got[k], want[k])


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestBuildInlineMarks(unittest.TestCase):
    """inline() の印 (斜体・太字・上付き・下付き・下線) と，引用のリンク．"""

    @classmethod
    def setUpClass(cls):
        cls.b = load("build")

    def inl(self, s):
        return self.b.inline(self.b.esc(s))

    def test_italic_next_to_japanese(self):
        self.assertEqual(self.inl("山麓部に*Abies*の林がある"), "山麓部に<italic>Abies</italic>の林がある")

    def test_bold_and_bold_italic(self):
        self.assertEqual(self.inl("a**太字**b"), "a<bold>太字</bold>b")
        self.assertEqual(self.inl("***強調***です"), "<bold><italic>強調</italic></bold>です")

    def test_star_in_a_word_is_not_a_mark(self):
        self.assertEqual(self.inl("N* と log*x* です"), "N* と log<italic>x</italic> です")

    def test_variable_after_a_coefficient(self):
        self.assertEqual(self.inl("0.414*x*+0.1022"), "0.414<italic>x</italic>+0.1022")

    def test_sup_sub_underline(self):
        self.assertEqual(self.inl("H~2~O と m^2^"), "H<sub>2</sub>O と m<sup>2</sup>")
        self.assertEqual(self.inl("__下線__です"), "<underline>下線</underline>です")

    def test_escaped_marks_stay_literal(self):
        self.assertEqual(self.inl("~300 m と \\~20 times"), "~300 m と ~20 times")
        self.assertEqual(self.inl("表の脚注 \\*1: 注"), "表の脚注 *1: 注")

    def test_ordinal_suffix_after_italic(self):
        self.assertEqual(self.inl("*i*th 番目"), "<italic>i</italic>th 番目")

    def test_semicolon_ends_the_url(self):
        s = self.inl("https://a.jp/x; 岐阜県")
        self.assertIn('xlink:href="https://a.jp/x"', s)
        self.assertTrue(s.endswith("; 岐阜県"))

    def test_paren_after_url_is_outside(self):
        self.assertIn('>http://a.jp/x</ext-link>)', self.inl("(http://a.jp/x)"))

    REFS = ["山田太郎・鈴木花子 2001. 植生の調査法. 植生学会誌 18: 1-10.",
            "Smith, J. & Lee, K. 1999. A study. Journal of X 5: 1-9.",
            "山田太郎 2005a. 植物. 雑誌 1: 1-2.",
            "山田太郎 2005b. 動物. 雑誌 1: 3-4."]

    def para(self, text):
        refs = [self.b.Ref(i + 1, t) for i, t in enumerate(self.REFS)]
        self.b.REPORT.clear()
        return self.b.para_xml(text, refs, {}, "body")

    def test_citation_with_authors_and_year_is_linked(self):
        self.assertEqual(self.para("山田・鈴木 (2001) は述べた．"),
                         '山田・鈴木 (<xref ref-type="bibr" rid="B1">2001</xref>) は述べた．')
        self.assertIn('rid="B2">1999</xref>', self.para("Smith & Lee (1999) は述べた．"))

    def test_year_with_a_b_suffixes(self):
        s = self.para("山田 (2005a, b) の結果．")
        self.assertIn('rid="B3">2005a</xref>', s)
        self.assertIn('rid="B4">b</xref>', s)

    def test_year_followed_by_nen_or_meter_is_not_a_citation(self):
        s = self.para("2011 年に，標高 1893 m で調べた．")
        self.assertNotIn("<xref", s)

    def test_ambiguous_author_is_not_linked(self):
        self.assertNotIn("<xref", self.para("山田 2005 は曖昧．"))


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestWebRefComparison(unittest.TestCase):
    """J-STAGE 登録ずみの引用文献 (refs_web.txt) との照合．"""

    @classmethod
    def setUpClass(cls):
        cls.b = load("build")

    def run_cmp(self, pdf_lines, web_lines):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            (work / "refs_web.txt").write_text("\n".join(web_lines) + "\n", encoding="utf-8")
            refs = [self.b.Ref(i + 1, t) for i, t in enumerate(pdf_lines)]
            self.b.REPORT.clear()
            res = self.b.compare_web_refs(work, refs)
            return res, list(self.b.REPORT)

    def test_identical_references_have_no_differences(self):
        lines = ["山田太郎 2001. 植生の調査法. 植生学会誌 18: 1-10."]
        res, report = self.run_cmp(lines, lines)
        self.assertEqual(res[2], 0)          # 中身の違い
        self.assertEqual(report, [])

    def test_a_dropped_character_is_a_content_difference(self):
        pdf = ["山田太郎 2001. 植生の調査法. 植生学会誌 18: 1-10."]
        web = ["山田太郎 2001. 植生の調査. 植生学会誌 18: 1-10."]
        res, report = self.run_cmp(pdf, web)
        self.assertEqual(res[2], 1)
        self.assertTrue([r for r in report if "違い" in r or "食い違" in r or "植生" in r], report)

    def test_issue_number_is_not_a_word(self):
        # 「no. 12」(号) は組み方で出入りするので，語に数えない
        words = self.b.ref_words("Smith 1999. Title. Journal vol. 5, no. 12, p. 1-9")
        self.assertNotIn("12", words)
        self.assertIn("1999", words)

    def test_organization_abbreviation_keeps_its_period(self):
        ref = self.b.Ref(1, "Acme Ltd. 2010. Report. Acme, London.")
        self.assertEqual(ref.names, ["Acme Ltd."])
        self.assertIn("<collab>Acme Ltd.</collab>", ref.xml)

    def test_word_overlap_helper(self):
        from collections import Counter
        a, b = Counter("abcd"), Counter("abxy")
        self.assertAlmostEqual(self.b.word_overlap(a, b), 0.5)
        self.assertEqual(self.b.word_overlap(Counter(), b), 0.0)


@unittest.skipUnless(HAVE_YAML and importlib.util.find_spec("pymupdf"), "PyYAML と PyMuPDF が要る")
class TestExtractOutputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ex = load("extract")

    def test_fresh_output_uses_figs_and_tables(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "w"
            self.ex.REPORT.clear()
            protect, img = self.ex.prepare_outputs(out, force=False)
            self.assertFalse(protect)
            self.assertEqual(img, {"figs": "figs", "tables": "tables"})
            for sub in ("pages", "figs", "tables"):
                self.assertTrue((out / sub).is_dir())

    def test_existing_body_md_is_protected(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "w"
            (out / "figs").mkdir(parents=True)
            (out / "figs" / "fig1.png").write_bytes(b"x")       # 手で切り出した図
            (out / "body.md").write_text("手で直した本文\n", encoding="utf-8")
            self.ex.REPORT.clear()
            protect, img = self.ex.prepare_outputs(out, force=False)
            self.assertTrue(protect)
            self.assertEqual(img, {"figs": "figs.new", "tables": "tables.new"})
            self.assertTrue((out / "figs" / "fig1.png").exists())    # 触らない
            self.assertTrue([r for r in self.ex.REPORT if "figs.new" in r])

    def test_force_clears_old_images(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "w"
            (out / "figs").mkdir(parents=True)
            (out / "figs" / "old.png").write_bytes(b"x")
            (out / "body.md").write_text("本文\n", encoding="utf-8")
            protect, img = self.ex.prepare_outputs(out, force=True)
            self.assertFalse(protect)
            self.assertFalse((out / "figs" / "old.png").exists())

    def test_check_era_without_meta_is_silent(self):
        with tempfile.TemporaryDirectory() as d:
            self.ex.REPORT.clear()
            self.ex.check_era({}, "x.pdf", d)
            self.assertEqual(self.ex.REPORT, [])


@unittest.skipUnless(HAVE_YAML and importlib.util.find_spec("pymupdf"), "PyYAML と PyMuPDF が要る")
class TestFillMeta(unittest.TestCase):
    META = ("# 書誌 (fetch_jstage.py が J-STAGE の記事ページから取ったもの)．\n"
            "# 原稿種別は PDF の1ページ目で埋める．\n"
            "article_type: 要確認 (PDF から)\n"
            "category: {ja: 要確認, en: 要確認}\n"
            "volume: '1'\nissue: '2'\nfpage: '3'\nlpage: '9'\n"
            "authors:\n- name: {ja: [山田, 太郎], en: [Yamada, Taro]}\n  corresp: false\n  email: null\n"
            "history: {received: '2026-01-10', accepted: '2026-05-20'}\n"
            "\n# J-STAGE の登録ずみの書誌 (merge_backup.py が控え x.zip から書いた．build.py が XML に出す)\n"
            "registered:\n  license: CC-BY\n  manuscript: M-1\n")

    def test_registered_block_and_comments_survive(self):
        ex = load("extract")
        pm = {"article_type": "original-article", "category": {"ja": "原著", "en": "Original"},
              "corresp_index": [0], "email": "a@example.org", "volume": "1", "issue": "2",
              "fpage": "3", "lpage": "9", "history": {"received": "2026-01-10", "accepted": "2026-05-20"}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "meta.yaml"
            path.write_text(self.META, encoding="utf-8")
            ex.REPORT.clear()
            ex.fill_meta(path, pm)
            out = path.read_text(encoding="utf-8")
            m = yaml.safe_load(out)
            self.assertEqual(m["article_type"], "original-article")
            self.assertTrue(m["authors"][0]["corresp"])
            self.assertEqual(m["registered"], {"license": "CC-BY", "manuscript": "M-1"})
            # 登録ずみの節のコメントが先頭に集まらず，節の直前に残る
            lines = out.splitlines()
            i = lines.index("registered:")
            self.assertTrue(lines[i - 1].startswith("# J-STAGE の登録ずみの書誌 (merge_backup.py"), lines[i - 3:i])
            self.assertFalse(any(l.startswith("# J-STAGE の登録ずみの書誌") for l in lines[:3]))

    def test_missing_history_does_not_crash(self):
        ex = load("extract")
        pm = {"article_type": "", "category": {}, "corresp_index": [], "email": None, "volume": "",
              "issue": "", "fpage": "", "lpage": "",
              "history": {"received": "2026-01-10", "accepted": None}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "meta.yaml"
            path.write_text("article_type: x\nauthors: []\n", encoding="utf-8")
            ex.REPORT.clear()
            ex.fill_meta(path, pm)
            self.assertTrue([r for r in ex.REPORT if "received" in r])


@unittest.skipUnless(HAVE_YAML and importlib.util.find_spec("pymupdf"), "PyYAML と PyMuPDF が要る")
class TestApplyBackup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ab = load("apply_backup")

    MD = "# ABSTRACT\nEnglish abstract.\n\n# INTRODUCTION\nBody text.\n\n# 謝辞\nthanks\n"

    def test_abstract_removal_stops_at_the_next_heading(self):
        # 英文要旨の節の終わりは次の見出し．次の本物の節 (INTRODUCTION) まで消してはいけない
        lines = self.MD.split("\n")
        start, end = self.ab.section_span(self.MD, ["ABSTRACT"], {"謝辞"}, strict_next=True)
        self.assertEqual(lines[start], "# ABSTRACT")
        self.assertEqual(lines[end], "# INTRODUCTION")

    def test_ja_punct_converts_japanese_context_only(self):
        self.assertEqual(self.ab.ja_punct("植生を調べ,結果を述べる."), "植生を調べ，結果を述べる．")
        self.assertEqual(self.ab.ja_punct("結果は(見よ)．"), "結果は（見よ）．")
        self.assertEqual(self.ab.ja_punct("(1) の結果，2.3 倍．"), "(1) の結果，2.3 倍．")   # 欧文・数は変えない

    def test_ja_punct_list_number_at_line_start(self):
        self.assertEqual(self.ab.ja_punct("1. はじめに\n2. 方法"), "1．はじめに\n2．方法")

    def test_ja_punct_keeps_a_decimal_at_line_start(self):
        # 行頭の小数 (3.5 倍) を箇条の番号と取り違えて「3．5」にしてはいけない
        self.assertEqual(self.ab.ja_punct("3.5 倍に増えた．"), "3.5 倍に増えた．")

    def test_fix_numbers_corrects_ocr_digits(self):
        log = []
        self.assertEqual(self.ab.fix_numbers("植生学会誌 18: 2DOO 年", "植生学会誌 18: 2000 年", log),
                         "植生学会誌 18: 2000 年")
        self.assertEqual(log, ["2DOO → 2000"])

    def test_fix_numbers_leaves_unmatched_alone(self):
        log = []
        self.assertEqual(self.ab.fix_numbers("2DOO", "1999", log), "2DOO")
        self.assertEqual(log, [])

    def test_default_span_still_skips_fake_headings(self):
        # 引用文献などでは，偽の見出し (「# 53.78」) を読み飛ばして次の本物の節まで
        md = "# 引用文献\nA 1999.\n# 53.78\nB 2000.\n\n# 謝辞\nthanks\n"
        lines = md.split("\n")
        start, end = self.ab.section_span(md, ["引用文献"], {"謝辞"})
        self.assertEqual(lines[end], "# 謝辞")


class TestManifest(unittest.TestCase):
    def test_round_trip_and_zip_members(self):
        import zipfile
        manifest = load("manifest")
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "work"
            (work / "out").mkdir(parents=True)
            (work / "figs").mkdir()
            (work / "figs" / "fig1.png").write_bytes(b"png")
            (work / "out" / "9_1.xml").write_text("<article/>", encoding="utf-8")
            (work / "9_1.pdf").write_bytes(b"%PDF")
            outside = Path(d) / "outside.png"           # 作業ディレクトリの外のファイル
            outside.write_bytes(b"png2")
            m = manifest.write(work, "vegsci", 9, 1, "9_1", work / "9_1.pdf",
                               [("9_1_01.png", work / "figs" / "fig1.png"), ("9_1_02.png", outside)])
            self.assertEqual(manifest.read(work), m)
            self.assertEqual(m["pdf"], "9_1.pdf")
            self.assertEqual(m["graphics"][0], ["9_1_01.png", "figs/fig1.png"])        # 中なら相対
            self.assertEqual(Path(m["graphics"][1][1]), outside.resolve())             # 外なら絶対
            names = sorted(n for _src, n in manifest.members(work, m))
            self.assertEqual(names, ["9_1.pdf", "9_1.xml", "Graphics/9_1_01.png", "Graphics/9_1_02.png"])
            zpath = work / "9_1.zip"
            with zipfile.ZipFile(zpath, "w") as z:
                self.assertEqual(manifest.add_to_zip(z, work, m), 4)
            self.assertEqual(manifest.zip_names(work, m),
                             {"9_1.xml", "9_1.pdf", "Graphics/9_1_01.png", "Graphics/9_1_02.png"})
            with zipfile.ZipFile(zpath) as z:
                self.assertTrue(all(n.startswith("vegsci/9/1/9_1/") for n in z.namelist()))

    def test_find_work_from_xml_path(self):
        manifest = load("manifest")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "out").mkdir()
            xml = Path(d) / "out" / "a.xml"
            xml.write_text("<a/>", encoding="utf-8")
            self.assertEqual(manifest.find_work(xml), Path(d).resolve())
            self.assertIsNone(manifest.find_work(Path(d) / "a.xml"))


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestArticleIds(unittest.TestCase):
    def test_non_numeric_start_page_does_not_crash_the_sort(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["JSTAGE_ROOT"] = d
            try:
                mod = load("article_ids")
            finally:
                del os.environ["JSTAGE_ROOT"]
            rows = {
                "13_e1": {"short": "13_e1", "article_id": "13_e1", "volume": "13", "issue": "1",
                          "fpage": "e1", "lpage": "e3", "url": "", "title": "電子論文"},
                "13_5": {"short": "13_5", "article_id": "13_5", "volume": "13", "issue": "1",
                         "fpage": "5", "lpage": "9", "url": "", "title": "通常"},
            }
            mod.save(rows)          # 開始ページが数でなくても落ちない
            self.assertEqual(sorted(mod.load()), ["13_5", "13_e1"])


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestJournalProfile(unittest.TestCase):
    def test_load_profile_and_as_list(self):
        jp = load("journal_profile")
        prof = jp.load_profile("vegsci")
        self.assertEqual(prof["journal_id"], "vegsci")
        self.assertEqual(jp.as_list("引用文献"), ["引用文献"])
        self.assertEqual(jp.as_list(("a", "b")), ["a", "b"])

    def test_every_script_uses_the_shared_loader(self):
        # 設定を読む場所を 1 つにしておく (journals/ を直接読む書き方を増やさない)
        for name in ("build", "extract", "extract_scan", "fetch_jstage", "from_backup"):
            text = (SCRIPTS / f"{name}.py").read_text(encoding="utf-8")
            self.assertIn("journal_profile", text, name)
            self.assertNotIn('/ "journals" /', text, name)


@unittest.skipUnless(HAVE_YAML, "PyYAML が要る")
class TestNoJournalDefault(unittest.TestCase):
    """既定の雑誌・ISSN (植生学会誌) を持たない．渡し忘れたら黙って植生学会誌を引かずに止まる．"""

    def run_script(self, name, *args):
        import subprocess
        r = subprocess.run([sys.executable, str(SCRIPTS / name)] + list(args), capture_output=True)
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")

    def test_epub_issn_helper(self):
        jp = load("journal_profile")
        self.assertEqual(jp.epub_issn(issn="1234-5678"), "1234-5678")
        self.assertEqual(jp.epub_issn(journal="vegsci"), jp.load_profile("vegsci")["issn"]["epub"])
        with self.assertRaises(SystemExit):
            jp.epub_issn()

    def test_article_ids_needs_issn_or_journal(self):
        code, out = self.run_script("article_ids.py", "update")
        self.assertNotEqual(code, 0)
        self.assertIn("--issn", out)

    def test_list_articles_html_needs_issn_or_journal(self):
        code, out = self.run_script("list_articles.py", "html")
        self.assertNotEqual(code, 0)
        self.assertIn("--issn", out)

    def test_fetch_jstage_needs_journal(self):
        code, out = self.run_script("fetch_jstage.py", "--out", "x")
        self.assertNotEqual(code, 0)
        self.assertIn("--journal", out)

    def test_no_script_hard_codes_the_default(self):
        for p in sorted(SCRIPTS.glob("*.py")):
            text = p.read_text(encoding="utf-8")
            self.assertNotIn('default="vegsci"', text, p.name)
            self.assertNotIn('default="2189-4809"', text, p.name)
            self.assertNotIn('or "vegsci"', text, p.name)


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
