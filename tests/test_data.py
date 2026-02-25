"""Tests for pvalue.data."""

import numpy as np
import pandas as pd
import pytest

from pvalue.data import build_condition_mask, get_time_interval_minutes, validate_metocean


def _make_df(n=100, freq="h", hs_range=(0.5, 3.0), wind_range=(2, 15)):
    """Create a synthetic metocean DataFrame for testing."""
    rng = np.random.default_rng(42)
    idx = pd.date_range("2020-01-01", periods=n, freq=freq)
    return pd.DataFrame(
        {
            "Hs": rng.uniform(*hs_range, size=n),
            "Wind": rng.uniform(*wind_range, size=n),
        },
        index=idx,
    )


class TestValidateMetocean:
    def test_valid(self):
        df = _make_df()
        ok, msg = validate_metocean(df)
        assert ok
        assert msg == "OK"

    def test_missing_column(self):
        df = _make_df().drop(columns=["Hs"])
        ok, msg = validate_metocean(df)
        assert not ok
        assert "Hs" in msg

    def test_non_datetime_index(self):
        df = _make_df().reset_index(drop=True)
        ok, msg = validate_metocean(df)
        assert not ok
        assert "DatetimeIndex" in msg

    def test_duplicate_timestamps(self):
        df = _make_df(n=50)
        df = pd.concat([df, df.iloc[:1]])
        ok, msg = validate_metocean(df)
        assert not ok
        assert "Duplicate" in msg

    def test_too_many_na(self):
        df = _make_df(n=100)
        df.loc[df.index[:60], "Hs"] = np.nan
        ok, msg = validate_metocean(df)
        assert not ok
        assert "missing" in msg.lower()

    def test_out_of_range(self):
        df = _make_df(n=50)
        df.iloc[0, 0] = -1.0  # Hs < 0
        ok, msg = validate_metocean(df)
        assert not ok

    def test_too_short(self):
        df = _make_df(n=10)
        ok, msg = validate_metocean(df)
        assert not ok
        assert "Insufficient" in msg


class TestGetTimeInterval:
    def test_hourly(self):
        df = _make_df(freq="h")
        assert get_time_interval_minutes(df) == 60

    def test_10min(self):
        df = _make_df(freq="10min")
        assert get_time_interval_minutes(df) == 10


class TestBuildConditionMask:
    def test_all_pass(self):
        df = _make_df(n=10, hs_range=(0.1, 0.5), wind_range=(1, 3))
        mask = build_condition_mask(df, {"Hs": 5.0, "Wind": 20.0})
        assert mask.all()

    def test_all_fail(self):
        df = _make_df(n=10, hs_range=(5.0, 10.0), wind_range=(1, 3))
        mask = build_condition_mask(df, {"Hs": 1.0})
        assert not mask.any()

    def test_permissive_na(self):
        df = _make_df(n=10)
        df.iloc[0, 0] = np.nan
        mask = build_condition_mask(df, {"Hs": 5.0}, na_handling="permissive")
        assert mask[0]

    def test_conservative_na(self):
        df = _make_df(n=10)
        df.iloc[0, 0] = np.nan
        mask = build_condition_mask(df, {"Hs": 5.0}, na_handling="conservative")
        assert not mask[0]

    def test_missing_column_raises(self):
        df = _make_df(n=10)
        with pytest.raises(KeyError, match="CurrentSpeed"):
            build_condition_mask(df, {"CurrentSpeed": 1.0})
