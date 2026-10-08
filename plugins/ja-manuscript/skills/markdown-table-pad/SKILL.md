---
name: markdown-table-pad
description: Markdownファイル内の表セルをパディングして列幅を揃えるスキル。「表を整形して」「テーブルを揃えて」「markdownの表をパディング(padding)」「表のカラム幅を統一」「md ファイルの表を綺麗にして」などと言ったときに必ず使う。ファイルを直接編集するか、テキストとして渡された表を整形して返す。日本語(全角文字)も正しく幅計算して揃える。
---

# Markdown Table Pad

## スクリプトの場所

```
${CLAUDE_SKILL_DIR}/scripts/pad_tables.py
```

## 使い方

### ファイルを直接整形（上書き）

```bash
python "${CLAUDE_SKILL_DIR}/scripts/pad_tables.py" path/to/file.md
```

複数ファイルも可:

```bash
python "${CLAUDE_SKILL_DIR}/scripts/pad_tables.py" file1.md file2.md
```

### 標準入力から整形

```bash
python "${CLAUDE_SKILL_DIR}/scripts/pad_tables.py" -
```

## 動作

- ファイル内のすべての Markdown 表を検出して列幅を揃える
- 日本語などの全角文字は幅2として計算し、ASCII と混在しても正しく整列する
- セパレータ行(`|:---|`)の `:` によるアライメント指定(`:-`, `-:`, `:-:`)を保持する
- 表以外の行(本文・見出し・コードブロック)は変更しない
- 変更があったファイルのみ書き換え、変更なしは `No change:` と報告する

## 手順

1. ユーザーが対象ファイルまたはテキストを指定する
2. ファイルパスが指定された場合は Bash でスクリプトを実行してファイルを直接更新する
3. テキストが貼り付けられた場合はスクリプトに標準入力で渡し、結果を返す
4. 処理結果(変更の有無)をユーザーに報告する
