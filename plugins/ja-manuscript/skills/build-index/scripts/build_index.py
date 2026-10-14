#!/usr/bin/env python3
"""terms.yaml とビルド済み PDF から索引 (Markdown) を組み立て，機械的に点検する.

- 見出し語をビルド済み PDF の本文から検索し，実際に載っているページ番号を得る．
- 辞書の規則 (清音 → 濁音 → 半濁音，長音符は直前の母音) で並べる．
- 主要なページ (terms.yaml の `主`) を太字にする．
- 循環参照・ページ数の偏り・分量・形式のそろいを点検する．

PDF の読み込みは pypdfium2，terms.yaml の読み込みは pyyaml (どちらも pip で入る)．
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- 並べ方
# 五十音の順 (主キーの比べ方に使う)．ゐ・ゑ は わ 行
GOJUON = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわゐゑをん"
RANK = {c: i for i, c in enumerate(GOJUON)}
ROWS = [
    ("あ", "あいうえお"), ("か", "かきくけこ"), ("さ", "さしすせそ"),
    ("た", "たちつてと"), ("な", "なにぬねの"), ("は", "はひふへほ"),
    ("ま", "まみむめも"), ("や", "やゆよ"), ("ら", "らりるれろ"),
    ("わ", "わゐゑをん"),
]
ROW_OF = {c: row for row, chars in ROWS for c in chars}
ROW_ORDER = [row for row, _ in ROWS] + ["英字"]
SMALL = dict(zip("ぁぃぅぇぉっゃゅょゎ", "あいうえおつやゆよわ"))
# 母音ごとの仮名 (長音符を直前の母音に置き換えるため)
VOWEL_OF = {}
for _vowel, _chars in zip("あいうえお", ["あかさたなはまやらわ", "いきしちにひみりゐ", "うくすつぬふむゆる",
                                         "えけせてねへめれゑ", "おこそとのほもよろを"]):
    for _c in _chars:
        VOWEL_OF[_c] = _vowel
VOWEL_OF["ん"] = "ん"
DAKUTEN, HANDAKUTEN = "゙", "゚"


def to_hira(s: str) -> str:
    """カタカナをひらがなにする (ヴ → ゔ，ヵ・ヶ → か・け)．"""
    out = []
    for ch in s:
        code = ord(ch)
        if ch == "ヵ":
            out.append("か")
        elif ch == "ヶ":
            out.append("け")
        elif 0x30A1 <= code <= 0x30F6:
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def kana_units(yomi: str):
    """よみを (基本の仮名，濁点の段階，長音符か，小書きか) の並びにする．

    - 濁点の段階: 0 清音，1 濁音，2 半濁音．
    - 長音符「ー」は，直前の仮名の母音として数える (長音符であることは覚えておく)．
    - 小書きの仮名 (っ・ゃ など) は，大きい仮名として数える (小書きであることは覚えておく)．
    - 空白と中黒は並べ方に関与しない．ここでは捨てる (中黒の有無は sort_key で別に見る)．
    """
    s = unicodedata.normalize("NFD", to_hira(yomi))
    units = []
    for ch in s:
        if ch in (DAKUTEN, HANDAKUTEN):
            if units:
                base, _, lng, sm = units[-1]
                units[-1] = (base, 1 if ch == DAKUTEN else 2, lng, sm)
            continue
        if ch in ("・", "･", " ", "　", "\t"):
            continue
        if ch in ("ー", "ｰ", "‐", "−"):
            if units:
                last = units[-1][0]
                units.append((VOWEL_OF.get(last, last), 0, True, False))
            continue
        small = ch in SMALL
        units.append((SMALL.get(ch, ch), 0, False, small))
    return units


def sort_key(yomi: str):
    """辞書の規則にそろえた並べ替えのキー．

    比べる順は次のとおり．
    1. 基本の仮名の並び (濁点・半濁点・小書き・長音符は無視．長音符は直前の母音に置き換える)．
    2. 清濁: 清音 → 濁音 → 半濁音 (左の文字から順に比べる)．
    3. 長音符: 同じ母音が並ぶ語どうしでは，長音符のある語が先．
    4. 小書き: 大きい仮名が先．
    5. 中黒・空白のある語は，無い語の後．
    英字などかなで始まらないよみは，かなの語の後に，大文字小文字を区別せずに並べる．
    """
    units = kana_units(yomi)
    if units and units[0][0] in RANK:
        primary = tuple(RANK.get(u[0], 1000 + ord(u[0])) for u in units)
        dakuten = tuple(u[1] for u in units)
        long_first = tuple(0 if u[2] else 1 for u in units)
        small = tuple(1 if u[3] else 0 for u in units)
        dots = 1 if re.search(r"[・･\s　]", yomi) else 0
        return (0, primary, dakuten, long_first, small, dots)
    text = unicodedata.normalize("NFKC", yomi).casefold()
    return (1, tuple(ord(c) for c in text), (), (), (), 0)


def row_of(yomi: str) -> str:
    units = kana_units(yomi)
    if units and units[0][0] in RANK:
        return ROW_OF[units[0][0]]
    return "英字"


# ---------------------------------------------------------------- ページ
def norm(text: str) -> str:
    """検索用に空白・改行を落として正規化する．"""
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", text)


def _toc_items(pdf):
    """(階層 0 始まり，題，ページ位置 0 始まり) の並びを返す (pypdfium2 の版の違いを吸収)．"""
    out = []
    for it in pdf.get_toc(max_depth=15):
        title = it.get_title() if hasattr(it, "get_title") else getattr(it, "title", "")
        idx = getattr(it, "page_index", None)
        if idx is None and hasattr(it, "get_dest"):
            dest = it.get_dest()
            idx = dest.get_index() if dest is not None else None
        if idx is None:
            continue
        out.append((int(it.level), str(title), int(idx)))
    return out


class Book:
    """ビルド済み PDF．ページ番号は紙面のノンブルで扱う．"""

    def __init__(self, path, offset: int | None = None):
        import pypdfium2 as pdfium
        self.pdf = pdfium.PdfDocument(str(path))
        self.text = []
        self.footer = []
        for page in self.pdf:
            tp = page.get_textpage()
            self.text.append(norm(tp.get_text_range()))
            w, _h = page.get_size()
            self.footer.append(tp.get_text_bounded(0, 0, w, 45))   # ページ下端 45pt
            tp.close()
            page.close()
        self.toc = _toc_items(self.pdf)
        if offset is None:
            offset = self._detect_offset()
        self.labels = [i + 1 + offset for i in range(len(self.text))]
        # 目次など本文より前のページは索引の対象にしない
        body = [p for _lv, _t, p in self.toc]
        self.skip = set(range(0, min(body))) if body else set()

    def exclude_section(self, title: str):
        """見出し (索引そのものなど) のページを対象から外す．"""
        starts = [(t, p) for lv, t, p in self.toc if lv == 0]
        for i, (t, start) in enumerate(starts):
            if title and title in t:
                end = starts[i + 1][1] - 1 if i + 1 < len(starts) else len(self.text) - 1
                self.skip |= set(range(start, end + 1))

    def _detect_offset(self) -> int:
        """ノンブル (紙面のページ番号) と PDF のページ位置のずれを多数決で決める．

        ページによってはノンブルが出ない (章扉など) ので，1ページずつ読むのではなく，
        全ページの (ノンブル - 位置) の最頻値をとる．
        """
        votes: dict[int, int] = {}
        for i, foot in enumerate(self.footer):
            for tok in foot.split():
                if tok.isdigit() and len(tok) <= 4:
                    d = int(tok) - (i + 1)
                    votes[d] = votes.get(d, 0) + 1
        if not votes:
            return 0
        best = max(votes, key=votes.get)
        agree = votes[best] / max(1, sum(votes.values()))
        if agree < 0.8:
            print(f"警告: ノンブルの読み取りが安定しません (一致率 {agree:.0%})．"
                  f"--offset で明示してください", file=sys.stderr)
        return best

    def chapter_ranges(self) -> dict[str, tuple[int, int]]:
        """`第N章` (または `Chapter N`) の見出しから 章 → (開始位置，終了位置) を作る．"""
        starts = []
        for level, title, page in self.toc:
            if level != 0:
                continue
            m = re.match(r"(?:第\s*(\d+)\s*章|Chapter\s+(\d+))", title, re.I)
            starts.append(((m.group(1) or m.group(2)) if m else title, page))
        ranges = {}
        for idx, (key, start) in enumerate(starts):
            end = starts[idx + 1][1] - 1 if idx + 1 < len(starts) else len(self.text) - 1
            ranges[str(key)] = (start, end)
        return ranges

    def section_of(self, pdf_idx: int) -> str:
        best = ""
        for _lv, title, page in self.toc:
            if page <= pdf_idx:
                best = title
            else:
                break
        return best

    def find(self, words: list[str], chapters: list | None) -> list[int]:
        allowed = None
        if chapters:
            ranges = self.chapter_ranges()
            allowed = set()
            for ch in chapters:
                rng = ranges.get(str(ch))
                if rng is None:
                    continue
                allowed |= set(range(rng[0], rng[1] + 1))
        keys = [norm(w) for w in words if w]
        hits = []
        for i, text in enumerate(self.text):
            if i in self.skip:
                continue
            if allowed is not None and i not in allowed:
                continue
            if any(k and k in text for k in keys):
                hits.append(self.labels[i])
        return sorted(set(hits))


def fmt_pages(pages: list[int], range_min: int = 2, main=()) -> str:
    """ページ番号を `12-14` の形にまとめる．

    主要ページ (main) は太字 `**13**` にする．主要ページを含む範囲は崩して書く:
    連続する 12, 13, 14 の 13 が主要なら `12, **13**, 14`．
    主要ページの前後がそれぞれ range_min 以上続くなら，そこは範囲のままにする
    (20-25 の 22 が主要なら `20-21, **22**, 23-25`)．
    """
    main = set(main)
    pages = sorted(set(pages))
    out, i = [], 0
    while i < len(pages):
        if pages[i] in main:
            out.append(f"**{pages[i]}**")
            i += 1
            continue
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1 and pages[j + 1] not in main:
            j += 1
        run = j - i + 1
        if run >= range_min:
            out.append(f"{pages[i]}-{pages[j]}")
        else:
            out.extend(str(p) for p in pages[i:j + 1])
        i = j + 1
    return ", ".join(out)


# ---------------------------------------------------------------- 読み込み・検索
def load_terms(path: Path) -> tuple[dict, list[dict]]:
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    meta = data.get("meta", {}) or {}
    entries = data.get("entries", []) or []
    return meta, entries


def _main_pages(e: dict) -> list[int]:
    v = e.get("主")
    if v is None:
        return []
    if isinstance(v, int):
        return [v]
    return [int(x) for x in v]


def resolve(entries: list[dict], book) -> list[dict]:
    """各見出しのページ (`_pages`) と主要ページ (`_main`) を決める．

    ページ = 検索で見つかった (または `ページ` で手指定した) ページ + `主` のページ．
    """
    def one(e: dict, inherited_chapters):
        main = _main_pages(e)
        manual = e.get("ページ")
        found = sorted(set(manual)) if manual else book.find(
            e.get("検索") or [e["見出し"]], e.get("章") or inherited_chapters)
        e["_pages"] = sorted(set(found) | set(main))
        e["_main"] = sorted(set(main))

    for e in entries:
        if e.get("参照"):
            e["_pages"], e["_main"] = [], []
            continue
        one(e, None)
        for sub in e.get("副", []) or []:
            one(sub, e.get("章"))
    return entries


# ---------------------------------------------------------------- 点検
def check(entries: list[dict], meta: dict, book, line_count: int) -> tuple[list, list]:
    errors, warns = [], []
    by_name = {e["見出し"]: e for e in entries}
    labels = list(book.labels)
    skip = getattr(book, "skip", set())
    body_labels = [lab for i, lab in enumerate(labels) if i not in skip] or labels
    lo_label, hi_label = (min(body_labels), max(body_labels)) if body_labels else (0, 0)

    if len(by_name) != len(entries):
        seen = set()
        for e in entries:
            if e["見出し"] in seen:
                errors.append(f"見出しが重複: {e['見出し']}")
            seen.add(e["見出し"])

    def check_pages(label: str, e: dict):
        for p in _main_pages(e):
            if not lo_label <= p <= hi_label:
                errors.append(f"主要ページが PDF の範囲 ({lo_label}-{hi_label}) の外: {label} の 主 {p}")
        for p in e.get("ページ") or []:
            if not lo_label <= p <= hi_label:
                warns.append(f"ページが PDF の範囲 ({lo_label}-{hi_label}) の外: {label} の ページ {p}")

    for e in entries:
        name = e["見出し"]
        yomi = e.get("よみ", "")
        if not yomi:
            errors.append(f"よみが無い: {name}")
        elif not re.fullmatch(r"[ぁ-ゖァ-ヺー・\sA-Za-z0-9]+", yomi):
            errors.append(f"よみはひらがな (英字は原綴) で書く: {name} → {yomi}")

        # 参照 (→) の循環・不在
        ref = e.get("参照")
        if ref:
            if ref == name:
                errors.append(f"自分自身への参照: {name}")
            elif ref not in by_name:
                errors.append(f"参照先が索引に無い: {name} → {ref}")
            elif by_name[ref].get("参照"):
                errors.append(f"参照が参照を指している (循環のもと): "
                              f"{name} → {ref} → {by_name[ref]['参照']}")
            if e.get("副") or e.get("ページ") or e.get("検索") or e.get("主"):
                warns.append(f"参照だけの見出しにページや副見出しがある (無視される): {name}")
            continue

        check_pages(name, e)
        for also in e.get("も見よ", []) or []:
            if also == name:
                errors.append(f"自分自身を「も見よ」に書いている: {name}")
            elif also not in by_name:
                errors.append(f"「も見よ」の先が索引に無い: {name} → {also}")
            elif by_name[also].get("参照"):
                warns.append(f"「も見よ」の先が参照見出し: {name} → {also}"
                             f" (実体の {by_name[also]['参照']} を指す)")

        if len(name) > 12:
            warns.append(f"見出し語が長い (短く言い切る): {name}")
        if re.match(r"^(大きな|小さな|新しい|様々な|多くの|重要な)", name):
            warns.append(f"修飾語で始まる見出し (名詞句にする): {name}")
        if not e.get("_pages") and not e.get("副"):
            warns.append(f"PDF に見つからない (表記ゆれか，参照専用にすべき): {name}")

        subs = e.get("副", []) or []
        if len(e.get("_pages", [])) >= 6 and not subs:
            warns.append(f"ページが {len(e['_pages'])} 箇所ある．副見出しに分ける: {name}")
        if subs:
            verbs = [bool(re.search(r"(する|る|た)$", s["見出し"])) for s in subs]
            if any(verbs) and not all(verbs):
                warns.append(f"副見出しの形式がそろっていない (名詞句と動詞句の混在): {name}")
            for s in subs:
                if not s.get("よみ"):
                    errors.append(f"副見出しのよみが無い: {name} > {s['見出し']}")
                check_pages(f"{name} > {s['見出し']}", s)
                if not s.get("_pages"):
                    warns.append(f"副見出しが PDF に見つからない: {name} > {s['見出し']}")

    # 分量 (本文ページ数の 2-3%)
    lines_per_page = meta.get("1ページの行数", 45)
    body_pages = meta.get("本文ページ数") or (max(body_labels) if body_labels else 1)
    est = line_count / lines_per_page
    lo, hi = body_pages * 0.02, body_pages * 0.03
    msg = (f"分量: 索引 {line_count} 行 ≒ {est:.1f} ページ "
           f"(本文 {body_pages} ページの目安 {lo:.1f}-{hi:.1f} ページ)")
    if est < lo:
        warns.append(msg + " → 少ない．見出し語を増やす")
    elif est > hi:
        warns.append(msg + " → 多い．副見出しへ寄せるか語を絞る")
    else:
        print(msg)
    return errors, warns


# ---------------------------------------------------------------- 書き出し
def render(entries: list[dict], title: str, range_min: int) -> tuple[str, int]:
    groups: dict[str, list] = {r: [] for r in ROW_ORDER}
    for e in entries:
        groups[row_of(e.get("よみ", ""))].append(e)

    out = [f"# {title} {{#index}}", ""]
    lines = 0
    for row in ROW_ORDER:
        items = sorted(groups[row], key=lambda e: sort_key(e.get("よみ", "")))
        if not items:
            continue
        out += [f"## {row}", ""]
        for e in items:
            if e.get("参照"):
                out.append(f"{e['見出し']} → {e['参照']}")
                lines += 1
                continue
            pages = fmt_pages(e.get("_pages", []), range_min, e.get("_main", []))
            also = e.get("も見よ") or []
            tail = f"  {'，'.join(also)} も見よ" if also else ""
            out.append(f"{e['見出し']}  {pages}{tail}".rstrip())
            lines += 1
            for s in sorted(e.get("副", []) or [], key=lambda s: sort_key(s.get("よみ", ""))):
                sp = fmt_pages(s.get("_pages", []), range_min, s.get("_main", []))
                out.append(f"    {s['見出し']}  {sp}".rstrip())
                lines += 1
        out.append("")
    return "\n".join(out) + "\n", lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="terms.yaml と PDF から索引を組み立てる")
    ap.add_argument("terms", help="見出し語の定義 (terms.yaml)")
    ap.add_argument("-p", "--pdf", help="ビルド済み PDF (既定は terms.yaml の meta.pdf．相対パスは terms.yaml のあるフォルダから)")
    ap.add_argument("-o", "--out", help="出力する索引 md (既定 chapter_98_index.md)")
    ap.add_argument("--title", default="索引", help="索引の見出し (既定 索引)")
    ap.add_argument("--offset", type=int, help="ノンブルを PDF ページ番号 + この値で決める")
    ap.add_argument("--range-min", type=int, default=2, help="連続ページを範囲にまとめる最小数")
    ap.add_argument("--check-only", action="store_true", help="点検だけして書き出さない")
    ap.add_argument("--report", action="store_true", help="語ごとのヒットページと節を表示する")
    args = ap.parse_args(argv)

    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        print("pypdfium2 が要ります: pip install pypdfium2", file=sys.stderr)
        return 2
    try:
        import yaml  # noqa: F401
    except ImportError:
        print("PyYAML が要ります: pip install pyyaml", file=sys.stderr)
        return 2

    terms_path = Path(args.terms)
    meta, entries = load_terms(terms_path)
    if args.pdf:
        pdf = Path(args.pdf)
    else:
        pdf = Path(meta.get("pdf", ""))
        if not pdf.is_absolute() and not pdf.exists():
            pdf = terms_path.resolve().parent / pdf
    if not pdf.is_file():
        print(f"PDF が見つかりません: {pdf}", file=sys.stderr)
        return 2
    book = Book(pdf, args.offset)
    book.exclude_section(args.title)  # 前の版の索引ページを拾わない
    entries = resolve(entries, book)

    text, line_count = render(entries, args.title, args.range_min)
    errors, warns = check(entries, meta, book, line_count)

    if args.report:
        label_to_idx = {}
        for i, lab in enumerate(book.labels):
            label_to_idx.setdefault(lab, i)
        for e in entries:
            if e.get("参照"):
                continue
            print(f"\n■ {e['見出し']}")
            for p in e["_pages"]:
                mark = " (主)" if p in e.get("_main", []) else ""
                print(f"  p.{p}{mark}  {book.section_of(label_to_idx.get(p, 0))}")

    for w in warns:
        print(f"警告: {w}")
    for er in errors:
        print(f"エラー: {er}", file=sys.stderr)
    if any("よみが無い" in er for er in errors):
        print("ヒント: よみの候補は suggest_yomi.py で出せます (pykakasi が要ります．確定は人が行う)．")

    if not args.check_only:
        out = Path(args.out or "chapter_98_index.md")
        out.write_text(text, encoding="utf-8")
        print(f"{out}: 見出し {len(entries)} 件 / {line_count} 行")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
