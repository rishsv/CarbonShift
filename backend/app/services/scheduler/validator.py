"""Independent constraint validator — verifies schedules without the solver."""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from app.core.logging import logger
from app.services.scheduler.types import PlanningProblem, ScheduleResult, Segment


def validate(result: ScheduleResult, problem: PlanningProblem) -> list[dict]:
    """Verify all hard constraints H1-H11 on a schedule result.

    Returns a list of violation dicts: {constraint, job_id, detail}
    Empty list = all good.
    """
    violations: list[dict] = []
    horizon = problem.horizon_slots
    job_by_id = {j.id: j for j in problem.jobs}

    # Group segments by job
    job_segments: dict[str, list[Segment]] = defaultdict(list)
    for seg in result.segments:
        job_segments[seg.job_id].append(seg)

    # Site usage: per slot, per site, per gpu type
    gpu_usage: dict[str, dict[int, dict[int, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    cpu_usage: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    power_usage: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))

    for seg in result.segments:
        job = job_by_id.get(seg.job_id)
        if not job:
            continue
        if seg.site_id not in problem.sites:
            continue
        si = problem.site_index(seg.site_id)

        for t in range(seg.start_slot, seg.end_slot):
            for gt, demand in job.gpu_demand.items():
                gpu_usage[gt][si][t] += demand
            cpu_usage[si][t] += job.cpu_units
            power_usage[si][t] += job.power_kw

    for job_id, segs in job_segments.items():
        job = job_by_id.get(job_id)
        if not job:
            continue

        # H1: Total slots == duration
        total_slots = sum(seg.end_slot - seg.start_slot for seg in segs)
        if total_slots != job.duration_slots:
            violations.append({
                "constraint": "H1",
                "job_id": job_id,
                "detail": f"Expected {job.duration_slots} slots, got {total_slots}",
            })

        # H2: All slots within release/deadline
        for seg in segs:
            if seg.start_slot < job.release_slot:
                violations.append({
                    "constraint": "H2",
                    "job_id": job_id,
                    "detail": f"Segment starts at slot {seg.start_slot} before release {job.release_slot}",
                })
            eff_deadline = job.deadline_slot - job.buffer_slots
            if seg.end_slot - 1 > eff_deadline:
                violations.append({
                    "constraint": "H2",
                    "job_id": job_id,
                    "detail": f"Segment ends at slot {seg.end_slot} after deadline {eff_deadline + 1}",
                })

        # H4: Single site
        sites_used = set(seg.site_id for seg in segs)
        if len(sites_used) > 1:
            violations.append({
                "constraint": "H4",
                "job_id": job_id,
                "detail": f"Job assigned to multiple sites: {sites_used}",
            })

        # H5: Contiguity for non-preemptible
        if not job.preemptible and len(segs) > 1:
            # Check if segments are contiguous
            sorted_segs = sorted(segs, key=lambda s: s.start_slot)
            for i in range(len(sorted_segs) - 1):
                if sorted_segs[i].end_slot != sorted_segs[i + 1].start_slot:
                    violations.append({
                        "constraint": "H5",
                        "job_id": job_id,
                        "detail": "Non-preemptible job has non-contiguous segments",
                    })

        # H6: Interruptions <= max_interruptions
        if job.preemptible:
            n_segments = len(segs)
            max_allowed = job.max_interruptions + 1
            if n_segments > max_allowed:
                violations.append({
                    "constraint": "H6",
                    "job_id": job_id,
                    "detail": f"Job has {n_segments} segments > max {max_allowed}",
                })

        # H9: Data residency (all sites are India; per-job allowed_sites)
        if job.allowed_sites:
            for seg in segs:
                if seg.site_id not in job.allowed_sites:
                    violations.append({
                        "constraint": "H9",
                        "job_id": job_id,
                        "detail": f"Job scheduled at {seg.site_id} not in allowed_sites",
                    })

        # H10: Hardware compatibility
        for seg in segs:
            if seg.site_id not in problem.sites:
                violations.append({
                    "constraint": "H10",
                    "job_id": job_id,
                    "detail": f"Site {seg.site_id} not in problem sites",
                })
                continue
            si = problem.site_index(seg.site_id)
            for gt, demand in job.gpu_demand.items():
                if gt in problem.gpu_capacity:
                    cap = problem.gpu_capacity[gt][si]
                    for t in range(seg.start_slot, seg.end_slot):
                        if t < horizon and cap[t] < demand:
                            # Already caught by H3; just note
                            pass
                else:
                    violations.append({
                        "constraint": "H10",
                        "job_id": job_id,
                        "detail": f"GPU type {gt} not available at site {seg.site_id}",
                    })

        # H8: Dependencies
        job_end = max((seg.end_slot for seg in segs), default=0)
        for dep_id in job.depends_on:
            dep_segs = job_segments.get(dep_id, [])
            if not dep_segs:
                continue
            dep_end = max(seg.end_slot for seg in dep_segs)
            job_start = min(seg.start_slot for seg in segs)
            if job_start < dep_end:
                violations.append({
                    "constraint": "H8",
                    "job_id": job_id,
                    "detail": f"Starts at slot {job_start} before dependency {dep_id} ends at slot {dep_end}",
                })

    # H3: GPU capacity per site per slot
    for gt, site_slot_usage in gpu_usage.items():
        if gt not in problem.gpu_capacity:
            continue
        for si, slot_usage in site_slot_usage.items():
            for t, used in slot_usage.items():
                if t < horizon:
                    cap = int(problem.gpu_capacity[gt][si, t])
                    if used > cap:
                        violations.append({
                            "constraint": "H3",
                            "site_idx": si,
                            "slot": t,
                            "detail": f"GPU {gt} usage {used} > capacity {cap}",
                        })

    # H3: CPU capacity
    for si, slot_usage in cpu_usage.items():
        for t, used in slot_usage.items():
            if t < horizon:
                cap = int(problem.cpu_units[si, t])
                if used > cap:
                    violations.append({
                        "constraint": "H3",
                        "site_idx": si,
                        "slot": t,
                        "detail": f"CPU usage {used} units > capacity {cap}",
                    })

    # H7: Power cap
    for si, slot_usage in power_usage.items():
        for t, used in slot_usage.items():
            if t < horizon:
                cap = float(problem.power_cap[si, t])
                if used > cap * 1.001:  # 0.1% tolerance for float math
                    violations.append({
                        "constraint": "H7",
                        "site_idx": si,
                        "slot": t,
                        "detail": f"Power {used:.1f}kW > cap {cap:.1f}kW",
                    })

    # H11: Blackouts
    for seg in result.segments:
        if seg.site_id not in problem.sites:
            continue
        si = problem.site_index(seg.site_id)
        for t in range(seg.start_slot, seg.end_slot):
            if t < horizon and problem.blackout[si, t]:
                violations.append({
                    "constraint": "H11",
                    "job_id": seg.job_id,
                    "slot": t,
                    "detail": f"Job runs during maintenance blackout at site {seg.site_id}",
                })

    if violations:
        logger.warning(f"Validator found {len(violations)} violation(s)")
    else:
        logger.info("Validator: all constraints satisfied")

    return violations


def verify_or_fallback(
    result: ScheduleResult,
    problem: PlanningProblem,
    fallback_result: ScheduleResult,
) -> ScheduleResult:
    """Return result if valid, else fallback with a warning."""
    violations = validate(result, problem)
    if violations:
        logger.error(
            f"CP-SAT result has {len(violations)} constraint violation(s). "
            f"Falling back to greedy."
        )
        fallback_result.fallback_reason = (
            f"CP-SAT solution had {len(violations)} violation(s): {violations[0]['detail']}"
        )
        return fallback_result
    return result


def constraint_status(violations: list[dict]) -> list[dict]:
    """Return per-constraint pass/fail status for the UI."""
    constraints = [
        ("H1", "Completion — each job gets full duration"),
        ("H2", "Time window — within release and deadline"),
        ("H3", "Capacity — site GPU/CPU limits"),
        ("H4", "Single-site assignment"),
        ("H5", "Contiguity for non-preemptible jobs"),
        ("H6", "Interruption limit for preemptible jobs"),
        ("H7", "Site power cap"),
        ("H8", "Job dependencies"),
        ("H9", "Data residency"),
        ("H10", "Hardware compatibility"),
        ("H11", "Maintenance blackouts"),
    ]
    viol_by_c = defaultdict(int)
    for v in violations:
        viol_by_c[v.get("constraint", "?")] += 1

    return [
        {
            "constraint": c,
            "label": label,
            "passed": viol_by_c[c] == 0,
            "violations": viol_by_c[c],
        }
        for c, label in constraints
    ]
