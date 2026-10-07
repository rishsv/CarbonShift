"""Accounting service — carbon, RE share, SLA, cost, savings, equivalents."""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from app.core.config import load_equivalents, load_tariffs
from app.services.scheduler.types import PlanningProblem, ScheduleResult, Segment


def _slot_energy_kwh(power_kw: float, slot_h: float, pue: float) -> float:
    return power_kw * slot_h * pue


def schedule_carbon_g(
    result: ScheduleResult,
    problem: PlanningProblem,
    use_p50: bool = True,
) -> float:
    """Total planned carbon in gCO2e. If use_p50=False, uses risk-adjusted CI."""
    job_by_id = {j.id: j for j in problem.jobs}
    slot_h = problem.slot_minutes / 60.0
    total = 0.0

    for seg in result.segments:
        job = job_by_id.get(seg.job_id)
        if not job or seg.site_id not in problem.sites:
            continue
        si = problem.site_index(seg.site_id)
        ci_arr = problem.ci_p50[si] if use_p50 else problem.ci_hat[si]
        pue_arr = problem.pue[si]

        for t in range(seg.start_slot, seg.end_slot):
            if t >= problem.horizon_slots:
                break
            ci = float(ci_arr[t])
            pue = float(pue_arr[t])
            e = _slot_energy_kwh(job.power_kw, slot_h, pue)
            total += e * ci

    return total


def schedule_energy_kwh(result: ScheduleResult, problem: PlanningProblem) -> float:
    """Total facility energy in kWh."""
    job_by_id = {j.id: j for j in problem.jobs}
    slot_h = problem.slot_minutes / 60.0
    total = 0.0

    for seg in result.segments:
        job = job_by_id.get(seg.job_id)
        if not job or seg.site_id not in problem.sites:
            continue
        si = problem.site_index(seg.site_id)
        pue_arr = problem.pue[si]

        for t in range(seg.start_slot, seg.end_slot):
            if t >= problem.horizon_slots:
                break
            pue = float(pue_arr[t])
            total += _slot_energy_kwh(job.power_kw, slot_h, pue)

    return total


def renewable_share_consumed(result: ScheduleResult, problem: PlanningProblem) -> float:
    """Weighted average renewable share of consumed energy."""
    job_by_id = {j.id: j for j in problem.jobs}
    slot_h = problem.slot_minutes / 60.0
    total_energy = 0.0
    green_energy = 0.0

    for seg in result.segments:
        job = job_by_id.get(seg.job_id)
        if not job or seg.site_id not in problem.sites:
            continue
        si = problem.site_index(seg.site_id)
        pue_arr = problem.pue[si]
        re_arr = problem.renewable_share[si]

        for t in range(seg.start_slot, seg.end_slot):
            if t >= problem.horizon_slots:
                break
            pue = float(pue_arr[t])
            re = float(re_arr[t])
            e = _slot_energy_kwh(job.power_kw, slot_h, pue)
            total_energy += e
            green_energy += e * re

    if total_energy <= 0:
        return 0.0
    return green_energy / total_energy


def sla_metrics(
    result: ScheduleResult,
    problem: PlanningProblem,
) -> dict:
    """Return SLA metrics: on_time, total, on_time_rate, avg_delay_slots."""
    job_by_id = {j.id: j for j in problem.jobs}
    job_segs: dict[str, list[Segment]] = defaultdict(list)
    for seg in result.segments:
        job_segs[seg.job_id].append(seg)

    on_time = 0
    total = len(problem.jobs)
    delays = []

    for job in problem.jobs:
        segs = job_segs.get(job.id, [])
        if not segs:
            continue  # infeasible job
        end_slot = max(seg.end_slot for seg in segs)
        start_slot = min(seg.start_slot for seg in segs)
        delay = max(0, start_slot - job.release_slot)
        delays.append(delay)
        if end_slot <= job.deadline_slot + 1:  # +1 because end_slot is exclusive
            on_time += 1

    return {
        "on_time": on_time,
        "total": total,
        "on_time_rate": on_time / max(total, 1),
        "avg_delay_slots": float(np.mean(delays)) if delays else 0.0,
        "infeasible": len(result.infeasible_jobs),
    }


