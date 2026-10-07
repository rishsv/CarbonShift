"""Shared planning data structures for all schedulers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class PlanningJob:
    """Normalized job representation for the optimizer."""
    id: str
    name: str
    archetype: str
    priority: int  # 1..5
    release_slot: int  # 0-based slot index
    deadline_slot: int  # inclusive slot (last allowed slot)
    duration_slots: int
    power_kw: float
    energy_kwh: float  # per duration (full job)
    preemptible: bool
    max_interruptions: int
    checkpoint_overhead_pct: float
    allowed_sites: list[str]  # site IDs; empty = all eligible
    data_class: str
    green_only: bool
    data_gb: float
    home_site: Optional[str]
    depends_on: list[str]  # job IDs
    # Computed
    buffer_slots: int = 0
    # GPU demands (per GPU type)
    gpu_demand: dict[str, int] = field(default_factory=dict)  # {"A100": 4}
    cpu_units: int = 0  # ceil(cores/8)


@dataclass
class PlanningSlot:
    """Per-site, per-slot arrays."""
    site_id: str
    slot: int
    ci_p10: float
    ci_p50: float
    ci_p90: float
    ci_hat: float  # risk-adjusted
    renewable_share: float
    pue: float
    price_inr_per_kwh: float
    # Capacity remaining per GPU type
    gpu_capacity: dict[str, int] = field(default_factory=dict)
    cpu_units: int = 0
    power_cap_kw: float = 100.0
    blackout: bool = False


@dataclass
class Segment:
    """A contiguous time block assigned to a job."""
    job_id: str
    site_id: str
    start_slot: int  # inclusive
    end_slot: int    # exclusive
    segment_idx: int = 0


@dataclass
class ScheduleResult:
    """Output of any scheduling strategy."""
    strategy: str
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | FALLBACK | GREEDY
    segments: list[Segment] = field(default_factory=list)
    infeasible_jobs: list[dict] = field(default_factory=list)  # {id, name, reason, fix}
    objective: Optional[float] = None
    best_bound: Optional[float] = None
    gap: Optional[float] = None
    solve_seconds: Optional[float] = None
    num_variables: Optional[int] = None
    fallback_reason: Optional[str] = None


@dataclass
class PlanningProblem:
    """Full planning problem passed to any scheduler."""
    jobs: list[PlanningJob]
    # Per site, per slot arrays (indexed [site_idx][slot])
    sites: list[str]  # site IDs in order
    horizon_slots: int
    horizon_start_utc: object  # datetime
    slot_minutes: int = 60

    # Arrays shape: (n_sites, horizon_slots)
    ci_p10: np.ndarray = field(default_factory=lambda: np.array([[]]))
    ci_p50: np.ndarray = field(default_factory=lambda: np.array([[]]))
    ci_p90: np.ndarray = field(default_factory=lambda: np.array([[]]))
    ci_hat: np.ndarray = field(default_factory=lambda: np.array([[]]))
    renewable_share: np.ndarray = field(default_factory=lambda: np.array([[]]))
    pue: np.ndarray = field(default_factory=lambda: np.array([[]]))
    price: np.ndarray = field(default_factory=lambda: np.array([[]]))
    power_cap: np.ndarray = field(default_factory=lambda: np.array([[]]))
    blackout: np.ndarray = field(default_factory=lambda: np.array([[]], dtype=bool))

    # GPU capacity arrays: dict[gpu_type] -> ndarray (n_sites, horizon_slots)
    gpu_capacity: dict = field(default_factory=dict)
    cpu_units: np.ndarray = field(default_factory=lambda: np.array([[]]))

    # Config
    risk_lambda: float = 0.3
    allow_spatial: bool = True
    carbon_budget_kg: Optional[float] = None
    weights: dict = field(default_factory=dict)

    def site_index(self, site_id: str) -> int:
        return self.sites.index(site_id)
