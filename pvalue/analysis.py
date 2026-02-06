"""Higher-level analysis workflows: batch runs, optimal start-month, etc."""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from pvalue.data import get_time_interval_minutes, load_csv, validate_metocean
from pvalue.models import SimulationConfig, Task
from pvalue.reporting import generate_excel_report
from pvalue.simulation import simulate_campaign, summarize_pxx
from pvalue.visualization import (
    plot_comparison_boxplot,
    plot_monthly_comparison,
    save_all_charts,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Single-file analysis
# ---------------------------------------------------------------------------

def run_single(
    df: pd.DataFrame,
    config: SimulationConfig,
    output_dir: Optional[str] = None,
) -> pd.DataFrame:
    """Validate data, run simulation, save outputs, and return the results DataFrame."""
    ok, msg = validate_metocean(df)
    if not ok:
        raise ValueError(f"Data validation failed: {msg}")

    interval_min = get_time_interval_minutes(df)
    logger.info("Data validated — %d records, %d-min interval", len(df), interval_min)

    cal_fn = config.build_calendar_mask_fn()

    res = simulate_campaign(
        df,
        config.tasks,
        n_sims=config.n_sims,
        start_month=config.start_month,
        calendar_mask_fn=cal_fn,
        split_mode=config.split_mode,
        time_interval_min=interval_min,
        na_handling=config.na_handling,
        seed=config.seed,
    )

    summary = summarize_pxx(res, config.pvals)
    logger.info("\n%s", summary.to_string(index=False))

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        res.to_csv(os.path.join(output_dir, "sim_results.csv"), index=False)
        summary.to_csv(os.path.join(output_dir, "summary.csv"), index=False)
        save_all_charts(res, config.pvals, output_dir, df, cal_fn)
        generate_excel_report(
            res,
            summary,
            {"tasks": [{"name": t.name, "duration_h": t.duration_h, "thresholds": t.thresholds} for t in config.tasks]},
            os.path.join(output_dir, "report.xlsx"),
        )
        logger.info("Results saved to %s", output_dir)

    return res


# ---------------------------------------------------------------------------
# Batch analysis
# ---------------------------------------------------------------------------

def batch_run(
    csv_files: List[str],
    config: SimulationConfig,
    csv_type: str = "general",
    output_dir: str = "./batch_outputs",
) -> Dict[str, dict]:
    """Run simulation on multiple CSV files and generate comparison charts."""
    all_results: Dict[str, dict] = {}

    for path in csv_files:
        name = os.path.basename(path).replace(".csv", "")
        logger.info("Analyzing: %s", name)
        try:
            df = load_csv(path, csv_type)
            ok, msg = validate_metocean(df)
            if not ok:
                logger.error("Validation failed for %s: %s", name, msg)
                continue

            interval_min = get_time_interval_minutes(df)
            res = simulate_campaign(
                df,
                config.tasks,
                n_sims=config.n_sims,
                start_month=config.start_month,
                calendar_mask_fn=config.build_calendar_mask_fn(),
                split_mode=config.split_mode,
                time_interval_min=interval_min,
                na_handling=config.na_handling,
                seed=config.seed,
            )
            summary = summarize_pxx(res, config.pvals)
            all_results[name] = {"results": res, "summary": summary}
            logger.info("Done: %s", name)
        except Exception as exc:
            logger.error("Failed: %s — %s", name, exc)

    if all_results:
        os.makedirs(output_dir, exist_ok=True)
        plot_comparison_boxplot(all_results, os.path.join(output_dir, "comparison_boxplot.png"))

        comparison = pd.DataFrame(
            {n: r["summary"]["Value_days"].values for n, r in all_results.items()},
            index=list(all_results.values())[0]["summary"]["Metric"],
        )
        comparison.to_csv(os.path.join(output_dir, "comparison.csv"))

    return all_results


# ---------------------------------------------------------------------------
# Optimal start-month analysis
# ---------------------------------------------------------------------------

def analyze_optimal_start_month(
    df: pd.DataFrame,
    config: SimulationConfig,
    save_path: Optional[str] = None,
) -> pd.DataFrame:
    """Find the best month to start the campaign (lowest P90).

    Returns:
        DataFrame with Month, P90_days, Mean_days columns.
    """
    interval_min = get_time_interval_minutes(df)
    cal_fn = config.build_calendar_mask_fn()
    rows = []

    for month in range(1, 13):
        logger.info("  Analyzing month %d/12 ...", month)
        res = simulate_campaign(
            df,
            config.tasks,
            n_sims=max(500, config.n_sims // 2),
            start_month=month,
            calendar_mask_fn=cal_fn,
            split_mode=config.split_mode,
            time_interval_min=interval_min,
            na_handling=config.na_handling,
            seed=config.seed,
        )
        rows.append(
            {
                "Month": month,
                "P90_days": float(np.percentile(res["elapsed_days"], 90)),
                "Mean_days": float(res["elapsed_days"].mean()),
            }
        )

    result_df = pd.DataFrame(rows)
    optimal = int(result_df.loc[result_df["P90_days"].idxmin(), "Month"])
    logger.info(
        "Optimal start month: %d (P90 = %.1f days)",
        optimal,
        result_df["P90_days"].min(),
    )

    plot_monthly_comparison(result_df, optimal, save_path)
    return result_df
