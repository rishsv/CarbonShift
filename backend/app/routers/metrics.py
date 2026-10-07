"""Metrics/Impact router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from app.core.db import get_session
from app.models import ScheduleRun
from app.schemas import ImpactResponse
from app.services.accounting import carbon_equivalents

router = APIRouter()


@router.get("/metrics/impact", response_model=ImpactResponse)
def get_impact(session: Session = Depends(get_session)):
    """Aggregate carbon savings across all realized runs."""
    # For hackathon, we sum savings over all primary runs
    stmt = select(ScheduleRun).where(ScheduleRun.parent_run_id == None)
    runs = session.exec(stmt).all()
    
    total_saved = 0.0
    total_re = 0.0
    total_re_count = 0
    on_time = 0
    total_jobs = 0

    for r in runs:
        if r.baseline_carbon_kg and r.planned_carbon_kg:
            total_saved += max(0, r.baseline_carbon_kg - r.planned_carbon_kg)
        if r.renewable_share_plan is not None:
            total_re += r.renewable_share_plan
            total_re_count += 1
        if r.sla_on_time is not None:
            on_time += r.sla_on_time
        if r.sla_total is not None:
            total_jobs += r.sla_total

    avg_re = total_re / total_re_count if total_re_count > 0 else 0.0
    sla_rate = on_time / total_jobs * 100.0 if total_jobs > 0 else 100.0

    eq = carbon_equivalents(total_saved)

    return ImpactResponse(
        total_kg_saved=total_saved,
        is_realized=False,  # Hackathon proto: mostly planned
        renewable_share_avg=avg_re,
        sla_rate=sla_rate,
        equiv_km_driven=eq["km_driven"],
        equiv_tree_years=eq["tree_years"],
        equiv_smartphone_charges=eq["smartphone_charges"],
        indicative_inr_saved=0.0,  # Not calculated in this stub
        runs_count=len(runs),
    )
