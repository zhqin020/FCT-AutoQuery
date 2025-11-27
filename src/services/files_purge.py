"""Filesystem helpers for backup and purge operations.

Currently provides `backup_output_year` which archives `output/<YEAR>` into a
tar.gz archive stored in the backups directory or at a user-specified path.
"""
from __future__ import annotations

import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional


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
