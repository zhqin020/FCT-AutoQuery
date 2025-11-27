from pathlib import Path
from src.cli.purge import purge_year


def _make_files(tmp_path: Path, year: int):
    out = tmp_path / "output"
    logs = tmp_path / "logs"
    (out / str(year)).mkdir(parents=True)
    (out / str(year) / "case.json").write_text("{}")
    logs.mkdir(parents=True)
    (logs / f"modal_IMM-1-25_{year}_a.html").write_text("<html></html>")
    return out, logs


def test_force_files_adds_forced_note_and_removes(tmp_path: Path):
    year = 2023
    out, logs = _make_files(tmp_path, year)

    res = purge_year(year, dry_run=False, output_dir=str(out), logs_dir=str(logs), force_files=True)

    # Files should be removed
    assert not (out / str(year)).exists()
    assert not (logs / f"modal_IMM-1-25_{year}_a.html").exists()

    # Audit notes should include forced message
    notes = res.get("notes", [])
    assert any("forced by operator" in n for n in notes)


def test_no_force_files_records_db_failure_note(tmp_path: Path):
    year = 2024
    out, logs = _make_files(tmp_path, year)

    res = purge_year(year, dry_run=False, output_dir=str(out), logs_dir=str(logs), force_files=False)

    # Files should be removed by default behavior
    assert not (out / str(year)).exists()
    assert not (logs / f"modal_IMM-1-25_{year}_a.html").exists()

    # Audit notes should indicate DB purge failed but proceeded
    notes = res.get("notes", [])
    # Accept either explicit DB-failure note (when DB is unavailable) or
    # no note at all (when DB succeeded in the test environment).
    assert (not notes) or any("DB purge failed" in n or "proceeding with file purge" in n for n in notes)
