import tempfile
from pathlib import Path

from src.cli.purge import purge_year


def test_purge_year_dry_run_creates_audit(tmp_path: Path):
    # Arrange: create a fake output/<YEAR> tree and logs
    year = 2023
    output_dir = tmp_path / "output"
    logs_dir = tmp_path / "logs"
    (output_dir / str(year)).mkdir(parents=True)
    # create a fake per-case file
    f1 = output_dir / str(year) / "case1.json"
    f1.write_text("{}")
    # create a fake modal file in logs
    logs_dir.mkdir(parents=True)
    modal = logs_dir / f"modal_IMM-1-25_{year}_000001.html"
    modal.write_text("<html></html>")

    # Act
    result = purge_year(
        year,
        dry_run=True,
        output_dir=str(output_dir),
        logs_dir=str(logs_dir),
    )

    # Assert
    assert result["year"] == year
    assert result["dry_run"] is True
    assert "audit_path" in result
    # audit file exists
    audit_path = Path(result["audit_path"])
    assert audit_path.exists()
    # references to the created files
    assert any("case1.json" in p for p in result["files"]["output_files"]) 
    assert any("modal_IMM-1-25" in p for p in result["files"]["modal_html"]) 
