"""Pydantic v2 request/response schemas for the CarbonShift API."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Sites ─────────────────────────────────────────────────────────────────────

class SiteCreate(BaseModel):
    id: str
    name: str
    region: str
    lat: float
    lon: float
    gpu_capacity: dict[str, int] = Field(default_factory=dict)
    cpu_cores: int = 0
    power_cap_kw: float = 100.0
    pue_base: float = 1.35
    pue_k: float = 0.012
    pue_temp_limit_c: float = 24.0
    allowed_classes: list[str] = Field(default_factory=lambda: ["public", "internal"])
    notes: Optional[str] = None


class SiteRead(SiteCreate):
    created_at: datetime
    updated_at: datetime


# ── Jobs ──────────────────────────────────────────────────────────────────────

VALID_ARCHETYPES = {
    "ml_training", "ml_finetune", "batch_inference", "etl",
    "render_transcode", "backup", "simulation", "ci_build", "report",
}
VALID_GPU_TYPES = {"T4", "V100", "A100", "H100"}
VALID_RESIDENCY = {"india_only", "site_pinned", "region_pinned"}
VALID_DATA_CLASSES = {"public", "internal", "restricted"}


class JobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    archetype: str
    team: str = "default"
    priority: int = Field(default=3, ge=1, le=5)
    release_ts: datetime
    deadline_ts: datetime
    duration_h: float = Field(gt=0, le=720)
    gpus: int = Field(default=0, ge=0)
    gpu_type: Optional[str] = None
    cpu_cores: int = Field(default=0, ge=0)
    util: float = Field(default=0.7, ge=0.0, le=1.0)
    preemptible: bool = False
    max_interruptions: int = Field(default=0, ge=0, le=5)
    checkpoint_overhead_pct: float = Field(default=0.02, ge=0.0, le=0.5)
    allowed_sites: list[str] = Field(default_factory=list)
    data_residency: str = "india_only"
    data_class: str = "internal"
    green_only: bool = False
    data_gb: float = Field(default=0.0, ge=0.0)
    home_site: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)  # job IDs

    @field_validator("archetype")
    @classmethod
    def validate_archetype(cls, v: str) -> str:
        if v not in VALID_ARCHETYPES:
            raise ValueError(f"archetype must be one of {sorted(VALID_ARCHETYPES)}")
        return v

    @field_validator("gpu_type")
    @classmethod
    def validate_gpu_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_GPU_TYPES:
            raise ValueError(f"gpu_type must be one of {sorted(VALID_GPU_TYPES)}")
        return v

    @field_validator("data_residency")
    @classmethod
    def validate_residency(cls, v: str) -> str:
        if v not in VALID_RESIDENCY:
            raise ValueError(f"data_residency must be one of {sorted(VALID_RESIDENCY)}")
        return v

    @field_validator("data_class")
    @classmethod
    def validate_data_class(cls, v: str) -> str:
        if v not in VALID_DATA_CLASSES:
            raise ValueError(f"data_class must be one of {sorted(VALID_DATA_CLASSES)}")
        return v

    @model_validator(mode="after")
    def validate_deadline_after_release(self) -> "JobCreate":
        if self.deadline_ts <= self.release_ts:
            raise ValueError("deadline_ts must be after release_ts")
        import math
        slack_h = (self.deadline_ts - self.release_ts).total_seconds() / 3600
        if slack_h < self.duration_h:
            raise ValueError(
                f"deadline_ts - release_ts ({slack_h:.1f}h) is less than duration_h ({self.duration_h}h). "
                f"The job cannot finish before its deadline."
            )
        return self

    @model_validator(mode="after")
    def validate_preemption(self) -> "JobCreate":
        if not self.preemptible and self.max_interruptions > 0:
            raise ValueError("max_interruptions must be 0 for non-preemptible jobs")
        return self

    @model_validator(mode="after")
    def validate_resources(self) -> "JobCreate":
        if self.gpus > 0 and not self.gpu_type:
            raise ValueError("gpu_type is required when gpus > 0")
        if self.gpus == 0 and self.cpu_cores == 0:
            raise ValueError("Job must request at least one GPU or CPU core")
        return self


class JobRead(BaseModel):
    id: str
    name: str
    archetype: str
    team: str
    priority: int
    status: str
    release_ts: datetime
    deadline_ts: datetime
    duration_h: float
    gpus: int
    gpu_type: Optional[str]
    cpu_cores: int
    util: float
    preemptible: bool
    max_interruptions: int
    allowed_sites: list[str]
    data_residency: str
    data_class: str
    green_only: bool
    data_gb: float
    home_site: Optional[str]
    energy_kwh: Optional[float]
    power_kw: Optional[float]
    created_at: datetime

    @property
    def slack_h(self) -> float:
        return (self.deadline_ts - self.release_ts).total_seconds() / 3600 - self.duration_h


class JobEstimateRequest(BaseModel):
    archetype: str
    gpus: int = 0
    gpu_type: Optional[str] = None
    cpu_cores: int = 0
    util: float = 0.7
    duration_h: float = 1.0
    site_id: Optional[str] = None
    deadline_ts: Optional[datetime] = None
    release_ts: Optional[datetime] = None


class JobEstimateResponse(BaseModel):
    power_kw: float
    it_energy_kwh: float
    facility_energy_kwh: float
    pue_used: float
    carbon_if_run_now_g: Optional[float] = None
    carbon_at_best_window_g: Optional[float] = None
    carbon_slack_pct: Optional[float] = None


# ── Forecast ──────────────────────────────────────────────────────────────────

class ForecastPoint(BaseModel):
    target_ts: datetime
    horizon_h: int
    ci_p10: float
    ci_p50: float
    ci_p90: float
    renewable_share_p50: float
    is_estimated: bool = True
    model_version: str = "twin"


class ForecastResponse(BaseModel):
    region: str
    issued_at: datetime
    points: list[ForecastPoint]
    data_source: str


class GreenWindow(BaseModel):
    site_id: str
    region: str
    start_ts: datetime
    end_ts: datetime
    duration_h: float
    avg_ci_p50: float
    avg_renewable_share: float
    delta_vs_now_pct: float


# ── Schedule ──────────────────────────────────────────────────────────────────

class ScheduleRunRequest(BaseModel):
    strategy: str = "cpsat"
    horizon_hours: int = Field(default=48, ge=12, le=168)
    risk_lambda: float = Field(default=0.3, ge=0.0, le=1.0)
    allow_spatial: bool = True
    carbon_budget_kg: Optional[float] = None
    preset: Optional[str] = None  # carbon_first | balanced | deadline_first
    solver_seconds: Optional[int] = Field(default=None, ge=5, le=120)

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        valid = {"fifo", "edf", "greedy", "cpsat"}
        if v not in valid:
            raise ValueError(f"strategy must be one of {sorted(valid)}")
        return v


class SegmentRead(BaseModel):
    start: datetime
    end: datetime
    carbon_g: float
    energy_kwh: float


class ScheduleItemRead(BaseModel):
    job_id: str
    job_name: str
    site_id: str
    segments: list[SegmentRead]
    planned_carbon_g: float
    planned_energy_kwh: float
    reason: Optional[str]
    risk_flag: str
    frozen: bool


class InfeasibleJobRead(BaseModel):
    job_id: str
    job_name: str
    reason: str
    suggested_fix: str


class ConstraintStatus(BaseModel):
    constraint: str
    label: str
    passed: bool
    violations: int = 0


class ScheduleRunSummary(BaseModel):
    run_id: str
    strategy: str
    status: str
    gap: Optional[float]
    solve_seconds: Optional[float]
    planned_carbon_kg: float
    baseline_carbon_kg: float  # FIFO
    savings_pct: float
    renewable_share: dict[str, float]  # {"plan": 0.41, "baseline": 0.29}
    sla: dict[str, int]  # {"on_time": 24, "total": 24}
    items: list[ScheduleItemRead]
    infeasible: list[InfeasibleJobRead]
    constraints_status: list[ConstraintStatus]
    fallback_reason: Optional[str] = None


class CompareResponse(BaseModel):
    run_id: str
    horizon_start: datetime
    horizon_end: datetime
    strategies: dict[str, dict[str, Any]]  # strategy → metrics


# ── Explain / Decision Card ────────────────────────────────────────────────────

class AlternativeWindow(BaseModel):
    start: datetime
    end: datetime
    avg_ci: float
    carbon_g: float
    delta_pct: float


class DecisionCard(BaseModel):
    job_id: str
    job_name: str
    site_id: str
    shift_hours: float
    ci_at_release: float
    ci_at_start: float
    ci_reduction_pct: float
    slack_before_deadline_h: float
    site_reason: str
    binding_constraint: str
    alternatives: list[AlternativeWindow]
    what_would_change: list[str]
    reason_sentence: str
    llm_polished: bool = False
    risk_flag: str


# ── Simulation ────────────────────────────────────────────────────────────────

class WhatIfRequest(BaseModel):
    run_id: str
    solar_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    wind_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    deadline_extension_h: float = Field(default=0.0, ge=0.0, le=48.0)
    capacity_change_pct: float = Field(default=0.0, ge=-50.0, le=100.0)
    preemptible_share_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    flexibility_share_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    risk_lambda: float = Field(default=0.3, ge=0.0, le=1.0)
    allow_spatial: bool = True
    carbon_budget_kg: Optional[float] = None


class WhatIfResponse(BaseModel):
    delta_carbon_kg: float
    delta_savings_pct: float
    delta_renewable_share: float
    new_sla: dict[str, int]
    new_carbon_kg: float
    new_savings_pct: float


class ReplayRequest(BaseModel):
    run_id: str
    speed: float = Field(default=60.0, ge=1.0, le=3600.0)  # sim hours per real second
    replan_policy: str = "none"  # none | on_drift | hourly
    drift_threshold_pct: float = 15.0
    seed: int = 42


# ── Impact ────────────────────────────────────────────────────────────────────

class ImpactResponse(BaseModel):
    total_kg_saved: float
    is_realized: bool
    renewable_share_avg: float
    sla_rate: float
    equiv_km_driven: float
    equiv_tree_years: float
    equiv_smartphone_charges: float
    indicative_inr_saved: Optional[float] = None
    runs_count: int


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    data_source: str
    forecaster_version: str
    db_ok: bool
    configs_ok: dict[str, bool]
