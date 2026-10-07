"""Health router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, text

from app.core.config import get_settings, validate_all_configs
from app.core.db import get_session
from app.schemas import HealthResponse
from app.services.forecaster import get_forecaster

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
def health_check(session: Session = Depends(get_session)):
    # Test DB
    db_ok = True
    try:
        session.exec(text("SELECT 1"))
    except Exception:
        db_ok = False

    forecaster = get_forecaster()

    return HealthResponse(
        status="ok",
        data_source=settings.DATA_SOURCE,
        forecaster_version=forecaster._model_version,
        db_ok=db_ok,
        configs_ok=validate_all_configs(),
    )
