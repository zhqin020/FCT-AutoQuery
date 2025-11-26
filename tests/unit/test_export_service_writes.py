import os
import json
import random
from datetime import datetime, timezone

import pytest

from src.services.export_service import ExportService
from src.lib.config import Config
from src.models.case import Case


def test_export_case_retries_and_calls_fsync(tmp_path, monkeypatch):
    import os
    import json
    import random
    from datetime import datetime, timezone

    import pytest

    from src.services.export_service import ExportService
    from src.lib.config import Config
    from src.models.case import Case


    def test_export_case_retries_and_calls_fsync(tmp_path, monkeypatch):
        outdir = tmp_path / "output"
        svc = ExportService(Config, output_dir=str(outdir))

        case = Case(case_id="IMM-TEST-RETRY", style_of_cause="Retry Test")

        # Track calls
        calls = {"replace": 0, "fsync": 0}

        real_replace = os.replace
        real_fsync = os.fsync

        def fake_replace(src, dst):
            calls["replace"] += 1
            if calls["replace"] == 1:
                raise OSError("simulated replace failure")
            return real_replace(src, dst)

        def fake_fsync(fd):
            calls["fsync"] += 1
            return real_fsync(fd)

        monkeypatch.setattr(os, "replace", fake_replace)
        monkeypatch.setattr(os, "fsync", fake_fsync)

        path = svc.export_case_to_json(case)
        assert os.path.exists(path)
        assert calls["replace"] >= 2
        assert calls["fsync"] >= 1

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("case_number") == "IMM-TEST-RETRY"


    def test_export_case_appends_suffix_if_exists(tmp_path):
        outdir = tmp_path / "output"
        svc = ExportService(Config, output_dir=str(outdir))

        # Build expected directory and pre-create a file to force suffix
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        per_case_subdir = Config.get_per_case_subdir()
        json_dir = outdir / per_case_subdir / date_str[:4]
        json_dir.mkdir(parents=True, exist_ok=True)

        safe_case = "IMM-EXIST-1"
        base_name = f"{safe_case}-{date_str}.json"
        existing = json_dir / base_name
        existing.write_text("{}", encoding="utf-8")

        case = Case(case_id=safe_case, style_of_cause="Exist Test")

        new_path = svc.export_case_to_json(case)
        assert os.path.exists(new_path)
        assert not str(new_path).endswith(base_name)
        # ensure suffix present
        assert "-1.json" in str(new_path) or "-2.json" in str(new_path)