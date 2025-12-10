#!/usr/bin/env python3
"""
Test analysis with limited cases by modifying database query.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import logging
import pandas as pd
from fct_analysis import parser as _parser, rules as _rules
from fct_analysis.db_schema import AnalysisResultStorage

def test_analysis():
    """Test analysis with a few cases."""
    logging.basicConfig(level=logging.INFO)
    
    print("Testing analysis with 5 cases...")
    
    # Direct database query for limited cases
    from lib.config import Config
    from psycopg2 import connect
    from psycopg2.extras import RealDictCursor
    
    db_config = Config.get_db_config()
    
    with connect(**db_config) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT 
                    c.case_number,
                    c.style_of_cause,
                    c.office,
                    c.filing_date,
                    c.case_type,
                    c.type_of_action,
                    c.nature_of_proceeding,
                    (
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'id', d.id_from_table,
                                'case_id', d.case_number,
                                'doc_id', d.id_from_table,
                                'entry_date', d.date_filed,
                                'entry_office', d.office,
                                'summary', d.recorded_entry_summary
                            )
                        )
                        FROM docket_entries d
                        WHERE d.case_number = c.case_number
                    ) as docket_entries
                FROM cases c
                WHERE c.case_number IN ('IMM-1-21', 'IMM-1-25')
                LIMIT 2
            """)
            
            cases = [dict(row) for row in cursor.fetchall()]
            print(f"Fetched {len(cases)} cases")
    
    # Parse cases
    df = _parser._parse_cases_list(cases)
    print(f"Parsed DataFrame: {len(df)} rows")
    
    # Analyze cases
    storage = AnalysisResultStorage()
    
    for idx, row in df.iterrows():
        case_id = row.get('case_number')
        raw_case = row.get('raw')
        
        # Rule-based analysis
        result = _rules.classify_case_rule(raw_case)
        
        print(f"Case {case_id}: type={result.get('type')}, status={result.get('status')}")
        
        # Save to analysis table
        analysis_result = {
            'type': result.get('type'),
            'status': result.get('status'),
            'visa_office': None,
            'judge': None,
            'title': raw_case.get('style_of_cause'),
            'court': raw_case.get('office'),
            'filing_date': raw_case.get('filing_date')
        }
        
        success = storage.save_analysis_result(case_id, analysis_result, 'rule')
        print(f"Saved result: {success}")
    
    return 0

if __name__ == "__main__":
    sys.exit(test_analysis())