"""Visualization functions for simulation results."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Font setup
# ---------------------------------------------------------------------------

def _detect_korean_font() -> str:
    """Auto-detect a Korean-capable font on the system."""
    fonts = {f.name for f in fm.fontManager.ttflist}
    priority = [
        "Malgun Gothic",
        "NanumGothic",
        "AppleGothic",
        "Noto Sans KR",
        "NanumBarunGothic",
    ]
    for name in priority:
        if name in fonts:
            return name
    for name in fonts:
        if any(k in name for k in ("Gothic", "Nanum", "Malgun", "Batang", "Dotum")):
            return name
    return "DejaVu Sans"


def configure_matplotlib() -> None:
    """Apply project-wide matplotlib defaults."""
    plt.rcParams["font.family"] = _detect_korean_font()
    plt.rcParams["axes.unicode_minus"] = False


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _pvalue_style(p: int, pvals: List[int]):
    """Return ``(color, linewidth, linestyle)`` for a percentile line."""
    if p == 50:
        return "royalblue", 2.5, "-"
    if p == 90:
        return "crimson", 2.5, "-"
    if p == min(pvals):
        return "darkred", 2.0, "-"
    if p == max(pvals):
        return "darkred", 2.0, ":"
    return "gray", 1.0, "--"


# ---------------------------------------------------------------------------
# Chart functions
# ---------------------------------------------------------------------------

def plot_histogram(
    res: pd.DataFrame,
    pvals: List[int],
    save_path: Optional[str] = None,
) -> None:
    """Histogram of campaign durations with percentile lines."""
    configure_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(res["elapsed_days"], bins=40, alpha=0.7, color="skyblue", edgecolor="black")

    for p in pvals:
        val = np.percentile(res["elapsed_days"], p)
        color, lw, ls = _pvalue_style(p, pvals)
        ax.axvline(val, color=color, linewidth=lw, linestyle=ls, label=f"P{p} = {val:.1f}d")

    ax.set_xlabel("Campaign Duration (days)", fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.set_title("Campaign Duration Distribution", fontsize=14, fontweight="bold")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    _save_or_show(fig, save_path)


def plot_timeline(
    res: pd.DataFrame,
    n_samples: int = 5,
    save_path: Optional[str] = None,
) -> None:
    """Stacked bar timeline for the longest simulations."""
    configure_matplotlib()
    samples = res.nlargest(n_samples, "elapsed_days")

    fig, axes = plt.subplots(n_samples, 1, figsize=(12, n_samples * 1.2), sharex=True)
    if n_samples == 1:
        axes = [axes]

    for idx, (_, row) in enumerate(samples.iterrows()):
        ax = axes[idx]
        work_d = row["work_hours"] / 24
        wait_d = row["wait_hours"] / 24
        total_d = row["elapsed_days"]

        ax.barh(0, work_d, color="seagreen", alpha=0.8, label="Work")
        ax.barh(0, wait_d, left=work_d, color="tomato", alpha=0.8, label="Wait")

        work_pct = work_d / total_d * 100
        wait_pct = wait_d / total_d * 100
        ax.text(work_d / 2, 0, f"{work_d:.1f}d\n({work_pct:.0f}%)", ha="center", va="center", fontsize=9, fontweight="bold")
        ax.text(work_d + wait_d / 2, 0, f"{wait_d:.1f}d\n({wait_pct:.0f}%)", ha="center", va="center", fontsize=9, fontweight="bold")

        ax.set_yticks([])
        ax.set_xlim(0, total_d * 1.05)
        ax.set_title(f'Sim #{row["sim"] + 1} — {total_d:.1f} days', fontsize=10, loc="left")
        if idx == 0:
            ax.legend(loc="upper right", fontsize=9)
        ax.grid(axis="x", alpha=0.3)

    axes[-1].set_xlabel("Duration (days)", fontsize=11)
    fig.suptitle(f"Work / Wait Timeline (Top {n_samples})", fontsize=13, fontweight="bold", y=0.995)
    fig.tight_layout()
    _save_or_show(fig, save_path)


def plot_cdf(
    res: pd.DataFrame,
    save_path: Optional[str] = None,
) -> None:
    """Cumulative distribution function of campaign durations."""
    configure_matplotlib()
    sorted_days = np.sort(res["elapsed_days"])
    cdf = np.arange(1, len(sorted_days) + 1) / len(sorted_days) * 100

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(sorted_days, cdf, linewidth=2, color="navy")
    ax.set_xlabel("Campaign Duration (days)", fontsize=12)
    ax.set_ylabel("Cumulative Probability (%)", fontsize=12)
    ax.set_title("Cumulative Distribution Function (CDF)", fontsize=14, fontweight="bold")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    _save_or_show(fig, save_path)


def plot_work_wait_scatter(
    res: pd.DataFrame,
    save_path: Optional[str] = None,
) -> None:
    """Scatter plot of work-hours vs. wait-hours."""
    configure_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(res["work_hours"] / 24, res["wait_hours"] / 24, alpha=0.5, s=20, color="steelblue")
    ax.set_xlabel("Work Time (days)", fontsize=12)
    ax.set_ylabel("Wait Time (days)", fontsize=12)
    ax.set_title("Work vs. Wait Time", fontsize=14, fontweight="bold")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    _save_or_show(fig, save_path)


def plot_calendar_availability(
    df: pd.DataFrame,
    calendar_fn: Callable,
    save_path: Optional[str] = None,
) -> None:
    """Hourly availability bar chart and overall pie chart."""
    if calendar_fn is None:
        return

    configure_matplotlib()
    mask = calendar_fn(df.index)
    hours_total = df.index.hour.value_counts().sort_index()
    hours_avail = df.index[mask].hour.value_counts().sort_index()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    x = list(range(24))
    ratio = [(hours_avail.get(h, 0) / hours_total.get(h, 1)) * 100 for h in x]
    ax1.bar(x, ratio, color="seagreen", alpha=0.7)
    ax1.set_xlabel("Hour of Day")
    ax1.set_ylabel("Availability (%)")
    ax1.set_title("Hourly Work Availability", fontweight="bold")
    ax1.set_xticks(range(0, 24, 2))
    ax1.grid(alpha=0.3)

    avail = int(mask.sum())
    blocked = len(df) - avail
    ax2.pie(
        [avail, blocked],
        labels=["Available", "Blocked"],
        autopct="%1.1f%%",
        colors=["seagreen", "lightgray"],
        startangle=90,
    )
    ax2.set_title("Overall Time Availability", fontweight="bold")

    fig.tight_layout()
    _save_or_show(fig, save_path)


def plot_monthly_comparison(
    monthly_df: pd.DataFrame,
    optimal_month: int,
    save_path: Optional[str] = None,
) -> None:
    """P90 and Mean by month with optimal marker."""
    configure_matplotlib()
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(monthly_df["Month"], monthly_df["P90_days"], marker="o", lw=2, label="P90")
    ax.plot(monthly_df["Month"], monthly_df["Mean_days"], marker="s", lw=2, alpha=0.7, label="Mean")
    ax.axvline(optimal_month, color="red", ls="--", alpha=0.5, label=f"Optimal: Month {optimal_month}")

    ax.set_xlabel("Start Month", fontsize=12)
    ax.set_ylabel("Campaign Duration (days)", fontsize=12)
    ax.set_title("Monthly Campaign Duration Analysis", fontsize=14, fontweight="bold")
    ax.set_xticks(range(1, 13))
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    _save_or_show(fig, save_path)


def plot_comparison_boxplot(
    all_results: dict,
    save_path: Optional[str] = None,
) -> None:
    """Side-by-side boxplots comparing multiple sites."""
    configure_matplotlib()
    fig, ax = plt.subplots(figsize=(12, 6))
    data = [r["results"]["elapsed_days"] for r in all_results.values()]
    labels = list(all_results.keys())
    ax.boxplot(data, labels=labels)
    ax.set_ylabel("Campaign Duration (days)", fontsize=12)
    ax.set_title("Site Comparison", fontsize=14, fontweight="bold")
    plt.xticks(rotation=45, ha="right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    _save_or_show(fig, save_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def save_all_charts(
    res: pd.DataFrame,
    pvals: List[int],
    output_dir: str,
    df: Optional[pd.DataFrame] = None,
    calendar_fn: Optional[Callable] = None,
) -> None:
    """Convenience: save the standard set of charts to *output_dir*."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    plot_histogram(res, pvals, str(out / "histogram_pvals.png"))
    plot_timeline(res, 5, str(out / "timeline.png"))
    plot_cdf(res, str(out / "cdf.png"))
    plot_work_wait_scatter(res, str(out / "work_vs_wait.png"))
    if df is not None and calendar_fn is not None:
        plot_calendar_availability(df, calendar_fn, str(out / "calendar.png"))


def _save_or_show(fig, save_path: Optional[str]) -> None:
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
