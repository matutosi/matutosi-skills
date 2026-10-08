#!/usr/bin/env python3
"""JPEG の Exif UserComment (tag 0x9286) と CSV の相互変換.

標準ライブラリのみで動作する (Pillow / piexif 不要).

  export : JPEG -> CSV (filename, comment)
  import : CSV -> JPEG (UserComment を書き込み)

CSV は 1 行目が見出し `filename,comment` の UTF-8 (BOM 付き, Excel 互換).
"""

import argparse
import csv
import os
import struct
import sys

# ---------------------------------------------------------------- 定数

EXIF_HEADER = b"Exif\x00\x00"

TAG_EXIF_IFD = 0x8769
TAG_GPS_IFD = 0x8825
TAG_INTEROP_IFD = 0xA005
TAG_USER_COMMENT = 0x9286
TAG_EXIF_VERSION = 0x9000
TAG_THUMB_OFFSET = 0x0201
TAG_THUMB_LENGTH = 0x0202

TYPE_LONG = 4
TYPE_UNDEFINED = 7

# Exif の型番号 -> 1 要素あたりのバイト数
TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1,
             8: 2, 9: 4, 10: 8, 11: 4, 12: 8}

CSV_HEADER = ["filename", "comment"]
# 読み出しは先頭だけ見れば足りる (Exif APP1 は SOI の直後にある).
# 全体を読むと写真 1 枚あたり数 MB の無駄な I/O になるため.
HEADER_SCAN = 131072

# --append で継ぎ足すときの区切り (--separator で変えられる)
DEFAULT_SEPARATOR = "\n"
JPEG_EXTS = (".jpg", ".jpeg", ".jpe", ".jfif")


class JpegError(Exception):
    """JPEG の解析・生成に失敗した."""


# ---------------------------------------------------------------- JPEG セグメント

def split_segments(data):
    """JPEG を [(marker, payload), ...] と SOS 以降の残りデータに分解する."""
    if data[:2] != b"\xff\xd8":
        raise JpegError("JPEG (SOI) ではありません")
    segments = []
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise JpegError("マーカーが見つかりません (壊れたファイル?)")
        while i < len(data) and data[i] == 0xFF:  # 埋め草の 0xFF を読み飛ばす
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        if marker == 0xD9 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            segments.append((marker, b""))
            continue
        if i + 2 > len(data):
            raise JpegError("セグメント長が読めません")
        length = struct.unpack(">H", data[i:i + 2])[0]
        if length < 2:
            raise JpegError("セグメント長が不正です")
        payload = data[i + 2:i + length]
        segments.append((marker, payload))
        i += length
        if marker == 0xDA:  # SOS 以降は圧縮データ
            return segments, data[i:]
    return segments, b""


def join_segments(segments, tail):
    out = [b"\xff\xd8"]
    for marker, payload in segments:
        out.append(bytes([0xFF, marker]))
        if marker == 0xD9 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if len(payload) + 2 > 0xFFFF:
            raise JpegError("セグメントが 64KB を超えました")
        out.append(struct.pack(">H", len(payload) + 2))
        out.append(payload)
    out.append(tail)
    return b"".join(out)


def find_exif(segments):
    """Exif APP1 セグメントの (index, tiff_bytes) を返す. 無ければ (None, None)."""
    for index, (marker, payload) in enumerate(segments):
        if marker == 0xE1 and payload[:6] == EXIF_HEADER:
            return index, payload[6:]
    return None, None


# ---------------------------------------------------------------- TIFF/Exif 解析

def _unpack(byte_order, fmt, buf, offset):
    size = struct.calcsize(byte_order + fmt)
    if offset + size > len(buf):
        raise JpegError("Exif データが途中で切れています")
    return struct.unpack_from(byte_order + fmt, buf, offset)


def parse_ifd(tiff, offset, byte_order):
    """IFD を {tag: (type, count, raw_value_bytes)} と次 IFD の offset に分解する."""
    (count,) = _unpack(byte_order, "H", tiff, offset)
    entries = {}
    pos = offset + 2
    for _ in range(count):
        tag, typ, num = _unpack(byte_order, "HHI", tiff, pos)
        field = tiff[pos + 8:pos + 12]
        pos += 12
        if typ not in TYPE_SIZE:
            continue  # 未知の型は捨てる
        size = TYPE_SIZE[typ] * num
        if size <= 4:
            value = field[:size]
        else:
            (value_offset,) = struct.unpack(byte_order + "I", field)
            if value_offset + size > len(tiff):
                continue  # 壊れたエントリは捨てる
            value = tiff[value_offset:value_offset + size]
        entries[tag] = (typ, num, value)
    next_offset = 0
    if pos + 4 <= len(tiff):
        (next_offset,) = _unpack(byte_order, "I", tiff, pos)
    return entries, next_offset


