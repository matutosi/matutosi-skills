# graphical-abstract の見本

どちらも架空の内容です．絵 (`illust/`) は Gemini の画像モデルで作りました．

| フォルダ | 型 | 中身 |
|---|---|---|
| `paper/` | 流れ (4 コマ) | 草刈りをやめた草地の種数 (架空の研究)．散布図と絵 2 枚 |
| `book/` | 書籍 (読者の旅) | 書籍の企画書の書き方 (架空の本)．箇条の箱と絵 2 枚 |

試し方 (スキルのフォルダから):

```bash
python scripts/compose.py ../../examples/paper/layout.json --out ga_paper
python scripts/make_prompts.py ../../examples/paper/layout.json --out prompts.md
```

`illust/` の絵を消すと，点線の枠と「画像待ち」が描かれます．
