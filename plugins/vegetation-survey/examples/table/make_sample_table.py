#!/usr/bin/env python3
"""transcripts/ の架空の組成表から，本文に挟まれた小さい表の紙面 sample_table.png を作る.

    python make_sample_table.py [--font FONT.ttc]

Pillow と日本語フォントが要る．転記表 (正解) と画像が食い違わないよう，表の中身は転記表から読む．
"""

import argparse
import csv
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TAB = os.path.join(HERE, "transcripts", "Tab.1")
FONTS = ["C:/Windows/Fonts/msgothic.ttc", "C:/Windows/Fonts/meiryo.ttc",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
TEXT = ["架空の海岸に見られる低木群落について述べる．この文章は見本であり，実在の調査とは関係がない．",
        "群落は砂丘の内陸側に成立し，風当たりの強い地点では丈が低くなる (Tab. 1)．"]
PLOTS = ["1", "2", "3"]


def read(name):
    with open(os.path.join(TAB, name), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--font")
    a = ap.parse_args()
    path = a.font or next((p for p in FONTS if os.path.exists(p)), None)
    if not path:
        sys.exit("日本語フォントが見つからない．--font で指定する")
    f, small = ImageFont.truetype(path, 26), ImageFont.truetype(path, 22)
    im = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(im)

    y = 90
    d.text((110, y), "12. 架空の海岸の低木群落", fill="black", font=f)
    y += 70
    for line in TEXT * 4:
        d.text((110, y), line[:40], fill="black", font=small)
        y += 38
    y += 40
    meta = {r["key"]: r["value"] for r in read("meta.tsv")}
    d.text((110, y), "Tab. 1.  " + meta["title_ja"], fill="black", font=small)
    y += 34
    d.text((110, y), "Vitex rotundifolia-Elaeagnus umbellata-Gesellschaft", fill="black", font=small)
    y += 50
    x_ja, x_val = 110, 640
    for r in read("header.tsv"):
        d.text((x_ja, y), r["item_ja"], fill="black", font=small)
        for i, p in enumerate(PLOTS):
            d.text((x_val + i * 130, y), r[p], fill="black", font=small)
        y += 34
    d.line([(110, y), (1130, y)], fill="black")
    y += 12
    for r in read("body.tsv"):
        if r["kind"] == "group":
            d.text((x_ja, y), r["group_ja"], fill="black", font=small)
        else:
            d.text((x_ja, y), r["s_name"], fill="black", font=small)
            d.text((x_ja + 340, y), r["j_name"], fill="black", font=small)
            for i, p in enumerate(PLOTS):
                d.text((x_val + i * 130, y), r[p], fill="black", font=small)
        y += 34
    y += 20
    d.text((110, y), "出現1回の種 Außerdem je einmal in Lfd. Nr.", fill="black", font=small)
    y += 34
    for r in read("once.tsv"):
        d.text((110, y), "%s: %s  %s  %s" % (r["plot"], r["s_name"], r["j_name"], r["value"]), fill="black", font=small)
        y += 34
    y += 6
    for r in read("notes.tsv"):
        d.text((110, y), r["value_raw"], fill="black", font=small)
        y += 34
    y += 40
    for line in TEXT * 3:
        d.text((110, y), line[:40], fill="black", font=small)
        y += 38
    im.save(os.path.join(HERE, "sample_table.png"))


if __name__ == "__main__":
    main()
