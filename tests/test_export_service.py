import json
import os
import tempfile

from pathlib import Path

import pytest

from src.services.export_service import export_case_to_json, _sanitize_case_number


def test_sanitize_case_number():
    assert _sanitize_case_number("IMM-1/25") == "IMM-1-25"
    assert _sanitize_case_number("  weird ## name  ") == "weird-name"


def test_export_case_to_json_creates_file_and_contents(tmp_path):
    case = {"case_number": "IMM-1-25", "foo": "bar"}
    out = export_case_to_json(case, output_root=str(tmp_path))
    p = Path(out)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["case_number"] == "IMM-1-25"
    assert data["foo"] == "bar"


def test_export_case_to_json_unique_suffix(tmp_path):
    case = {"case_number": "DUP-1", "x": 1}
    # create an existing file with same base name
    from datetime import datetime

    date_str = datetime.utcnow().strftime("%Y%m%d")
    dir_path = Path(tmp_path) / "json" / datetime.utcnow().strftime("%Y")
    dir_path.mkdir(parents=True, exist_ok=True)
    base = dir_path / f"{_sanitize_case_number(case['case_number'])}-{date_str}.json"
    base.write_text(json.dumps({"existing": True}), encoding="utf-8")

    out = export_case_to_json(case, output_root=str(tmp_path))
    assert out != str(base)
    p = Path(out)
    assert p.exists()


def test_export_case_to_json_retries(monkeypatch, tmp_path):
    case = {"case_number": "RTRY-1", "y": 2}

    real_mkstemp = tempfile.mkstemp

    calls = {"n": 0}

    def flaky_mkstemp(dir=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated mkstemp failure")
        return real_mkstemp(dir=dir)

    monkeypatch.setattr(tempfile, "mkstemp", flaky_mkstemp)

    out = export_case_to_json(case, output_root=str(tmp_path))
    assert Path(out).exists()
import json
import os
from pathlib import Path

import pytest

from src.models.case import Case
from src.services.export_service import ExportService


def make_case(case_id: str) -> Case:
    return Case(case_id=case_id, style_of_cause="Test Case", office="Federal Court")


def test_export_case_to_json_creates_file_and_contents(tmp_path):
    out_dir = tmp_path / "out"
    svc = ExportService(config=None, output_dir=str(out_dir))

    case = make_case("IMM-1-25")

    path_str = svc.export_case_to_json(case)
    p = Path(path_str)
    assert p.exists()

    payload = json.loads(p.read_text(encoding="utf-8"))
    # exported payload should be a dict with case_id matching
    assert payload.get("case_id") == case.case_id

    # cleanup
    p.unlink()
    # remove year dir
    try:
        p.parent.rmdir()
    except Exception:
        pass


def test_export_case_to_json_unique_suffix(tmp_path):
    out_dir = tmp_path / "out"
    svc = ExportService(config=None, output_dir=str(out_dir))

    case = make_case("IMM-2-25")

    first = Path(svc.export_case_to_json(case))
    second = Path(svc.export_case_to_json(case))

    assert first.exists()
    assert second.exists()
    # Behavior: export should overwrite existing per-case JSON for same case/date
    assert first == second

    # cleanup
    try:
        first.unlink()
        second.unlink()
    except Exception:
        pass


def test_export_case_to_json_retries_on_mkstemp(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"
    svc = ExportService(config=None, output_dir=str(out_dir))

    case = make_case("IMM-3-25")

    import tempfile as _tempfile

    real_mkstemp = _tempfile.mkstemp

    calls = {"n": 0}

    def failing_mkstemp(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated mkstemp failure")
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr("tempfile.mkstemp", failing_mkstemp)

    path = svc.export_case_to_json(case)
    assert Path(path).exists()
    # ensure mkstemp was called at least twice (first failed, second succeeded)
    assert calls["n"] >= 2

    # cleanup
    try:
        Path(path).unlink()
    except Exception:
        pass
