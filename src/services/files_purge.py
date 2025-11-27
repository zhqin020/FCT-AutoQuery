"""Filesystem helpers for backup and purge operations.

Currently provides `backup_output_year` which archives `output/<YEAR>` into a
tar.gz archive stored in the backups directory or at a user-specified path.
"""
from __future__ import annotations

import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional
import shutil


def purge_output_year(output_dir: Path, year: int) -> Dict[str, int]:
    """Atomically remove the `output/<year>` directory by renaming then deleting.

    Returns a dict with counts: {'removed_files': n, 'removed_dirs': m}
    """
    year_dir = output_dir / str(year)
    if not year_dir.exists():
        return {"removed_files": 0, "removed_dirs": 0}

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_name = output_dir / f"{year}_to_delete_{ts}"
    # Rename (atomic on same filesystem)
    year_dir.replace(temp_name)

    removed_files = 0
    removed_dirs = 0
    # Now remove recursively
    for root, dirs, files in os.walk(temp_name):
        removed_files += len(files)
        removed_dirs += len(dirs)
    shutil.rmtree(temp_name)

    return {"removed_files": removed_files, "removed_dirs": removed_dirs}


def remove_modal_html_for_year(logs_dir: Path, year: int) -> Dict[str, int]:
    """Remove modal HTML files matching the year token in filename.

    Returns counts {'removed': n, 'skipped': m}
    """
    removed = 0
    skipped = 0
    if not logs_dir.exists():
        return {"removed": 0, "skipped": 0}
    year_token = str(year)
    for p in logs_dir.iterdir():
        if p.is_file() and year_token in p.name and p.suffix.lower() in (".html", ".htm"):
            try:
                p.unlink()
                removed += 1
            except Exception:
                skipped += 1
    return {"removed": removed, "skipped": skipped}



def backup_output_year(output_dir: Path, year: int, dest_dir: Optional[Path] = None) -> Path:
    """Create a tar.gz backup of `output/<year>`.

    Args:
        output_dir: base output directory (contains per-year dirs)
        year: year to backup
        dest_dir: destination directory for the backup archive; if None,
                  `output_dir / 'backups'` will be used.

    Returns:
        Path to the created archive.
    """
    year_dir = output_dir / str(year)
    if not year_dir.exists():
        raise FileNotFoundError(f"Year directory not found: {year_dir}")

    if dest_dir is None:
        dest_dir = output_dir / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = dest_dir / f"output_backup_{year}_{ts}.tar.gz"

    with tarfile.open(archive_name, "w:gz") as tar:
        # add the year_dir contents; use arcname so the tar contains the
        # year directory at its root
        tar.add(year_dir, arcname=str(year_dir.name))

    return archive_name
