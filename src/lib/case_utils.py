"""Utilities for handling case number canonicalization and formatting.

Canonicalization ensures 'IMM-0005-21' and 'IMM-5-21' are treated as the same
case by normalizing them to 'IMM-5-21'.
"""
import re


def canonicalize_case_number(case_number: str) -> str:
    """Return a canonical case number string.

    Canonical form: 'IMM-<seq>-YY' with the sequence as a non-zero-padded integer.
    Examples:
      - 'IMM-0005-21' -> 'IMM-5-21'
      - 'IMM/05/21' -> 'IMM-5-21'
      - 'IMM 5 21' -> 'IMM-5-21'
    If case_number cannot be parsed, return case_number unchanged.
    """
    if not case_number:
        return case_number
    try:
        # Accept a flexible separator between IMM and the numeric parts
        # match 'IMM' with optional non-digit separators, sequence, and 2-digit year
        m = re.search(r"(?i)IMM\D*0*(\d+)\D*(\d{2})", case_number)
        if m:
            seq = str(int(m.group(1)))
            yy = m.group(2)
            return f"IMM-{seq}-{yy}"
    except Exception:
        pass
    return case_number
