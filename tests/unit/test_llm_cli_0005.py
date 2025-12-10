import json
from pathlib import Path

import pandas as pd

from fct_analysis import cli


def _write_cases_json(path: Path, cases: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(cases, fh, ensure_ascii=False)


def test_analyze_llm_heuristic_only(tmp_path, monkeypatch):
    # Case with heuristic-detectable visa office and judge
    case = {
        "case_number": "IMM-1-21",
        "filing_date": "2021-01-03",
        "title": "SANOD KUWAR v. MCI",
        "office": "Beijing",
        "docket_entries": [],
        "style_of_cause": "SANOD KUWAR v. MCI",
    }
    infile = tmp_path / "cases.json"
    _write_cases_json(infile, [case])

    outdir = tmp_path / "out"
    res = cli.analyze(input_path=str(infile), mode="llm", output_dir=outdir, input_format="file", sample_audit=0, resume=False)
    assert res == 0

    details = outdir / "federal_cases_0005_details.csv"
    assert details.exists()
    df = pd.read_csv(details)
    # Heuristics should have populated visa_office (Beijing) and judge may be None
    assert "visa_office" in df.columns
    assert df.loc[0, "visa_office"] in ("Beijing", "Beijing")


def test_analyze_llm_with_llm_and_checkpoint(tmp_path, monkeypatch):
    # Case without heuristics; mock LLM to return values
    case = {
        "case_number": "IMM-2-21",
        "filing_date": "2021-02-01",
        "title": "Unknown Case",
        "office": "",
        "docket_entries": [],
    }
    infile = tmp_path / "cases2.json"
    _write_cases_json(infile, [case])

    # Mock the LLM client
    def fake_llm(text, model="qwen2.5-7b-instruct", ollama_url=None):
        return {"visa_office": "Vancouver", "judge": "Justice Doe"}

    monkeypatch.setattr("fct_analysis.llm.extract_entities_with_ollama", fake_llm)

    outdir = tmp_path / "out2"
    res = cli.analyze(input_path=str(infile), mode="llm", output_dir=outdir, input_format="file", sample_audit=1, resume=False)
    assert res == 0

    # Check outputs
    details = outdir / "federal_cases_0005_details.csv"
    assert details.exists()
    df = pd.read_csv(details)
    assert "visa_office" in df.columns
    assert df.loc[0, "visa_office"] == "Vancouver"

    # Check checkpoint file
    checkpoint = outdir / "0005_checkpoint.ndjson"
    assert checkpoint.exists()
    with checkpoint.open("r", encoding="utf-8") as fh:
        lines = [json.loads(l) for l in fh if l.strip()]
    assert any(l.get("case_number") == "IMM-2-21" and l.get("visa_office") == "Vancouver" for l in lines)
