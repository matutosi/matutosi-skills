# jpg-user-comment のサンプル

`photos/` の JPEG 2枚と，そのコメントを書いた `comments.csv` です．
**写真を書き換えるので，このフォルダを別の場所に写してから試してください．**

## Claude Code で試す

写したフォルダで，次のように頼んでください．

1. 「`comments.csv` のコメントを写真に書き込んで」
2. 「`photos/` の写真のコメントを CSV に書き出して」

2 で書き出した CSV に，1 で書き込んだコメント (`ススキ 穂` と `空, 雲`) が出ていれば成功です．

## スクリプトで直接試す

`S` はスキルの `scripts/jpg_comment.py` を指します．

```bash
python "$S" import comments.csv -n                   # 書き込む内容の確認だけ
python "$S" import comments.csv                      # 書き込む
python "$S" export photos --basename -o out.csv      # 書き出す (UTF-8，BOM 付き)
```

`comments.csv` の `filename` は，CSV のあるフォルダからの相対パスで書いてあります．
コメントにカンマを含むときは，`"空, 雲"` のように二重引用符で囲みます．