def _pointer(entries, tag, byte_order):
    entry = entries.get(tag)
    if not entry:
        return None
    try:
        (offset,) = struct.unpack(byte_order + "I", entry[2][:4])
    except struct.error:
        return None
    return offset or None


class Exif(object):
    """Exif (TIFF) 構造を保持し, 書き戻せる形に再構築する."""

    # 新規作成時はビッグエンディアン (MM) にする. UNICODE の UserComment を
    # 常に UTF-16-BE と解釈する実装 (piexif など) とも一致し, 互換性が高いため.
    def __init__(self, byte_order=">"):
        self.byte_order = byte_order
        self.ifd0 = {}
        self.exif = {}
        self.gps = None
        self.interop = None
        self.ifd1 = None
        self.thumbnail = b""

    # ---- 読み込み
    @classmethod
    def parse(cls, tiff):
        if tiff[:2] == b"II":
            byte_order = "<"
        elif tiff[:2] == b"MM":
            byte_order = ">"
        else:
            raise JpegError("TIFF ヘッダが不正です")
        self = cls(byte_order)
        (magic, ifd0_offset) = _unpack(byte_order, "HI", tiff, 2)
        if magic != 42:
            raise JpegError("TIFF マジックが不正です")
        self.ifd0, next_offset = parse_ifd(tiff, ifd0_offset, byte_order)

        exif_offset = _pointer(self.ifd0, TAG_EXIF_IFD, byte_order)
        if exif_offset:
            self.exif, _ = parse_ifd(tiff, exif_offset, byte_order)
        gps_offset = _pointer(self.ifd0, TAG_GPS_IFD, byte_order)
        if gps_offset:
            self.gps, _ = parse_ifd(tiff, gps_offset, byte_order)
        interop_offset = _pointer(self.exif, TAG_INTEROP_IFD, byte_order)
        if interop_offset:
            self.interop, _ = parse_ifd(tiff, interop_offset, byte_order)

        if next_offset:
            self.ifd1, _ = parse_ifd(tiff, next_offset, byte_order)
            offset = _pointer(self.ifd1, TAG_THUMB_OFFSET, byte_order)
            length_entry = self.ifd1.get(TAG_THUMB_LENGTH)
            if offset and length_entry:
                length = self._scalar(length_entry)
                self.thumbnail = tiff[offset:offset + length]
        return self

    def _scalar(self, entry):
        typ, _num, value = entry
        fmt = {3: "H", 4: "I", 9: "i"}.get(typ)
        if not fmt:
            return 0
        try:
            return struct.unpack(self.byte_order + fmt, value[:TYPE_SIZE[typ]])[0]
        except struct.error:
            return 0

    # ---- UserComment
    def get_comment(self):
        entry = self.exif.get(TAG_USER_COMMENT)
        if not entry:
            return ""
        return decode_user_comment(entry[2], self.byte_order)

    def set_comment(self, comment):
        if comment:
            value = encode_user_comment(comment, self.byte_order)
            self.exif[TAG_USER_COMMENT] = (TYPE_UNDEFINED, len(value), value)
        else:
            self.exif.pop(TAG_USER_COMMENT, None)
        if TAG_EXIF_VERSION not in self.exif:
            self.exif[TAG_EXIF_VERSION] = (TYPE_UNDEFINED, 4, b"0230")

    # ---- 書き出し
    def to_bytes(self):
        byte_order = self.byte_order
        ifd0 = dict(self.ifd0)
        exif = dict(self.exif)
        gps = dict(self.gps) if self.gps is not None else None
        interop = dict(self.interop) if self.interop is not None else None
        ifd1 = dict(self.ifd1) if self.ifd1 is not None else None

        placeholder = (TYPE_LONG, 1, b"\x00\x00\x00\x00")
        for tag in (TAG_EXIF_IFD, TAG_GPS_IFD):
            ifd0.pop(tag, None)
        exif.pop(TAG_INTEROP_IFD, None)
        if exif:
            ifd0[TAG_EXIF_IFD] = placeholder
        if gps:
            ifd0[TAG_GPS_IFD] = placeholder
        if interop:
            exif[TAG_INTEROP_IFD] = placeholder
        if ifd1 is not None:
            if self.thumbnail:
                ifd1[TAG_THUMB_OFFSET] = placeholder
                ifd1[TAG_THUMB_LENGTH] = (
                    TYPE_LONG, 1, struct.pack(byte_order + "I", len(self.thumbnail)))
            else:
                ifd1.pop(TAG_THUMB_OFFSET, None)
                ifd1.pop(TAG_THUMB_LENGTH, None)
                if not ifd1:
                    ifd1 = None

        # ポインタ値は 4 バイトに収まるため, 先に全ブロックのサイズを確定できる
        blocks = [ifd0, exif, interop, gps, ifd1]
        offsets = []
        pos = 8
        for entries in blocks:
            if entries is None:
                offsets.append(None)
                continue
            offsets.append(pos)
            pos += ifd_size(entries) + data_size(entries)
        thumb_offset = pos

        def long_value(number):
            return (TYPE_LONG, 1, struct.pack(byte_order + "I", number))

        if exif:
            ifd0[TAG_EXIF_IFD] = long_value(offsets[1])
        if gps:
            ifd0[TAG_GPS_IFD] = long_value(offsets[3])
        if interop:
            exif[TAG_INTEROP_IFD] = long_value(offsets[2])
        if ifd1 is not None and self.thumbnail:
            ifd1[TAG_THUMB_OFFSET] = long_value(thumb_offset)

        out = [b"II" if byte_order == "<" else b"MM",
               struct.pack(byte_order + "HI", 42, offsets[0])]
        for index, entries in enumerate(blocks):
            if entries is None:
                continue
            is_ifd0 = index == 0
            next_offset = offsets[4] if (is_ifd0 and ifd1 is not None) else 0
            out.append(serialize_ifd(entries, offsets[index], next_offset, byte_order))
        out.append(self.thumbnail)
        return b"".join(out)


