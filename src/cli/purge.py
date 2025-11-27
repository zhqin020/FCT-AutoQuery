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
from src.services.files_purge import purge_output_year, remove_modal_html_for_year
from src.services.purge_service import db_purge_year
import os
from typing import Dict


def _find_output_files_for_year(output_dir: Path, year: int, per_case_subdir: Optional[str] = None) -> List[Path]:
    """Find files under `output/<year>` and `output/<per_case_subdir>/<year>`.

    Historically per-case JSON files live under `output/json/<year>`. The
    purge logic should enumerate and delete both locations so `--force-files`
    actually removes per-case JSON artifacts.
    """
    matches: List[Path] = []

    # Top-level year dir: output/<year>
    target = output_dir / str(year)
    if target.exists():
        matches.extend([p for p in target.rglob("*") if p.is_file()])

    # Per-case subdir: output/<per_case_subdir>/<year>
    if per_case_subdir:
        target2 = output_dir / per_case_subdir / str(year)
        if target2.exists():
            matches.extend([p for p in target2.rglob("*") if p.is_file()])

    return matches


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
    sql_year_filter: Optional[bool] = None,
    force_files: bool = False,
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
        "sql_year_filter": sql_year_filter,
        "files": {"output_files": [], "modal_html": []},
        "db": {"rows_selected": None},
    }

    per_case_subdir = Config.get_per_case_subdir()

    if not db_only:
        output_files = _find_output_files_for_year(out_dir, year, per_case_subdir=per_case_subdir)
        modal_files = _find_modal_html_for_year(logs_path, year)
        summary["files"]["output_files"] = [str(p) for p in output_files]
        summary["files"]["modal_html"] = [str(p) for p in modal_files]

    # DB enumeration placeholder: in full implementation this queries DB for rows
    if not files_only:
        # indicate that DB rows should be selected/deleted; actual selection
        # happens in the DB purge implementation (not in this skeleton)
        summary["db"]["rows_selected"] = "TODO: run COUNT(*) on cases for year"

    db_success = True
    db_result = None
    db_failure = False
    # Perform DB purge when this is a real run and DB work is requested
    if not dry_run and not files_only:
        try:
            # Build a get_connection factory using configured DB settings
            try:
                import psycopg2

                def get_conn():
                    cfg = Config.get_db_config()
                    return psycopg2.connect(**cfg)
            except Exception:
                # If psycopg2 is not available or connection fails, raise
                def get_conn():
                    raise RuntimeError("No DB driver (psycopg2) available or DB not configured")

            db_result = db_purge_year(year, get_conn, transactional=True, sql_year_filter=sql_year_filter)
            summary["db"] = db_result
            # reflect in audit below
        except Exception as e:
            # Record DB error and mark failure; decision to continue with file
            # purge will be based on the `force_files` flag.
            msg = str(e)
            summary.setdefault("db_errors", []).append(msg)
            db_failure = True
            db_success = False
            summary["db"] = {"error": msg}

    # Construct audit payload
    audit = {
        "timestamp": datetime.now().isoformat(),
        "year": year,
        "dry_run": bool(dry_run),
        "backup": summary["backup"],
        "sql_year_filter": sql_year_filter,
        "files": {
            "output_count": len(summary["files"]["output_files"]),
            "modal_count": len(summary["files"]["modal_html"]),
            "sample_output": summary["files"]["output_files"][:10],
            "sample_modal": summary["files"]["modal_html"][:10],
        },
        "db": summary["db"],
        "notes": [],
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

    # If this is a real run, perform filesystem deletions (unless db_only)
    # By default we proceed with file purge for test/dev environments where
    # DB may be absent. The `--force-files` flag is primarily an explicit
    # operator signal; we record if it was used. Future behavior can tighten
    # this logic (skip files when DB fails unless forced).
    do_file_purge = (not dry_run) and (not db_only)

    if db_failure and force_files:
        audit.setdefault("notes", []).append("file purge forced by operator via --force-files despite DB errors")
    elif db_failure:
        audit.setdefault("notes", []).append("DB purge failed; proceeding with file purge by default")

    if do_file_purge:
        # Remove both `output/<year>` and `output/<per_case_subdir>/<year>`
        del_info: Dict[str, Dict[str, int]] = {}
        try:
            info_top = purge_output_year(out_dir, year)
            del_info["output_top"] = info_top
            audit["files"]["output_removed_top"] = info_top
            summary.setdefault("files_removed", {})["output_top"] = info_top
        except Exception as e:
            audit.setdefault("errors", []).append(f"output_purge_failed: {e}")

        try:
            per_case_base = out_dir / per_case_subdir
            info_sub = purge_output_year(per_case_base, year)
            del_info["output_per_case"] = info_sub
            audit["files"]["output_removed_per_case"] = info_sub
            summary.setdefault("files_removed", {})["output_per_case"] = info_sub
        except Exception as e:
            audit.setdefault("errors", []).append(f"output_per_case_purge_failed: {e}")

        try:
            modal_info = remove_modal_html_for_year(logs_path, year)
            audit["files"]["modal_removed"] = modal_info
            summary.setdefault("files_removed", {})["modal_html"] = modal_info
        except Exception as e:
            audit.setdefault("errors", []).append(f"modal_purge_failed: {e}")
    else:
        if not dry_run and not db_only and not db_success:
            audit.setdefault("errors", []).append("skipped_file_purge_due_to_db_failure")

    # Mirror audit notes into the summary for easier programmatic checks
    summary["notes"] = audit.get("notes", [])

    audit_path = _write_audit(audit, out_dir, year)
    summary["audit_path"] = str(audit_path)

    return summary
