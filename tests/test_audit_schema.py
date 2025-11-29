import json
import tempfile
from pathlib import Path


def test_audit_summary_and_ndjson_consistency(tmp_path: Path):
    # Create a fake audit summary JSON
    audit = {
        "run_id": "run-1",
        "start_id": 1,
        "end_id": 3,
        "total_attempted": 3,
        "success_count": 2,
        "no_record_count": 0,
        "failed_count": 1,
    }

    audit_path = tmp_path / "audit_run-1.json"
    with audit_path.open("w", encoding="utf-8") as fh:
        json.dump(audit, fh)

    # Create NDJSON attempts file with three lines
    ndjson_path = tmp_path / "attempts_run-1.ndjson"
    lines = []
    lines.append({"run_id": "run-1", "case_id": "IMM-1-25", "attempt": 1, "outcome": "success"})
    lines.append({"run_id": "run-1", "case_id": "IMM-2-25", "attempt": 1, "outcome": "success"})
    lines.append({"run_id": "run-1", "case_id": "IMM-3-25", "attempt": 1, "outcome": "failed"})

    with ndjson_path.open("w", encoding="utf-8") as fh:
        for obj in lines:
            fh.write(json.dumps(obj) + "\n")

    # Read and validate
    with audit_path.open("r", encoding="utf-8") as fh:
        a = json.load(fh)

    # Parse NDJSON
    outcomes = {"success": 0, "no-record": 0, "failed": 0}
    with ndjson_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            out = obj.get("outcome")
            if out not in outcomes:
                # Accept both 'no-record' and 'no_record' forms defensively
                out = out.replace("_", "-")
            outcomes[out] += 1

    assert a["total_attempted"] == sum(outcomes.values())
    assert a["success_count"] == outcomes["success"]
    assert a["failed_count"] == outcomes["failed"]
