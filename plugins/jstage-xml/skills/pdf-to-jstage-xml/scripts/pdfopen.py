"""PDF を開く (パスワード付きにも対応する)．

パスワードは，各スクリプトの `--password` か，環境変数 `PDF_PASSWORD` で渡す
(履歴に残したくなければ環境変数のほうがよい)．
`--password` を受けたスクリプトは apply(args) で環境変数に写すので，
そのスクリプトが呼ぶ別のスクリプト・関数 (layout.detect など) も同じパスワードで開ける．
"""
import os
import sys

import pymupdf


def add_arg(ap):
    ap.add_argument("--password", help="パスワード付き PDF のパスワード (環境変数 PDF_PASSWORD でも渡せる)")


def apply(args):
    """--password が渡されたら環境変数に写す (以後の open_pdf が使う)．"""
    if getattr(args, "password", None) is not None:
        os.environ["PDF_PASSWORD"] = args.password


def open_pdf(path):
    """pymupdf.open の代わり．パスワード付きなら PDF_PASSWORD で復号し，無い・違うときは分かるメッセージで止める．"""
    doc = pymupdf.open(path)
    if doc.needs_pass:
        pw = os.environ.get("PDF_PASSWORD")
        if not pw:
            sys.exit(f"パスワード付きの PDF です: {path}\n--password か環境変数 PDF_PASSWORD で渡す")
        if not doc.authenticate(pw):
            sys.exit(f"PDF のパスワードが違います: {path}")
    return doc
