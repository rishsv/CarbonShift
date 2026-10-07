"""CP-SAT optimizer — the primary scheduler.

Implements the full constraint model from spec §9 using Google OR-Tools CP-SAT.
Warm-started from the greedy solution.
"""
from __future__ import annotations

import math
import os
import time
from typing import Any, Callable, Optional

import numpy as np

from app.core.logging import logger
from app.services.scheduler.greedy import run_greedy
from app.services.scheduler.types import PlanningJob, PlanningProblem, ScheduleResult, Segment

try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except (ImportError, OSError) as e:
    ORTOOLS_AVAILABLE = False
    logger.warning(f"OR-Tools not available ({e}); CP-SAT will fall back to greedy")


# ── Integer scaling ───────────────────────────────────────────────────────────

SCALE = 1  # milligram units; if coefficients overflow int32, divide by GLOBAL_SCALE
GLOBAL_SCALE = 1


def _carbon_coeff(slot_energy_kwh: float, ci_hat: float) -> int:
    """Integer carbon coefficient in milli-gram CO2e."""
    val = slot_energy_kwh * 1000.0 * ci_hat / GLOBAL_SCALE
    return max(0, int(round(val)))


# ── Priority delay weights ────────────────────────────────────────────────────

PRIORITY_DELAY_WEIGHTS = {1: 1, 2: 3, 3: 10, 4: 40, 5: 1000}


# ── Main CP-SAT scheduler ─────────────────────────────────────────────────────

