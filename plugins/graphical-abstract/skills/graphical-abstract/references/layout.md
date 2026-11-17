# layout.json の書き方

座標はすべて mm，原点は左上．文字の大きさは pt (実寸)．
見本は `examples/paper/layout.json` と `examples/book/layout.json`．

## 全体

```json
{
  "title": "図の名前 (指示文の見出しに使う)",
  "canvas": {"width_mm": 330, "height_mm": 132, "dpi": 300, "min_font_pt": 7,
             "background": "#ffffff", "font": "auto", "text_color": "#333333"},
  "palette": {"keep": "#1b7a3a", "stop": "#b35900"},
  "style": {"description": "clean flat vector illustration ...", "palette": ["#1b7a3a"],
            "background": "plain white background", "avoid": "text, letters, ..."},
  "elements": [ ... ]
}
```

- `font` が `auto` なら，日本語の書体を BIZ UDPGothic → Yu Gothic → Meiryo → Hiragino → Noto Sans CJK JP → IPAex の順に探す．名前を書けばその書体．
- `palette` の名前は，要素の色 (`fill`・`color` など) に書ける．
- `style` は make_prompts.py が全部の絵の指示文に足す画風．

## 要素

すべての要素に `type` と `id` (省略すると自動で付く)．`parent` に枠 (panel・box) の id を書くと，その枠からのはみ出しを点検する．

| type | 要る項目 | 主な任意の項目 |
|---|---|---|
| `panel` | x, y, w, h | `title`・`title_size` (12)・`fill`・`edge`・`radius` |
| `box` | x, y, w, h | `text`・`size` (10)・`fill`・`color` (文字．既定は白)・`wrap` |
| `text` | x, y, text | `size` (10)・`weight`・`ha` (left/center/right)・`va` (top/center/bottom)・`color`・`wrap_mm`・`rotation`・`over` |
| `image` | x, y, w, h | `src` (絵の置き場．layout.json からの相対)・`prompt` (描くもの．英語)・`note` (日本語の補足)・`knockout_white` (白に近い背景と，縁と同じうすい色を透明に．既定 true．数ならしきい値)・`trim_white` (周りの余白を切り落とす．既定 true)・`halign`/`valign` (枠の中で寄せる向き．left/center/right，top/center/bottom)・`ref` (外部ツールに添える参照画像．同じ場面・人物にそろえる) |
| `arrow` | from [x, y], to [x, y] | `color`・`linewidth` (2) |
| `line` | from, to | `color`・`linewidth`・`linestyle` |
| `chart` | x, y, w, h, kind, data | 下の表 |

- `text` の `x`, `y` は `ha`・`va` で決まる点 (既定は左上)．
- `box` の文字は，`\n` を含まなければ枠の幅で自動に折り返す．含めば手の改行のまま．
- `image` は余白を切り落とし，縦横比を保って枠に収め，中央 (か `halign`・`valign` の向き) に置く．`src` が無いか，ファイルが無ければ点線の枠を描く．
- 大きさの違いを見せたいとき (草丈 30 cm と 150 cm など) は，枠の高さを変えて `"valign": "bottom"` で下端 (地面) をそろえる．
- 同じ絵を 2 か所で使うときは，2 つ目の `image` に `prompt` を書かず，同じ `src` を書く．

## グラフ (chart)

| 項目 | 意味 |
|---|---|
| `kind` | `scatter`・`bar`・`line` |
| `data` | `{"x": [...], "y": [...], "group": [...]}`．`group` は色分け (省略可) |
| `colors` | `{"群の名前": "色"}` |
| `xlabel`・`ylabel`・`xticks`・`yticks`・`xlim`・`ylim` | 軸 |
| `size` | 目盛の字の大きさ (8)．軸名は +1 |
| `margins_mm` | 枠の内側に取る余白 [左, 右, 上, 下] (既定 [12, 3, 3, 10])．目盛と軸名がはみ出すなら広げる |
| `legend` | true で凡例 |
| `bar_labels` | 棒の上に値を書く (既定 true) |
| `approx`・`approx_note` | 値が概略 (原図からの読み取り) のとき．注記はグラフの右上に出る |

## 点検の許し

- 文字を絵の上に載せたいとき (絵の上の見出しなど) は `"over": true`．
- 絵がまだ無いうちは `--allow-missing-images` で終了コードを 0 にできる．
