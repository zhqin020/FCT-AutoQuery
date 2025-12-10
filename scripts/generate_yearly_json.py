#!/usr/bin/env python3
"""
Generate year-based JSON file structure for testing analysis module.

This script converts existing case data into the year-based directory structure
expected by the updated analysis module.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import re

def extract_year_from_case_number(case_number: str) -> int:
    """Extract year from case number like IMM-1-21 (for 2021)."""
    if not case_number:
        return datetime.now().year
        
    # Pattern: IMM-XXX-YY where YY is last 2 digits of year
    match = re.search(r'IMM-\d+-(\d{2})', case_number.upper())
    if match:
        year_suffix = match.group(1)
        # Convert 2-digit year to 4-digit year
        if year_suffix.startswith('0'):
            return 2000 + int(year_suffix)
        else:
            return 1900 + int(year_suffix)
    
    return datetime.now().year

def extract_year_from_date(date_str: str) -> int:
    """Extract year from ISO date string."""
    if not date_str:
        return None
        
    try:
        return datetime.fromisoformat(date_str.split('T')[0]).year
    except:
        return None

def convert_to_yearly_structure(input_file: Path, output_dir: Path) -> None:
    """Convert input JSON file to year-based directory structure."""
    
    # Load input data
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        data = [data]
    
    # Group cases by year
    cases_by_year: Dict[int, List[Dict[str, Any]]] = {}
    
    for case in data:
        # Try to determine year
        year = None
        
        # First try filing_date
        filing_date = case.get('filing_date') or case.get('date')
        if filing_date:
            year = extract_year_from_date(filing_date)
        
        # Fallback to case_number
        if not year:
            case_number = case.get('case_number') or case.get('case_id')
            year = extract_year_from_case_number(case_number)
        
        if not year:
            print(f"Warning: Could not determine year for case {case.get('case_number')}")
            continue
        
        if year not in cases_by_year:
            cases_by_year[year] = []
        
        cases_by_year[year].append(case)
    
    # Create output directory structure
    json_dir = output_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    
    # Write cases to year directories
    for year, cases in sorted(cases_by_year.items()):
        year_dir = json_dir / str(year)
        year_dir.mkdir(exist_ok=True)
        
        for case in cases:
            case_number = case.get('case_number') or case.get('case_id', 'unknown')
            filing_date = case.get('filing_date') or case.get('date', datetime.now().strftime('%Y-%m-%d'))
            
            # Create filename: case_number-date.json
            date_part = filing_date.replace('-', '')
            filename = f"{case_number}-{date_part}.json"
            filepath = year_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(case, f, indent=2, ensure_ascii=False)
        
        print(f"Created {len(cases)} files for year {year} in {year_dir}")
    
    print(f"Total: {len(data)} cases organized into {len(cases_by_year)} years")
    print(f"Output directory: {json_dir}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_yearly_json.py <input_json_file> [output_dir]")
        print("Example: python generate_yearly_json.py cases.json output/")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output")
    
    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        sys.exit(1)
    
    convert_to_yearly_structure(input_file, output_dir)

if __name__ == "__main__":
    main()