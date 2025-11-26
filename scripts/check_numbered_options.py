#!/usr/bin/env python3
"""
Check that any Markdown section titled with "Options"/"Choices"/"选择"/"选项"
uses numbered lists (e.g. `1. Item`) rather than bullets or lettered options.

Usage: python3 scripts/check_numbered_options.py
Exits with non-zero status if violations are found.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [
    re.compile(r"^#+\s*(Options|Choices|Select|选择|选项)\b", re.I),
]
NUMBERED_ITEM_RE = re.compile(r"^\s*\d+\.\s+")
UNNUMBERED_ITEM_RE = re.compile(r"^\s*([-\*]|[A-Za-z]\)|\([A-Za-z]\))\s+")

def files_to_check():
    globs = ["specs/**/*.md", "docs/**/*.md", "README.md", "USAGE_GUIDE.md"]
    seen = []
    for g in globs:
        for p in ROOT.glob(g):
            if p.is_file():
                seen.append(p)
    return seen

def check_file(p: Path):
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    in_section = False
    section_start = None
    violations = []
    for i, line in enumerate(lines, start=1):
        # header detection
        if any(pat.match(line) for pat in PATTERNS):
            in_section = True
            section_start = i
            continue
        # if another header of same or higher level starts, leave section
        if in_section and re.match(r"^#+\s+", line):
            in_section = False
            section_start = None
            continue
        if in_section:
            if line.strip() == "":
                continue
            # If it's a list item and not numbered, it's a violation
            if UNNUMBERED_ITEM_RE.match(line) and not NUMBERED_ITEM_RE.match(line):
                violations.append((i, line))
    return violations

def main():
    files = files_to_check()
    if not files:
        return 0
    total_violations = 0
    for f in files:
        v = check_file(f)
        if v:
            total_violations += len(v)
            print(f"{f}: found {len(v)} unnumbered option(s) in 'Options' section:")
            for lineno, line in v:
                print(f"  L{lineno}: {line.strip()}")
    if total_violations > 0:
        print("\nERROR: Please use numbered lists (e.g. '1. Item') for option sections.")
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
