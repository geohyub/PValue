"""Background workers using QThread for simulation tasks."""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal

from pvalue.data import build_condition_mask, get_time_interval_minutes, validate_metocean
from pvalue.models import SimulationConfig, Task
from pvalue.simulation import simulate_campaign, summarize_pxx


class SimulationWorker(QThread):
    """Run Monte Carlo simulation in background thread."""

    progress = pyqtSignal(int, int)  # current, total
    finished = pyqtSignal(object, object)  # results_df, summary_df
    error = pyqtSignal(str)
    log = pyqtSignal(str)

    def __init__(
        self,
        df: pd.DataFrame,
        config: SimulationConfig,
        interval_min: int,
        parent=None,
    ):
        super().__init__(parent)
        self.df = df
        self.config = config
        self.interval_min = interval_min
        self._cancelled = False

    def run(self):
        try:
            self.log.emit(f"Starting simulation — {self.config.n_sims} iterations...")

            def _cb(current, total):
                if self._cancelled:
                    raise InterruptedError("Cancelled by user")
                self.progress.emit(current, total)

            res = simulate_campaign(
                self.df,
                self.config.tasks,
                n_sims=self.config.n_sims,
                start_month=self.config.start_month,
                calendar_mask_fn=self.config.build_calendar_mask_fn(),
                split_mode=self.config.split_mode,
                time_interval_min=self.interval_min,
                na_handling=self.config.na_handling,
                seed=self.config.seed,
                progress_callback=_cb,
            )
            summary = summarize_pxx(res, self.config.pvals)
            self.log.emit("Simulation complete.")
            self.finished.emit(res, summary)

        except InterruptedError:
            self.log.emit("Simulation cancelled.")
        except Exception as exc:
            self.error.emit(str(exc))

    def cancel(self):
        self._cancelled = True


class OptimalMonthWorker(QThread):
    """Analyse all 12 months in background."""

    progress = pyqtSignal(int)  # month (1-12)
    finished = pyqtSignal(object, int)  # result_df, optimal_month
    error = pyqtSignal(str)

    def __init__(
        self,
        df: pd.DataFrame,
        config: SimulationConfig,
        interval_min: int,
        parent=None,
    ):
        super().__init__(parent)
        self.df = df
        self.config = config
        self.interval_min = interval_min

    def run(self):
        try:
            rows = []
            for month in range(1, 13):
                self.progress.emit(month)
                res = simulate_campaign(
                    self.df,
                    self.config.tasks,
                    n_sims=max(500, self.config.n_sims // 2),
                    start_month=month,
                    split_mode=self.config.split_mode,
                    time_interval_min=self.interval_min,
                    na_handling=self.config.na_handling,
                    seed=self.config.seed,
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
            self.finished.emit(result_df, optimal)

        except Exception as exc:
            self.error.emit(str(exc))
