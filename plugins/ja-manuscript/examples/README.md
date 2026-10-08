# ja-manuscript のサンプル

6つのスキルを手で試すための，短い練習原稿です．
**原稿を書き換えるので，このフォルダを別の場所に写してから試してください．**

| ファイル | 中身 |
|---|---|
| `chapter_01.md` | 第1章．誤り・表記ゆれ・整っていない表を**わざと**入れてある |
| `chapter_02.md` | 第2章．存在しない章への参照を1つ入れてある |
| `_rewrite/chapter_01.md` | 第1章のリライト (見出しから書き起こした草稿)．事実の誤りを1つ入れてある |
| `_polish/config.json` | `polish-loop` の照合で使う用語の組 (正，誤) |
| `fixes_example.json` | `polish-loop` の一括適用に渡す修正案の例 |
| `proof/chapter_01_proof.pdf` | `chapter_01.md` を組んで，手書きの注釈 (Ink) で朱書きを7つ入れた校正 PDF |
| `proof/expected_fixes.json` | 上の朱書きを反映したときの正解 (6件) |
| `proof/make_proof_pdf.py` | 校正 PDF を作り直すスクリプト (PyMuPDF と fontTools が要る) |

`chapter_01.md` に入れた誤りは次のとおりです．

| 種類 | 箇所 |
|---|---|
| 誤字 | 「誤時」 |
| 語の重複 | 「状況は調査者によって状況は」 |
| 冗長な表現 | 「検討を行う」「洗い出すことができます」 |
| 用語のゆれ | 「デンドログラム」と「樹形図」，「デフォルト」と「既定」 |
| 全角の括弧 | 「（0〜5 の外にある値）」 |
| 1行に複数の文 | 冒頭の段落 |
| 列幅のそろわない表 | 1.2 節の表 |

## スキルごとの試し方

写したフォルダで，Claude Code に次のように頼んでください．
`/ja-manuscript:<スキル名>` で直接呼ぶこともできます．

1. **sentence-per-line**: 「`chapter_01.md` を1文ごとに改行して」
   - 冒頭の段落が3行に分かれれば成功です．見出し・箇条書き・表は変わりません．
2. **markdown-table-pad**: 「`chapter_01.md` の表を整形して」
   - 1.2 節の表の縦棒がそろえば成功です．全角文字は幅2として数えます．
3. **manuscript-polish**: 「`chapter_01.md` と `chapter_02.md` を推敲して」
   - 上の表の誤りが問題点の一覧に挙がれば成功です．
     `chapter_02.md` の「第3章(\@ref(ch-name))」が参照切れとして挙がるかも見てください．
4. **polish-loop**: 「この原稿で推敲ループを1巡回して」
   - 照合のスクリプトだけを試すなら，`python <skills>/polish-loop/scripts/scan_recurring.py` を実行します．
     「次の3点」「検討を行う」「デンドログラム」「デフォルト」「（」が要確認として挙がります．
   - 修正案の一括適用は `python <skills>/polish-loop/scripts/apply_fixes.py fixes_example.json` で確認し，
     `--apply` を付けると書き換えます．3件とも当たり，当てる箇所ごとに前後の文脈が置換前・置換後で並びます．
     `fixes_example.json` に `{"file": "chapter_01.md", "before": "調査", "after": "踏査"}` のような短い行を足すと，
     一致が1回でなければ止まり，1回だけでも「短い」「語の途中で切れている」の警告が出ます．
5. **rewrite-improve**: 「`_rewrite` のリライトをもとに `chapter_01.md` を改善して」
   - リライトの冒頭の主題文が採り入れられ，**被度の範囲の誤り (0〜9) は採り入れられなければ**成功です
     (元原稿の 0〜5 が正しい)．
6. **apply-proof-marks**: 「`proof/chapter_01_proof.pdf` の朱書きを `chapter_01.md` に反映して」
   - 朱書きは次の7つです．6件が修正案の表に挙がり，7 が要判断として別に扱われれば成功です．

     | 朱書き | 意味 |
     |---|---|
     | 1. 「誤時」の「時」を消し，上に「字」 | 「誤字」に直す |
     | 2. 2つ目の「状況は」を消し，「トル」 | 削除 |
     | 3. 「すことができます」を消し，上に「します」 | 「洗い出します」に直す |
     | 4. 「重複」の後に挿入の印と「と欠番」 | 「重複と欠番」に直す |
     | 5. 括弧2つを丸で囲み，「半角」 | 全角の括弧を半角に |
     | 6. 「樹形図」を消し，上に「デンドログラム」 | 用語をそろえる |
     | 7. 表の右の余白に「縦長の例も？」 | **要判断** (勝手に直さない) |

   - 答え合わせは，`proof/expected_fixes.json` と，スキルが作った修正案を見比べます．
     正解をそのまま当てるなら `python <skills>/polish-loop/scripts/apply_fixes.py proof/expected_fixes.json` で確認し，`--apply` で書き換えます．
   - 朱書きを取り出す部分だけを試すなら，次を実行します．帯 (朱書きのかたまり) が4本出ます．

     ```bash
     python <skills>/apply-proof-marks/scripts/extract_marks.py proof/chapter_01_proof.pdf --list
     python <skills>/apply-proof-marks/scripts/extract_marks.py proof/chapter_01_proof.pdf --pages 1 --clean always --ink always
     ```

     `marks/` に，帯ごとの画像 (`p001_b1.png`)・朱書きを消した版 (`_clean`)・朱書きだけの版 (`_ink`) ができます．
     画像まで出すには `pypdfium2` が要ります (`pip install pypdfium2`)．
   - 手書きの文字は，フォントの字形の輪郭をなぞった筆跡なので，輪郭だけの太い字に見えます．
     自分の朱書きで試すなら，原稿を PDF にしてタブレットで手書きの注釈を入れてください．
