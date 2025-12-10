"""Utility helpers: logging and checkpoint management (minimal)."""
from __future__ import annotations

from pathlib import Path
import json


def write_checkpoint(path: str | Path, obj: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
