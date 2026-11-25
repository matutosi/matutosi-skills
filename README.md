# matutosi-skills

Claude Code のプラグインのマーケットプレイスです．
次の6つのプラグイン (計14個のスキル) を収めています．

| プラグイン | スキル | 何をするか |
|---|---|---|
| [ja-manuscript](#ja-manuscript) | `apply-proof-marks` | 朱書きした校正 PDF・スキャン・写真を読み，原稿 (Markdown・Word) に反映する (採否はブラウザでも決められる) |
| | `build-index` | 書籍の原稿と PDF から，巻末の索引を作る |
| | `manuscript-polish` | 入稿前の原稿を1回点検し，問題を一覧にする |
| | `markdown-table-pad` | Markdown の表の列幅をそろえる |
| | `polish-loop` | 推敲を，指摘が収束するまで巡ごとに回す |
| | `rewrite-improve` | リライトの良い点を元原稿に採り入れる |
| | `sentence-per-line` | 原稿を1文1行に整形する |
| [jpg-user-comment](#jpg-user-comment) | `jpg-user-comment` | JPEG 写真のコメントを CSV で書き出し，書き戻す |
| [jstage-xml](#jstage-xml) | `pdf-to-jstage-xml` | 学会誌の論文 PDF から J-STAGE の全文 XML を作る |
| [vegetation-survey](#vegetation-survey) | `veg-sheet-to-csv` | 植生調査票を読み取って CSV にする (読み取りはブラウザで画像と見比べて直せる) |
| | `veg-table-to-csv` | 組成表 (ページ内の小さい表・折り込み) を AI が読み，地点情報と組成の CSV にする |
| | `veg-table-to-csv2` | 組成表を印字のまま読んで転記を固定し，規則で決定の CSV を作り直す．どの規則でどう直したかを列に残す |
| [graphical-abstract](#graphical-abstract) | `graphical-abstract` | 論文・書籍のグラフィカルアブストラクトを作る (絵は外部の画像生成ツールに回す) |
| [video-highlight](#video-highlight) | `video-highlight` | 2〜3分の動画から良い部分を選び，60 秒・30 秒などの指定の長さに縮める |

A Claude Code plugin marketplace with skills for Japanese manuscripts (Markdown; proof marks can also be applied to Word files as tracked changes), for the Exif UserComment of JPEG files, for building J-STAGE full-text XML from journal PDFs, for turning vegetation survey sheets into CSV, for composing graphical abstracts of papers and books, and for cutting a short video down to its best parts.

<a id="requirements"></a>

## 必要な環境 / Requirements

| プラグイン | Python | 追加のパッケージ (`pip install`) |
|---|---|---|
| ja-manuscript | 3.9 以降 | `apply-proof-marks` と `build-index` だけが要ります (下の表) |
| jpg-user-comment | 3.8 以降 (目安) | なし (標準ライブラリだけ．`comment_server.py` は `Pillow` があれば画像を縮小する) |
| jstage-xml | 3.11 以降 | `pymupdf` `lxml` `pyyaml`．論文一覧の取得 (`list_articles.py toc`) には `beautifulsoup4` も |
| vegetation-survey | `veg-sheet-to-csv` は 3.8 以降，`veg-table-to-csv`・`veg-table-to-csv2` は 3.9 以降 | `veg-table-to-csv` は `Pillow`，PDF を読むときは `pymupdf`．種名の照合だけ `openpyxl`，格子の点検と下線の確認 (`check_grid.py`・`marks_grid.py`・`shift_check.py`・`ul_sheet.py`) と傾きの直し (`crop.py --deskew`) だけ `numpy` と `scipy`．`veg-table-to-csv2` の固定と決定 (`freeze.py`・`decide.py`) は標準ライブラリだけ (種名の照合に `openpyxl`)．`veg-sheet-to-csv` は種名の照合 (`openpyxl`) のほかは標準ライブラリだけ (`build_csv.py`・`review.py`) |
| graphical-abstract | 3.8 以降 | `matplotlib` (`numpy` も入る)．PDF を読むときは `pymupdf`，JPEG の絵を使うときは `Pillow`．`make_prompts.py` は標準ライブラリだけ |
| video-highlight | 3.9 以降 | `numpy` `Pillow` `faster-whisper`．ほかに `ffmpeg`・`ffprobe` (PATH に置く) |

<a id="install"></a>

## 入れ方 / Install

Claude Code で次を実行してください．

```
/plugin marketplace add matutosi/matutosi-skills
/plugin install ja-manuscript@matutosi-skills
/plugin install jpg-user-comment@matutosi-skills
/plugin install jstage-xml@matutosi-skills
/plugin install vegetation-survey@matutosi-skills
/plugin install graphical-abstract@matutosi-skills
/plugin install video-highlight@matutosi-skills
```

PowerShell などのターミナルから入れるときは，次のようにします (`/plugin` の代わりに `claude plugin` と書きます)．

```
claude plugin marketplace add matutosi/matutosi-skills
claude plugin install ja-manuscript@matutosi-skills
claude plugin install jpg-user-comment@matutosi-skills
claude plugin install jstage-xml@matutosi-skills
claude plugin install vegetation-survey@matutosi-skills
claude plugin install graphical-abstract@matutosi-skills
claude plugin install video-highlight@matutosi-skills
```

必要なプラグインだけを入れても構いません．
入れたあとは，Claude Code を開き直すとスキルが読み込まれます．

コマンドが分からないときは，Claude Code にふつうの言葉で頼んでも入れてくれます．

```
GitHub の matutosi/matutosi-skills から ja-manuscript のスキルをインストールして
```

プラグイン名 (`ja-manuscript`) を `jpg-user-comment`・`jstage-xml`・`vegetation-survey`・`graphical-abstract`・`video-highlight` に替えれば，ほかのプラグインも同じように入れられます．

<a id="update"></a>

## 新しい版にする / Update

入れたプラグインは自動では新しい版になりません．
Claude Code で次を実行し，マーケットプレイスの情報を取り直してから，プラグインごとに更新してください．

```
/plugin marketplace update matutosi-skills
/plugin update ja-manuscript@matutosi-skills
/plugin update jpg-user-comment@matutosi-skills
/plugin update jstage-xml@matutosi-skills
/plugin update vegetation-survey@matutosi-skills
/plugin update graphical-abstract@matutosi-skills
/plugin update video-highlight@matutosi-skills
```

PowerShell などのターミナルから更新するときは，次のようにします．

```
claude plugin marketplace update matutosi-skills
claude plugin update ja-manuscript@matutosi-skills
claude plugin update jpg-user-comment@matutosi-skills
claude plugin update jstage-xml@matutosi-skills
claude plugin update vegetation-survey@matutosi-skills
claude plugin update graphical-abstract@matutosi-skills
claude plugin update video-highlight@matutosi-skills
```

入れていないプラグインの行は飛ばしてください．
更新したあとは，Claude Code を開き直すと新しい版が読み込まれます．
いまの版は `claude plugin list` で確かめられます．

コマンドが分からないときは，Claude Code にふつうの言葉で頼んでも更新してくれます．

```
matutosi-skills のプラグインを，すべて新しい版に更新して
```

1つだけ更新するときは，「matutosi-skills の ja-manuscript を新しい版に更新して」のようにプラグイン名を書きます．

<a id="plugins"></a>

## プラグイン / Plugins

<a id="ja-manuscript"></a>

### ja-manuscript (日本語原稿の整形・推敲)

| スキル | 何をするか |
|---|---|
| `apply-proof-marks` | 紙に朱書きした校正 PDF (手書きの注釈入り)・スキャン・スマホの写真を読み，原稿に反映する．原稿は Markdown などの UTF-8 のテキストと Word (.docx．変更履歴・書き換え・コメントから選ぶ．既定は変更履歴)．修正案は，朱書きの画像と修正前・修正後の差分を並べたブラウザの画面で採否を決められる (案の選択・文の手直し・自分で書いた直し・保留とメモ．`proof_review.py`) |
| `build-index` | 書籍の原稿とビルド済み PDF から，巻末の索引を作る．PDF を全文検索してページ番号を付け，辞書の規則 (清音 → 濁音 → 半濁音，長音符は直前の母音) で並べる．主要ページの太字と点検も行う |
| `manuscript-polish` | 入稿前の原稿を1回点検し，誤字脱字・表記ゆれ・文体・相互参照の問題を一覧にする |
| `markdown-table-pad` | Markdown の表の列幅を，全角文字の幅を数えてそろえる |
| `polish-loop` | 章を分担した複数のレビュアで推敲を巡ごとに回し，指摘が収束するまで続ける |
| `rewrite-improve` | 見出しから書き起こしたリライトと元原稿を比べ，リライトの良い点を元原稿に採り入れる |
| `sentence-per-line` | 原稿を1文1行に整形し，段落の間の空行を1つにそろえる |

「1文ごとに改行して」「表を整形して」「推敲を回して」「朱書きを反映して」「索引を作って」のように頼むと，対応するスキルが使われます．

スキルごとに要る道具は次のとおりです (Python は 3.9 以降)．

| スキル | 追加のパッケージ (`pip install`) | 任意で足すもの |
|---|---|---|
| `apply-proof-marks` | `pypdf` `pypdfium2` `numpy` `Pillow` | もとの原稿との差で探す `--ref` を使うときだけ `opencv-python`．AES で暗号化された PDF を開くときだけ `cryptography`．ブラウザの画面 (`proof_review.py`) と Word の原稿に当てる `apply_docx.py` は追加なしで動く |
| `build-index` | `pypdfium2` `pyyaml` | 見出しのよみの候補を出す補助に `pykakasi` |
| ほかの5つ | なし (標準ライブラリだけ) | |

パスワード付きの PDF は，`--password <パスワード>` か環境変数 `PDF_PASSWORD` で渡すと開けます (`apply-proof-marks`・`build-index`．履歴に残したくなければ環境変数)．
AES で暗号化された PDF を `apply-proof-marks` で開くときは，`pip install cryptography` も要ります．

<a id="jpg-user-comment"></a>

### jpg-user-comment (JPEG のコメント)

JPEG の Exif UserComment (タグ 0x9286) を，ファイル名とコメントの2列の CSV で書き出し，書き戻します．
表計算ソフトでコメントをまとめて編集したいときに使えます．
写真を見ながらブラウザで直すこともできます (`comment_server.py`．左に写真，右にコメント欄が並びます)．
Python の標準ライブラリだけで動きます (Pillow があれば，ブラウザの画像の縮小と回転が効きます)．

Export the Exif UserComment of JPEG files to a CSV, edit it in a spreadsheet or in the browser next to each photo, and import it back.
Only the Python standard library is required.

<a id="vegetation-survey"></a>

### vegetation-survey (植生調査資料のデータ化)

植生調査票 (PDF・画像) を読み取り，植生調査資料DB形式 (47 列) の CSV にするスキル `veg-sheet-to-csv` です．
「この植生調査票を CSV にして」のように頼むと使われます．手順は [SKILL.md](plugins/vegetation-survey/skills/veg-sheet-to-csv/SKILL.md) にあります．

- 先に選べる項目 (実行時に番号つきの表で示します):

  | 項目 | 選べるもの | 既定 |
  |---|---|---|
  | 出力の形 | 1ファイル／地点と組成の2ファイル | 1ファイル |
  | 種名のカナ | 全角／半角 | 半角 |
  | データの無いセル | 空欄／`NA` | 空欄 |
  | 文字コード | `cp932`／`utf-8-sig`／`utf-8` | `cp932` |
  | 不明なコード (面積測定方法・被度の評価方法) | `0`／空欄 | `0` |

- 調査票の書き方のパターン (被度・群度，階層，地点情報，種名) を `references/patterns.md` にまとめています．入力と出力の例を渡すと，それに合わせます．
- **読み取った結果は，ブラウザで調査票の画像と見比べながら直せます** (`review.py serve`)．左に画像 (拡大・移動)，右に地点情報と種の表が並び，その場で直して保存すると JSON に書き戻します (初回に写しを残す)．自信の低い箇所と，種名の照合で見つからない・似た名前の種に色が付きます．
- 実行中に足りない点が見つかれば，直す案を示し，選んだものだけスキルに反映します．
- 種名は，GBIF Japan の[維管束植物和名チェックリスト](https://gbif.jp/activities/checklist/wamei_checklist_110/) (ver. 1.10，CC BY 4.0) と照合できます (`check_names.py`)．異名の検出・似た名前の候補・空の学名と科名の補完をします．
- 必要な Python は **3.8 以上**です (スクリプトの構文は 3.6 でも通りますが，3.8 以上を目安にしています)．道具は[必要な環境](#requirements)の表を見てください．

組成表を読むスキル `veg-table-to-csv` もあります．
「この組成表を CSV にして」のように頼むと使われます．手順は [SKILL.md](plugins/vegetation-survey/skills/veg-table-to-csv/SKILL.md) にあります．

- **読むのは AI，切り出し・変換・検算はスクリプト**です．AI は画像を印字のまま転記表 (TSV) に書き，スクリプトが値を分解して縦持ちの `sites.csv`・`composition.csv` にし，出現種数と照合します．
- **AI が画像を読むので，トークンの消費が大きい点に注意してください**．ページ内の小さい表で 1 表あたり約 1.4 万トークン，折り込みの大きい表では 1 表で数十万トークンになることがあります ([消費と時間の目安](plugins/vegetation-survey/skills/veg-table-to-csv/SKILL.md#消費と時間の目安))．表が多いときは，まず 1 表だけ読んで消費を確かめ，サブエージェントに数表ずつ渡すと抑えられます．
- 本文・写真と同じ紙面の小さい表，2 段組，表頭の無い表，1 枚に複数の表が載った折り込みを読めます．本は，縮小画像の一覧から表のあるページを選びます．
- **AI が決められない箇所は，ブラウザで画像を見ながらユーザが決められます**．
  和名などの直しは `review.py serve` の画面 (左に画像，右に入力欄．欄から離れると保存し，`apply` で転記へ反映)，
  値の確認などは赤い印つきの画像を埋め込んだ 1 枚の HTML (`review_html.py`．サーバ不要．選択肢はラジオボタン，回答は JSON で保存) で答えます．
  推定で決めた割り当てや読めない値は，読みながら `user_review.tsv` に積み，指示が無くても確認用の HTML を用意します．
- 表ごとに進み具合を `tables.tsv` に記録するので，途中から再開できます．
- 実行中の気づきを `improvements.tsv` に貯め，スキルの直し方の案として示します．選んだものだけ反映します．

組成表を印字のまま読み直し，規則で決定を作るスキル `veg-table-to-csv2` もあります．
「組成表を印字のまま読み直して」「規則を変えて CSV を作り直して」のように頼むと使われます．手順は [SKILL.md](plugins/vegetation-survey/skills/veg-table-to-csv2/SKILL.md) にあります．

- **転記・矛盾・決定の 3 層**に分けます．転記は印字のままの値で，固定したあとは書き換えません．決定は，転記に規則を当てた結果です．
- 読み方の決まりは [reading.md](plugins/vegetation-survey/skills/veg-table-to-csv2/references/reading.md) にあります．読むときは値を直さず，印字のとおりに書きます．
- 決定の規則 (D01〜D40) は，字の乱れ・書式・名前・表頭・階層・1 回出現の見出しのずれの 6 段に分かれます．一覧は [rules.md](plugins/vegetation-survey/skills/veg-table-to-csv2/references/rules.md) にあります．
- 決定の CSV には，どの規則でどう直したかを列に残します．そのため，規則を変えても画像を読み直さずに決定だけを作り直せます．
- 規則で決まらない箇所は，個別の判断 (`judgments.tsv`) と画像の確認 (`user_review.tsv`) に回します．
- 画像の切り出し・照合・検算の道具は `veg-table-to-csv` のものを使います．

<a id="jstage-xml"></a>

### jstage-xml (J-STAGE の全文 XML)

学会誌の論文 PDF (原稿の無い過去の号を含む) から，J-STAGE に登載する全文 XML (JATS 1.1，FULL-J) と登載用の zip を作るスキル `pdf-to-jstage-xml` です．
「この論文 PDF を J-STAGE の全文 XML にして」のように頼むと使われます．手順は [SKILL.md](plugins/jstage-xml/skills/pdf-to-jstage-xml/SKILL.md) にあります．

- 雑誌ごとの設定は `journals/<資料コード>.yaml` に置きます．ひな形 (`_template`) と，作例として植生学会誌 (`vegsci`) の設定と記録が入っています．
- 作業ディレクトリ・控え・記事識別子の対応表は，任意のフォルダ (作業の根) に置きます．環境変数 `JSTAGE_ROOT` で渡します (`from_backup.py` と `fix_ja_names.py` は `--root` でも渡せます)．
- 必要な道具は[必要な環境](#requirements)の表を見てください．スキャンの号は，PDF に入っている OCR の文字をそのまま使います．
- パスワード付きの PDF は，`--password <パスワード>` か環境変数 `PDF_PASSWORD` で渡すと開けます．
- 論文一覧の取得 (`scripts/list_articles.py`) と，登載前に見た目を確かめる手元のプレビュー (`scripts/preview_tool/`) も入っています．
- 控えの取り方と調査のまとめは，[support-ac](https://github.com/matutosi/support-ac) の `jstage/` を見てください．

<a id="graphical-abstract"></a>

### graphical-abstract (グラフィカルアブストラクト)

論文や書籍の内容を1枚の図にするスキル `graphical-abstract` です．
「この論文のグラフィカルアブストラクトを作って」「本の内容を1枚の絵にまとめて」のように頼むと使われます．手順は [SKILL.md](plugins/graphical-abstract/skills/graphical-abstract/SKILL.md) にあります．

- **筋は AI，絵は外部ツール，組むのと点検はスクリプト**に分けます．Claude Code は絵を描けないので，絵は画像生成ツール (ChatGPT・Gemini・Midjourney など) か手描きで作ります．
- 論文から問い・方法・結果・結論を取り出し，**誇張しない決まり** (関連を因果の矢印にしない・調べた範囲を超えて一般化しない・数値は転記元のページを控える) で 3-5 コマに縮めます．
- 配置は mm 単位の JSON (`layout.json`) で書き，`compose.py` が matplotlib で組みます．**文字のはみ出し・重なり・絵の上の文字・小さすぎる字・画像待ち・概略の値の注記漏れ**を機械的に点検し，PNG・PDF・SVG で書き出します．
- `make_prompts.py` が，絵の枠ごとに縦横比と大きさを合わせ，**同じ画風の指示文**をツールごとの形 (汎用・Midjourney・Stable Diffusion 系・YAML) で作ります．
- `pdf_pages.py` が，PDF を開けるか・文字の層があるか (スキャンか) を調べ，ページを画像にします．
- 型は「流れ」「対比」「中心と周り」「書籍 (読者の旅)」から選びます．

Compose a graphical abstract for a paper or a book: condense the story without overclaiming, lay it out in millimetres with matplotlib, check for overflowing or overlapping text, and hand the illustrations off to an external image generator with consistent prompts.

<a id="video-highlight"></a>

### video-highlight (動画を指定の長さに縮める)

2〜3分の動画から良い部分を選んで，60 秒・30 秒などの指定の長さに縮めるスキル `video-highlight` です．
「この動画を1分にまとめて」「30秒に縮めて」「良いところだけ切り出して」のように頼むと使われます．手順は [SKILL.md](plugins/video-highlight/skills/video-highlight/SKILL.md) にあります．

- **調べるのと切るのはスクリプト，どこを残すかは AI** に分けます．
- `analyze` が，ffmpeg で無音・場面の切り替え (スライドの切り替えも)・音量を調べ，faster-whisper で音声を書き起こして，区間の一覧 (`summary.md`) と縮小画像の一覧表 (コンタクトシート) を作ります．
- AI はそれを読んで筋道を決め，残す区間を `selection.json` に書きます．文の途中で切らない・言いよどみや脇道を落とす，などの選び方は SKILL.md にあります．
- `render` が区間を切り出してつなぎます．切り口は近くの無音へ寄せるので，言葉の頭や尻が切れにくくなっています．
- `check` が，できた動画を書き起こし直して，つなぎ目で言葉が切れていないかを確かめます．
- **処理はすべて手元で行い，動画を外部へ送りません** (初回だけ，書き起こしのモデルを Hugging Face から取ってきます)．GPU が無くても CPU で動きます (2分30秒の動画の書き起こしで約2分)．NVIDIA の GPU があれば，`pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"` で約10秒になります．
- 順番の入れ替え・字幕・BGM はしません．話していない動画では，縮小画像と音量・場面の切り替えだけで選ぶので，選ぶ精度が落ちます．

Cut a 2-3 minute video down to a target length (e.g. 60 or 30 seconds): ffmpeg and faster-whisper map the silences, scene changes and speech, the AI picks the segments that tell the story, and the script cuts them at nearby silences and joins them. Everything runs locally.

<a id="examples"></a>

## サンプル / Examples

各プラグインの `examples/` に，手で試すためのサンプルと手順 (README) があります．
試すときは，フォルダを別の場所に写してから使ってください (原稿や写真を書き換えるため)．

| プラグイン | 場所 | 入っているもの |
|---|---|---|
| ja-manuscript | [examples/](plugins/ja-manuscript/examples/) | 誤りをわざと入れた2章の練習原稿と，リライトの草稿．朱書きの校正 PDF の例は [proof/](plugins/ja-manuscript/examples/proof/)，索引づくりの例 (架空の入門書 3 章と組んだ PDF) は [index/](plugins/ja-manuscript/examples/index/) |
| jpg-user-comment | [examples/](plugins/jpg-user-comment/examples/) | JPEG 2枚と，コメントを書いた CSV |
| vegetation-survey | [examples/](plugins/vegetation-survey/examples/) | 架空の植生調査票1枚の画像と，それを読み取った JSON，正解の CSV．架空の組成表の画像と転記表，正解の CSV は [table/](plugins/vegetation-survey/examples/table/) |
| graphical-abstract | [examples/](plugins/graphical-abstract/examples/) | 架空の論文 (流れ) と架空の書籍 (読者の旅) の配置の JSON と，Gemini で作った絵 |

`jstage-xml` には `examples/` がありません．雑誌の設定の作例として，植生学会誌の設定と記録 (`journals/vegsci.*`) が入っています．
`video-highlight` にも `examples/` はありません (お手元の動画で試してください)．

<a id="tests"></a>

## テスト / Tests

スクリプトのテストは，各スキルの `tests/` にあります．
次のコマンドで，すべてを順に走らせます．

```
python run_tests.py
```

テストに要る道具と，無いときの動きは次のとおりです．

| プラグイン・スキル | テストに要るもの | 無いとき |
|---|---|---|
| jstage-xml | `pymupdf` `pyyaml` | 一部を飛ばす |
| build-index | `pypdfium2` `pyyaml` | PDF を使う試験を飛ばす |
| apply-proof-marks | `pypdf` `Pillow` | (必須) |
| 〃 (画像の切り出しの試験) | `pypdfium2` | 飛ばす |
| 〃 (`--ref` の試験) | `opencv-python` | 飛ばす |
| vegetation-survey (`check_names.py` の xlsx を読む試験) | `openpyxl` | その試験だけ飛ばす |
| vegetation-survey (`veg-table-to-csv` の画像の試験) | `Pillow` `pymupdf` | 飛ばす |
| graphical-abstract | `matplotlib`．PDF の試験は `pymupdf` | 飛ばす |
| video-highlight | `numpy`．通しの試験は `ffmpeg` (書き起こしは試さないので `faster-whisper` は要らない) | 通しの試験を飛ばす |

GitHub では，push のたびに Ubuntu と Windows でテストを回します (`.github/workflows/test.yml`)．

<a id="license"></a>

## ライセンス / License

MIT License．[LICENSE](LICENSE) を見てください．
