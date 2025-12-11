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
from . import database as _database
from . import db_schema as _db_schema
from . import utils as _utils
from . import nlp_engine as _nlp_engine


def _compute_detailed_statistics(df: pd.DataFrame, year_filter: Optional[int] = None) -> dict:
    """Compute detailed statistics by case type and status."""
    from loguru import logger
    
    # Filter by year if specified
    if year_filter:
        # Try to extract year from filing_date
        df_filtered = df.copy()
        
        if 'filing_date' in df.columns:
            # Convert filing_date to datetime if it's not already
            df_filtered['filing_date_parsed'] = pd.to_datetime(df_filtered['filing_date'], errors='coerce')
            # Filter by year
            df_filtered = df_filtered[df_filtered['filing_date_parsed'].dt.year == year_filter]
            logger.info(f"Filtered to {len(df_filtered)} cases from year {year_filter}")
        elif 'case_number' in df.columns:
            # Try to extract year from case number (e.g., IMM-123-22)
            year_suffix = f"-{year_filter % 100:02d}"
            df_filtered = df_filtered[df_filtered['case_number'].str.endswith(year_suffix, na=False)]
            logger.info(f"Filtered to {len(df_filtered)} cases with case number ending in {year_suffix}")
        else:
            logger.warning(f"Cannot filter by year {year_filter}: no filing_date or case_number column found")
    else:
        df_filtered = df
    
    stats = {
        "overall": {
            "total_cases": len(df_filtered),
            "by_type": {},
            "by_status": {},
            "by_type_status": {}
        }
    }
    
    if year_filter:
        stats["year_filter"] = int(year_filter)
        stats["original_total_cases"] = int(len(df))
    
    # Overall statistics by type
    if 'type' in df_filtered.columns:
        type_counts = df_filtered['type'].value_counts().to_dict()
        stats["overall"]["by_type"] = type_counts
    
    # Overall statistics by status  
    if 'status' in df_filtered.columns:
        status_counts = df_filtered['status'].value_counts().to_dict()
        stats["overall"]["by_status"] = status_counts
    
    # Cross-tabulation: type vs status
    if 'type' in df_filtered.columns and 'status' in df_filtered.columns:
        cross_tab = pd.crosstab(df_filtered['type'], df_filtered['status'])
        stats["overall"]["by_type_status"] = cross_tab.to_dict()
    
    # Duration statistics by type and status
    duration_cols = ['time_to_close', 'age_of_case', 'rule9_wait']
    for col in duration_cols:
        if col in df_filtered.columns:
            stats[f"{col}_stats"] = {
                "overall": {
                    "mean": float(df_filtered[col].mean()) if not df_filtered[col].isna().all() else None,
                    "median": float(df_filtered[col].median()) if not df_filtered[col].isna().all() else None,
                    "min": float(df_filtered[col].min()) if not df_filtered[col].isna().all() else None,
                    "max": float(df_filtered[col].max()) if not df_filtered[col].isna().all() else None,
                    "count": int(df_filtered[col].notna().sum())
                }
            }
            
            # By type
            if 'type' in df_filtered.columns:
                by_type = {}
                for case_type in df_filtered['type'].dropna().unique():
                    type_data = df_filtered[df_filtered['type'] == case_type][col]
                    if not type_data.isna().all():
                        by_type[case_type] = {
                            "mean": float(type_data.mean()),
                            "median": float(type_data.median()),
                            "min": float(type_data.min()),
                            "max": float(type_data.max()),
                            "count": int(type_data.notna().sum())
                        }
                stats[f"{col}_stats"]["by_type"] = by_type
            
            # By status
            if 'status' in df_filtered.columns:
                by_status = {}
                for status in df_filtered['status'].dropna().unique():
                    status_data = df_filtered[df_filtered['status'] == status][col]
                    if not status_data.isna().all():
                        by_status[status] = {
                            "mean": float(status_data.mean()),
                            "median": float(status_data.median()),
                            "min": float(status_data.min()),
                            "max": float(status_data.max()),
                            "count": int(status_data.notna().sum())
                        }
                stats[f"{col}_stats"]["by_status"] = by_status
    
    # Visa office statistics
    if 'visa_office' in df_filtered.columns:
        visa_office_counts = df_filtered['visa_office'].value_counts().head(20).to_dict()
        stats["visa_office_stats"] = {
            "top_offices": visa_office_counts,
            "total_with_visa_office": int(df_filtered['visa_office'].notna().sum())
        }
        
        # Duration by visa office
        for col in duration_cols:
            if col in df_filtered.columns and df_filtered['visa_office'].notna().sum() > 0:
                office_duration = df_filtered.groupby('visa_office')[col].agg(['mean', 'median', 'count']).dropna()
                stats[f"{col}_stats"]["by_visa_office"] = office_duration.to_dict()
    
    return stats


