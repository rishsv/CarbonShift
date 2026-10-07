"""Sites router — CRUD for compute sites."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.core.db import get_session
from app.models import Site
from app.schemas import SiteCreate, SiteRead

router = APIRouter()


def _site_to_read(s: Site) -> SiteRead:
    return SiteRead(
        id=s.id,
        name=s.name,
        region=s.region,
        lat=s.lat,
        lon=s.lon,
        gpu_capacity=json.loads(s.gpu_capacity_json),
        cpu_cores=s.cpu_cores,
        power_cap_kw=s.power_cap_kw,
        pue_base=s.pue_base,
        pue_k=s.pue_k,
        pue_temp_limit_c=s.pue_temp_limit_c,
        allowed_classes=json.loads(s.allowed_classes_json),
        notes=s.notes,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@router.get("/sites", response_model=list[SiteRead])
def list_sites(
    region: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    stmt = select(Site)
    if region:
        stmt = stmt.where(Site.region == region)
    stmt = stmt.offset(offset).limit(limit)
    sites = session.exec(stmt).all()
    return [_site_to_read(s) for s in sites]


@router.get("/sites/{site_id}", response_model=SiteRead)
def get_site(site_id: str, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site {site_id} not found")
    return _site_to_read(site)


@router.post("/sites", response_model=SiteRead, status_code=201)
def create_site(body: SiteCreate, session: Session = Depends(get_session)):
    existing = session.get(Site, body.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Site {body.id} already exists")
    site = Site(
        id=body.id,
        name=body.name,
        region=body.region,
        lat=body.lat,
        lon=body.lon,
        gpu_capacity_json=json.dumps(body.gpu_capacity),
        cpu_cores=body.cpu_cores,
        power_cap_kw=body.power_cap_kw,
        pue_base=body.pue_base,
        pue_k=body.pue_k,
        pue_temp_limit_c=body.pue_temp_limit_c,
        allowed_classes_json=json.dumps(body.allowed_classes),
        notes=body.notes,
    )
    session.add(site)
    session.commit()
    session.refresh(site)
    return _site_to_read(site)


@router.put("/sites/{site_id}", response_model=SiteRead)
def update_site(site_id: str, body: SiteCreate, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site {site_id} not found")
    site.name = body.name
    site.region = body.region
    site.lat = body.lat
    site.lon = body.lon
    site.gpu_capacity_json = json.dumps(body.gpu_capacity)
    site.cpu_cores = body.cpu_cores
    site.power_cap_kw = body.power_cap_kw
    site.pue_base = body.pue_base
    site.pue_k = body.pue_k
    site.pue_temp_limit_c = body.pue_temp_limit_c
    site.allowed_classes_json = json.dumps(body.allowed_classes)
    site.notes = body.notes
    site.updated_at = datetime.utcnow()
    session.add(site)
    session.commit()
    session.refresh(site)
    return _site_to_read(site)
