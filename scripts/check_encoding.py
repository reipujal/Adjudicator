#!/usr/bin/env python3
"""Detect non-UTF-8 text files and common mojibake artifacts.

Usage: python scripts/check_encoding.py <files...>
Exits non-zero when it finds problems, so it is suitable for pre-commit.
"""
import re
import sys

USAGE = """Usage:
  python scripts/check_encoding.py <files...>
  python scripts/check_encoding.py --help

Detects non-UTF-8 files and common mojibake artifacts.
"""

# Keep suspicious tokens escaped so this checker does not flag its own source.
MOJIBAKE = (
    "\u00c3\u00b1",  # n with tilde decoded as latin-1 once
    "\u00c3\u00b3",
    "\u00c3\u00a9",
    "\u00c3\u00ad",
    "\u00c3\u00ba",
    "\u00c3\u00a1",
    "\u00c2\u00bf",
    "\u00c2\u00a1",
    "\u00c3\u0192\u00c2\u00b1",  # decoded as latin-1 twice
    "\u00c3\u0192\u00c2\u00b3",
    "\u00c3\u0192\u00c2\u00a9",
    "\u00c3\u0192\u00c2\u00ad",
    "\u00c3\u0192\u00c2\u00ba",
    "\u00c3\u0192\u00c2\u00a1",
    "\u00c3\u201a\u00c2\u00bf",
    "\u00c3\u201a\u00c2\u00a1",
    "\u00ef\u00bf\u00bd",  # replacement character rendered through mojibake
)

# CJK ranges: Han, Hiragana/Katakana, Hangul. Unexpected in this Spanish/English repo.
_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def check(path: str) -> list[str]:
    problems: list[str] = []
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return problems
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        problems.append(f"{path}: not valid UTF-8")
        return problems
    for token in MOJIBAKE:
        if token in text:
            problems.append(f"{path}: possible mojibake token found")
    if "\ufffd" in text:
        problems.append(f"{path}: replacement character found")
    if _CJK.search(text):
        problems.append(f"{path}: unexpected CJK/script character")
    return problems


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(USAGE.strip())
        return 0
    if len(argv) == 1:
        print(USAGE.strip(), file=sys.stderr)
        return 2
    found: list[str] = []
    for path in argv[1:]:
        found.extend(check(path))
    for p in found:
        print(p, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
