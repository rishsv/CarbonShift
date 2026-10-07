"""Grid data router — current conditions and history."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from app.core.config import load_regions_config
from app.core.time import now_utc
from app.services.carbon_sources.twin import TwinSource
from app.services.carbon_sources.electricitymaps import get_em_client

router = APIRouter()
_twin = TwinSource()
REGIONS = list(load_regions_config().keys())


@router.get("/grid/now")
def get_grid_now():
    """Current CI and mix for all regions."""
    now = now_utc()
    result = {}
    em = get_em_client()
    for region in REGIONS:
        obs = None
        if em:
            ci_data = em.get_carbon_intensity_now(region)
            mix_data = em.get_power_breakdown_now(region)
            if ci_data and mix_data:
                obs = {**ci_data, **mix_data}
        
        if not obs:
            obs = _twin.latest(region)
            
        if obs:
            result[region] = {
                "ts": obs.get("ts"),
                "ci_g_per_kwh": obs.get("ci_g_per_kwh"),
                "renewable_share": obs.get("renewable_share"),
                "share_solar": obs.get("share_solar", 0),
                "share_wind": obs.get("share_wind", 0),
                "share_hydro": obs.get("share_hydro", 0),
                "share_thermal": obs.get("share_thermal", 0),
                "demand_mw": obs.get("demand_mw", 0),
                "is_estimated": obs.get("is_estimated", True),
                "source": obs.get("source", "twin"),
            }
    return result


@router.get("/grid/history")
def get_grid_history(
    region: str = Query(...),
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    hours: int = Query(default=48, ge=1, le=720),
):
    """Historical CI and mix for a region."""
    if to_ts is None:
        to_ts = now_utc()
    if from_ts is None:
        from_ts = to_ts - timedelta(hours=hours)

    em = get_em_client()
    records = []
    
    if em:
        em_records = em.get_carbon_intensity_history(region, from_ts, to_ts)
        if em_records:
            return em_records
            
    df = _twin.history(region, from_ts, to_ts)
    if df.empty:
        return []

    for _, row in df.iterrows():
        records.append({
            "ts": row["ts"],
            "region": region,
            "ci_g_per_kwh": row.get("ci_g_per_kwh"),
            "renewable_share": row.get("renewable_share"),
            "share_solar": row.get("share_solar", 0),
            "share_wind": row.get("share_wind", 0),
            "share_hydro": row.get("share_hydro", 0),
            "share_nuclear": row.get("share_nuclear", 0),
            "share_thermal": row.get("share_thermal", 0),
            "demand_mw": row.get("demand_mw", 0),
            "is_estimated": row.get("is_estimated", True),
            "source": row.get("source", "twin"),
        })
    return records
