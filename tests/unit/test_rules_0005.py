from fct_analysis import rules


def test_classify_mandamus():
    row = {"style_of_cause": "Application for Mandamus", "docket_entries": [{"summary": "compel"}]}
    out = rules.classify_case_rule(row)
    assert out["type"] == "Mandamus"
    assert out["status"] in ("Discontinued", "Granted", "Dismissed", "Ongoing")
from fct_analysis.rules import classify_case_rule


def test_classify_mandamus_by_title():
    case = {
        "style_of_cause": "Application for Mandamus to compel decision",
        "title": "Mandamus - IRCC delay",
        "docket_entries": [{"summary": "Application filed", "entry_date": "2024-01-01"}],
    }
    res = classify_case_rule(case)
    assert res["type"] == "Mandamus"
    assert res["status"] in ("Ongoing", "Discontinued", "Granted", "Dismissed")


def test_classify_status_priority_discontinued():
    case = {
        "style_of_cause": "Some title",
        "title": "Notice of Discontinuance filed",
        "docket_entries": [{"summary": "Notice of Discontinuance", "entry_date": "2024-02-01"}],
    }
    res = classify_case_rule(case)
    assert res["status"] == "Discontinued"
