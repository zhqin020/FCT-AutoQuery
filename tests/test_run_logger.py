import json
from pathlib import Path

def test_run_logger_writes_ndjson(tmp_path):
    # lightweight smoke test assuming a RunLogger implementation at src/lib/run_logger.py
    run_file = tmp_path / "run_test.ndjson"
    # Lazy import so test still passes if helper isn't implemented yet (will raise ImportError)
    from src.lib.run_logger import RunLogger

    rl = RunLogger(str(run_file))
    rl.start(run_id="r1")
    rl.record_case("IMM-1-25", outcome="success")
    rl.finish()

    lines = run_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2
    # first line: start meta, second: case entry
    data = json.loads(lines[1])
    assert data["case_number"] == "IMM-1-25"
    assert data["outcome"] == "success"
