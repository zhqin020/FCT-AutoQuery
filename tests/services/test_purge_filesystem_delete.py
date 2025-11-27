from pathlib import Path

from src.cli.purge import purge_year


def test_purge_removes_output_and_modal(tmp_path: Path):
    year = 2025
    output_dir = tmp_path / "output"
    logs_dir = tmp_path / "logs"
    (output_dir / str(year)).mkdir(parents=True)
    sample = output_dir / str(year) / "s.json"
    sample.write_text("{}")
    logs_dir.mkdir(parents=True)
    modal = logs_dir / f"modal_IMM-1-25_{year}_abc.html"
    modal.write_text("<html></html>")

    # Act: perform non-dry run which should remove output/<year> and modal
    res = purge_year(year, dry_run=False, output_dir=str(output_dir), logs_dir=str(logs_dir))

    # Assert: output/<year> no longer exists and modal removed
    assert not (output_dir / str(year)).exists()
    assert not modal.exists()
    assert "files_removed" in res
    assert res["files_removed"]["output"]["removed_files"] >= 1
    assert res["files_removed"]["modal_html"]["removed"] == 1