def ifd_size(entries):
    return 2 + 12 * len(entries) + 4


def data_size(entries):
    total = 0
    for _typ, _num, value in entries.values():
        if len(value) > 4:
            total += len(value) + len(value) % 2  # 偶数境界に揃える
    return total


def serialize_ifd(entries, ifd_offset, next_offset, byte_order):
    head = [struct.pack(byte_order + "H", len(entries))]
    data = []
    data_offset = ifd_offset + ifd_size(entries)
    cursor = 0
    for tag in sorted(entries):
        typ, num, value = entries[tag]
        if len(value) <= 4:
            field = value + b"\x00" * (4 - len(value))
        else:
            field = struct.pack(byte_order + "I", data_offset + cursor)
            padded = value + (b"\x00" if len(value) % 2 else b"")
            data.append(padded)
            cursor += len(padded)
        head.append(struct.pack(byte_order + "HHI", tag, typ, num) + field)
    head.append(struct.pack(byte_order + "I", next_offset))
    return b"".join(head) + b"".join(data)


# ---------------------------------------------------------------- UserComment の符号化

def encode_user_comment(comment, byte_order):
    """Exif 仕様の 8 バイト文字コード識別子 + 本体 を作る."""
    if comment.isascii():
        return b"ASCII\x00\x00\x00" + comment.encode("ascii")
    encoding = "utf-16-le" if byte_order == "<" else "utf-16-be"
    return b"UNICODE\x00" + comment.encode(encoding)


# 識別子が当てにならないときに試す符号化. 厳密に解けた最初のものを採る.
# 日本語の写真は識別子が空で本体が cp932 (Shift-JIS) のものが多い.
FALLBACK_ENCODINGS = ("utf-8", "cp932", "euc_jp")


def decode_text(data):
    for encoding in FALLBACK_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def decode_user_comment(raw, byte_order):
    if not raw:
        return ""
    prefix, body = raw[:8], raw[8:]
    if prefix == b"ASCII\x00\x00\x00":
        text = decode_text(body)
    elif prefix == b"UNICODE\x00":
        encoding = "utf-16-le" if byte_order == "<" else "utf-16-be"
        text = body.decode(encoding, "replace")
        if "�" in text or "\x00" in text.rstrip("\x00"):
            other = "utf-16-be" if encoding == "utf-16-le" else "utf-16-le"
            alt = body.decode(other, "replace")
            if alt.count("�") < text.count("�"):
                text = alt
    elif prefix == b"JIS\x00\x00\x00\x00\x00":
        text = body.decode("iso2022_jp", "replace")
    elif prefix == b"\x00" * 8:
        text = decode_text(body)
    else:
        text = decode_text(raw)  # 識別子なしの実装向け
    return text.rstrip("\x00").rstrip()


