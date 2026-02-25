"""Core data models for the Marine P-Value Simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Task:
    """A single marine operation task with weather constraints.

    Attributes:
        name: Human-readable task name.
        duration_h: Net working duration in hours.
        thresholds: Weather parameter limits (e.g. ``{"Hs": 1.5, "Wind": 10}``).
            Values above these thresholds block work.
        setup_h: Setup time in hours before work begins.
        teardown_h: Teardown time in hours after work ends.
    """

    name: str
    duration_h: int
    thresholds: Dict[str, float]
    setup_h: int = 0
    teardown_h: int = 0

    @property
    def total_hours(self) -> int:
        """Total required hours including setup and teardown."""
        return self.setup_h + self.duration_h + self.teardown_h

    def __post_init__(self) -> None:
        if self.duration_h <= 0:
            raise ValueError(f"duration_h must be positive, got {self.duration_h}")
        if not self.thresholds:
            raise ValueError("At least one threshold must be specified")


@dataclass
class SimulationConfig:
    """Configuration for a Monte Carlo simulation run.

    Attributes:
        tasks: List of task definitions.
        n_sims: Number of Monte Carlo iterations.
        start_month: Restrict simulation starts to this month (1-12), or None for any.
        split_mode: If True, use accumulated (split) work mode instead of continuous.
        na_handling: How to treat missing data — ``"permissive"`` (work allowed)
            or ``"conservative"`` (work blocked).
        pvals: Percentiles to report (e.g. ``[50, 75, 90]``).
        calendar_hours: Tuple of ``(start_hour, end_hour)`` or None for 24h operation.
        seed: Random seed for reproducibility.
    """

    tasks: List[Task] = field(default_factory=list)
    n_sims: int = 1000
    start_month: Optional[int] = None
    split_mode: bool = False
    na_handling: str = "permissive"
    pvals: List[int] = field(default_factory=lambda: [50, 75, 90])
    calendar_hours: Optional[tuple] = None
    seed: Optional[int] = 7

    def __post_init__(self) -> None:
        if self.na_handling not in ("permissive", "conservative"):
            raise ValueError(f"na_handling must be 'permissive' or 'conservative', got '{self.na_handling}'")
        if self.start_month is not None and not 1 <= self.start_month <= 12:
            raise ValueError(f"start_month must be 1-12, got {self.start_month}")
        if any(not 0 <= p <= 100 for p in self.pvals):
            raise ValueError(f"pvals must be between 0 and 100, got {self.pvals}")

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationConfig":
        """Create config from a dictionary (e.g. parsed JSON)."""
        tasks = [Task(**t) if isinstance(t, dict) else t for t in data.get("tasks", [])]
        calendar = data.get("calendar")
        calendar_hours = None
        if calendar and len(calendar) >= 3 and calendar[0] == "custom":
            sh, eh = map(int, calendar[2].split("-"))
            calendar_hours = (sh, eh)
        return cls(
            tasks=tasks,
            n_sims=data.get("n_sims", 1000),
            start_month=data.get("start_month"),
            split_mode=data.get("split_mode", False),
            na_handling=data.get("na_handling", "permissive"),
            pvals=data.get("pvals", [50, 75, 90]),
            calendar_hours=calendar_hours,
            seed=data.get("seed", 7),
        )

    def build_calendar_mask_fn(self):
        """Return a callable that creates a boolean mask for business hours, or None."""
        if self.calendar_hours is None:
            return None
        sh, eh = self.calendar_hours

        def _mask(index):
            import numpy as np

            hrs = index.hour
            return (hrs >= sh) & (hrs < eh)

        return _mask
