#!/usr/bin/env python3
"""配置の JSON (layout.json) から，外部の画像生成ツールに渡す指示文を作る.

    python make_prompts.py layout.json --out prompts.md

Claude Code は絵 (イラスト) を描けないので，絵は外部ツールで作る．
`image` 要素の `prompt` (描くものを英語で) と，最上位の `style` (全部の絵で共通の画風) から，
ツールごとの形 (汎用・Midjourney・Stable Diffusion 系・YAML で受けるツール) の指示文を書く．
できた画像を `src` の場所に置き，compose.py で組み直す．

style の例:
  "style": {
    "description": "flat vector illustration, simple shapes, soft colors, scientific",
    "palette": ["#1b7a3a", "#b35900", "#f5f5f2"],
    "background": "plain white background",
    "avoid": "text, letters, numbers, labels, watermark, signature, frame"
  }
"""

import argparse
import json
import math
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from compose import LayoutError, MM_PER_INCH, load_layout  # noqa: E402

COMMON_RATIOS = [(1, 1), (5, 4), (4, 3), (3, 2), (16, 9), (2, 1), (21, 9),
                 (4, 5), (3, 4), (2, 3), (9, 16), (1, 2)]

DEFAULT_STYLE = {
    "description": "clean flat vector illustration, simple shapes, scientific style, consistent line weight",
    "palette": [],
    "background": "plain white background, isolated subject",
    "avoid": "text, letters, numbers, labels, captions, watermark, signature, frame, border",
}


def nearest_ratio(w, h):
    """w:h に最も近いよくある縦横比を "16:9" の形で返す."""
    r = w / h
    best = min(COMMON_RATIOS, key=lambda p: abs(math.log(r) - math.log(p[0] / p[1])))
    return "%d:%d" % best


def slot_pixels(el, dpi, scale=2.0):
    """枠の実寸 (mm) と dpi から，作ってほしい画像の大きさ (px) を返す．縮めて使うので scale 倍にする."""
    w = int(round(el["w"] / MM_PER_INCH * dpi * scale))
    h = int(round(el["h"] / MM_PER_INCH * dpi * scale))
    return w, h


def build_prompt(subject, style):
    st = dict(DEFAULT_STYLE)
    st.update({k: v for k, v in (style or {}).items() if v})
    parts = [subject.strip().rstrip("."), st["description"], st["background"]]
    if st.get("palette"):
        parts.append("color palette limited to " + ", ".join(st["palette"]))
    parts.append("no text of any kind")
    positive = ", ".join(p for p in parts if p)
    return positive, st["avoid"]


def collect(layout):
    slots = []
    dpi = layout["canvas"]["dpi"]
    for el in layout["elements"]:
        if el["type"] != "image":
            continue
        if not el.get("prompt"):
            slots.append({"id": el["id"], "src": el.get("src_given", el.get("src", "")),
                          "note": el.get("note", ""), "skip": True})
            continue
        positive, negative = build_prompt(el["prompt"], layout.get("style"))
        w, h = slot_pixels(el, dpi)
        slots.append({
            "id": el["id"],
            "src": el.get("src_given", el.get("src", "")),
            "subject": el["prompt"],
            "note": el.get("note", ""),
            "ref": el.get("ref", ""),
            "ratio": nearest_ratio(el["w"], el["h"]),
            "pixels": [w, h],
            "prompt": positive,
            "negative": negative,
            "skip": False,
        })
    return slots


