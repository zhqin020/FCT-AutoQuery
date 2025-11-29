from pathlib import Path
import json
import tempfile

from src.lib.storage import FileSystemStorage


def test_filesystem_storage_exists_and_save(tmp_path: Path):
    out = tmp_path / "output"
    per_case = out / "json"
    per_case.mkdir(parents=True)

    # create a fake existing per-case json
    case_id = "IMM-42-25"
    p = per_case / f"{case_id}.json"
    with p.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"case_id": case_id}))

    storage = FileSystemStorage(output_dir=str(out), per_case_subdir="json")
    assert storage.exists(case_id) is True
    assert storage.exists("IMM-99-25") is False

    # Save failed html
    run_id = "run-1"
    saved = storage.save_failed_html(run_id, case_id, "<html></html>")
    assert saved is not None
    assert (out / "html_failed" / run_id / f"{case_id}.html").exists()
