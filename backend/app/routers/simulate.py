"""Simulate/What-If router."""
from __future__ import annotations

import copy

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.core.db import get_session
from app.models import ScheduleRun
from app.schemas import WhatIfRequest, WhatIfResponse
from app.services.scheduler.runner import execute_schedule

router = APIRouter()


@router.post("/simulate/whatif", response_model=WhatIfResponse)
def run_what_if(
    body: WhatIfRequest,
    session: Session = Depends(get_session),
):
    """Run a scenario by cloning state, mutating params, and re-solving."""
    base_run = session.get(ScheduleRun, body.run_id)
    if not base_run:
        raise HTTPException(status_code=404, detail="Base run not found")

    # In a real implementation, we would clone the PlanningProblem,
    # mutate it based on the multipliers (solar/wind capacity, deadline extensions, etc.),
    # and re-run CP-SAT.
    # For this hackathon stub, we'll execute a fast schedule with the current DB state
    # but varying the strategy to simulate a result.
    
    # Actually execute a new run linked to the parent
    new_run = execute_schedule(
        session=session,
        strategy="cpsat",  # always use cpsat for what-if
        horizon_hours=int((base_run.horizon_end - base_run.horizon_start).total_seconds() / 3600),
        risk_lambda=body.risk_lambda,
        allow_spatial=body.allow_spatial,
        carbon_budget_kg=body.carbon_budget_kg,
        solver_seconds=5,  # fast solve for interactive what-if
        parent_run_id=base_run.id,
    )

    base_carbon = base_run.planned_carbon_kg or 0.0
    new_carbon = new_run.planned_carbon_kg or 0.0

    return WhatIfResponse(
        delta_carbon_kg=new_carbon - base_carbon,
        delta_savings_pct=(new_run.savings_pct or 0.0) - (base_run.savings_pct or 0.0),
        delta_renewable_share=(new_run.renewable_share_plan or 0.0) - (base_run.renewable_share_plan or 0.0),
        new_sla={"on_time": new_run.sla_on_time or 0, "total": new_run.sla_total or 0},
        new_carbon_kg=new_carbon,
        new_savings_pct=new_run.savings_pct or 0.0,
    )
