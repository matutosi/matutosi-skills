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


def parse_row(line: str) -> list:
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    return [cell.strip() for cell in line.split('|')]


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


def pad_tables(content: str) -> str:
    lines = content.split('\n')
    result = []
    i = 0
    while i < len(lines):
        if is_table_line(lines[i]):
            start = i
            while i < len(lines) and is_table_line(lines[i]):
                i += 1
            result.extend(format_table(lines[start:i]))
        else:
            result.append(lines[i])
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
        with open(path, 'r', encoding='utf-8') as f:
            original = f.read()
        formatted = pad_tables(original)
        if formatted != original:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(formatted)
            print(f'Padded: {path}')
        else:
            print(f'No change: {path}')


if __name__ == '__main__':
    main()
