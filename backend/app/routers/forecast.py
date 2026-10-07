"""Forecast router — CI forecasts, green windows, accuracy."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

from app.core.time import floor_hour_utc, now_utc
from app.schemas import ForecastPoint, ForecastResponse, GreenWindow
from app.services.forecaster import get_forecaster

router = APIRouter()


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(
    region: str = Query(..., description="Region code: NR|WR|SR|ER|NER"),
    hours: int = Query(default=48, ge=1, le=168),
    issued_at: Optional[datetime] = None,
):
    """Return CI forecast with p10/p50/p90 bands for a region."""
    if issued_at is None:
        issued_at = now_utc()

    forecaster = get_forecaster()
    df = forecaster.forecast(region, issued_at, hours)

    points = []
    for _, row in df.iterrows():
        points.append(ForecastPoint(
            target_ts=row["target_ts"],
            horizon_h=int(row["horizon_h"]),
            ci_p10=float(row["ci_p10"]),
            ci_p50=float(row["ci_p50"]),
            ci_p90=float(row["ci_p90"]),
            renewable_share_p50=float(row["renewable_share_p50"]),
            is_estimated=bool(row.get("is_estimated", True)),
            model_version=str(row.get("model_version", "twin-fallback")),
        ))

    return ForecastResponse(
        region=region,
        issued_at=issued_at,
        points=points,
        data_source=str(row.get("model_version", "twin")) if not df.empty else "twin",
    )


@router.get("/forecast/windows", response_model=list[GreenWindow])
def get_green_windows(
    region: Optional[str] = None,
    hours: int = Query(default=12, ge=1, le=48),
    window_h: float = Query(default=2.0, ge=0.5, le=12.0),
):
    """Return ranked 'green windows' — best upcoming CI windows per site."""
    from app.services.green_windows import find_green_windows
    return find_green_windows(region=region, hours=hours, window_h=window_h)


@router.get("/forecast/accuracy")
def get_forecast_accuracy():
    """Return forecaster accuracy metrics from the last evaluation run."""
    forecaster = get_forecaster()
    return forecaster.accuracy_metrics()
