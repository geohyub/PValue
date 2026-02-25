"""Data loading, validation, and preprocessing utilities."""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_VALID_RANGES = {
    "Hs": (0, 20),    # significant wave height [m]
    "Wind": (0, 70),   # wind speed [m/s]
}


def validate_metocean(
    df: pd.DataFrame,
    required_cols: List[str] | None = None,
) -> Tuple[bool, str]:
    """Validate a metocean DataFrame.

    Returns:
        ``(True, "OK")`` on success, ``(False, reason)`` on failure.
    """
    if required_cols is None:
        required_cols = ["Hs", "Wind"]

    for col in required_cols:
        if col not in df.columns:
            return False, f"Required column missing: {col}"

    if not isinstance(df.index, pd.DatetimeIndex):
        return False, "Index must be a DatetimeIndex"

    if df.index.duplicated().any():
        return False, "Duplicate timestamps detected"

    # Warn about irregular intervals (non-blocking)
    intervals = df.index.to_series().diff()[1:].value_counts()
    if len(intervals) > 2:
        logger.warning(
            "Irregular time intervals detected — most common: %s (%d records)",
            intervals.index[0],
            intervals.values[0],
        )

    for col in required_cols:
        na_ratio = df[col].isna().sum() / len(df) * 100
        if na_ratio > 50:
            return False, f"Too many missing values in {col}: {na_ratio:.1f}%"

    for col in required_cols:
        if col in _VALID_RANGES:
            lo, hi = _VALID_RANGES[col]
            vals = df[col].dropna()
            if (vals < lo).any() or (vals > hi).any():
                return False, f"{col} values out of valid range ({lo}–{hi})"

    if len(df) < 24:
        return False, f"Insufficient data: {len(df)} records (minimum 24)"

    return True, "OK"


# ---------------------------------------------------------------------------
# Time interval detection
# ---------------------------------------------------------------------------

def get_time_interval_minutes(df: pd.DataFrame) -> int:
    """Detect the most common time interval in *minutes*."""
    intervals = df.index.to_series().diff()[1:].value_counts()
    return int(intervals.index[0].total_seconds() / 60)


# ---------------------------------------------------------------------------
# Condition mask
# ---------------------------------------------------------------------------

def build_condition_mask(
    block: pd.DataFrame,
    thresholds: dict[str, float],
    na_handling: str = "permissive",
) -> np.ndarray:
    """Create a boolean array where ``True`` = work is feasible.

    Args:
        block: Metocean data block.
        thresholds: Column-name → maximum-allowed-value mapping.
        na_handling: ``"permissive"`` treats NaN as *work-OK*;
            ``"conservative"`` treats NaN as *work-blocked*.
    """
    mask = np.ones(len(block), dtype=bool)

    for col, thr in thresholds.items():
        if col not in block.columns:
            raise KeyError(f"Column '{col}' not found in metocean data")
        values = block[col].values.astype(float)
        cond = values <= thr
        na_mask = np.isnan(values)
        fill = na_handling == "permissive"
        cond = np.where(na_mask, fill, cond)
        mask &= cond

    return mask


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

_ENCODINGS = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]


def load_csv(
    path: str,
    csv_type: str = "general",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Load a metocean CSV file.

    Args:
        path: Path to the CSV file.
        csv_type: ``"general"`` for standard format, ``"hindcast"`` for ERA5.
        start_date: Optional start date filter (hindcast only).
        end_date: Optional end date filter (hindcast only).

    Raises:
        ValueError: If loading fails with all attempted encodings.
    """
    loader = _load_hindcast if csv_type == "hindcast" else _load_general

    for enc in _ENCODINGS:
        try:
            df = loader(path, enc, start_date, end_date)
            if df is not None:
                logger.info(
                    "Loaded %s (%d records, encoding=%s)", path, len(df), enc
                )
                return df
        except Exception:
            continue

    raise ValueError(f"Failed to load CSV: {path}")


def _load_general(
    path: str, encoding: str, start_date=None, end_date=None
) -> pd.DataFrame | None:
    df = pd.read_csv(path, encoding=encoding, parse_dates=["timestamp"])
    df = df.set_index("timestamp")
    return df


def _load_hindcast(
    path: str, encoding: str, start_date=None, end_date=None
) -> pd.DataFrame | None:
    df_raw = pd.read_csv(path, skiprows=5, encoding=encoding)
    df_raw.columns = [c.strip().replace("[", "").replace("]", "") for c in df_raw.columns]

    time_col = df_raw.columns[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            df_raw[time_col] = pd.to_datetime(df_raw[time_col], format=fmt)
            break
        except (ValueError, TypeError):
            continue
    else:
        return None

    df_raw = df_raw.set_index(time_col)

    wind_col = hs_col = None
    for col in df_raw.columns:
        low = col.lower()
        if "10m" in low and "wind" in low:
            wind_col = col
        if "hs" in low and "m" in low:
            hs_col = col

    if not wind_col or not hs_col:
        return None

    df = df_raw[[wind_col, hs_col]].copy()
    df.columns = ["Wind", "Hs"]
    df = df.apply(pd.to_numeric, errors="coerce")

    if start_date:
        df = df[df.index >= start_date]
    if end_date:
        df = df[df.index <= end_date]

    return df
