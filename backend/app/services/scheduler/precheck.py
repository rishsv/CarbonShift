"""Pre-solve feasibility checker — validates jobs before sending to any scheduler."""
from __future__ import annotations

import math
from typing import Optional

from app.services.scheduler.types import PlanningJob, PlanningProblem, ScheduleResult


def compute_buffer_slots(job: PlanningJob, uncertainty_pct: float = 10.0) -> int:
    """Deadline safety buffer in slots. Grows with priority."""
    raw = math.ceil(job.duration_slots * uncertainty_pct / 100.0 * (job.priority / 5.0))
    return raw


def _earliest_feasible_start(
    job: PlanningJob,
    problem: PlanningProblem,
    all_jobs_by_id: dict[str, PlanningJob],
    earliest_ends: dict[str, int],
) -> Optional[int]:
    """Return the earliest slot a job CAN start (considering dependencies and capacity).

    Returns None if no feasible start exists within the window.
    """
    # Dependency: must start after all predecessors finish
    dep_start = job.release_slot
    for dep_id in job.depends_on:
        if dep_id in earliest_ends:
            dep_start = max(dep_start, earliest_ends[dep_id])

    # Must finish by deadline - buffer
    latest_start = job.deadline_slot - job.buffer_slots - job.duration_slots + 1

    if dep_start > latest_start:
        return None

    # Check if any allowed site has capacity at some point
    for site_id in (job.allowed_sites or problem.sites):
        if site_id not in problem.sites:
            continue
        si = problem.site_index(site_id)

        # Check GPU type compatibility
        if job.gpu_demand:
            gpu_type = list(job.gpu_demand.keys())[0]
            if gpu_type not in problem.gpu_capacity:
                continue
            cap_arr = problem.gpu_capacity[gpu_type][si]
        else:
            cap_arr = problem.cpu_units[si]

        demand = list(job.gpu_demand.values())[0] if job.gpu_demand else job.cpu_units
        if demand == 0:
            return dep_start  # No resource demand, always feasible

        # Scan for a contiguous window with enough capacity
        for t in range(dep_start, min(latest_start + 1, problem.horizon_slots - job.duration_slots + 1)):
            window = cap_arr[t : t + job.duration_slots]
            if len(window) == job.duration_slots and all(c >= demand for c in window):
                return t

    return None


def precheck(problem: PlanningProblem) -> tuple[list[PlanningJob], list[dict]]:
    """Pre-check all jobs for feasibility.

    Returns:
        (feasible_jobs, infeasible_records)
    """
    all_by_id = {j.id: j for j in problem.jobs}
    feasible: list[PlanningJob] = []
    infeasible: list[dict] = []

    # Topological order by dependencies
    ordered = _topo_sort(problem.jobs, all_by_id)

    earliest_ends: dict[str, int] = {}

    for job in ordered:
        # Attach buffer (may be reduced to 0 if needed)
        job.buffer_slots = compute_buffer_slots(job)

        reason = None
        fix = None

        # 1. Window too short (even with 0 buffer)
        window = job.deadline_slot - job.release_slot
        if window < job.duration_slots:
            gap = job.duration_slots - window
            reason = (
                f"Time window ({window} slots) is shorter than job duration ({job.duration_slots} slots). "
                f"Job cannot complete before deadline."
            )
            fix = f"Extend deadline by {gap} slot(s) or reduce duration."
        else:
            # 2. Try to find earliest feasible start
            # First try with buffer, then drop buffer to 0
            es = _earliest_feasible_start(job, problem, all_by_id, earliest_ends)
            if es is None:
                # Try without buffer
                job.buffer_slots = 0
                es = _earliest_feasible_start(job, problem, all_by_id, earliest_ends)
                if es is not None:
                    job.buffer_slots = 0  # keep at 0, job is feasible but tight

            if es is None:
                # Find what's blocking it
                reason = _diagnose_infeasibility(job, problem, all_by_id, earliest_ends)
                fix = _suggest_fix(job, problem)

        if reason:
            infeasible.append({
                "id": job.id,
                "name": job.name,
                "reason": reason,
                "suggested_fix": fix or "Review job parameters.",
            })
        else:
            feasible.append(job)
            # Record earliest possible end for dependency tracking
            dep_start = max(job.release_slot, max(
                (earliest_ends.get(d, 0) for d in job.depends_on), default=job.release_slot
            ))
            earliest_ends[job.id] = dep_start + job.duration_slots

    return feasible, infeasible


def _topo_sort(jobs: list[PlanningJob], by_id: dict[str, PlanningJob]) -> list[PlanningJob]:
    """Kahn's algorithm topological sort."""
    in_degree = {j.id: 0 for j in jobs}
    children: dict[str, list[str]] = {j.id: [] for j in jobs}
    for j in jobs:
        for dep_id in j.depends_on:
            if dep_id in in_degree:
                in_degree[j.id] += 1
                children[dep_id].append(j.id)

    queue = [j for j in jobs if in_degree[j.id] == 0]
    result = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for child_id in children[node.id]:
            in_degree[child_id] -= 1
            if in_degree[child_id] == 0:
                queue.append(by_id[child_id])
    return result


def _diagnose_infeasibility(
    job: PlanningJob,
    problem: PlanningProblem,
    all_by_id: dict[str, PlanningJob],
    earliest_ends: dict[str, int],
) -> str:
    if not job.allowed_sites and not problem.sites:
        return "No eligible sites: data residency or GPU type restrictions leave no valid site."

    if job.gpu_demand:
        gpu_type = list(job.gpu_demand.keys())[0]
        demand = list(job.gpu_demand.values())[0]
        sites_with_gpu = [
            s for s in (job.allowed_sites or problem.sites)
            if s in problem.sites
            and gpu_type in problem.gpu_capacity
            and max(problem.gpu_capacity[gpu_type][problem.site_index(s)]) >= demand
        ]
        if not sites_with_gpu:
            return (
                f"No site in allowed set has {demand} × {gpu_type} GPUs available in the horizon. "
                f"Largest available: check site capacities."
            )

    dep_block = False
    for dep_id in job.depends_on:
        if dep_id in earliest_ends and earliest_ends[dep_id] >= job.deadline_slot:
            dep_block = True
            break
    if dep_block:
        return "Predecessor job(s) finish after this job's deadline."

    return "No feasible schedule found: capacity, residency or dependency constraints prevent placement."


def _suggest_fix(job: PlanningJob, problem: PlanningProblem) -> str:
    window = job.deadline_slot - job.release_slot
    if window < job.duration_slots:
        extra = job.duration_slots - window
        return (
            f"Extend deadline by {extra} slot(s) ({extra * problem.slot_minutes // 60}h), "
            f"or reduce GPU count / duration."
        )
    if job.gpu_demand:
        gpu_type = list(job.gpu_demand.keys())[0]
        demand = list(job.gpu_demand.values())[0]
        return (
            f"Allow additional sites, reduce {gpu_type} GPUs from {demand} to a smaller count, "
            f"or extend deadline to give more scheduling flexibility."
        )
    return "Extend deadline, allow more sites, or reduce resource requirements."