def _log_final_results(output_dir: Path, details_path: Path, summary_path: Path, 
                      stats_path: Path, detailed_stats: dict) -> None:
    """Log final results including generated files and key statistics."""
    from loguru import logger
    
    logger.info("=" * 60)
    logger.info("ANALYSIS COMPLETED - FINAL RESULTS")
    logger.info("=" * 60)
    
    # Log generated files
    logger.info(f"📁 Output directory: {output_dir}")
    logger.info(f"📄 Details file: {details_path}")
    logger.info(f"📊 Summary file: {summary_path}")
    logger.info(f"📈 Statistics file: {stats_path}")
    
    # Log key statistics
    overall = detailed_stats.get("overall", {})
    total_cases = overall.get("total_cases", 0)
    
    # Log year filter information if applicable
    if "year_filter" in detailed_stats:
        year = detailed_stats["year_filter"]
        original_total = detailed_stats.get("original_total_cases", 0)
        logger.info(f"📅 Year filter applied: {year}")
        logger.info(f"📋 Original total cases: {original_total}")
        logger.info(f"📋 Cases from {year}: {total_cases}")
    else:
        logger.info(f"📋 Total cases analyzed: {total_cases}")
    
    # By case type
    by_type = overall.get("by_type", {})
    if by_type:
        logger.info("🏷️  Cases by type:")
        for case_type, count in by_type.items():
            percentage = (count / total_cases) * 100 if total_cases > 0 else 0
            logger.info(f"   {case_type}: {count} ({percentage:.1f}%)")
    
    # By case status
    by_status = overall.get("by_status", {})
    if by_status:
        logger.info("📊 Cases by status:")
        for status, count in by_status.items():
            percentage = (count / total_cases) * 100 if total_cases > 0 else 0
            logger.info(f"   {status}: {count} ({percentage:.1f}%)")
    
    # Type vs Status cross-tabulation
    by_type_status = overall.get("by_type_status", {})
    if by_type_status:
        logger.info("📈 Case Type vs Status breakdown:")
        for case_type, status_dict in by_type_status.items():
            logger.info(f"   {case_type}:")
            for status, count in status_dict.items():
                logger.info(f"     {status}: {count}")
    
    # Duration statistics
    for duration_type in ['time_to_close_stats', 'age_of_case_stats', 'rule9_wait_stats']:
        if duration_type in detailed_stats:
            duration_stats = detailed_stats[duration_type].get("overall", {})
            if duration_stats.get("count", 0) > 0:
                name = duration_type.replace('_stats', '').replace('_', ' ').title()
                logger.info(f"⏱️  {name} statistics:")
                logger.info(f"   Mean: {duration_stats.get('mean', 0):.1f} days")
                logger.info(f"   Median: {duration_stats.get('median', 0):.1f} days")
                logger.info(f"   Range: {duration_stats.get('min', 0):.0f} - {duration_stats.get('max', 0):.0f} days")
                logger.info(f"   Count: {duration_stats.get('count', 0)} cases")
    
    # Visa office statistics
    visa_stats = detailed_stats.get("visa_office_stats", {})
    if visa_stats and visa_stats.get("top_offices"):
        logger.info(f"🌍 Top visa offices:")
        for office, count in list(visa_stats["top_offices"].items())[:10]:
            logger.info(f"   {office}: {count} cases")
    
    # LLM analysis statistics (if available)
    llm_stats = detailed_stats.get("llm_stats", {})
    if llm_stats:
        logger.info("🤖 LLM Analysis Statistics:")
        logger.info(f"   Total processed: {llm_stats.get('total_processed', 0)}")
        logger.info(f"   LLM API calls: {llm_stats.get('llm_calls', 0)}")
        logger.info(f"   Rule-based only: {llm_stats.get('rule_based_only', 0)}")
        logger.info(f"   Hybrid method: {llm_stats.get('hybrid_method', 0)}")
        logger.info(f"   Entities extracted: {llm_stats.get('entities_extracted', 0)}")
        logger.info(f"   Processing errors: {llm_stats.get('errors', 0)}")
        
        # Calculate and show hybrid method percentage
        total = llm_stats.get('total_processed', 0)
        hybrid = llm_stats.get('hybrid_method', 0)
        if total > 0:
            hybrid_percentage = (hybrid / total) * 100
            logger.info(f"   Hybrid method usage: {hybrid_percentage:.1f}%")
    
    # File sizes
    try:
        for file_path in [details_path, summary_path, stats_path]:
            if file_path.exists():
                size_kb = file_path.stat().st_size / 1024
                logger.info(f"📏 {file_path.name}: {size_kb:.1f} KB")
    except Exception as e:
        logger.warning(f"Could not determine file sizes: {e}")
    
    logger.info("=" * 60)
    logger.info("✅ Analysis completed successfully!")
    logger.info("=" * 60)


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
    logger.info(f"Input format: {input_format}")
    logger.info(f"Log file: {log_file}")
    
    # Initialize database managers if using database
    db_storage = None
    db_manager = None
    if input_format == "database":
        db_storage = _db_schema.AnalysisResultStorage()
        db_manager = _db_schema.AnalysisDBManager()
        
        # Ensure database schema is up to date
        if not db_manager.migrate_database():
            logger.error("Failed to migrate database schema")
            return 1

    # Perform analysis
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

    # Perform analysis
    types = []
    statuses = []
    visa_offices = []
    judges = []
    
    # Track LLM usage statistics
    llm_stats = {
        'total_processed': 0,
        'llm_calls': 0,
        'rule_based_only': 0,
        'hybrid_method': 0,
        'errors': 0,
        'entities_extracted': 0
    }
    
    # Add progress tracking
    total_cases = len(df)
    logger.info("=" * 60)
    logger.info(f"🚀 STARTING ANALYSIS - Mode: {mode.upper()}")
    logger.info(f"📊 Total cases to analyze: {total_cases}")
    logger.info(f"📁 Output directory: {output_dir}")
    if year:
        logger.info(f"📅 Year filter: {year}")
    if mode == "llm":
        logger.info(f"🤖 LLM analysis enabled with fallback")
        if Config.get_ollama_model():
            logger.info(f"🎯 Configured model: {Config.get_ollama_model()}")
        else:
            logger.info(f"🔍 Will auto-detect running model")
    logger.info("=" * 60)
    
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
                
                # Use enhanced NLP engine (rule-based + LLM fallback)
                if mode == "llm":
                    # Use the hybrid NLP engine
                    logger.debug(f"🔍 Processing case {case_id} with LLM-enhanced analysis")
                    llm_stats['total_processed'] += 1
                    
                    # Initialize variables to ensure they're always defined
                    case_type = None
                    case_status = None
                    visa_office = None
                    judge = None
                    method = None
                    confidence = None
                    
                    try:
                        res = _nlp_engine.classify_case_enhanced(raw_case, use_llm_fallback=True)
                        case_type = res.get("type")
                        case_status = res.get("status")
                        visa_office = res.get("visa_office")
                        judge = res.get("judge")
                        method = res.get("method", "hybrid")
                        confidence = res.get("confidence", "medium")
                        
                        # Update statistics
                        if method == "hybrid":
                            llm_stats['llm_calls'] += 1
                            llm_stats['hybrid_method'] += 1
                        else:
                            llm_stats['rule_based_only'] += 1
                        
                        if visa_office or judge:
                            llm_stats['entities_extracted'] += 1
                        
                        logger.info(f"📊 Case {case_id}: {case_type} | {case_status} | Method: {method} | Confidence: {confidence}")
                        if visa_office or judge:
                            logger.debug(f"📍 Case {case_id} entities - Visa: {visa_office}, Judge: {judge}")
                    
                    except Exception as e:
                        llm_stats['errors'] += 1
                        logger.error(f"💥 Error processing case {case_id}: {e}")
                        # Fallback to rule-based
                        res = _rules.classify_case_rule(raw_case)
                        case_type = res.get("type")
                        case_status = res.get("status")
                        visa_office = None
                        judge = None
                        method = "rule_fallback"
                        confidence = "low"
                        
                else:
                    # Rule-based mode only - no entity extraction
                    logger.debug(f"🔍 Processing case {case_id} with rule-based analysis")
                    res = _rules.classify_case_rule(raw_case)
                    case_type = res.get("type")
                    case_status = res.get("status")
                    visa_office = None
                    judge = None
                    method = "rule_based"
                    logger.debug(f"📊 Case {case_id}: {case_type} | {case_status} | Method: rule_based")
                
                # Checkpoint results for resumability (only in LLM mode)
                if mode == "llm" and checkpoint_path and case_id:
                    _utils.write_checkpoint(checkpoint_path, {
                        "case_number": case_id, 
                        "type": case_type,
                        "status": case_status,
                        "visa_office": visa_office, 
                        "judge": judge,
                        "method": method,
                        "confidence": confidence
                    })
                
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
                    
                    # Log progress every 50 cases (more frequent for better visibility)
                    if current_count % 50 == 0:
                        progress_pct = (current_count / total_cases) * 100
                        logger.info(f"📈 Progress: {current_count}/{total_cases} ({progress_pct:.1f}%) cases processed")
                        
                        # Log LLM statistics every 100 cases
                        if mode == "llm" and current_count % 100 == 0:
                            llm_call_rate = (llm_stats['llm_calls'] / llm_stats['total_processed']) * 100 if llm_stats['total_processed'] > 0 else 0
                            entity_rate = (llm_stats['entities_extracted'] / llm_stats['total_processed']) * 100 if llm_stats['total_processed'] > 0 else 0
                            logger.info(f"🤖 LLM Stats: {llm_stats['llm_calls']}/{llm_stats['total_processed']} calls ({llm_call_rate:.1f}%), "
                                      f"{llm_stats['entities_extracted']} entities extracted ({entity_rate:.1f}%), {llm_stats['errors']} errors")
    
    # Close progress bar
    pbar.close()
    logger.info(f"✅ Analysis completed for {total_cases} cases")
    
    # Log final LLM statistics if LLM mode was used
    if mode == "llm" and llm_stats['total_processed'] > 0:
        logger.info("=" * 60)
        logger.info("🤖 LLM ANALYSIS STATISTICS")
        logger.info("=" * 60)
        logger.info(f"📊 Total processed: {llm_stats['total_processed']}")
        logger.info(f"🤖 LLM calls made: {llm_stats['llm_calls']}")
        logger.info(f"📏 Rule-based only: {llm_stats['rule_based_only']}")
        logger.info(f"🔄 Hybrid method: {llm_stats['hybrid_method']}")
        logger.info(f"📍 Entities extracted: {llm_stats['entities_extracted']}")
        logger.info(f"💥 Errors: {llm_stats['errors']}")
        
        if llm_stats['total_processed'] > 0:
            llm_call_rate = (llm_stats['llm_calls'] / llm_stats['total_processed']) * 100
            entity_rate = (llm_stats['entities_extracted'] / llm_stats['total_processed']) * 100
            error_rate = (llm_stats['errors'] / llm_stats['total_processed']) * 100
            
            logger.info(f"📈 LLM call rate: {llm_call_rate:.1f}%")
            logger.info(f"📍 Entity extraction rate: {entity_rate:.1f}%")
            logger.info(f"💥 Error rate: {error_rate:.1f}%")
        
        logger.info("=" * 60)
    
    # Add analysis results to DataFrame
    df["type"] = types
    df["status"] = statuses
    if visa_offices:
        df["visa_office"] = visa_offices
    if judges:
        df["judge"] = judges

    # Compute duration metrics
    df2 = _metrics.compute_durations(df)

    # Compute detailed statistics by case type and status
    detailed_stats = _compute_detailed_statistics(df2, year_filter=year)
    
    # Add LLM statistics if in LLM mode
    if mode == "llm" and 'llm_stats' in locals():
        detailed_stats["llm_stats"] = llm_stats
    
    # Export results
    details_path = output_dir / "federal_cases_0005_details.csv"
    summary_path = output_dir / "federal_cases_0005_summary.json"
    stats_path = output_dir / "federal_cases_0005_statistics.json"
    
    _export.write_case_details(df2, str(details_path))
    
    # Include database statistics if available
    if db_storage:
        stats = db_storage.get_analysis_statistics()
        summary = {
            "total_cases": int(len(df2)),
            "rows": int(len(df2)),
            "database_stats": stats,
            "detailed_statistics": detailed_stats
        }
    else:
        summary = {
            "total_cases": int(len(df2)), 
            "rows": int(len(df2)),
            "detailed_statistics": detailed_stats
        }
    
    _export.write_summary(summary, str(summary_path))
    _export.write_summary(detailed_stats, str(stats_path))
    
    # Log final results
    _log_final_results(output_dir, details_path, summary_path, stats_path, detailed_stats)

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
    
    # Analysis options
    p.add_argument("--mode", choices=("rule", "llm"), help="Analysis mode")
    p.add_argument("--year", type=int, help="Filter by year (for database/directory input)")
    p.add_argument("--skip-analyzed", action=argparse.BooleanOptionalAction, default=None,
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
    )


if __name__ == "__main__":
    raise SystemExit(main())