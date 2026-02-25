"""Tests for pvalue.simulation."""

import numpy as np
import pandas as pd
import pytest

from pvalue.models import Task
from pvalue.simulation import (
    find_next_window,
    find_window_accumulated,
    simulate_campaign,
    summarize_pxx,
)


class TestFindNextWindow:
    def test_immediate_window(self):
        mask = np.array([True, True, True, True, True])
        start, end, wait = find_next_window(mask, 0, 3)
        assert start == 0
        assert end == 2
        assert wait == 0

    def test_delayed_window(self):
        mask = np.array([False, False, True, True, True])
        start, end, wait = find_next_window(mask, 0, 3)
        assert start == 2
        assert wait == 2

    def test_wrap_around(self):
        mask = np.array([True, True, False, False, True])
        start, end, wait = find_next_window(mask, 3, 3)
        assert wait > 0  # must wait past the False values

    def test_no_window_raises(self):
        mask = np.array([True, False, True, False, True])
        with pytest.raises(RuntimeError, match="No feasible"):
            find_next_window(mask, 0, 3)


class TestFindWindowAccumulated:
    def test_split_work(self):
        mask = np.array([True, False, True, False, True])
        end, waited, worked = find_window_accumulated(mask, 0, 3)
        assert worked == 3
        assert waited == 2

    def test_continuous_work(self):
        mask = np.ones(10, dtype=bool)
        end, waited, worked = find_window_accumulated(mask, 0, 5)
        assert worked == 5
        assert waited == 0

    def test_insufficient_raises(self):
        mask = np.array([True, False, False, False, False])
        with pytest.raises(RuntimeError, match="No feasible"):
            find_window_accumulated(mask, 0, 3)


def _make_metocean(n=8760, freq="h"):
    """One year of synthetic hourly metocean data."""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2020-01-01", periods=n, freq=freq)
    return pd.DataFrame({"Hs": rng.uniform(0.3, 3.0, n), "Wind": rng.uniform(1, 15, n)}, index=idx)


class TestSimulateCampaign:
    def test_basic_run(self):
        df = _make_metocean()
        tasks = [Task("T1", duration_h=6, thresholds={"Hs": 2.5, "Wind": 14})]
        res = simulate_campaign(df, tasks, n_sims=50, seed=42)
        assert len(res) == 50
        assert "elapsed_days" in res.columns
        assert (res["elapsed_days"] > 0).all()

    def test_split_mode(self):
        df = _make_metocean()
        tasks = [Task("T1", duration_h=24, thresholds={"Hs": 1.5})]
        res = simulate_campaign(df, tasks, n_sims=30, split_mode=True, seed=42)
        assert len(res) == 30

    def test_start_month(self):
        df = _make_metocean()
        tasks = [Task("T1", duration_h=12, thresholds={"Hs": 2.5})]
        res = simulate_campaign(df, tasks, n_sims=20, start_month=6, seed=42)
        assert len(res) == 20

    def test_progress_callback(self):
        df = _make_metocean()
        tasks = [Task("T1", duration_h=6, thresholds={"Hs": 3.0})]
        calls = []
        res = simulate_campaign(
            df, tasks, n_sims=100, seed=42,
            progress_callback=lambda c, t: calls.append((c, t)),
        )
        assert len(calls) > 0


class TestSummarizePxx:
    def test_default_percentiles(self):
        df = pd.DataFrame({"elapsed_days": np.random.default_rng(0).uniform(5, 30, 500)})
        summary = summarize_pxx(df)
        assert list(summary["Metric"]) == ["P50", "P75", "P90", "Mean", "Std", "Min", "Max"]
        assert len(summary) == 7

    def test_custom_percentiles(self):
        df = pd.DataFrame({"elapsed_days": np.arange(1, 101)})
        summary = summarize_pxx(df, [10, 50, 99])
        assert summary["Metric"].iloc[0] == "P10"
        assert summary["Metric"].iloc[2] == "P99"
