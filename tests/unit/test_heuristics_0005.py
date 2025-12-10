from fct_analysis.heuristics import extract_visa_office_heuristic, extract_judge_heuristic


def test_extract_visa_office_from_common_names():
    text = "This case involves the Beijing visa office and related delays."
    assert extract_visa_office_heuristic(text) == "Beijing"


def test_extract_visa_office_pattern():
    text = "Some text. Visa Office: Ankara. More text."
    assert extract_visa_office_heuristic(text) == "Ankara"


def test_extract_judge_simple():
    text = "Reasons of Justice Smith for the decision." 
    assert extract_judge_heuristic(text) == "Smith"
