from fct_analysis.parser import parse_cases
from pathlib import Path


def test_parse_cases_loads_fixture():
    fixture = Path("tests/fixtures/0005_cases.json")
    df = parse_cases(str(fixture))
    assert not df.empty
    assert "case_number" in df.columns
    assert "filing_date" in df.columns
    # each row must have a docket_entries list
    assert all(isinstance(x, list) for x in df["docket_entries"])
