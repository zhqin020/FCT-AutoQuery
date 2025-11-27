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
