"""Scheduler runner orchestrator — executes the scheduling pipeline."""
from __future__ import annotations

import json
from datetime import timedelta

from sqlmodel import Session, select

from app.core.config import get_settings, load_optimizer_presets
from app.core.logging import logger
from app.core.time import now_utc
from app.models import Job, JobDependency, ScheduleItem, ScheduleRun, Site
from app.services.accounting import (
    per_job_carbon,
    per_job_energy,
    renewable_share_consumed,
    savings_pct,
    schedule_carbon_g,
    sla_metrics,
)
from app.services.scheduler.builder import build_problem
from app.services.scheduler.cpsat import run_cpsat
from app.services.scheduler.fifo import run_fifo
from app.services.scheduler.greedy import run_greedy
from app.services.scheduler.precheck import precheck
from app.services.scheduler.validator import constraint_status, verify_or_fallback

settings = get_settings()


def execute_schedule(
    session: Session,
    strategy: str = "cpsat",
    horizon_hours: int = 48,
    risk_lambda: float = 0.3,
    allow_spatial: bool = True,
    carbon_budget_kg: float | None = None,
    preset_name: str | None = None,
    solver_seconds: int | None = None,
    parent_run_id: str | None = None,
) -> ScheduleRun:
    """Run the end-to-end scheduling pipeline and save results to DB."""
    logger.info(f"Executing schedule: strategy={strategy}, horizon={horizon_hours}h")

    # Load active jobs and sites
    jobs = session.exec(
        select(Job).where(Job.status.in_(["PENDING", "DEFERRED_BY_BUDGET"]))
    ).all()
    # Eager load dependencies
    job_deps = {}
    for j in jobs:
        deps = session.exec(
            select(JobDependency).where(JobDependency.job_id == j.id)
        ).all()
        job_deps[j.id] = [d.depends_on_job_id for d in deps]

    sites = session.exec(select(Site)).all()

    if not jobs or not sites:
        logger.warning("No jobs or sites found for scheduling.")
        run = ScheduleRun(
            strategy=strategy,
            horizon_start=now_utc(),
            horizon_end=now_utc() + timedelta(hours=horizon_hours),
            status="FEASIBLE",
            planned_carbon_kg=0.0,
            baseline_carbon_kg=0.0,
            savings_pct=0.0,
            config_snapshot_json="{}",
        )
        session.add(run)
        session.commit()
        return run

    # Presets
    presets = load_optimizer_presets()
    preset = presets["presets"].get(preset_name, presets["presets"]["balanced"])
    max_time = solver_seconds or presets["solver_defaults"]["max_time_seconds"]

    # Current UTC hour floor
    now = now_utc().replace(minute=0, second=0, microsecond=0)

    # 1. Build Problem
    problem = build_problem(
        jobs=list(jobs),
        sites=list(sites),
        horizon_start=now,
        horizon_hours=horizon_hours,
        slot_minutes=settings.SLOT_MINUTES,
        risk_lambda=risk_lambda,
        allow_spatial=allow_spatial,
        weights=preset,
        carbon_budget_kg=carbon_budget_kg,
        job_deps=job_deps,
    )

    # 2. Pre-check feasibility
    feasible_jobs, infeasible_records = precheck(problem)
    problem.jobs = feasible_jobs
    logger.info(f"Precheck: {len(feasible_jobs)} feasible, {len(infeasible_records)} infeasible.")

    # 3. Calculate FIFO Baseline
    fifo_result = run_fifo(problem)
    baseline_carbon = schedule_carbon_g(fifo_result, problem)
    baseline_re_share = renewable_share_consumed(fifo_result, problem)
    logger.info(f"Baseline (FIFO) Carbon: {baseline_carbon/1000:.1f} kg")

    # 4. Run Selected Strategy
    if strategy == "fifo":
        result = fifo_result
    elif strategy == "greedy":
        result = run_greedy(problem)
        result = verify_or_fallback(result, problem, fifo_result)
    elif strategy == "cpsat":
        result = run_cpsat(
            problem,
            max_time_seconds=max_time,
            num_workers=settings.SOLVER_NUM_WORKERS,
            seed=settings.SEED,
        )
        result = verify_or_fallback(result, problem, fifo_result)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    # Add back precheck infeasibilities
    result.infeasible_jobs.extend(infeasible_records)

    # 5. Accounting
    plan_carbon = schedule_carbon_g(result, problem)
    plan_re_share = renewable_share_consumed(result, problem)
    savings = savings_pct(baseline_carbon, plan_carbon)
    sla = sla_metrics(result, problem)
    violations = validate_result_wrapper(result, problem) # reuse validator for UI report
    status_checks = constraint_status(violations)

    carbon_per_job = per_job_carbon(result, problem)
    energy_per_job = per_job_energy(result, problem)

    # 6. Save to DB
    run = ScheduleRun(
        parent_run_id=parent_run_id,
        strategy=result.strategy,
        horizon_start=now,
        horizon_end=now + timedelta(hours=horizon_hours),
        risk_lambda=risk_lambda,
        allow_spatial=allow_spatial,
        carbon_budget_kg=carbon_budget_kg,
        status=result.status,
        fallback_reason=result.fallback_reason,
        objective=result.objective,
        best_bound=result.best_bound,
        gap=result.gap,
        solve_seconds=result.solve_seconds,
        num_variables=result.num_variables,
        planned_carbon_kg=plan_carbon / 1000.0,
        baseline_carbon_kg=baseline_carbon / 1000.0,
        savings_pct=savings,
        renewable_share_plan=plan_re_share,
        renewable_share_baseline=baseline_re_share,
        sla_on_time=sla["on_time"],
        sla_total=sla["total"],
        config_snapshot_json=json.dumps({
            "preset": preset_name,
            "weights": preset,
            "infeasible_count": len(result.infeasible_jobs),
            "constraints_status": status_checks,
        }),
    )
    session.add(run)
    session.flush()

    for seg in result.segments:
        item = ScheduleItem(
            run_id=run.id,
            job_id=seg.job_id,
            site_id=seg.site_id,
            segment_idx=seg.segment_idx,
            start_ts=now + timedelta(minutes=seg.start_slot * settings.SLOT_MINUTES),
            end_ts=now + timedelta(minutes=seg.end_slot * settings.SLOT_MINUTES),
            planned_carbon_g=carbon_per_job.get(seg.job_id, 0.0),
            planned_energy_kwh=energy_per_job.get(seg.job_id, 0.0),
            frozen=False,
            risk_flag="low", # TODO: flag high risk from p90 vs p50 deviation
        )
        session.add(item)

    # Mark infeasible in DB if this is a primary run (not what-if)
    if parent_run_id is None:
        scheduled_ids = {seg.job_id for seg in result.segments}
        for job in jobs:
            if job.id not in scheduled_ids:
                job.status = "INFEASIBLE"
                session.add(job)
            else:
                job.status = "SCHEDULED"
                session.add(job)

    session.commit()
    session.refresh(run)
    return run

def validate_result_wrapper(result: ScheduleResult, problem: PlanningProblem) -> list[dict]:
    from app.services.scheduler.validator import validate
    return validate(result, problem)

