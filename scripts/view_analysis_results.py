#!/usr/bin/env python3
"""
View and analyze FCT analysis results from database.

This script provides various ways to view and summarize analysis results
stored in the database without re-running the analysis.
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, Any, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fct_analysis.db_schema import AnalysisResultStorage
import pandas as pd

def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def print_summary(storage: AnalysisResultStorage):
    """Print analysis summary."""
    print("=== ANALYSIS SUMMARY ===")
    stats = storage.get_analysis_statistics()
    
    overall = stats.get('overall', {})
    print(f"Total cases in database: {overall.get('total_cases', 0)}")
    print(f"Analyzed cases: {overall.get('analyzed_cases', 0)}")
    print(f"  Mandamus cases: {overall.get('mandamus_cases', 0)}")
    print(f"  Other cases: {overall.get('other_cases', 0)}")
    print()
    
    print("Case Status Distribution:")
    print(f"  Discontinued: {overall.get('discontinued_cases', 0)}")
    print(f"  Granted: {overall.get('granted_cases', 0)}")
    print(f"  Dismissed: {overall.get('dismissed_cases', 0)}")
    print(f"  Ongoing: {overall.get('ongoing_cases', 0)}")
    print()
    
    by_mode = stats.get('by_mode', [])
    if by_mode:
        print("By Analysis Mode:")
        for mode_stat in by_mode:
            mode = mode_stat.get('analysis_mode', 'unknown')
            count = mode_stat.get('count', 0)
            avg_time = mode_stat.get('avg_time_to_close', 0)
            avg_age = mode_stat.get('avg_age_of_case', 0)
            print(f"  {mode}: {count} cases")
            print(f"    Avg time to close: {avg_time:.1f} days" if avg_time else "    Avg time to close: N/A")
            print(f"    Avg age of case: {avg_age:.1f} days" if avg_age else "    Avg age of case: N/A")

def print_cases(storage: AnalysisResultStorage, mode: str = None, limit: int = 10):
    """Print detailed case information."""
    cases = storage.get_analyzed_cases(mode=mode, limit=limit)
    
    if not cases:
        print("No analyzed cases found.")
        return
    
    print(f"\n=== RECENT ANALYZED CASES (Mode: {mode or 'All'}) ===")
    
    # Convert to DataFrame for nice formatting
    df = pd.DataFrame(cases)
    
    # Display key columns
    display_cols = [
        'case_number', 'case_type', 'case_status', 'visa_office', 
        'judge', 'time_to_close', 'age_of_case', 'analysis_mode', 'analyzed_at'
    ]
    
    # Filter to existing columns
    available_cols = [col for col in display_cols if col in df.columns]
    
    if not df.empty:
        print(df[available_cols].to_string(index=False))
        print(f"\nShowing {len(df)} cases")

def export_cases(storage: AnalysisResultStorage, output_file: str, 
                mode: str = None, format: str = 'csv'):
    """Export cases to file."""
    cases = storage.get_analyzed_cases(mode=mode)
    
    if not cases:
        print("No cases to export.")
        return
    
    df = pd.DataFrame(cases)
    
    try:
        if format.lower() == 'csv':
            df.to_csv(output_file, index=False)
        elif format.lower() == 'excel':
            df.to_excel(output_file, index=False)
        elif format.lower() == 'json':
            df.to_json(output_file, orient='records', indent=2, date_format='iso')
        else:
            print(f"Unsupported format: {format}")
            return
        
        print(f"Exported {len(df)} cases to {output_file}")
        
    except Exception as e:
        print(f"Failed to export: {e}")

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="View FCT analysis results from database"
    )
    
    parser.add_argument("--mode", choices=["rule", "llm"], 
                       help="Filter by analysis mode")
    parser.add_argument("--limit", type=int, default=10,
                       help="Number of cases to show (default: 10)")
    parser.add_argument("--export", 
                       help="Export cases to file")
    parser.add_argument("--format", choices=["csv", "excel", "json"], 
                       default="csv", help="Export format")
    parser.add_argument("--summary-only", action="store_true",
                       help="Show only summary statistics")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose logging")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Initialize storage
    storage = AnalysisResultStorage()
    
    # Always show summary
    print_summary(storage)
    
    if not args.summary_only:
        # Show cases
        print_cases(storage, mode=args.mode, limit=args.limit)
    
    # Export if requested
    if args.export:
        export_cases(storage, args.export, mode=args.mode, format=args.format)

if __name__ == "__main__":
    main()