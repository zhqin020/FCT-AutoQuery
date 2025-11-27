from pathlib import Path
import tarfile

from src.cli.purge import purge_year


def test_purge_creates_backup(tmp_path: Path):
    year = 2024
    output_dir = tmp_path / "output"
    (output_dir / str(year)).mkdir(parents=True)
    # create sample file
    sample = output_dir / str(year) / "sample.json"
    sample.write_text("{}")

    # Act: perform non-dry run so backup is created
    res = purge_year(year, dry_run=False, output_dir=str(output_dir), no_backup=False)

    assert "backup_path" in res
    assert res["backup_path"] is not None
    archive = Path(res["backup_path"])
    assert archive.exists()
    # Inspect archive to ensure it contains the sample file
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
        # The archive should contain a path like '2024/sample.json'
        assert any("sample.json" in n for n in names)
