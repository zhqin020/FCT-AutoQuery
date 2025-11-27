import json
from pathlib import Path

from src.services.export_service import ExportService
from src.models.case import Case


def make_case(case_id: str) -> Case:
    return Case(case_id=case_id, style_of_cause="Test Case", office="Federal Court")


def test_export_service_basic_write(tmp_path):
    out_dir = tmp_path / "out"
    svc = ExportService(config=None, output_dir=str(out_dir))
    case = make_case("HOOK-TEST-1")
    path = svc.export_case_to_json(case)
    p = Path(path)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("case_id") == case.case_id
