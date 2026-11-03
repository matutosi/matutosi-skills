#!/usr/bin/env python3
"""apply_docx.py の自己テスト (外部ライブラリ不要)。

    python tests/test_apply_docx.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import apply_docx as A  # noqa: E402

for _stream in (sys.stdout, sys.stderr):    # run() が日本語を出すので，Windows の cp932 で落ちないようにする
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

W = A.W
ROOT = ('<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:w="%s" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'mc:Ignorable="w14">' % W)
BODY = (
    '<w:body>'
    # 段落 1: 「庭の」(太字) +「木に小さな鳥が」+「とまった．」と run が割れている
    '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>庭の</w:t></w:r><w:r><w:t>木に小さな鳥が</w:t></w:r>'
    '<w:r><w:t>とまった．</w:t></w:r></w:p>'
    # 段落 2: 図の参照のフィールド (fldChar) を含む
    '<w:p><w:r><w:t xml:space="preserve">朝の市場で </w:t></w:r><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText> REF fig1 </w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>'
    '<w:r><w:t>野菜を買い出します．</w:t></w:r></w:p>'
    # 段落 3: 表の中
    '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表の中の語</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    '<w:sectPr/></w:body></w:document>')
CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
      '</Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
DOCRELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>')


def make_docx(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + ROOT + BODY)
        z.writestr("word/_rels/document.xml.rels", DOCRELS)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.doc = os.path.join(self.dir, "ms.docx")
        make_docx(self.doc)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def run_fix(self, rows, mode="track", apply=True):
        fixes = [dict(n=i + 1, file="ms.docx", count=1, **r) for i, r in enumerate(rows)]
        return A.run(fixes, self.dir, apply, mode, "校正者", "2026-11-03T00:00:00Z")

    def raw(self):
        with open(self.doc, "rb") as fh:
            return fh.read()

    def xml(self, part="word/document.xml"):
        with zipfile.ZipFile(self.doc) as z:
            return z.read(part).decode("utf-8")


class TestText(Base):
    def test_text(self):
        self.assertEqual(A.docx_text(self.doc), "庭の木に小さな鳥がとまった．\n朝の市場で 野菜を買い出します．\n表の中の語")


class TestApply(Base):
    def test_track_across_runs(self):
        ok, bad = self.run_fix([{"old": "庭の木に", "new": "庭の松に"}])
        self.assertEqual((ok, bad), (1, []))
        x = self.xml()
        self.assertIn("<w:delText", x)
        self.assertRegex(x, r'<w:del [^>]*w:author="校正者"')
        self.assertIn(">木</w:delText>", x)         # 違う部分だけを消す
        self.assertIn(">松</w:t>", x)
        self.assertEqual(A.docx_text(self.doc).split("\n")[0], "庭の松に小さな鳥がとまった．")
        self.assertTrue(x.split("?>", 1)[1].lstrip().startswith(ROOT))   # 名前空間の宣言が元のまま
        self.assertTrue(os.path.exists(self.doc + ".bak"))

    def test_track_keeps_bold_of_first_run(self):
        self.run_fix([{"old": "庭の木", "new": "裏庭の木"}])
        x = self.xml()
        self.assertRegex(x, r"<w:ins [^>]*><w:r><w:rPr><w:b ?/></w:rPr><w:t[^>]*>裏</w:t>")
        self.assertEqual(A.docx_text(self.doc).split("\n")[0], "裏庭の木に小さな鳥がとまった．")

    def test_insert_only(self):
        self.run_fix([{"old": "小さな鳥", "new": "小さな青い鳥"}])
        x = self.xml()
        self.assertNotIn("<w:del ", x)
        self.assertIn(">青い</w:t>", x)
        self.assertEqual(A.docx_text(self.doc).split("\n")[0], "庭の木に小さな青い鳥がとまった．")

    def test_direct(self):
        self.run_fix([{"old": "の木に小さな", "new": "の大きな"}, {"old": "表の中の語", "new": "表の語"}], mode="direct")
        x = self.xml()
        self.assertNotIn("<w:del ", x)
        self.assertNotIn("<w:ins ", x)
        self.assertEqual(A.docx_text(self.doc), "庭の大きな鳥がとまった．\n朝の市場で 野菜を買い出します．\n表の語")

    def test_comment(self):
        self.run_fix([{"old": "小さな鳥", "new": "小鳥"}], mode="comment")
        self.assertEqual(A.docx_text(self.doc).split("\n")[0], "庭の木に小さな鳥がとまった．")   # 本文は変えない
        x = self.xml()
        self.assertIn("commentRangeStart", x)
        self.assertIn("commentReference", x)
        self.assertIn("朱書き: 「小さな鳥」→「小鳥」", self.xml("word/comments.xml"))
        self.assertIn("comments.xml", self.xml("word/_rels/document.xml.rels"))
        self.assertIn("/word/comments.xml", self.xml("[Content_Types].xml"))

    def test_two_fixes_in_one_paragraph(self):
        ok, bad = self.run_fix([{"old": "庭の木", "new": "庭の松"}, {"old": "とまった", "new": "止まった"}])
        self.assertEqual((ok, bad), (2, []))
        self.assertEqual(A.docx_text(self.doc).split("\n")[0], "庭の松に小さな鳥が止まった．")

    def test_failures_write_nothing(self):
        before = self.raw()
        ok, bad = self.run_fix([{"old": "庭の木", "new": "庭の松"},          # 当たる
                                {"old": "無い文字列", "new": "x"},           # 0 件
                                {"old": "で 野菜", "new": "で，果物"},        # 違う部分がフィールドをまたぐ
                                {"old": "た．\n朝", "new": "た．朝"}])        # 段落をまたぐ
        self.assertEqual(ok, 1)
        self.assertEqual([n for n, _ in bad], [2, 3, 4])
        self.assertIn("0 件ヒット", bad[0][1])
        self.assertIn("改行", bad[2][1])
        self.assertEqual(self.raw(), before)
        self.assertFalse(os.path.exists(self.doc + ".bak"))

    def test_space_before_field_is_plain(self):
        # 違う部分 (空白) がフィールドの手前の平らな run だけにあれば当てられる
        ok, bad = self.run_fix([{"old": "で 野菜", "new": "で野菜"}])
        self.assertEqual((ok, bad), (1, []))
        self.assertIn("REF fig1", self.xml())
        self.assertEqual(A.docx_text(self.doc).splitlines()[1], "朝の市場で野菜を買い出します．")

    def test_field_run_untouched_when_outside(self):
        ok, bad = self.run_fix([{"old": "野菜を", "new": "果物を"}])
        self.assertEqual((ok, bad), (1, []))
        x = self.xml()
        self.assertIn("REF fig1", x)
        self.assertEqual(A.docx_text(self.doc).split("\n")[1], "朝の市場で 果物を買い出します．")

    def test_cli_dry_run(self):
        fx = os.path.join(self.dir, "fixes.json")
        with open(fx, "w", encoding="utf-8") as fh:
            json.dump([{"file": "ms.docx", "old": "庭の木", "new": "庭の松"}], fh, ensure_ascii=False)
        before = self.raw()
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "apply_docx.py"), fx, "--base", self.dir],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        out = r.stdout.decode("utf-8")
        self.assertEqual(r.returncode, 0, out + r.stderr.decode("utf-8"))
        self.assertIn("当てられる 1 件", out)
        self.assertEqual(self.raw(), before)        # 確かめだけ


if __name__ == "__main__":
    unittest.main()
