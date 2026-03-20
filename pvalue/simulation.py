"""Monte Carlo simulation engine for marine operation campaigns."""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import numpy as np
import pandas as pd

from pvalue.data import build_condition_mask
from pvalue.models import Task


# ---------------------------------------------------------------------------
# Window-finding algorithms
# ---------------------------------------------------------------------------

def find_next_window(
    mask: np.ndarray, start_idx: int, need_steps: int
) -> Tuple[int, int, int]:
    """Find the next continuous window of *need_steps* feasible time-steps.

    Returns:
        ``(window_start, window_end, waiting_steps)``

    Raises:
        RuntimeError: If no feasible window is found within two full cycles.
    """
    n = len(mask)
    run = 0
    start_run = None
    i = start_idx
    limit = 2 * n

    for step in range(limit):
        if mask[i]:
            if run == 0:
                start_run = i
            run += 1
            if run >= need_steps:
                end_idx = (start_run + need_steps - 1) % n
                waiting = (start_run - start_idx) % n
                return start_run, end_idx, waiting
        else:
            run = 0
            start_run = None
        i = (i + 1) % n

    # Provide actionable guidance
    max_run = 0
    run_len = 0
    for idx in range(n):
        if mask[idx]:
            run_len += 1
            max_run = max(max_run, run_len)
        else:
            run_len = 0
    raise RuntimeError(
        f"No feasible continuous window found.\n"
        f"필요: {need_steps} 연속 스텝, 데이터 내 최대 연속 가용: {max_run} 스텝.\n"
        f"해결 방법:\n"
        f"  - Split (accumulated) mode 사용\n"
        f"  - Business hours 설정 해제 (연속 모드에서 일일 제한이 윈도우를 차단)\n"
        f"  - 임계값(Hs/Wind) 완화 또는 작업 시간 단축"
    )


def find_window_accumulated(
    mask: np.ndarray, start_idx: int, need_steps: int
) -> Tuple[int, int, int]:
    """Find accumulated (split) work steps totalling *need_steps*.

    Returns:
        ``(end_idx, waiting_steps, worked_steps)``

    Raises:
        RuntimeError: If insufficient feasible steps within two full cycles.
    """
    n = len(mask)
    i = start_idx
    waited = 0
    worked = 0
    limit = 2 * n

    for _ in range(limit):
        if worked >= need_steps:
            break
        if mask[i]:
            worked += 1
        else:
            waited += 1
        i = (i + 1) % n

    if worked < need_steps:
        raise RuntimeError("No feasible accumulated window found")

    end_idx = (i - 1) % n
    return end_idx, waited, worked


# ---------------------------------------------------------------------------
# Campaign simulation
# ---------------------------------------------------------------------------

def simulate_campaign(
    metocean: pd.DataFrame,
    tasks: List[Task],
    n_sims: int = 1000,
    start_month: Optional[int] = None,
    calendar_mask_fn: Optional[Callable] = None,
    seed: Optional[int] = 7,
    split_mode: bool = False,
    time_interval_min: int = 60,
    na_handling: str = "permissive",
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> pd.DataFrame:
    """Run a Monte Carlo campaign simulation.

    Args:
        metocean: Validated metocean DataFrame with DatetimeIndex.
        tasks: Ordered list of tasks to complete.
        n_sims: Number of simulation iterations.
        start_month: Restrict random start to a specific month (1-12).
        calendar_mask_fn: Callable ``(DatetimeIndex) -> np.ndarray[bool]``.
        seed: Random seed (None for non-deterministic).
        split_mode: Use accumulated/split work mode.
        time_interval_min: Data time resolution in minutes.
        na_handling: ``"permissive"`` or ``"conservative"``.
        progress_callback: Optional ``(current, total) -> None``.

    Returns:
        DataFrame with columns: sim, year_sample, start_time,
        elapsed_hours, wait_hours, work_hours, elapsed_days.
    """
    if seed is not None:
        np.random.seed(seed)

    df = metocean.copy()
    if "year" not in df.columns:
        df["year"] = df.index.year

    years = sorted(df["year"].unique())
    steps_per_hour = 60 / time_interval_min
    results = []

    for sim in range(n_sims):
        if progress_callback and (sim + 1) % max(1, n_sims // 20) == 0:
            progress_callback(sim + 1, n_sims)

        yr = int(np.random.choice(years))
        block = df[df["year"] == yr]

        # Pick random start point (by index, not timestamp arithmetic)
        if start_month is None:
            start_idx = np.random.randint(0, len(block))
        else:
            month_mask = block.index.month == start_month
            month_indices = np.where(month_mask)[0]
            if len(month_indices) == 0:
                start_idx = np.random.randint(0, len(block))
            else:
                start_idx = int(np.random.choice(month_indices))

        start_time = block.index[start_idx]
        current_idx = start_idx

        cal_mask = (
            calendar_mask_fn(block.index)
            if calendar_mask_fn is not None
            else np.ones(len(block), dtype=bool)
        )

        total_elapsed = 0
        total_wait = 0

        for t in tasks:
            cond_mask = build_condition_mask(block, t.thresholds, na_handling) & cal_mask
            required_steps = int(t.total_hours * steps_per_hour)

            if not split_mode:
                s, e, waiting = find_next_window(cond_mask, current_idx, required_steps)
                total_wait += waiting
                total_elapsed += waiting + required_steps
                current_idx = (e + 1) % len(block)
            else:
                e, waiting, worked = find_window_accumulated(
                    cond_mask, current_idx, required_steps
                )
                total_wait += waiting
                total_elapsed += waiting + worked
                current_idx = (e + 1) % len(block)

        elapsed_h = total_elapsed / steps_per_hour
        wait_h = total_wait / steps_per_hour

        results.append(
            {
                "sim": sim,
                "year_sample": yr,
                "start_time": start_time,
                "elapsed_hours": elapsed_h,
                "wait_hours": wait_h,
                "work_hours": elapsed_h - wait_h,
                "elapsed_days": elapsed_h / 24.0,
            }
        )

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def summarize_pxx(
    df: pd.DataFrame, p_list: List[int] | None = None
) -> pd.DataFrame:
    """Compute percentile summary statistics.

    Returns:
        DataFrame with columns ``Metric`` and ``Value_days``.
    """
    if p_list is None:
        p_list = [50, 75, 90]

    days = df["elapsed_days"]
    metrics = [f"P{p}" for p in p_list] + ["Mean", "Std", "Min", "Max"]
    values = [np.percentile(days, p) for p in p_list]
    values += [days.mean(), days.std(), days.min(), days.max()]

    return pd.DataFrame({"Metric": metrics, "Value_days": values})
