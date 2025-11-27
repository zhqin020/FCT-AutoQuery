import tempfile
from pathlib import Path
from src.services.files_purge import purge_output_year, remove_modal_html_for_year


def create_sample_year_tree(base_dir: Path, year: int, filenames):
    target = base_dir / str(year)
    target.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        p = target / name
        p.write_text("x")
    return target


def test_purge_output_year_removes_files_and_dirs(tmp_path):
    base = tmp_path / "output"
    # create top-level year dir with 3 files
    ydir = create_sample_year_tree(base, 1999, ["a.json", "b.json", "c.txt"])
    res = purge_output_year(base, 1999)
    assert res["removed_files"] == 3
    assert res["removed_dirs"] >= 0
    assert not ydir.exists()


def test_remove_modal_html_for_year(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    # create html files with year token
    (logs / "modal_IMM-1-1999_1.html").write_text("x")
    (logs / "modal_IMM-2-1999_2.html").write_text("x")
    (logs / "other.txt").write_text("x")

    res = remove_modal_html_for_year(logs, 1999)
    assert res["removed"] == 2
    # ensure other file remains
    assert (logs / "other.txt").exists()
