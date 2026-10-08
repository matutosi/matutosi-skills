---
name: jpg-user-comment
description: Read and write the Exif UserComment (tag 0x9286) of JPEG files using a CSV of filename and comment. Use when the user wants to export photo comments to CSV, bulk-edit or bulk-tag JPEG comments from a spreadsheet, or import comments back into .jpg files. JPEG のユーザーコメント (User Comment) を CSV で一括入力・出力したいとき。
---

# JPEG ユーザーコメント ⇄ CSV

JPEG の Exif **UserComment** (tag 0x9286) を CSV (`filename,comment`) で読み書きする。
`scripts/jpg_comment.py` は Python 標準ライブラリのみで動作する (Pillow / piexif は不要)。

## 使い方

```bash
S=${CLAUDE_SKILL_DIR}/scripts/jpg_comment.py

# 出力: JPEG -> CSV
python3 "$S" export photos/ -o comments.csv     # ディレクトリ内の JPEG (filename はフルパス)
python3 "$S" export a.jpg b.jpg                 # 個別指定 (-o 省略で標準出力)
python3 "$S" export photos/ -r -o comments.csv              # 再帰 (フルパス)
python3 "$S" export photos/ -r --relative -o comments.csv   # 再帰 + 相対パス
python3 "$S" export photos/ --basename -o comments.csv      # ファイル名だけ

# 入力: CSV -> JPEG
python3 "$S" import comments.csv                 # 既定は --append (継ぎ足す)
python3 "$S" import comments.csv -n              # dry-run (書き込まない)
python3 "$S" import comments.csv --overwrite     # comment が空でない行だけ置き換える
python3 "$S" import comments.csv --overwrite-all # 空の行も置き換える (= タグを削除)
python3 "$S" import comments.csv --separator " / "  # 継ぎ足しの区切りを変える
python3 "$S" import comments.csv --outdir out/   # 元ファイルを残して別ディレクトリへ
```

主なオプション:

| オプション | 対象 | 意味 |
|---|---|---|
| `-o, --output` | export | 出力 CSV (既定: 標準出力) |
| `-r, --recursive` | export | サブディレクトリも辿る |
| `--basename` | export | `filename` 列をファイル名だけにする |
| `--relative` / `--base` | export | `filename` 列を基準ディレクトリからの相対パスにする |
| `--base` | import | `filename` を解決する基準 (既定: CSV と同じディレクトリ) |
| `--append` | import | 既存のコメントに継ぎ足す (**既定**) |
| `--overwrite` | import | `comment` が空でない行だけ置き換える |
| `--overwrite-all` | import | `comment` の有無に関わらず置き換える |
| `--separator` | import | `--append` の区切り (既定: 改行) |
| `--outdir` | import | 上書きせず別ディレクトリに書き出す |
| `-n, --dry-run` | import | 書き込まず内容を表示 |

## CSV の形式

`filename` 列は**既定でフルパス**にする (`--basename` / `--relative` で変えられる)。
同じ名前の写真が別のディレクトリにあっても取り違えないため。

```csv
filename,comment
D:\photo\2026\DSC_0001.jpg,桜の花, 京都
D:\photo\2026\DSC_0002.jpg,"改行や ""引用符"" を含む場合は CSV の規則どおり"
D:\photo\2026\DSC_0003.jpg,
```

- 1 行目の見出し `filename,comment` は省略可 (あれば読み飛ばす)。
- 文字コードは **UTF-8 (BOM 付き)** で書き出すため、Excel でそのまま開ける。読み込みは BOM あり・なしのどちらも可。
- `comment` が空の行の扱いはモードで変わる (下の「書き込みのモード」)。
- import 時の `filename` は絶対パス、または `--base` 基準の相対パス。

## 書き込みのモード

`import` は 3 つのうち 1 つで動く (同時には指定できない)。**既定は `--append`**。

| モード | `comment` が空でない | `comment` が空 |
|---|---|---|
| `--append` (既定) | 既存と**同じなら何もしない**。違えば区切りを挟んで**継ぎ足す** | 何もしない |
| `--overwrite` | **置き換える** | 何もしない |
| `--overwrite-all` | **置き換える** | **タグを削除する** |

- `--append` の「同じ」は、既存を区切りで分けた各段との比較 (前後の空白は無視)。
  そのため**同じ CSV を何度流し込んでも増えない**。
- 区切りは既定で**改行**。`--separator " / "` のように変えられる。
  CSV 側では改行を含むセルとして引用符で囲まれるので、往復しても崩れない。
- どのモードでも、**CSV に行が無いファイルには触れない**。
- 迷ったらまず `-n` (dry-run) で、何がどう書かれるかを見る。

## 振る舞いと注意点

- 書き込みは Exif ブロックを再構築するが、**既存の Exif は保持する** — 撮影日時・メーカー/機種・GPS・Interop・サムネイル・IFD1、および画像データそのものは変更されない。バイトオーダー (II/MM) も元のまま。
- Exif が無い JPEG には、最小の Exif (APP1) を新規に作って挿入する (JFIF APP0 の直後)。新規作成分はビッグエンディアン (MM) にして、UNICODE を常に UTF-16-BE と解釈する実装 (piexif など) とも読み合わせが一致するようにしている。
- 文字コード識別子は Exif 仕様どおり、ASCII のみなら `ASCII\0\0\0`、それ以外は `UNICODE\0` + UTF-16。読み込み時は ASCII / UNICODE / JIS および識別子なしの実装にも対応する。
- 識別子が `ASCII` や**空 (0 埋め)** の場合、中身は UTF-8 とは限らない。日本語の写真は **cp932 (Shift-JIS)** で書かれていることが多いので、`utf-8` → `cp932` → `euc_jp` の順に**厳密に解けた最初の符号化**を採る (`FALLBACK_ENCODINGS`)。UTF-8 決め打ちだと日本語が全て U+FFFD に化ける (2026-09-08 に修正)。
- 書き込みは一時ファイル経由の `os.replace` なので、途中で失敗しても元ファイルは壊れない。
- 読み出しは**先頭 128KB だけ**を読んで Exif APP1 を探す (`HEADER_SCAN`)。そこで決着しなければ全体を読み直して元の経路で解釈するので、結果は変わらない。写真 1 枚が数 MB あっても I/O は頭だけで済む。
- **Pillow / piexif は使わない**。写真 200 枚 (計 495MB) で計測すると 標準ライブラリ 0.08 秒 に対し Pillow は 0.13 秒 で、外部依存を足しても速くならない (2026-09-08 実測)。
- Exif は 1 セグメント 64KB までのため、極端に長いコメントはエラーになる。
- UserComment は Windows エクスプローラーの「コメント」欄 (XPComment, tag 0x9C9C) とは**別のタグ**。エクスプローラー表示が目的の場合はその旨を確認する。

## 動作確認

```bash
python3 ${CLAUDE_SKILL_DIR}/tests/test_jpg_comment.py
```

外部依存なしで、往復変換・日本語・既存 Exif とサムネイルの保持・削除・冪等性を検証する。
