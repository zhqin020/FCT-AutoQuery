"""Export cases with '(Final decision)' in docket entries for a specific year.
"""
import sys
import os
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add src to path if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from lib.config import Config
from lib.logging_config import setup_logging

# 配置输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def date_handler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return obj

def export_final_decisions(year: int):
    # Setup logging
    setup_logging(log_level="INFO")
    logger = logging.getLogger(__name__)
    
    # Get DB connection
    db_cfg = Config.get_db_config()
    db_dsn = f"postgresql://{db_cfg['user']}:{db_cfg['password']}@{db_cfg['host']}:{db_cfg['port']}/{db_cfg['database']}"
    engine = create_engine(db_dsn)
    
    year_suffix = f"-{year % 100:02d}"
    msg = f"🔍 Searching for cases from year {year} (suffix {year_suffix}) with '(Final decision)'..."
    logger.info(msg)
    print(msg)
    
    # 1. Find cases with "(Final decision)" in docket entries for the year
    # We join with cases to ensure they belong to the correct year or use case_number suffix
    query_cases = text("""
        SELECT DISTINCT c.case_number
        FROM cases c
        JOIN docket_entries d ON c.case_number = d.case_number
        WHERE c.case_number LIKE :suffix
        AND d.recorded_entry_summary LIKE '%(Final decision)%'
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query_cases, {"suffix": f"%{year_suffix}"})
        case_numbers = [row[0] for row in result]
    
    if not case_numbers:
        msg = f"⚠️ No cases found for year {year} containing '(Final decision)' in docket entries."
        logger.warning(msg)
        print(msg)
        return
    
    msg = f"📈 Found {len(case_numbers)} cases with final decisions."
    logger.info(msg)
    print(msg)
    
    # 2. Fetch analysis results, case info, and all docket entries for these cases
    batch_size = 100
    # Group results: { Type: { Status: [cases] } }
    grouped_data = {
        "Mandamus": {},
        "Others": {}
    }
    stats = {"Granted": 0, "Dismissed": 0, "Other": 0}
    
    print(f"📦 Fetching details for {len(case_numbers)} cases...")
    for i in range(0, len(case_numbers), batch_size):
        batch = case_numbers[i:i+batch_size]
        
        # Get analysis results
        analysis_query = text("""
            SELECT * FROM case_analysis 
            WHERE case_number IN :case_ids
        """)
        
        # Get raw case info
        cases_query = text("""
            SELECT * FROM cases 
            WHERE case_number IN :case_ids
        """)
        
        # Get all docket entries
        docket_query = text("""
            SELECT * FROM docket_entries 
            WHERE case_number IN :case_ids
            ORDER BY case_number, date_filed ASC
        """)
        
        with engine.connect() as conn:
            analysis_rows = [dict(row._mapping) for row in conn.execute(analysis_query, {"case_ids": tuple(batch)})]
            case_rows = [dict(row._mapping) for row in conn.execute(cases_query, {"case_ids": tuple(batch)})]
            docket_rows = [dict(row._mapping) for row in conn.execute(docket_query, {"case_ids": tuple(batch)})]
            
        # Organize data
            for case_num in batch:
            analysis = next((r for r in analysis_rows if r.get('case_number') == case_num), {})
            case_info = next((r for r in case_rows if r['case_number'] == case_num), {})
            dockets = [r for r in docket_rows if r['case_number'] == case_num]
            
            # Update stats
            status = analysis.get('case_status', 'Unknown')
            case_type_raw = analysis.get('case_type', 'Other')
            judge = analysis.get('judge', 'None')
            
            # Map type to "Mandamus" or "Others"
            group_key = "Mandamus" if case_type_raw == "Mandamus" else "Others"
            
            # Print individual case result
            print(f"📄 Case {case_num}: Type={case_type_raw}, Status={status}, Judge={judge}")
            
            if status == 'Granted':
                stats['Granted'] += 1
            elif status == 'Dismissed':
                stats['Dismissed'] += 1
            else:
                stats['Other'] += 1
                
            case_obj = {
                "case_number": case_num,
                "analysis_result": {k: date_handler(v) for k, v in analysis.items()},
                "raw_case_info": {k: date_handler(v) for k, v in case_info.items()},
                "docket_entries": [{k: date_handler(v) for k, v in e.items()} for e in dockets]
            }
            
            # Add to grouped data
            if status not in grouped_data[group_key]:
                grouped_data[group_key][status] = []
            grouped_data[group_key][status].append(case_obj)
            
    # 3. Output stats and save JSON
    total_count = sum(len(cases) for type_groups in grouped_data.values() for cases in type_groups.values())
    
    # Header
    output_msg = [
        "=" * 40,
        "    FINAL DECISION EXPORT STATS",
        "=" * 40,
        f"Total Cases Found: {total_count}",
        ""
    ]
    
    # Add stats for each category
    for group_name in ["Mandamus", "Others"]:
        group_total = sum(len(cases) for cases in grouped_data[group_name].values())
        output_msg.append(f"📂 {group_name} (Total: {group_total})")
        
        # Sort statuses by count descending
        sorted_statuses = sorted(grouped_data[group_name].items(), key=lambda x: len(x[1]), reverse=True)
        for status, cases in sorted_statuses:
            output_msg.append(f"   - {status:12}: {len(cases):>4}")
        output_msg.append("")
        
    output_msg.append("=" * 40)
    
    for line in output_msg:
        logger.info(line)
        print(line)
    
    output_file = os.path.join(OUTPUT_DIR, f"final_decisions_{year}.json")
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(grouped_data, f, ensure_ascii=False, indent=2)
        success_msg = f"✅ Exported grouped data to {output_file}"
        logger.info(success_msg)
        print(success_msg)
    except Exception as e:
        logger.error(f"Failed to write export file: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export cases with (Final decision) in dockets")
    parser.add_argument("--year", type=int, default=2025, help="Year to export (default: 2025)")
    args = parser.parse_args()
    
    export_final_decisions(args.year)
