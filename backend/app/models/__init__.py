"""SQLModel database tables for CarbonShift AI."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel

from app.core.time import now_utc

# ── Helper ────────────────────────────────────────────────────────────────────

def new_uuid() -> str:
    return str(uuid.uuid4())


# ── Sites ─────────────────────────────────────────────────────────────────────

class Site(SQLModel, table=True):
    __tablename__ = "sites"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    name: str
    region: str  # NR | WR | SR | ER | NER
    lat: float
    lon: float

    # Capacity per GPU type (JSON: {"A100": 8, "V100": 4, ...})
    gpu_capacity_json: str = Field(default="{}", sa_column=Column(Text))
    cpu_cores: int = 0
    power_cap_kw: float = 100.0

    # PUE model
    pue_base: float = 1.35
    pue_k: float = 0.012
    pue_temp_limit_c: float = 24.0

    # Allowed data classes (JSON list)
    allowed_classes_json: str = Field(default='["public","internal"]', sa_column=Column(Text))

    # Maintenance blackouts (JSON list of {start, end} dicts)
    maintenance_blackouts_json: str = Field(default="[]", sa_column=Column(Text))

    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


# ── Grid observations ──────────────────────────────────────────────────────────

class GridObservation(SQLModel, table=True):
    __tablename__ = "grid_observations"

    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime  # UTC hour start
    region: str
    ci_g_per_kwh: float
    share_solar: float = 0.0
    share_wind: float = 0.0
    share_hydro: float = 0.0
    share_nuclear: float = 0.0
    share_thermal: float = 0.0
    share_other: float = 0.0
    renewable_share: float = 0.0
    demand_mw: float = 0.0
    source: str = "twin"  # twin | electricitymaps | replay
    is_estimated: bool = True


# ── Forecasts ─────────────────────────────────────────────────────────────────

class Forecast(SQLModel, table=True):
    __tablename__ = "forecasts"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    issued_at: datetime  # UTC
    region: str
    target_ts: datetime  # UTC
    horizon_h: int
    ci_p10: float
    ci_p50: float
    ci_p90: float
    renewable_share_p50: float = 0.0
    model_version: str = "v0"


# ── Jobs ──────────────────────────────────────────────────────────────────────

class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    name: str
    archetype: str  # ml_training | ml_finetune | batch_inference | etl | ...
    team: str = "default"
    priority: int = 3  # 1..5
    status: str = "PENDING"  # PENDING | SCHEDULED | RUNNING | COMPLETED | INFEASIBLE | DEFERRED_BY_BUDGET

    release_ts: datetime  # UTC; earliest start
    deadline_ts: datetime  # UTC; must finish by
    duration_h: float

    # Resources
    gpus: int = 0
    gpu_type: Optional[str] = None  # A100 | V100 | T4 | H100
    cpu_cores: int = 0
    util: float = 0.7
    preemptible: bool = False
    max_interruptions: int = 0
    checkpoint_overhead_pct: float = 0.02

    # Site constraints
    allowed_sites_json: str = Field(default="[]", sa_column=Column(Text))  # [] = all
    data_residency: str = "india_only"
    data_class: str = "internal"  # public | internal | restricted
    green_only: bool = False
    data_gb: float = 0.0
    home_site: Optional[str] = None  # preferred site

    # Computed estimates
    energy_kwh: Optional[float] = None
    power_kw: Optional[float] = None

    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class JobDependency(SQLModel, table=True):
    __tablename__ = "job_dependencies"

    job_id: str = Field(foreign_key="jobs.id", primary_key=True)
    depends_on_job_id: str = Field(foreign_key="jobs.id", primary_key=True)


# ── Schedule runs ─────────────────────────────────────────────────────────────

class ScheduleRun(SQLModel, table=True):
    __tablename__ = "schedule_runs"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    parent_run_id: Optional[str] = Field(default=None, foreign_key="schedule_runs.id")
    created_at: datetime = Field(default_factory=now_utc)

    strategy: str = "cpsat"  # fifo | edf | greedy | cpsat
    horizon_start: datetime
    horizon_end: datetime
    risk_lambda: float = 0.3
    allow_spatial: bool = True
    carbon_budget_kg: Optional[float] = None

    status: str = "PENDING"  # PENDING | OPTIMAL | FEASIBLE | INFEASIBLE | FALLBACK
    fallback_reason: Optional[str] = None
    objective: Optional[float] = None
    best_bound: Optional[float] = None
    gap: Optional[float] = None
    solve_seconds: Optional[float] = None
    num_variables: Optional[int] = None

    # Carbon accounting
    planned_carbon_kg: Optional[float] = None
    baseline_carbon_kg: Optional[float] = None  # FIFO baseline
    savings_pct: Optional[float] = None
    renewable_share_plan: Optional[float] = None
    renewable_share_baseline: Optional[float] = None
    sla_on_time: Optional[int] = None
    sla_total: Optional[int] = None

    config_snapshot_json: str = Field(default="{}", sa_column=Column(Text))


class ScheduleItem(SQLModel, table=True):
    __tablename__ = "schedule_items"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    run_id: str = Field(foreign_key="schedule_runs.id")
    job_id: str = Field(foreign_key="jobs.id")
    site_id: str = Field(foreign_key="sites.id")
    segment_idx: int = 0  # 0 for non-preempted; 0,1,2... for segments

    start_ts: datetime  # UTC
    end_ts: datetime  # UTC
    planned_carbon_g: float = 0.0
    planned_energy_kwh: float = 0.0

    reason: Optional[str] = None
    reason_facts_json: str = Field(default="{}", sa_column=Column(Text))
    risk_flag: str = "low"  # low | medium | high
    frozen: bool = False  # True for jobs frozen during rolling replan


# ── Executions (Plan vs Actual) ───────────────────────────────────────────────

class Execution(SQLModel, table=True):
    __tablename__ = "executions"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    run_id: str = Field(foreign_key="schedule_runs.id")
    job_id: str = Field(foreign_key="jobs.id")

    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    actual_carbon_g: Optional[float] = None
    actual_energy_kwh: Optional[float] = None
    deadline_met: Optional[bool] = None


# ── Scenarios ─────────────────────────────────────────────────────────────────

class Scenario(SQLModel, table=True):
    __tablename__ = "scenarios"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    name: str
    params_json: str = Field(default="{}", sa_column=Column(Text))
    result_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=now_utc)


# ── Carbon ledger ─────────────────────────────────────────────────────────────

class LedgerEntry(SQLModel, table=True):
    __tablename__ = "ledger"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    ts: datetime = Field(default_factory=now_utc)
    run_id: str = Field(foreign_key="schedule_runs.id")
    kg_saved_vs_fifo: float = 0.0
    cumulative_kg_saved: float = 0.0
    is_realized: bool = False  # True when based on actual replay data


# ── Config (key-value store) ──────────────────────────────────────────────────

class ConfigEntry(SQLModel, table=True):
    __tablename__ = "config_entries"

    key: str = Field(primary_key=True)
    value_json: str = Field(default="null", sa_column=Column(Text))
    updated_at: datetime = Field(default_factory=now_utc)
