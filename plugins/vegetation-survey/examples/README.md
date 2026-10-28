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