# ---------------------------------------------------------------- ファイル単位の入出力

_NO_EXIF = object()


def _scan_exif_head(data):
    """先頭バッファから Exif の TIFF 部を探す (読み出し専用の速い経路).

    戻り値は次の 3 通り.
      bytes    : Exif が見つかった
      _NO_EXIF : Exif が無いと確定した (SOS まで届いた)
      None     : 判断できない (バッファが足りない / 壊れている)
    None のときは呼び出し側が全体を読み直し, 元の経路で解釈する.
    """
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            return None
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            return None
        marker = data[i]
        i += 1
        if marker == 0xD9 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xDA:  # SOS 以降に Exif は現れない
            return _NO_EXIF
        if i + 2 > len(data):
            return None
        length = struct.unpack(">H", data[i:i + 2])[0]
        if length < 2:
            return None
        end = i + length
        if end > len(data):  # セグメントが途中で切れている
            return None
        if marker == 0xE1 and data[i + 2:i + 8] == EXIF_HEADER:
            return data[i + 8:end]
        i = end
    return None


def read_comment(path):
    with open(path, "rb") as handle:
        data = handle.read(HEADER_SCAN)
        found = _scan_exif_head(data)
        if found is _NO_EXIF:
            return ""
        if found is not None:
            return Exif.parse(found).get_comment()
        if len(data) >= HEADER_SCAN:  # 足りなければ残りを読んで元の経路へ
            data += handle.read()
    segments, _tail = split_segments(data)
    _index, tiff = find_exif(segments)
    if tiff is None:
        return ""
    return Exif.parse(tiff).get_comment()


def write_comment(path, comment, out_path=None):
    with open(path, "rb") as handle:
        data = handle.read()
    segments, tail = split_segments(data)
    index, tiff = find_exif(segments)
    if tiff is None and not comment and not out_path:
        return  # Exif が無いファイルに空コメント -> 何もしない
    exif = Exif.parse(tiff) if tiff is not None else Exif()
    exif.set_comment(comment)
    payload = EXIF_HEADER + exif.to_bytes()
    if len(payload) + 2 > 0xFFFF:
        raise JpegError("Exif が 64KB を超えるため書き込めません")
    if index is None:
        index = 1 if segments and segments[0][0] == 0xE0 else 0
        segments.insert(index, (0xE1, payload))
    else:
        segments[index] = (0xE1, payload)
    target = out_path or path
    tmp = target + ".tmp"
    with open(tmp, "wb") as handle:
        handle.write(join_segments(segments, tail))
    os.replace(tmp, target)


def collect_jpegs(paths, recursive):
    files = []
    for path in paths:
        if os.path.isdir(path):
            if recursive:
                for root, _dirs, names in os.walk(path):
                    files += [os.path.join(root, n) for n in sorted(names)
                              if n.lower().endswith(JPEG_EXTS)]
            else:
                files += [os.path.join(path, n) for n in sorted(os.listdir(path))
                          if n.lower().endswith(JPEG_EXTS)]
        else:
            files.append(path)
    return files


# ---------------------------------------------------------------- コマンド

def cmd_export(args):
    files = collect_jpegs(args.paths, args.recursive)
    if not files:
        sys.exit("JPEG ファイルが見つかりません")
    base = args.base or (args.paths[0] if os.path.isdir(args.paths[0]) else ".")
    rows = []
    errors = 0
    for path in files:
        if args.basename:
            name = os.path.basename(path)
        elif args.relative:
            name = os.path.relpath(path, base)
        else:
            name = os.path.abspath(path)
        try:
            rows.append([name, read_comment(path)])
        except (JpegError, OSError) as error:
            errors += 1
            print("skip: %s (%s)" % (path, error), file=sys.stderr)
    stream = (open(args.output, "w", encoding="utf-8-sig", newline="")
              if args.output else sys.stdout)
    try:
        writer = csv.writer(stream)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    finally:
        if args.output:
            stream.close()
    print("exported %d file(s)%s" % (len(rows), " / %d error(s)" % errors if errors else ""),
          file=sys.stderr)