def run_cpsat(
    problem: PlanningProblem,
    max_time_seconds: int = 15,
    num_workers: int = 8,
    seed: int = 42,
    progress_callback: Optional[Callable[[dict], None]] = None,
) -> ScheduleResult:
    """Solve the carbon-aware scheduling problem with CP-SAT.

    Falls back to greedy on timeout (returns best feasible found) or error.
    """
    if not ORTOOLS_AVAILABLE:
        logger.warning("OR-Tools not available; falling back to greedy")
        result = run_greedy(problem)
        result.strategy = "cpsat"
        result.fallback_reason = "OR-Tools not installed"
        return result

    t0 = time.perf_counter()

    # Get greedy warm start
    greedy_result = run_greedy(problem)
    greedy_segments = {s.job_id: s for s in greedy_result.segments}

    model = cp_model.CpModel()
    slot_h = problem.slot_minutes / 60.0
    horizon = problem.horizon_slots
    n_sites = len(problem.sites)
    n_jobs = len(problem.jobs)

    weights = problem.weights
    alpha = weights.get("alpha", 60)
    beta = weights.get("beta", 10)
    gamma = weights.get("gamma", 1_000_000)
    delta = weights.get("delta", 10)
    mu = weights.get("mu", 3)
    rho = weights.get("rho", 2)
    tau = weights.get("tau", 1)
    eta = weights.get("eta_smooth", 0)

    job_by_id = {j.id: j for j in problem.jobs}

    # ── Variables ─────────────────────────────────────────────────────────────
    # x[j][s][t] = 1 if job j runs on site s at slot t
    x: list[list[list[Any]]] = []
    # z[j][s] = 1 if job j is assigned to site s
    z: list[list[Any]] = []
    # y[j][s][t] = 1 if non-preemptible job j starts on site s at slot t
    y: list[list[list[Any]]] = []
    # start[j], end[j], delay[j]
    start_var: list[Any] = []
    end_var: list[Any] = []
    delay_var: list[Any] = []
    late_var: list[Any] = []

    job_sites: list[list[int]] = []  # eligible site indices per job

    for ji, job in enumerate(problem.jobs):
        # Eligible site indices
        eligible = [
            si for si, s in enumerate(problem.sites)
            if not job.allowed_sites or s in job.allowed_sites
        ]
        job_sites.append(eligible)

        # x[j][s][t]: only create for eligible sites and valid time windows
        x_j: list[list[Any]] = []
        z_j: list[Any] = []
        y_j: list[list[Any]] = []

        for si in range(n_sites):
            x_js: list[Any] = []
            y_js: list[Any] = []
            if si in eligible:
                for t in range(job.release_slot, min(job.deadline_slot - job.buffer_slots + 1, horizon)):
                    xvar = model.NewBoolVar(f"x_{ji}_{si}_{t}")
                    x_js.append(xvar)
                    if not job.preemptible:
                        # y only at start positions that fit
                        if t + job.duration_slots <= job.deadline_slot - job.buffer_slots + 1:
                            yvar = model.NewBoolVar(f"y_{ji}_{si}_{t}")
                            y_js.append(yvar)
                        else:
                            y_js.append(None)
                    else:
                        y_js.append(None)
                z_j.append(model.NewBoolVar(f"z_{ji}_{si}"))
            else:
                z_j.append(model.NewConstant(0))
            x_j.append(x_js)
            y_j.append(y_js)

        x.append(x_j)
        z.append(z_j)
        y.append(y_j)

        # Scalar variables for start, end, delay, late
        s_lo = job.release_slot
        s_hi = max(job.release_slot, job.deadline_slot - job.buffer_slots - job.duration_slots + 1)
        start_v = model.NewIntVar(s_lo, max(s_lo, s_hi), f"start_{ji}")
        end_v = model.NewIntVar(s_lo + job.duration_slots, min(job.deadline_slot + 1, horizon), f"end_{ji}")
        delay_v = model.NewIntVar(0, horizon, f"delay_{ji}")
        late_v = model.NewIntVar(0, 0, f"late_{ji}")  # forced to 0 for pre-checked feasible jobs

        start_var.append(start_v)
        end_var.append(end_v)
        delay_var.append(delay_v)
        late_var.append(late_v)

    # ── Helper: slot offset into x_j[si] list ─────────────────────────────────
    def slot_to_xidx(ji: int, si: int, t: int) -> int | None:
        job = problem.jobs[ji]
        offset = t - job.release_slot
        if offset < 0 or offset >= len(x[ji][si]):
            return None
        return offset

    def get_x(ji: int, si: int, t: int) -> Any | None:
        idx = slot_to_xidx(ji, si, t)
        if idx is None:
            return None
        return x[ji][si][idx]

    # ── Hard constraints ──────────────────────────────────────────────────────

    for ji, job in enumerate(problem.jobs):
        eligible = job_sites[ji]
        duration = job.duration_slots

        # H1: Total slots == duration
        all_x_vars = [
            xvar
            for si in eligible
            for t_off, xvar in enumerate(x[ji][si])
        ]
        model.Add(sum(all_x_vars) == duration)

        # H4: Single site assignment
        z_eligible = [z[ji][si] for si in eligible]
        if z_eligible:
            model.Add(sum(z_eligible) == 1)
        for si in eligible:
            for t_off, xvar in enumerate(x[ji][si]):
                model.Add(xvar <= z[ji][si])

        # H5/H6: Contiguity for non-preemptible, interruption limit for preemptible
        if not job.preemptible:
            for si in eligible:
                # y[j][s][start] indicates job starts at this slot
                # sum y_{s,u for u in [t-p+1,t]} = x[j][s][t]
                y_si = y[ji][si]
                x_si = x[ji][si]
                for t_off, xvar in enumerate(x_si):
                    t = t_off + job.release_slot
                    # Compute sum of y at start slots that cover this slot
                    y_sum_terms = []
                    for start_off, yvar in enumerate(y_si):
                        if yvar is None:
                            continue
                        start_t = start_off + job.release_slot
                        if start_t <= t < start_t + duration:
                            y_sum_terms.append(yvar)
                    if y_sum_terms:
                        model.Add(xvar == sum(y_sum_terms))
                    else:
                        model.Add(xvar == 0)
                # sum y == z[j][s]
                valid_ys = [yv for yv in y_si if yv is not None]
                if valid_ys:
                    model.Add(sum(valid_ys) == z[ji][si])
        else:
            # H6: Interruptions <= max_interruptions
            for si in eligible:
                x_si = x[ji][si]
                if len(x_si) < 2:
                    continue
                resumes = []
                for t_off in range(1, len(x_si)):
                    # resume at t = 1 if x[t]=1 and x[t-1]=0
                    resume = model.NewBoolVar(f"resume_{ji}_{si}_{t_off}")
                    model.AddBoolAnd([x_si[t_off], x_si[t_off - 1].Not()]).OnlyEnforceIf(resume)
                    model.AddBoolOr([x_si[t_off].Not(), x_si[t_off - 1]]).OnlyEnforceIf(resume.Not())
                    resumes.append(resume)
                # first slot running counts as one "segment start"
                first_resume = model.NewBoolVar(f"resume_first_{ji}_{si}")
                model.Add(first_resume == x_si[0])
                all_resumes = [first_resume] + resumes
                model.Add(sum(all_resumes) <= job.max_interruptions + 1)

        # H2: late_j = 0 (already enforced by making late_j an IntVar(0,0))
        # H8: Dependencies
        for dep_id in job.depends_on:
            dep_ji = next((i for i, j in enumerate(problem.jobs) if j.id == dep_id), None)
            if dep_ji is not None:
                model.Add(start_var[ji] >= end_var[dep_ji])

    # H3: Capacity constraints (per site, per GPU type, per slot)
    for si, site_id in enumerate(problem.sites):
        for t in range(horizon):
            # Per GPU type
            for gpu_type, cap_arr in problem.gpu_capacity.items():
                cap = int(cap_arr[si, t]) if not problem.blackout[si, t] else 0
                x_terms = []
                for ji, job in enumerate(problem.jobs):
                    if si not in job_sites[ji]:
                        continue
                    if gpu_type not in job.gpu_demand:
                        continue
                    demand = job.gpu_demand[gpu_type]
                    xvar = get_x(ji, si, t)
                    if xvar is not None and demand > 0:
                        x_terms.append((demand, xvar))
                if x_terms:
                    model.Add(sum(d * v for d, v in x_terms) <= cap)

            # CPU units
            cpu_cap = int(problem.cpu_units[si, t]) if not problem.blackout[si, t] else 0
            cpu_terms = []
            for ji, job in enumerate(problem.jobs):
                if si not in job_sites[ji] or job.cpu_units == 0:
                    continue
                xvar = get_x(ji, si, t)
                if xvar is not None:
                    cpu_terms.append((job.cpu_units, xvar))
            if cpu_terms:
                model.Add(sum(d * v for d, v in cpu_terms) <= cpu_cap)

            # H7: Power cap (integerize kW * 100)
            power_cap_100 = int(problem.power_cap[si, t] * 100)
            power_terms = []
            for ji, job in enumerate(problem.jobs):
                if si not in job_sites[ji]:
                    continue
                pue_val = problem.pue[si, t]
                p_100 = int(job.power_kw * pue_val * 100)
                xvar = get_x(ji, si, t)
                if xvar is not None and p_100 > 0:
                    power_terms.append((p_100, xvar))
            if power_terms:
                model.Add(sum(p * v for p, v in power_terms) <= power_cap_100)

    # ── Objective ─────────────────────────────────────────────────────────────
    carbon_terms = []
    delay_terms = []
    nonrenew_terms = []

    for ji, job in enumerate(problem.jobs):
        eligible = job_sites[ji]
        slot_h_ = slot_h
        w_j = PRIORITY_DELAY_WEIGHTS.get(job.priority, 10)

        for si in eligible:
            pue_si = problem.pue[si]
            ci_hat_si = problem.ci_hat[si]
            re_si = problem.renewable_share[si]

            for t_off, xvar in enumerate(x[ji][si]):
                t = t_off + job.release_slot
                if t >= horizon:
                    break
                slot_energy = job.power_kw * slot_h_ * float(pue_si[t] if t < len(pue_si) else 1.35)
                ci_val = float(ci_hat_si[t] if t < len(ci_hat_si) else 600.0)
                re_val = float(re_si[t] if t < len(re_si) else 0.3)

                coeff = _carbon_coeff(slot_energy, ci_val)
                if coeff > 0:
                    carbon_terms.append(alpha * coeff * xvar)

                # Non-renewable energy (delta term)
                nonrenew_coeff = _carbon_coeff(slot_energy * (1.0 - re_val), 1000.0)
                if nonrenew_coeff > 0 and delta > 0:
                    nonrenew_terms.append(delta * nonrenew_coeff // 1000 * xvar)

        # Delay (beta * w_j * delay_j)
        delay_terms.append(beta * w_j * delay_var[ji])

    objective_terms = carbon_terms + delay_terms + nonrenew_terms
    if objective_terms:
        model.Minimize(sum(objective_terms))

    # ── Warm start from greedy ─────────────────────────────────────────────────
    for ji, job in enumerate(problem.jobs):
        eligible = job_sites[ji]
        greedy_seg = greedy_segments.get(job.id)

        if greedy_seg:
            greedy_si = problem.sites.index(greedy_seg.site_id) if greedy_seg.site_id in problem.sites else -1
            for si in eligible:
                z_val = 1 if si == greedy_si else 0
                model.AddHint(z[ji][si], z_val)

                for t_off, xvar in enumerate(x[ji][si]):
                    t = t_off + job.release_slot
                    in_greedy = (
                        si == greedy_si
                        and greedy_seg.start_slot <= t < greedy_seg.end_slot
                    )
                    model.AddHint(xvar, 1 if in_greedy else 0)

    # ── Solve ─────────────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    solver.parameters.num_search_workers = min(num_workers, os.cpu_count() or 4)
    solver.parameters.random_seed = seed
    solver.parameters.log_search_progress = False

    logger.info(f"CP-SAT: solving with {n_jobs} jobs × {n_sites} sites × {horizon} slots")
    logger.info(f"  time_limit={max_time_seconds}s, workers={solver.parameters.num_search_workers}")

    status = solver.Solve(model)
    elapsed = time.perf_counter() - t0

    logger.info(
        f"CP-SAT: status={solver.StatusName(status)}, "
        f"obj={solver.ObjectiveValue():.0f}, "
        f"bound={solver.BestObjectiveBound():.0f}, "
        f"gap={solver.SolutionInfo()}, "
        f"time={elapsed:.1f}s"
    )

    # ── Extract solution ───────────────────────────────────────────────────────
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        segments: list[Segment] = []
        for ji, job in enumerate(problem.jobs):
            eligible = job_sites[ji]
            for si in eligible:
                if solver.Value(z[ji][si]) == 0:
                    continue
                site_id = problem.sites[si]
                # Find running slots
                current_seg_start: int | None = None
                seg_idx = 0
                for t_off, xvar in enumerate(x[ji][si]):
                    t = t_off + job.release_slot
                    running = solver.Value(xvar) == 1
                    if running and current_seg_start is None:
                        current_seg_start = t
                    elif not running and current_seg_start is not None:
                        segments.append(Segment(
                            job_id=job.id,
                            site_id=site_id,
                            start_slot=current_seg_start,
                            end_slot=t,
                            segment_idx=seg_idx,
                        ))
                        seg_idx += 1
                        current_seg_start = None
                if current_seg_start is not None:
                    last_t = job.release_slot + len(x[ji][si])
                    segments.append(Segment(
                        job_id=job.id,
                        site_id=site_id,
                        start_slot=current_seg_start,
                        end_slot=last_t,
                        segment_idx=seg_idx,
                    ))

        obj = solver.ObjectiveValue()
        bound = solver.BestObjectiveBound()
        gap = abs(obj - bound) / (abs(obj) + 1e-9) if obj != 0 else 0.0

        return ScheduleResult(
            strategy="cpsat",
            status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            segments=segments,
            infeasible_jobs=[],
            objective=obj,
            best_bound=bound,
            gap=gap,
            solve_seconds=elapsed,
            num_variables=model.Proto().variables.__len__(),
        )
    else:
        # Fall back to greedy
        logger.warning(f"CP-SAT returned {solver.StatusName(status)}; falling back to greedy")
        result = greedy_result
        result.strategy = "cpsat"
        result.fallback_reason = f"CP-SAT returned {solver.StatusName(status)} after {elapsed:.1f}s"
        result.solve_seconds = elapsed
        return result
