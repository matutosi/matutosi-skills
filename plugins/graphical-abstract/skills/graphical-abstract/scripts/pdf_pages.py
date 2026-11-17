#!/usr/bin/env python3
"""論文・原稿の PDF を読める形にする (最初に必ず通す).

    python pdf_pages.py paper.pdf --out pages            # 調べて，ページを PNG にし，文字を書き出す
    python pdf_pages.py paper.pdf --info                 # 調べるだけ
    python pdf_pages.py paper.pdf --out pages --pages 2-5 --dpi 200

調べること (JSON で標準出力に出す):
  - 開くのにパスワードが要るか (needs_password)．要るなら止める (解除はしない)
  - 所有者パスワード (印刷・複写の制限) の印があるか (owner_restricted)．
    Claude Code の Read ツールは，この印が無い PDF でも開けないことがある．ページを画像にすれば読める
  - ページごとの文字の数．ほぼ 0 ならスキャン (scanned: true) で，画像から読む

書き出すもの (--out のとき):
  - <out>/p01.png … ページの画像 (Read ツールで1枚ずつ読む)
  - <out>/text.txt  文字の層があるときだけ．ページの区切りに "=== p01 ===" を入れる

要るもの: PyMuPDF (pymupdf)．
"""

import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_pages(spec, n):
    """"2-5,7" を 0 始まりの番号の並びにする．None なら全部."""
    if not spec:
        return list(range(n))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a else 1
            b = int(b) if b else n
            out.extend(range(a - 1, min(b, n)))
        else:
            out.append(int(part) - 1)
    return [p for p in out if 0 <= p < n]


def inspect(path):
    import pymupdf
    doc = pymupdf.open(path)
    info = {
        "file": os.path.basename(path),
        "pages": doc.page_count,
        "needs_password": bool(doc.needs_pass),
        "owner_restricted": False,
        "text_chars": [],
        "scanned": None,
    }
    if doc.needs_pass:
        doc.close()
        return info, None
    # 開けたが暗号化の辞書がある = 所有者パスワード (制限) だけ
    try:
        trailer_encrypt = doc.xref_get_key(-1, "Encrypt")
        info["owner_restricted"] = trailer_encrypt[0] != "null"
    except Exception:
        info["owner_restricted"] = bool(doc.metadata.get("encryption"))
    for page in doc:
        info["text_chars"].append(len(page.get_text().strip()))
    body = info["text_chars"][1:] or info["text_chars"]
    info["scanned"] = (sum(body) / max(len(body), 1)) < 50
    return info, doc


def main(argv=None):
    ap = argparse.ArgumentParser(description="PDF を調べ，ページを画像にし，文字を書き出す")
    ap.add_argument("pdf")
    ap.add_argument("--out", help="ページの画像と text.txt の置き場")
    ap.add_argument("--info", action="store_true", help="調べるだけ")
    ap.add_argument("--pages", help="ページの範囲 (1 始まり)．例: 2-5,7")
    ap.add_argument("--dpi", type=int, default=150, help="画像の解像度 (既定 150．小さい字の表は 200)")
    args = ap.parse_args(argv)
    try:
        info, doc = inspect(args.pdf)
    except ImportError:
        print("PyMuPDF が要る: pip install pymupdf", file=sys.stderr)
        return 2
    except Exception as e:  # 壊れた PDF など
        print("PDF を開けない: %s" % e, file=sys.stderr)
        return 2
    if info["needs_password"]:
        info["advice"] = "開くのにパスワードが要る．ユーザにパスワードの無い版を頼む (解除はしない)"
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 3
    if info["scanned"]:
        info["advice"] = "文字の層がほぼ無い (スキャン)．ページの画像を Read で読む"
    else:
        info["advice"] = "text.txt で本文を読み，図表はページの画像で確かめる"
    # Read ツールは，暗号化の辞書が無い PDF でも「password-protected」と断ることがある．
    # そのときも PDF 本体ではなく，ページの画像と text.txt を読めばよい
    info["advice"] += "．Read が PDF を断っても，ページの画像と text.txt は読める"
    if args.out and not args.info:
        os.makedirs(args.out, exist_ok=True)
        pages = parse_pages(args.pages, doc.page_count)
        written = []
        for i in pages:
            path = os.path.join(args.out, "p%02d.png" % (i + 1))
            doc[i].get_pixmap(dpi=args.dpi).save(path)
            written.append(path)
        info["images"] = written
        if not info["scanned"]:
            tpath = os.path.join(args.out, "text.txt")
            with open(tpath, "w", encoding="utf-8", newline="\n") as f:
                for i in pages:
                    f.write("=== p%02d ===\n" % (i + 1))
                    f.write(doc[i].get_text())
                    f.write("\n")
            info["text"] = tpath
    doc.close()
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