SKIP = object()


def resolve_comment(existing, comment, mode, separator=DEFAULT_SEPARATOR):
    """書き込むべき UserComment を返す. 触らないときは SKIP を返す.

    overwrite      : CSV の comment が空でないときだけ置き換える
    overwrite-all  : 空でも置き換える (空ならタグを削除する)
    append (既定)  : 既に同じ内容があれば触らず, 無ければ継ぎ足す
    """
    if mode == "overwrite-all":
        return comment
    if not comment.strip():
        return SKIP          # overwrite / append は空の comment では何もしない
    if mode == "overwrite":
        return comment
    if not existing.strip():
        return comment
    # 同じ内容を二度足さない (繰り返し実行しても増えない)
    if comment.strip() in [part.strip() for part in existing.split(separator)]:
        return SKIP
    return existing + separator + comment


def cmd_import(args):
    with open(args.csv, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        sys.exit("CSV が空です")
    if [c.strip().lower() for c in rows[0][:2]] == CSV_HEADER:
        rows = rows[1:]
    base = args.base or os.path.dirname(os.path.abspath(args.csv))
    updated = 0
    skipped = 0
    errors = 0
    for number, row in enumerate(rows, start=2):
        if not row or not row[0].strip():
            continue
        name = row[0].strip()
        comment = row[1] if len(row) > 1 else ""
        path = name if os.path.isabs(name) else os.path.join(base, name)
        out_path = None
        if args.outdir:
            out_path = os.path.join(args.outdir, os.path.basename(name))
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        try:
            existing = "" if args.mode == "overwrite-all" else read_comment(path)
            value = resolve_comment(existing, comment, args.mode, args.separator)
            if value is SKIP:
                skipped += 1
                continue
            if args.dry_run:
                print("%s <- %s" % (path, value))
            else:
                write_comment(path, value, out_path)
            updated += 1
        except (JpegError, OSError) as error:
            errors += 1
            print("line %d: skip %s (%s)" % (number, path, error), file=sys.stderr)
    print("%s %d file(s)%s%s" % ("would update" if args.dry_run else "updated", updated,
                                 " / %d unchanged" % skipped if skipped else "",
                                 " / %d error(s)" % errors if errors else ""),
          file=sys.stderr)
    if errors:
        sys.exit(1)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="JPEG の Exif UserComment を CSV (filename,comment) で入出力する")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="JPEG のコメントを CSV に書き出す")
    export.add_argument("paths", nargs="+", help="JPEG ファイルまたはディレクトリ")
    export.add_argument("-o", "--output", help="出力 CSV (既定: 標準出力)")
    export.add_argument("-r", "--recursive", action="store_true", help="サブディレクトリも辿る")
    export.add_argument("--basename", action="store_true",
                        help="filename 列をファイル名だけにする (既定はフルパス)")
    export.add_argument("--relative", action="store_true",
                        help="filename 列を基準ディレクトリからの相対パスにする")
    export.add_argument("--base", help="--relative の基準ディレクトリ")
    export.set_defaults(func=cmd_export)

    imp = sub.add_parser("import", help="CSV のコメントを JPEG に書き込む")
    imp.add_argument("csv", help="入力 CSV (filename,comment)")
    imp.add_argument("--base", help="filename を解決する基準ディレクトリ (既定: CSV と同じ場所)")
    imp.add_argument("--outdir", help="上書きせず, このディレクトリに書き出す")
    imp.add_argument("-n", "--dry-run", action="store_true", help="書き込まずに内容を表示する")
    mode = imp.add_mutually_exclusive_group()
    mode.add_argument("--append", dest="mode", action="store_const", const="append",
                      help="既存のコメントに継ぎ足す (既定. 同じ内容なら足さない)")
    mode.add_argument("--overwrite", dest="mode", action="store_const", const="overwrite",
                      help="CSV の comment が空でない行だけ置き換える")
    mode.add_argument("--overwrite-all", dest="mode", action="store_const", const="overwrite-all",
                      help="comment の有無に関わらず置き換える (空ならタグを削除)")
    imp.set_defaults(mode="append")
    imp.add_argument("--separator", default=DEFAULT_SEPARATOR,
                     help="--append の区切り (既定: 改行)")
    imp.set_defaults(func=cmd_import)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
