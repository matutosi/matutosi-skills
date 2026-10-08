#!/usr/bin/env python3
"""jpg_comment.py の自己テスト (外部ライブラリ不要).

    python3 tests/test_jpg_comment.py
"""

import base64
import os
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import jpg_comment as jc  # noqa: E402

# Exif を持たない 1x1 の JPEG
PLAIN_JPEG = base64.b64decode("""
/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcp
LDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy
MjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAA
AgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6
Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXG
x8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREA
AgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5
OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPE
xcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q==
""".replace("\n", ""))

# 既存 Exif (Make/Model/GPS/Interop/DateTimeOriginal/サムネイル, ビッグエンディアン MM) 付きの JPEG
EXIF_JPEG = base64.b64decode("""
/9j/4AAQSkZJRgABAQAAAQABAAD/4QOgRXhpZgAATU0AKgAAAAgABgEPAAIAAAAJAAAAVgEQAAIAAAAKAAAAYAEaAAUAAAAB
AAAAagEbAAUAAAABAAAAcodpAAQAAAABAAAAeoglAAQAAAABAAAAygAAAQBUZXN0TWFrZQAAVGVzdE1vZGVsAAAAAEgAAAAB
AAAASAAAAAEAA5AAAAcAAAAEMDIzMJADAAIAAAAUAAAApKAFAAQAAAABAAAAuAAAAAAyMDI2OjA5OjA3IDEwOjAwOjAwAAAB
AAEAAgAAAARSOTgAAAAAAAACAAEAAgAAAAJOAAAAAAIABQAAAAMAAADoAAAAAAAAACMAAAABAAAAAAAAAAEAAAAAAAAAAQAD
ARoABQAAAAEAAAEqAgEABAAAAAEAAAEyAgIABAAAAAEAAAJmAAAAAAAAAEgAAAAB/9j/2wBDAAgGBgcGBQgHBwcJCQgKDBQN
DAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy
MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAKABADASIAAhEBAxEB/8QAHwAAAQUB
AQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0Kx
wRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKT
lJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEB
AQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHB
CSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImK
kpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIR
AxEAPwDxGiiitjI//9n/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0
Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy
MjIyMjIyMjL/wAARCABQAHgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIE
AwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdI
SUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT
1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQD
BAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZH
SElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK
0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwCzRRRXzJ9QFFFFABRRRQAUUUUAFFFFABRRRQAUUUUA
FFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUA
FFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAf//Z
""".replace("\n", ""))


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir)

    def path(self, name, data=PLAIN_JPEG):
        target = os.path.join(self.dir, name)
        with open(target, "wb") as handle:
            handle.write(data)
        return target


class TestCodec(Base):
    def test_ascii_and_unicode_prefix(self):
        self.assertEqual(jc.encode_user_comment("abc", "<")[:8], b"ASCII\x00\x00\x00")
        self.assertEqual(jc.encode_user_comment("桜", "<")[:8], b"UNICODE\x00")

    def test_decode_round_trip(self):
        for text in ("hello", "桜の花", "改行\nあり", "emoji ✓"):
            for order in ("<", ">"):
                raw = jc.encode_user_comment(text, order)
                self.assertEqual(jc.decode_user_comment(raw, order), text)

    def test_new_file_comment_is_utf16_be(self):
        # UNICODE を常に UTF-16-BE として読む実装とも一致すること
        path = self.path("n.jpg")
        jc.write_comment(path, "日本語")
        with open(path, "rb") as handle:
            segments, _tail = jc.split_segments(handle.read())
        _index, tiff = jc.find_exif(segments)
        raw = jc.Exif.parse(tiff).exif[jc.TAG_USER_COMMENT][2]
        self.assertEqual(raw[8:].decode("utf-16-be"), "日本語")

    def test_decode_tolerates_missing_prefix(self):
        self.assertEqual(jc.decode_user_comment(b"\x00" * 8 + "桜".encode(), "<"), "桜")
        self.assertEqual(jc.decode_user_comment(b"", "<"), "")


