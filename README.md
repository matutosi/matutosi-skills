# matutosi-skills

Claude Code のプラグインのマーケットプレイスです．
日本語の Markdown 原稿を整形・推敲するスキル，JPEG 写真のコメントを CSV で読み書きするスキル，
学会誌の論文 PDF から J-STAGE の全文 XML を作るスキルを収めています．

A Claude Code plugin marketplace with skills for Japanese Markdown manuscripts and for the Exif UserComment of JPEG files.

<a id="install"></a>

## 入れ方 / Install

Claude Code で次を実行してください．

```
/plugin marketplace add matutosi/matutosi-skills
/plugin install ja-manuscript@matutosi-skills
/plugin install jpg-user-comment@matutosi-skills
/plugin install jstage-xml@matutosi-skills
```

必要なプラグインだけを入れても構いません．
入れたあとは，Claude Code を開き直すとスキルが読み込まれます．

<a id="plugins"></a>

## プラグイン / Plugins

<a id="ja-manuscript"></a>

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
- `apply-proof-marks`: `pypdf`・`pypdfium2`・`numpy`・`Pillow` (どれも `pip install` で入る)
- ほかの5つ: Python の標準ライブラリだけ

<a id="jpg-user-comment"></a>

### jpg-user-comment (JPEG のコメント)

JPEG の Exif UserComment (タグ 0x9286) を，ファイル名とコメントの2列の CSV で書き出し，書き戻します．
表計算ソフトでコメントをまとめて編集したいときに使えます．
Python の標準ライブラリだけで動きます．

Export the Exif UserComment of JPEG files to a CSV, edit it in a spreadsheet, and import it back.
Only the Python standard library is required.

<a id="jstage-xml"></a>

### jstage-xml (J-STAGE の全文 XML)

学会誌の論文 PDF (原稿の無い過去の号を含む) から，J-STAGE に登載する全文 XML (JATS 1.1，FULL-J) と登載用の zip を作るスキル `pdf-to-jstage-xml` です．
「この論文 PDF を J-STAGE の全文 XML にして」のように頼むと使われます．手順は [SKILL.md](plugins/jstage-xml/skills/pdf-to-jstage-xml/SKILL.md) にあります．

- 雑誌ごとの設定は `journals/<資料コード>.yaml` に置きます．ひな形 (`_template`) と，作例として植生学会誌 (`vegsci`) の設定と記録が入っています．
- 作業ディレクトリ・控え・記事識別子の対応表は，任意のフォルダ (作業の根) に置きます．環境変数 `JSTAGE_ROOT` か `--root` で渡します．
- 必要な道具: Python 3.11 以降と `pip install pymupdf lxml pyyaml`．スキャンの号は，PDF に入っている OCR の文字をそのまま使います．
- 論文一覧の取得 (`scripts/list_articles.py`) と，登載前に見た目を確かめる手元のプレビュー (`scripts/preview_tool/`) も入っています．
- 控えの取り方と調査のまとめは，[support-ac](https://github.com/matutosi/support-ac) の `jstage/` を見てください．

<a id="examples"></a>

## サンプル / Examples

各プラグインの `examples/` に，手で試すためのサンプルと手順 (README) があります．
試すときは，フォルダを別の場所に写してから使ってください (原稿や写真を書き換えるため)．

- [plugins/ja-manuscript/examples/](plugins/ja-manuscript/examples/): 誤りをわざと入れた2章の練習原稿と，リライトの草稿
- [plugins/jpg-user-comment/examples/](plugins/jpg-user-comment/examples/): JPEG 2枚と，コメントを書いた CSV

<a id="tests"></a>

## テスト / Tests

スクリプトのテストは，各スキルの `tests/` にあります．
次のコマンドで，すべてを順に走らせます．

```
python run_tests.py
```

`jstage-xml` のテストは PyMuPDF・PyYAML が無いと一部を飛ばします．
`apply-proof-marks` のテストには `pypdf`・`Pillow` が要り，画像の切り出しの試験には `pypdfium2` も要ります．
無いときは，その試験だけを飛ばします．
GitHub では，push のたびに Ubuntu と Windows でテストを回します (`.github/workflows/test.yml`)．

<a id="license"></a>

## ライセンス / License

MIT License．[LICENSE](LICENSE) を見てください．
