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


class KmaFetchWorker(QThread):
    """Fetch ocean observation data from KMA API Hub in background thread."""

    progress = pyqtSignal(int, int)  # current_chunk, total_chunks
    status = pyqtSignal(str)  # status message
    finished = pyqtSignal(object)  # pd.DataFrame
    error = pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        stype: str,
        station_id: str,
        start: "datetime",
        end: "datetime",
        parent=None,
    ):
        super().__init__(parent)
        self.api_key = api_key
        self.stype = stype
        self.station_id = station_id
        self._start_dt = start
        self._end_dt = end
        self._cancelled = False

    def run(self):
        from pvalue.kma import fetch_timeseries, get_station_label

        label = get_station_label(self.stype, self.station_id)
        self.status.emit(f"{label} 데이터 수신 중...")
        try:
            def _progress(cur, total):
                if self._cancelled:
                    raise InterruptedError("Cancelled")
                self.progress.emit(cur, total)

            df = fetch_timeseries(
                self.api_key,
                self.stype,
                self.station_id,
                self._start_dt,
                self._end_dt,
                progress_callback=_progress,
            )
            if not self._cancelled:
                self.status.emit(f"완료 — {len(df):,}건 수신")
                self.finished.emit(df)
        except InterruptedError:
            self.status.emit("취소됨")
        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))

    def cancel(self):
        self._cancelled = True


class KhoaFetchWorker(QThread):
    """Fetch ocean observation data from KHOA (data.go.kr) in background thread."""

    progress = pyqtSignal(int, int)  # current_day, total_days
    status = pyqtSignal(str)  # status message
    finished = pyqtSignal(object)  # pd.DataFrame
    error = pyqtSignal(str)

    def __init__(
        self,
        service_key: str,
        obs_code: str,
        start: "datetime",
        end: "datetime",
        parent=None,
    ):
        super().__init__(parent)
        self.service_key = service_key
        self.obs_code = obs_code
        self._start_dt = start
        self._end_dt = end
        self._cancelled = False

    def run(self):
        from pvalue.khoa import fetch_timeseries, get_station_label

        label = get_station_label(self.obs_code)
        self.status.emit(f"{label} 데이터 수신 중...")
        try:
            def _progress(cur, total):
                if self._cancelled:
                    raise InterruptedError("Cancelled")
                self.progress.emit(cur, total)

            df = fetch_timeseries(
                self.service_key,
                self.obs_code,
                self._start_dt,
                self._end_dt,
                progress_callback=_progress,
            )
            if not self._cancelled:
                self.status.emit(f"완료 — {len(df):,}건 수신")
                self.finished.emit(df)
        except InterruptedError:
            self.status.emit("취소됨")
        except Exception as exc:
            if not self._cancelled:
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
        self._cancelled = False

    def run(self):
        try:
            rows = []
            cal_mask_fn = self.config.build_calendar_mask_fn()
            for month in range(1, 13):
                if self._cancelled:
                    return
                self.progress.emit(month)
                res = simulate_campaign(
                    self.df,
                    self.config.tasks,
                    n_sims=max(500, self.config.n_sims // 2),
                    start_month=month,
                    calendar_mask_fn=cal_mask_fn,
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

            if self._cancelled:
                return
            result_df = pd.DataFrame(rows)
            optimal = int(result_df.loc[result_df["P90_days"].idxmin(), "Month"])
            self.finished.emit(result_df, optimal)

        except Exception as exc:
            if not self._cancelled:
                self.error.emit(str(exc))

    def cancel(self):
        self._cancelled = True
