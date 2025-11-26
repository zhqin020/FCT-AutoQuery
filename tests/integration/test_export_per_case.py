"""Integration test for per-case audit entries from ExportService.export_and_save()."""

import json
import os
import tempfile
from datetime import date, datetime

from src.lib.config import Config
from src.models.case import Case
from src.services.export_service import ExportService


def test_export_and_save_returns_per_case_entries():
    """ExportService.export_and_save should return `per_case` audit entries."""
    cases = [
        Case(
            url="https://www.fct-cf.ca/en/court-files-and-decisions/IMM-88888-25",
            court_file_no="IMM-88888-25",
            case_title="Per-case Audit Test",
            court_name="Federal Court",
            case_date=date(2024, 3, 1),
            html_content="<html><body>Audit test</body></html>",
            scraped_at=datetime(2024, 3, 1, 12, 0, 0),
        )
    ]

    with tempfile.TemporaryDirectory() as temp_dir:
        svc = ExportService(Config, temp_dir)

        result = svc.export_and_save(cases, base_filename="per_case_test")

        # Export produced JSON path
        assert isinstance(result, dict)
        assert "json" in result and result["json"] is not None

        # Database summary present
        assert "database" in result
        assert isinstance(result["database"], dict)

        # per_case audit entries present and well-formed
        assert "per_case" in result
        per_case = result["per_case"]
        assert isinstance(per_case, list)
        assert len(per_case) == 1
        entry = per_case[0]
        assert "case_number" in entry
        assert entry["case_number"] == "IMM-88888-25"
        assert "status" in entry
        assert entry["status"] in ("new", "updated", "failed")
        assert "message" in entry

        # Verify JSON file exists on disk
        json_path = result.get("json")
        assert os.path.exists(json_path)

        # Validate JSON contains exported case
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert any(d.get("case_number") == "IMM-88888-25" for d in data)
