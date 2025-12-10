"""Plotting utilities for reports (Phase 3).

Stubs that will be implemented later; keep imports local to avoid heavy deps.
"""
from __future__ import annotations

from pathlib import Path


def make_charts(input_csv: str | Path, out_dir: str | Path) -> None:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    # placeholder: real plotting not implemented in scaffold
    for name in ("stacked_bar.png", "boxplot.png", "donut.png", "heatmap.png"):
        Path(out_dir, name).write_text("placeholder")
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


def volume_trend(df, outpath: str | Path, date_col: str = "filing_date") -> None:
    """Create a stacked bar chart (YYYY-MM) of case counts by type.

    Expects `df` to have `filing_date` and `type` columns.
    """
    p = Path(outpath)
    p.parent.mkdir(parents=True, exist_ok=True)

    d = df.copy()
    d = d.dropna(subset=[date_col])
    d["month"] = d[date_col].astype(str).str.slice(0, 7)
    grouped = d.groupby(["month", "type"]).size().unstack(fill_value=0)

    ax = grouped.plot(kind="bar", stacked=True, figsize=(10, 5))
    ax.set_xlabel("Month (YYYY-MM)")
    ax.set_ylabel("Cases")
    ax.set_title("Monthly Case Volume by Type")
    plt.tight_layout()
    plt.savefig(p)
    plt.close()


def duration_boxplot(df, outpath: str | Path, duration_col: str = "time_to_close") -> None:
    """Create a boxplot of durations by case type.

    Expects `df` to have `type` and `time_to_close` columns.
    """
    p = Path(outpath)
    p.parent.mkdir(parents=True, exist_ok=True)
    d = df.dropna(subset=[duration_col, "type"])[:]
    if d.empty:
        # write an empty placeholder image
        plt.figure(figsize=(6, 2))
        plt.text(0.5, 0.5, "No duration data available", ha="center", va="center")
        plt.axis("off")
        plt.savefig(p)
        plt.close()
        return

    plt.figure(figsize=(8, 5))
    sns.boxplot(x="type", y=duration_col, data=d)
    plt.title("Duration (days) by Case Type")
    plt.tight_layout()
    plt.savefig(p)
    plt.close()


def outcome_donut(df, outpath: str | Path, status_col: str = "status") -> None:
    p = Path(outpath)
    p.parent.mkdir(parents=True, exist_ok=True)
    counts = df[status_col].value_counts()
    if counts.empty:
        plt.figure(figsize=(4, 4))
        plt.text(0.5, 0.5, "No outcome data", ha="center", va="center")
        plt.axis("off")
        plt.savefig(p)
        plt.close()
        return

    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts = ax.pie(counts, labels=counts.index, wedgeprops=dict(width=0.4))
    ax.set_title("Case Outcome Distribution")
    plt.savefig(p)
    plt.close()


def visa_office_heatmap(df, outpath: str | Path, office_col: str = "visa_office") -> None:
    p = Path(outpath)
    p.parent.mkdir(parents=True, exist_ok=True)
    counts = df[office_col].fillna("Unknown").value_counts()
    if counts.empty:
        plt.figure(figsize=(6, 2))
        plt.text(0.5, 0.5, "No visa office data", ha="center", va="center")
        plt.axis("off")
        plt.savefig(p)
        plt.close()
        return

    # horizontal bar chart
    fig, ax = plt.subplots(figsize=(8, max(4, len(counts) * 0.3)))
    counts.sort_values().plot(kind="barh", ax=ax, color=sns.color_palette("viridis", len(counts)))
    ax.set_xlabel("Cases")
    ax.set_ylabel("Visa Office")
    ax.set_title("Cases by Visa Office")
    plt.tight_layout()
    plt.savefig(p)
    plt.close()
