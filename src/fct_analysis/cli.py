"""Clean CLI implementation for fct_analysis.

Enhanced to support database and year-based directory structure as data sources.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from tqdm import tqdm

from lib.config import Config
from lib.logging_config import setup_logging
from . import parser as _parser
from . import rules as _rules
from . import metrics as _metrics
from . import export as _export
from . import heuristics as _heuristics
from . import llm as _llm
from . import database as _database
from . import db_schema as _db_schema
from . import utils as _utils
from . import database as _database
from . import db_schema as _db_schema


def analyze(
    input_path: Optional[str] = None,
    mode: Optional[str] = None,
    output_dir: Optional[str | Path] = None,
    resume: bool = False,
    sample_audit: Optional[int] = None,
    ollama_url: Optional[str] = None,
    input_format: Optional[str] = None,
    year: Optional[int] = None,
    skip_analyzed: Optional[bool] = None,
    update_mode: Optional[str] = None,
    from_db: bool = False,
) -> int:
    """Analyze FCT cases with flexible data source support.
    
    Args:
        input_path: Override file path (for file-based input)
        mode: Analysis mode ('rule' or 'llm')
        output_dir: Output directory
        resume: Resume LLM processing from checkpoint
        sample_audit: Number of LLM samples to audit
        ollama_url: Custom Ollama URL
        input_format: Data source format ('database', 'directory', 'file')
        year: Filter by year (for database or directory input)
        skip_analyzed: Skip already analyzed cases
        update_mode: How to handle analyzed cases ('smart', 'force', 'skip')
        from_db: Read analysis results directly from database (skip analysis)
    """
    # Use config defaults if not provided
    mode = mode or Config.get_analysis_mode()
    sample_audit = sample_audit if sample_audit is not None else Config.get_analysis_sample_audit()
    ollama_url = ollama_url or Config.get_ollama_url()
    input_format = input_format or Config.get_analysis_input_format()
    skip_analyzed = skip_analyzed if skip_analyzed is not None else Config.get_analysis_skip_analyzed()
    update_mode = update_mode or Config.get_analysis_update_mode()
    
    # Setup output directory
    if output_dir is None:
        output_dir = Config.get_analysis_output_path("")
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup logging with file output using config
    log_file = Config.get_analysis_log_file()
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    
    setup_logging(
        log_level=Config.get_analysis_log_level(),
        log_file=log_file,
        log_base=Config.get_analysis_log_base(),
        max_index=Config.get_analysis_log_max_index()
    )
    from loguru import logger
    logger.info(f"Starting FCT analysis with mode: {mode}")
    logger.info(f"Input format: {input_format}, From database: {from_db}")
    logger.info(f"Log file: {log_file}")
    
    # Initialize database managers if using database
    db_storage = None
    db_manager = None
    if input_format == "database" or from_db:
        db_storage = _db_schema.AnalysisResultStorage()
        db_manager = _db_schema.AnalysisDBManager()
        
        # Ensure database schema is up to date
        if not db_manager.migrate_database():
            logger.error("Failed to migrate database schema")
            return 1

    # Handle different analysis modes
    if from_db:
        # Read already analyzed results from database
        if not db_storage:
            logger.error("Database storage not initialized")
            return 1
            
        analyzed_cases = db_storage.get_analyzed_cases(mode)
        if not analyzed_cases:
            logger.info("No analyzed cases found in database")
            return 0
            
        # Convert to DataFrame format for export
        rows = []
        for case in analyzed_cases:
            filing_date = case.get('filing_date')
            docket_entries = case.get('docket_entries') or []
            
            # Build row similar to parser output
            row = {
                'case_number': case.get('case_number'),
                'filing_date': filing_date,
                'docket_entries': docket_entries,
                'raw': case,  # Full case data
                'type': case.get('case_type'),
                'status': case.get('case_status'),
                'visa_office': case.get('visa_office'),
                'judge': case.get('judge'),
                'time_to_close': case.get('time_to_close'),
                'age_of_case': case.get('age_of_case'),
                'rule9_wait': case.get('rule9_wait'),
                'outcome_date': case.get('outcome_date'),
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        logger.info(f"Loaded {len(df)} analyzed cases from database")
        
    else:
        # Perform new analysis
        # Get data from configured source
        if input_format == "file" and input_path:
            # Traditional file-based input
            df = _parser.parse_cases(input_path)
        else:
            # Database or directory-based input
            try:
                if input_format == "directory":
                    # Use FileReader with year filter
                    file_reader = _database.FileReader()
                    cases = file_reader.read_directory(year)
                else:
                    cases = _database.get_data_source(input_format)
                    
                    # Filter by year if specified
                    if year and input_format == "database":
                        # Refetch with year filter
                        db_reader = _database.DatabaseReader()
                        cases = db_reader.fetch_cases(year=year)
                    elif year:
                        # Filter loaded cases by year
                        cases = [
                            case for case in cases 
                            if case.get('filing_date') and str(year) in case['filing_date']
                        ]
                
                # Convert to DataFrame using parser logic
                    df = _parser._parse_cases_list(cases)
                    
            except Exception as e:
                logger.error(f"Failed to load data from {input_format}: {e}")
                if input_path:
                    logger.info(f"Falling back to file input: {input_path}")
                    df = _parser.parse_cases(input_path)
                else:
                    raise

    # Setup resume checkpoint and audit logging
    checkpoint_path = output_dir / Config.get_analysis_checkpoint_file()
    processed = set()
    if resume and checkpoint_path.exists():
        try:
            with checkpoint_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        obj = __import__("json").loads(line)
                        if obj and isinstance(obj, dict) and obj.get("case_number"):
                            processed.add(obj.get("case_number"))
                    except Exception:
                        continue
        except Exception:
            processed = set()

    samples_written = 0
    audit_failures = Path(Config.get_analysis_audit_failures_file())
    audit_failures.parent.mkdir(parents=True, exist_ok=True)

    # Only perform analysis if not loading from database
    if not from_db:
        types = []
        statuses = []
        visa_offices = []
        judges = []
        
        # Add progress tracking
        total_cases = len(df)
        logger.info("Starting analysis of {} cases", total_cases)
        
        # Process each case with database storage support and progress bar
        with tqdm(total=total_cases, desc="Analyzing cases", unit="case") as pbar:
            for idx, row in df.iterrows():
                case_id = row.get("case_number") or row.get("caseNumber") or row.get("case_id")
                raw_case = row.get("raw") or row.to_dict() if hasattr(row, 'to_dict') else row
                
                # Check if already analyzed in analysis table
                existing_analysis = None
                if skip_analyzed and db_storage and case_id:
                    existing_analysis = db_storage.is_analyzed(case_id, mode)
                    if existing_analysis and update_mode == "skip":
                        # Use existing analysis results
                        types.append(existing_analysis.get('case_type'))
                        statuses.append(existing_analysis.get('case_status'))
                        visa_offices.append(existing_analysis.get('visa_office'))
                        judges.append(existing_analysis.get('judge'))
                        logger.debug(f"Skipping analysis for {case_id} (already analyzed)")
                        pbar.update(1)
                        continue
                    elif existing_analysis and update_mode == "smart":
                        logger.info(f"Case {case_id} already analyzed, updating if needed")
                
                # Perform rule-based analysis
                res = _rules.classify_case_rule(raw_case)
                case_type = res.get("type")
                case_status = res.get("status")
                
                # LLM mode: try heuristics first, then LLM if missing
                visa_office = None
                judge = None
                
                if mode == "llm":
                    # Build searchable text from case data
                    text_parts = []
                    if isinstance(raw_case, dict):
                        # Add title/style_of_cause
                        title = raw_case.get("title") or raw_case.get("style_of_cause", "")
                        if title:
                            text_parts.append(title)
                        
                        # Add docket entries summaries
                        docket_entries = raw_case.get("docket_entries", [])
                        if isinstance(docket_entries, list):
                            for entry in docket_entries:
                                if isinstance(entry, dict):
                                    summary = entry.get("summary", "")
                                    if summary:
                                        text_parts.append(summary)
                        
                        # Add other potentially useful fields
                        for field in ["office", "court"]:
                            value = raw_case.get(field, "")
                            if value:
                                text_parts.append(value)
                    
                    text = " ".join(text_parts)
                    visa_office = _heuristics.extract_visa_office_heuristic(text)
                    judge = _heuristics.extract_judge_heuristic(text)
                    
                    if not visa_office or not judge:
                        # check resume
                        if resume and checkpoint_path.exists() and case_id:
                            processed_case = None
                            try:
                                with checkpoint_path.open("r", encoding="utf-8") as fh:
                                    for line in fh:
                                        try:
                                            obj = __import__("json").loads(line)
                                            if obj and isinstance(obj, dict) and obj.get("case_number") == case_id:
                                                processed_case = obj
                                                break
                                        except Exception:
                                            continue
                            except Exception:
                                pass
                            
                            if processed_case:
                                visa_office = visa_office or processed_case.get("visa_office")
                                judge = judge or processed_case.get("judge")
                        
                        if not visa_office or not judge:
                            try:
                                llm_out = _llm.extract_entities_with_ollama(text, ollama_url=ollama_url)
                                if llm_out:
                                    visa_office = visa_office or llm_out.get("visa_office")
                                    judge = judge or llm_out.get("judge")
                                    
                                    # checkpoint the LLM output for this case
                                    if checkpoint_path and case_id:
                                        _utils.write_checkpoint(checkpoint_path, {
                                            "case_number": case_id, 
                                            "visa_office": visa_office, 
                                            "judge": judge
                                        })
                                    
                                    # optionally write sample audit entries
                                    if sample_audit and samples_written < sample_audit:
                                        _utils.write_checkpoint(Path(Config.get_analysis_audit_samples_file()), {
                                            "case_number": case_id, 
                                            "llm": llm_out
                                        })
                                        samples_written += 1
                            except ConnectionError as exc:
                                # record failure to audit log
                                if checkpoint_path:
                                    _utils.write_checkpoint(audit_failures, {"case_number": case_id, "error": str(exc)})
                
                # Store results for current case
                types.append(case_type)
                statuses.append(case_status)
                visa_offices.append(visa_office)
                judges.append(judge)
                
                # Save analysis to dedicated analysis table
                if db_storage and case_id:
                    analysis_result = {
                        'type': case_type,
                        'status': case_status,
                        'visa_office': visa_office,
                        'judge': judge,
                        'title': raw_case.get('title'),
                        'court': raw_case.get('court'),
                        'filing_date': raw_case.get('filing_date')
                    }
                    success = db_storage.save_analysis_result(case_id, analysis_result, mode)
                    if not success:
                        logger.warning(f"Failed to save analysis result for {case_id}")
                    
                    # Update progress bar and log progress
                    pbar.update(1)
                    current_count = len(types)
                    if current_count % 100 == 0:
                        logger.info(f"Processed {current_count}/{total_cases} cases")
        
        # Close progress bar
        pbar.close()
        logger.info(f"Analysis completed for {total_cases} cases")
        
        # Add analysis results to DataFrame
        df["type"] = types
        df["status"] = statuses
        if visa_offices:
            df["visa_office"] = visa_offices
        if judges:
            df["judge"] = judges
    
    # Compute duration metrics
    df2 = _metrics.compute_durations(df)

    # Export results
    details_path = output_dir / "federal_cases_0005_details.csv"
    summary_path = output_dir / "federal_cases_0005_summary.json"
    _export.write_case_details(df2, str(details_path))
    
    # Include database statistics if available
    if db_storage:
        stats = db_storage.get_analysis_statistics()
        summary = {
            "total_cases": int(len(df2)),
            "rows": int(len(df2)),
            "database_stats": stats
        }
    else:
        summary = {"total_cases": int(len(df2)), "rows": int(len(df2))}
    
    _export.write_summary(summary, str(summary_path))

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser(prog="fct_analysis")
    
    # Input options
    input_group = p.add_mutually_exclusive_group()
    input_group.add_argument("--input", "-i", help="Input file path (for file mode)")
    input_group.add_argument("--input-format", choices=("database", "directory", "file"), 
                           help="Data source format (overrides config)")
    p.add_argument("--from-db", action="store_true", 
                   help="Load already analyzed results from database (skip analysis)")
    
    # Analysis options
    p.add_argument("--mode", choices=("rule", "llm"), help="Analysis mode")
    p.add_argument("--year", type=int, help="Filter by year (for database/directory input)")
    p.add_argument("--skip-analyzed", action="store_true", default=None,
                   help="Skip already analyzed cases")
    p.add_argument("--update-mode", choices=("smart", "force", "skip"), 
                   help="How to handle analyzed cases (smart/skip/force)")
    
    # Output options
    p.add_argument("--output-dir", "-o", help="Output directory")
    
    # LLM options
    p.add_argument("--resume", action="store_true", help="Resume LLM processing using checkpoint file")
    p.add_argument("--sample-audit", type=int, help="Write sample LLM outputs to audit file (N samples)")
    p.add_argument("--ollama-url", help="Custom Ollama base URL")
    
    # Database management
    p.add_argument("--migrate-db", action="store_true", 
                   help="Migrate database schema and exit")
    
    ns = p.parse_args(argv)
    
    # Handle database migration
    if ns.migrate_db:
        db_manager = _db_schema.AnalysisDBManager()
        if db_manager.migrate_database():
            print("Database migration completed successfully")
            return 0
        else:
            print("Database migration failed")
            return 1
    
    return analyze(
        input_path=ns.input,
        mode=ns.mode,
        output_dir=ns.output_dir,
        resume=ns.resume,
        sample_audit=ns.sample_audit,
        ollama_url=ns.ollama_url,
        input_format=ns.input_format,
        year=ns.year,
        skip_analyzed=ns.skip_analyzed,
        update_mode=ns.update_mode,
        from_db=ns.from_db,
    )


if __name__ == "__main__":
    raise SystemExit(main())