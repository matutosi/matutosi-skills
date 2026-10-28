#!/usr/bin/env python3
"""架空の植生調査票の画像 (sample_sheet.png) を sample.json から作る.

    python make_sample_sheet.py [--font FONT.ttc]

スキルを試すための入力例．実在の調査ではない．
sample.json が「読み取りの正解」で，この画像を読んだ結果がそれと一致すればよい．
手書きらしく，文字ごとに位置と傾きを少し揺らす (乱数は固定)．Pillow が要る．
"""

import argparse
import json
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = [
    "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/msgothic.ttc", "C:/Windows/Fonts/meiryo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
]
LAYER_NAMES = {"T1": "高木層", "T2": "亜高木層", "S1": "低木層", "S2": "第2低木層", "H1": "草本層", "H2": "第2草本層"}


def load_font(path, size):
    for p in ([path] if path else []) + FONTS:
        if p and os.path.exists(p):
            return ImageFont.truetype(p, size)
    sys.exit("日本語フォントが見つからない: --font で指定する")


def jitter_text(img, xy, text, font, rng, fill=(20, 20, 60)):
    """1文字ずつ位置と傾きを揺らして描く."""
    x, y = xy
    for ch in text:
        w = int(font.getlength(ch)) + 2
        tile = Image.new("RGBA", (w + 20, font.size + 20), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((10, 6), ch, font=font, fill=fill + (255,))
        tile = tile.rotate(rng.uniform(-4, 4), resample=Image.BICUBIC)
        img.alpha_composite(tile, (int(x - 10 + rng.uniform(-1, 1)), int(y - 6 + rng.uniform(-2, 2))))
        x += w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "sample_sheet.png"))
    a = ap.parse_args()

    with open(os.path.join(HERE, "sample.json"), encoding="utf-8") as f:
        d = json.load(f)
    site, species = d["site"], d["species"]
    rng = random.Random(1)
    W, H = 1240, 730
    img = Image.new("RGBA", (W, H), (252, 250, 244, 255))
    dr = ImageDraw.Draw(img)
    big, mid, small = load_font(a.font, 34), load_font(a.font, 26), load_font(a.font, 22)
    line = (90, 90, 90)

    dr.text((40, 24), "植 生 調 査 票", font=big, fill=(40, 40, 40))
    # ヘッダ (印刷の見出し + 手書きの値)
    y = 90
    heads = [
        ("調査年月日", "%s年%s月%s日" % (site["調査年月日"][:4], int(site["調査年月日"][4:6]), int(site["調査年月日"][6:]))),
        ("調査者", site["調査者名"]),
        ("場所", site["都道府県"] + site["市郡町村区名"] + site["以下"]),
        ("地形・方位", "%s  %s  傾斜 %s°  標高 %s m" % (site["地形条件"], site["斜面方位"], site["傾斜角度"], site["標高"])),
        ("面積", "%s × %s m" % (site["面積1"], site["面積2"])),
        ("群落名", site["群落名"]),
    ]
    for k, v in heads:
        dr.text((40, y), k, font=small, fill=(60, 60, 60))
        jitter_text(img, (220, y - 4), v, mid, rng)
        dr.line((210, y + 32, W - 40, y + 32), fill=line, width=1)
        y += 48

    # 階層の表
    y += 10
    cols = [40, 300, 640, 760, 880]  # 階層 / 種名 / 被度 / 群度
    dr.rectangle((40, y, W - 40, y + 40), outline=line, width=2)
    for x, t in zip(cols, ["階層 (高さ・植被率)", "種 名", "被度", "群度"]):
        dr.text((x + 8, y + 8), t, font=small, fill=(60, 60, 60))
    y += 40
    heights = {"T1": ("高木層", site.get("高木層階層高"), site.get("高木層植被率")),
               "H1": ("草本層", site.get("第1草本層階層高"), site.get("第1草本層植被率"))}
    prev = None
    for sp in species:
        lay = sp["階層"]
        cover = str(sp.get("被度・群度", ""))
        parts = [p for p in cover.replace("，", ",").split(",") if p]
        c, g = (parts + ["", ""])[:2]
        row_h = 52
        dr.rectangle((40, y, W - 40, y + row_h), outline=line, width=1)
        for x in cols[1:]:
            dr.line((x, y, x, y + row_h), fill=line, width=1)
        if lay != prev:
            nm, hgt, cov = heights.get(lay, (LAYER_NAMES.get(lay, lay), None, None))
            label = "%s %sm %s%%" % (nm, hgt, cov) if hgt else nm
            jitter_text(img, (cols[0] + 8, y + 10), label, small, rng)
            prev = lay
        jitter_text(img, (cols[1] + 10, y + 8), sp["種名"], mid, rng)
        jitter_text(img, (cols[2] + 20, y + 8), c, mid, rng)
        jitter_text(img, (cols[3] + 20, y + 8), g, mid, rng)
        y += row_h
    jitter_text(img, (40, y + 24), "出現種数 %s" % site["出現種数"], mid, rng)
    img.convert("RGB").save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
