"""Clean CLI implementation for fct_analysis.

Enhanced to support database and year-based directory structure as data sources.
"""
from __future__ import annotations

import os
import sys
import re
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
from . import llm as _llm


def _extract_year_from_case_number(case_number: str) -> Optional[int]:
    """Extract year from case number like IMM-1-21 (for 2021).
    
    Args:
        case_number: Case number string (e.g., "IMM-12345-25")
        
    Returns:
        Year as integer, or None if cannot extract
    """
    if not case_number or not isinstance(case_number, str):
        return None
        
    # Pattern: IMM-XXX-YY where YY is last 2 digits of year
    match = re.search(r'IMM-\d+-(\d{2})', case_number.upper())
    if match:
        year_suffix = match.group(1)
        # Convert 2-digit year to 4-digit year (assuming 2000+ for 00-99)
        return 2000 + int(year_suffix)
    
    return None


def check_ollama_status(ollama_url: Optional[str] = None) -> int:
    """Check Ollama service status and display information.
    
    Args:
        ollama_url: Custom Ollama base URL
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    from loguru import logger
    
    logger.info("🔍 Checking Ollama service status...")
    logger.info("=" * 50)
    
    # Check basic availability
    if not _llm.check_service_availability():
        logger.error("❌ Ollama service is not available")
        logger.info("💡 Try starting Ollama with: ollama serve")
        return 1
    
    logger.info("✅ Ollama service is available")
    
    # Get running session count
    try:
        session_count = _llm.get_running_session_count(ollama_url)
        logger.info(f"📊 Active sessions: {session_count}")
        
        if session_count == 0:
            logger.info("✅ Ollama is currently idle")
        else:
            logger.info(f"⏳ Ollama is busy with {session_count} active session(s)")
        
        # Get running model info
        running_model = _llm.get_running_model(ollama_url)
        if running_model:
            logger.info(f"🤖 Running model: {running_model}")
        else:
            logger.info("ℹ️ No models currently loaded")
            
    except Exception as e:
        logger.warning(f"⚠️ Error checking session status: {e}")
    
    # Test idle check
    try:
        is_idle = _llm.is_ollama_idle(ollama_url)
        if is_idle:
            logger.info("✅ Ollama is ready for new requests")
        else:
            logger.info("⏳ Ollama is busy, new requests may need to wait")
    except Exception as e:
        logger.warning(f"⚠️ Error checking idle status: {e}")
    
    logger.info("=" * 50)
    return 0


def _compute_detailed_statistics(df: pd.DataFrame, year_filter: Optional[int] = None) -> dict:
    """Compute detailed statistics by case type and status."""
    from loguru import logger
    
    # Filter by year if specified
    df_filtered = df.copy()
    if year_filter:
        # Priority: use case_number first (more reliable), fallback to filing_date
        year_suffix = f"-{year_filter % 100:02d}"
        filtered_by_case_number = False
        
        if 'case_number' in df.columns:
            # Extract year from case number (e.g., IMM-123-22) - primary method
            case_mask = df_filtered['case_number'].str.endswith(year_suffix, na=False)
            df_filtered = df_filtered[case_mask]
            filtered_by_case_number = True
            logger.info(f"Primary filter: {len(df_filtered)} cases with case number ending in {year_suffix}")
        
        # Fallback: use filing_date if case_number filtering didn't work or no results
        if (len(df_filtered) == 0 or not filtered_by_case_number) and 'filing_date' in df.columns:
            # Convert filing_date to datetime if it's not already
            df_temp = df.copy()
            df_temp['filing_date_parsed'] = pd.to_datetime(df_temp['filing_date'], errors='coerce')
            # Filter by year
            filing_mask = df_temp['filing_date_parsed'].dt.year == year_filter
            df_filtered = df_temp[filing_mask]
            logger.info(f"Fallback filter: {len(df_filtered)} cases from filing_date year {year_filter}")
        
        if len(df_filtered) == 0:
            logger.warning(f"No cases found for year {year_filter} using either case_number or filing_date")
        
        logger.info(f"Final filtered to {len(df_filtered)} cases for year {year_filter}")
    
    # If no year filter, use all data
    else:
        logger.info(f"No year filter applied, using all {len(df_filtered)} cases")
    
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
    
    # Year distribution analysis (shows reliability of year extraction methods)
    if 'case_number' in df_filtered.columns:
        year_distribution = {}
        for case_num in df_filtered['case_number'].dropna():
            extracted_year = _extract_year_from_case_number(str(case_num))
            if extracted_year:
                year_distribution[extracted_year] = year_distribution.get(extracted_year, 0) + 1
        
        if year_distribution:
            stats["year_distribution"] = dict(sorted(year_distribution.items()))
            logger.info(f"Year distribution from case numbers: {stats['year_distribution']}")
    
    # Filing date reliability check
    if 'filing_date' in df.columns and 'case_number' in df.columns:
        # Compare filing_date years vs case_number years
        filing_years = []
        case_number_years = []
        
        for _, row in df.iterrows():
            # From case_number
            cn_year = _extract_year_from_case_number(str(row.get('case_number', '')))
            
            # From filing_date
            fd = row.get('filing_date')
            fd_year = None
            if pd.notna(fd) and fd:
                try:
                    fd_year = pd.to_datetime(fd).year
                except:
                    pass
            
            if cn_year and fd_year:
                filing_years.append(fd_year)
                case_number_years.append(cn_year)
        
        if filing_years and case_number_years:
            match_count = sum(1 for f, c in zip(filing_years, case_number_years) if f == c)
            reliability = match_count / len(filing_years) * 100 if filing_years else 0
            stats["filing_date_reliability"] = {
                "total_comparable": len(filing_years),
                "matching_years": match_count,
                "reliability_percent": round(reliability, 1)
            }
            logger.info(f"Filing date reliability: {reliability:.1f}% match with case_number years")
    
    # Duration statistics by type and status
    duration_cols = ['time_to_close', 'age_of_case', 'rule9_wait', 'memo_response_time', 'memo_to_outcome_time', 'reply_memo_time', 'reply_to_outcome_time']
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





def _compute_case_durations(raw_case: dict | pd.Series, case_id: str = None, db_engine = None) -> dict:
    """Compute duration metrics for a single case.
    
    Args:
        raw_case: Raw case data dictionary
        case_id: Case number for database lookup
        db_engine: Database engine for querying docket_entries
        
    Returns:
        Dictionary with duration metrics
    """
    from datetime import datetime, timezone
    
    # Use timezone-aware UTC date for 'today'
    today_date = datetime.now(timezone.utc).date()
    
    # Helper to convert to date
    def _to_date(d):
        if d is None:
            return None
        try:
            return pd.to_datetime(d)
        except Exception:
            return None
    
    filing_date = _to_date(raw_case.get('filing_date'))
    
    # Age of case
    age_of_case = None
    if filing_date:
        try:
            age_of_case = int((today_date - filing_date.date()).days)
        except Exception:
            pass
    
    # Time to close
    time_to_close = None
    outcome_date = raw_case.get('outcome_date') or raw_case.get('decision_date')
    
    # If no outcome_date in raw_case, try to find it from docket_entries
    if not outcome_date and case_id and db_engine:
        try:
            from sqlalchemy import text
            with db_engine.connect() as conn:
                # Look for judgment, order, or discontinuance entries that indicate case closure
                docket_query = """
                SELECT date_filed, recorded_entry_summary
                FROM docket_entries 
                WHERE case_number = :case_id
                AND (
                    LOWER(recorded_entry_summary) LIKE '%judgment dated%'
                    OR LOWER(recorded_entry_summary) LIKE '%order dated%'
                    OR LOWER(recorded_entry_summary) LIKE '%discontinuance%'
                    OR LOWER(recorded_entry_summary) LIKE '%final decision%'
                )
                ORDER BY date_filed DESC
                LIMIT 1
                """
                result = conn.execute(text(docket_query), {"case_id": case_id}).fetchone()
                if result and result.date_filed:
                    outcome_date = result.date_filed
        except Exception:
            pass  # If database lookup fails, continue without outcome_date
    
    # Memo response time
    memo_response_time = None
    memo_to_outcome_time = None
    reply_memo_time = None
    reply_to_outcome_time = None
    first_memo_date = None
    first_reply_date = None
    doj_memo_date = None
    reply_memo_date = None
    
    # First try to extract from raw_case docket entries, then fallback to database
    if raw_case and 'docket_entries' in raw_case and raw_case['docket_entries']:
        docket_entries = raw_case['docket_entries']
        
        # Find first DOJ/IRCC memo
        for entry in docket_entries:
            if not entry:  # Skip None entries
                continue
            summary = entry.get('summary', entry.get('recorded_entry_summary', '')).lower() if entry.get('summary', entry.get('recorded_entry_summary', '')) else ''
            entry_date = entry.get('entry_date', entry.get('date_filed'))
            
            if not entry_date:
                continue
                
            # Check if this is a DOJ/IRCC memo (improved logic)
            if ( ('memorandum of argument' in summary and 'respondent' in summary) or
                 ('memorandum on behalf of the respondent' in summary and 'appearance' not in summary) or
                 ('respondent\'s memorandum' in summary and 'appearance' not in summary) or
                 ('memorandum' in summary and 'filed on behalf of the respondent' in summary and 'appearance' not in summary) or
                 ('letter from' in summary and any(term in summary for term in ['department of justice', 'attorney general'])) or
                 ('letter from' in summary and 'ircc' in summary and 'decision' in summary and 'no decision' not in summary) ):
                
                first_memo_date = _to_date(entry_date)
                doj_memo_date = entry_date
                if filing_date and first_memo_date:
                    try:
                        memo_response_time = int((first_memo_date - filing_date).days)
                    except Exception:
                        pass
                break
        
        # Find first applicant reply (after DOJ memo)
        if first_memo_date:
            for entry in docket_entries:
                if not entry:  # Skip None entries
                    continue
                summary = entry.get('summary', entry.get('recorded_entry_summary', '')).lower() if entry.get('summary', entry.get('recorded_entry_summary', '')) else ''
                entry_date = entry.get('entry_date', entry.get('date_filed'))
                
                if not entry_date:
                    continue
                    
                entry_dt = _to_date(entry_date)
                if entry_dt and entry_dt >= first_memo_date:
                    # Check if this is an applicant reply (improved logic)
                    if ( ('reply memorandum' in summary and 'applicant' in summary) or
                         ('reply to memorandum' in summary) or
                         ('response to memorandum' in summary) or
                         ('applicant\'s reply memorandum' in summary) or
                         ('counsel for applicant' in summary and any(term in summary for term in ['reply', 'response']) and 'memorandum' in summary) ):
                        
                        first_reply_date = entry_dt
                        reply_memo_date = entry_date
                        
                        # Calculate reply memo time
                        try:
                            reply_memo_time = int((first_reply_date - first_memo_date).days)
                        except Exception:
                            pass
                        
                        # Calculate reply to outcome time
                        if outcome_date:
                            outcome_dt = _to_date(outcome_date)
                            if outcome_dt:
                                try:
                                    reply_to_outcome_time = int((outcome_dt - first_reply_date).days)
                                except Exception:
                                    pass
                        break
        
        # Calculate memo to outcome time if we have both dates
        if outcome_date and first_memo_date:
            outcome_dt = _to_date(outcome_date)
            if outcome_dt:
                try:
                    memo_to_outcome_time = int((outcome_dt - first_memo_date).days)
                except Exception:
                    pass
    
    # Fallback to database if not found in raw data
    elif case_id and db_engine:
        try:
            from sqlalchemy import text
            with db_engine.connect() as conn:
                # Look for first DOJ/IRCC response memo (improved logic)
                memo_query = """
                SELECT de.date_filed, de.recorded_entry_summary
                FROM docket_entries de
                WHERE de.case_number = :case_id
                AND (
                    (LOWER(de.recorded_entry_summary) LIKE '%memorandum of argument%' AND LOWER(de.recorded_entry_summary) LIKE '%respondent%')
                    OR (LOWER(de.recorded_entry_summary) LIKE '%memorandum on behalf of the respondent%' AND LOWER(de.recorded_entry_summary) NOT LIKE '%appearance%')
                    OR (LOWER(de.recorded_entry_summary) LIKE '%respondent%''s memorandum%' AND LOWER(de.recorded_entry_summary) NOT LIKE '%appearance%')
                    OR (LOWER(de.recorded_entry_summary) LIKE '%memorandum%' AND LOWER(de.recorded_entry_summary) LIKE '%filed on behalf of the respondent%' AND LOWER(de.recorded_entry_summary) NOT LIKE '%appearance%')
                    OR (LOWER(de.recorded_entry_summary) LIKE '%letter from%' AND (
                        (LOWER(de.recorded_entry_summary) LIKE '%ircc%' AND LOWER(de.recorded_entry_summary) LIKE '%decision%' AND LOWER(de.recorded_entry_summary) NOT LIKE '%no decision%') OR
                        LOWER(de.recorded_entry_summary) LIKE '%department of justice%'
                    ))
                )
                ORDER BY de.date_filed ASC
                LIMIT 1
                """
                memo_result = conn.execute(text(memo_query), {"case_id": case_id}).fetchone()
                if memo_result and memo_result.date_filed:
                    first_memo_date = _to_date(memo_result.date_filed)
                    doj_memo_date = memo_result.date_filed
                    if filing_date and first_memo_date:
                        try:
                            memo_response_time = int((first_memo_date - filing_date).days)
                        except Exception:
                            pass
                            
                    # Calculate memo to outcome time if we have both dates
                    if outcome_date and first_memo_date:
                        outcome_dt = _to_date(outcome_date)
                        if outcome_dt:
                            try:
                                memo_to_outcome_time = int((outcome_dt - first_memo_date).days)
                            except Exception:
                                pass
        except Exception:
            pass  # If database lookup fails, continue without memo_response_time
    
    # Applicant reply time to DOJ memo
    if case_id and db_engine and first_memo_date:
        try:
            from sqlalchemy import text
            with db_engine.connect() as conn:
                # Look for first applicant response to DOJ memo (improved logic)
                reply_query = """
                SELECT de.date_filed, de.recorded_entry_summary
                FROM docket_entries de
                WHERE de.case_number = :case_id
                AND de.date_filed > :first_memo_date
                AND (
                    (LOWER(de.recorded_entry_summary) LIKE '%reply memorandum%' AND LOWER(de.recorded_entry_summary) LIKE '%applicant%')
                    OR (LOWER(de.recorded_entry_summary) LIKE '%reply to memorandum%')
                    OR (LOWER(de.recorded_entry_summary) LIKE '%response to memorandum%')
                    OR (LOWER(de.recorded_entry_summary) LIKE '%applicant%''s reply memorandum%')
                    OR (LOWER(de.recorded_entry_summary) LIKE '%counsel for applicant%' AND (
                        (LOWER(de.recorded_entry_summary) LIKE '%reply%' OR LOWER(de.recorded_entry_summary) LIKE '%response%')
                        AND LOWER(de.recorded_entry_summary) LIKE '%memorandum%'
                    ))
                )
                ORDER BY de.date_filed ASC
                LIMIT 1
                """
                reply_result = conn.execute(text(reply_query), {"case_id": case_id, "first_memo_date": first_memo_date}).fetchone()
                if reply_result and reply_result.date_filed:
                    first_reply_date = _to_date(reply_result.date_filed)
                    reply_memo_date = reply_result.date_filed
                    if first_reply_date:
                        try:
                            reply_memo_time = int((first_reply_date - first_memo_date).days)
                        except Exception:
                            pass
                    
                    # Calculate reply to outcome time
                    if outcome_date and first_reply_date:
                        outcome_dt = _to_date(outcome_date)
                        if outcome_dt:
                            try:
                                reply_to_outcome_time = int((outcome_dt - first_reply_date).days)
                            except Exception:
                                pass
        except Exception:
            pass  # If database lookup fails, continue without reply_memo_time
    
    if filing_date and outcome_date:
        outcome_dt = _to_date(outcome_date)
        if outcome_dt:
            try:
                time_to_close = int((outcome_dt - filing_date).days)
            except Exception:
                pass
    
    # Rule 9 wait
    rule9_wait = None
    if filing_date:
        import re
        RULE9_RE = re.compile(r"rule\s*9", re.I)
        for de in raw_case.get("docket_entries") or []:
            summary = de.get("summary") or ""
            if RULE9_RE.search(summary):
                entry_date = _to_date(de.get("entry_date"))
                if entry_date:
                    try:
                        rule9_wait = int((entry_date - filing_date).days)
                        break
                    except Exception:
                        pass
    
    return {
        'age_of_case': age_of_case,
        'time_to_close': time_to_close,
        'rule9_wait': rule9_wait,
        'outcome_date': outcome_date,
        'memo_response_time': memo_response_time,
        'memo_to_outcome_time': memo_to_outcome_time,
        'reply_memo_time': reply_memo_time,
        'reply_to_outcome_time': reply_to_outcome_time,
        # Actual datetime fields
        'doj_memo_date': doj_memo_date,
        'reply_memo_date': reply_memo_date
    }

def _format_case_analysis_log(case_id: str, case_data: dict, res: dict, durations: dict) -> str:
    """Format detailed case analysis results for logging."""
    import json
    lines = [
        f"🔍 Case Analysis: {case_id}",
        f"📋 Basic Info: {case_data.get('style_of_cause') or case_data.get('title')}",
        f"   Nature: {case_data.get('nature_of_proceeding')} | Office: {case_data.get('office')} | Language: {case_data.get('language')}",
        f"📅 Milestones: Filed: {case_data.get('filing_date')} | DOJ: {durations.get('doj_memo_date') or 'N/A'} | Reply: {durations.get('reply_memo_date') or 'N/A'} | Outcome: {durations.get('outcome_date') or 'N/A'}",
        f"✅ Results: Type={res.get('type')} | Status={res.get('status')} | Judge={res.get('judge') or 'None'} | Visa={res.get('visa_office') or 'None'} | Hearing={res.get('has_hearing')}",
        f"🔬 Method: {res.get('method')} | Confidence: {res.get('confidence', 'N/A')}",
        f"⏱️  Metrics: Age: {durations.get('age_of_case')}d | Close: {durations.get('time_to_close') or 'N/A'}d | Memo: {durations.get('memo_response_time') or 'N/A'}d | Reply: {durations.get('reply_memo_time') or 'N/A'}d",
        f"📊 Raw Result JSON: {json.dumps(res, default=str)}"
    ]
    return "\n" + "\n".join(lines)


def analyze(
    input_path: Optional[str] = None,
    mode: Optional[str] = None,
    output_dir: Optional[str | Path] = None,
    resume: bool = False,
    sample_audit: Optional[int] = None,
    ollama_url: Optional[str] = None,
    input_format: Optional[str] = None,
    year: Optional[int] = None,
    force: Optional[bool] = None,
    wait_for_ollama: bool = True,
    ollama_wait_time: int = 120,
    single_case: Optional[str] = None,
    max_cases: Optional[int] = None,
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
        force: Force analysis of all cases (ignore existing analysis)
        single_case: Analyze a specific case and output detailed results
        max_cases: Maximum number of cases to analyze (only with --year)
    """
    # Use config defaults if not provided
    mode = mode or Config.get_analysis_mode()
    sample_audit = sample_audit if sample_audit is not None else Config.get_analysis_sample_audit()
    ollama_url = ollama_url or Config.get_ollama_url()
    input_format = input_format or Config.get_analysis_input_format()
    force = force if force is not None else False  # Default to not force
    
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
    db_engine = None
    if input_format == "database":
        db_storage = _db_schema.AnalysisResultStorage()
        db_manager = _db_schema.AnalysisDBManager()
        
        # Create SQLAlchemy engine for docket_entries queries
        db_cfg = Config.get_db_config() or {}
        env_dsn = os.getenv('DB_CONNECTION_STR')
        if env_dsn:
            db_dsn = env_dsn
        else:
            db_dsn = f"postgresql://{db_cfg.get('user')}:{db_cfg.get('password')}@{db_cfg.get('host')}:{db_cfg.get('port')}/{db_cfg.get('database')}"
        
        from sqlalchemy import create_engine
        db_engine = create_engine(db_dsn)
        
        # Ensure database schema is up to date
        if not db_manager.migrate_database():
            logger.error("Failed to migrate database schema")
            return 1

    # Handle single case analysis
    if single_case:
        return _analyze_single_case(
            case_id=single_case,
            mode=mode,
            db_engine=db_engine,
            wait_for_ollama=wait_for_ollama,
            ollama_wait_time=ollama_wait_time
        )

    # Perform analysis
        # Get data from configured source
    df = None  # Initialize to avoid UnboundLocalError
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
                # Apply limit if year exists
                if year and max_cases:
                    cases = cases[:max_cases]
            else:
                # For database or other sources
                if year and input_format == "database":
                    # Fetch with year filter and optional limit
                    db_reader = _database.DatabaseReader()
                    cases = db_reader.fetch_cases(year=year, limit=max_cases)
                else:
                    cases = _database.get_data_source(input_format)
                    
                    # Manual filter by year if specified for non-db sources
                    if year:
                        # Filter loaded cases by year using case_number (more reliable)
                        year_suffix = f"-{year % 100:02d}"
                        cases = [
                            case for case in cases 
                            if case.get('case_number', '').endswith(year_suffix)
                        ]
                        
                        # Apply limit if specified
                        if max_cases:
                            cases = cases[:max_cases]
            
            # Convert to DataFrame using parser logic
            df = _parser._parse_cases_list(cases)
            
        except Exception as e:
            logger.error(f"Failed to load data from {input_format}: {e}")
            if input_path:
                logger.info(f"Falling back to file input: {input_path}")
                df = _parser.parse_cases(input_path)
            else:
                raise
    
    # Ensure df is defined
    if df is None:
        raise ValueError("Failed to load any case data")

    # Setup resume checkpoint and audit logging
    checkpoint_path = output_dir / Config.get_analysis_checkpoint_file()
    processed = set()
    resume_force = False  # Track if resumed session was using force mode
    if resume and checkpoint_path.exists():
        try:
            with checkpoint_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    try:
                        obj = __import__("json").loads(line)
                        if obj and isinstance(obj, dict):
                            if obj.get("case_number"):
                                processed.add(obj.get("case_number"))
                            # Check if this checkpoint was created with force mode
                            if obj.get("force_mode") is True:
                                resume_force = True
                    except Exception:
                        continue
                        
            # If resumed from a force session, apply force mode
            if resume_force:
                original_force = force
                force = True
                logger.info(f"🔄 Resumed from force mode session - applying force mode (was: {original_force}, now: {force})")
                
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
                if not force and db_storage and case_id:
                    existing_analysis = db_storage.is_analyzed(case_id, mode)
                    if existing_analysis:
                        # Use existing analysis results
                        types.append(existing_analysis.get('case_type'))
                        statuses.append(existing_analysis.get('case_status'))
                        visa_offices.append(existing_analysis.get('visa_office'))
                        judges.append(existing_analysis.get('judge'))
                        logger.debug(f"Skipping analysis for {case_id} (already analyzed)")
                        pbar.update(1)
                        continue
                
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
                        res = _nlp_engine.classify_case_enhanced(raw_case, use_llm_fallback=True, 
                                                            wait_for_ollama=wait_for_ollama, 
                                                            ollama_wait_time=ollama_wait_time)
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
                        visa_office = res.get("visa_office")
                        judge = res.get("judge")
                        method = "rule_fallback"
                        confidence = "low"
                        res["method"] = method
                        res["confidence"] = confidence
                        
                else:
                    # Rule-based mode with direct entity extraction from nlp_engine
                    logger.debug(f"🔍 Processing case {case_id} with rule-based analysis")
                    res = _rules.classify_case_rule(raw_case)
                    case_type = res.get("type")
                    case_status = res.get("status")
                    visa_office = res.get("visa_office")
                    judge = res.get("judge")
                    
                    method = "rule_based"
                    res["method"] = method
                    res["confidence"] = res.get("confidence", "high")
                    logger.debug(f"📊 Case {case_id}: {case_type} | {case_status} | Method: rule_based")
                    if visa_office or judge:
                        logger.debug(f"📍 Case {case_id} entities - Visa: {visa_office}, Judge: {judge}")
                
                # Checkpoint results for resumability (only in LLM mode)
                if mode == "llm" and checkpoint_path and case_id:
                    checkpoint_data = {
                        "case_number": case_id, 
                        "type": case_type,
                        "status": case_status,
                        "visa_office": visa_office, 
                        "judge": judge,
                        "method": method,
                        "confidence": confidence
                    }
                    
                    # Save force mode state for proper resume behavior
                    if force:
                        checkpoint_data["force_mode"] = True
                    # If resumed from force session, also save it
                    elif resume_force:
                        checkpoint_data["force_mode"] = True
                    
                    _utils.write_checkpoint(checkpoint_path, checkpoint_data)
                
                # Store results for current case
                types.append(case_type)
                statuses.append(case_status)
                visa_offices.append(visa_office)
                judges.append(judge)

                # Compute durations (used for logging and DB)
                durations = _compute_case_durations(raw_case, case_id, db_engine)
                
                # Log detailed results for every case in batch
                logger.info(_format_case_analysis_log(case_id, raw_case, res, durations))
                
                # Save analysis to dedicated analysis table
                if db_storage and case_id:
                    analysis_result = {
                        'type': case_type,
                        'status': case_status,
                        'visa_office': visa_office,
                        'judge': judge,
                        'has_hearing': res.get('has_hearing'),
                        'time_to_close': durations.get('time_to_close'),
                        'age_of_case': durations.get('age_of_case'),
                        'rule9_wait': durations.get('rule9_wait'),
                        'outcome_date': durations.get('outcome_date'),
                        'memo_response_time': durations.get('memo_response_time'),
                        'memo_to_outcome_time': durations.get('memo_to_outcome_time'),
                        'reply_memo_time': durations.get('reply_memo_time'),
                        'reply_to_outcome_time': durations.get('reply_to_outcome_time'),
                        'doj_memo_date': durations.get('doj_memo_date'),
                        'reply_memo_date': durations.get('reply_memo_date'),
                        'title': raw_case.get('style_of_cause') or raw_case.get('title'),
                        'court': raw_case.get('office') or raw_case.get('court'),
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
    
    # Clean up database connections
    if db_engine:
        try:
            db_engine.dispose()
            logger.info("🔌 Database connections cleaned up")
        except Exception as e:
            logger.warning(f"⚠️ Error cleaning up database connections: {e}")

    return 0


def _analyze_single_case(
    case_id: str,
    mode: str,
    db_engine: Optional[Any] = None,
    wait_for_ollama: bool = True,
    ollama_wait_time: int = 120
) -> int:
    """Analyze a single case and print detailed results."""
    from loguru import logger
    import json
    
    logger.info(f"\n🔍 Analyzing single case: {case_id}")
    logger.info("=" * 60)
    
    try:
        # Load case data
        case_data = None
        if db_engine:
            from sqlalchemy import text
            with db_engine.connect() as conn:
                # Get case info
                case_query = "SELECT * FROM cases WHERE case_number = :case_id"
                case_row = conn.execute(text(case_query), {"case_id": case_id}).fetchone()
                
                if not case_row:
                    logger.error(f"❌ Case {case_id} not found in database.")
                    return 1
                    
                # Get docket entries
                docket_query = "SELECT date_filed, recorded_entry_summary FROM docket_entries WHERE case_number = :case_id ORDER BY date_filed ASC"
                docket_rows = conn.execute(text(docket_query), {"case_id": case_id}).fetchall()
                
                dockets = []
                for r in docket_rows:
                    dockets.append({
                        "date_filed": str(r.date_filed),
                        "recorded_entry_summary": r.recorded_entry_summary,
                        "summary": r.recorded_entry_summary
                    })
                
                case_data = dict(case_row._mapping)
                case_data['docket_entries'] = dockets
        else:
            logger.error("❌ Single case analysis currently requires database connection.")
            return 1

        # Compute durations
        durations = _compute_case_durations(case_data, case_id, db_engine)
        
        # Display Basic Information
        logger.info("\n📋 Basic Information:")
        logger.info("-" * 30)
        logger.info(f"Case Number:  {case_data.get('case_number')}")
        logger.info(f"Title:        {case_data.get('style_of_cause')}")
        logger.info(f"Nature:       {case_data.get('nature_of_proceeding')}")
        logger.info(f"Office:       {case_data.get('office')}")
        logger.info(f"Language:     {case_data.get('language')}")

        # Display Key Dates
        logger.info("\n📅 Key Dates & Milestones:")
        logger.info("-" * 30)
        logger.info(f"Filing Date (Start): {case_data.get('filing_date')}")
        logger.info(f"DOJ Memo Date:      {durations.get('doj_memo_date') or 'N/A'}")
        logger.info(f"Reply Memo Date:    {durations.get('reply_memo_date') or 'N/A'}")
        logger.info(f"Outcome Date (End): {durations.get('outcome_date') or 'N/A'}")
        
        # Check text extraction
        extracted_text = _nlp_engine.get_nlp_engine()._extract_text(case_data)
        logger.info("\n📝 Extracted Text Preview:")
        logger.info(extracted_text[:1000] + ("..." if len(extracted_text) > 1000 else ""))
        
        # Actual classification
        if mode == "llm":
            res = _nlp_engine.classify_case_enhanced(
                case_data, 
                use_llm_fallback=True, 
                wait_for_ollama=wait_for_ollama, 
                ollama_wait_time=ollama_wait_time
            )
        else:
            res = _rules.classify_case_rule(case_data)

        logger.info("\n✅ Analysis Results:")
        logger.info("-" * 30)
        logger.info(f"Type:       {res.get('type')}")
        logger.info(f"Status:     {res.get('status')}")
        logger.info(f"Method:     {res.get('method')}")
        logger.info(f"Confidence: {res.get('confidence', 'N/A')}")
        logger.info(f"Judge:      {res.get('judge')}")
        logger.info(f"Visa Office:{res.get('visa_office')}")
        logger.info(f"Hearing:    {res.get('has_hearing')}")
        
        logger.info("\n⏱️ Duration Metrics:")
        logger.info("-" * 30)
        logger.info(f"Age of Case:     {durations.get('age_of_case')} days")
        logger.info(f"Time to Close:   {durations.get('time_to_close')} days")
        logger.info(f"DOJ Memo Date:   {durations.get('doj_memo_date')} ")
        logger.info(f"Reply Memo Date: {durations.get('reply_memo_date')} ")
        logger.info(f"Reply Memo to Outcome:  {durations.get('reply_to_outcome_time')} days")
        
        # Raw result JSON
        logger.info("\n📊 Raw Result JSON:")
        logger.info(json.dumps(res, indent=2, default=str))
        
        logger.info("=" * 60)
        return 0
        
    except Exception as e:
        logger.error(f"❌ Error during single case analysis: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import signal
    
    # Setup graceful shutdown
    def signal_handler(signum, frame):
        from loguru import logger
        logger.info(f"🛑 Received signal {signum}, shutting down gracefully...")
        raise SystemExit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

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
    p.add_argument("--force", action="store_true", 
                   help="Force analysis of all cases (ignore existing analysis)")
    p.add_argument("--single-case", help="Analyze a specific case and output detailed results")
    p.add_argument("--max-cases", type=int, help="Maximum number of cases to analyze (only works with --year)")
    
    # Output options
    p.add_argument("--output-dir", "-o", help="Output directory")
    
    # LLM options
    p.add_argument("--resume", action="store_true", help="Resume LLM processing using checkpoint file")
    p.add_argument("--sample-audit", type=int, help="Write sample LLM outputs to audit file (N samples)")
    p.add_argument("--ollama-url", help="Custom Ollama base URL")
    p.add_argument("--wait-for-ollama", action="store_true", default=True, help="Wait for Ollama to be idle before starting requests")
    p.add_argument("--ollama-wait-time", type=int, default=120, help="Maximum time to wait for Ollama to become idle (default: 120s)")
    
    # Database management
    p.add_argument("--migrate-db", action="store_true", 
                   help="Migrate database schema and exit")
    p.add_argument("--check-ollama", action="store_true",
                   help="Check Ollama service status and exit")
    
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
    
    # Handle Ollama status check
    if ns.check_ollama:
        return check_ollama_status(ns.ollama_url)
    
    return analyze(
        input_path=ns.input,
        mode=ns.mode,
        output_dir=ns.output_dir,
        resume=ns.resume,
        sample_audit=ns.sample_audit,
        ollama_url=ns.ollama_url,
        input_format=ns.input_format,
        year=ns.year,
        force=ns.force,
        wait_for_ollama=ns.wait_for_ollama,
        ollama_wait_time=ns.ollama_wait_time,
        single_case=ns.single_case,
        max_cases=ns.max_cases,
    )


if __name__ == "__main__":
    raise SystemExit(main())