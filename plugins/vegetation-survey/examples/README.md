# 例

`sample.json` は，架空の調査票 1 枚を読み取ったあとの JSON です (実在の調査ではありません)．
これを CSV にして，出力の形を確かめられます．

```bash
S=skills/veg-sheet-to-csv/scripts/build_csv.py

# 1 ファイル (既定: 半角カナ・空欄・cp932)
python $S examples/sample.json -o out/sample

# 2 ファイル (地点と組成を分ける)・全角カナ・NA・UTF-8
python $S examples/sample.json -o out/sample --layout two --kana full --missing na --encoding utf-8-sig
```

JSON の書き方:

- `site` に地点の項目，`species` に種の行を入れる．列名は CSV の列名そのまま．
- 種の被度と群度は `被度・群度` に `"3,4"` や `"+"` と書くと分かれる．
- `site.出現種数` は CSV の列にならず，種名の数との照合に使う．
- 複数の調査票は `{"sheets": [{"site": ..., "species": [...]}, ...]}`．

## 試す (入力 → 読み取り → 出力)

| ファイル | 中身 |
|---|---|
| `sample_sheet.png` | **入力の例**．架空の植生調査票 (手書き風の画像)．スキルにこの画像を読ませる |
| `sample.json` | **読み取りの正解**．画像を読んだ結果がこれと一致すればよい |
| `expected_single.csv` | **出力の例**．`sample.json` から作った既定の CSV (1ファイル・半角カナ・空欄・cp932．テストが1バイトまで照合する) |
| `make_sample_sheet.py` | `sample.json` から `sample_sheet.png` を作り直す (Pillow と日本語フォントが要る) |

試し方: Claude Code に「`examples/sample_sheet.png` を植生調査票として CSV にして」と頼み，出てきた CSV を `expected_single.csv` と比べる．
通常の実行と同じく，**先に選択肢の表が示される** (出力の形・カナ・空欄／`NA`・文字コードなど)．「既定で」と返せば，見本と同じ形になる．
種名の照合 (`check_names.py`) を試すときは，`sample.json` の種名に `コジイ` (異名．標準和名はツブラジイ) が入っている．

**スキルを実行して比べるときの注意**: スキルは既定で種名を照合し (`check_names.py --fill latin,family`)，空の科名を補う．
そのため，出てきた CSV と `expected_single.csv` の差は**科名の列だけ** (`expected_single.csv` は照合していないので科名が空)．学名と，その他の列は一致する (2026-10 に確かめた)．
