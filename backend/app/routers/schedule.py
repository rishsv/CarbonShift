"""Schedule router — trigger runs, fetch results, compare."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select

from app.core.db import get_session
from app.models import Job, ScheduleItem, ScheduleRun, Site
from app.schemas import (
    CompareResponse,
    ConstraintStatus,
    InfeasibleJobRead,
    ScheduleItemRead,
    ScheduleRunRequest,
    ScheduleRunSummary,
    SegmentRead,
)
from app.services.scheduler.runner import execute_schedule

router = APIRouter()


@router.post("/schedule", response_model=ScheduleRunSummary, status_code=201)
def trigger_schedule(
    body: ScheduleRunRequest,
    session: Session = Depends(get_session),
):
    """Trigger a new schedule run synchronously."""
    try:
        run = execute_schedule(
            session=session,
            strategy=body.strategy,
            horizon_hours=body.horizon_hours,
            risk_lambda=body.risk_lambda,
            allow_spatial=body.allow_spatial,
            carbon_budget_kg=body.carbon_budget_kg,
            preset_name=body.preset,
            solver_seconds=body.solver_seconds,
        )
        return _build_summary(run, session)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule/runs", response_model=list[ScheduleRunSummary])
def list_runs(limit: int = 10, session: Session = Depends(get_session)):
    """List recent schedule runs."""
    runs = session.exec(
        select(ScheduleRun)
        .where(ScheduleRun.parent_run_id == None)  # Only primary runs
        .order_by(ScheduleRun.created_at.desc())
        .limit(limit)
    ).all()
    return [_build_summary(r, session, include_items=False) for r in runs]


@router.get("/schedule/runs/{run_id}", response_model=ScheduleRunSummary)
def get_run(run_id: str, session: Session = Depends(get_session)):
    """Get full details of a specific run."""
    run = session.get(ScheduleRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _build_summary(run, session, include_items=True)


@router.get("/schedule/compare", response_model=CompareResponse)
def compare_strategies(
    horizon_hours: int = 48,
    session: Session = Depends(get_session),
):
    """Run FIFO, EDF, Greedy, and CP-SAT to compare baseline metrics."""
    # Build standard params
    from app.core.time import floor_hour_utc, now_utc
    from app.services.scheduler.builder import build_problem
    from app.services.scheduler.fifo import run_fifo, run_edf
    from app.services.scheduler.greedy import run_greedy
    from app.services.scheduler.cpsat import run_cpsat
    from app.services.accounting import schedule_carbon_g, sla_metrics, renewable_share_consumed

    now = floor_hour_utc(now_utc())
    jobs = list(session.exec(select(Job).where(Job.status.in_(["PENDING", "DEFERRED_BY_BUDGET"]))).all())
    sites = list(session.exec(select(Site)).all())

    problem = build_problem(jobs, sites, now, horizon_hours)
    
    results = {}
    
    # 1. FIFO
    f_res = run_fifo(problem)
    f_carbon = schedule_carbon_g(f_res, problem)
    results["fifo"] = {
        "carbon_kg": f_carbon / 1000,
        "sla": sla_metrics(f_res, problem),
        "re_share": renewable_share_consumed(f_res, problem),
        "savings_pct": 0.0,
    }

    # 2. EDF
    e_res = run_edf(problem)
    e_carbon = schedule_carbon_g(e_res, problem)
    results["edf"] = {
        "carbon_kg": e_carbon / 1000,
        "sla": sla_metrics(e_res, problem),
        "re_share": renewable_share_consumed(e_res, problem),
        "savings_pct": (f_carbon - e_carbon) / f_carbon * 100 if f_carbon > 0 else 0.0,
    }

    # 3. Greedy
    g_res = run_greedy(problem)
    g_carbon = schedule_carbon_g(g_res, problem)
    results["greedy"] = {
        "carbon_kg": g_carbon / 1000,
        "sla": sla_metrics(g_res, problem),
        "re_share": renewable_share_consumed(g_res, problem),
        "savings_pct": (f_carbon - g_carbon) / f_carbon * 100 if f_carbon > 0 else 0.0,
    }

    # 4. CP-SAT (short timeout for comparison endpoint)
    c_res = run_cpsat(problem, max_time_seconds=5)
    c_carbon = schedule_carbon_g(c_res, problem)
    results["cpsat"] = {
        "carbon_kg": c_carbon / 1000,
        "sla": sla_metrics(c_res, problem),
        "re_share": renewable_share_consumed(c_res, problem),
        "savings_pct": (f_carbon - c_carbon) / f_carbon * 100 if f_carbon > 0 else 0.0,
        "gap": c_res.gap,
    }

    return CompareResponse(
        run_id="compare_" + str(int(now.timestamp())),
        horizon_start=now,
        horizon_end=now + __import__("datetime").timedelta(hours=horizon_hours),
        strategies=results,
    )


def _build_summary(run: ScheduleRun, session: Session, include_items: bool = True) -> ScheduleRunSummary:
    items = []
    infeasible = []
    
    if include_items:
        # Fetch items
        db_items = session.exec(select(ScheduleItem).where(ScheduleItem.run_id == run.id)).all()
        # Group by job
        by_job = {}
        for item in db_items:
            if item.job_id not in by_job:
                job = session.get(Job, item.job_id)
                by_job[item.job_id] = {
                    "job_name": job.name if job else "Unknown",
                    "site_id": item.site_id,
                    "planned_carbon_g": 0.0,
                    "planned_energy_kwh": 0.0,
                    "reason": item.reason,
                    "risk_flag": item.risk_flag,
                    "frozen": item.frozen,
                    "segments": [],
                }
            by_job[item.job_id]["planned_carbon_g"] += item.planned_carbon_g
            by_job[item.job_id]["planned_energy_kwh"] += item.planned_energy_kwh
            by_job[item.job_id]["segments"].append(SegmentRead(
                start=item.start_ts,
                end=item.end_ts,
                carbon_g=item.planned_carbon_g,
                energy_kwh=item.planned_energy_kwh,
            ))
            
        for jid, data in by_job.items():
            items.append(ScheduleItemRead(
                job_id=jid,
                **data
            ))

    config = json.loads(run.config_snapshot_json) if run.config_snapshot_json else {}
    status_checks = config.get("constraints_status", [])
    
    # Rebuild constraints if missing
    if not status_checks:
        status_checks = [ConstraintStatus(constraint="?", label="Unknown", passed=True)]

    return ScheduleRunSummary(
        run_id=run.id,
        strategy=run.strategy,
        status=run.status,
        gap=run.gap,
        solve_seconds=run.solve_seconds,
        planned_carbon_kg=run.planned_carbon_kg or 0.0,
        baseline_carbon_kg=run.baseline_carbon_kg or 0.0,
        savings_pct=run.savings_pct or 0.0,
        renewable_share={
            "plan": run.renewable_share_plan or 0.0,
            "baseline": run.renewable_share_baseline or 0.0,
        },
        sla={
            "on_time": run.sla_on_time or 0,
            "total": run.sla_total or 0,
        },
        items=items,
        infeasible=infeasible,
        constraints_status=[ConstraintStatus(**c) for c in status_checks],
        fallback_reason=run.fallback_reason,
    )