def render_markdown(slots, title=""):
    lines = ["# イラストの指示文%s" % ((" (%s)" % title) if title else ""), ""]
    lines.append("Claude Code は絵を描けないので，以下の指示文を外部の画像生成ツールに渡して作る．")
    lines.append("できた画像は各節の「置き場」に置き，`compose.py` で組み直す．")
    lines.append("")
    lines.append("- どの絵も**同じツール・同じ画風の指定**で作ると，並べたときにそろう．")
    lines.append("- 絵の中の文字は図の側 (compose.py) で入れる．ツールが字を描いたら作り直すか，その部分を消す．")
    lines.append("- 背景は白か透明にする．透明 (PNG) にできるツールなら透明が扱いやすい．")
    lines.append("- 使ったツール・モデル・日付を記録しておく (投稿規定で生成 AI の利用の明記を求める雑誌がある)．")
    lines.append("")
    for s in slots:
        lines.append("## %s" % s["id"])
        lines.append("")
        if s["skip"]:
            lines.append("`prompt` が無いので指示文は作らない (ほかの枠の絵の使い回し・手描き・写真・既存の図)．置き場: `%s`" % s["src"])
            if s.get("note"):
                lines.append("")
                lines.append("- 補足: %s" % s["note"])
            lines.append("")
            continue
        lines.append("- 描くもの: %s" % s["subject"])
        if s["note"]:
            lines.append("- 補足: %s" % s["note"])
        lines.append("- 置き場: `%s`" % s["src"])
        if s.get("ref"):
            lines.append("- 参照画像: `%s` (この絵を先に作り，ツールに添えて渡す．同じ場面・人物・画風にそろう)" % s["ref"])
        lines.append("- 縦横比: %s (目安の大きさ %d × %d px 以上)" % (s["ratio"], s["pixels"][0], s["pixels"][1]))
        lines.append("")
        lines.append("汎用 (ChatGPT・Gemini・Copilot など，文章で頼むツール):")
        lines.append("")
        lines.append("```text")
        lines.append("%s. Aspect ratio %s. Avoid: %s." % (s["prompt"], s["ratio"], s["negative"]))
        lines.append("```")
        lines.append("")
        lines.append("Midjourney:")
        lines.append("")
        lines.append("```text")
        lines.append("%s --ar %s --no %s" % (s["prompt"], s["ratio"], s["negative"].replace(", ", ", ")))
        lines.append("```")
        lines.append("")
        lines.append("Stable Diffusion 系 (正と負の指示文を分けるツール):")
        lines.append("")
        lines.append("```text")
        lines.append("Positive: %s" % s["prompt"])
        lines.append("Negative: %s" % s["negative"])
        lines.append("```")
        lines.append("")
        lines.append("YAML で指示を受けるツール (Gemini などの API を呼ぶ自作のスクリプト):")
        lines.append("")
        lines.append("```yaml")
        lines.append("image:")
        lines.append("  mode: illustration")
        lines.append("  title: \"%s\"" % s["id"])
        lines.append("  description: \"%s\"" % s["prompt"].replace("\"", "'"))
        lines.append("  academic_style: false   # 画風は description に書いた．ツールの既定の画風 (白黒の線画など) を足さない")
        lines.append("  color_mode: color")
        lines.append("  aspect_ratio: \"%s\"" % s["ratio"])
        lines.append("  resolution: %d" % _resolution(max(s["pixels"])))
        if s.get("ref"):
            lines.append("  reference_image: \"%s\"" % s["ref"].replace("\\", "/"))
        lines.append("output:")
        lines.append("  path: \"%s\"" % s["src"].replace("\\", "/"))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _resolution(px):
    for r in (512, 1024, 2048, 4096):
        if px <= r:
            return r
    return 4096


def main(argv=None):
    ap = argparse.ArgumentParser(description="外部の画像生成ツールに渡すイラストの指示文を作る")
    ap.add_argument("layout", help="配置の JSON (layout.json)")
    ap.add_argument("--out", help="書き出す Markdown (既定は標準出力)")
    ap.add_argument("--json", help="指示文を JSON でも書き出す")
    args = ap.parse_args(argv)
    try:
        layout = load_layout(args.layout)
    except (LayoutError, json.JSONDecodeError) as e:
        print("配置の誤り: %s" % e, file=sys.stderr)
        return 2
    slots = collect(layout)
    md = render_markdown(slots, layout.get("title", ""))
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(md + "\n")
        print("書いた: %s (絵 %d 枚)" % (args.out, sum(1 for s in slots if not s["skip"])))
    else:
        print(md)
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(slots, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
