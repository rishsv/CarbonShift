"""FIFO and EDF schedulers — simple baselines."""
from __future__ import annotations

import time
from typing import Literal

import numpy as np

from app.services.scheduler.types import PlanningJob, PlanningProblem, ScheduleResult, Segment


def _find_earliest_contiguous_slot(
    job: PlanningJob,
    site_idx: int,
    gpu_capacity: np.ndarray,  # (horizon_slots,) for the right GPU type
    cpu_units: np.ndarray,
    power_used: np.ndarray,
    problem: PlanningProblem,
    start_from: int = 0,
) -> int | None:
    """Find the earliest contiguous slot window for a job at a given site."""
    horizon = problem.horizon_slots
    duration = job.duration_slots
    power_cap = problem.power_cap[site_idx]

    gpu_demand = list(job.gpu_demand.values())[0] if job.gpu_demand else 0
    cpu_demand = job.cpu_units
    power_demand = job.power_kw

    for t in range(max(start_from, job.release_slot), job.deadline_slot - duration + 1):
        window_end = min(t + duration, horizon)
        if window_end - t < duration:
            break

        # Check capacity and power cap across the entire window
        feasible = True
        for s in range(t, t + duration):
            if s >= horizon:
                feasible = False
                break
            if problem.blackout[site_idx, s]:
                feasible = False
                break
            if gpu_demand > 0 and gpu_capacity[s] < gpu_demand:
                feasible = False
                break
            if cpu_demand > 0 and cpu_units[s] < cpu_demand:
                feasible = False
                break
            if power_used[s] + power_demand > power_cap[s]:
                feasible = False
                break

        if feasible:
            return t

    return None


def _book_slots(
    job: PlanningJob,
    site_idx: int,
    start_slot: int,
    gpu_capacity: np.ndarray,
    cpu_units: np.ndarray,
    power_used: np.ndarray,
    problem: PlanningProblem,
) -> None:
    """Deduct job resources from capacity arrays."""
    gpu_demand = list(job.gpu_demand.values())[0] if job.gpu_demand else 0
    gpu_type = list(job.gpu_demand.keys())[0] if job.gpu_demand else None

    for s in range(start_slot, start_slot + job.duration_slots):
        if gpu_demand > 0 and gpu_type:
            gpu_capacity[s] -= gpu_demand
        if job.cpu_units > 0:
            cpu_units[s] -= job.cpu_units
        power_used[s] += job.power_kw


def run_fifo_or_edf(
    problem: PlanningProblem,
    order: Literal["fifo", "edf"],
) -> ScheduleResult:
    """FIFO or EDF scheduler."""
    t0 = time.perf_counter()

    # Sort jobs
    if order == "fifo":
        jobs = list(problem.jobs)  # already in arrival order (assumed)
    else:  # edf
        jobs = sorted(problem.jobs, key=lambda j: j.deadline_slot)

    n_sites = len(problem.sites)
    horizon = problem.horizon_slots

    # Mutable capacity arrays per site
    # GPU: {gpu_type: ndarray(n_sites, horizon)}
    gpu_cap = {
        gt: problem.gpu_capacity[gt].copy() if gt in problem.gpu_capacity
        else np.zeros((n_sites, horizon), dtype=int)
        for gt in set(gt for j in jobs for gt in j.gpu_demand)
    }
    cpu_units = problem.cpu_units.copy()
    power_used = np.zeros((n_sites, horizon), dtype=float)

    segments: list[Segment] = []
    infeasible: list[dict] = []

    for job in jobs:
        placed = False

        # Collect eligible sites
        eligible_sites = [
            (si, s)
            for si, s in enumerate(problem.sites)
            if (not job.allowed_sites or s in job.allowed_sites)
        ]

        if not eligible_sites:
            infeasible.append({
                "id": job.id,
                "name": job.name,
                "reason": "No eligible sites after residency/hardware filter.",
                "suggested_fix": "Allow additional sites or change data class.",
            })
            continue

        # Try each eligible site in order (first allowed)
        for si, site_id in eligible_sites:
            gpu_type = list(job.gpu_demand.keys())[0] if job.gpu_demand else None
            g_cap = gpu_cap.get(gpu_type, np.zeros((n_sites, horizon), dtype=int))[si] if gpu_type else None
            c_cap = cpu_units[si]
            p_used = power_used[si]

            start = _find_earliest_contiguous_slot(
                job, si,
                g_cap if g_cap is not None else np.full(horizon, 9999),
                c_cap, p_used, problem
            )

            if start is not None and start <= job.deadline_slot - job.duration_slots:
                # Book the slots
                if gpu_type:
                    _book_slots(job, si, start, gpu_cap[gpu_type][si], cpu_units[si], power_used[si], problem)
                else:
                    _book_slots(job, si, start, np.full(horizon, 9999), cpu_units[si], power_used[si], problem)

                segments.append(Segment(
                    job_id=job.id,
                    site_id=site_id,
                    start_slot=start,
                    end_slot=start + job.duration_slots,
                ))
                placed = True
                break

        if not placed:
            infeasible.append({
                "id": job.id,
                "name": job.name,
                "reason": "Could not find a feasible slot within the deadline on any eligible site.",
                "suggested_fix": "Extend deadline, reduce resources, or allow more sites.",
            })

    elapsed = time.perf_counter() - t0
    return ScheduleResult(
        strategy=order,
        status="FEASIBLE" if not infeasible else "PARTIAL",
        segments=segments,
        infeasible_jobs=infeasible,
        solve_seconds=elapsed,
        gap=None,
    )


def run_fifo(problem: PlanningProblem) -> ScheduleResult:
    return run_fifo_or_edf(problem, "fifo")


def run_edf(problem: PlanningProblem) -> ScheduleResult:
    return run_fifo_or_edf(problem, "edf")
