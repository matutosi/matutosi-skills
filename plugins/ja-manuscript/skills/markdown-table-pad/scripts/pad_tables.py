#!/usr/bin/env python3
"""Pad markdown table columns to align cells.

Usage:
  python pad_tables.py file.md          # in-place edit
  python pad_tables.py file1.md file2.md  # multiple files
  python pad_tables.py -                 # stdin -> stdout
  cat file.md | python pad_tables.py    # stdin -> stdout
"""

import re
import sys
import unicodedata


def str_width(s: str) -> int:
    """Calculate display width considering East Asian full-width characters."""
    width = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ('W', 'F'):
            width += 2
        else:
            width += 1
    return width


def ljust_width(s: str, width: int) -> str:
    """Left-justify string to display width (handles full-width chars)."""
    padding = max(0, width - str_width(s))
    return s + ' ' * padding


def is_table_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and stripped[0] == '|' and stripped[-1] == '|'


def split_cells(s: str) -> list:
    """`|` で列を切る．バックスラッシュでエスケープした `|` とコードスパンの中では切らない"""
    cells, cur, i, n = [], [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch == '\\' and i + 1 < n:
            cur.append(s[i:i + 2])
            i += 2
        elif ch == '`':
            j = i
            while j < n and s[j] == '`':
                j += 1
            run = s[i:j]
            k = s.find(run, j)
            while k != -1 and k + len(run) < n and s[k + len(run)] == '`':
                k = s.find(run, k + 1)   # 閉じが，より長い `` の一部なら探し直す
            if k == -1:
                cur.append(run)
                i = j
            else:
                cur.append(s[i:k + len(run)])
                i = k + len(run)
        elif ch == '|':
            cells.append(''.join(cur))
            cur = []
            i += 1
        else:
            cur.append(ch)
            i += 1
    cells.append(''.join(cur))
    return cells


def parse_row(line: str) -> list:
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|') and not line.endswith('\\|'):
        line = line[:-1]
    return [cell.strip() for cell in split_cells(line)]


def is_separator_row(cells: list) -> bool:
    filled = [cell.strip() for cell in cells if cell.strip()]
    if not filled:
        # 全セルが空の行(記入式の表の空欄)は区切り行ではない
        return False
    return all(re.match(r'^:?-+:?$', cell) for cell in filled)


def format_separator_cell(cell: str, width: int) -> str:
    cell = cell.strip()
    left = cell.startswith(':')
    right = cell.endswith(':')
    dashes = '-' * (width - (1 if left else 0) - (1 if right else 0))
    return (':' if left else '') + dashes + (':' if right else '')


def format_table(table_lines: list) -> list:
    rows = [parse_row(line) for line in table_lines]

    max_cols = max(len(row) for row in rows)
    for row in rows:
        while len(row) < max_cols:
            row.append('')

    col_widths = [3] * max_cols
    for row in rows:
        if is_separator_row(row):
            continue
        for j, cell in enumerate(row):
            col_widths[j] = max(col_widths[j], str_width(cell))

    result = []
    for row in rows:
        if is_separator_row(row):
            cells = [format_separator_cell(row[j], col_widths[j]) for j in range(max_cols)]
        else:
            cells = [ljust_width(row[j], col_widths[j]) for j in range(max_cols)]
        result.append('| ' + ' | '.join(cells) + ' |')
    return result


RE_FENCE = re.compile(r'^\s*(`{3,}|~{3,})')


def _split_cr(line: str):
    """行末の CR を分ける．(本体, CR か空文字)"""
    if line.endswith('\r'):
        return line[:-1], '\r'
    return line, ''


def pad_tables(content: str) -> str:
    """表だけを整形する．字下げと各行の改行コード (CRLF/LF) は保ち，コードブロックの中は触らない"""
    lines = content.split('\n')
    result = []
    fence = None   # 開いているコードブロックの囲み (``` や ~~~)
    i = 0
    while i < len(lines):
        raw = lines[i]
        core, _ = _split_cr(raw)
        m = RE_FENCE.match(core)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            result.append(raw)
            i += 1
        elif m:
            fence = m.group(1)
            result.append(raw)
            i += 1
        elif is_table_line(core):
            start = i
            while i < len(lines) and is_table_line(_split_cr(lines[i])[0]):
                i += 1
            block = [_split_cr(b) for b in lines[start:i]]
            cores = [b[0] for b in block]
            indent = cores[0][:len(cores[0]) - len(cores[0].lstrip())]
            for text, (_, cr) in zip(format_table(cores), block):
                result.append(indent + text + cr)
        else:
            result.append(raw)
            i += 1
    return '\n'.join(result)


def main():
    args = sys.argv[1:]

    if not args or args == ['-']:
        # Windows では標準入出力が既定で OS の文字コードになるので，UTF-8 に固定する
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
        print(pad_tables(sys.stdin.read()), end='')
        return

    for path in args:
        # バイトで読み書きし，BOM と改行コード (CRLF/LF) を元のまま保つ
        with open(path, 'rb') as f:
            data = f.read().decode('utf-8')
        bom = data.startswith('﻿')
        original = data[1:] if bom else data
        formatted = pad_tables(original)
        if formatted != original:
            with open(path, 'wb') as f:
                f.write((('﻿' if bom else '') + formatted).encode('utf-8'))
            print(f'Padded: {path}')
        else:
            print(f'No change: {path}')


if __name__ == '__main__':
    main()
