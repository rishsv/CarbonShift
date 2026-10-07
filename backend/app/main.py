"""CarbonShift AI — FastAPI application entry point."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings, validate_all_configs
from app.core.db import create_db_and_tables
from app.core.logging import logger, setup_logging
from app.routers import config, demo, forecast, grid, health, jobs, metrics, schedule, simulate, sites

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown tasks."""
    setup_logging(debug=settings.DEBUG)
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    create_db_and_tables()
    logger.info("Database tables created/verified")
    cfg_ok = validate_all_configs()
    failed = [k for k, v in cfg_ok.items() if not v]
    if failed:
        logger.warning(f"Config load issues: {failed}")
    else:
        logger.info("All configs loaded OK")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="CarbonShift AI",
    description="Carbon-aware workload scheduler for India — hackathon prototype.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN, "http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler (RFC 7807) ───────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Unhandled exception on {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "type": "about:blank",
            "title": "Internal Server Error",
            "detail": str(exc),
            "status": 500,
        },
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(sites.router, prefix="/api/v1", tags=["sites"])
app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
app.include_router(forecast.router, prefix="/api/v1", tags=["forecast"])
app.include_router(grid.router, prefix="/api/v1", tags=["grid"])
app.include_router(schedule.router, prefix="/api/v1", tags=["schedule"])
app.include_router(simulate.router, prefix="/api/v1", tags=["simulate"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(config.router, prefix="/api/v1", tags=["config"])
app.include_router(demo.router, prefix="/api/v1", tags=["demo"])


@app.get("/")
async def root():
    return {"message": f"{settings.APP_NAME} API", "docs": "/docs"}
