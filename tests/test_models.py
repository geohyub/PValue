"""Tests for pvalue.models."""

import pytest

from pvalue.models import SimulationConfig, Task


class TestTask:
    def test_basic_creation(self):
        t = Task(name="Install", duration_h=24, thresholds={"Hs": 1.5})
        assert t.name == "Install"
        assert t.total_hours == 24

    def test_total_hours_with_setup(self):
        t = Task(name="T", duration_h=10, thresholds={"Hs": 2.0}, setup_h=2, teardown_h=3)
        assert t.total_hours == 15

    def test_invalid_duration(self):
        with pytest.raises(ValueError, match="positive"):
            Task(name="T", duration_h=0, thresholds={"Hs": 1.0})

    def test_empty_thresholds(self):
        with pytest.raises(ValueError, match="threshold"):
            Task(name="T", duration_h=10, thresholds={})


class TestSimulationConfig:
    def test_defaults(self):
        cfg = SimulationConfig()
        assert cfg.n_sims == 1000
        assert cfg.na_handling == "permissive"
        assert cfg.pvals == [50, 75, 90]

    def test_invalid_na_handling(self):
        with pytest.raises(ValueError, match="na_handling"):
            SimulationConfig(na_handling="unknown")

    def test_invalid_month(self):
        with pytest.raises(ValueError, match="start_month"):
            SimulationConfig(start_month=13)

    def test_from_dict(self):
        data = {
            "tasks": [{"name": "A", "duration_h": 12, "thresholds": {"Hs": 1.5}}],
            "n_sims": 500,
            "split_mode": True,
        }
        cfg = SimulationConfig.from_dict(data)
        assert cfg.n_sims == 500
        assert cfg.split_mode is True
        assert len(cfg.tasks) == 1

    def test_from_dict_with_calendar(self):
        data = {
            "tasks": [],
            "calendar": ["custom", "weekdays", "8-18"],
        }
        cfg = SimulationConfig.from_dict(data)
        assert cfg.calendar_hours == (8, 18)

    def test_build_calendar_mask_fn_none(self):
        cfg = SimulationConfig()
        assert cfg.build_calendar_mask_fn() is None

    def test_build_calendar_mask_fn(self):
        import numpy as np
        import pandas as pd

        cfg = SimulationConfig(calendar_hours=(9, 17))
        fn = cfg.build_calendar_mask_fn()
        idx = pd.date_range("2020-01-01", periods=24, freq="h")
        mask = fn(idx)
        assert mask.sum() == 8  # hours 9-16
