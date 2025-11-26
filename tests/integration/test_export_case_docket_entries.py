import json
from datetime import date, datetime

from src.services.export_service import ExportService
from src.lib.config import Config
from src.models.case import Case
from src.models.docket_entry import DocketEntry


def test_export_case_includes_docket_entries(tmp_path):
    """Integration test: exporting a Case with DocketEntry objects writes docket_entries."""
    out_dir = tmp_path / "output"
    out_dir.mkdir()

    exp = ExportService(Config, output_dir=str(out_dir))

    case = Case(
        case_id="IMM-INT-25",
        style_of_cause="Integration Test",
        office="Test Court",
        filing_date=date.today(),
        html_content="",
        scraped_at=datetime.now(),
    )

    de = DocketEntry(case_id="IMM-INT-25", doc_id=1, entry_date=date.today(), entry_office="Office", summary="Entry")
    case.docket_entries = [de]

    path = exp.export_case_to_json(case)

    # read back and assert
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    assert isinstance(data, dict)
    assert "docket_entries" in data
    assert isinstance(data["docket_entries"], list)
    assert len(data["docket_entries"]) == 1
    first = data["docket_entries"][0]
    assert first.get("doc_id") == 1
    assert first.get("case_id") == "IMM-INT-25"
