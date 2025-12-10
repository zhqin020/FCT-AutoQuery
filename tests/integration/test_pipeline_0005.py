from fct_analysis import cli
from pathlib import Path
import json


def test_pipeline_rule_mode(tmp_path):
    sample = [
        {"case_number": "IMM-1", "filing_date": "2024-12-01", "docket_entries": [{"summary": "compel"}]}
    ]
    p = tmp_path / "cases.json"
    p.write_text(json.dumps(sample))
    out_dir = tmp_path / "output"
    rc = cli.analyze(str(p), mode="rule", output_dir=out_dir)
    assert rc == 0
    assert (out_dir / "federal_cases_0005_details.csv").exists()
    assert (out_dir / "federal_cases_0005_summary.json").exists()
import subprocess
from pathlib import Path


def test_pipeline_rule_mode_creates_outputs(tmp_path):
    outdir = tmp_path / "out"
    outdir.mkdir()
    fixture = Path("tests/fixtures/0005_cases.json")
    # invoke CLI module directly via python -m
    cmd = ["python", "-m", "fct_analysis.cli", "--input", str(fixture), "--mode", "rule", "--output-dir", str(outdir)]
    subprocess.check_call(cmd)

    assert (outdir / "federal_cases_0005_details.csv").exists()
    assert (outdir / "federal_cases_0005_summary.json").exists()
