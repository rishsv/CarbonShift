"""Greedy carbon scheduler — the primary heuristic and CP-SAT warm start."""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from app.services.scheduler.types import PlanningJob, PlanningProblem, ScheduleResult, Segment


def _window_carbon_cost(
    job: PlanningJob,
    site_idx: int,
    start_slot: int,
    problem: PlanningProblem,
) -> float:
    """Compute the risk-adjusted carbon cost of placing job at (site_idx, start_slot)."""
    slot_h = problem.slot_minutes / 60.0
    total_carbon = 0.0
    for s in range(start_slot, start_slot + job.duration_slots):
        if s >= problem.horizon_slots:
            break
        ci_hat = problem.ci_hat[site_idx, s]
        pue = problem.pue[site_idx, s]
        energy_slot = job.power_kw * slot_h * pue
        total_carbon += energy_slot * ci_hat
    return total_carbon


def _is_feasible_window(
    job: PlanningJob,
    site_idx: int,
    start_slot: int,
    gpu_cap_arr: Optional[np.ndarray],
    cpu_units_arr: np.ndarray,
    power_used_arr: np.ndarray,
    power_cap_arr: np.ndarray,
    blackout_arr: np.ndarray,
    problem: PlanningProblem,
) -> bool:
    """Check if a (site, start_slot) window is feasible for a job."""
    horizon = problem.horizon_slots
    duration = job.duration_slots

    if start_slot < job.release_slot:
        return False
    if start_slot + duration - 1 > job.deadline_slot:
        return False

    gpu_demand = list(job.gpu_demand.values())[0] if job.gpu_demand else 0
    cpu_demand = job.cpu_units

    for s in range(start_slot, start_slot + duration):
        if s >= horizon:
            return False
        if blackout_arr[s]:
            return False
        if gpu_demand > 0 and gpu_cap_arr is not None and gpu_cap_arr[s] < gpu_demand:
            return False
        if cpu_demand > 0 and cpu_units_arr[s] < cpu_demand:
            return False
        if power_used_arr[s] + job.power_kw > power_cap_arr[s]:
            return False

    # Green-only check
    if job.green_only:
        from app.core.config import load_optimizer_presets
        theta = load_optimizer_presets().get("green_only_threshold", 0.35)
        for s in range(start_slot, start_slot + duration):
            if s < problem.horizon_slots and problem.renewable_share[site_idx, s] < theta:
                return False

    return True


def run_greedy(problem: PlanningProblem) -> ScheduleResult:
    """Greedy carbon-aware scheduler.

    Sort jobs by (slack ascending, priority descending).
    For each job, enumerate feasible (site, start) windows, pick lowest risk-adjusted carbon.
    Process dependencies in topological order.
    """
    t0 = time.perf_counter()
    horizon = problem.horizon_slots
    n_sites = len(problem.sites)

    # Mutable capacity arrays
    gpu_cap: dict[str, np.ndarray] = {}
    for gt, arr in problem.gpu_capacity.items():
        gpu_cap[gt] = arr.copy()
    cpu_units = problem.cpu_units.copy()
    power_used = np.zeros((n_sites, horizon), dtype=float)

    # Sort: dependencies first (topo), then by (slack, priority)
    from app.services.scheduler.precheck import _topo_sort
    all_by_id = {j.id: j for j in problem.jobs}
    ordered = _topo_sort(problem.jobs, all_by_id)

    # Within topo order, sort by (slack asc, priority desc)
    ordered.sort(key=lambda j: (
        (j.deadline_slot - j.release_slot - j.duration_slots),  # slack
        -j.priority,
    ))

    segments: list[Segment] = []
    infeasible: list[dict] = []
    job_end_slots: dict[str, int] = {}  # for dependency tracking

    for job in ordered:
        # Effective release: max of release_slot and all dep ends
        dep_release = job.release_slot
        for dep_id in job.depends_on:
            if dep_id in job_end_slots:
                dep_release = max(dep_release, job_end_slots[dep_id])

        best_carbon = float("inf")
        best_site_idx = -1
        best_start = -1

        eligible_sites = [
            (si, s)
            for si, s in enumerate(problem.sites)
            if (not job.allowed_sites or s in job.allowed_sites)
        ]

        for si, site_id in eligible_sites:
            gpu_type = list(job.gpu_demand.keys())[0] if job.gpu_demand else None
            g_arr = gpu_cap.get(gpu_type, np.zeros((n_sites, horizon), dtype=int))[si] if gpu_type else None

            for t in range(dep_release, job.deadline_slot - job.duration_slots + 1):
                if not _is_feasible_window(
                    job, si, t,
                    g_arr, cpu_units[si], power_used[si], problem.power_cap[si],
                    problem.blackout[si], problem,
                ):
                    continue

                carbon = _window_carbon_cost(job, si, t, problem)
                # Add priority-weighted delay cost (beta * w_j * delay)
                weights = problem.weights
                beta = weights.get("beta", 10)
                w_j = {1: 1, 2: 3, 3: 10, 4: 40, 5: 1000}.get(job.priority, 10)
                delay = t - dep_release
                carbon += beta * w_j * delay * 0.001  # scale to same magnitude

                if carbon < best_carbon:
                    best_carbon = carbon
                    best_site_idx = si
                    best_start = t

        if best_site_idx < 0 or best_start < 0:
            infeasible.append({
                "id": job.id,
                "name": job.name,
                "reason": "No feasible carbon-minimal window found in the horizon.",
                "suggested_fix": "Extend deadline, reduce resources, or allow more sites.",
            })
            continue

        # Book the best window
        site_id = problem.sites[best_site_idx]
        gpu_type = list(job.gpu_demand.keys())[0] if job.gpu_demand else None
        for s in range(best_start, best_start + job.duration_slots):
            if gpu_type and gpu_type in gpu_cap:
                gpu_cap[gpu_type][best_site_idx, s] -= list(job.gpu_demand.values())[0]
            if job.cpu_units > 0:
                cpu_units[best_site_idx, s] -= job.cpu_units
            power_used[best_site_idx, s] += job.power_kw

        segments.append(Segment(
            job_id=job.id,
            site_id=site_id,
            start_slot=best_start,
            end_slot=best_start + job.duration_slots,
        ))
        job_end_slots[job.id] = best_start + job.duration_slots

    elapsed = time.perf_counter() - t0
    return ScheduleResult(
        strategy="greedy",
        status="FEASIBLE" if not infeasible else "PARTIAL",
        segments=segments,
        infeasible_jobs=infeasible,
        solve_seconds=elapsed,
        gap=None,
    )
