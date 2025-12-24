#!/usr/bin/env python3
"""Batch case analyzer for processing case numbers from a text file.

This script reads a text file containing comma-separated case numbers,
analyzes each case using LLM, and outputs the results grouped by status
in JSON format matching the existing structure.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.fct_analysis import nlp_engine as _nlp_engine
from src.fct_analysis import database as _database
from src.fct_analysis import db_schema as _db_schema
from src.fct_analysis import rules as _rules
from src.lib.config import Config
from src.lib.logging_config import setup_logging
from loguru import logger


def serialize_dates(obj):
    """Convert date objects to ISO format strings for JSON serialization."""
    if hasattr(obj, 'isoformat'):  # Handles datetime.date, datetime.datetime objects
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_dates(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_dates(item) for item in obj]
    else:
        return obj


class BatchCaseAnalyzer:
    """Analyzer for processing multiple cases from a text file."""
    
    def __init__(self, db_connection_str: Optional[str] = None):
        """Initialize the analyzer with database connection."""
        # Setup database connection
        if db_connection_str:
            self.db_connection_str = db_connection_str
        else:
            db_cfg = Config.get_db_config() or {}
            self.db_connection_str = (
                f"postgresql://{db_cfg.get('user')}:{db_cfg.get('password')}"
                f"@{db_cfg.get('host')}:{db_cfg.get('port')}/{db_cfg.get('database')}"
            )
        
        self.engine = create_engine(self.db_connection_str)
        # Get database config for the analysis storage
        self.db_storage = _db_schema.AnalysisResultStorage()  # Uses Config.get_db_config() internally
        
        # Also create a database connection for nlp_engine
        self.db_connection_str = self.db_connection_str
        
        # Output directory
        self.output_dir = os.path.join(project_root, 'output')
        os.makedirs(self.output_dir, exist_ok=True)
    
    def read_case_numbers(self, file_path: str) -> List[str]:
        """Read case numbers from a text file.
        
        Args:
            file_path: Path to the text file containing case numbers
            
        Returns:
            List of case numbers (stripped of whitespace)
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # Split by comma and strip whitespace
                case_numbers = [cn.strip() for cn in content.split(',') if cn.strip()]
            return case_numbers
        except Exception as e:
            logger.error(f"Error reading case numbers from {file_path}: {e}")
            raise
    
    def get_case_data(self, case_number: str) -> Optional[Dict[str, Any]]:
        """Retrieve case data and docket entries from database.
        
        Args:
            case_number: The case number to retrieve
            
        Returns:
            Dictionary with case info and docket entries, or None if not found
        """
        try:
            with self.engine.connect() as conn:
                # Get case info
                case_query = "SELECT * FROM cases WHERE case_number = :case_number"
                case_row = conn.execute(text(case_query), {"case_number": case_number}).fetchone()
                
                if not case_row:
                    logger.warning(f"Case {case_number} not found in database")
                    return None
                    
                # Get docket entries
                docket_query = """
                SELECT * FROM docket_entries 
                WHERE case_number = :case_number 
                ORDER BY id_from_table DESC
                """
                docket_rows = conn.execute(text(docket_query), {"case_number": case_number}).fetchall()
                
                # Convert to dict format
                case_data = dict(case_row._mapping)
                case_data['docket_entries'] = [dict(row._mapping) for row in docket_rows]
                
                return case_data
                
        except Exception as e:
            logger.error(f"Error retrieving data for case {case_number}: {e}")
            return None
    
    def analyze_case(self, case_data: Dict[str, Any], mode: str = "llm", force_reanalyze: bool = True) -> Optional[Dict[str, Any]]:
        """Analyze a single case using the specified mode.
        
        Args:
            case_data: Case data dictionary
            mode: Analysis mode ('llm' or 'rule')
            force_reanalyze: If True, always reanalyze instead of using existing results
            
        Returns:
            Analysis result dictionary or None if analysis failed
        """
        try:
            case_number = case_data.get('case_number')
            
            if not case_number:
                logger.error("Case number is missing from case data")
                return None
            
            # Only use existing analysis if not forcing reanalysis
            if not force_reanalyze:
                existing_analysis = self.db_storage.is_analyzed(case_number, mode)
                if existing_analysis:
                    logger.info(f"Using existing analysis for {case_number}")
                    return existing_analysis
            
            # Perform new analysis
            if mode == "llm":
                # Set environment variable for database connection if needed
                import os
                os.environ['DB_CONNECTION_STR'] = self.db_connection_str
                logger.info(f"🤖 {case_number}: Starting LLM analysis...")
                result = _nlp_engine.classify_case_enhanced(
                    case_data, 
                    use_llm_fallback=True, 
                    wait_for_ollama=True, 
                    ollama_wait_time=180
                )
            else:
                logger.info(f"⚖️ {case_number}: Starting rule-based analysis...")
                result = _rules.classify_case_rule(case_data)
            
            if not result:
                logger.error(f"Analysis failed for case {case_number}")
                return None
            
            # Store analysis in database
            try:
                # Create analysis data and serialize all date objects
                analysis_data = {
                    'type': result.get('type', 'Unknown'),
                    'status': result.get('status', 'Unknown'),
                    'judge': result.get('judge'),
                    'visa_office': result.get('visa_office'),
                    'has_hearing': result.get('has_hearing'),
                    'time_to_close': result.get('time_to_close'),
                    'age_of_case': result.get('age_of_case'),
                    'memo_response_time': result.get('memo_response_time'),
                    'reply_to_outcome_time': result.get('reply_to_outcome_time'),
                    'outcome_date': result.get('outcome_date'),
                    'outcome_entry': result.get('outcome_entry')
                }
                
                # Serialize all date objects
                analysis_data = serialize_dates(analysis_data)
                
                self.db_storage.save_analysis_result(case_number, analysis_data, mode)
                
                # Log detailed analysis result
                case_type = result.get('type', 'Unknown')
                case_status = result.get('status', 'Unknown')
                method = result.get('method', 'hybrid')
                confidence = result.get('confidence', 'unknown')
                logger.info(f"✅ {case_number}: {case_type} | {case_status} | Method: {method} | Confidence: {confidence}")
                
            except Exception as e:
                logger.warning(f"Failed to store analysis for {case_number}: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing case: {e}")
            return None
    
    def analyze_batch(self, case_numbers: List[str], mode: str = "llm") -> Dict[str, List[Dict[str, Any]]]:
        """Analyze a batch of cases and group by status.
        
        Args:
            case_numbers: List of case numbers to analyze
            mode: Analysis mode ('llm' or 'rule')
            
        Returns:
            Dictionary with status as keys and lists of case data as values
        """
        results_by_status = {}
        
        logger.info(f"Starting batch analysis of {len(case_numbers)} cases using {mode} mode")
        logger.info(f"Analysis mode: {'Force reanalysis enabled' if mode == 'llm' else 'Rule-based analysis'}")
        
        for case_number in tqdm(case_numbers, desc="Analyzing cases"):
            logger.info(f"🔄 Processing {case_number}...")
            # Get case data
            case_data = self.get_case_data(case_number)
            if not case_data:
                continue
            
            # Analyze case (force reanalysis for all cases)
            analysis_result = self.analyze_case(case_data, mode, force_reanalyze=True)
            if not analysis_result:
                continue
            
            # Get analysis data from database for consistent format
            # Try both rule and llm modes since hybrid mode may store as either
            stored_analysis = self.db_storage.is_analyzed(case_number, mode)
            if not stored_analysis:
                stored_analysis = self.db_storage.is_analyzed(case_number, 'llm' if mode == 'rule' else 'rule')
            if not stored_analysis:
                logger.warning(f"No stored analysis found for {case_number}")
                continue
            
            # Use the stored analysis status for grouping
            status = stored_analysis.get('case_status', 'Unknown')
            if status not in results_by_status:
                results_by_status[status] = []
            
            # Format case data to match existing JSON structure
            formatted_case = {
                "case_number": case_number,
                "analysis_result": stored_analysis,
                "raw_case_info": case_data,
                "docket_entries": case_data.get('docket_entries', [])
            }
            
            results_by_status[status].append(formatted_case)
        
        return results_by_status
    
    def generate_summary(self, cases_by_status: Dict[str, List[Dict[str, Any]]], 
                        status: str) -> Dict[str, Any]:
        """Generate summary statistics for a specific status group.
        
        Args:
            cases_by_status: Dictionary of cases grouped by status
            status: The status to generate summary for
            
        Returns:
            Summary dictionary
        """
        cases = cases_by_status.get(status, [])
        
        if not cases:
            return {
                'total_cases': 0,
                'case_number_list': '',
                'age_of_case_avg': None,
                'reply_to_outcome_time_avg': None
            }
        
        total_cases = len(cases)
        case_numbers = [case['case_number'] for case in cases]
        case_number_list = ','.join(case_numbers)
        
        # Calculate averages from analysis results
        age_values = []
        rto_values = []
        
        for case in cases:
            analysis = case.get('analysis_result', {})
            if analysis.get('age_of_case') is not None:
                age_values.append(float(analysis['age_of_case']))
            if analysis.get('reply_to_outcome_time') is not None:
                rto_values.append(float(analysis['reply_to_outcome_time']))
        
        age_avg = sum(age_values) / len(age_values) if age_values else None
        rto_avg = sum(rto_values) / len(rto_values) if rto_values else None
        
        return {
            'total_cases': total_cases,
            'case_number_list': case_number_list,
            'age_of_case_avg': round(age_avg, 1) if age_avg else None,
            'reply_to_outcome_time_avg': round(rto_avg, 1) if rto_avg else None
        }
    
    def save_results(self, results_by_status: Dict[str, List[Dict[str, Any]]], 
                    output_filename: str = None) -> str:
        """Save analysis results to JSON file.
        
        Args:
            results_by_status: Dictionary of cases grouped by status
            output_filename: Optional custom output filename
            
        Returns:
            Path to the saved file
        """
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"batch_analysis_results_{timestamp}.json"
        
        if not output_filename:
            output_filename = "batch_analysis_results.json"
        
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Generate final output structure
        output_data = {}
        
        for status, cases in results_by_status.items():
            if cases:  # Only include statuses that have cases
                summary = self.generate_summary(results_by_status, status)
                output_data[status] = {
                    'summary': summary,
                    'cases': cases
                }
        
        # Serialize all date objects in the output data
        output_data = serialize_dates(output_data)
        
        # Save to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Results saved to: {output_path}")
        return output_path


