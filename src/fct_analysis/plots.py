"""Plot generation for feature 0005 using seaborn/matplotlib.

Functions accept a pandas.DataFrame with the columns produced by `fct_analysis`.
Each function writes a PNG to the specified output path.
"""
from __future__ import annotations

from typing import Optional
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd


def volume_trend(df: pd.DataFrame, output_path: str | Path) -> None:
    """Create stacked bar chart showing case volume trends over time."""
    # Check if we have the required columns for both filing and outcome analysis
    has_filing = "filing_date" in df.columns and not df.empty
    has_outcome = "outcome_date" in df.columns and not df.empty
    
    if not has_filing and not has_outcome:
        # Create empty plot
        plt.figure(figsize=(10, 6))
        plt.savefig(output_path)
        plt.close()
        return
        
    plt.figure(figsize=(12, 6))
    
    # Plot filing trends (new cases) - using filing_date
    if has_filing and df['filing_date'].notna().any():
        df_filing = df.dropna(subset=['filing_date']).copy()
        df_filing["year_month"] = pd.to_datetime(df_filing["filing_date"], errors="coerce").dt.to_period("M")
        filing_monthly = df_filing.groupby("year_month").size()
        
        # Plot filing trend as line
        filing_monthly.plot(kind="line", marker='o', label="New Cases (Filing)", ax=plt.gca())
    
    # Plot outcome trends (resolved cases) - using outcome_date for resolution
    if has_outcome:
        # Only include resolved cases with valid outcome dates
        resolved_statuses = ['Granted', 'Dismissed', 'Discontinued', 'Struck', 'Moot', 'Settled']
        df_resolved = df[df['case_status'].isin(resolved_statuses)].dropna(subset=['outcome_date'])
        
        if not df_resolved.empty:
            df_resolved["year_month"] = pd.to_datetime(df_resolved["outcome_date"], errors="coerce").dt.to_period("M")
            
            # Group by month and outcome status
            outcome_monthly = df_resolved.groupby(["year_month", "case_status"]).size().unstack(fill_value=0)
            
            # Plot each outcome type as stacked area
            outcome_monthly.plot(kind="area", stacked=True, alpha=0.7, ax=plt.gca())
    
    plt.title("Monthly Case Trends: New Cases vs Resolved Cases")
    plt.xlabel("Month")
    plt.ylabel("Number of Cases")
    plt.legend(title="Case Type/Status")
    plt.xticks(rotation=45)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def duration_boxplot(df: pd.DataFrame, output_path: str | Path) -> None:
    """Create box plot showing case duration distribution."""
    if "duration_days" not in df.columns or df.empty:
        plt.figure(figsize=(10, 6))
        plt.savefig(output_path)
        plt.close()
        return
        
    plt.figure(figsize=(10, 6))
    sns.boxplot(data=df, x="type", y="duration_days")
    plt.title("Case Duration Distribution by Type")
    plt.xlabel("Case Type")
    plt.ylabel("Duration (Days)")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def outcome_donut(df: pd.DataFrame, output_path: str | Path) -> None:
    """Create donut chart showing case outcome distribution."""
    if "status" not in df.columns or df.empty:
        plt.figure(figsize=(8, 8))
        plt.savefig(output_path)
        plt.close()
        return
        
    status_counts = df["status"].value_counts()
    
    plt.figure(figsize=(8, 8))
    plt.pie(status_counts.values, labels=status_counts.index, autopct="%1.1f%%", 
            startangle=90, wedgeprops=dict(width=0.3))
    plt.title("Case Outcome Distribution")
    plt.savefig(output_path)
    plt.close()


def visa_office_heatmap(df: pd.DataFrame, output_path: str | Path) -> None:
    """Create horizontal bar chart showing visa office performance."""
    if df.empty:
        plt.figure(figsize=(10, 6))
        plt.savefig(output_path)
        plt.close()
        return
        
    # Extract visa office from meta column if available
    visa_offices = []
    durations = []
    
    for _, row in df.iterrows():
        visa_office = None
        if "meta" in row and isinstance(row["meta"], dict):
            visa_office = row["meta"].get("visa_office")
        
        if visa_office and "duration_days" in row and pd.notna(row["duration_days"]):
            visa_offices.append(visa_office)
            durations.append(row["duration_days"])
    
    if not visa_offices:
        plt.figure(figsize=(10, 6))
        plt.savefig(output_path)
        plt.close()
        return
        
    # Create dataframe for plotting
    office_df = pd.DataFrame({
        "visa_office": visa_offices,
        "duration_days": durations
    })
    
    # Aggregate by visa office
    office_stats = office_df.groupby("visa_office").agg({
        "duration_days": ["mean", "count"]
    }).round(1)
    office_stats.columns = ["avg_duration", "case_count"]
    office_stats = office_stats.sort_values("avg_duration", ascending=True)
    
    plt.figure(figsize=(10, 8))
    plt.barh(office_stats.index, office_stats["avg_duration"])
    plt.title("Average Case Duration by Visa Office")
    plt.xlabel("Average Duration (Days)")
    plt.ylabel("Visa Office")
    
    # Add case count as text
    for i, (avg, count) in enumerate(zip(office_stats["avg_duration"], office_stats["case_count"])):
        plt.text(avg + 1, i, f"n={int(count)}", va="center")
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def make_charts(input_csv: str | Path, out_dir: str | Path) -> None:
    """Convenience function to generate all charts from CSV."""
    try:
        df = pd.read_csv(input_csv)
    except Exception:
        df = pd.DataFrame()
    
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    volume_trend(df, out_path / "volume_trend.png")
    duration_boxplot(df, out_path / "duration_boxplot.png")
    outcome_donut(df, out_path / "outcome_donut.png")
    visa_office_heatmap(df, out_path / "visa_office_heatmap.png")