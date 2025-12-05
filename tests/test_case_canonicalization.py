from src.lib.case_utils import canonicalize_case_number


def test_canonicalize_various_forms():
    variants = {
        'IMM-0005-21': 'IMM-5-21',
        'IMM-05-21': 'IMM-5-21',
        'IMM/05/21': 'IMM-5-21',
        'IMM 005 21': 'IMM-5-21',
        'IMM–005–21': 'IMM-5-21',
        'IMM—5—21': 'IMM-5-21',
        'IMM-5-21': 'IMM-5-21',
        'IMM-0123-25': 'IMM-123-25',
    }

    for input_val, expected in variants.items():
        assert canonicalize_case_number(input_val) == expected
