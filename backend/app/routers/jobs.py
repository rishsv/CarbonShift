"""Jobs router — CRUD, bulk import, NL parse, energy estimate."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from sqlmodel import Session, select

from app.core.db import get_session
from app.models import Job, JobDependency
from app.schemas import JobCreate, JobEstimateRequest, JobEstimateResponse, JobRead
from app.services.energy import estimate_job

router = APIRouter()

VALID_STATUSES = {"PENDING", "SCHEDULED", "RUNNING", "COMPLETED", "INFEASIBLE", "DEFERRED_BY_BUDGET"}


def _job_to_read(j: Job) -> JobRead:
    return JobRead(
        id=j.id,
        name=j.name,
        archetype=j.archetype,
        team=j.team,
        priority=j.priority,
        status=j.status,
        release_ts=j.release_ts,
        deadline_ts=j.deadline_ts,
        duration_h=j.duration_h,
        gpus=j.gpus,
        gpu_type=j.gpu_type,
        cpu_cores=j.cpu_cores,
        util=j.util,
        preemptible=j.preemptible,
        max_interruptions=j.max_interruptions,
        allowed_sites=json.loads(j.allowed_sites_json),
        data_residency=j.data_residency,
        data_class=j.data_class,
        green_only=j.green_only,
        data_gb=j.data_gb,
        home_site=j.home_site,
        energy_kwh=j.energy_kwh,
        power_kw=j.power_kw,
        created_at=j.created_at,
    )


def _attach_energy(j: Job) -> None:
    """Compute and attach energy/power estimates to a Job model."""
    est = estimate_job(j.gpus, j.gpu_type, j.cpu_cores, j.util, j.duration_h)
    j.energy_kwh = est["facility_energy_kwh"]
    j.power_kw = est["power_kw"]


@router.get("/jobs", response_model=list[JobRead])
def list_jobs(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    team: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    session: Session = Depends(get_session),
):
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status)
    if priority:
        stmt = stmt.where(Job.priority == priority)
    if team:
        stmt = stmt.where(Job.team == team)
    if search:
        stmt = stmt.where(Job.name.contains(search))
    stmt = stmt.offset(offset).limit(limit).order_by(Job.created_at.desc())
    jobs = session.exec(stmt).all()
    return [_job_to_read(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _job_to_read(job)


@router.post("/jobs", response_model=JobRead, status_code=201)
def create_job(body: JobCreate, session: Session = Depends(get_session)):
    # Validate dependencies exist
    for dep_id in body.depends_on:
        if not session.get(Job, dep_id):
            raise HTTPException(status_code=422, detail=f"Dependency job {dep_id} not found")

    job = Job(
        name=body.name,
        archetype=body.archetype,
        team=body.team,
        priority=body.priority,
        release_ts=body.release_ts.replace(tzinfo=None) if body.release_ts.tzinfo else body.release_ts,
        deadline_ts=body.deadline_ts.replace(tzinfo=None) if body.deadline_ts.tzinfo else body.deadline_ts,
        duration_h=body.duration_h,
        gpus=body.gpus,
        gpu_type=body.gpu_type,
        cpu_cores=body.cpu_cores,
        util=body.util,
        preemptible=body.preemptible,
        max_interruptions=body.max_interruptions,
        checkpoint_overhead_pct=body.checkpoint_overhead_pct,
        allowed_sites_json=json.dumps(body.allowed_sites),
        data_residency=body.data_residency,
        data_class=body.data_class,
        green_only=body.green_only,
        data_gb=body.data_gb,
        home_site=body.home_site,
    )
    _attach_energy(job)
    session.add(job)
    session.flush()  # get the id

    for dep_id in body.depends_on:
        dep = JobDependency(job_id=job.id, depends_on_job_id=dep_id)
        session.add(dep)

    session.commit()
    session.refresh(job)
    return _job_to_read(job)


@router.put("/jobs/{job_id}", response_model=JobRead)
def update_job(job_id: str, body: JobCreate, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job.name = body.name
    job.archetype = body.archetype
    job.team = body.team
    job.priority = body.priority
    job.release_ts = body.release_ts.replace(tzinfo=None) if body.release_ts.tzinfo else body.release_ts
    job.deadline_ts = body.deadline_ts.replace(tzinfo=None) if body.deadline_ts.tzinfo else body.deadline_ts
    job.duration_h = body.duration_h
    job.gpus = body.gpus
    job.gpu_type = body.gpu_type
    job.cpu_cores = body.cpu_cores
    job.util = body.util
    job.preemptible = body.preemptible
    job.max_interruptions = body.max_interruptions
    job.allowed_sites_json = json.dumps(body.allowed_sites)
    job.data_residency = body.data_residency
    job.data_class = body.data_class
    job.green_only = body.green_only
    job.data_gb = body.data_gb
    job.home_site = body.home_site
    job.updated_at = datetime.utcnow()
    _attach_energy(job)
    session.add(job)
    session.commit()
    session.refresh(job)
    return _job_to_read(job)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    # Remove dependencies
    deps = session.exec(select(JobDependency).where(JobDependency.job_id == job_id)).all()
    for d in deps:
        session.delete(d)
    session.delete(job)
    session.commit()


@router.post("/jobs/bulk", response_model=list[JobRead], status_code=201)
def bulk_import_jobs(
    jobs: list[JobCreate] = Body(...),
    session: Session = Depends(get_session),
):
    created = []
    for body in jobs:
        job = Job(
            name=body.name,
            archetype=body.archetype,
            team=body.team,
            priority=body.priority,
            release_ts=body.release_ts.replace(tzinfo=None) if body.release_ts.tzinfo else body.release_ts,
            deadline_ts=body.deadline_ts.replace(tzinfo=None) if body.deadline_ts.tzinfo else body.deadline_ts,
            duration_h=body.duration_h,
            gpus=body.gpus,
            gpu_type=body.gpu_type,
            cpu_cores=body.cpu_cores,
            util=body.util,
            preemptible=body.preemptible,
            max_interruptions=body.max_interruptions,
            allowed_sites_json=json.dumps(body.allowed_sites),
            data_residency=body.data_residency,
            data_class=body.data_class,
            green_only=body.green_only,
            data_gb=body.data_gb,
            home_site=body.home_site,
        )
        _attach_energy(job)
        session.add(job)
        created.append(job)

    session.commit()
    for j in created:
        session.refresh(j)
    return [_job_to_read(j) for j in created]


@router.post("/jobs/estimate", response_model=JobEstimateResponse)
def estimate_job_endpoint(body: JobEstimateRequest):
    est = estimate_job(body.gpus, body.gpu_type, body.cpu_cores, body.util, body.duration_h, body.site_id)
    return JobEstimateResponse(
        power_kw=est["power_kw"],
        it_energy_kwh=est["it_energy_kwh"],
        facility_energy_kwh=est["facility_energy_kwh"],
        pue_used=est["pue_used"],
    )


@router.post("/jobs/nl")
def nl_parse_job(text: str = Body(..., embed=True)):
    """Parse a natural-language job description into a draft job spec."""
    from app.services.nl_parser import parse_nl_job
    return parse_nl_job(text)
