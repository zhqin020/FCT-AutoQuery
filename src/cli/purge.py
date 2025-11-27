"""Purge helper for yearly data removal.

Implements a safe dry-run enumeration and audit writer. This module intentionally
keeps destructive actions out of the initial implementation: `purge_year` supports
dry-run and writing an audit JSON. Filesystem paths can be injected for testability.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.lib.config import Config
from src.services.files_purge import backup_output_year


def _find_output_files_for_year(output_dir: Path, year: int) -> List[Path]:
    target = output_dir / str(year)
    if not target.exists():
        return []
    return [p for p in target.rglob("*") if p.is_file()]


def _find_modal_html_for_year(logs_dir: Path, year: int) -> List[Path]:
    # Modal HTML filenames include the timestamp and sometimes the year; we
    # match files that contain the year string in their name (simple heuristic).
    matches: List[Path] = []
    if not logs_dir.exists():
        return matches
    year_token = str(year)
    for p in logs_dir.iterdir():
        if p.is_file() and year_token in p.name and p.suffix.lower() in (".html", ".htm"):
            matches.append(p)
    return matches


def _write_audit(audit: Dict[str, Any], output_dir: Path, year: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit_path = output_dir / f"purge_audit_{ts}_{year}.json"
    with audit_path.open("w", encoding="utf-8") as fh:
        json.dump(audit, fh, indent=2, default=str)
    return audit_path


def purge_year(
    year: int,
    *,
    dry_run: bool = True,
    backup: Optional[str] = None,
    no_backup: bool = False,
    files_only: bool = False,
    db_only: bool = False,
    output_dir: Optional[str] = None,
    logs_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Enumerate (and optionally later delete) data for `year`.

    Current implementation performs enumeration and writes an audit JSON.

    Args:
        year: year to purge
        dry_run: if True, do not perform destructive actions
        backup: optional backup path (unused in this minimal impl)
        no_backup: if True, skip backups
        files_only: only consider filesystem artifacts
        db_only: only consider DB artifacts
        output_dir: override output directory (for testing)
        logs_dir: override logs directory (for testing)

    Returns:
        dict summary containing counts and `audit_path` (where audit written)
    """
    cfg_output = Config.get_output_dir()
    out_dir = Path(output_dir) if output_dir else Path(cfg_output)
    cfg_logs = Path("logs")
    logs_path = Path(logs_dir) if logs_dir else cfg_logs

    summary: Dict[str, Any] = {
        "year": year,
        "dry_run": bool(dry_run),
        "backup": None if no_backup else (backup or "default"),
        "files": {"output_files": [], "modal_html": []},
        "db": {"rows_selected": None},
    }

    if not db_only:
        output_files = _find_output_files_for_year(out_dir, year)
        modal_files = _find_modal_html_for_year(logs_path, year)
        summary["files"]["output_files"] = [str(p) for p in output_files]
        summary["files"]["modal_html"] = [str(p) for p in modal_files]

    # DB enumeration placeholder: in full implementation this queries DB for rows
    if not files_only:
        # indicate that DB rows should be selected/deleted; actual selection
        # happens in the DB purge implementation (not in this skeleton)
        summary["db"]["rows_selected"] = "TODO: run COUNT(*) on cases for year"

    # Construct audit payload
    audit = {
        "timestamp": datetime.now().isoformat(),
        "year": year,
        "dry_run": bool(dry_run),
        "backup": summary["backup"],
        "files": {
            "output_count": len(summary["files"]["output_files"]),
            "modal_count": len(summary["files"]["modal_html"]),
            "sample_output": summary["files"]["output_files"][:10],
            "sample_modal": summary["files"]["modal_html"][:10],
        },
        "db": summary["db"],
        "notes": "dry_run only; no deletions performed by this implementation",
    }

    # If this is a real run (not dry-run) and backups are enabled, create backup
    if not dry_run and not no_backup:
        try:
            dest = Path(backup) if backup else None
            archive = backup_output_year(out_dir, year, dest)
            audit["backup_created"] = str(archive)
            summary["backup_path"] = str(archive)
        except Exception as e:
            audit.setdefault("errors", []).append(f"backup_failed: {e}")
            summary["backup_path"] = None

    audit_path = _write_audit(audit, out_dir, year)
    summary["audit_path"] = str(audit_path)

    return summary
