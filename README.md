# matutosi-skills

Claude Code のプラグインのマーケットプレイスです．
日本語の Markdown 原稿を整形・推敲するスキルと，JPEG 写真のコメントを CSV で読み書きするスキルを収めています．

A Claude Code plugin marketplace with skills for Japanese Markdown manuscripts and for the Exif UserComment of JPEG files.

## 入れ方 / Install

Claude Code で次を実行してください．

```
/plugin marketplace add matutosi/matutosi-skills
/plugin install ja-manuscript@matutosi-skills
/plugin install jpg-user-comment@matutosi-skills
```

必要なプラグインだけを入れても構いません．
入れたあとは，Claude Code を開き直すとスキルが読み込まれます．

## プラグイン / Plugins

### ja-manuscript (日本語原稿の整形・推敲)

| スキル | 何をするか |
|---|---|
| `sentence-per-line` | 原稿を1文1行に整形し，段落の間の空行を1つにそろえる |
| `markdown-table-pad` | Markdown の表の列幅を，全角文字の幅を数えてそろえる |
| `manuscript-polish` | 入稿前の原稿を1回点検し，誤字脱字・表記ゆれ・文体・相互参照の問題を一覧にする |
| `polish-loop` | 章を分担した複数のレビュアで推敲を巡ごとに回し，指摘が収束するまで続ける |
| `rewrite-improve` | 見出しから書き起こしたリライトと元原稿を比べ，リライトの良い点を元原稿に採り入れる |
| `apply-proof-marks` | 紙に朱書きした校正 PDF (手書きの注釈入り) を読み，原稿の Markdown に反映する |

「1文ごとに改行して」「表を整形して」「推敲を回して」「朱書きを反映して」のように頼むと，対応するスキルが使われます．

必要な道具は次のとおりです．

- Python 3.9 以降
- `apply-proof-marks`: `pypdf`・`numpy`・`Pillow`，および poppler (`pdftoppm`・`pdftotext`)
- ほかの5つ: Python の標準ライブラリだけ

### jpg-user-comment (JPEG のコメント)

JPEG の Exif UserComment (タグ 0x9286) を，ファイル名とコメントの2列の CSV で書き出し，書き戻します．
表計算ソフトでコメントをまとめて編集したいときに使えます．
Python の標準ライブラリだけで動きます．

Export the Exif UserComment of JPEG files to a CSV, edit it in a spreadsheet, and import it back.
Only the Python standard library is required.

## サンプル / Examples

各プラグインの `examples/` に，手で試すためのサンプルと手順 (README) があります．
試すときは，フォルダを別の場所に写してから使ってください (原稿や写真を書き換えるため)．

- [plugins/ja-manuscript/examples/](plugins/ja-manuscript/examples/): 誤りをわざと入れた2章の練習原稿と，リライトの草稿
- [plugins/jpg-user-comment/examples/](plugins/jpg-user-comment/examples/): JPEG 2枚と，コメントを書いた CSV

## テスト / Tests

スクリプトのテストは，各スキルの `tests/` にあります．
次のコマンドで，すべてを順に走らせます．

```
python run_tests.py
```

`apply-proof-marks` のテストには `pypdf`・`Pillow` が要り，画像の切り出しの試験には poppler も要ります．
無いときは，その試験だけを飛ばします．
GitHub では，push のたびに Ubuntu と Windows でテストを回します (`.github/workflows/test.yml`)．

## ライセンス / License

MIT License．[LICENSE](LICENSE) を見てください．