def savings_pct(baseline_carbon_g: float, plan_carbon_g: float) -> float:
    """% reduction vs baseline. Positive = savings."""
    if baseline_carbon_g <= 0:
        return 0.0
    return (baseline_carbon_g - plan_carbon_g) / baseline_carbon_g * 100.0


def cost_inr(result: ScheduleResult, problem: PlanningProblem) -> float:
    """Indicative ToD electricity cost in INR."""
    job_by_id = {j.id: j for j in problem.jobs}
    slot_h = problem.slot_minutes / 60.0
    tariff_arr = problem.price  # (n_sites, horizon_slots)
    total_cost = 0.0

    for seg in result.segments:
        job = job_by_id.get(seg.job_id)
        if not job or seg.site_id not in problem.sites:
            continue
        si = problem.site_index(seg.site_id)
        pue_arr = problem.pue[si]

        for t in range(seg.start_slot, seg.end_slot):
            if t >= problem.horizon_slots:
                break
            pue = float(pue_arr[t])
            price = float(tariff_arr[si, t])
            e = _slot_energy_kwh(job.power_kw, slot_h, pue)
            total_cost += e * price

    return total_cost


def carbon_equivalents(carbon_kg: float) -> dict:
    """Convert kg CO2 saved to human-readable equivalents."""
    eq = load_equivalents()
    km = carbon_kg * eq["km_per_kg_co2"]["value"]
    trees = carbon_kg / eq["tree_kg_co2_per_year"]["value"]
    phones = carbon_kg * eq["smartphone_charges_per_kg_co2"]["value"]
    return {
        "km_driven": round(km, 1),
        "tree_years": round(trees, 2),
        "smartphone_charges": round(phones, 0),
        "km_label": eq["km_per_kg_co2"]["label"],
        "tree_label": eq["tree_kg_co2_per_year"]["label"],
        "phone_label": eq["smartphone_charges_per_kg_co2"]["label"],
    }


def per_job_carbon(
    result: ScheduleResult,
    problem: PlanningProblem,
) -> dict[str, float]:
    """Return {job_id: planned_carbon_g} for all scheduled jobs."""
    job_by_id = {j.id: j for j in problem.jobs}
    slot_h = problem.slot_minutes / 60.0
    result_dict: dict[str, float] = defaultdict(float)

    for seg in result.segments:
        job = job_by_id.get(seg.job_id)
        if not job or seg.site_id not in problem.sites:
            continue
        si = problem.site_index(seg.site_id)
        ci_arr = problem.ci_p50[si]
        pue_arr = problem.pue[si]

        for t in range(seg.start_slot, seg.end_slot):
            if t >= problem.horizon_slots:
                break
            ci = float(ci_arr[t])
            pue = float(pue_arr[t])
            e = _slot_energy_kwh(job.power_kw, slot_h, pue)
            result_dict[seg.job_id] += e * ci

    return dict(result_dict)


def per_job_energy(
    result: ScheduleResult,
    problem: PlanningProblem,
) -> dict[str, float]:
    """Return {job_id: planned_energy_kwh} for all scheduled jobs."""
    job_by_id = {j.id: j for j in problem.jobs}
    slot_h = problem.slot_minutes / 60.0
    result_dict: dict[str, float] = defaultdict(float)

    for seg in result.segments:
        job = job_by_id.get(seg.job_id)
        if not job or seg.site_id not in problem.sites:
            continue
        si = problem.site_index(seg.site_id)
        pue_arr = problem.pue[si]

        for t in range(seg.start_slot, seg.end_slot):
            if t >= problem.horizon_slots:
                break
            pue = float(pue_arr[t])
            result_dict[seg.job_id] += _slot_energy_kwh(job.power_kw, slot_h, pue)

    return dict(result_dict)