class TestReadWrite(Base):
    def test_no_exif_reads_empty(self):
        self.assertEqual(jc.read_comment(self.path("p.jpg")), "")

    def test_write_then_read(self):
        path = self.path("p.jpg")
        jc.write_comment(path, "桜の花, 京都")
        self.assertEqual(jc.read_comment(path), "桜の花, 京都")

    def test_ascii_write(self):
        path = self.path("p.jpg")
        jc.write_comment(path, "plain ascii")
        self.assertEqual(jc.read_comment(path), "plain ascii")

    def test_repeated_write_is_stable(self):
        path = self.path("p.jpg")
        jc.write_comment(path, "コメント")
        size = os.path.getsize(path)
        for _ in range(3):
            jc.write_comment(path, "コメント")
        self.assertEqual(os.path.getsize(path), size)
        self.assertEqual(jc.read_comment(path), "コメント")

    def test_empty_comment_removes_tag(self):
        path = self.path("e.jpg", EXIF_JPEG)
        jc.write_comment(path, "あとで消す")
        jc.write_comment(path, "")
        self.assertEqual(jc.read_comment(path), "")

    def test_no_exif_and_empty_comment_leaves_file_untouched(self):
        path = self.path("p.jpg")
        jc.write_comment(path, "")
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), PLAIN_JPEG)

    def test_outdir_keeps_original(self):
        path = self.path("p.jpg")
        target = os.path.join(self.dir, "out.jpg")
        jc.write_comment(path, "copy", out_path=target)
        self.assertEqual(jc.read_comment(target), "copy")
        self.assertEqual(jc.read_comment(path), "")

    def test_not_a_jpeg(self):
        path = os.path.join(self.dir, "x.jpg")
        with open(path, "wb") as handle:
            handle.write(b"not a jpeg")
        self.assertRaises(jc.JpegError, jc.read_comment, path)


class TestExifPreservation(Base):
    def tags(self, path):
        with open(path, "rb") as handle:
            segments, _tail = jc.split_segments(handle.read())
        _index, tiff = jc.find_exif(segments)
        return jc.Exif.parse(tiff)

    def test_existing_tags_survive(self):
        path = self.path("e.jpg", EXIF_JPEG)
        before = self.tags(path)
        self.assertEqual(before.byte_order, ">")
        jc.write_comment(path, "日本語コメント")
        after = self.tags(path)

        self.assertEqual(after.byte_order, ">")
        self.assertEqual(after.get_comment(), "日本語コメント")
        for tag in (0x010F, 0x0110):  # Make, Model
            self.assertEqual(after.ifd0[tag], before.ifd0[tag])
        self.assertEqual(after.exif[0x9003], before.exif[0x9003])  # DateTimeOriginal
        self.assertEqual(after.gps, before.gps)
        self.assertEqual(after.interop, before.interop)
        self.assertEqual(after.thumbnail, before.thumbnail)
        self.assertTrue(before.thumbnail.startswith(b"\xff\xd8"))

    def test_image_data_unchanged(self):
        path = self.path("e.jpg", EXIF_JPEG)

        def scan(data):
            segments, tail = jc.split_segments(data)
            return [(m, p) for m, p in segments if m != 0xE1], tail

        before = scan(EXIF_JPEG)
        jc.write_comment(path, "コメント")
        with open(path, "rb") as handle:
            self.assertEqual(scan(handle.read()), before)

    def test_new_exif_is_big_endian_and_valid(self):
        path = self.path("p.jpg")
        jc.write_comment(path, "new")
        exif = self.tags(path)
        self.assertEqual(exif.byte_order, ">")  # UTF-16-BE 前提の実装との互換性
        self.assertIn(jc.TAG_EXIF_IFD, exif.ifd0)
        self.assertEqual(exif.exif[jc.TAG_EXIF_VERSION][2], b"0230")

    def test_app1_inserted_after_jfif(self):
        path = self.path("p.jpg")
        jc.write_comment(path, "x")
        with open(path, "rb") as handle:
            segments, _tail = jc.split_segments(handle.read())
        self.assertEqual([m for m, _p in segments[:2]], [0xE0, 0xE1])


