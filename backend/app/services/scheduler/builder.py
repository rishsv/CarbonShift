"""Builder for converting DB state + forecasts into a PlanningProblem."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import numpy as np

from app.core.config import load_tariffs
from app.core.time import (
    floor_hour_utc,
    floor_slot_utc,
    ist_hour,
    slot_index,
    to_ist,
    to_utc,
)
from app.models import Job, Site
from app.services.forecaster import get_forecaster
from app.services.scheduler.types import PlanningJob, PlanningProblem


def build_problem(
    jobs: list[Job],
    sites: list[Site],
    horizon_start: datetime,
    horizon_hours: int = 48,
    slot_minutes: int = 60,
    risk_lambda: float = 0.3,
    allow_spatial: bool = True,
    weights: dict | None = None,
    carbon_budget_kg: float | None = None,
    job_deps: dict[str, list[str]] | None = None,
) -> PlanningProblem:
    """Build a PlanningProblem from DB models."""
    job_deps = job_deps or {}
    horizon_start_utc = floor_slot_utc(horizon_start, slot_minutes)
    horizon_slots = int(horizon_hours * 60 / slot_minutes)

    # 1. Map Sites
    site_ids = [s.id for s in sites]
    n_sites = len(sites)

    problem = PlanningProblem(
        jobs=[],
        sites=site_ids,
        horizon_slots=horizon_slots,
        horizon_start_utc=horizon_start_utc,
        slot_minutes=slot_minutes,
        risk_lambda=risk_lambda,
        allow_spatial=allow_spatial,
        weights=weights or {},
        carbon_budget_kg=carbon_budget_kg,
    )

    # 2. Build Site capacity and cost arrays
    problem.cpu_units = np.zeros((n_sites, horizon_slots), dtype=int)
    problem.power_cap = np.zeros((n_sites, horizon_slots), dtype=float)
    problem.pue = np.zeros((n_sites, horizon_slots), dtype=float)
    problem.blackout = np.zeros((n_sites, horizon_slots), dtype=bool)
    problem.price = np.zeros((n_sites, horizon_slots), dtype=float)

    tariffs = load_tariffs()
    forecaster = get_forecaster()
    forecasts = {}  # Cache forecast by region

    # Initialize GPU capacities dynamically based on available types
    gpu_types = set()
    for s in sites:
        gpu_cap = json.loads(s.gpu_capacity_json)
        gpu_types.update(gpu_cap.keys())
    for gt in gpu_types:
        problem.gpu_capacity[gt] = np.zeros((n_sites, horizon_slots), dtype=int)

    for si, site in enumerate(sites):
        # Fetch or get forecast
        if site.region not in forecasts:
            df = forecaster.forecast(site.region, horizon_start_utc, horizon_hours)
            forecasts[site.region] = df
        df = forecasts[site.region]

        gpu_cap = json.loads(site.gpu_capacity_json)
        for gt, cap in gpu_cap.items():
            problem.gpu_capacity[gt][si, :] = cap
        problem.cpu_units[si, :] = site.cpu_cores // 8  # Simplified unit mapping
        problem.power_cap[si, :] = site.power_cap_kw

        # Blackouts
        blackouts = json.loads(site.maintenance_blackouts_json)
        for b in blackouts:
            try:
                b_start = to_utc(datetime.fromisoformat(b["start"]))
                b_end = to_utc(datetime.fromisoformat(b["end"]))
                start_s = max(0, slot_index(b_start, horizon_start_utc, slot_minutes))
                end_s = min(horizon_slots, slot_index(b_end, horizon_start_utc, slot_minutes))
                if start_s < horizon_slots and end_s > 0:
                    problem.blackout[si, start_s:end_s] = True
            except (ValueError, KeyError):
                pass

        # Time-based arrays (pue varies by ambient temp, price by ToD)
        for t in range(horizon_slots):
            ts = horizon_start_utc + timedelta(minutes=t * slot_minutes)
            h = ist_hour(ts)

            # PUE simple ambient model
            # Let's say ambient temp peaks at 14h IST
            temp = 28.0 + 8.0 * np.sin(np.pi * (h - 8) / 12) if 8 <= h <= 20 else 24.0
            problem.pue[si, t] = site.pue_base + site.pue_k * max(0.0, temp - site.pue_temp_limit_c)

            # ToD Tariff
            rate = tariffs["slots"]["normal"]["rate_inr_per_kwh"]
            for tod_name, tod_info in tariffs["slots"].items():
                if "hours_ist" in tod_info and h in tod_info["hours_ist"]:
                    rate = tod_info["rate_inr_per_kwh"]
                    # Priority for peaks over normal
                    if tod_name != "normal":
                        break
            problem.price[si, t] = rate

    # 3. Forecast Arrays
    problem.ci_p10 = np.zeros((n_sites, horizon_slots), dtype=float)
    problem.ci_p50 = np.zeros((n_sites, horizon_slots), dtype=float)
    problem.ci_p90 = np.zeros((n_sites, horizon_slots), dtype=float)
    problem.ci_hat = np.zeros((n_sites, horizon_slots), dtype=float)
    problem.renewable_share = np.zeros((n_sites, horizon_slots), dtype=float)

    for si, site in enumerate(sites):
        df = forecasts[site.region]
        if df.empty:
            continue
        for t in range(horizon_slots):
            ts = horizon_start_utc + timedelta(minutes=t * slot_minutes)
            # Find closest hour in forecast
            # Forecast is hourly. Slot might be 30m.
            row_idx = int((ts - horizon_start_utc).total_seconds() / 3600)
            if row_idx < len(df):
                row = df.iloc[row_idx]
                p10 = float(row["ci_p10"])
                p50 = float(row["ci_p50"])
                p90 = float(row["ci_p90"])
                problem.ci_p10[si, t] = p10
                problem.ci_p50[si, t] = p50
                problem.ci_p90[si, t] = p90
                # Risk adjustment: CI_hat = p50 + lambda * (p90 - p50)
                problem.ci_hat[si, t] = p50 + risk_lambda * (p90 - p50)
                problem.renewable_share[si, t] = float(row["renewable_share_p50"])
            else:
                # Pad with last value if horizon exceeds forecast
                last_row = df.iloc[-1]
                problem.ci_p10[si, t] = float(last_row["ci_p10"])
                problem.ci_p50[si, t] = float(last_row["ci_p50"])
                problem.ci_p90[si, t] = float(last_row["ci_p90"])
                problem.ci_hat[si, t] = float(last_row["ci_p50"]) + risk_lambda * (float(last_row["ci_p90"]) - float(last_row["ci_p50"]))
                problem.renewable_share[si, t] = float(last_row["renewable_share_p50"])

    # 4. Map Jobs
    planning_jobs = []
    for db_job in jobs:
        # Calculate slots
        rel_ts = max(horizon_start_utc, to_utc(db_job.release_ts))
        rel_s = slot_index(rel_ts, horizon_start_utc, slot_minutes)
        dead_ts = to_utc(db_job.deadline_ts)
        dead_s = slot_index(dead_ts, horizon_start_utc, slot_minutes) - 1 # inclusive last slot

        # Fix out-of-bounds
        rel_s = max(0, min(rel_s, horizon_slots - 1))
        # It's possible deadline is beyond horizon. If so, cap it.
        dead_s = min(dead_s, horizon_slots - 1)

        dur_s = int(np.ceil(db_job.duration_h * 60 / slot_minutes))

        gpu_demand = {}
        if db_job.gpus > 0 and db_job.gpu_type:
            gpu_demand[db_job.gpu_type] = db_job.gpus

        allowed = json.loads(db_job.allowed_sites_json)
        if not allow_spatial and db_job.home_site:
            allowed = [db_job.home_site]
        elif not allowed:
            # If residency is site_pinned but list is empty (fallback), use home_site
            if db_job.data_residency == "site_pinned" and db_job.home_site:
                allowed = [db_job.home_site]

        dep_ids = job_deps.get(db_job.id, [])

        pj = PlanningJob(
            id=db_job.id,
            name=db_job.name,
            archetype=db_job.archetype,
            priority=db_job.priority,
            release_slot=rel_s,
            deadline_slot=dead_s,
            duration_slots=dur_s,
            power_kw=db_job.power_kw or 0.0,
            energy_kwh=db_job.energy_kwh or 0.0,
            preemptible=db_job.preemptible,
            max_interruptions=db_job.max_interruptions,
            checkpoint_overhead_pct=db_job.checkpoint_overhead_pct,
            allowed_sites=allowed,
            data_class=db_job.data_class,
            green_only=db_job.green_only,
            data_gb=db_job.data_gb,
            home_site=db_job.home_site,
            depends_on=dep_ids,
            gpu_demand=gpu_demand,
            cpu_units=db_job.cpu_cores // 8,
        )
        planning_jobs.append(pj)

    problem.jobs = planning_jobs
    return problem