def main():
    """Main function to run the batch analyzer."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch analyze FCT cases from a text file')
    parser.add_argument('input_file', help='Text file containing comma-separated case numbers')
    parser.add_argument('--mode', choices=['llm', 'rule'], default='llm', 
                       help='Analysis mode (default: llm)')
    parser.add_argument('--output', help='Output filename (optional)')
    parser.add_argument('--db-connection', help='Database connection string (optional)')
    
    args = parser.parse_args()
    
    # Setup logging with file output
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/batch_analysis.log"
    
    setup_logging(
        log_level="INFO",
        log_file=log_file
    )
    
    # Initialize analyzer
    analyzer = BatchCaseAnalyzer(args.db_connection)
    
    # Read case numbers
    try:
        case_numbers = analyzer.read_case_numbers(args.input_file)
        logger.info(f"Read {len(case_numbers)} case numbers from {args.input_file}")
        
        if not case_numbers:
            logger.error("No case numbers found in input file")
            return 1
            
    except Exception as e:
        logger.error(f"Failed to read input file: {e}")
        return 1
    
    # Analyze cases
    try:
        results_by_status = analyzer.analyze_batch(case_numbers, args.mode)
        
        if not results_by_status:
            logger.error("No cases were successfully analyzed")
            return 1
        
        # Print detailed summary
        total_cases = sum(len(cases) for cases in results_by_status.values())
        logger.info("="*60)
        logger.info(f"🎉 BATCH ANALYSIS COMPLETED SUCCESSFULLY!")
        logger.info("="*60)
        logger.info(f"📊 Total cases analyzed: {total_cases}")
        logger.info(f"📋 Analysis mode: {args.mode}")
        logger.info(f"🔄 Force reanalysis: ENABLED")
        logger.info("")
        logger.info("📈 Results by status:")
        for status, cases in results_by_status.items():
            case_list = [c['case_number'] for c in cases[:5]]  # Show first 5 case numbers
            more_text = f" +{len(cases)-5} more" if len(cases) > 5 else ""
            logger.info(f"  ✅ {status}: {len(cases)} cases (e.g., {', '.join(case_list)}{more_text})")
        logger.info("="*60)
        
        # Save results
        output_path = analyzer.save_results(results_by_status, args.output)
        logger.info(f"Results saved to: {output_path}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())