class TestCsv(Base):
    def run_cli(self, argv):
        jc.main(argv)

    def test_export_import_round_trip(self):
        names = ["a.jpg", "b.jpg", "c.jpg"]
        for name in names:
            self.path(name)
        csv_path = os.path.join(self.dir, "c.csv")
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write('filename,comment\na.jpg,"桜, 京都"\nb.jpg,ascii\nc.jpg,\n')
        self.run_cli(["import", csv_path])
        self.assertEqual(jc.read_comment(os.path.join(self.dir, "a.jpg")), "桜, 京都")
        self.assertEqual(jc.read_comment(os.path.join(self.dir, "b.jpg")), "ascii")
        self.assertEqual(jc.read_comment(os.path.join(self.dir, "c.jpg")), "")

        out = os.path.join(self.dir, "out.csv")
        self.run_cli(["export", self.dir, "-o", out])
        with open(out, encoding="utf-8-sig") as handle:
            text = handle.read()
        self.assertIn('a.jpg,"桜, 京都"', text)
        self.assertIn("b.jpg,ascii", text)
        self.assertTrue(text.startswith("filename,comment"))

    def test_export_is_utf8_with_bom(self):
        self.path("a.jpg")
        out = os.path.join(self.dir, "out.csv")
        self.run_cli(["export", self.dir, "-o", out])
        with open(out, "rb") as handle:
            self.assertTrue(handle.read(3) == b"\xef\xbb\xbf")

    def test_export_to_stdout_is_utf8(self):
        # -o を省くと標準出力へ．パイプで受けても (Windows でも) UTF-8 になる
        import subprocess
        path = self.path("a.jpg")
        jc.write_comment(path, "桜")
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "jpg_comment.py")
        r = subprocess.run([sys.executable, script, "export", self.dir, "--basename"],
                           capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("a.jpg,桜", r.stdout.decode("utf-8"))

    def test_dry_run_does_not_write(self):
        path = self.path("a.jpg")
        csv_path = os.path.join(self.dir, "c.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("filename,comment\na.jpg,書かない\n")
        self.run_cli(["import", csv_path, "-n"])
        self.assertEqual(jc.read_comment(path), "")

    def test_header_is_optional(self):
        path = self.path("a.jpg")
        csv_path = os.path.join(self.dir, "c.csv")
        with open(csv_path, "w", encoding="utf-8", newline="") as handle:
            handle.write("a.jpg,見出しなし\n")
        self.run_cli(["import", csv_path])
        self.assertEqual(jc.read_comment(path), "見出しなし")

    def test_recursive_and_relative(self):
        os.makedirs(os.path.join(self.dir, "sub"))
        self.path(os.path.join("sub", "d.jpg"))
        out = os.path.join(self.dir, "out.csv")
        self.run_cli(["export", self.dir, "-r", "--relative", "-o", out])
        with open(out, encoding="utf-8-sig") as handle:
            self.assertIn("sub/d.jpg", handle.read().replace("\\", "/"))


    def test_export_uses_absolute_path_by_default(self):
        path = self.path("a.jpg")
        out = os.path.join(self.dir, "out.csv")
        self.run_cli(["export", self.dir, "-o", out])
        with open(out, encoding="utf-8-sig") as handle:
            text = handle.read()
        self.assertIn(os.path.abspath(path), text)

    def test_export_basename_option(self):
        path = self.path("a.jpg")
        out = os.path.join(self.dir, "out.csv")
        self.run_cli(["export", self.dir, "--basename", "-o", out])
        with open(out, encoding="utf-8-sig") as handle:
            text = handle.read()
        self.assertNotIn(os.path.abspath(path), text)
        self.assertIn("a.jpg", text)


class TestHeaderScan(Base):
    """先頭だけ読む速い経路と, 全体を読む経路が同じ結果になること."""

    def test_fast_and_slow_paths_agree(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "先頭だけ読む")
        fast = jc.read_comment(path)
        saved = jc.HEADER_SCAN
        try:
            jc.HEADER_SCAN = 4  # 速い経路を必ず諦めさせる
            slow = jc.read_comment(path)
        finally:
            jc.HEADER_SCAN = saved
        self.assertEqual(fast, "先頭だけ読む")
        self.assertEqual(slow, fast)

    def test_fallback_still_reports_broken_file(self):
        path = os.path.join(self.dir, "broken.jpg")
        with open(path, "wb") as handle:
            handle.write(b"not a jpeg at all")
        with self.assertRaises(jc.JpegError):
            jc.read_comment(path)


class TestDecodeFallback(Base):
    """識別子が当てにならない UserComment の復号."""

    def test_zero_prefix_cp932(self):
        raw = b"\x00" * 8 + "シカやイノシシの足跡".encode("cp932")
        self.assertEqual(jc.decode_user_comment(raw, "<"), "シカやイノシシの足跡")

    def test_ascii_prefix_cp932(self):
        raw = b"ASCII\x00\x00\x00" + "京都の桜".encode("cp932")
        self.assertEqual(jc.decode_user_comment(raw, "<"), "京都の桜")

    def test_utf8_wins_over_cp932(self):
        raw = b"ASCII\x00\x00\x00" + "京都の桜".encode("utf-8")
        self.assertEqual(jc.decode_user_comment(raw, "<"), "京都の桜")

    def test_plain_ascii_unchanged(self):
        raw = b"ASCII\x00\x00\x00" + b"hello world"
        self.assertEqual(jc.decode_user_comment(raw, "<"), "hello world")


class TestImportModes(Base):
    """import の 3 つの書き込みモード."""

    def csv(self, text):
        path = os.path.join(self.dir, "c.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        return path

    def run_cli(self, argv):
        jc.main(argv)

    # ---- append (既定)

    def test_append_is_the_default(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "もとの")
        self.run_cli(["import", self.csv("filename,comment\na.jpg,あとの\n")])
        self.assertEqual(jc.read_comment(path), "もとの\nあとの")

    def test_append_skips_when_same(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "同じ")
        self.run_cli(["import", self.csv("filename,comment\na.jpg,同じ\n")])
        self.assertEqual(jc.read_comment(path), "同じ")

    def test_append_is_idempotent(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "もとの")
        for _ in range(3):
            self.run_cli(["import", self.csv("filename,comment\na.jpg,あとの\n")])
        self.assertEqual(jc.read_comment(path), "もとの\nあとの")

    def test_append_on_empty_writes_plain(self):
        path = self.path("a.jpg")
        self.run_cli(["import", self.csv("filename,comment\na.jpg,はじめて\n")])
        self.assertEqual(jc.read_comment(path), "はじめて")

    def test_append_ignores_empty_comment(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "残る")
        self.run_cli(["import", self.csv("filename,comment\na.jpg,\n")])
        self.assertEqual(jc.read_comment(path), "残る")

    def test_append_separator_option(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "もとの")
        self.run_cli(["import", self.csv("filename,comment\na.jpg,あとの\n"),
                      "--separator", " / "])
        self.assertEqual(jc.read_comment(path), "もとの / あとの")

    # ---- overwrite

    def test_overwrite_replaces(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "もとの")
        self.run_cli(["import", self.csv("filename,comment\na.jpg,あとの\n"), "--overwrite"])
        self.assertEqual(jc.read_comment(path), "あとの")

    def test_overwrite_keeps_when_comment_is_empty(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "残る")
        self.run_cli(["import", self.csv("filename,comment\na.jpg,\n"), "--overwrite"])
        self.assertEqual(jc.read_comment(path), "残る")

    # ---- overwrite-all

    def test_overwrite_all_replaces(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "もとの")
        self.run_cli(["import", self.csv("filename,comment\na.jpg,あとの\n"), "--overwrite-all"])
        self.assertEqual(jc.read_comment(path), "あとの")

    def test_overwrite_all_deletes_when_comment_is_empty(self):
        path = self.path("a.jpg")
        jc.write_comment(path, "消える")
        self.run_cli(["import", self.csv("filename,comment\na.jpg,\n"), "--overwrite-all"])
        self.assertEqual(jc.read_comment(path), "")

    # ---- 排他

    def test_modes_are_mutually_exclusive(self):
        self.path("a.jpg")
        with self.assertRaises(SystemExit):
            self.run_cli(["import", self.csv("filename,comment\na.jpg,x\n"),
                          "--overwrite", "--append"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
