# build-index のサンプル

架空の入門書『はじめてのパンづくり』(3章) の原稿と，それを組んだ小さな PDF で，索引づくりを一通り試せます．
原稿は書き換えませんが，作業ファイルを作るので，このフォルダを別の場所に写してから試すのが無難です．

| ファイル | 中身 |
|---|---|
| `chapter_01.md`〜`chapter_03.md` | 原稿 (材料と道具・生地づくり・焼成と保存)．同じ語が章をまたいで出てきます |
| `sample_book.pdf` | 原稿を組んだ PDF (A6 で 11 ページ．1ページ目は目次でノンブルなし，本文は 2 ページ目が 1．日本語フォントは埋め込み) |
| `make_index_pdf.py` | `sample_book.pdf` を作り直すスクリプト (PyMuPDF と fontTools が要る) |
| `terms.yaml` | 見出し語の定義 (18 語．副見出し・参照・「も見よ」・主要ページを含む) |
| `index.md` | できあがりの索引 (正解) |

## 再現手順

必要なパッケージ: `pip install pypdfium2 pyyaml`．

```bash
# 1. 見出し語の候補を出す (章ごとの候補と，全章の表)
python <skills>/build-index/scripts/extract_candidates.py chapter_*.md -o _index_work

# 2. terms.yaml から索引を組み立てる
python <skills>/build-index/scripts/build_index.py terms.yaml -o my_index.md

# 3. 語ごとにヒットしたページと節を見る
python <skills>/build-index/scripts/build_index.py terms.yaml --check-only --report

# 4. 本文の段落を抜いて，索引から引けるかを確かめる
python <skills>/build-index/scripts/sample_paragraphs.py chapter_*.md -n 4 -t terms.yaml
```

`my_index.md` が `index.md` と同じになれば成功です．

## 見てほしいところ

- **並べ方**: 「発酵」「パンチ」「ハンドミキサー」「ベーキングパウダー」がは行にまとまり，
  「はっこう」(促音) が「ぱんち」(半濁音) より先に来ます．「ガス」は「型」より先です (がす < かた)．
  「pH」は英字の項に入ります．
- **主要ページ**: 「酵母」の 1，「グルテン」の 2，「焼成」の 8，「発酵」の 5 と 7 が太字です．
  「発酵」は 2, 5, 6, 7, 8, 9 のうち 5 と 7 が主要なので，`2, **5**, 6, **7**, 8-9` となります
  (主要ページを含む範囲は崩して書きます)．
- **参照**: 「イースト → 酵母」は，ページを持たずに参照先へ導きます．
- **警告**: この例は索引が本文に比べて大きいので，「分量が多い」の警告が1件出ます (小さな例なので正常です)．

## 点検を試す

`terms.yaml` を写して，次のように書き換えてから `--check-only` を実行すると，エラーが出ます．

| 書き換え | 出るエラー |
|---|---|
| 「発酵」の `主` を `[50]` にする | 主要ページが PDF の範囲の外 |
| 「イースト」の `参照` を `イースト` にする | 自分自身への参照 |
| 「パンチ」の `よみ` を消す | よみが無い (`suggest_yomi.py` の案内が出る) |

よみの候補を出すには，`pip install pykakasi` のうえで
`python <skills>/build-index/scripts/suggest_yomi.py terms.yaml` を実行します (書き込みません)．

## PDF を作り直す

```bash
pip install pymupdf fonttools
python make_index_pdf.py                  # 日本語フォントは自動で探す
python make_index_pdf.py --font <フォントの.ttf/.ttc>
```

フォントによって折り返しの位置が変わり，ページ番号がずれることがあります．
そのときは `build_index.py` で索引を作り直し，`terms.yaml` の `主` を確かめてください．
